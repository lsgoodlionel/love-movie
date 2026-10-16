"""Create durable generation progress events."""

from alembic import op
import sqlalchemy as sa


revision = "0004_generation_events"
down_revision = "0003_ai_resources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "generation_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("generation_task_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("message", sa.String(length=240), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["generation_task_id"], ["generation_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_generation_events_generation_task_id", "generation_events", ["generation_task_id"])


def downgrade() -> None:
    op.drop_table("generation_events")
