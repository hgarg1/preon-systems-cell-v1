# Preon Systems Cell

Preon Systems Cell is a deterministic, multi-cell simulation and analytics platform for population dynamics, lineage tracing, energy metabolism, and BI-ready run analysis.

The project started as a single-cell ATP simulator and has evolved into a full-stack analytics system:

- Python simulation engine with typed scenario validation
- FastAPI backend with Postgres-first persistence and in-memory fallback
- Next.js analytics dashboard for run history, charts, lineage, cell inspection, and run comparison
- Native BI export pipeline for Parquet, Power BI, and Tableau
- ML-ready analytics layer for future forecasting, clustering, and run characterization

This is biology-inspired and scientifically anchored, but it is not intended to be a literal biochemical simulator. The model is designed for deterministic experimentation, product analytics, and platform architecture work.

## Current Platform

```text
Scenario YAML
    |
    v
Python simulation engine
    |
    +--> typed run artifacts
    +--> per-step metrics
    +--> cell lifecycle state
    +--> lineage and event logs
    |
    v
FastAPI storage API
    |
    +--> Postgres primary storage
    +--> memory fallback when degraded
    +--> BI export bundles
    |
    v
Next.js analytics dashboard
    |
    +--> population and energy charts
    +--> run intelligence panel
    +--> N-run comparison
    +--> 3D lineage visualization
    +--> cell drilldown and event navigation
```

## Highlights

- **Multi-cell architecture**: each run tracks a retained population, alive/dead/divided status, deterministic lineage IDs, and full descendant history.
- **Deterministic lineage**: cells use IDs such as `cell-1.2.1`, making ancestry stable across runs with the same seed and scenario.
- **Cell division semantics**: division creates two daughter cells, splits resources, retains dead/divided cells for history, and continues the simulation until all cells are dead or max steps are reached.
- **Energy metabolism model**: glucose transport, glycolysis, pyruvate oxidation, TCA cycle, electron transport, oxidative phosphorylation, ATP maintenance, repair, growth, toxicity, and membrane integrity.
- **Postgres-first runtime**: dashboard APIs persist and read runs, cells, metrics, events, compare data, and exports from Postgres when available.
- **Graceful fallback**: if Postgres is down, the API starts in memory mode and the dashboard shows a clear yellow degradation ribbon.
- **Analytics dashboard**: production-style Next.js interface with time-series charts, run intelligence, N-run comparisons, lineage visualization, cell details, and native export controls.
- **BI-ready data pipeline**: generates Parquet datasets, Power BI project artifacts, and Tableau Hyper assets without CSV as the primary interface.
- **Tested runtime paths**: backend unit tests, frontend lint/build, live Postgres smoke checks, forced fallback checks, and visual verification of storage status.

## Repository Layout

```text
preon_systems_cell/
  analytics/       Run intelligence, time-series, comparison, feature extraction
  bi/              Parquet, Power BI, and Tableau export pipeline
  domain/          Run and domain-level schema helpers
  storage/         In-memory and Postgres persistence layers
  telemetry/       Metric/event collection and sink abstractions
  api.py           Python API for scenario validation and simulation runs
  engine.py        Core deterministic simulation step logic
  models.py        Pydantic schemas for scenarios, state, events, metrics, runs
  web.py           FastAPI application and dashboard API

frontend/
  src/app/         Next.js App Router pages
  src/components/  Dashboard, charts, lineage scene, cell inspector, UI components
  src/lib/         API client and shared frontend utilities

docs/
  bi-exports.md    Native BI export workflow
  dev-setup.md     Development setup notes
  postgres/        Postgres schema, Timescale fallback, runtime role setup

tests/
  test_*.py        Engine, API, BI, analytics, storage, and web coverage
```

## Requirements

- Python 3.12+
- Node.js 22.12+ and npm 10+
- PostgreSQL for durable storage
- Optional: TimescaleDB, when compatible with your PostgreSQL major version
- Optional BI extras:
  - `pyarrow` for Parquet
  - `tableauhyperapi` for Tableau Hyper

## Quick Start: Backend

Install the Python package with development, BI, and Postgres extras:

```powershell
python -m pip install -e ".[dev,bi,postgres]"
```

Run tests:

```powershell
python -m pytest -q
```

Run a simulation from the CLI:

```powershell
python main.py validate scenarios/default_cell.yaml
python main.py run scenarios/default_cell.yaml --seed 7 --max-steps 80 --out runs/demo
python main.py inspect runs/demo/run_summary.json
```

Start FastAPI:

```powershell
simulate-web
```

If the script is not on your `PATH`:

```powershell
python main.py web
```

FastAPI runs at:

```text
http://127.0.0.1:8000
```

## Quick Start: Next.js Dashboard

In a second shell:

```powershell
cd frontend
npm install
npm run dev
```

Open:

```text
http://127.0.0.1:3000
```

The dashboard uses `NEXT_PUBLIC_API_BASE_URL` and defaults to:

```text
http://127.0.0.1:8000
```

Production build:

```powershell
cd frontend
npm run lint
npm run build
npm run start
```

## Postgres Runtime

