"""Initial schema: memories, channel sets and set members.

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-01
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "memories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fingerprint", sa.String(64), nullable=False, unique=True),
        sa.Column("freq_hz", sa.BigInteger(), nullable=False),
        sa.Column("duplex", sa.String(8), nullable=False),
        sa.Column("offset_hz", sa.BigInteger(), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("tmode", sa.String(16), nullable=False),
        sa.Column("rtone_dhz", sa.Integer(), nullable=False),
        sa.Column("ctone_dhz", sa.Integer(), nullable=False),
        sa.Column("dtcs", sa.Integer(), nullable=False),
        sa.Column("rx_dtcs", sa.Integer(), nullable=False),
        sa.Column("dtcs_polarity", sa.String(2), nullable=False),
        sa.Column("cross_mode", sa.String(32), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("skip", sa.String(1), nullable=False),
        sa.Column("power_mw", sa.Integer(), nullable=True),
        sa.Column("tuning_step_hz", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "channel_sets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "set_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("set_id", sa.Integer(),
                  sa.ForeignKey("channel_sets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("memory_id", sa.Integer(),
                  sa.ForeignKey("memories.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("alias", sa.String(64), nullable=True),
        sa.Column("skip", sa.String(1), nullable=True),
        sa.UniqueConstraint("set_id", "memory_id", name="uq_set_member"),
    )


def downgrade() -> None:
    op.drop_table("set_members")
    op.drop_table("channel_sets")
    op.drop_table("memories")
