from __future__ import annotations

from preon_systems_cell.domain.runs import RunRecord
from preon_systems_cell.models import EventType, StepSnapshot, StepTransition, WorldState
from preon_systems_cell.telemetry.sinks import TelemetrySink


class TelemetryCollector:
    def __init__(self, sinks: list[TelemetrySink], record_every: int) -> None:
        self.sinks = sinks
        self.record_every = max(record_every, 1)

    def start_run(self, run: RunRecord) -> None:
        for sink in self.sinks:
            sink.on_run_start(run)

    def record_step(self, result: StepTransition) -> None:
        snapshot = result.snapshot if self._should_store_snapshot(result) else None
        for sink in self.sinks:
            sink.on_step(result, snapshot)

    def complete_run(self, run: RunRecord, final_state: WorldState) -> None:
        for sink in self.sinks:
            sink.on_run_complete(run, final_state)

    def _should_store_snapshot(self, result: StepTransition) -> bool:
        if result.terminated:
            return True
        if result.state.step % self.record_every == 0:
            return True
        return any(event.type in {EventType.DEATH, EventType.DIVISION} for event in result.events)

    def ensure_final_snapshot(self, result: StepTransition, snapshots: list[StepSnapshot]) -> None:
        if not snapshots or snapshots[-1].step != result.state.step:
            snapshots.append(result.snapshot)

