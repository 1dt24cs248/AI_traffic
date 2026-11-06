"""Insert-only persistence for validated TomTom flow responses."""

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import math
from typing import Callable
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.tomtom_traffic import TomTomRoadSegment, TomTomTrafficObservation
from app.schemas.tomtom import CurrentTrafficFlow

PROVIDER = "tomtom"
SOURCE = "TomTom Traffic Flow API"
SOURCE_ENDPOINT = "/traffic/services/4/flowSegmentData/absolute/10/json"
PROVENANCE_VERSION = "tomtom-flow-v4"
SPEED_UNIT = "km/h"
TRAVEL_TIME_UNIT = "seconds"
COORDINATE_SYSTEM = "EPSG:4326"
IDENTITY_VERSION = "unverified-v1"
MAPPING_VERSION = "unmapped-v1"
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ObservationPersistResult:
    observation_id: UUID
    segment_id: UUID
    segment_identity_status: str
    inserted: bool


def _finite_number(value: object, field: str, *, maximum: float | None = None) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a finite number.")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{field} must be a finite, non-negative number.")
    if maximum is not None and number > maximum:
        raise ValueError(f"{field} must not exceed {maximum}.")
    return number


def _utc_datetime(value: object, field: str, *, optional: bool = False) -> datetime | None:
    if value is None and optional:
        return None
    if not isinstance(value, datetime):
        raise ValueError(f"{field} must be a timezone-aware datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware.")
    return value.astimezone(timezone.utc)


def _validated_values(
    flow: CurrentTrafficFlow,
    provider_segment_reference: str | None,
    speed_unit: str,
    travel_time_unit: str,
    coordinate_system: str,
) -> dict:
    if flow.source != SOURCE:
        raise ValueError("Only responses identified as the TomTom Traffic Flow API can be stored.")

    latitude = _finite_number(flow.latitude, "latitude", maximum=90)
    longitude = _finite_number(flow.longitude, "longitude", maximum=180)
    if latitude is None or longitude is None:
        raise ValueError("Latitude and longitude are required.")
    if latitude < -90 or longitude < -180:
        raise ValueError("Coordinates are outside the valid WGS84 range.")

    current_speed = _finite_number(flow.current_speed, "current_speed")
    free_flow_speed = _finite_number(flow.free_flow_speed, "free_flow_speed")
    confidence = _finite_number(flow.confidence, "confidence", maximum=1)
    if confidence is not None and confidence > 1:
        raise ValueError("confidence must be between 0 and 1.")

    travel_time = flow.current_travel_time_seconds
    if travel_time is not None:
        if isinstance(travel_time, bool) or not isinstance(travel_time, int) or travel_time < 0:
            raise ValueError("current_travel_time_seconds must be a non-negative integer.")
    if flow.road_closure is not None and not isinstance(flow.road_closure, bool):
        raise ValueError("road_closure must be a boolean or null.")
    if all(
        value is None
        for value in (current_speed, free_flow_speed, travel_time, confidence, flow.road_closure)
    ):
        raise ValueError("The TomTom response contains no usable traffic measurements.")

    if provider_segment_reference is not None:
        if not isinstance(provider_segment_reference, str) or not provider_segment_reference.strip():
            raise ValueError("provider_segment_reference must be a non-empty string or null.")
        provider_segment_reference = provider_segment_reference.strip()
        if len(provider_segment_reference) > 255:
            raise ValueError("provider_segment_reference exceeds 255 characters.")

    if speed_unit != SPEED_UNIT:
        raise ValueError(f"TomTom speed must be stored in {SPEED_UNIT}.")
    if travel_time_unit != TRAVEL_TIME_UNIT:
        raise ValueError(f"Travel time must be stored in {TRAVEL_TIME_UNIT}.")
    if coordinate_system != COORDINATE_SYSTEM:
        raise ValueError(f"Coordinates must use {COORDINATE_SYSTEM}.")

    observed_at = _utc_datetime(flow.observation_time, "observation_time", optional=True)
    retrieved_at = _utc_datetime(flow.retrieved_at, "retrieved_at")

    return {
        "provider_segment_reference": provider_segment_reference,
        "requested_latitude": latitude,
        "requested_longitude": longitude,
        "provider_observed_at": observed_at,
        "retrieved_at": retrieved_at,
        "current_speed": current_speed,
        "free_flow_speed": free_flow_speed,
        "travel_time_seconds": travel_time,
        "confidence": confidence,
        "road_closure": flow.road_closure,
    }


