from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from pathlib import Path
from random import Random
from uuid import uuid4

from preon_systems_cell.artifacts import write_run_artifacts
from preon_systems_cell.domain.runs import RunRecord, RunStatus
from preon_systems_cell.engine import (
    ENGINE_VERSION,
    initial_state_for_scenario,
    metrics_for_state,
    snapshot_for_state,
    step_simulation as engine_step_simulation,
)
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
from preon_systems_cell.storage.repositories import GLOBAL_RUN_REPOSITORY, InMemoryRunRepository
from preon_systems_cell.telemetry import InMemoryTelemetrySink, TelemetryCollector


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
    repository: InMemoryRunRepository | None = None,
) -> RunArtifacts:
    effective_scenario = scenario
    if dt is not None and dt != scenario.simulation.dt:
        effective_scenario = scenario.model_copy(
            update={"simulation": scenario.simulation.model_copy(update={"dt": dt})}
        )
    effective_max_steps = max_steps if max_steps is not None else effective_scenario.simulation.max_steps
    if effective_max_steps <= 0:
        raise ValueError("max_steps must be greater than 0")
    run_id = _new_run_id()
    scenario_hash = _scenario_hash(effective_scenario)
    started_at = datetime.now(UTC)
    run_record = RunRecord(
        run_id=run_id,
        scenario_name=effective_scenario.scenario_name,
        scenario_hash=scenario_hash,
        seed=seed,
        status=RunStatus.RUNNING,
        started_at=started_at,
        max_steps=effective_max_steps,
    )

    rng = Random(seed)
    state = initial_state_for_scenario(effective_scenario)
    telemetry_sink = InMemoryTelemetrySink()
    telemetry = TelemetryCollector([telemetry_sink], record_every=effective_scenario.simulation.record_every)
    telemetry.start_run(run_record)
    termination_reason = TerminationReason.MAX_STEPS_REACHED

    for _ in range(effective_max_steps):
        transition = step_simulation_api(state, effective_scenario, rng)
        state = transition.state
        telemetry.record_step(transition)
        if transition.terminated:
            termination_reason = transition.termination_reason or TerminationReason.MAX_STEPS_REACHED
            break
    else:
        telemetry_sink.events.append(
            Event(
                step=state.step,
                time=state.time,
                type=EventType.TERMINATION,
                message="Simulation terminated after reaching max steps",
                values={"reason": TerminationReason.MAX_STEPS_REACHED.value},
            )
        )

    if not telemetry_sink.metrics:
        telemetry_sink.metrics.append(metrics_for_state(state))
        telemetry_sink.snapshots.append(snapshot_for_state(state))
    elif not telemetry_sink.snapshots or telemetry_sink.snapshots[-1].step != state.step:
        telemetry_sink.snapshots.append(snapshot_for_state(state))

    completed_record = run_record.model_copy(
        update={
            "status": RunStatus.COMPLETED,
            "completed_at": datetime.now(UTC),
            "final_step": state.step,
            "termination_reason": termination_reason.value,
        }
    )
    telemetry.complete_run(completed_record, state)

    artifacts = RunArtifacts(
        resolved_scenario=effective_scenario,
        metadata=RunMetadata(
            run_id=run_id,
            scenario_name=effective_scenario.scenario_name,
            engine_version=ENGINE_VERSION,
            seed=seed,
            dt=effective_scenario.simulation.dt,
            max_steps=effective_max_steps,
        ),
        metrics=telemetry_sink.metrics,
        snapshots=telemetry_sink.snapshots,
        events=telemetry_sink.events,
        final_state=state,
        termination_reason=termination_reason,
    )
    (repository or GLOBAL_RUN_REPOSITORY).save(completed_record, artifacts)
    if output_dir is not None:
        write_run_artifacts(output_dir, artifacts)
    return artifacts


def _new_run_id() -> str:
    return f"run-{uuid4().hex[:12]}"


def _scenario_hash(scenario: Scenario) -> str:
    payload = scenario.model_dump_json()
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
