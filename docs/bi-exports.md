# BI Exports

The simulator exports analytics data without CSV. Parquet is the canonical dataset, and native BI assets are generated beside it for desktop tools.

## Generate From CLI

```bash
python main.py run scenarios/default_cell.yaml --seed 7 --max-steps 48 --out runs/demo
python main.py export-bi --run-dir runs/demo --out exports/demo --formats parquet,powerbi,tableau
```

Install the optional BI dependencies when Parquet or Tableau export support is needed:

```bash
python -m pip install "preon-systems-cell[bi]"
```

## Bundle Layout

```text
exports/demo/
  manifest.json
  parquet/
    runs.parquet
    step_metrics.parquet
    cells.parquet
    cell_events.parquet
    run_features.parquet
    cell_features.parquet
  powerbi/
    preon-cell-analytics.pbip
    preon-cell-analytics.Report/
    preon-cell-analytics.SemanticModel/
  tableau/
    preon-cell-analytics.hyper
    preon-cell-analytics.twb
    preon-cell-analytics.twbx
```

Every table includes `run_id` and `scenario_name`.

## Power BI

Open `powerbi/preon-cell-analytics.pbip` in Power BI Desktop. The semantic model imports the sibling Parquet dataset generated in the same bundle. `.pbit` files are Power BI binary template packages and are not generated directly; after validating the project locally, use Power BI Desktop to save a `.pbit` template if a distributable template is required.

## Tableau

Open `tableau/preon-cell-analytics.twbx` in Tableau Desktop. The packaged workbook includes the generated Hyper extract.

## Dashboard Downloads

The Next.js analytics dashboard exposes export controls on each run detail page. The buttons call FastAPI to generate a bundle and download a zip for the selected format.
