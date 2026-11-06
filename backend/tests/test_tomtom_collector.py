import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.traffic import collector


def test_collect_once_fetches_and_persists_observation(monkeypatch):
    flow = MagicMock()

    get_current_flow = MagicMock(return_value=flow)
    persist_observation = MagicMock(return_value=True)

    monkeypatch.setattr(collector, "get_current_flow", get_current_flow)
    monkeypatch.setattr(
        collector,
        "persist_tomtom_observation_best_effort",
        persist_observation,
    )
    monkeypatch.setattr(
        collector,
        "COLLECTION_LOCATIONS",
        [(13.0108, 77.5550)],
    )

    asyncio.run(collector.collect_once())

    get_current_flow.assert_called_once_with(13.0108, 77.5550)
    persist_observation.assert_called_once_with(flow)


def test_collect_once_handles_tomtom_error(monkeypatch):
    get_current_flow = MagicMock(
        side_effect=collector.TomTomError("Simulated provider failure")
    )
    persist_observation = MagicMock(return_value=True)

    monkeypatch.setattr(collector, "get_current_flow", get_current_flow)
    monkeypatch.setattr(
        collector,
        "persist_tomtom_observation_best_effort",
        persist_observation,
    )
    monkeypatch.setattr(
        collector,
        "COLLECTION_LOCATIONS",
        [(13.0108, 77.5550)],
    )

    asyncio.run(collector.collect_once())

    persist_observation.assert_not_called()


def test_collect_once_continues_after_unexpected_error(monkeypatch):
    locations = [
        (13.0108, 77.5550),
        (13.0200, 77.5600),
    ]

    def get_flow(latitude, longitude):
        if latitude == locations[0][0]:
            raise RuntimeError("Simulated unexpected failure")
        return MagicMock()

    get_current_flow = MagicMock(side_effect=get_flow)
    persist_observation = MagicMock(return_value=True)

    monkeypatch.setattr(collector, "get_current_flow", get_current_flow)
    monkeypatch.setattr(
        collector,
        "persist_tomtom_observation_best_effort",
        persist_observation,
    )
    monkeypatch.setattr(collector, "COLLECTION_LOCATIONS", locations)

    asyncio.run(collector.collect_once())

    assert get_current_flow.call_count == 2
    persist_observation.assert_called_once()


def test_collector_loop_stops_when_stop_event_is_set(monkeypatch):
    stop_event = asyncio.Event()
    collect_once = AsyncMock()

    async def collect_and_stop():
        await collect_once()
        stop_event.set()

    monkeypatch.setattr(collector, "collect_once", collect_and_stop)

    asyncio.run(
        asyncio.wait_for(
            collector.collector_loop(stop_event),
            timeout=2,
        )
    )

    collect_once.assert_awaited_once()


def test_collector_lock_is_not_acquired_for_non_postgres_database(monkeypatch):
    monkeypatch.setattr(collector.engine, "dialect", MagicMock(name="sqlite"))
    collector.engine.dialect.name = "sqlite"

    assert collector.try_acquire_collector_lock() is None


def test_collector_lock_contention_closes_connection(monkeypatch):
    connection = MagicMock()
    connection.execute.return_value.scalar_one.return_value = False
    monkeypatch.setattr(collector.engine, "dialect", MagicMock(name="postgresql"))
    collector.engine.dialect.name = "postgresql"
    monkeypatch.setattr(collector.engine, "connect", lambda: connection)

    assert collector.try_acquire_collector_lock() is None
    connection.close.assert_called_once()


def test_collector_lock_success_returns_committed_connection(monkeypatch):
    connection = MagicMock()
    connection.execute.return_value.scalar_one.return_value = True
    monkeypatch.setattr(collector.engine, "dialect", MagicMock(name="postgresql"))
    collector.engine.dialect.name = "postgresql"
    monkeypatch.setattr(collector.engine, "connect", lambda: connection)

    assert collector.try_acquire_collector_lock() is connection
    connection.commit.assert_called_once()
    connection.close.assert_not_called()


def test_collector_lock_database_error_disables_collection(monkeypatch):
    connection = MagicMock()
    connection.execute.side_effect = RuntimeError("simulated database failure")
    monkeypatch.setattr(collector.engine, "dialect", MagicMock(name="postgresql"))
    collector.engine.dialect.name = "postgresql"
    monkeypatch.setattr(collector.engine, "connect", lambda: connection)

    assert collector.try_acquire_collector_lock() is None
    connection.close.assert_called_once()


def test_collector_lock_release_unlocks_and_closes_connection():
    connection = MagicMock()

    collector.release_collector_lock(connection)

    connection.execute.assert_called_once()
    connection.commit.assert_called_once()
    connection.close.assert_called_once()
