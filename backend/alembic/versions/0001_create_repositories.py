"""Create repositories table.

Revision ID: 0001_create_repositories
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0001_create_repositories"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None

SOURCE_TYPE = sa.Enum("local", "git", name="repository_source_type")
STATUS = sa.Enum(
    "pending",
    "ready",
    "indexing",
    "indexed",
    "failed",
    "deleted",
    name="repository_status",
)


def upgrade() -> None:
    op.create_table(
        "repositories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("source_type", SOURCE_TYPE, nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("local_path", sa.Text(), nullable=True),
        sa.Column("default_branch", sa.String(100), nullable=True),
        sa.Column("current_commit_sha", sa.String(64), nullable=True),
        sa.Column("status", STATUS, nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "name", name="uq_repositories_owner_name"),
    )
    op.create_index("ix_repositories_owner_id", "repositories", ["owner_id"])
    op.create_index("ix_repositories_status", "repositories", ["status"])
    op.create_index("ix_repositories_created_at", "repositories", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_repositories_created_at", table_name="repositories")
    op.drop_index("ix_repositories_status", table_name="repositories")
    op.drop_index("ix_repositories_owner_id", table_name="repositories")
    op.drop_table("repositories")
    STATUS.drop(op.get_bind(), checkfirst=True)
    SOURCE_TYPE.drop(op.get_bind(), checkfirst=True)
