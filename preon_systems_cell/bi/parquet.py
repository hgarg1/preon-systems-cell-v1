from __future__ import annotations

from pathlib import Path
from typing import Any


def write_parquet_tables(directory: str | Path, tables: dict[str, list[dict[str, Any]]]) -> list[Path]:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError("Parquet export requires pyarrow. Install with: pip install 'preon-systems-cell[bi]'") from exc

    destination = Path(directory)
    destination.mkdir(parents=True, exist_ok=True)
    written = []
    for name, rows in tables.items():
        path = destination / f"{name}.parquet"
        table = pa.Table.from_pylist(rows or [{}])
        if not rows:
            table = table.slice(0, 0)
        pq.write_table(table, path)
        written.append(path)
    return written