def persist_tomtom_observation(
    flow: CurrentTrafficFlow,
    *,
    provider_segment_reference: str | None = None,
    speed_unit: str = SPEED_UNIT,
    travel_time_unit: str = TRAVEL_TIME_UNIT,
    coordinate_system: str = COORDINATE_SYSTEM,
    session_factory: Callable[[], Session] | None = None,
) -> ObservationPersistResult:
    """Persist one response in its own transaction; never updates an observation."""
    values = _validated_values(
        flow,
        provider_segment_reference,
        speed_unit,
        travel_time_unit,
        coordinate_system,
    )
    factory = session_factory or SessionLocal
    for attempt in range(2):
        session = factory()
        try:
            segment = None
            if values["provider_segment_reference"] is not None:
                segment = (
                    session.query(TomTomRoadSegment)
                    .filter_by(
                        provider=PROVIDER,
                        provider_segment_reference=values["provider_segment_reference"],
                    )
                    .first()
                )

            if segment is None:
                segment = TomTomRoadSegment(
                    provider=PROVIDER,
                    provider_segment_reference=values["provider_segment_reference"],
                    identity_status=(
                        "unverified"
                        if values["provider_segment_reference"] is not None
                        else "provisional"
                    ),
                    identity_version=IDENTITY_VERSION,
                    mapping_version=MAPPING_VERSION,
                )
                session.add(segment)
                session.flush()

            observed_at = values["provider_observed_at"]
            if values["provider_segment_reference"] is not None and observed_at is not None:
                existing = (
                    session.query(TomTomTrafficObservation)
                    .filter_by(segment_id=segment.id, provider_observed_at=observed_at)
                    .first()
                )
                if existing is not None:
                    return ObservationPersistResult(
                        observation_id=existing.id,
                        segment_id=segment.id,
                        segment_identity_status=segment.identity_status,
                        inserted=False,
                    )

            observation = TomTomTrafficObservation(
                segment_id=segment.id,
                provider=PROVIDER,
                source=SOURCE,
                source_endpoint=SOURCE_ENDPOINT,
                provenance_version=PROVENANCE_VERSION,
                requested_latitude=values["requested_latitude"],
                requested_longitude=values["requested_longitude"],
                coordinate_system=COORDINATE_SYSTEM,
                provider_observed_at=observed_at,
                retrieved_at=values["retrieved_at"],
                current_speed=values["current_speed"],
                free_flow_speed=values["free_flow_speed"],
                travel_time_seconds=values["travel_time_seconds"],
                confidence=values["confidence"],
                road_closure=values["road_closure"],
                speed_unit=SPEED_UNIT,
                travel_time_unit=TRAVEL_TIME_UNIT,
            )
            session.add(observation)
            session.flush()
            session.commit()
            return ObservationPersistResult(
                observation_id=observation.id,
                segment_id=segment.id,
                segment_identity_status=segment.identity_status,
                inserted=True,
            )
        except IntegrityError:
            session.rollback()
            if (
                values["provider_segment_reference"] is not None
                and values["provider_observed_at"] is not None
            ):
                duplicate = _find_existing_observation(
                    factory,
                    values["provider_segment_reference"],
                    values["provider_observed_at"],
                )
                if duplicate is not None:
                    return duplicate
            if attempt == 1:
                raise
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    raise RuntimeError("TomTom observation insert retry exhausted.")


def _find_existing_observation(
    session_factory: Callable[[], Session],
    provider_segment_reference: str,
    observed_at: datetime,
) -> ObservationPersistResult | None:
    session = session_factory()
    try:
        segment = (
            session.query(TomTomRoadSegment)
            .filter_by(
                provider=PROVIDER,
                provider_segment_reference=provider_segment_reference,
            )
            .first()
        )
        if segment is None:
            return None
        observation = (
            session.query(TomTomTrafficObservation)
            .filter_by(segment_id=segment.id, provider_observed_at=observed_at)
            .first()
        )
        if observation is None:
            return None
        return ObservationPersistResult(
            observation_id=observation.id,
            segment_id=segment.id,
            segment_identity_status=segment.identity_status,
            inserted=False,
        )
    finally:
        session.close()


def persist_tomtom_observation_best_effort(flow: CurrentTrafficFlow) -> bool:
    """Attempt persistence without allowing storage failure to affect live flow."""
    try:
        persist_tomtom_observation(flow)
    except Exception:
        logger.warning(
            "TomTom observation persistence failed; live traffic response is unaffected."
        )
        return False
    return True
