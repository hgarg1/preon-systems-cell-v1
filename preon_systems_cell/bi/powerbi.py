from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile


POWERBI_PROJECT_NAME = "preon-cell-analytics"


def write_powerbi_project(directory: str | Path, tables: dict[str, list[dict[str, Any]]]) -> list[Path]:
    destination = Path(directory)
    destination.mkdir(parents=True, exist_ok=True)

    pbip_path = destination / f"{POWERBI_PROJECT_NAME}.pbip"
    semantic_dir = destination / f"{POWERBI_PROJECT_NAME}.SemanticModel"
    report_dir = destination / f"{POWERBI_PROJECT_NAME}.Report"
    semantic_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    written = [
        _write_json(pbip_path, _pbip_payload()),
        _write_json(report_dir / "definition.pbir", _report_payload()),
        _write_json(semantic_dir / "definition.pbism", _semantic_payload()),
        _write_json(semantic_dir / "model.bim", _model_payload(tables)),
        _write_readme(destination / "README.md"),
    ]
    written.append(_write_pbit(destination / f"{POWERBI_PROJECT_NAME}.pbit", written, destination))
    return written


def _pbip_payload() -> dict[str, Any]:
    return {
        "version": "1.0",
        "artifacts": [
            {"report": {"path": f"{POWERBI_PROJECT_NAME}.Report"}},
            {"semanticModel": {"path": f"{POWERBI_PROJECT_NAME}.SemanticModel"}},
        ],
    }


def _report_payload() -> dict[str, Any]:
    return {
        "version": "4.0",
        "datasetReference": {"byPath": {"path": f"../{POWERBI_PROJECT_NAME}.SemanticModel"}},
    }


def _semantic_payload() -> dict[str, Any]:
    return {"version": "1.0", "artifacts": [{"path": "model.bim"}]}


def _model_payload(tables: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    return {
        "compatibilityLevel": 1600,
        "model": {
            "culture": "en-US",
            "defaultPowerBIDataSourceVersion": "powerBI_V3",
            "expressions": [
                {
                    "name": "ParquetRoot",
                    "kind": "m",
                    "expression": "\"../parquet\"",
                }
            ],
            "tables": [_powerbi_table(name, rows) for name, rows in tables.items()],
        },
    }


def _powerbi_table(name: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    sample = rows[0] if rows else {}
    return {
        "name": name,
        "columns": [
            {
                "name": column,
                "dataType": _powerbi_type(value),
                "sourceColumn": column,
            }
            for column, value in sample.items()
        ],
        "partitions": [
            {
                "name": name,
                "mode": "import",
                "source": {
                    "type": "m",
                    "expression": [
                        "let",
                        f"    Source = Parquet.Document(File.Contents(ParquetRoot & \"/{name}.parquet\"))",
                        "in",
                        "    Source",
                    ],
                },
            }
        ],
    }


def _powerbi_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "int64"
    if isinstance(value, float):
        return "double"
    return "string"


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _write_readme(path: Path) -> Path:
    path.write_text(
        "\n".join(
            [
                "# Power BI Native Project",
                "",
                "Open `preon-cell-analytics.pbip` in Power BI Desktop.",
                "The semantic model imports the sibling `../parquet` dataset generated in the same export bundle.",
                "`preon-cell-analytics.pbit` is a packaged copy of the generated project files for handoff workflows.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


def _write_pbit(path: Path, project_files: list[Path], root: Path) -> Path:
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        for file_path in project_files:
            archive.write(file_path, file_path.relative_to(root).as_posix())
    return path
