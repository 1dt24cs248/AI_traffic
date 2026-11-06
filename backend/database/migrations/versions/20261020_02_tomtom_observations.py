"""Add TomTom segment registry and append-only observations.

Revision ID: 20261020_02
Revises: 20261019_01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261020_02"
down_revision = "20261019_01"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    offline = op.get_context().as_sql
    inspector = None if offline else sa.inspect(bind)

    if inspector is None or not inspector.has_table("tomtom_road_segments"):
        op.create_table(
            "tomtom_road_segments",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("provider", sa.String(length=50), nullable=False),
            sa.Column("provider_segment_reference", sa.String(length=255), nullable=True),
            sa.Column("identity_status", sa.String(length=20), nullable=False),
            sa.Column("identity_version", sa.String(length=50), nullable=False),
            sa.Column("mapping_version", sa.String(length=50), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.UniqueConstraint(
                "provider",
                "provider_segment_reference",
                name="uq_tomtom_segment_provider_reference",
            ),
            sa.CheckConstraint(
                "identity_status IN ('provisional', 'unverified', 'verified')",
                name="ck_tomtom_segment_identity_status",
            ),
            sa.CheckConstraint(
                "identity_status != 'verified' OR provider_segment_reference IS NOT NULL",
                name="ck_tomtom_verified_segment_has_reference",
            ),
            sa.CheckConstraint(
                "identity_status != 'verified' OR mapping_version != 'unmapped-v1'",
                name="ck_tomtom_verified_segment_has_mapping",
            ),
        )

    if inspector is None or not inspector.has_table("tomtom_traffic_observations"):
        op.create_table(
            "tomtom_traffic_observations",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "segment_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("tomtom_road_segments.id", ondelete="RESTRICT"),
                nullable=False,
            ),
            sa.Column("provider", sa.String(length=50), nullable=False),
            sa.Column("source", sa.String(length=100), nullable=False),
            sa.Column("source_endpoint", sa.String(length=255), nullable=False),
            sa.Column("provenance_version", sa.String(length=50), nullable=False),
            sa.Column("requested_latitude", sa.Float(), nullable=False),
            sa.Column("requested_longitude", sa.Float(), nullable=False),
            sa.Column("coordinate_system", sa.String(length=20), nullable=False),
            sa.Column("provider_observed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("current_speed", sa.Float(), nullable=True),
            sa.Column("free_flow_speed", sa.Float(), nullable=True),
            sa.Column("travel_time_seconds", sa.Integer(), nullable=True),
            sa.Column("confidence", sa.Float(), nullable=True),
            sa.Column("road_closure", sa.Boolean(), nullable=True),
            sa.Column("speed_unit", sa.String(length=20), nullable=False),
            sa.Column("travel_time_unit", sa.String(length=20), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.UniqueConstraint(
                "segment_id",
                "provider_observed_at",
                name="uq_tomtom_observation_segment_observed_at",
            ),
            sa.CheckConstraint(
                "requested_latitude >= -90 AND requested_latitude <= 90",
                name="ck_tomtom_observation_latitude",
            ),
            sa.CheckConstraint(
                "requested_longitude >= -180 AND requested_longitude <= 180",
                name="ck_tomtom_observation_longitude",
            ),
            sa.CheckConstraint(
                "current_speed IS NULL OR current_speed >= 0",
                name="ck_tomtom_observation_current_speed",
            ),
            sa.CheckConstraint(
                "free_flow_speed IS NULL OR free_flow_speed >= 0",
                name="ck_tomtom_observation_free_flow_speed",
            ),
            sa.CheckConstraint(
                "travel_time_seconds IS NULL OR travel_time_seconds >= 0",
                name="ck_tomtom_observation_travel_time",
            ),
            sa.CheckConstraint(
                "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
                name="ck_tomtom_observation_confidence",
            ),
        )

    inspector = None if offline else sa.inspect(bind)
    existing_observation_indexes = (
        set()
        if inspector is None
        else {index["name"] for index in inspector.get_indexes("tomtom_traffic_observations")}
    )
    for name, columns in (("ix_tomtom_observation_retrieved_at", ["retrieved_at"]),):
        if name not in existing_observation_indexes:
            op.create_index(name, "tomtom_traffic_observations", columns, unique=False)


def downgrade():
    raise NotImplementedError(
        "This migration is non-destructive; preserve TomTom observation history."
    )
