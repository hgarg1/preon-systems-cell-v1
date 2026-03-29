from __future__ import annotations

from random import Random

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


ENGINE_VERSION = "0.1.0"


def _metrics(state: WorldState) -> StepMetrics:
    return StepMetrics(
        step=state.step,
        time=state.time,
        atp=state.cell.energy.atp,
        adp=state.cell.energy.adp,
        nutrient_reserve=state.cell.nutrient_reserve,
        environment_nutrients=state.environment.nutrient_concentration,
        waste=state.cell.waste,
        toxicity=state.environment.toxicity,
        membrane_integrity=state.cell.membrane_integrity,
        biomass=state.cell.biomass,
    )


def _event(state: WorldState, event_type: EventType, message: str, **values: float) -> Event:
    return Event(
        step=state.step,
        time=state.time,
        type=event_type,
        message=message,
        values=values,
    )


def _apply_environment_supply(state: WorldState, scenario: Scenario) -> None:
    state.environment.nutrient_concentration += scenario.environment.replenishment_rate * scenario.simulation.dt
    state.environment.toxicity += scenario.environment.toxicity_rate * scenario.simulation.dt


def _apply_transport(state: WorldState, scenario: Scenario, events: list[Event]) -> None:
    cell = state.cell
    env = state.environment
    if not cell.alive or env.nutrient_concentration <= 0:
        return

    membrane_factor = max(cell.membrane_integrity, 0.05)
    uptake_capacity = scenario.transport.uptake_rate * membrane_factor * scenario.simulation.dt
    max_affordable = cell.energy.atp / max(scenario.transport.atp_cost_per_unit, 1e-9)
    imported = min(env.nutrient_concentration, uptake_capacity, max_affordable)
    if imported <= 0:
        return

    transport_cost = imported * scenario.transport.atp_cost_per_unit
    cell.energy.atp -= transport_cost
    cell.energy.adp += transport_cost
    cell.nutrient_reserve += imported
    env.nutrient_concentration -= imported
    events.append(_event(state, EventType.TRANSPORT, "Imported nutrients across the membrane", imported=imported, atp_cost=transport_cost))


def _apply_metabolism(state: WorldState, scenario: Scenario, rng: Random, events: list[Event]) -> None:
    cell = state.cell
    if not cell.alive or cell.nutrient_reserve <= 0:
        return

    metabolic_efficiency = 0.92 + (rng.random() * 0.06)
    converted = min(cell.nutrient_reserve, scenario.metabolism.reserve_conversion_cap * scenario.simulation.dt)
    if converted <= 0:
        return

    produced_atp = converted * scenario.metabolism.atp_yield_per_nutrient * metabolic_efficiency
    waste_generated = converted * scenario.metabolism.waste_per_nutrient
    cell.nutrient_reserve -= converted
    cell.energy.atp += produced_atp
    cell.energy.adp = max(cell.energy.adp - produced_atp, 0)
    cell.waste += waste_generated
    events.append(_event(state, EventType.METABOLISM, "Converted nutrient reserves into ATP", converted=converted, atp_generated=produced_atp, waste_generated=waste_generated))


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
        repair_cost = repair_target * scenario.maintenance.repair_atp_cost
        affordable_repair = min(repair_target, cell.energy.atp / max(scenario.maintenance.repair_atp_cost, 1e-9))
        if affordable_repair > 0:
            actual_cost = affordable_repair * scenario.maintenance.repair_atp_cost
            cell.energy.atp -= actual_cost
            cell.energy.adp += actual_cost
            cell.membrane_integrity = min(cell.membrane_integrity + affordable_repair, 1)
            events.append(_event(state, EventType.REPAIR, "Repaired membrane damage", repaired=affordable_repair, atp_cost=actual_cost))


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
    events.append(_event(state, EventType.GROWTH, "Invested ATP into biomass growth", atp_cost=growth_cost, biomass_gain=scenario.maintenance.biomass_gain_per_growth * scenario.simulation.dt))

    if cell.biomass >= scenario.cell.division_biomass_threshold:
        cell.division_count += 1
        cell.biomass *= 0.5
        cell.energy.atp *= 0.5
        cell.energy.adp *= 0.5
        events.append(_event(state, EventType.GROWTH, "Completed a simple division event", division_count=cell.division_count))


def _check_termination(state: WorldState, scenario: Scenario, events: list[Event]) -> TerminationReason | None:
    cell = state.cell
    if cell.energy.atp < 0:
        events.append(_event(state, EventType.INVARIANT, "ATP dropped below zero", atp=cell.energy.atp))
        cell.energy.atp = 0
    if cell.nutrient_reserve < 0:
        events.append(_event(state, EventType.INVARIANT, "Nutrient reserve dropped below zero", reserve=cell.nutrient_reserve))
        cell.nutrient_reserve = 0
    if state.environment.nutrient_concentration < 0:
        events.append(_event(state, EventType.INVARIANT, "Environment nutrients dropped below zero", environment_nutrients=state.environment.nutrient_concentration))
        state.environment.nutrient_concentration = 0

    if cell.energy.atp <= 0:
        cell.alive = False
        return TerminationReason.ATP_DEPLETION
    if cell.energy.atp < scenario.cell.maintenance_threshold_atp and cell.nutrient_reserve <= 0 and state.environment.nutrient_concentration <= 0:
        cell.alive = False
        return TerminationReason.STARVATION
    if cell.membrane_integrity <= 0:
        cell.alive = False
        return TerminationReason.MEMBRANE_FAILURE
    if state.environment.toxicity + cell.waste >= max(10.0, scenario.cell.biomass * 3):
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
    _apply_maintenance_and_repair(next_state, scenario, events)
    _apply_growth(next_state, scenario, events)

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
