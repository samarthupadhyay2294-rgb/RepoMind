"""Create investigations + investigation_actions (Part 4/5 debug, snapshot-scoped).

Revision ID: 0005_investigations
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0005_investigations"
down_revision: str | None = "0004_architecture_overviews"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "investigations",
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
            sa.ForeignKey("repository_index_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("error_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("stack_trace", sa.Text(), nullable=True),
        sa.Column("affected_route", sa.String(512), nullable=True),
        sa.Column("environment", sa.String(256), nullable=True),
        sa.Column("expected_behavior", sa.Text(), nullable=True),
        sa.Column("actual_behavior", sa.Text(), nullable=True),
        sa.Column("reproduction_steps", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("verdict", sa.String(16), nullable=True),
        sa.Column("confidence", sa.String(16), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("findings", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("next_steps", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("limitations", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("citations", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("stop_reason", sa.String(64), nullable=False, server_default=""),
        sa.Column("tool_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("llm_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column(
            "evidence_truncated",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("session_id", sa.String(64), nullable=True),
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
        "ix_investigations_repository_id", "investigations", ["repository_id"]
    )
    op.create_index(
        "ix_investigations_snapshot_id", "investigations", ["snapshot_id"]
    )
    op.create_index(
        "ix_investigations_repo_snapshot",
        "investigations",
        ["repository_id", "snapshot_id"],
    )
    op.create_index(
        "ix_investigations_status", "investigations", ["repository_id", "status"]
    )
    op.create_table(
        "investigation_actions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "investigation_id",
            sa.Uuid(),
            sa.ForeignKey("investigations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tool_name", sa.String(64), nullable=False, server_default=""),
        sa.Column("arguments", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("ok", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("result_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("warning", sa.String(256), nullable=False, server_default=""),
        sa.Column("duration_ms", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_inv_actions_investigation_id",
        "investigation_actions",
        ["investigation_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_inv_actions_investigation_id", table_name="investigation_actions"
    )
    op.drop_table("investigation_actions")
    op.drop_index("ix_investigations_status", table_name="investigations")
    op.drop_index("ix_investigations_repo_snapshot", table_name="investigations")
    op.drop_index("ix_investigations_snapshot_id", table_name="investigations")
    op.drop_index("ix_investigations_repository_id", table_name="investigations")
    op.drop_table("investigations")
