from __future__ import annotations

import html
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile


TABLEAU_WORKBOOK_NAME = "preon-cell-analytics"


def write_tableau_bundle(directory: str | Path, tables: dict[str, list[dict[str, Any]]]) -> list[Path]:
    try:
        from tableauhyperapi import (
            Connection,
            CreateMode,
            HyperProcess,
            Inserter,
            SqlType,
            TableDefinition,
            TableName,
            Telemetry,
        )
    except ImportError as exc:
        raise RuntimeError("Tableau export requires tableauhyperapi. Install with: pip install 'preon-systems-cell[bi]'") from exc

    destination = Path(directory)
    destination.mkdir(parents=True, exist_ok=True)
    hyper_path = destination / f"{TABLEAU_WORKBOOK_NAME}.hyper"
    twb_path = destination / f"{TABLEAU_WORKBOOK_NAME}.twb"
    twbx_path = destination / f"{TABLEAU_WORKBOOK_NAME}.twbx"

    with HyperProcess(telemetry=Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU) as hyper:
        with Connection(endpoint=hyper.endpoint, database=hyper_path, create_mode=CreateMode.CREATE_AND_REPLACE) as connection:
            connection.catalog.create_schema("Extract")
            for table_name, rows in tables.items():
                definition = TableDefinition(
                    table_name=TableName("Extract", table_name),
                    columns=[
                        TableDefinition.Column(column, _hyper_type(SqlType, _sample_value(rows, column)))
                        for column in _columns(rows)
                    ],
                )
                connection.catalog.create_table(definition)
                if rows:
                    with Inserter(connection, definition) as inserter:
                        inserter.add_rows([[_coerce_value(row.get(column)) for column in _columns(rows)] for row in rows])
                        inserter.execute()

    twb_path.write_text(_tableau_workbook_xml(hyper_path.name, tables), encoding="utf-8")
    _write_twbx(twbx_path, twb_path, hyper_path)
    readme_path = _write_readme(destination / "README.md")
    return [hyper_path, twb_path, twbx_path, readme_path]


def _columns(rows: list[dict[str, Any]]) -> list[str]:
    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    return columns


def _sample_value(rows: list[dict[str, Any]], column: str) -> Any:
    for row in rows:
        value = row.get(column)
        if value is not None:
            return value
    return None


def _hyper_type(sql_type: Any, value: Any) -> Any:
    if isinstance(value, bool):
        return sql_type.bool()
    if isinstance(value, int):
        return sql_type.big_int()
    if isinstance(value, float):
        return sql_type.double()
    return sql_type.text()


def _coerce_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str | int | float | bool):
        return value
    return str(value)


def _tableau_workbook_xml(hyper_filename: str, tables: dict[str, list[dict[str, Any]]]) -> str:
    datasource_name = "preon-cell-analytics"
    relations = "\n".join(
        f'      <relation connection="hyper" name="{html.escape(name)}" table="[Extract].[{html.escape(name)}]" type="table" />'
        for name in tables
    )
    return f"""<?xml version='1.0' encoding='utf-8'?>
<workbook source-build='preon-systems-cell' source-platform='win' version='18.1'>
  <datasources>
    <datasource caption='Preon Cell Analytics' inline='true' name='{datasource_name}' version='18.1'>
      <connection class='hyper' dbname='{html.escape(hyper_filename)}' filename='{html.escape(hyper_filename)}' server=''>
{relations}
      </connection>
    </datasource>
  </datasources>
  <worksheets>
    <worksheet name='Run Summary'>
      <table>
        <view>
          <datasources>
            <datasource caption='Preon Cell Analytics' name='{datasource_name}' />
          </datasources>
        </view>
      </table>
    </worksheet>
  </worksheets>
</workbook>
"""


def _write_twbx(path: Path, twb_path: Path, hyper_path: Path) -> None:
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.write(twb_path, twb_path.name)
        archive.write(hyper_path, hyper_path.name)


def _write_readme(path: Path) -> Path:
    path.write_text(
        "\n".join(
            [
                "# Tableau Native Assets",
                "",
                "Open `preon-cell-analytics.twbx` in Tableau Desktop.",
                "The packaged workbook includes `preon-cell-analytics.hyper` with the exported BI tables.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path
