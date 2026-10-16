"""align user email uniqueness with ORM metadata

Revision ID: 0006_user_email_index
Revises: 0005_generation_reliability
"""

from alembic import op


revision = "0006_user_email_index"
down_revision = "0005_generation_reliability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("users_email_key", "users", type_="unique")
    op.drop_index("ix_users_email", table_name="users")
    op.create_index("ix_users_email", "users", ["email"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_email", table_name="users")
    op.create_index("ix_users_email", "users", ["email"], unique=False)
    op.create_unique_constraint("users_email_key", "users", ["email"])
