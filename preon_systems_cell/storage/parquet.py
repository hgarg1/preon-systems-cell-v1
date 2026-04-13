from __future__ import annotations

from pathlib import Path

from preon_systems_cell.bi.parquet import write_parquet_tables
from preon_systems_cell.bi.tables import build_bi_tables
from preon_systems_cell.models import RunArtifacts


def write_parquet_run(directory: str | Path, artifacts: RunArtifacts) -> None:
    write_parquet_tables(Path(directory), build_bi_tables(artifacts))
