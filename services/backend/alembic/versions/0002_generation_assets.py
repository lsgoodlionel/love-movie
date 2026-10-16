"""Create generation tasks, steps, assets and usage ledger."""

from alembic import op
import sqlalchemy as sa


revision = "0002_generation_assets"
down_revision = "0001_identity_projects"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "generation_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("current_step", sa.String(length=64), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("remote_prompt_id", sa.String(length=128), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("workflow_version", sa.String(length=120), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_generation_tenant_idempotency"),
    )
    op.create_index("ix_generation_tasks_project_id", "generation_tasks", ["project_id"], unique=False)
    op.create_index("ix_generation_tasks_remote_prompt_id", "generation_tasks", ["remote_prompt_id"], unique=False)
    op.create_index("ix_generation_tasks_status", "generation_tasks", ["status"], unique=False)
    op.create_index("ix_generation_tasks_tenant_id", "generation_tasks", ["tenant_id"], unique=False)
    op.create_table(
        "generation_steps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("generation_task_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("remote_prompt_id", sa.String(length=128), nullable=True),
        sa.Column("input_digest", sa.String(length=64), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["generation_task_id"], ["generation_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_generation_steps_generation_task_id", "generation_steps", ["generation_task_id"], unique=False)
    op.create_index("ix_generation_steps_remote_prompt_id", "generation_steps", ["remote_prompt_id"], unique=False)
    op.create_table(
        "assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("generation_task_id", sa.Uuid(), nullable=False),
        sa.Column("parent_asset_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("object_key", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["generation_task_id"], ["generation_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_key"),
    )
    op.create_index("ix_assets_generation_task_id", "assets", ["generation_task_id"], unique=False)
    op.create_index("ix_assets_project_id", "assets", ["project_id"], unique=False)
    op.create_index("ix_assets_tenant_id", "assets", ["tenant_id"], unique=False)
    op.create_table(
        "usage_ledger",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("generation_task_id", sa.Uuid(), nullable=False),
        sa.Column("requested_model", sa.String(length=120), nullable=True),
        sa.Column("actual_model", sa.String(length=120), nullable=True),
        sa.Column("fallback_reason", sa.String(length=240), nullable=True),
        sa.Column("gpu_seconds", sa.Float(), nullable=False),
        sa.Column("storage_bytes", sa.Integer(), nullable=False),
        sa.Column("content_safety_decision", sa.String(length=64), nullable=False),
        sa.Column("adult_content_declared", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["generation_task_id"], ["generation_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_usage_ledger_generation_task_id", "usage_ledger", ["generation_task_id"], unique=False)
    op.create_index("ix_usage_ledger_project_id", "usage_ledger", ["project_id"], unique=False)
    op.create_index("ix_usage_ledger_tenant_id", "usage_ledger", ["tenant_id"], unique=False)


def downgrade() -> None:
    op.drop_table("usage_ledger")
    op.drop_table("assets")
    op.drop_table("generation_steps")
    op.drop_table("generation_tasks")
