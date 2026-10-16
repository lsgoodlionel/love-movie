"""tenant-scoped routes, quota reservations and atomic usage

Revision ID: 0008_tenant_reliability
Revises: 0007_dispatch_confirmation
"""

from alembic import op
import sqlalchemy as sa


revision = "0008_tenant_reliability"
down_revision = "0007_dispatch_confirmation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("model_routes", sa.Column("tenant_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_model_routes_tenant_id", "model_routes", "tenants", ["tenant_id"], ["id"], ondelete="CASCADE"
    )
    op.drop_constraint("model_routes_capability_quality_key", "model_routes", type_="unique")
    op.create_unique_constraint(
        "uq_model_routes_tenant_capability_quality", "model_routes", ["tenant_id", "capability", "quality"]
    )
    op.create_index("ix_model_routes_tenant_id", "model_routes", ["tenant_id"], unique=False)
    op.add_column(
        "generation_tasks",
        sa.Column("reserved_gpu_seconds", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "generation_tasks",
        sa.Column("reserved_storage_bytes", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.create_unique_constraint("uq_usage_generation_task", "usage_ledger", ["generation_task_id"])


def downgrade() -> None:
    op.drop_constraint("uq_usage_generation_task", "usage_ledger", type_="unique")
    op.drop_column("generation_tasks", "reserved_storage_bytes")
    op.drop_column("generation_tasks", "reserved_gpu_seconds")
    op.drop_index("ix_model_routes_tenant_id", table_name="model_routes")
    op.drop_constraint("uq_model_routes_tenant_capability_quality", "model_routes", type_="unique")
    op.create_unique_constraint(
        "model_routes_capability_quality_key", "model_routes", ["capability", "quality"]
    )
    op.drop_constraint("fk_model_routes_tenant_id", "model_routes", type_="foreignkey")
    op.drop_column("model_routes", "tenant_id")
