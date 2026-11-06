"""Create the Phase 1 journey and simulation tables when absent.

Revision ID: 20261019_00
Revises:
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261019_00"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    offline = op.get_context().as_sql
    inspector = None if offline else sa.inspect(bind)
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    uuid_type = postgresql.UUID(as_uuid=True)

    if inspector is None or not inspector.has_table("simulation_runs"):
        op.create_table(
            "simulation_runs",
            sa.Column("id", uuid_type, primary_key=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("scenario_type", sa.String(length=100), nullable=False),
            sa.Column("parameters", json_type, nullable=False),
            sa.Column("road_ids_affected", json_type, nullable=True),
            sa.Column("baseline_snapshot", json_type, nullable=True),
            sa.Column("scenario_snapshot", json_type, nullable=False),
            sa.Column("comparison", json_type, nullable=True),
            sa.Column("duration_minutes", sa.Integer(), nullable=False),
            sa.Column("interval_minutes", sa.Integer(), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("created_by", uuid_type, nullable=True),
        )

    inspector = None if offline else sa.inspect(bind)
    if inspector is None or not inspector.has_table("journeys"):
        op.create_table(
            "journeys",
            sa.Column("id", uuid_type, primary_key=True),
            sa.Column("origin_lat", sa.Float(), nullable=False),
            sa.Column("origin_lon", sa.Float(), nullable=False),
            sa.Column("origin_label", sa.String(length=500), nullable=True),
            sa.Column("destination_lat", sa.Float(), nullable=False),
            sa.Column("destination_lon", sa.Float(), nullable=False),
            sa.Column("destination_label", sa.String(length=500), nullable=True),
            sa.Column("vehicle_type", sa.String(length=50), nullable=False),
            sa.Column("route_preference", sa.String(length=50), nullable=True),
            sa.Column("selected_route_index", sa.Integer(), nullable=False),
            sa.Column("route_distance_km", sa.Float(), nullable=True),
            sa.Column("route_duration_minutes", sa.Float(), nullable=True),
            sa.Column("recommended_index", sa.Integer(), nullable=True),
            sa.Column("shortest_index", sa.Integer(), nullable=True),
            sa.Column("fastest_index", sa.Integer(), nullable=True),
            sa.Column("ranking_basis", sa.Text(), nullable=True),
            sa.Column("incidents_snapshot", json_type, nullable=True),
            sa.Column("weather_snapshot", json_type, nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("user_id", uuid_type, nullable=True),
        )
        op.create_index("ix_journeys_created_at", "journeys", ["created_at"])


def downgrade():
    raise NotImplementedError(
        "This migration is non-destructive; preserve journey and simulation data."
    )
