"""generation reliability constraints

Revision ID: 0005_generation_reliability
Revises: 0004_generation_events
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_generation_reliability"
down_revision = "0004_generation_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("gpu_seconds_limit", sa.Float(), nullable=True))
    op.add_column("tenants", sa.Column("storage_bytes_limit", sa.BigInteger(), nullable=True))
    op.add_column("generation_tasks", sa.Column("request_digest", sa.String(length=64), nullable=True))
    op.create_unique_constraint(
        "uq_generation_step_task_name",
        "generation_steps",
        ["generation_task_id", "name"],
    )
    op.alter_column("usage_ledger", "storage_bytes", existing_type=sa.Integer(), type_=sa.BigInteger())


def downgrade() -> None:
    op.alter_column("usage_ledger", "storage_bytes", existing_type=sa.BigInteger(), type_=sa.Integer())
    op.drop_constraint("uq_generation_step_task_name", "generation_steps", type_="unique")
    op.drop_column("generation_tasks", "request_digest")
    op.drop_column("tenants", "storage_bytes_limit")
    op.drop_column("tenants", "gpu_seconds_limit")
