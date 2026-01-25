"""Add conflict events table.

Revision ID: 0002_conflict_events
Revises: 0001_init
Create Date: 2025-01-01 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_conflict_events"
down_revision = "0001_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conflict_events",
        sa.Column("event_id", sa.Integer(), primary_key=True),
        sa.Column("doc_id", sa.String(length=64), nullable=False),
        sa.Column("canonical_path", sa.String(length=256), nullable=False),
        sa.Column("node_id_a", sa.String(length=64), nullable=False),
        sa.Column("node_id_b", sa.String(length=64), nullable=False),
        sa.Column("version_id_a", sa.Integer(), nullable=False),
        sa.Column("version_id_b", sa.Integer(), nullable=False),
        sa.Column("valid_from_a", sa.Date(), nullable=True),
        sa.Column("valid_to_a", sa.Date(), nullable=True),
        sa.Column("valid_from_b", sa.Date(), nullable=True),
        sa.Column("valid_to_b", sa.Date(), nullable=True),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["doc_id"], ["documents.doc_id"]),
        sa.ForeignKeyConstraint(["node_id_a"], ["nodes.node_id"]),
        sa.ForeignKeyConstraint(["node_id_b"], ["nodes.node_id"]),
        sa.ForeignKeyConstraint(["version_id_a"], ["document_versions.version_id"]),
        sa.ForeignKeyConstraint(["version_id_b"], ["document_versions.version_id"]),
    )
    op.create_index("ix_conflicts_doc_path", "conflict_events", ["doc_id", "canonical_path"])


def downgrade() -> None:
    op.drop_index("ix_conflicts_doc_path", table_name="conflict_events")
    op.drop_table("conflict_events")
