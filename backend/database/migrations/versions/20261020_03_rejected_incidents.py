"""Add the rejected state to incident moderation (additive only)."""

from alembic import op

revision = "20261020_03"
down_revision = "20261020_02"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TYPE incidentstatus ADD VALUE IF NOT EXISTS 'REJECTED'")


def downgrade():
    raise NotImplementedError("Incident status migrations preserve existing records.")
