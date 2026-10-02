"""
Module 2 pipeline:
Raw Data -> Validation -> Schema checking -> Duplicate detection -> Storage

This module is deliberately separate from the API route so it can be reused by:
- the CSV upload endpoint (this phase)
- the simulation-mode replayer (Phase 13)
- a future live-API connector (optional)
"""

import csv
import io
from datetime import datetime

from pydantic import ValidationError
from sqlalchemy import and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.traffic_record import TrafficRecord
from app.schemas.traffic import TrafficRecordIn, IngestionSummary


MAX_REPORTED_ERRORS = 20


# External CSV files may use different names from our internal schema.
# Example:
#     CSV column: weather
#     Internal field: weather_condition
#
# This mapping is applied before Pydantic validation so that external
# column names are converted to the canonical application field names.
EXTERNAL_FIELD_ALIASES = {
    "weather": "weather_condition",
}


def _map_external_field_names(row: dict) -> dict:
    """
    Rename known external CSV aliases to canonical schema field names.

    If both the alias and canonical field are present, the canonical
    field is preserved when it already contains a real value.
    """
    for alias, canonical in EXTERNAL_FIELD_ALIASES.items():
        if alias in row and not row.get(canonical):
            row[canonical] = row.pop(alias)

    return row


def _derive_temporal_fields(ts: datetime) -> tuple[int, int]:
    """
    day_of_week: 0=Monday..6=Sunday
    hour: 0-23

    Derived if the source data omits them.
    """
    return ts.weekday(), ts.hour


def ingest_rows(
    db: Session,
    rows: list[dict],
    source: str,
) -> IngestionSummary:
    """
    Core ingestion pipeline.

    `rows` is a list of raw dicts (already parsed from CSV/JSON).

    Runs validation + duplicate detection + storage row by row so one
    bad row doesn't fail the whole batch.
    """

    inserted = 0
    duplicates = 0
    invalid = 0
    errors: list[str] = []

    for idx, raw_row in enumerate(rows):

        # --- Validation & schema checking ---
        try:
            clean = TrafficRecordIn(**raw_row)

        except ValidationError as e:
            invalid += 1

            if len(errors) < MAX_REPORTED_ERRORS:
                errors.append(
                    f"Row {idx}: {e.errors()[0]['msg']}"
                )

            continue

        day_of_week, hour = _derive_temporal_fields(
            clean.timestamp
        )

        record = TrafficRecord(
            road_id=clean.road_id,
            road_name=clean.road_name,
            latitude=clean.latitude,
            longitude=clean.longitude,
            timestamp=clean.timestamp,
            vehicle_count=clean.vehicle_count,
            average_speed=clean.average_speed,
            road_capacity=clean.road_capacity,
            occupancy=clean.occupancy,
            weather_condition=clean.weather_condition,
            temperature=clean.temperature,
            rainfall=clean.rainfall,
            day_of_week=day_of_week,
            hour=hour,
            event_indicator=clean.event_indicator,
            source=source,
        )

        # --- Duplicate detection ---
        # Same road_id + timestamp already stored.
        exists = db.query(TrafficRecord).filter(
            and_(
                TrafficRecord.road_id == clean.road_id,
                TrafficRecord.timestamp == clean.timestamp,
            )
        ).first()

        if exists:
            duplicates += 1
            continue

        # --- Storage ---
        db.add(record)

        try:
            # Catch race-condition duplicates via the unique constraint.
            db.flush()
            inserted += 1

        except IntegrityError:
            db.rollback()
            duplicates += 1

    db.commit()

    return IngestionSummary(
        total_rows_received=len(rows),
        rows_inserted=inserted,
        rows_duplicate=duplicates,
        rows_invalid=invalid,
        invalid_row_errors=errors,
    )


def parse_csv_bytes(file_bytes: bytes) -> list[dict]:
    """
    Parse uploaded CSV bytes into a list of raw dictionaries.

    Does NOT validate values yet.
    """

    # Handles Excel-exported CSV files containing a UTF-8 BOM.
    text = file_bytes.decode("utf-8-sig")

    reader = csv.DictReader(io.StringIO(text))

    rows = []

    for row in reader:

        # Strip whitespace from string values.
        cleaned = {
            k: (v.strip() if isinstance(v, str) else v)
            for k, v in row.items()
        }

        # Convert empty strings to None so Pydantic Optional fields work.
        cleaned = {
            k: (None if v == "" else v)
            for k, v in cleaned.items()
        }

        # Convert external column names to our internal schema names.
        #
        # Example:
        # weather -> weather_condition
        cleaned = _map_external_field_names(cleaned)

        rows.append(cleaned)

    return rows