from __future__ import annotations

from random import Random
from typing import Any

from preon_systems_cell.models import (
    Event,
    EventType,
    Scenario,
    StepMetrics,
    StepTransition,
    TerminationReason,
    WorldState,
    build_initial_state,
)


ENGINE_VERSION = "0.2.0"


def _metrics(state: WorldState) -> StepMetrics:
    return StepMetrics(
        step=state.step,
        time=state.time,
        atp=state.cell.energy.atp,
        adp=state.cell.energy.adp,
        cytosolic_glucose=state.cell.cytosol.glucose,
        pyruvate=state.cell.cytosol.pyruvate,
        nadh=state.cell.cytosol.nadh,
        acetyl_coa=state.cell.cytosol.acetyl_coa,
        nad_plus=state.cell.cytosol.nad_plus,
        fad=state.cell.cytosol.fad,
        fadh2=state.cell.cytosol.fadh2,
        co2=state.cell.cytosol.co2,
        membrane_gradient=state.cell.cytosol.membrane_gradient,
        environment_glucose=state.environment.glucose_concentration,
        environment_electron_acceptor=state.environment.electron_acceptor_concentration,
        waste=state.cell.waste,
        toxicity=state.environment.toxicity,
        membrane_integrity=state.cell.membrane_integrity,
        glucose_transporter_density=state.cell.glucose_transporter_density,
        biomass=state.cell.biomass,
        x=state.cell.x,
        y=state.cell.y,
        z=state.cell.z,
    )


def _event(state: WorldState, event_type: EventType, message: str, **values: Any) -> Event:
    return Event(
        step=state.step,
        time=state.time,
        type=event_type,
        message=message,
        values=values,
    )


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


def _apply_transport(state: WorldState, scenario: Scenario, events: list[Event]) -> None:
    cell = state.cell
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
        _event(
            state,
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


def _apply_metabolism(state: WorldState, scenario: Scenario, _rng: Random, events: list[Event]) -> None:
    cell = state.cell
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
        _event(
            state,
            EventType.GLYCOLYSIS,
            "Converted cytosolic glucose through glycolysis",
            glucose_processed=processed,
            pyruvate_generated=pyruvate_generated,
            atp_generated=atp_generated,
            nadh_generated=nadh_generated,
        )
    )


def _apply_pyruvate_oxidation(state: WorldState, scenario: Scenario, events: list[Event]) -> None:
    cell = state.cell
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
        _event(
            state,
            EventType.PYRUVATE_OXIDATION,
            "Oxidized pyruvate into acetyl-CoA",
            pyruvate_oxidized=oxidized,
            acetyl_coa_generated=oxidized,
            co2_generated=oxidized,
            nadh_generated=oxidized,
            nad_plus_consumed=oxidized,
        )
    )


