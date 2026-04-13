from __future__ import annotations

from typing import Protocol

from preon_systems_cell.domain.runs import RunRecord
from preon_systems_cell.models import Event, PopulationMetrics, StepSnapshot, StepTransition, WorldState


class TelemetrySink(Protocol):
    def on_run_start(self, run: RunRecord) -> None: ...

    def on_step(self, result: StepTransition, snapshot: StepSnapshot | None) -> None: ...

    def on_run_complete(self, run: RunRecord, final_state: WorldState) -> None: ...


class InMemoryTelemetrySink:
    def __init__(self) -> None:
        self.run: RunRecord | None = None
        self.metrics: list[PopulationMetrics] = []
        self.snapshots: list[StepSnapshot] = []
        self.events: list[Event] = []
        self.final_state: WorldState | None = None

    def on_run_start(self, run: RunRecord) -> None:
        self.run = run

    def on_step(self, result: StepTransition, snapshot: StepSnapshot | None) -> None:
        self.metrics.append(result.metrics)
        if snapshot is not None:
            self.snapshots.append(snapshot)
        self.events.extend(result.events)

    def on_run_complete(self, run: RunRecord, final_state: WorldState) -> None:
        self.run = run
        self.final_state = final_state

