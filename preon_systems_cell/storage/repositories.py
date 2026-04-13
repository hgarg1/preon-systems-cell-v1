from __future__ import annotations

from collections.abc import Iterable

from preon_systems_cell.domain.runs import RunRecord
from preon_systems_cell.models import CellState, Event, RunArtifacts


class InMemoryRunRepository:
    def __init__(self) -> None:
        self._runs: dict[str, RunRecord] = {}
        self._artifacts: dict[str, RunArtifacts] = {}

    def save(self, run: RunRecord, artifacts: RunArtifacts) -> None:
        self._runs[run.run_id] = run
        self._artifacts[run.run_id] = artifacts

    def list_runs(self) -> list[RunRecord]:
        return sorted(self._runs.values(), key=lambda run: run.started_at, reverse=True)

    def get_run(self, run_id: str) -> RunRecord | None:
        return self._runs.get(run_id)

    def get_artifacts(self, run_id: str) -> RunArtifacts | None:
        return self._artifacts.get(run_id)

    def get_metrics(self, run_id: str, from_step: int = 0, to_step: int | None = None, resolution: int = 1) -> list[dict]:
        artifacts = self.get_artifacts(run_id)
        if artifacts is None:
            return []
        step_stride = max(resolution, 1)
        rows = []
        for metric in artifacts.metrics:
            if metric.step < from_step:
                continue
            if to_step is not None and metric.step > to_step:
                continue
            if (metric.step - from_step) % step_stride != 0:
                continue
            rows.append(metric.model_dump(mode="json"))
        return rows

    def get_cell(self, run_id: str, cell_id: str) -> CellState | None:
        artifacts = self.get_artifacts(run_id)
        if artifacts is None:
            return None
        return next((cell for cell in artifacts.final_state.cells if cell.id == cell_id), None)

    def lineage(self, run_id: str, root: str | None = None) -> dict[str, object] | None:
        artifacts = self.get_artifacts(run_id)
        if artifacts is None:
            return None
        cells = artifacts.final_state.cells
        if root is not None:
            allowed = self._descendant_ids(cells, root)
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

    def cell_events(self, run_id: str, cell_id: str, scope: str = "self") -> list[Event] | None:
        artifacts = self.get_artifacts(run_id)
        if artifacts is None:
            return None
        cells = artifacts.final_state.cells
        if scope == "lineage":
            ids = self._ancestor_ids(cells, cell_id) | self._descendant_ids(cells, cell_id)
        elif scope == "descendants":
            ids = self._descendant_ids(cells, cell_id)
        else:
            ids = {cell_id}
        events = [event for event in artifacts.events if self._event_mentions_any(event, ids)]
        return sorted(events, key=lambda event: (event.step, event.time, event.type.value, event.message))

    def _ancestor_ids(self, cells: Iterable[CellState], cell_id: str) -> set[str]:
        by_id = {cell.id: cell for cell in cells}
        ids = set()
        cursor = by_id.get(cell_id)
        while cursor is not None:
            ids.add(cursor.id)
            cursor = by_id.get(cursor.parent_id) if cursor.parent_id is not None else None
        return ids

    def _descendant_ids(self, cells: Iterable[CellState], cell_id: str) -> set[str]:
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

    def _event_mentions_any(self, event: Event, cell_ids: set[str]) -> bool:
        values = event.values
        if values.get("cell_id") in cell_ids:
            return True
        if values.get("parent_id") in cell_ids:
            return True
        daughter_ids = values.get("daughter_ids")
        return isinstance(daughter_ids, list) and any(daughter_id in cell_ids for daughter_id in daughter_ids)


GLOBAL_RUN_REPOSITORY = InMemoryRunRepository()
