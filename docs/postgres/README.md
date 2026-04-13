# Postgres Persistence Setup

The FastAPI backend is Postgres-first when `PREON_DATABASE_URL` is configured. The dashboard-facing `/api/runs*` routes persist and read runs, metrics, lineage, events, compare data, streams, and BI exports from Postgres. If Postgres is unavailable, the app starts in memory fallback mode and exposes that state through `/health` and the Next.js storage ribbon.

Do not commit database passwords. Put the connection string in your shell or process manager.

## 1. Create Database

```powershell
$env:PGPASSWORD = "<local postgres password>"
createdb -h 127.0.0.1 -U postgres preon_systems_cell
```

If the database already exists, skip `createdb`.

## 2. Apply Schema

```powershell
$env:PGPASSWORD = "<local postgres password>"
psql -h 127.0.0.1 -U postgres -d preon_systems_cell -f docs/postgres/schema.sql
```

## 3. Optional TimescaleDB

TimescaleDB support can lag new PostgreSQL majors. If PostgreSQL 18 is not supported by the installed Timescale package, keep standard Postgres and use the indexes in `schema.sql`.

Detect availability:

```sql
SELECT version();
SELECT name, default_version, installed_version
FROM pg_available_extensions
WHERE name = 'timescaledb';
```

Enable when available:

```powershell
$env:PGPASSWORD = "<local postgres password>"
psql -h 127.0.0.1 -U postgres -d preon_systems_cell -f docs/postgres/timescale_optional.sql
```

If this prints a notice that TimescaleDB is unavailable or cannot be enabled, no application change is required. `step_metrics` remains a regular table with `(run_id, step)` and `step` indexes.

## 4. Install Python DB Dependency

```powershell
python -m pip install -e ".[postgres]"
```

## 5. Create A Runtime App User

Use the `postgres` account for local provisioning only. Run the API as a separate login role.

```powershell
$env:PGPASSWORD = "<local postgres admin password>"
psql -h 127.0.0.1 -U postgres -d postgres
```

```sql
CREATE ROLE preon_app LOGIN PASSWORD '<generated app password>';
GRANT CONNECT ON DATABASE preon_systems_cell TO preon_app;
\connect preon_systems_cell
GRANT USAGE, CREATE ON SCHEMA public TO preon_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO preon_app;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO preon_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO preon_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO preon_app;
```

For local development, the role may also own the app schema objects so startup schema checks and future local migrations can run without the superuser:

```sql
ALTER SCHEMA public OWNER TO preon_app;
ALTER TABLE runs OWNER TO preon_app;
ALTER TABLE cells OWNER TO preon_app;
ALTER TABLE step_metrics OWNER TO preon_app;
ALTER TABLE events OWNER TO preon_app;
ALTER SEQUENCE events_event_id_seq OWNER TO preon_app;
```

## 6. Run FastAPI With Postgres Enabled

```powershell
$env:PREON_DATABASE_URL = "postgresql://preon_app:<url-encoded app password>@127.0.0.1:5432/preon_systems_cell"
simulate-web
```

URL-encode reserved password characters before placing them in the connection URL. For example, `@` becomes `%40`, `#` becomes `%23`, and `!` becomes `%21`.

The password above should be provided locally only. For production, use your secret manager or platform environment variables.

Optional controls:

```powershell
$env:PREON_STORAGE_MODE = "memory"       # force memory fallback for local debugging
$env:PREON_DB_ENABLE_TIMESCALE = "true"  # attempt TimescaleDB; standard Postgres remains active if unavailable
```

Check active storage mode:

```http
GET /health
```

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

## 7. Dashboard API

Create a fully materialized persisted run:

```http
POST /api/runs
Content-Type: application/json

{
  "scenario": { "...": "default scenario payload" },
  "seed": 7,
  "max_steps": 80
}
```

Read dashboard data:

```http
GET /api/runs
GET /api/runs/run-abc123
GET /api/runs/run-abc123/metrics?from_step=0&to_step=80&resolution=1
GET /api/runs/run-abc123/timeseries
GET /api/runs/run-abc123/intelligence
GET /api/runs/run-abc123/lineage
GET /api/runs/run-abc123/cells/cell-1
GET /api/runs/run-abc123/cells/cell-1/events?scope=lineage
GET /api/runs/compare?runs=run-a,run-b,run-c
POST /api/runs/run-abc123/exports
GET /api/runs/run-abc123/exports/all/download
```

## 8. Incremental DB-Backed Endpoints

Start a persisted run:

```http
POST /runs/start
Content-Type: application/json

{
  "scenario": { "...": "default scenario payload" },
  "seed": 7,
  "max_steps": 80
}
```

Step the run:

```http
POST /runs/run-abc123/step
```

Read persisted metrics:

```http
GET /runs/run-abc123/metrics?from_step=0&to_step=80&resolution=1
```

Read cells:

```http
GET /runs/run-abc123/cells
```

Read events:

```http
GET /runs/run-abc123/events?cell_id=cell-1&from_step=0&limit=500
```

## 9. Operating Notes

1. Keep `PREON_DATABASE_URL` set in local, staging, and production when durable run history is required.
2. Watch structured log events: `storage_mode_selected`, `storage_fallback_activated`, `timescale_unavailable_using_standard_postgres`, `run_persisted`, `bi_export_created`, and export failure events.
3. Treat memory fallback as degraded. It is useful for development and demo continuity, but runs reset when the API process restarts.
4. TimescaleDB is optional. On PostgreSQL 18 without a compatible Timescale package, the schema keeps standard indexes on `(run_id, step)` for time-series reads.
5. Do not run the API with the `postgres` superuser outside one-off provisioning or repair work.