The API is Postgres-first when `PREON_DATABASE_URL` is configured. Use a dedicated runtime role rather than the `postgres` superuser.

Recommended connection string shape:

```powershell
$env:PREON_DATABASE_URL = "postgresql://preon_app:<url-encoded app password>@127.0.0.1:5432/preon_systems_cell"
simulate-web
```

Health includes active storage status:

```http
GET /health
```

Healthy Postgres response:

```json
{
  "status": "ok",
  "engine_version": "0.3.0",
  "storage": {
    "mode": "postgres",
    "primary": "postgres",
    "fallback": "memory",
    "degraded": false,
    "reason": null
  }
}
```

Fallback response:

```json
{
  "status": "ok",
  "engine_version": "0.3.0",
  "storage": {
    "mode": "memory",
    "primary": "postgres",
    "fallback": "memory",
    "degraded": true,
    "reason": "Postgres connection failed; using in-memory fallback"
  }
}
```

The dashboard mirrors this state with a storage ribbon:

- green: Postgres connected
- yellow: memory fallback active
- red: API status unavailable

See [docs/postgres/README.md](docs/postgres/README.md) for schema setup, the `preon_app` runtime role, TimescaleDB compatibility notes, and operating guidance.

## FastAPI Dashboard API

The Next.js dashboard consumes the `/api/runs*` family.

```http
GET  /api/runs
POST /api/runs
GET  /api/runs/{run_id}
GET  /api/runs/{run_id}/metrics
GET  /api/runs/{run_id}/timeseries
GET  /api/runs/{run_id}/intelligence
GET  /api/runs/{run_id}/lineage
GET  /api/runs/{run_id}/cells/{cell_id}
GET  /api/runs/{run_id}/cells/{cell_id}/events?scope=lineage
GET  /api/runs/compare?runs=run-a,run-b,run-c
GET  /api/runs/{run_id}/exports
POST /api/runs/{run_id}/exports
GET  /api/runs/{run_id}/exports/{format}/download
WS   /api/runs/{run_id}/stream
```

Create a run:

```json
{
  "scenario": {
    "...": "scenario payload"
  },
  "seed": 7,
  "max_steps": 80
}
```

Compare up to eight runs:

```http
GET /api/runs/compare?runs=run-a,run-b,run-c&resolution=1
```

## Simulation Model

Each run starts from a typed scenario and produces:

- resolved scenario
- run metadata
- final world state
- per-step population metrics
- step snapshots
- per-cell events
- lineage graph
- termination reason

The world state tracks:

- `cells`: retained multi-cell population
- `environment`: glucose, electron acceptor, toxicity, basal levels
- `step` and `time`

Each cell tracks:

- deterministic ID and parent ID
- generation, birth step, death step
- status: alive, divided, dead
- ATP and ADP
- cytosol resources: glucose, pyruvate, NADH, acetyl-CoA, NAD+, FAD, FADH2, CO2, membrane gradient
- biomass, waste, membrane integrity, transporter density
- 3D position

## Analytics

The analytics layer turns raw simulation output into operational signals:

- population versus step
- total ATP and biomass over time
- ATP per alive cell
- peak population
- time to peak
- lifespan
- collapse cause
- early and late growth rate
- survival ratio
- division intensity
- N-run aligned comparison and deltas

These outputs power the dashboard today and can feed forecasting, clustering, and run classification later.

## BI Exports

The export pipeline generates native analysis bundles:

- **Parquet**: typed analytics tables for warehouse and ML workflows
- **Power BI**: native project files for Power BI Desktop workflows
- **Tableau**: Tableau Hyper assets for Tableau analysis

Primary export route:

```http
GET /api/runs/{run_id}/exports/all/download
```

See [docs/bi-exports.md](docs/bi-exports.md) for file layout and optional dependency details.

## Verification

Core commands:

```powershell
python -m pytest -q
cd frontend
npm run lint
npm run build
```

Recent verification scope:

- backend test suite: 58 passing tests
- Next.js lint and production build
- local Postgres smoke through `preon_app`
- forced memory fallback smoke
- BI export ZIP validation
- browser visual check for green Postgres ribbon and yellow fallback ribbon

## Security And Operations

- Do not run the API as the `postgres` superuser outside provisioning or repair work.
- Do not commit database passwords or local `.env` files.
- Use `preon_app` or an equivalent least-privilege runtime role.
- Treat memory fallback as degraded because runs reset when the API process restarts.
- TimescaleDB is optional; on PostgreSQL versions without a compatible Timescale package, standard Postgres indexes remain active.
- Watch structured logs for:
  - `storage_mode_selected`
  - `storage_fallback_activated`
  - `timescale_unavailable_using_standard_postgres`
  - `run_persisted`
  - `bi_export_created`
  - BI export failure events

## Development Notes

The platform is intentionally modular:

- the engine can run without FastAPI
- FastAPI can operate with Postgres or memory fallback
- the dashboard consumes stable JSON contracts
- BI exports reuse run artifacts rather than recomputing simulation state
- analytics code is isolated for future ML feature extraction

That separation keeps the project practical today while leaving room for larger datasets, warehouse integration, and model training workflows.
