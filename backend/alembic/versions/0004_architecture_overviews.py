"""Create architecture_overviews (Part 3 overview, snapshot-scoped).

Revision ID: 0004_architecture_overviews
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0004_architecture_overviews"
down_revision: str | None = "0003_code_graph"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "architecture_overviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "repository_id",
            sa.Uuid(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "snapshot_id",
            sa.Uuid(),
            sa.ForeignKey(
                "repository_index_snapshots.id", ondelete="CASCADE"
            ),
            nullable=False,
        ),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("architecture_style", sa.String(64), nullable=True),
        sa.Column("entry_points", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("components", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("data_flows", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("boundaries", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column(
            "key_dependencies", sa.JSON(), nullable=False, server_default="[]"
        ),
        sa.Column(
            "configuration_areas", sa.JSON(), nullable=False, server_default="[]"
        ),
        sa.Column("uncertainties", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("evidence", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column(
            "evidence_truncated", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "evidence_items_total", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "evidence_items_used", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "generation_model", sa.String(128), nullable=False, server_default=""
        ),
        sa.Column(
            "generation_status",
            sa.String(16),
            nullable=False,
            server_default="completed",
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "prompt_version", sa.String(32), nullable=False, server_default="v1"
        ),
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
    )
    op.create_index(
        "ix_overviews_repository_id", "architecture_overviews", ["repository_id"]
    )
    op.create_index(
        "ix_overviews_snapshot_id", "architecture_overviews", ["snapshot_id"]
    )
    op.create_index(
        "ix_overviews_repo_snapshot",
        "architecture_overviews",
        ["repository_id", "snapshot_id"],
    )
    op.create_index(
        "ix_overviews_status",
        "architecture_overviews",
        ["repository_id", "generation_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_overviews_status", table_name="architecture_overviews")
    op.drop_index("ix_overviews_repo_snapshot", table_name="architecture_overviews")
    op.drop_index("ix_overviews_snapshot_id", table_name="architecture_overviews")
    op.drop_index(
        "ix_overviews_repository_id", table_name="architecture_overviews"
    )
    op.drop_table("architecture_overviews")
