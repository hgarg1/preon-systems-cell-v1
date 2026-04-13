from __future__ import annotations

from math import cos, sin, tau
from random import Random
from typing import Any

from preon_systems_cell.models import (
    CellState,
    CellStatus,
    CytosolState,
    EnergyState,
    Event,
    EventType,
    PopulationMetrics,
    Scenario,
    StepSnapshot,
    StepTransition,
    TerminationReason,
    WorldState,
    build_initial_state,
)


ENGINE_VERSION = "0.3.0"


def _living_cells(state: WorldState) -> list[CellState]:
    return [cell for cell in state.cells if cell.status == CellStatus.ALIVE and cell.alive]


def _metrics(state: WorldState) -> PopulationMetrics:
    living = _living_cells(state)
    dead_count = sum(1 for cell in state.cells if cell.status == CellStatus.DEAD)
    divided_count = sum(1 for cell in state.cells if cell.status == CellStatus.DIVIDED)
    return PopulationMetrics(
        step=state.step,
        time=state.time,
        population_count=len(state.cells),
        alive_count=len(living),
        dead_count=dead_count,
        divided_count=divided_count,
        division_count_total=divided_count,
        total_atp=sum(cell.energy.atp for cell in living),
        total_biomass=sum(cell.biomass for cell in living),
        environment_glucose=state.environment.glucose_concentration,
        environment_electron_acceptor=state.environment.electron_acceptor_concentration,
        toxicity=state.environment.toxicity,
    )


def _snapshot(state: WorldState) -> StepSnapshot:
    metrics = _metrics(state)
    return StepSnapshot(**metrics.model_dump(), state=state.model_copy(deep=True))


def metrics_for_state(state: WorldState) -> PopulationMetrics:
    return _metrics(state)


def snapshot_for_state(state: WorldState) -> StepSnapshot:
    return _snapshot(state)


def _event(state: WorldState, event_type: EventType, message: str, **values: Any) -> Event:
    return Event(
        step=state.step,
        time=state.time,
        type=event_type,
        message=message,
        values=values,
    )


def _cell_event(state: WorldState, cell: CellState, event_type: EventType, message: str, **values: Any) -> Event:
    return _event(state, event_type, message, cell_id=cell.id, **values)


def _apply_environment_supply(state: WorldState, scenario: Scenario) -> None:
    env = state.environment
    if env.glucose_concentration < env.basal_glucose_level:
        replenishment = min(
            scenario.environment.glucose_replenishment_rate * scenario.simulation.dt,
            env.basal_glucose_level - env.glucose_concentration,
        )
        env.glucose_concentration += replenishment
    if env.electron_acceptor_concentration < env.basal_electron_acceptor_level:
        electron_acceptor_replenishment = min(
            scenario.environment.electron_acceptor_replenishment_rate * scenario.simulation.dt,
            env.basal_electron_acceptor_level - env.electron_acceptor_concentration,
        )
        env.electron_acceptor_concentration += electron_acceptor_replenishment
    env.toxicity += scenario.environment.toxicity_rate * scenario.simulation.dt


def _apply_transport(state: WorldState, scenario: Scenario, cell: CellState, events: list[Event]) -> None:
    env = state.environment
    if not cell.alive or env.glucose_concentration <= cell.cytosol.glucose:
        return

    membrane_factor = max(cell.membrane_integrity, 0.05)
    gradient = env.glucose_concentration - cell.cytosol.glucose
    flux_cap = (
        scenario.transport.passive_diffusion_rate
        * cell.glucose_transporter_density
        * membrane_factor
        * scenario.simulation.dt
    )
    imported = min(gradient, flux_cap, env.glucose_concentration)
    if imported <= 0:
        return

    environment_before = env.glucose_concentration
    cytosol_before = cell.cytosol.glucose
    env.glucose_concentration -= imported
    cell.cytosol.glucose += imported
    events.append(
        _cell_event(
            state,
            cell,
            EventType.TRANSPORT,
            "Imported glucose by passive membrane transport",
            imported_glucose=imported,
            gradient=gradient,
            environment_glucose_before=environment_before,
            environment_glucose_after=env.glucose_concentration,
            cytosol_glucose_before=cytosol_before,
            cytosol_glucose_after=cell.cytosol.glucose,
        )
    )


