from __future__ import annotations

from pathlib import Path
from random import Random

from preon_systems_cell.artifacts import write_run_artifacts
from preon_systems_cell.engine import ENGINE_VERSION, initial_state_for_scenario, step_simulation as engine_step_simulation
from preon_systems_cell.models import (
    CellCreateParams,
    CellCreateResponse,
    Event,
    EventType,
    RunArtifacts,
    RunMetadata,
    Scenario,
    StepTransition,
    TerminationReason,
    ValidationReport,
    WorldState,
)
from preon_systems_cell.scenario import load_scenario as _load_scenario
from preon_systems_cell.scenario import validate_scenario as _validate_scenario


def load_scenario(path: str | Path) -> Scenario:
    return _load_scenario(path)


def validate_scenario(scenario: Scenario) -> ValidationReport:
    return _validate_scenario(scenario)


def step_simulation_api(state: WorldState, scenario: Scenario, rng: Random) -> StepTransition:
    return engine_step_simulation(state, scenario, rng)


def step_simulation(state: WorldState, dt: float, rng: Random, scenario: Scenario | None = None) -> StepTransition:
    if scenario is None:
        raise ValueError("scenario is required for stepping the simulation")
    if dt != scenario.simulation.dt:
        scenario = scenario.model_copy(update={"simulation": scenario.simulation.model_copy(update={"dt": dt})})
    return step_simulation_api(state, scenario, rng)


def create_cell(scenario: Scenario, params: CellCreateParams | None = None) -> CellCreateResponse:
    effective_scenario = scenario
    if params is not None:
        scenario_updates = params.model_dump(exclude_none=True)
        if scenario_updates:
            cytosol_updates = scenario_updates.pop("cytosol", None)
            cell_config = scenario.cell
            if cytosol_updates:
                cell_config = cell_config.model_copy(
                    update={"cytosol": cell_config.cytosol.model_copy(update=cytosol_updates)}
                )
            effective_scenario = scenario.model_copy(
                update={"cell": cell_config.model_copy(update=scenario_updates)}
            )
    return CellCreateResponse(
        scenario=effective_scenario,
        state=initial_state_for_scenario(effective_scenario),
    )


def run_simulation(
    scenario: Scenario,
    seed: int,
    max_steps: int | None = None,
    dt: float | None = None,
    output_dir: str | Path | None = None,
) -> RunArtifacts:
    effective_scenario = scenario
    if dt is not None and dt != scenario.simulation.dt:
        effective_scenario = scenario.model_copy(
            update={"simulation": scenario.simulation.model_copy(update={"dt": dt})}
        )
    effective_max_steps = max_steps if max_steps is not None else effective_scenario.simulation.max_steps

    rng = Random(seed)
    state = initial_state_for_scenario(effective_scenario)
    metrics = []
    events = []
    termination_reason = TerminationReason.MAX_STEPS_REACHED

    for _ in range(effective_max_steps):
        transition = step_simulation_api(state, effective_scenario, rng)
        state = transition.state
        if state.step % effective_scenario.simulation.record_every == 0:
            metrics.append(transition.metrics)
        events.extend(transition.events)
        if transition.terminated:
            termination_reason = transition.termination_reason or TerminationReason.MAX_STEPS_REACHED
            break
    else:
        events.append(
            Event(
                step=state.step,
                time=state.time,
                type=EventType.TERMINATION,
                message="Simulation terminated after reaching max steps",
                values={"reason": TerminationReason.MAX_STEPS_REACHED.value},
            )
        )

    if not metrics:
        metrics.append(
            step_simulation_api(initial_state_for_scenario(effective_scenario), effective_scenario, Random(seed)).metrics
        )

    artifacts = RunArtifacts(
        resolved_scenario=effective_scenario,
        metadata=RunMetadata(
            scenario_name=effective_scenario.scenario_name,
            engine_version=ENGINE_VERSION,
            seed=seed,
            dt=effective_scenario.simulation.dt,
            max_steps=effective_max_steps,
        ),
        metrics=metrics,
        events=events,
        final_state=state,
        termination_reason=termination_reason,
    )
    if output_dir is not None:
        write_run_artifacts(output_dir, artifacts)
    return artifacts
