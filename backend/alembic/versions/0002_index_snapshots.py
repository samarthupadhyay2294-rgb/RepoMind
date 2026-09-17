"""Create repository_index_snapshots + repositories.active_snapshot_id.

Revision ID: 0002_index_snapshots
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0002_index_snapshots"
down_revision: str | None = "0001_create_repositories"
branch_labels: str | None = None
depends_on: str | None = None

SNAPSHOT_STATUS = sa.Enum(
    "pending", "indexing", "ready", "failed", name="snapshot_status"
)


def upgrade() -> None:
    op.create_table(
        "repository_index_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "repository_id",
            sa.Uuid(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("revision", sa.String(128), nullable=True),
        sa.Column("manifest_hash", sa.String(128), nullable=False),
        sa.Column("parser_version", sa.String(64), nullable=False, server_default="v1"),
        sa.Column(
            "embedding_model",
            sa.String(128),
            nullable=False,
            server_default="mistral-embed",
        ),
        sa.Column(
            "embedding_dimensions", sa.Integer(), nullable=False, server_default="1024"
        ),
        sa.Column("status", SNAPSHOT_STATUS, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_snapshots_repository_id",
        "repository_index_snapshots",
        ["repository_id"],
    )
    op.create_index(
        "ix_snapshots_repo_status",
        "repository_index_snapshots",
        ["repository_id", "status"],
    )
    op.create_index(
        "ix_snapshots_created_at", "repository_index_snapshots", ["created_at"]
    )
    op.add_column(
        "repositories",
        sa.Column("active_snapshot_id", sa.Uuid(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("repositories", "active_snapshot_id")
    op.drop_index("ix_snapshots_created_at", table_name="repository_index_snapshots")
    op.drop_index("ix_snapshots_repo_status", table_name="repository_index_snapshots")
    op.drop_index("ix_snapshots_repository_id", table_name="repository_index_snapshots")
    op.drop_table("repository_index_snapshots")
    SNAPSHOT_STATUS.drop(op.get_bind(), checkfirst=True)
