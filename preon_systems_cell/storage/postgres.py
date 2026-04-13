from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import logging
import os
from pathlib import Path
from random import Random
from typing import Any

from preon_systems_cell.domain.runs import RunRecord
from preon_systems_cell.engine import ENGINE_VERSION
from preon_systems_cell.models import (
    CellState,
    Event,
    PopulationMetrics,
    RunArtifacts,
    RunMetadata,
    Scenario,
    StepTransition,
    TerminationReason,
    WorldState,
)

try:
    import asyncpg
except ImportError:  # pragma: no cover - exercised only when optional dependency is absent
    asyncpg = None  # type: ignore[assignment]


SQL_DIR = Path(__file__).resolve().parent / "sql"
SCHEMA_PATH = SQL_DIR / "schema.sql"
TIMESCALE_PATH = SQL_DIR / "timescale_optional.sql"
logger = logging.getLogger("preon_systems_cell.storage.postgres")


@dataclass(frozen=True)
class PostgresSettings:
    database_url: str | None = None
    min_pool_size: int = 1
    max_pool_size: int = 8
    command_timeout: float = 30.0
    enable_timescale: bool = False

    @classmethod
    def from_env(cls) -> "PostgresSettings":
        return cls(
            database_url=os.getenv("PREON_DATABASE_URL") or os.getenv("DATABASE_URL"),
            min_pool_size=int(os.getenv("PREON_DB_POOL_MIN", "1")),
            max_pool_size=int(os.getenv("PREON_DB_POOL_MAX", "8")),
            command_timeout=float(os.getenv("PREON_DB_COMMAND_TIMEOUT", "30")),
            enable_timescale=os.getenv("PREON_DB_ENABLE_TIMESCALE", "").lower() in {"1", "true", "yes"},
        )


@dataclass(frozen=True)
class PersistedRunContext:
    run: RunRecord
    scenario: Scenario
    state: WorldState
    rng: Random


class PostgresUnavailableError(RuntimeError):
    pass


