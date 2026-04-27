from __future__ import annotations

import json
from pathlib import Path
from typing import Any


POWERBI_PROJECT_NAME = "preon-cell-analytics"
PBIP_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json"
PBIR_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json"
PBISM_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json"
PBIR_VERSION_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json"
PBIR_REPORT_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/1.0.0/schema.json"
PBIR_PAGES_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.0.0/schema.json"
PBIR_PAGE_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/1.0.0/schema.json"
REPORT_PAGE_NAME = "ReportSection"


def write_powerbi_project(directory: str | Path, tables: dict[str, list[dict[str, Any]]]) -> list[Path]:
    destination = Path(directory)
    destination.mkdir(parents=True, exist_ok=True)

    pbip_path = destination / f"{POWERBI_PROJECT_NAME}.pbip"
    semantic_dir = destination / f"{POWERBI_PROJECT_NAME}.SemanticModel"
    report_dir = destination / f"{POWERBI_PROJECT_NAME}.Report"
    report_definition_dir = report_dir / "definition"
    report_pages_dir = report_definition_dir / "pages" / REPORT_PAGE_NAME
    semantic_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    report_pages_dir.mkdir(parents=True, exist_ok=True)

    written = [
        _write_json(pbip_path, _pbip_payload()),
        _write_json(report_dir / "definition.pbir", _report_payload()),
        _write_json(report_definition_dir / "version.json", _report_definition_version_payload()),
        _write_json(report_definition_dir / "report.json", _report_definition_payload()),
        _write_json(report_definition_dir / "pages" / "pages.json", _report_pages_payload()),
        _write_json(report_pages_dir / "page.json", _report_page_payload()),
        _write_json(semantic_dir / "definition.pbism", _semantic_payload()),
        _write_json(semantic_dir / "model.bim", _model_payload(tables)),
        _write_readme(destination / "README.md"),
    ]
    return written


def _pbip_payload() -> dict[str, Any]:
    return {
        "$schema": PBIP_SCHEMA,
        "version": "1.0",
        "artifacts": [
            {"report": {"path": f"{POWERBI_PROJECT_NAME}.Report"}},
        ],
    }


def _report_payload() -> dict[str, Any]:
    return {
        "$schema": PBIR_SCHEMA,
        "version": "4.0",
        "datasetReference": {"byPath": {"path": f"../{POWERBI_PROJECT_NAME}.SemanticModel"}},
    }


def _semantic_payload() -> dict[str, Any]:
    return {"$schema": PBISM_SCHEMA, "version": "1.0"}


def _report_definition_version_payload() -> dict[str, Any]:
    return {"$schema": PBIR_VERSION_SCHEMA, "version": "1.0.0"}


def _report_definition_payload() -> dict[str, Any]:
    return {
        "$schema": PBIR_REPORT_SCHEMA,
        "layoutOptimization": "None",
        "themeCollection": {
            "baseTheme": {
                "name": "CY24SU06",
                "reportVersionAtImport": "5.55",
                "type": "SharedResources",
            }
        },
        "settings": {},
    }


def _report_pages_payload() -> dict[str, Any]:
    return {"$schema": PBIR_PAGES_SCHEMA, "activePageName": REPORT_PAGE_NAME, "pageOrder": [REPORT_PAGE_NAME]}


def _report_page_payload() -> dict[str, Any]:
    return {
        "$schema": PBIR_PAGE_SCHEMA,
        "displayName": "Overview",
        "displayOption": "FitToPage",
        "height": 720,
        "name": REPORT_PAGE_NAME,
        "width": 1280,
    }


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
                "If a `.pbit` template is required, open the `.pbip` first and save a template from Power BI Desktop.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path
