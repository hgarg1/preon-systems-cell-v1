from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from preon_systems_cell.models import BaseConfigModel


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunRecord(BaseConfigModel):
    run_id: str = Field(min_length=1)
    scenario_name: str = Field(min_length=1)
    scenario_hash: str = Field(min_length=1)
    seed: int
    status: RunStatus = RunStatus.QUEUED
    started_at: datetime
    completed_at: datetime | None = None
    max_steps: int = Field(gt=0)
    final_step: int | None = Field(default=None, ge=0)
    termination_reason: str | None = None