class PostgresRunStore:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    @classmethod
    async def create(cls, settings: PostgresSettings) -> "PostgresRunStore":
        if not settings.database_url:
            raise PostgresUnavailableError("PREON_DATABASE_URL is not configured")
        if asyncpg is None:
            raise PostgresUnavailableError('asyncpg is not installed; run python -m pip install -e ".[postgres]"')
        pool = await asyncpg.create_pool(
            dsn=settings.database_url,
            min_size=settings.min_pool_size,
            max_size=settings.max_pool_size,
            command_timeout=settings.command_timeout,
        )
        store = cls(pool)
        try:
            await store.apply_schema(enable_timescale=settings.enable_timescale)
        except Exception:
            await pool.close()
            raise
        return store

    async def close(self) -> None:
        await self._pool.close()

    async def apply_schema(self, enable_timescale: bool = False) -> None:
        schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
        async with self._pool.acquire() as connection:
            await connection.execute(schema_sql)
            if enable_timescale:
                try:
                    await connection.execute(TIMESCALE_PATH.read_text(encoding="utf-8"))
                except Exception as exc:
                    logger.warning("timescale_unavailable_using_standard_postgres", extra={"reason": str(exc)})

    async def start_run(self, run: RunRecord, scenario: Scenario, state: WorldState, rng: Random) -> None:
        buffer = PostgresRunBuffer()
        buffer.extend_cells(run.run_id, state.cells, state.step)
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    """
                    INSERT INTO runs (
                        run_id, scenario_name, scenario_hash, engine_version, seed, status,
                        started_at, completed_at, max_steps, final_step, termination_reason,
                        scenario, current_state, rng_state
                    )
                    VALUES (
                        $1, $2, $3, $4, $5, $6,
                        $7, $8, $9, $10, $11,
                        $12::jsonb, $13::jsonb, $14::jsonb
                    )
                    ON CONFLICT (run_id) DO UPDATE SET
                        status = EXCLUDED.status,
                        current_state = EXCLUDED.current_state,
                        rng_state = EXCLUDED.rng_state,
                        updated_at = now()
                    """,
                    run.run_id,
                    run.scenario_name,
                        run.scenario_hash,
                    ENGINE_VERSION,
                    run.seed,
                    run.status.value,
                    _utc(run.started_at),
                    _utc(run.completed_at) if run.completed_at else None,
                    run.max_steps,
                    run.final_step,
                    run.termination_reason,
                    _json(scenario),
                    _json(state),
                    _json(encode_rng_state(rng)),
                )
                await buffer.flush(connection)

    async def save_artifacts(self, run: RunRecord, artifacts: RunArtifacts) -> None:
        """Persist a fully materialized run produced by the batch simulation API."""
        rng = Random(run.seed)
        buffer = PostgresRunBuffer()
        for metric in artifacts.metrics:
            buffer.add_metric(run.run_id, metric)
        buffer.extend_events(run.run_id, artifacts.events)
        buffer.extend_cells(run.run_id, artifacts.final_state.cells, artifacts.final_state.step)
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    """
                    INSERT INTO runs (
                        run_id, scenario_name, scenario_hash, engine_version, seed, status,
                        started_at, completed_at, max_steps, final_step, termination_reason,
                        scenario, current_state, rng_state
                    )
                    VALUES (
                        $1, $2, $3, $4, $5, $6,
                        $7, $8, $9, $10, $11,
                        $12::jsonb, $13::jsonb, $14::jsonb
                    )
                    ON CONFLICT (run_id) DO UPDATE SET
                        scenario_name = EXCLUDED.scenario_name,
                        scenario_hash = EXCLUDED.scenario_hash,
                        engine_version = EXCLUDED.engine_version,
                        seed = EXCLUDED.seed,
                        status = EXCLUDED.status,
                        completed_at = EXCLUDED.completed_at,
                        max_steps = EXCLUDED.max_steps,
                        final_step = EXCLUDED.final_step,
                        termination_reason = EXCLUDED.termination_reason,
                        scenario = EXCLUDED.scenario,
                        current_state = EXCLUDED.current_state,
                        rng_state = EXCLUDED.rng_state,
                        updated_at = now()
                    """,
                    run.run_id,
                    run.scenario_name,
                    run.scenario_hash,
                    ENGINE_VERSION,
                    run.seed,
                    run.status.value,
                    _utc(run.started_at),
                    _utc(run.completed_at) if run.completed_at else None,
                    run.max_steps,
                    run.final_step,
                    run.termination_reason,
                    _json(artifacts.resolved_scenario),
                    _json(artifacts.final_state),
                    _json(encode_rng_state(rng)),
                )
                await connection.execute("DELETE FROM events WHERE run_id = $1", run.run_id)
                await connection.execute("DELETE FROM step_metrics WHERE run_id = $1", run.run_id)
                await connection.execute("DELETE FROM cells WHERE run_id = $1", run.run_id)
                await buffer.flush(connection)

    async def list_runs(self) -> list[RunRecord]:
        async with self._pool.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT run_id, scenario_name, scenario_hash, seed, status, started_at,
                       completed_at, max_steps, final_step, termination_reason
                FROM runs
                ORDER BY started_at DESC
                """
            )
        return [_run_record_from_row(row) for row in rows]

    async def get_run(self, run_id: str) -> RunRecord | None:
        async with self._pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT run_id, scenario_name, scenario_hash, seed, status, started_at,
                       completed_at, max_steps, final_step, termination_reason
                FROM runs
                WHERE run_id = $1
                """,
                run_id,
            )
        return _run_record_from_row(row) if row is not None else None

    async def get_artifacts(self, run_id: str) -> RunArtifacts | None:
        async with self._pool.acquire() as connection:
            run_row = await connection.fetchrow(
                """
                SELECT run_id, scenario_name, scenario_hash, engine_version, seed, status, started_at,
                       completed_at, max_steps, final_step, termination_reason,
                       scenario, current_state
                FROM runs
                WHERE run_id = $1
                """,
                run_id,
            )
            if run_row is None:
                return None
            metric_rows = await connection.fetch(
                """
                SELECT payload
                FROM step_metrics
                WHERE run_id = $1
                ORDER BY step
                """,
                run_id,
            )
            event_rows = await connection.fetch(
                """
                SELECT step, time, event_type AS type, message, values
                FROM events
                WHERE run_id = $1
                ORDER BY step, time, event_id
                """,
                run_id,
            )
        scenario = Scenario.model_validate(_decode_json(run_row["scenario"]))
        final_state = WorldState.model_validate(_decode_json(run_row["current_state"]))
        metrics = [PopulationMetrics.model_validate(_decode_json(row["payload"])) for row in metric_rows]
        events = [
            Event.model_validate(
                {
                    "step": row["step"],
                    "time": row["time"],
                    "type": row["type"],
                    "message": row["message"],
                    "values": _decode_json(row["values"]),
                }
            )
            for row in event_rows
        ]
        termination_reason = run_row["termination_reason"] or TerminationReason.MAX_STEPS_REACHED.value
        return RunArtifacts(
            resolved_scenario=scenario,
            metadata=RunMetadata(
                run_id=run_row["run_id"],
                scenario_name=run_row["scenario_name"],
                engine_version=run_row["engine_version"],
                seed=run_row["seed"],
                dt=scenario.simulation.dt,
                max_steps=run_row["max_steps"],
            ),
            metrics=metrics,
            snapshots=[],
            events=events,
            final_state=final_state,
            termination_reason=TerminationReason(termination_reason),
        )

    async def load_run_context(self, run_id: str) -> PersistedRunContext | None:
        async with self._pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT run_id, scenario_name, scenario_hash, seed, status, started_at,
                       completed_at, max_steps, final_step, termination_reason,
                       scenario, current_state, rng_state
                FROM runs
                WHERE run_id = $1
                """,
                run_id,
            )
        if row is None:
            return None
        rng = Random()
        rng.setstate(decode_rng_state(row["rng_state"]))
        return PersistedRunContext(
            run=RunRecord(
                run_id=row["run_id"],
                scenario_name=row["scenario_name"],
                scenario_hash=row["scenario_hash"],
                seed=row["seed"],
                status=row["status"],
                started_at=row["started_at"],
                completed_at=row["completed_at"],
                max_steps=row["max_steps"],
                final_step=row["final_step"],
                termination_reason=row["termination_reason"],
            ),
            scenario=Scenario.model_validate(_decode_json(row["scenario"])),
            state=WorldState.model_validate(_decode_json(row["current_state"])),
            rng=rng,
        )

    async def append_step(self, run: RunRecord, transition: StepTransition, rng: Random) -> None:
        buffer = PostgresRunBuffer()
        buffer.add_metric(run.run_id, transition.metrics)
        buffer.extend_events(run.run_id, transition.events)
        buffer.extend_cells(run.run_id, transition.state.cells, transition.state.step)
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    """
                    UPDATE runs
                    SET status = $2,
                        completed_at = $3,
                        final_step = $4,
                        termination_reason = $5,
                        current_state = $6::jsonb,
                        rng_state = $7::jsonb,
                        updated_at = now()
                    WHERE run_id = $1
                    """,
                    run.run_id,
                    run.status.value,
                    _utc(run.completed_at) if run.completed_at else None,
                    run.final_step,
                    run.termination_reason,
                    _json(transition.state),
                    _json(encode_rng_state(rng)),
                )
                await buffer.flush(connection)

    async def get_metrics(
        self,
        run_id: str,
        from_step: int = 0,
        to_step: int | None = None,
        resolution: int = 1,
    ) -> list[dict[str, Any]]:
        params: list[Any] = [run_id, from_step, resolution]
        upper_bound = ""
        if to_step is not None:
            params.append(to_step)
            upper_bound = f"AND step <= ${len(params)}"
        async with self._pool.acquire() as connection:
            rows = await connection.fetch(
                f"""
                SELECT step, time, population_count, alive_count, dead_count, divided_count,
                       division_count_total, total_atp, total_biomass, environment_glucose,
                       environment_electron_acceptor, toxicity
                FROM step_metrics
                WHERE run_id = $1
                  AND step >= $2
                  {upper_bound}
                  AND ((step - $2) % $3) = 0
                ORDER BY step
                """,
                *params,
            )
        return [dict(row) for row in rows]

    async def get_cells(self, run_id: str) -> list[dict[str, Any]] | None:
        if not await self.run_exists(run_id):
            return None
        async with self._pool.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT payload
                FROM cells
                WHERE run_id = $1
                ORDER BY generation, cell_id
                """,
                run_id,
            )
        return [_decode_json(row["payload"]) for row in rows]

    async def get_cell(self, run_id: str, cell_id: str) -> CellState | None:
        async with self._pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT payload
                FROM cells
                WHERE run_id = $1 AND cell_id = $2
                """,
                run_id,
                cell_id,
            )
        return CellState.model_validate(_decode_json(row["payload"])) if row is not None else None

    async def lineage(self, run_id: str, root: str | None = None) -> dict[str, object] | None:
        cells_payload = await self.get_cells(run_id)
        if cells_payload is None:
            return None
        cells = [CellState.model_validate(payload) for payload in cells_payload]
        if root is not None:
            allowed = _descendant_ids(cells, root)
            cells = [cell for cell in cells if cell.id in allowed]
        nodes = [
            {
                "id": cell.id,
                "parent_id": cell.parent_id,
                "generation": cell.generation,
                "status": cell.status.value,
                "birth_step": cell.birth_step,
                "death_step": cell.death_step,
            }
            for cell in cells
        ]
        node_ids = {node["id"] for node in nodes}
        edges = [
            {"source": cell.parent_id, "target": cell.id}
            for cell in cells
            if cell.parent_id is not None and cell.parent_id in node_ids
        ]
        return {"run_id": run_id, "root": root, "nodes": nodes, "edges": edges}

    async def cell_events(self, run_id: str, cell_id: str, scope: str = "self") -> list[Event] | None:
        artifacts = await self.get_artifacts(run_id)
        if artifacts is None:
            return None
        cells = artifacts.final_state.cells
        if scope == "lineage":
            ids = _ancestor_ids(cells, cell_id) | _descendant_ids(cells, cell_id)
        elif scope == "descendants":
            ids = _descendant_ids(cells, cell_id)
        else:
            ids = {cell_id}
        events = [event for event in artifacts.events if _event_mentions_any(event, ids)]
        return sorted(events, key=lambda event: (event.step, event.time, event.type.value, event.message))

    async def get_events(
        self,
        run_id: str,
        cell_id: str | None = None,
        from_step: int = 0,
        to_step: int | None = None,
        event_type: str | None = None,
        limit: int = 5000,
    ) -> list[dict[str, Any]] | None:
        if not await self.run_exists(run_id):
            return None
        params: list[Any] = [run_id, from_step, limit]
        predicates = ["run_id = $1", "step >= $2"]
        if to_step is not None:
            params.append(to_step)
            predicates.append(f"step <= ${len(params)}")
        if cell_id is not None:
            params.append(cell_id)
            predicates.append(f"(cell_id = ${len(params)} OR values->>'parent_id' = ${len(params)} OR values->'daughter_ids' ? ${len(params)})")
        if event_type is not None:
            params.append(event_type)
            predicates.append(f"event_type = ${len(params)}")
        async with self._pool.acquire() as connection:
            rows = await connection.fetch(
                f"""
                SELECT step, time, event_type AS type, message, values
                FROM events
                WHERE {" AND ".join(predicates)}
                ORDER BY step, time, event_id
                LIMIT $3
                """,
                *params,
            )
        return [
            {
                "step": row["step"],
                "time": row["time"],
                "type": row["type"],
                "message": row["message"],
                "values": _decode_json(row["values"]),
            }
            for row in rows
        ]

    async def run_exists(self, run_id: str) -> bool:
        async with self._pool.acquire() as connection:
            return bool(await connection.fetchval("SELECT 1 FROM runs WHERE run_id = $1", run_id))


class PostgresRunBuffer:
    def __init__(self) -> None:
        self.metrics: list[tuple[Any, ...]] = []
        self.events: list[tuple[Any, ...]] = []
        self.cells: list[tuple[Any, ...]] = []

    def add_metric(self, run_id: str, metric: PopulationMetrics) -> None:
        self.metrics.append(
            (
                run_id,
                metric.step,
                metric.time,
                metric.population_count,
                metric.alive_count,
                metric.dead_count,
                metric.divided_count,
                metric.division_count_total,
                metric.total_atp,
                metric.total_biomass,
                metric.environment_glucose,
                metric.environment_electron_acceptor,
                metric.toxicity,
                _json(metric),
            )
        )

    def extend_events(self, run_id: str, events: Sequence[Event]) -> None:
        self.events.extend(
            (
                run_id,
                event.step,
                event.time,
                event.type.value,
                _event_cell_id(event),
                event.message,
                _json(event.values),
            )
            for event in events
        )

    def extend_cells(self, run_id: str, cells: Sequence[CellState], updated_step: int) -> None:
        self.cells.extend(
            (
                run_id,
                cell.id,
                cell.parent_id,
                cell.generation,
                cell.birth_step,
                cell.death_step,
                cell.status.value,
                cell.alive,
                cell.x,
                cell.y,
                cell.z,
                cell.energy.atp,
                cell.biomass,
                updated_step,
                _json(cell),
            )
            for cell in cells
        )

    async def flush(self, connection: Any) -> None:
        if self.metrics:
            await connection.executemany(
                """
                INSERT INTO step_metrics (
                    run_id, step, time, population_count, alive_count, dead_count,
                    divided_count, division_count_total, total_atp, total_biomass,
                    environment_glucose, environment_electron_acceptor, toxicity, payload
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14::jsonb)
                ON CONFLICT (run_id, step) DO UPDATE SET
                    time = EXCLUDED.time,
                    population_count = EXCLUDED.population_count,
                    alive_count = EXCLUDED.alive_count,
                    dead_count = EXCLUDED.dead_count,
                    divided_count = EXCLUDED.divided_count,
                    division_count_total = EXCLUDED.division_count_total,
                    total_atp = EXCLUDED.total_atp,
                    total_biomass = EXCLUDED.total_biomass,
                    environment_glucose = EXCLUDED.environment_glucose,
                    environment_electron_acceptor = EXCLUDED.environment_electron_acceptor,
                    toxicity = EXCLUDED.toxicity,
                    payload = EXCLUDED.payload
                """,
                self.metrics,
            )
        if self.cells:
            await connection.executemany(
                """
                INSERT INTO cells (
                    run_id, cell_id, parent_id, generation, birth_step, death_step, status, alive,
                    x, y, z, atp, biomass, updated_step, payload
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15::jsonb)
                ON CONFLICT (run_id, cell_id) DO UPDATE SET
                    parent_id = EXCLUDED.parent_id,
                    generation = EXCLUDED.generation,
                    birth_step = EXCLUDED.birth_step,
                    death_step = EXCLUDED.death_step,
                    status = EXCLUDED.status,
                    alive = EXCLUDED.alive,
                    x = EXCLUDED.x,
                    y = EXCLUDED.y,
                    z = EXCLUDED.z,
                    atp = EXCLUDED.atp,
                    biomass = EXCLUDED.biomass,
                    updated_step = EXCLUDED.updated_step,
                    payload = EXCLUDED.payload
                """,
                self.cells,
            )
        if self.events:
            await connection.executemany(
                """
                INSERT INTO events (run_id, step, time, event_type, cell_id, message, values)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
                """,
                self.events,
            )


def encode_rng_state(rng: Random) -> Any:
    return json.loads(json.dumps(rng.getstate()))


def decode_rng_state(raw: Any) -> object:
    raw = _decode_json(raw)
    return (raw[0], tuple(raw[1]), raw[2])


def _event_cell_id(event: Event) -> str | None:
    cell_id = event.values.get("cell_id")
    return cell_id if isinstance(cell_id, str) else None


def _run_record_from_row(row: Any) -> RunRecord:
    return RunRecord(
        run_id=row["run_id"],
        scenario_name=row["scenario_name"],
        scenario_hash=row["scenario_hash"],
        seed=row["seed"],
        status=row["status"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        max_steps=row["max_steps"],
        final_step=row["final_step"],
        termination_reason=row["termination_reason"],
    )


def _ancestor_ids(cells: Sequence[CellState], cell_id: str) -> set[str]:
    by_id = {cell.id: cell for cell in cells}
    ids = set()
    cursor = by_id.get(cell_id)
    while cursor is not None:
        ids.add(cursor.id)
        cursor = by_id.get(cursor.parent_id) if cursor.parent_id is not None else None
    return ids


def _descendant_ids(cells: Sequence[CellState], cell_id: str) -> set[str]:
    children_by_parent: dict[str, list[CellState]] = {}
    for cell in cells:
        if cell.parent_id is not None:
            children_by_parent.setdefault(cell.parent_id, []).append(cell)
    ids = {cell_id}
    pending = [cell_id]
    while pending:
        parent_id = pending.pop()
        for child in children_by_parent.get(parent_id, []):
            if child.id not in ids:
                ids.add(child.id)
                pending.append(child.id)
    return ids


def _event_mentions_any(event: Event, cell_ids: set[str]) -> bool:
    values = event.values
    if values.get("cell_id") in cell_ids:
        return True
    if values.get("parent_id") in cell_ids:
        return True
    daughter_ids = values.get("daughter_ids")
    return isinstance(daughter_ids, list) and any(daughter_id in cell_ids for daughter_id in daughter_ids)


def _json(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, separators=(",", ":"))


def _decode_json(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
