"""Create configurable compute nodes, workflows and model routes."""

import uuid

from alembic import op
import sqlalchemy as sa


revision = "0003_ai_resources"
down_revision = "0002_generation_assets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "compute_nodes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("base_url", sa.String(length=512), nullable=False),
        sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("vram_gb", sa.Integer(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "workflow_definitions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("version", sa.String(length=40), nullable=False),
        sa.Column("capability", sa.String(length=80), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "version"),
    )
    op.create_table(
        "model_routes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("capability", sa.String(length=80), nullable=False),
        sa.Column("quality", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("capability", "quality"),
    )

    routes = sa.table(
        "model_routes",
        sa.column("id", sa.Uuid()),
        sa.column("capability", sa.String()),
        sa.column("quality", sa.String()),
        sa.column("model", sa.String()),
        sa.column("priority", sa.Integer()),
        sa.column("enabled", sa.Boolean()),
    )
    op.bulk_insert(
        routes,
        [
            {"id": uuid.uuid4(), "capability": "cleanup", "quality": "interactive", "model": "qwen3.5:4b", "priority": 10, "enabled": True},
            {"id": uuid.uuid4(), "capability": "json_repair", "quality": "interactive", "model": "qwen3.5:4b", "priority": 20, "enabled": True},
            {"id": uuid.uuid4(), "capability": "story_planning", "quality": "interactive", "model": "qwen3.5:latest", "priority": 30, "enabled": True},
            {"id": uuid.uuid4(), "capability": "dialogue_enhancement", "quality": "interactive", "model": "gemma4:12b", "priority": 40, "enabled": True},
            {"id": uuid.uuid4(), "capability": "longform_planning", "quality": "high_quality_async", "model": "qwen3.8:27b", "priority": 50, "enabled": True},
            {"id": uuid.uuid4(), "capability": "final_review", "quality": "manual", "model": "gemma4:31b", "priority": 60, "enabled": True},
        ],
    )

    workflows = sa.table(
        "workflow_definitions",
        sa.column("id", sa.Uuid()),
        sa.column("name", sa.String()),
        sa.column("version", sa.String()),
        sa.column("capability", sa.String()),
        sa.column("enabled", sa.Boolean()),
    )
    op.bulk_insert(
        workflows,
        [
            {"id": uuid.uuid4(), "name": "z_image_turbo", "version": "v1", "capability": "text_to_image", "enabled": True},
            {"id": uuid.uuid4(), "name": "wan_i2v", "version": "v1", "capability": "image_to_video", "enabled": True},
        ],
    )


def downgrade() -> None:
    op.drop_table("model_routes")
    op.drop_table("workflow_definitions")
    op.drop_table("compute_nodes")
