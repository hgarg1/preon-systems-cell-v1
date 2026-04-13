from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Literal
from zipfile import ZIP_DEFLATED, ZipFile

from pydantic import BaseModel, Field

from preon_systems_cell.bi.parquet import write_parquet_tables
from preon_systems_cell.bi.powerbi import write_powerbi_project
from preon_systems_cell.bi.tableau import write_tableau_bundle
from preon_systems_cell.bi.tables import BI_SCHEMA_VERSION, build_bi_tables
from preon_systems_cell.models import RunArtifacts


BI_EXPORT_FORMATS = ("parquet", "powerbi", "tableau")
BIFormat = Literal["parquet", "powerbi", "tableau"]


class ExportedFile(BaseModel):
    path: str
    bytes: int = Field(ge=0)


class ExportManifest(BaseModel):
    run_id: str
    schema_version: str = BI_SCHEMA_VERSION
    generated_at: datetime
    formats: list[str]
    row_counts: dict[str, int]
    files: dict[str, list[ExportedFile]]


def describe_export_formats() -> list[dict[str, object]]:
    return [
        {
            "format": "parquet",
            "label": "Parquet",
            "native": False,
            "available": _module_available("pyarrow"),
            "description": "Columnar analytics dataset for BI, warehouse loading, and ML features.",
        },
        {
            "format": "powerbi",
            "label": "Power BI",
            "native": True,
            "available": True,
            "description": "Power BI project files wired to the generated Parquet dataset.",
        },
        {
            "format": "tableau",
            "label": "Tableau",
            "native": True,
            "available": _module_available("tableauhyperapi"),
            "description": "Tableau Hyper extract and packaged workbook.",
        },
    ]


def write_bi_bundle(
    artifacts: RunArtifacts,
    output_dir: str | Path,
    formats: list[str] | tuple[str, ...] = BI_EXPORT_FORMATS,
) -> ExportManifest:
    normalized_formats = _normalize_formats(formats)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    existing_manifest = read_export_manifest(destination)
    if existing_manifest is not None and existing_manifest.run_id != artifacts.metadata.run_id:
        raise ValueError(
            f"export directory already contains run {existing_manifest.run_id}; "
            f"cannot overwrite with {artifacts.metadata.run_id}"
        )
    tables = build_bi_tables(artifacts)
    row_counts = {name: len(rows) for name, rows in tables.items()}
    files: dict[str, list[ExportedFile]] = dict(existing_manifest.files) if existing_manifest else {}
    manifest_formats = list(existing_manifest.formats) if existing_manifest else []

    for export_format in normalized_formats:
        format_dir = destination / export_format
        if export_format == "parquet":
            written = write_parquet_tables(format_dir, tables)
        elif export_format == "powerbi":
            parquet_files = _ensure_parquet_for_powerbi(tables, destination)
            written = [*write_powerbi_project(format_dir, tables), *parquet_files]
            files["parquet"] = [_file_entry(path, destination) for path in sorted(parquet_files)]
            if "parquet" not in manifest_formats:
                manifest_formats.append("parquet")
        elif export_format == "tableau":
            written = write_tableau_bundle(format_dir, tables)
        else:
            raise ValueError(f"unsupported BI export format: {export_format}")
        files[export_format] = [_file_entry(path, destination) for path in sorted(written)]
        if export_format not in manifest_formats:
            manifest_formats.append(export_format)

    manifest = ExportManifest(
        run_id=artifacts.metadata.run_id,
        generated_at=datetime.now(UTC),
        formats=manifest_formats,
        row_counts=row_counts,
        files=files,
    )
    _write_manifest(destination / "manifest.json", manifest)
    return manifest


def read_export_manifest(output_dir: str | Path) -> ExportManifest | None:
    path = Path(output_dir) / "manifest.json"
    if not path.exists():
        return None
    return ExportManifest.model_validate_json(path.read_text(encoding="utf-8"))


def write_export_zip(output_dir: str | Path, export_format: str) -> Path:
    destination = Path(output_dir)
    manifest = read_export_manifest(destination)
    if manifest is None:
        raise FileNotFoundError("export manifest not found")
    normalized = "all" if export_format == "all" else _normalize_formats([export_format])[0]
    zip_path = destination / f"{normalized}.zip"
    include_formats = manifest.formats if normalized == "all" else [normalized]
    archived_paths = {"manifest.json"}
    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as archive:
        archive.write(destination / "manifest.json", "manifest.json")
        for format_name in include_formats:
            for file_entry in manifest.files.get(format_name, []):
                path = destination / file_entry.path
                if not path.exists():
                    raise FileNotFoundError(f"export file missing: {file_entry.path}")
                if file_entry.path in archived_paths:
                    continue
                archive.write(path, file_entry.path)
                archived_paths.add(file_entry.path)
    return zip_path


def _normalize_formats(formats: list[str] | tuple[str, ...]) -> list[BIFormat]:
    normalized = []
    for export_format in formats:
        if export_format not in BI_EXPORT_FORMATS:
            raise ValueError(f"unsupported BI export format: {export_format}")
        if export_format not in normalized:
            normalized.append(export_format)
    return normalized  # type: ignore[return-value]


def _ensure_parquet_for_powerbi(tables: dict[str, list[dict]], destination: Path) -> list[Path]:
    parquet_dir = destination / "parquet"
    if not parquet_dir.exists() or not any(parquet_dir.glob("*.parquet")):
        return write_parquet_tables(parquet_dir, tables)
    return list(parquet_dir.glob("*.parquet"))


def _file_entry(path: Path, root: Path) -> ExportedFile:
    return ExportedFile(path=path.relative_to(root).as_posix(), bytes=path.stat().st_size)


def _write_manifest(path: Path, manifest: ExportManifest) -> None:
    path.write_text(json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _module_available(module_name: str) -> bool:
    try:
        __import__(module_name)
    except ImportError:
        return False
    return True
