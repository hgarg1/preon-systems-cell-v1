from __future__ import annotations

import json
from pathlib import Path

from preon_systems_cell.analytics.exports import write_feature_json
from preon_systems_cell.models import (
    Event,
    PopulationMetrics,
    RunArtifacts,
    RunMetadata,
    RunSummary,
    Scenario,
    StepSnapshot,
    TerminationReason,
    WorldState,
)
from preon_systems_cell.storage.jsonl import write_jsonl_run


def write_run_artifacts(output_dir: str | Path, artifacts: RunArtifacts) -> None:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)

    _write_json(destination / "resolved_scenario.json", artifacts.resolved_scenario.model_dump(mode="json"))
    _write_json(destination / "run_metadata.json", artifacts.metadata.model_dump(mode="json"))
    _write_json(destination / "metrics.json", [metric.model_dump(mode="json") for metric in artifacts.metrics])
    _write_json(destination / "snapshots.json", [snapshot.model_dump(mode="json") for snapshot in artifacts.snapshots])
    _write_json(destination / "events.json", [event.model_dump(mode="json") for event in artifacts.events])
    _write_json(destination / "final_state.json", artifacts.final_state.model_dump(mode="json"))
    write_jsonl_run(destination / "analytics", artifacts)
    write_feature_json(destination / "features", artifacts)
    _write_json(
        destination / "run_summary.json",
        RunSummary(
            metadata=artifacts.metadata,
            final_state=artifacts.final_state,
            final_metrics=artifacts.metrics[-1],
            termination_reason=artifacts.termination_reason,
            steps_completed=artifacts.final_state.step,
            event_count=len(artifacts.events),
        ).model_dump(mode="json"),
    )


def read_json(path: str | Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read_run_artifacts(directory: str | Path) -> RunArtifacts:
    source = Path(directory)
    metadata = RunMetadata.model_validate(read_json(source / "run_metadata.json"))
    final_state = WorldState.model_validate(read_json(source / "final_state.json"))
    summary = read_json(source / "run_summary.json")
    return RunArtifacts(
        resolved_scenario=Scenario.model_validate(read_json(source / "resolved_scenario.json")),
        metadata=metadata,
        metrics=[PopulationMetrics.model_validate(row) for row in read_json(source / "metrics.json")],
        snapshots=[StepSnapshot.model_validate(row) for row in read_json(source / "snapshots.json")],
        events=[Event.model_validate(row) for row in read_json(source / "events.json")],
        final_state=final_state,
        termination_reason=TerminationReason(summary["termination_reason"]),
    )


def _write_json(path: Path, payload: object) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
