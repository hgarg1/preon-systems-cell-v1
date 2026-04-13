import asyncio

from preon_systems_cell.storage.manager import StorageManager
from preon_systems_cell.storage.postgres import PostgresRunStore, PostgresSettings
from preon_systems_cell.storage.repositories import InMemoryRunRepository


def test_storage_manager_can_force_memory_mode(monkeypatch):
    monkeypatch.setenv("PREON_STORAGE_MODE", "memory")

    manager = asyncio.run(
        StorageManager.create(
            settings=PostgresSettings(database_url="postgresql://unused"),
            memory=InMemoryRunRepository(),
        )
    )

    assert manager.postgres is None
    assert manager.status.mode == "memory"
    assert manager.status.primary == "postgres"
    assert manager.status.fallback == "memory"
    assert manager.status.degraded is True


def test_storage_manager_falls_back_without_database_url(monkeypatch):
    monkeypatch.delenv("PREON_STORAGE_MODE", raising=False)

    manager = asyncio.run(
        StorageManager.create(
            settings=PostgresSettings(database_url=None),
            memory=InMemoryRunRepository(),
        )
    )

    assert manager.postgres is None
    assert manager.status.mode == "memory"
    assert manager.status.degraded is True
    assert "PREON_DATABASE_URL" in (manager.status.reason or "")


def test_storage_manager_uses_safe_public_reason_for_connection_failures(monkeypatch):
    async def fail_create(_settings):
        raise RuntimeError("DO_NOT_EXPOSE_DB_DETAIL")

    monkeypatch.delenv("PREON_STORAGE_MODE", raising=False)
    monkeypatch.setattr(PostgresRunStore, "create", fail_create)

    manager = asyncio.run(
        StorageManager.create(
            settings=PostgresSettings(database_url="postgresql://localhost/db"),
            memory=InMemoryRunRepository(),
        )
    )

    assert manager.status.mode == "memory"
    assert manager.status.reason == "Postgres connection failed; using in-memory fallback"
    assert "DO_NOT_EXPOSE_DB_DETAIL" not in (manager.status.reason or "")
