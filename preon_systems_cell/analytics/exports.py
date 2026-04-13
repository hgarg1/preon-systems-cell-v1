from __future__ import annotations

import json
from pathlib import Path

from preon_systems_cell.analytics.features import extract_cell_features, extract_run_features
from preon_systems_cell.models import RunArtifacts


def write_feature_json(directory: str | Path, artifacts: RunArtifacts) -> None:
    destination = Path(directory)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "run_features.json").write_text(
        json.dumps(extract_run_features(artifacts), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (destination / "cell_features.json").write_text(
        json.dumps(extract_cell_features(artifacts), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

