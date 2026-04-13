from __future__ import annotations

from preon_systems_cell.engine import metrics_for_state, snapshot_for_state
from preon_systems_cell.models import PopulationMetrics, StepSnapshot, WorldState


def step_metrics_from_state(state: WorldState) -> PopulationMetrics:
    return metrics_for_state(state)


def snapshot_from_state(state: WorldState) -> StepSnapshot:
    return snapshot_for_state(state)

