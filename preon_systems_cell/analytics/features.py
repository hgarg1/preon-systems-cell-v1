from __future__ import annotations

from collections import Counter

from preon_systems_cell.models import CellState, EventType, RunArtifacts


FEATURE_VERSION = "cell-platform-v1"


def extract_run_features(artifacts: RunArtifacts) -> dict[str, float | int | str | None]:
    metrics = artifacts.metrics
    division_steps = [event.step for event in artifacts.events if event.type == EventType.DIVISION]
    death_steps = [event.step for event in artifacts.events if event.type == EventType.DEATH]
    alive_counts = [metric.alive_count for metric in metrics]
    atp_values = [metric.total_atp for metric in metrics]
    return {
        "feature_version": FEATURE_VERSION,
        "scenario_name": artifacts.resolved_scenario.scenario_name,
        "max_alive": max(alive_counts, default=0),
        "final_alive": metrics[-1].alive_count if metrics else 0,
        "final_population": metrics[-1].population_count if metrics else 0,
        "time_to_first_division": min(division_steps) if division_steps else None,
        "division_count": len(division_steps),
        "death_count": len(death_steps),
        "max_generation": max((cell.generation for cell in artifacts.final_state.cells), default=0),
        "alive_auc": sum(alive_counts),
        "total_atp_min": min(atp_values, default=0),
        "total_atp_max": max(atp_values, default=0),
        "termination_reason": artifacts.termination_reason.value,
    }


def extract_cell_features(artifacts: RunArtifacts) -> list[dict[str, float | int | str | None]]:
    descendant_counts = _descendant_counts(artifacts.final_state.cells)
    events_by_cell = _event_counts_by_cell(artifacts)
    rows = []
    for cell in artifacts.final_state.cells:
        lifespan = (cell.death_step or artifacts.final_state.step) - cell.birth_step
        event_counts = events_by_cell.get(cell.id, Counter())
        rows.append(
            {
                "feature_version": FEATURE_VERSION,
                "scenario_name": artifacts.resolved_scenario.scenario_name,
                "cell_id": cell.id,
                "parent_id": cell.parent_id,
                "generation": cell.generation,
                "status": cell.status.value,
                "lifespan_steps": lifespan,
                "descendant_count": descendant_counts.get(cell.id, 0),
                "final_atp": cell.energy.atp,
                "final_biomass": cell.biomass,
                "division_events": event_counts.get(EventType.DIVISION.value, 0),
                "death_events": event_counts.get(EventType.DEATH.value, 0),
                "movement_events": event_counts.get(EventType.MOVEMENT.value, 0),
            }
        )
    return rows


def _descendant_counts(cells: list[CellState]) -> dict[str, int]:
    children_by_parent: dict[str, list[str]] = {}
    for cell in cells:
        if cell.parent_id is not None:
            children_by_parent.setdefault(cell.parent_id, []).append(cell.id)
    counts = {}
    for cell in cells:
        seen = set()
        pending = list(children_by_parent.get(cell.id, []))
        while pending:
            child_id = pending.pop()
            if child_id in seen:
                continue
            seen.add(child_id)
            pending.extend(children_by_parent.get(child_id, []))
        counts[cell.id] = len(seen)
    return counts


def _event_counts_by_cell(artifacts: RunArtifacts) -> dict[str, Counter]:
    counts: dict[str, Counter] = {}
    for event in artifacts.events:
        cell_ids = []
        if isinstance(event.values.get("cell_id"), str):
            cell_ids.append(event.values["cell_id"])
        if isinstance(event.values.get("parent_id"), str):
            cell_ids.append(event.values["parent_id"])
        daughter_ids = event.values.get("daughter_ids")
        if isinstance(daughter_ids, list):
            cell_ids.extend(str(daughter_id) for daughter_id in daughter_ids)
        for cell_id in cell_ids:
            counts.setdefault(cell_id, Counter())[event.type.value] += 1
    return counts