def _apply_metabolism(state: WorldState, scenario: Scenario, cell: CellState, events: list[Event]) -> None:
    if not cell.alive or cell.cytosol.glucose <= 0:
        return

    processed = min(
        cell.cytosol.glucose,
        scenario.metabolism.glucose_processing_cap_per_step * scenario.simulation.dt,
    )
    if processed <= 0:
        return

    pyruvate_generated = processed * 2.0
    atp_generated = processed * 2.0
    nadh_generated = processed * 2.0
    cell.cytosol.glucose -= processed
    cell.cytosol.pyruvate += pyruvate_generated
    cell.cytosol.nadh += nadh_generated
    cell.energy.atp += atp_generated
    cell.energy.adp = max(cell.energy.adp - atp_generated, 0)
    events.append(
        _cell_event(
            state,
            cell,
            EventType.GLYCOLYSIS,
            "Converted cytosolic glucose through glycolysis",
            glucose_processed=processed,
            pyruvate_generated=pyruvate_generated,
            atp_generated=atp_generated,
            nadh_generated=nadh_generated,
        )
    )


def _apply_pyruvate_oxidation(state: WorldState, scenario: Scenario, cell: CellState, events: list[Event]) -> None:
    cytosol = cell.cytosol
    cap = scenario.metabolism.pyruvate_oxidation_cap_per_step * scenario.simulation.dt
    if not cell.alive or cap <= 0 or cytosol.pyruvate <= 0 or cytosol.nad_plus <= 0:
        return

    oxidized = min(cytosol.pyruvate, cytosol.nad_plus, cap)
    if oxidized <= 0:
        return

    cytosol.pyruvate -= oxidized
    cytosol.nad_plus -= oxidized
    cytosol.acetyl_coa += oxidized
    cytosol.co2 += oxidized
    cytosol.nadh += oxidized
    events.append(
        _cell_event(
            state,
            cell,
            EventType.PYRUVATE_OXIDATION,
            "Oxidized pyruvate into acetyl-CoA",
            pyruvate_oxidized=oxidized,
            acetyl_coa_generated=oxidized,
            co2_generated=oxidized,
            nadh_generated=oxidized,
            nad_plus_consumed=oxidized,
        )
    )


def _apply_tca_cycle(state: WorldState, scenario: Scenario, cell: CellState, events: list[Event]) -> None:
    cytosol = cell.cytosol
    cap = scenario.metabolism.tca_cycle_cap_per_step * scenario.simulation.dt
    if (
        not cell.alive
        or cap <= 0
        or cytosol.acetyl_coa <= 0
        or cytosol.nad_plus < 3
        or cytosol.fad <= 0
        or cell.energy.adp <= 0
    ):
        return

    turns = min(cytosol.acetyl_coa, cytosol.nad_plus / 3.0, cytosol.fad, cell.energy.adp, cap)
    if turns <= 0:
        return

    cytosol.acetyl_coa -= turns
    cytosol.nad_plus -= turns * 3.0
    cytosol.fad -= turns
    cell.energy.adp -= turns
    cytosol.co2 += turns * 2.0
    cytosol.nadh += turns * 3.0
    cytosol.fadh2 += turns
    cell.energy.atp += turns
    events.append(
        _cell_event(
            state,
            cell,
            EventType.TCA_CYCLE,
            "Processed acetyl-CoA through the citric acid cycle",
            tca_turns=turns,
            acetyl_coa_consumed=turns,
            co2_generated=turns * 2.0,
            nadh_generated=turns * 3.0,
            fadh2_generated=turns,
            atp_generated=turns,
        )
    )


