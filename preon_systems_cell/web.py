from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
import json
import logging
from pathlib import Path
from random import Random
import tempfile

from fastapi import FastAPI, HTTPException
from fastapi import Query, WebSocket
from fastapi import WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from preon_systems_cell.analytics.comparison import compare_runs
from preon_systems_cell.analytics.intelligence import summarize_run_intelligence
from preon_systems_cell.analytics.series import build_time_series
from preon_systems_cell.api import _new_run_id, _scenario_hash, create_cell, run_simulation, step_simulation, step_simulation_api, validate_scenario
from preon_systems_cell.bi import BI_EXPORT_FORMATS, describe_export_formats, read_export_manifest, write_bi_bundle, write_export_zip
from preon_systems_cell.domain.runs import RunRecord, RunStatus
from preon_systems_cell.engine import ENGINE_VERSION, initial_state_for_scenario
from preon_systems_cell.models import (
    CellCreateParams,
    CellCreateResponse,
    Event,
    EventType,
    RunComparisonResponse,
    RunArtifacts,
    RunIntelligence,
    RunTimeSeriesResponse,
    Scenario,
    ValidationReport,
    WorldState,
    TerminationReason,
)
from preon_systems_cell.storage.manager import StorageManager
from preon_systems_cell.storage.postgres import PostgresRunStore, PostgresSettings, PostgresUnavailableError
from preon_systems_cell.storage.repositories import GLOBAL_RUN_REPOSITORY, InMemoryRunRepository


APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
DEFAULT_SCENARIO_PATH = APP_DIR.parent / "scenarios" / "default_cell.yaml"
logger = logging.getLogger("preon_systems_cell.web")


class StepRequest(BaseModel):
    scenario: Scenario
    state: WorldState | None = None
    seed: int = Field(default=7)
    dt: float | None = Field(default=None, gt=0)


class RunRequest(BaseModel):
    scenario: Scenario
    seed: int = Field(default=7)
    max_steps: int | None = Field(default=None, gt=0)
    dt: float | None = Field(default=None, gt=0)


class CreateCellRequest(BaseModel):
    scenario: Scenario
    cell: CellCreateParams | None = None


