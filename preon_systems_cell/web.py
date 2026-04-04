from __future__ import annotations

import json
from pathlib import Path
from random import Random

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from preon_systems_cell.api import create_cell, run_simulation, step_simulation, validate_scenario
from preon_systems_cell.engine import ENGINE_VERSION, initial_state_for_scenario
from preon_systems_cell.models import CellCreateParams, CellCreateResponse, Scenario, ValidationReport, WorldState


APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
DEFAULT_SCENARIO_PATH = APP_DIR.parent / "scenarios" / "default_cell.yaml"


class StepRequest(BaseModel):
    scenario: Scenario
    state: WorldState | None = None
    seed: int = Field(default=7)
    dt: float | None = None


class RunRequest(BaseModel):
    scenario: Scenario
    seed: int = Field(default=7)
    max_steps: int | None = None
    dt: float | None = None


class CreateCellRequest(BaseModel):
    scenario: Scenario
    cell: CellCreateParams | None = None


def create_app() -> FastAPI:
    app = FastAPI(
        title="Preon Systems Cell API",
        version=ENGINE_VERSION,
        description="HTTP API and small web UI for the deterministic glucose-centric cell simulator.",
    )
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "engine_version": ENGINE_VERSION}

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
    def run(request: RunRequest) -> dict[str, object]:
        report = validate_scenario(request.scenario)
        if not report.valid:
            raise HTTPException(status_code=422, detail=report.errors)

        artifacts = run_simulation(
            scenario=request.scenario,
            seed=request.seed,
            max_steps=request.max_steps,
            dt=request.dt,
        )
        return artifacts.model_dump(mode="json")

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


app = create_app()


def main(host: str = "127.0.0.1", port: int = 8000) -> None:
    import uvicorn

    uvicorn.run("preon_systems_cell.web:app", host=host, port=port, reload=False)
