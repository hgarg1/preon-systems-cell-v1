from __future__ import annotations

import json
from pathlib import Path

from preon_systems_cell.models import RunArtifacts


def write_jsonl_run(directory: str | Path, artifacts: RunArtifacts) -> None:
    destination = Path(directory)
    destination.mkdir(parents=True, exist_ok=True)
    _write_rows(destination / "step_metrics.jsonl", (metric.model_dump(mode="json") for metric in artifacts.metrics))
    _write_rows(destination / "cell_events.jsonl", (event.model_dump(mode="json") for event in artifacts.events))
    _write_rows(destination / "cells.jsonl", (cell.model_dump(mode="json") for cell in artifacts.final_state.cells))


def _write_rows(path: Path, rows) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True))
            handle.write("\n")

