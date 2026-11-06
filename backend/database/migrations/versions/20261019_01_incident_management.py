"""Additive incident management fields and table.

Revision ID: 20261019_01
Revises:
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261019_01"
down_revision = "20261019_00"
branch_labels = None
depends_on = None


incident_type = postgresql.ENUM(
    "ROAD_CLOSURE",
    "ACCIDENT",
    "FALLEN_TREE",
    "WATERLOGGING",
    "CONSTRUCTION",
    "BROKEN_VEHICLE",
    "OBSTRUCTION",
    "PARTIAL_OBSTRUCTION",
    "OTHER",
    name="incidenttype",
    create_type=False,
)
incident_severity = postgresql.ENUM(
    "LOW", "MEDIUM", "HIGH", "CRITICAL",
    name="incidentseverity",
    create_type=False,
)
incident_status = postgresql.ENUM(
    "REPORTED", "VERIFIED", "RESOLVED",
    name="incidentstatus",
    create_type=False,
)
incident_source = postgresql.ENUM(
    "USER_REPORT", "SYSTEM", "SIMULATION", "DEMO",
    name="incidentsource",
    create_type=False,
)


def upgrade():
    bind = op.get_bind()
    offline = op.get_context().as_sql
    inspector = None if offline else sa.inspect(bind)
    if bind.dialect.name == "postgresql":
        for enum_type in (
            incident_type,
            incident_severity,
            incident_status,
            incident_source,
        ):
            enum_type.create(bind, checkfirst=not offline)
        op.execute(
            "ALTER TYPE incidenttype ADD VALUE IF NOT EXISTS 'PARTIAL_OBSTRUCTION'"
        )

    if inspector is None or not inspector.has_table("incidents"):
        op.create_table(
            "incidents",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("type", incident_type, nullable=False),
            sa.Column("latitude", sa.Float(), nullable=False),
            sa.Column("longitude", sa.Float(), nullable=False),
            sa.Column("road_id", sa.String(length=100), nullable=True),
            sa.Column("road_reference", sa.String(length=255), nullable=True),
            sa.Column("severity", incident_severity, nullable=False),
            sa.Column("status", incident_status, nullable=False),
            sa.Column("source", incident_source, nullable=False),
            sa.Column("verified", sa.Boolean(), nullable=False),
            sa.Column("confidence", sa.Float(), nullable=True),
            sa.Column("verified_at", sa.DateTime(), nullable=True),
            sa.Column("verified_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("ended_at", sa.DateTime(), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        )
    else:
        columns = {column["name"] for column in inspector.get_columns("incidents")}
        additions = (
            ("road_reference", sa.String(length=255)),
            ("verified_at", sa.DateTime()),
            ("verified_by", postgresql.UUID(as_uuid=True)),
        )
        for name, column_type in additions:
            if name not in columns:
                op.add_column("incidents", sa.Column(name, column_type, nullable=True))
        if "updated_at" not in columns:
            op.add_column(
                "incidents",
                sa.Column(
                    "updated_at",
                    sa.DateTime(),
                    nullable=True,
                    server_default=sa.func.now(),
                ),
            )
            op.execute(
                sa.text("UPDATE incidents SET updated_at = created_at WHERE updated_at IS NULL")
            )
            op.alter_column(
                "incidents",
                "updated_at",
                existing_type=sa.DateTime(),
                nullable=False,
                server_default=None,
            )

    existing_indexes = (
        set()
        if offline
        else {index["name"] for index in sa.inspect(bind).get_indexes("incidents")}
    )
    for name, columns in (
        ("ix_incidents_road_id", ["road_id"]),
        ("ix_incidents_type", ["type"]),
        ("ix_incidents_status", ["status"]),
        ("ix_incident_lat_lon", ["latitude", "longitude"]),
        ("ix_incident_status_type", ["status", "type"]),
    ):
        if name not in existing_indexes:
            op.create_index(name, "incidents", columns, unique=False)


def downgrade():
    raise NotImplementedError(
        "Incident migration is intentionally non-destructive; preserve reported incident data."
    )