def _apply_tca_cycle(state: WorldState, scenario: Scenario, events: list[Event]) -> None:
    cell = state.cell
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
        _event(
            state,
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


def _apply_electron_transport(state: WorldState, scenario: Scenario, events: list[Event]) -> None:
    cell = state.cell
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
        _event(
            state,
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


def _apply_oxidative_phosphorylation(state: WorldState, scenario: Scenario, events: list[Event]) -> None:
    cell = state.cell
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
        _event(
            state,
            EventType.OXIDATIVE_PHOSPHORYLATION,
            "Converted membrane gradient into ATP",
            gradient_used=gradient_used,
            atp_generated=atp_generated,
        )
    )


def _apply_membrane_gradient_decay(state: WorldState, scenario: Scenario) -> None:
    cell = state.cell
    if not cell.alive:
        return
    gradient_loss = scenario.metabolism.membrane_gradient_decay * scenario.simulation.dt
    if gradient_loss <= 0:
        return
    cell.cytosol.membrane_gradient = max(cell.cytosol.membrane_gradient - gradient_loss, 0)


def _apply_maintenance_and_repair(state: WorldState, scenario: Scenario, events: list[Event]) -> None:
    cell = state.cell
    if not cell.alive:
        return

    basal_cost = scenario.maintenance.basal_atp_cost * scenario.simulation.dt
    cell.energy.atp -= basal_cost
    cell.energy.adp += basal_cost
    events.append(_event(state, EventType.MAINTENANCE, "Paid basal ATP maintenance cost", atp_cost=basal_cost))

    membrane_decay = scenario.maintenance.membrane_decay * scenario.simulation.dt
    cell.membrane_integrity = max(cell.membrane_integrity - membrane_decay, 0)
    if membrane_decay > 0:
        events.append(_event(state, EventType.DAMAGE, "Membrane integrity decayed", membrane_loss=membrane_decay))

    repair_target = min(1 - cell.membrane_integrity, scenario.maintenance.repair_rate * scenario.simulation.dt)
    if repair_target > 0:
        affordable_repair = min(repair_target, cell.energy.atp / max(scenario.maintenance.repair_atp_cost, 1e-9))
        if affordable_repair > 0:
            actual_cost = affordable_repair * scenario.maintenance.repair_atp_cost
            cell.energy.atp -= actual_cost
            cell.energy.adp += actual_cost
            cell.membrane_integrity = min(cell.membrane_integrity + affordable_repair, 1)
            events.append(
                _event(
                    state,
                    EventType.REPAIR,
                    "Repaired membrane damage",
                    repaired=affordable_repair,
                    atp_cost=actual_cost,
                )
            )


def _apply_growth(state: WorldState, scenario: Scenario, events: list[Event]) -> None:
    cell = state.cell
    if not cell.alive or scenario.maintenance.growth_atp_cost <= 0 or scenario.maintenance.biomass_gain_per_growth <= 0:
        return
    if cell.energy.atp < (scenario.cell.maintenance_threshold_atp * 1.5):
        return

    growth_cost = scenario.maintenance.growth_atp_cost * scenario.simulation.dt
    if cell.energy.atp < growth_cost:
        return

    cell.energy.atp -= growth_cost
    cell.energy.adp += growth_cost
    cell.biomass += scenario.maintenance.biomass_gain_per_growth * scenario.simulation.dt
    events.append(
        _event(
            state,
            EventType.GROWTH,
            "Invested ATP into biomass growth",
            atp_cost=growth_cost,
            biomass_gain=scenario.maintenance.biomass_gain_per_growth * scenario.simulation.dt,
        )
    )

    if cell.biomass >= scenario.cell.division_biomass_threshold:
        cell.division_count += 1
        cell.biomass *= 0.5
        cell.energy.atp *= 0.5
        cell.energy.adp *= 0.5
        cell.cytosol.glucose *= 0.5
        cell.cytosol.pyruvate *= 0.5
        cell.cytosol.nadh *= 0.5
        cell.cytosol.acetyl_coa *= 0.5
        cell.cytosol.nad_plus *= 0.5
        cell.cytosol.fad *= 0.5
        cell.cytosol.fadh2 *= 0.5
        cell.cytosol.co2 *= 0.5
        cell.cytosol.membrane_gradient *= 0.5
        cell.waste *= 0.5
        events.append(
            _event(
                state,
                EventType.GROWTH,
                "Completed a simple division event",
                division_count=cell.division_count,
                post_division_biomass=cell.biomass,
                post_division_atp=cell.energy.atp,
                post_division_adp=cell.energy.adp,
                post_division_glucose=cell.cytosol.glucose,
                post_division_pyruvate=cell.cytosol.pyruvate,
                post_division_nadh=cell.cytosol.nadh,
                post_division_acetyl_coa=cell.cytosol.acetyl_coa,
                post_division_nad_plus=cell.cytosol.nad_plus,
                post_division_fad=cell.cytosol.fad,
                post_division_fadh2=cell.cytosol.fadh2,
                post_division_co2=cell.cytosol.co2,
                post_division_membrane_gradient=cell.cytosol.membrane_gradient,
                post_division_waste=cell.waste,
            )
        )


def _apply_movement(state: WorldState, scenario: Scenario, rng: Random, events: list[Event]) -> None:
    cell = state.cell
    if not cell.alive or not scenario.movement.enabled or scenario.movement.drift_strength <= 0:
        return

    mobility = (
        scenario.movement.drift_strength
        * scenario.simulation.dt
        * max(cell.membrane_integrity, 0.1)
        * (1.0 + (cell.energy.atp * scenario.movement.atp_influence))
    )
    dx = (rng.uniform(-1.0, 1.0)) * mobility
    dy = (rng.uniform(-1.0, 1.0)) * mobility * scenario.movement.vertical_drift
    dz = (rng.uniform(-1.0, 1.0)) * mobility

    cell.x += dx
    cell.y += dy
    cell.z += dz
    events.append(
        _event(
            state,
            EventType.MOVEMENT,
            "Cell drifted through 3D space",
            delta_x=dx,
            delta_y=dy,
            delta_z=dz,
            distance=(dx**2 + dy**2 + dz**2) ** 0.5,
        )
    )


def _check_termination(state: WorldState, scenario: Scenario, events: list[Event]) -> TerminationReason | None:
    cell = state.cell
    env = state.environment
    if cell.energy.atp < 0:
        events.append(_event(state, EventType.INVARIANT, "ATP dropped below zero", atp=cell.energy.atp))
        cell.energy.atp = 0
    if cell.cytosol.glucose < 0:
        events.append(_event(state, EventType.INVARIANT, "Cytosolic glucose dropped below zero", glucose=cell.cytosol.glucose))
        cell.cytosol.glucose = 0
    if cell.cytosol.pyruvate < 0:
        events.append(_event(state, EventType.INVARIANT, "Pyruvate dropped below zero", pyruvate=cell.cytosol.pyruvate))
        cell.cytosol.pyruvate = 0
    if cell.cytosol.nadh < 0:
        events.append(_event(state, EventType.INVARIANT, "NADH dropped below zero", nadh=cell.cytosol.nadh))
        cell.cytosol.nadh = 0
    if cell.cytosol.acetyl_coa < 0:
        events.append(_event(state, EventType.INVARIANT, "Acetyl-CoA dropped below zero", acetyl_coa=cell.cytosol.acetyl_coa))
        cell.cytosol.acetyl_coa = 0
    if cell.cytosol.nad_plus < 0:
        events.append(_event(state, EventType.INVARIANT, "NAD+ dropped below zero", nad_plus=cell.cytosol.nad_plus))
        cell.cytosol.nad_plus = 0
    if cell.cytosol.fad < 0:
        events.append(_event(state, EventType.INVARIANT, "FAD dropped below zero", fad=cell.cytosol.fad))
        cell.cytosol.fad = 0
    if cell.cytosol.fadh2 < 0:
        events.append(_event(state, EventType.INVARIANT, "FADH2 dropped below zero", fadh2=cell.cytosol.fadh2))
        cell.cytosol.fadh2 = 0
    if cell.cytosol.co2 < 0:
        events.append(_event(state, EventType.INVARIANT, "CO2 dropped below zero", co2=cell.cytosol.co2))
        cell.cytosol.co2 = 0
    if cell.cytosol.membrane_gradient < 0:
        events.append(
            _event(
                state,
                EventType.INVARIANT,
                "Membrane gradient dropped below zero",
                membrane_gradient=cell.cytosol.membrane_gradient,
            )
        )
        cell.cytosol.membrane_gradient = 0
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

    if cell.energy.atp <= 0:
        cell.alive = False
        return TerminationReason.ATP_DEPLETION
    if (
        cell.energy.atp < scenario.cell.maintenance_threshold_atp
        and cell.cytosol.glucose <= 0
        and env.glucose_concentration <= 0
    ):
        cell.alive = False
        return TerminationReason.STARVATION
    if cell.membrane_integrity <= 0:
        cell.alive = False
        return TerminationReason.MEMBRANE_FAILURE
    if env.toxicity + cell.waste >= max(10.0, scenario.cell.biomass * 3):
        cell.alive = False
        return TerminationReason.TOXICITY
    return None


def step_simulation(state: WorldState, scenario: Scenario, rng: Random) -> StepTransition:
    next_state = state.model_copy(deep=True)
    next_state.step += 1
    next_state.time += scenario.simulation.dt

    events: list[Event] = []
    _apply_environment_supply(next_state, scenario)
    _apply_transport(next_state, scenario, events)
    _apply_metabolism(next_state, scenario, rng, events)
    _apply_pyruvate_oxidation(next_state, scenario, events)
    _apply_tca_cycle(next_state, scenario, events)
    _apply_electron_transport(next_state, scenario, events)
    _apply_oxidative_phosphorylation(next_state, scenario, events)
    _apply_membrane_gradient_decay(next_state, scenario)
    _apply_maintenance_and_repair(next_state, scenario, events)
    _apply_growth(next_state, scenario, events)
    _apply_movement(next_state, scenario, rng, events)

    termination_reason = _check_termination(next_state, scenario, events)
    terminated = termination_reason is not None
    if terminated:
        events.append(_event(next_state, EventType.TERMINATION, "Simulation terminated", reason=termination_reason.value))

    return StepTransition(
        state=next_state,
        metrics=_metrics(next_state),
        events=events,
        terminated=terminated,
        termination_reason=termination_reason,
    )


def initial_state_for_scenario(scenario: Scenario) -> WorldState:
    return build_initial_state(scenario)
