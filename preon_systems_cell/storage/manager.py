from __future__ import annotations

from dataclasses import dataclass
import logging
import os

from preon_systems_cell.storage.postgres import PostgresRunStore, PostgresSettings, PostgresUnavailableError
from preon_systems_cell.storage.repositories import InMemoryRunRepository


logger = logging.getLogger("preon_systems_cell.storage")


@dataclass(frozen=True)
class StorageStatus:
    mode: str
    primary: str
    fallback: str
    degraded: bool
    reason: str | None = None

    def model_dump(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "primary": self.primary,
            "fallback": self.fallback,
            "degraded": self.degraded,
            "reason": self.reason,
        }


class StorageManager:
    def __init__(
        self,
        *,
        memory: InMemoryRunRepository,
        postgres: PostgresRunStore | None,
        status: StorageStatus,
    ) -> None:
        self.memory = memory
        self.postgres = postgres
        self.status = status

    @classmethod
    async def create(
        cls,
        *,
        settings: PostgresSettings,
        memory: InMemoryRunRepository,
    ) -> "StorageManager":
        forced_mode = os.getenv("PREON_STORAGE_MODE", "postgres").strip().lower()
        if forced_mode == "memory":
            status = StorageStatus(
                mode="memory",
                primary="postgres",
                fallback="memory",
                degraded=True,
                reason="PREON_STORAGE_MODE=memory",
            )
            logger.warning("storage_mode_selected", extra=status.model_dump())
            return cls(memory=memory, postgres=None, status=status)

        if forced_mode not in {"", "postgres"}:
            logger.warning("unknown_storage_mode", extra={"requested_mode": forced_mode})

        try:
            postgres = await PostgresRunStore.create(settings)
        except Exception as exc:
            reason = _public_fallback_reason(exc)
            status = StorageStatus(
                mode="memory",
                primary="postgres",
                fallback="memory",
                degraded=True,
                reason=reason,
            )
            logger.warning(
                "storage_fallback_activated",
                exc_info=not isinstance(exc, PostgresUnavailableError),
                extra=status.model_dump(),
            )
            return cls(memory=memory, postgres=None, status=status)

        status = StorageStatus(
            mode="postgres",
            primary="postgres",
            fallback="memory",
            degraded=False,
            reason=None,
        )
        logger.info("storage_mode_selected", extra=status.model_dump())
        return cls(memory=memory, postgres=postgres, status=status)

    async def close(self) -> None:
        if self.postgres is not None:
            await self.postgres.close()


def _public_fallback_reason(exc: Exception) -> str:
    if isinstance(exc, PostgresUnavailableError):
        return str(exc)
    return "Postgres connection failed; using in-memory fallback"