def _apply_electron_transport(state: WorldState, scenario: Scenario, cell: CellState, events: list[Event]) -> None:
    cytosol = cell.cytosol
    env = state.environment
    cap = scenario.metabolism.electron_transport_cap_per_step * scenario.simulation.dt
    if not cell.alive or cap <= 0 or env.electron_acceptor_concentration <= 0:
        return

    remaining_capacity = cap
    nadh_oxidized = min(cytosol.nadh, env.electron_acceptor_concentration, remaining_capacity)
    if nadh_oxidized > 0:
        cytosol.nadh -= nadh_oxidized
        cytosol.nad_plus += nadh_oxidized
        env.electron_acceptor_concentration -= nadh_oxidized
        cytosol.membrane_gradient += nadh_oxidized * scenario.metabolism.gradient_per_nadh
        remaining_capacity -= nadh_oxidized

    fadh2_oxidized = min(cytosol.fadh2, env.electron_acceptor_concentration, remaining_capacity)
    if fadh2_oxidized > 0:
        cytosol.fadh2 -= fadh2_oxidized
        cytosol.fad += fadh2_oxidized
        env.electron_acceptor_concentration -= fadh2_oxidized
        cytosol.membrane_gradient += fadh2_oxidized * scenario.metabolism.gradient_per_fadh2

    if nadh_oxidized <= 0 and fadh2_oxidized <= 0:
        return

    events.append(
        _cell_event(
            state,
            cell,
            EventType.ELECTRON_TRANSPORT,
            "Moved carrier electrons onto the terminal acceptor",
            nadh_oxidized=nadh_oxidized,
            fadh2_oxidized=fadh2_oxidized,
            electron_acceptor_consumed=nadh_oxidized + fadh2_oxidized,
            gradient_generated=(
                nadh_oxidized * scenario.metabolism.gradient_per_nadh
                + fadh2_oxidized * scenario.metabolism.gradient_per_fadh2
            ),
        )
    )


def _apply_oxidative_phosphorylation(state: WorldState, scenario: Scenario, cell: CellState, events: list[Event]) -> None:
    cytosol = cell.cytosol
    cap = scenario.metabolism.oxidative_phosphorylation_cap_per_step * scenario.simulation.dt
    atp_per_gradient = scenario.metabolism.atp_per_gradient
    if not cell.alive or cap <= 0 or atp_per_gradient <= 0 or cytosol.membrane_gradient <= 0 or cell.energy.adp <= 0:
        return

    gradient_used = min(cytosol.membrane_gradient, cell.energy.adp / atp_per_gradient, cap)
    if gradient_used <= 0:
        return

    atp_generated = gradient_used * atp_per_gradient
    cytosol.membrane_gradient -= gradient_used
    cell.energy.atp += atp_generated
    cell.energy.adp -= atp_generated
    events.append(
        _cell_event(
            state,
            cell,
            EventType.OXIDATIVE_PHOSPHORYLATION,
            "Converted membrane gradient into ATP",
            gradient_used=gradient_used,
            atp_generated=atp_generated,
        )
    )


def _apply_membrane_gradient_decay(cell: CellState, scenario: Scenario) -> None:
    if not cell.alive:
        return
    gradient_loss = scenario.metabolism.membrane_gradient_decay * scenario.simulation.dt
    if gradient_loss <= 0:
        return
    cell.cytosol.membrane_gradient = max(cell.cytosol.membrane_gradient - gradient_loss, 0)


def _apply_maintenance_and_repair(state: WorldState, scenario: Scenario, cell: CellState, events: list[Event]) -> None:
    if not cell.alive:
        return

    basal_cost = scenario.maintenance.basal_atp_cost * scenario.simulation.dt
    cell.energy.atp -= basal_cost
    cell.energy.adp += basal_cost
    events.append(_cell_event(state, cell, EventType.MAINTENANCE, "Paid basal ATP maintenance cost", atp_cost=basal_cost))

    membrane_decay = scenario.maintenance.membrane_decay * scenario.simulation.dt
    cell.membrane_integrity = max(cell.membrane_integrity - membrane_decay, 0)
    if membrane_decay > 0:
        events.append(_cell_event(state, cell, EventType.DAMAGE, "Membrane integrity decayed", membrane_loss=membrane_decay))

    repair_target = min(1 - cell.membrane_integrity, scenario.maintenance.repair_rate * scenario.simulation.dt)
    if repair_target > 0:
        affordable_repair = min(repair_target, cell.energy.atp / max(scenario.maintenance.repair_atp_cost, 1e-9))
        if affordable_repair > 0:
            actual_cost = affordable_repair * scenario.maintenance.repair_atp_cost
            cell.energy.atp -= actual_cost
            cell.energy.adp += actual_cost
            cell.membrane_integrity = min(cell.membrane_integrity + affordable_repair, 1)
            events.append(
                _cell_event(
                    state,
                    cell,
                    EventType.REPAIR,
                    "Repaired membrane damage",
                    repaired=affordable_repair,
                    atp_cost=actual_cost,
                )
            )


