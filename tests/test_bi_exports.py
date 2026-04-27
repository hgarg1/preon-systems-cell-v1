import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from preon_systems_cell.api import load_scenario, run_simulation
from preon_systems_cell.artifacts import read_run_artifacts
from preon_systems_cell.bi import write_bi_bundle, write_export_zip
from preon_systems_cell.bi.tables import build_bi_tables
from preon_systems_cell.cli import main as cli_main


SCENARIO_PATH = Path("scenarios/default_cell.yaml")


def test_bi_tables_include_run_context():
    artifacts = run_simulation(load_scenario(SCENARIO_PATH), seed=7, max_steps=4)

    tables = build_bi_tables(artifacts)

    assert set(tables) == {
        "runs",
        "step_metrics",
        "cells",
        "cell_events",
        "run_features",
        "cell_features",
        "run_intelligence",
    }
    assert all(row["run_id"] == artifacts.metadata.run_id for rows in tables.values() for row in rows)
    assert all("scenario_name" in row for rows in tables.values() for row in rows)


def test_write_bi_bundle_writes_parquet_and_powerbi_without_csv(tmp_path):
    artifacts = run_simulation(load_scenario(SCENARIO_PATH), seed=9, max_steps=5)

    manifest = write_bi_bundle(artifacts, tmp_path, formats=["parquet", "powerbi"])
    zip_path = write_export_zip(tmp_path, "powerbi")

    assert manifest.run_id == artifacts.metadata.run_id
    assert manifest.row_counts["runs"] == 1
    assert manifest.row_counts["step_metrics"] == len(artifacts.metrics)
    assert manifest.row_counts["run_intelligence"] == 1
    assert (tmp_path / "parquet" / "runs.parquet").exists()
    assert (tmp_path / "powerbi" / "preon-cell-analytics.pbip").exists()
    assert not (tmp_path / "powerbi" / "preon-cell-analytics.pbit").exists()
    pbip = json.loads((tmp_path / "powerbi" / "preon-cell-analytics.pbip").read_text(encoding="utf-8"))
    pbir = json.loads(
        (tmp_path / "powerbi" / "preon-cell-analytics.Report" / "definition.pbir").read_text(encoding="utf-8")
    )
    report_definition = json.loads(
        (tmp_path / "powerbi" / "preon-cell-analytics.Report" / "definition" / "report.json").read_text(
            encoding="utf-8"
        )
    )
    pages = json.loads(
        (tmp_path / "powerbi" / "preon-cell-analytics.Report" / "definition" / "pages" / "pages.json").read_text(
            encoding="utf-8"
        )
    )
    page = json.loads(
        (
            tmp_path
            / "powerbi"
            / "preon-cell-analytics.Report"
            / "definition"
            / "pages"
            / "ReportSection"
            / "page.json"
        ).read_text(encoding="utf-8")
    )
    pbism = json.loads(
        (tmp_path / "powerbi" / "preon-cell-analytics.SemanticModel" / "definition.pbism").read_text(encoding="utf-8")
    )
    assert pbip["$schema"].endswith("/fabric/pbip/pbipProperties/1.0.0/schema.json")
    assert pbip["artifacts"] == [{"report": {"path": "preon-cell-analytics.Report"}}]
    assert pbir["$schema"].endswith("/fabric/item/report/definitionProperties/2.0.0/schema.json")
    assert pbir["datasetReference"]["byPath"]["path"] == "../preon-cell-analytics.SemanticModel"
    assert report_definition["$schema"].endswith("/fabric/item/report/definition/report/1.0.0/schema.json")
    assert report_definition["layoutOptimization"] == "None"
    assert pages == {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.0.0/schema.json",
        "activePageName": "ReportSection",
        "pageOrder": ["ReportSection"],
    }
    assert page["name"] == "ReportSection"
    assert page["displayName"] == "Overview"
    assert pbism == {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",
        "version": "1.0",
    }
    with ZipFile(zip_path) as archive:
        names = archive.namelist()
    assert "powerbi/preon-cell-analytics.Report/definition/report.json" in names
    assert "powerbi/preon-cell-analytics.Report/definition/pages/ReportSection/page.json" in names
    assert "powerbi/preon-cell-analytics.pbit" not in names
    assert zip_path.exists()
    assert "parquet" in manifest.formats
    assert "parquet" in manifest.files
    assert not list(tmp_path.rglob("*.csv"))


def test_all_export_zip_deduplicates_shared_parquet_files(tmp_path):
    artifacts = run_simulation(load_scenario(SCENARIO_PATH), seed=10, max_steps=4)
    write_bi_bundle(artifacts, tmp_path, formats=["parquet", "powerbi"])

    zip_path = write_export_zip(tmp_path, "all")

    with ZipFile(zip_path) as archive:
        names = archive.namelist()
    assert len(names) == len(set(names))
    assert "parquet/step_metrics.parquet" in names
    assert "powerbi/preon-cell-analytics.pbip" in names


def test_parquet_files_are_readable_and_include_run_id(tmp_path):
    pyarrow = pytest.importorskip("pyarrow.parquet")
    artifacts = run_simulation(load_scenario(SCENARIO_PATH), seed=11, max_steps=4)

    write_bi_bundle(artifacts, tmp_path, formats=["parquet"])
    table = pyarrow.read_table(tmp_path / "parquet" / "step_metrics.parquet")

    assert "run_id" in table.column_names
    assert table.num_rows == len(artifacts.metrics)


def test_cli_export_bi_reads_run_directory(tmp_path):
    run_dir = tmp_path / "run"
    out_dir = tmp_path / "exports"
    artifacts = run_simulation(load_scenario(SCENARIO_PATH), seed=13, max_steps=4, output_dir=run_dir)

    assert read_run_artifacts(run_dir).metadata.run_id == artifacts.metadata.run_id
    exit_code = cli_main(["export-bi", "--run-dir", str(run_dir), "--out", str(out_dir), "--formats", "parquet,powerbi"])

    assert exit_code == 0
    assert (out_dir / "manifest.json").exists()
    assert (out_dir / "parquet" / "cells.parquet").exists()
    assert not list(out_dir.rglob("*.csv"))


def test_export_bundle_rejects_stale_run_directory(tmp_path):
    first = run_simulation(load_scenario(SCENARIO_PATH), seed=1, max_steps=2)
    second = run_simulation(load_scenario(SCENARIO_PATH), seed=2, max_steps=2)

    write_bi_bundle(first, tmp_path, formats=["parquet"])

    with pytest.raises(ValueError, match="already contains run"):
        write_bi_bundle(second, tmp_path, formats=["parquet"])


def test_export_zip_fails_when_manifest_file_is_missing(tmp_path):
    artifacts = run_simulation(load_scenario(SCENARIO_PATH), seed=3, max_steps=2)
    write_bi_bundle(artifacts, tmp_path, formats=["powerbi"])
    (tmp_path / "powerbi" / "preon-cell-analytics.pbip").unlink()

    with pytest.raises(FileNotFoundError, match="export file missing"):
        write_export_zip(tmp_path, "powerbi")


def test_tableau_bundle_when_hyper_api_is_installed(tmp_path):
    pytest.importorskip("tableauhyperapi")
    artifacts = run_simulation(load_scenario(SCENARIO_PATH), seed=17, max_steps=4)

    manifest = write_bi_bundle(artifacts, tmp_path, formats=["tableau"])

    assert "tableau" in manifest.formats
    assert (tmp_path / "tableau" / "preon-cell-analytics.hyper").exists()
    assert (tmp_path / "tableau" / "preon-cell-analytics.twbx").exists()
