"""Create code_symbols + code_relationships (Part 2 graph, snapshot-scoped).

Revision ID: 0003_code_graph
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0003_code_graph"
down_revision: str | None = "0002_index_snapshots"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "code_symbols",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("repository_id", sa.Uuid(), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), sa.ForeignKey("repository_index_snapshots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stable_key", sa.String(1024), nullable=False),
        sa.Column("symbol_type", sa.String(32), nullable=False),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("qualified_name", sa.String(1024), nullable=False),
        sa.Column("path", sa.String(1024), nullable=False),
        sa.Column("start_line", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("end_line", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("signature", sa.Text(), nullable=True),
        sa.Column("parent_symbol_id", sa.Uuid(), nullable=True),
        sa.Column("language", sa.String(32), nullable=True),
        sa.Column("visibility", sa.String(32), nullable=True),
        sa.Column("provenance", sa.String(16), nullable=False, server_default="parser"),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_symbols_repository_id", "code_symbols", ["repository_id"])
    op.create_index("ix_symbols_snapshot_id", "code_symbols", ["snapshot_id"])
    op.create_index("ix_symbols_repo_snapshot", "code_symbols", ["repository_id", "snapshot_id"])
    op.create_index("ix_symbols_stable_key", "code_symbols", ["repository_id", "snapshot_id", "stable_key"])
    op.create_index("ix_symbols_path", "code_symbols", ["repository_id", "snapshot_id", "path"])
    op.create_index("ix_symbols_parent", "code_symbols", ["parent_symbol_id"])

    op.create_table(
        "code_relationships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("repository_id", sa.Uuid(), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), sa.ForeignKey("repository_index_snapshots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_symbol_id", sa.Uuid(), nullable=False),
        sa.Column("target_symbol_id", sa.Uuid(), nullable=False),
        sa.Column("relationship_type", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("provenance", sa.String(16), nullable=False, server_default="parser"),
        sa.Column("path", sa.String(1024), nullable=False, server_default=""),
        sa.Column("start_line", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("end_line", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("excerpt", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rels_repository_id", "code_relationships", ["repository_id"])
    op.create_index("ix_rels_snapshot_id", "code_relationships", ["snapshot_id"])
    op.create_index("ix_rels_repo_snapshot", "code_relationships", ["repository_id", "snapshot_id"])
    op.create_index("ix_rels_source", "code_relationships", ["repository_id", "snapshot_id", "source_symbol_id"])
    op.create_index("ix_rels_target", "code_relationships", ["repository_id", "snapshot_id", "target_symbol_id"])
    op.create_index("ix_rels_type", "code_relationships", ["repository_id", "snapshot_id", "relationship_type"])


def downgrade() -> None:
    op.drop_index("ix_rels_type", table_name="code_relationships")
    op.drop_index("ix_rels_target", table_name="code_relationships")
    op.drop_index("ix_rels_source", table_name="code_relationships")
    op.drop_index("ix_rels_repo_snapshot", table_name="code_relationships")
    op.drop_index("ix_rels_snapshot_id", table_name="code_relationships")
    op.drop_index("ix_rels_repository_id", table_name="code_relationships")
    op.drop_table("code_relationships")
    op.drop_index("ix_symbols_parent", table_name="code_symbols")
    op.drop_index("ix_symbols_path", table_name="code_symbols")
    op.drop_index("ix_symbols_stable_key", table_name="code_symbols")
    op.drop_index("ix_symbols_repo_snapshot", table_name="code_symbols")
    op.drop_index("ix_symbols_snapshot_id", table_name="code_symbols")
    op.drop_index("ix_symbols_repository_id", table_name="code_symbols")
    op.drop_table("code_symbols")