def _apply_growth_and_division(
    state: WorldState,
    scenario: Scenario,
    cell: CellState,
    rng: Random,
    events: list[Event],
) -> None:
    if not cell.alive or scenario.maintenance.growth_atp_cost <= 0 or scenario.maintenance.biomass_gain_per_growth <= 0:
        return
    if cell.energy.atp < (scenario.cell.maintenance_threshold_atp * 1.5):
        return

    growth_cost = scenario.maintenance.growth_atp_cost * scenario.simulation.dt
    if cell.energy.atp < growth_cost:
        return

    cell.energy.atp -= growth_cost
    cell.energy.adp += growth_cost
    biomass_gain = scenario.maintenance.biomass_gain_per_growth * scenario.simulation.dt
    cell.biomass += biomass_gain
    events.append(
        _cell_event(
            state,
            cell,
            EventType.GROWTH,
            "Invested ATP into biomass growth",
            atp_cost=growth_cost,
            biomass_gain=biomass_gain,
        )
    )

    if cell.biomass < scenario.cell.division_biomass_threshold:
        return

    if len(_living_cells(state)) >= scenario.cell.max_population:
        events.append(
            _cell_event(
                state,
                cell,
                EventType.POPULATION_CAP,
                "Population cap prevented division",
                max_population=scenario.cell.max_population,
                biomass=cell.biomass,
            )
        )
        return

    daughters = _divide_cell(state, cell, rng)
    state.cells.extend(daughters)
    daughter_ids = [daughter.id for daughter in daughters]
    events.append(
        _cell_event(
            state,
            cell,
            EventType.DIVISION,
            "Completed cell division",
            parent_id=cell.id,
            daughter_ids=daughter_ids,
            generation=cell.generation + 1,
            parent_biomass=cell.biomass,
            daughter_biomass=daughters[0].biomass,
            daughter_atp=daughters[0].energy.atp,
            daughter_adp=daughters[0].energy.adp,
        )
    )


def _divide_cell(state: WorldState, cell: CellState, rng: Random) -> list[CellState]:
    cell.division_count += 1
    cell.status = CellStatus.DIVIDED
    cell.alive = False

    angle = rng.uniform(0, tau)
    radius = 0.35 + (cell.generation * 0.05)
    vertical_offset = rng.uniform(-0.12, 0.12)
    offsets = [
        (cos(angle) * radius, vertical_offset, sin(angle) * radius),
        (-cos(angle) * radius, -vertical_offset, -sin(angle) * radius),
    ]

    daughters = []
    for index, (dx, dy, dz) in enumerate(offsets, start=1):
        daughters.append(
            CellState(
                id=f"{cell.id}.{index}",
                parent_id=cell.id,
                generation=cell.generation + 1,
                birth_step=state.step,
                death_step=None,
                status=CellStatus.ALIVE,
                name=cell.name,
                energy=EnergyState(atp=cell.energy.atp * 0.5, adp=cell.energy.adp * 0.5),
                cytosol=_halve_cytosol(cell.cytosol),
                waste=cell.waste * 0.5,
                membrane_integrity=cell.membrane_integrity,
                glucose_transporter_density=cell.glucose_transporter_density,
                biomass=cell.biomass * 0.5,
                x=cell.x + dx,
                y=cell.y + dy,
                z=cell.z + dz,
            )
        )
    return daughters


def _halve_cytosol(cytosol: CytosolState) -> CytosolState:
    return CytosolState(
        glucose=cytosol.glucose * 0.5,
        pyruvate=cytosol.pyruvate * 0.5,
        nadh=cytosol.nadh * 0.5,
        acetyl_coa=cytosol.acetyl_coa * 0.5,
        nad_plus=cytosol.nad_plus * 0.5,
        fad=cytosol.fad * 0.5,
        fadh2=cytosol.fadh2 * 0.5,
        co2=cytosol.co2 * 0.5,
        membrane_gradient=cytosol.membrane_gradient * 0.5,
    )


