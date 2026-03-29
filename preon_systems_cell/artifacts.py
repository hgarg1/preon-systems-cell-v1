from __future__ import annotations

import json
from pathlib import Path

from preon_systems_cell.models import RunArtifacts, RunSummary


def write_run_artifacts(output_dir: str | Path, artifacts: RunArtifacts) -> None:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)

    _write_json(destination / "resolved_scenario.json", artifacts.resolved_scenario.model_dump(mode="json"))
    _write_json(destination / "run_metadata.json", artifacts.metadata.model_dump(mode="json"))
    _write_json(destination / "metrics.json", [metric.model_dump(mode="json") for metric in artifacts.metrics])
    _write_json(destination / "events.json", [event.model_dump(mode="json") for event in artifacts.events])
    _write_json(destination / "final_state.json", artifacts.final_state.model_dump(mode="json"))
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


def _write_json(path: Path, payload: object) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
