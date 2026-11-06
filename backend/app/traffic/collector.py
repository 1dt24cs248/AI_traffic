"""Optional scheduled collector for current TomTom traffic observations."""

import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.core.config import settings
from app.core.database import engine
from app.traffic.observation_store import (
    persist_tomtom_observation_best_effort,
)
from app.traffic.tomtom import (
    TomTomError,
    get_current_flow,
)

logger = logging.getLogger(__name__)
COLLECTOR_LOCK_KEY = 0x544F4D544F4D

# Initial Bengaluru test location.
# Add more locations only after the single-location workflow is verified.
COLLECTION_LOCATIONS = [
    (13.0108, 77.5550),
]


def try_acquire_collector_lock() -> Connection | None:
    """Acquire the process-wide PostgreSQL lock before starting a collector."""
    if engine.dialect.name != "postgresql":
        logger.warning("TomTom collector requires PostgreSQL advisory locks; collection is disabled.")
        return None

    connection = None
    try:
        connection = engine.connect()
        acquired = connection.execute(
            text("SELECT pg_try_advisory_lock(:lock_key)"),
            {"lock_key": COLLECTOR_LOCK_KEY},
        ).scalar_one()
        connection.commit()
        if acquired:
            return connection
        connection.close()
        logger.info("TomTom collector is already active in another API worker.")
    except Exception:
        if connection is not None:
            connection.close()
        logger.warning("TomTom collector lock could not be acquired; collection is disabled.")
    return None


def release_collector_lock(connection: Connection) -> None:
    """Release the advisory lock and its dedicated database connection."""
    try:
        connection.execute(
            text("SELECT pg_advisory_unlock(:lock_key)"),
            {"lock_key": COLLECTOR_LOCK_KEY},
        )
        connection.commit()
    except Exception:
        logger.warning("TomTom collector lock release failed; closing its connection.")
    finally:
        connection.close()


async def collect_once() -> None:
    """Collect traffic once for each configured location."""
    for latitude, longitude in COLLECTION_LOCATIONS:
        try:
            flow = await asyncio.to_thread(
                get_current_flow,
                latitude,
                longitude,
            )

            persisted = await asyncio.to_thread(
                persist_tomtom_observation_best_effort,
                flow,
            )

            if persisted:
                logger.info(
                    "TomTom observation processed for "
                    "latitude=%s longitude=%s",
                    latitude,
                    longitude,
                )
            else:
                logger.warning(
                    "TomTom observation persistence failed for "
                    "latitude=%s longitude=%s",
                    latitude,
                    longitude,
                )

        except TomTomError as exc:
            logger.warning(
                "TomTom collection failed for "
                "latitude=%s longitude=%s: %s",
                latitude,
                longitude,
                exc,
            )
        except Exception:
            logger.exception(
                "Unexpected collection error for "
                "latitude=%s longitude=%s",
                latitude,
                longitude,
            )


async def collector_loop(stop_event: asyncio.Event) -> None:
    """Collect periodically until the application requests shutdown."""
    interval = settings.TOMTOM_COLLECTOR_INTERVAL_SECONDS

    while not stop_event.is_set():
        await collect_once()

        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=interval,
            )
        except asyncio.TimeoutError:
            pass