def _apply_movement(state: WorldState, scenario: Scenario, cell: CellState, rng: Random, events: list[Event]) -> None:
    if not cell.alive or not scenario.movement.enabled or scenario.movement.drift_strength <= 0:
        return

    mobility = (
        scenario.movement.drift_strength
        * scenario.simulation.dt
        * max(cell.membrane_integrity, 0.1)
        * (1.0 + (cell.energy.atp * scenario.movement.atp_influence))
    )
    dx = rng.uniform(-1.0, 1.0) * mobility
    dy = rng.uniform(-1.0, 1.0) * mobility * scenario.movement.vertical_drift
    dz = rng.uniform(-1.0, 1.0) * mobility

    cell.x += dx
    cell.y += dy
    cell.z += dz
    events.append(
        _cell_event(
            state,
            cell,
            EventType.MOVEMENT,
            "Cell drifted through 3D space",
            delta_x=dx,
            delta_y=dy,
            delta_z=dz,
            distance=(dx**2 + dy**2 + dz**2) ** 0.5,
        )
    )


def _check_cell_invariants_and_death(
    state: WorldState,
    scenario: Scenario,
    cell: CellState,
    events: list[Event],
) -> TerminationReason | None:
    if cell.energy.atp < 0:
        events.append(_cell_event(state, cell, EventType.INVARIANT, "ATP dropped below zero", atp=cell.energy.atp))
        cell.energy.atp = 0
    if cell.cytosol.glucose < 0:
        events.append(
            _cell_event(state, cell, EventType.INVARIANT, "Cytosolic glucose dropped below zero", glucose=cell.cytosol.glucose)
        )
        cell.cytosol.glucose = 0
    if cell.cytosol.pyruvate < 0:
        events.append(_cell_event(state, cell, EventType.INVARIANT, "Pyruvate dropped below zero", pyruvate=cell.cytosol.pyruvate))
        cell.cytosol.pyruvate = 0
    if cell.cytosol.nadh < 0:
        events.append(_cell_event(state, cell, EventType.INVARIANT, "NADH dropped below zero", nadh=cell.cytosol.nadh))
        cell.cytosol.nadh = 0
    if cell.cytosol.acetyl_coa < 0:
        events.append(
            _cell_event(state, cell, EventType.INVARIANT, "Acetyl-CoA dropped below zero", acetyl_coa=cell.cytosol.acetyl_coa)
        )
        cell.cytosol.acetyl_coa = 0
    if cell.cytosol.nad_plus < 0:
        events.append(_cell_event(state, cell, EventType.INVARIANT, "NAD+ dropped below zero", nad_plus=cell.cytosol.nad_plus))
        cell.cytosol.nad_plus = 0
    if cell.cytosol.fad < 0:
        events.append(_cell_event(state, cell, EventType.INVARIANT, "FAD dropped below zero", fad=cell.cytosol.fad))
        cell.cytosol.fad = 0
    if cell.cytosol.fadh2 < 0:
        events.append(_cell_event(state, cell, EventType.INVARIANT, "FADH2 dropped below zero", fadh2=cell.cytosol.fadh2))
        cell.cytosol.fadh2 = 0
    if cell.cytosol.co2 < 0:
        events.append(_cell_event(state, cell, EventType.INVARIANT, "CO2 dropped below zero", co2=cell.cytosol.co2))
        cell.cytosol.co2 = 0
    if cell.cytosol.membrane_gradient < 0:
        events.append(
            _cell_event(
                state,
                cell,
                EventType.INVARIANT,
                "Membrane gradient dropped below zero",
                membrane_gradient=cell.cytosol.membrane_gradient,
            )
        )
        cell.cytosol.membrane_gradient = 0

    if cell.energy.atp <= 0:
        _mark_dead(state, cell, TerminationReason.ATP_DEPLETION, events)
        return TerminationReason.ATP_DEPLETION
    if (
        cell.energy.atp < scenario.cell.maintenance_threshold_atp
        and cell.cytosol.glucose <= 0
        and state.environment.glucose_concentration <= 0
    ):
        _mark_dead(state, cell, TerminationReason.STARVATION, events)
        return TerminationReason.STARVATION
    if cell.membrane_integrity <= 0:
        _mark_dead(state, cell, TerminationReason.MEMBRANE_FAILURE, events)
        return TerminationReason.MEMBRANE_FAILURE
    return None


