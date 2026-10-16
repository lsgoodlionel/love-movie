"""persist queue dispatch confirmation

Revision ID: 0007_dispatch_confirmation
Revises: 0006_user_email_index
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_dispatch_confirmation"
down_revision = "0006_user_email_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "generation_tasks",
        sa.Column("dispatch_confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("generation_tasks", "dispatch_confirmed_at")