class ExportRequest(BaseModel):
    formats: list[str] = Field(default_factory=lambda: ["parquet", "powerbi", "tableau"])


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.storage = await StorageManager.create(
            settings=PostgresSettings.from_env(),
            memory=GLOBAL_RUN_REPOSITORY,
        )
        try:
            yield
        finally:
            await _storage_manager(app).close()

    app = FastAPI(
        title="Preon Systems Cell API",
        version=ENGINE_VERSION,
        description="HTTP API and small web UI for the deterministic glucose-centric cell simulator.",
        lifespan=lifespan,
    )
    app.state.run_update_clients = set()
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/health")
    def health() -> dict[str, object]:
        storage = _storage_manager(app)
        return {"status": "ok", "engine_version": ENGINE_VERSION, "storage": storage.status.model_dump()}

    @app.get("/api/default-scenario")
    def get_default_scenario() -> dict[str, object]:
        scenario = _load_default_scenario()
        return {"scenario": scenario.model_dump(mode="json")}

    @app.post("/api/validate", response_model=ValidationReport)
    def validate(request: RunRequest) -> ValidationReport:
        return validate_scenario(request.scenario)

    @app.post("/api/cells", response_model=CellCreateResponse)
    def create_cell_route(request: CreateCellRequest) -> CellCreateResponse:
        report = validate_scenario(request.scenario)
        if not report.valid:
            raise HTTPException(status_code=422, detail=report.errors)
        try:
            return create_cell(request.scenario, request.cell)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=[err["msg"] for err in exc.errors()]) from exc

    @app.post("/api/step")
    def step(request: StepRequest) -> dict[str, object]:
        report = validate_scenario(request.scenario)
        if not report.valid:
            raise HTTPException(status_code=422, detail=report.errors)

        state = request.state or initial_state_for_scenario(request.scenario)
        transition = step_simulation(
            state=state,
            dt=request.dt or request.scenario.simulation.dt,
            rng=Random(request.seed),
            scenario=request.scenario,
        )
        return transition.model_dump(mode="json")

    @app.post("/api/run")
    async def run(request: RunRequest) -> dict[str, object]:
        run_record, artifacts = await _create_materialized_run(app, request)
        await _broadcast_run_created(app, run_record)
        return artifacts.model_dump(mode="json")

    @app.get("/api/runs")
    async def list_runs() -> dict[str, object]:
        storage = _storage_manager(app)
        if storage.postgres is not None:
            runs = await storage.postgres.list_runs()
        else:
            runs = storage.memory.list_runs()
        return {"runs": [run.model_dump(mode="json") for run in runs]}

    @app.post("/api/runs")
    async def create_run(request: RunRequest) -> dict[str, object]:
        run_record, artifacts = await _create_materialized_run(app, request)
        await _broadcast_run_created(app, run_record)
        return {
            "run": run_record.model_dump(mode="json"),
            "final_state": artifacts.final_state.model_dump(mode="json"),
            "termination_reason": artifacts.termination_reason.value,
        }

    @app.post("/runs/start")
    async def start_persisted_run(request: RunRequest) -> dict[str, object]:
        store = _postgres_store(app)
        report = validate_scenario(request.scenario)
        if not report.valid:
            raise HTTPException(status_code=422, detail=report.errors)
        scenario = _effective_scenario(request.scenario, request.dt)
        max_steps = request.max_steps if request.max_steps is not None else scenario.simulation.max_steps
        run_record = RunRecord(
            run_id=_new_run_id(),
            scenario_name=scenario.scenario_name,
            scenario_hash=_scenario_hash(scenario),
            seed=request.seed,
            status=RunStatus.RUNNING,
            started_at=datetime.now(UTC),
            max_steps=max_steps,
        )
        state = initial_state_for_scenario(scenario)
        rng = Random(request.seed)
        await store.start_run(run_record, scenario, state, rng)
        return {"run": run_record.model_dump(mode="json"), "state": state.model_dump(mode="json")}

    @app.post("/runs/{run_id}/step")
    async def step_persisted_run(run_id: str) -> dict[str, object]:
        store = _postgres_store(app)
        context = await store.load_run_context(run_id)
        if context is None:
            raise HTTPException(status_code=404, detail="run not found")
        if context.run.status != RunStatus.RUNNING:
            raise HTTPException(status_code=409, detail=f"run is {context.run.status.value}")

        transition = step_simulation_api(context.state, context.scenario, context.rng)
        termination_reason = transition.termination_reason
        completed = transition.terminated
        events = list(transition.events)
        if not completed and transition.state.step >= context.run.max_steps:
            termination_reason = TerminationReason.MAX_STEPS_REACHED
            completed = True
            events.append(
                Event(
                    step=transition.state.step,
                    time=transition.state.time,
                    type=EventType.TERMINATION,
                    message="Simulation terminated after reaching max steps",
                    values={"reason": termination_reason.value},
                )
            )
            transition = transition.model_copy(
                update={"events": events, "terminated": True, "termination_reason": termination_reason}
            )

        next_run = context.run.model_copy(
            update={
                "status": RunStatus.COMPLETED if completed else RunStatus.RUNNING,
                "completed_at": datetime.now(UTC) if completed else None,
                "final_step": transition.state.step if completed else None,
                "termination_reason": termination_reason.value if termination_reason else None,
            }
        )
        await store.append_step(next_run, transition, context.rng)
        return {"run": next_run.model_dump(mode="json"), "transition": transition.model_dump(mode="json")}

    @app.get("/runs/{run_id}/metrics")
    async def get_persisted_metrics(
        run_id: str,
        from_step: int = Query(default=0, ge=0),
        to_step: int | None = Query(default=None, ge=0),
        resolution: int = Query(default=1, ge=1),
    ) -> dict[str, object]:
        _validate_step_window(from_step, to_step)
        store = _postgres_store(app)
        if not await store.run_exists(run_id):
            raise HTTPException(status_code=404, detail="run not found")
        return {
            "run_id": run_id,
            "resolution": resolution,
            "series": await store.get_metrics(run_id, from_step, to_step, resolution),
        }

    @app.get("/runs/{run_id}/cells")
    async def get_persisted_cells(run_id: str) -> dict[str, object]:
        store = _postgres_store(app)
        cells = await store.get_cells(run_id)
        if cells is None:
            raise HTTPException(status_code=404, detail="run not found")
        return {"run_id": run_id, "cells": cells}

    @app.get("/runs/{run_id}/events")
    async def get_persisted_events(
        run_id: str,
        cell_id: str | None = None,
        from_step: int = Query(default=0, ge=0),
        to_step: int | None = Query(default=None, ge=0),
        event_type: str | None = None,
        limit: int = Query(default=5000, ge=1, le=50000),
    ) -> dict[str, object]:
        _validate_step_window(from_step, to_step)
        store = _postgres_store(app)
        events = await store.get_events(run_id, cell_id, from_step, to_step, event_type, limit)
        if events is None:
            raise HTTPException(status_code=404, detail="run not found")
        return {"run_id": run_id, "events": events}

    @app.get("/api/runs/compare", response_model=RunComparisonResponse)
    async def compare_run_set(
        runs: str = Query(..., min_length=1),
        resolution: int = Query(default=1, ge=1),
        from_step: int = Query(default=0, ge=0),
        to_step: int | None = Query(default=None, ge=0),
    ) -> RunComparisonResponse:
        _validate_step_window(from_step, to_step)
        run_ids = _parse_compare_run_ids(runs)
        if len(run_ids) < 2:
            raise HTTPException(status_code=422, detail="compare requires at least two unique runs")
        if len(run_ids) > 8:
            raise HTTPException(status_code=422, detail="compare supports at most 8 runs")
        storage = _storage_manager(app)
        pairs = []
        for run_id in run_ids:
            if storage.postgres is not None:
                run_record = await storage.postgres.get_run(run_id)
                artifacts = await storage.postgres.get_artifacts(run_id)
            else:
                run_record = storage.memory.get_run(run_id)
                artifacts = storage.memory.get_artifacts(run_id)
            if run_record is None or artifacts is None:
                raise HTTPException(status_code=404, detail=f"run not found: {run_id}")
            pairs.append((run_record, artifacts))
        return compare_runs(pairs, resolution=resolution, from_step=from_step, to_step=to_step)

    @app.websocket("/api/runs/updates")
    async def stream_run_updates(websocket: WebSocket) -> None:
        await websocket.accept()
        clients = _run_update_clients(app)
        clients.add(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            clients.discard(websocket)
        except Exception:
            clients.discard(websocket)

    @app.get("/api/runs/{run_id}")
    async def get_run(run_id: str) -> dict[str, object]:
        run_record = await _get_run_record(app, run_id)
        if run_record is None:
            raise HTTPException(status_code=404, detail="run not found")
        return {"run": run_record.model_dump(mode="json")}

    @app.post("/api/runs/{run_id}/start")
    async def start_run(run_id: str) -> dict[str, object]:
        run_record = await _get_run_record(app, run_id)
        if run_record is None:
            raise HTTPException(status_code=404, detail="run not found")
        return {"run": run_record.model_dump(mode="json")}

    @app.post("/api/runs/{run_id}/cancel")
    async def cancel_run(run_id: str) -> dict[str, object]:
        run_record = await _get_run_record(app, run_id)
        if run_record is None:
            raise HTTPException(status_code=404, detail="run not found")
        return {"run": run_record.model_dump(mode="json"), "cancelled": False, "reason": "run already materialized"}

    @app.get("/api/runs/{run_id}/metrics")
    async def get_run_metrics(
        run_id: str,
        from_step: int = Query(default=0, ge=0),
        to_step: int | None = Query(default=None, ge=0),
        resolution: int = Query(default=1, ge=1),
    ) -> dict[str, object]:
        _validate_step_window(from_step, to_step)
        storage = _storage_manager(app)
        if await _get_run_record(app, run_id) is None:
            raise HTTPException(status_code=404, detail="run not found")
        if storage.postgres is not None:
            series = await storage.postgres.get_metrics(run_id, from_step, to_step, resolution)
        else:
            series = storage.memory.get_metrics(run_id, from_step, to_step, resolution)
        return {
            "run_id": run_id,
            "resolution": resolution,
            "series": series,
        }

    @app.get("/api/runs/{run_id}/timeseries", response_model=RunTimeSeriesResponse)
    async def get_run_timeseries(
        run_id: str,
        from_step: int = Query(default=0, ge=0),
        to_step: int | None = Query(default=None, ge=0),
        resolution: int = Query(default=1, ge=1),
    ) -> RunTimeSeriesResponse:
        _validate_step_window(from_step, to_step)
        artifacts = await _get_run_artifacts(app, run_id)
        if artifacts is None:
            raise HTTPException(status_code=404, detail="run not found")
        return RunTimeSeriesResponse(
            run_id=run_id,
            resolution=resolution,
            points=build_time_series(artifacts, from_step=from_step, to_step=to_step, resolution=resolution),
        )

    @app.get("/api/runs/{run_id}/intelligence", response_model=RunIntelligence)
    async def get_run_intelligence(run_id: str) -> RunIntelligence:
        artifacts = await _get_run_artifacts(app, run_id)
        if artifacts is None:
            raise HTTPException(status_code=404, detail="run not found")
        return summarize_run_intelligence(artifacts)

    @app.get("/api/runs/{run_id}/lineage")
    async def get_lineage(run_id: str, root: str | None = None) -> dict[str, object]:
        storage = _storage_manager(app)
        if await _get_run_record(app, run_id) is None:
            raise HTTPException(status_code=404, detail="run not found")
        if root is not None and await _get_cell_state(app, run_id, root) is None:
            raise HTTPException(status_code=404, detail="cell not found")
        if storage.postgres is not None:
            lineage = await storage.postgres.lineage(run_id, root)
        else:
            lineage = storage.memory.lineage(run_id, root)
        return lineage if lineage is not None else {"run_id": run_id, "root": root, "nodes": [], "edges": []}

    @app.get("/api/runs/{run_id}/cells/{cell_id}")
    async def get_cell(run_id: str, cell_id: str) -> dict[str, object]:
        cell = await _get_cell_state(app, run_id, cell_id)
        if cell is None:
            raise HTTPException(status_code=404, detail="cell not found")
        return {"run_id": run_id, "cell": cell.model_dump(mode="json")}

    @app.get("/api/runs/{run_id}/cells/{cell_id}/events")
    async def get_cell_events(run_id: str, cell_id: str, scope: str = "self") -> dict[str, object]:
        if scope not in {"self", "lineage", "descendants"}:
            raise HTTPException(status_code=422, detail="scope must be self, lineage, or descendants")
        storage = _storage_manager(app)
        if await _get_run_record(app, run_id) is None:
            raise HTTPException(status_code=404, detail="run not found")
        if await _get_cell_state(app, run_id, cell_id) is None:
            raise HTTPException(status_code=404, detail="cell not found")
        if storage.postgres is not None:
            events = await storage.postgres.cell_events(run_id, cell_id, scope)
        else:
            events = storage.memory.cell_events(run_id, cell_id, scope)
        if events is None:
            events = []
        return {"run_id": run_id, "cell_id": cell_id, "scope": scope, "events": [event.model_dump(mode="json") for event in events]}

    @app.get("/api/runs/{run_id}/exports")
    async def get_run_exports(run_id: str) -> dict[str, object]:
        if await _get_run_record(app, run_id) is None:
            raise HTTPException(status_code=404, detail="run not found")
        manifest = read_export_manifest(_export_dir(run_id))
        return {
            "run_id": run_id,
            "formats": describe_export_formats(),
            "manifest": manifest.model_dump(mode="json") if manifest is not None else None,
        }

    @app.post("/api/runs/{run_id}/exports")
    async def create_run_exports(run_id: str, request: ExportRequest) -> dict[str, object]:
        artifacts = await _get_run_artifacts(app, run_id)
        if artifacts is None:
            raise HTTPException(status_code=404, detail="run not found")
        try:
            manifest = write_bi_bundle(artifacts, _export_dir(run_id), request.formats)
            logger.info(
                "bi_export_created",
                extra={"run_id": run_id, "formats": ",".join(request.formats), "storage_mode": _storage_manager(app).status.mode},
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RuntimeError as exc:
            logger.exception("bi_export_failed", extra={"run_id": run_id, "formats": ",".join(request.formats)})
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return {"run_id": run_id, "manifest": manifest.model_dump(mode="json")}

    @app.get("/api/runs/{run_id}/exports/{export_format}/download")
    async def download_run_export(run_id: str, export_format: str) -> FileResponse:
        artifacts = await _get_run_artifacts(app, run_id)
        if artifacts is None:
            raise HTTPException(status_code=404, detail="run not found")
        formats = list(BI_EXPORT_FORMATS) if export_format == "all" else [export_format]
        try:
            manifest = read_export_manifest(_export_dir(run_id))
            if manifest is None or any(item not in manifest.formats for item in formats):
                write_bi_bundle(artifacts, _export_dir(run_id), formats)
            zip_path = write_export_zip(_export_dir(run_id), export_format)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except RuntimeError as exc:
            logger.exception("bi_export_download_failed", extra={"run_id": run_id, "format": export_format})
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return FileResponse(
            zip_path,
            media_type="application/zip",
            filename=f"{run_id}-{export_format}.zip",
        )

    @app.websocket("/api/runs/{run_id}/stream")
    async def stream_run(websocket: WebSocket, run_id: str) -> None:
        await websocket.accept()
        artifacts = await _get_run_artifacts(app, run_id)
        if artifacts is None:
            await websocket.send_json({"type": "error", "message": "run not found"})
            await websocket.close()
            return
        events_by_step = {}
        for event in artifacts.events:
            events_by_step.setdefault(event.step, []).append(event.model_dump(mode="json"))
        for metric in artifacts.metrics:
            await websocket.send_json(
                {
                    "type": "step",
                    "run_id": run_id,
                    "metrics": metric.model_dump(mode="json"),
                    "events": events_by_step.get(metric.step, []),
                }
            )
        await websocket.send_json({"type": "complete", "run_id": run_id, "termination_reason": artifacts.termination_reason.value})
        await websocket.close()

    @app.get("/", response_class=FileResponse)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    return app


def _load_default_scenario() -> Scenario:
    try:
        raw = json.loads(DEFAULT_SCENARIO_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        import yaml

        raw = yaml.safe_load(DEFAULT_SCENARIO_PATH.read_text(encoding="utf-8"))
    try:
        return Scenario.model_validate(raw)
    except ValidationError as exc:
        raise RuntimeError(f"default scenario is invalid: {exc}") from exc


def _export_dir(run_id: str) -> Path:
    return Path(tempfile.gettempdir()) / "preon-systems-cell-exports" / run_id


def _parse_compare_run_ids(raw: str) -> list[str]:
    run_ids = []
    for item in raw.split(","):
        run_id = item.strip()
        if run_id and run_id not in run_ids:
            run_ids.append(run_id)
    return run_ids


def _validate_step_window(from_step: int, to_step: int | None) -> None:
    if to_step is not None and to_step < from_step:
        raise HTTPException(status_code=422, detail="to_step must be greater than or equal to from_step")


async def _create_materialized_run(app: FastAPI, request: RunRequest) -> tuple[RunRecord, RunArtifacts]:
    report = validate_scenario(request.scenario)
    if not report.valid:
        raise HTTPException(status_code=422, detail=report.errors)

    storage = _storage_manager(app)
    repository = InMemoryRunRepository() if storage.postgres is not None else storage.memory
    artifacts = run_simulation(
        scenario=request.scenario,
        seed=request.seed,
        max_steps=request.max_steps,
        dt=request.dt,
        repository=repository,
    )
    run_record = repository.get_run(artifacts.metadata.run_id)
    if run_record is None:
        raise HTTPException(status_code=500, detail="run was created without a run record")

    if storage.postgres is not None:
        await storage.postgres.save_artifacts(run_record, artifacts)
        logger.info(
            "run_persisted",
            extra={
                "run_id": run_record.run_id,
                "storage_mode": storage.status.mode,
                "metric_count": len(artifacts.metrics),
                "event_count": len(artifacts.events),
                "cell_count": len(artifacts.final_state.cells),
            },
        )
    return run_record, artifacts


def _run_update_clients(app: FastAPI) -> set[WebSocket]:
    clients = getattr(app.state, "run_update_clients", None)
    if clients is None:
        clients = set()
        app.state.run_update_clients = clients
    return clients


async def _broadcast_run_created(app: FastAPI, run_record: RunRecord) -> None:
    clients = set(_run_update_clients(app))
    if not clients:
        return

    storage = _storage_manager(app)
    payload = {
        "type": "run_created",
        "run": run_record.model_dump(mode="json"),
        "storage": storage.status.model_dump(),
    }
    stale_clients = []
    for websocket in clients:
        try:
            await websocket.send_json(payload)
        except Exception:
            stale_clients.append(websocket)
    for websocket in stale_clients:
        _run_update_clients(app).discard(websocket)


def _effective_scenario(scenario: Scenario, dt: float | None) -> Scenario:
    if dt is None or dt == scenario.simulation.dt:
        return scenario
    return scenario.model_copy(update={"simulation": scenario.simulation.model_copy(update={"dt": dt})})


def _storage_manager(app: FastAPI) -> StorageManager:
    storage = getattr(app.state, "storage", None)
    if storage is None:
        storage = StorageManager(memory=GLOBAL_RUN_REPOSITORY, postgres=None, status=_memory_status("app storage not initialized"))
        app.state.storage = storage
    return storage


def _memory_status(reason: str):
    from preon_systems_cell.storage.manager import StorageStatus

    return StorageStatus(mode="memory", primary="postgres", fallback="memory", degraded=True, reason=reason)


async def _get_run_record(app: FastAPI, run_id: str) -> RunRecord | None:
    storage = _storage_manager(app)
    if storage.postgres is not None:
        return await storage.postgres.get_run(run_id)
    return storage.memory.get_run(run_id)


async def _get_run_artifacts(app: FastAPI, run_id: str):
    storage = _storage_manager(app)
    if storage.postgres is not None:
        return await storage.postgres.get_artifacts(run_id)
    return storage.memory.get_artifacts(run_id)


async def _get_cell_state(app: FastAPI, run_id: str, cell_id: str):
    storage = _storage_manager(app)
    if storage.postgres is not None:
        return await storage.postgres.get_cell(run_id, cell_id)
    return storage.memory.get_cell(run_id, cell_id)


def _postgres_store(app: FastAPI) -> PostgresRunStore:
    storage = _storage_manager(app)
    if storage.postgres is None:
        raise HTTPException(
            status_code=503,
            detail=f"Postgres persistence is unavailable; active storage mode is {storage.status.mode}",
        )
    store = storage.postgres
    if isinstance(store, PostgresUnavailableError):
        raise HTTPException(status_code=503, detail=str(store))
    return store


app = create_app()


def main(host: str = "127.0.0.1", port: int = 8000) -> None:
    import uvicorn

    uvicorn.run("preon_systems_cell.web:app", host=host, port=port, reload=False)