def _mark_dead(state: WorldState, cell: CellState, reason: TerminationReason, events: list[Event]) -> None:
    if cell.status != CellStatus.ALIVE:
        return
    cell.status = CellStatus.DEAD
    cell.alive = False
    cell.death_step = state.step
    events.append(
        _cell_event(
            state,
            cell,
            EventType.DEATH,
            "Cell died",
            reason=reason.value,
            final_atp=cell.energy.atp,
            final_biomass=cell.biomass,
        )
    )


def _check_environment_invariants(state: WorldState, events: list[Event]) -> None:
    env = state.environment
    if env.glucose_concentration < 0:
        events.append(
            _event(
                state,
                EventType.INVARIANT,
                "Environment glucose dropped below zero",
                environment_glucose=env.glucose_concentration,
            )
        )
        env.glucose_concentration = 0
    if env.electron_acceptor_concentration < 0:
        events.append(
            _event(
                state,
                EventType.INVARIANT,
                "Environment electron acceptor dropped below zero",
                environment_electron_acceptor=env.electron_acceptor_concentration,
            )
        )
        env.electron_acceptor_concentration = 0


def _check_global_termination(state: WorldState, events: list[Event]) -> TerminationReason | None:
    living = _living_cells(state)
    total_living_biomass = sum(cell.biomass for cell in living)
    total_living_waste = sum(cell.waste for cell in living)
    if state.environment.toxicity + total_living_waste >= max(10.0, total_living_biomass * 3):
        for cell in living:
            _mark_dead(state, cell, TerminationReason.TOXICITY, events)
        return TerminationReason.TOXICITY
    if not _living_cells(state):
        return TerminationReason.ALL_CELLS_DEAD
    return None


def _cell_by_id(state: WorldState, cell_id: str) -> CellState | None:
    return next((cell for cell in state.cells if cell.id == cell_id), None)


def step_simulation(state: WorldState, scenario: Scenario, rng: Random) -> StepTransition:
    next_state = state.model_copy(deep=True)
    next_state.step += 1
    next_state.time += scenario.simulation.dt

    events: list[Event] = []
    _apply_environment_supply(next_state, scenario)
    starting_living_ids = [cell.id for cell in _living_cells(next_state)]
    for cell_id in starting_living_ids:
        cell = _cell_by_id(next_state, cell_id)
        if cell is None or cell.status != CellStatus.ALIVE or not cell.alive:
            continue

        _apply_transport(next_state, scenario, cell, events)
        _apply_metabolism(next_state, scenario, cell, events)
        _apply_pyruvate_oxidation(next_state, scenario, cell, events)
        _apply_tca_cycle(next_state, scenario, cell, events)
        _apply_electron_transport(next_state, scenario, cell, events)
        _apply_oxidative_phosphorylation(next_state, scenario, cell, events)
        _apply_membrane_gradient_decay(cell, scenario)
        _apply_maintenance_and_repair(next_state, scenario, cell, events)
        _check_cell_invariants_and_death(next_state, scenario, cell, events)
        _apply_movement(next_state, scenario, cell, rng, events)
        _apply_growth_and_division(next_state, scenario, cell, rng, events)

    _check_environment_invariants(next_state, events)
    termination_reason = _check_global_termination(next_state, events)
    terminated = termination_reason is not None
    if terminated:
        events.append(_event(next_state, EventType.TERMINATION, "Simulation terminated", reason=termination_reason.value))

    return StepTransition(
        state=next_state,
        metrics=_metrics(next_state),
        snapshot=_snapshot(next_state),
        events=events,
        terminated=terminated,
        termination_reason=termination_reason,
    )


def initial_state_for_scenario(scenario: Scenario) -> WorldState:
    return build_initial_state(scenario)
