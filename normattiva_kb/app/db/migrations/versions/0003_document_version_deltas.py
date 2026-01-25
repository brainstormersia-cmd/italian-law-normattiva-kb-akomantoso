"""Add document version deltas table.

Revision ID: 0003_document_version_deltas
Revises: 0002_conflict_events
Create Date: 2025-01-01 00:00:01.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003_document_version_deltas"
down_revision = "0002_conflict_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_version_deltas",
        sa.Column("delta_id", sa.Integer(), primary_key=True),
        sa.Column("doc_id", sa.String(length=64), nullable=False),
        sa.Column("version_id", sa.Integer(), nullable=False),
        sa.Column("base_version_id", sa.Integer(), nullable=True),
        sa.Column("delta_text", sa.Text(), nullable=False),
        sa.Column("compression_ratio", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["doc_id"], ["documents.doc_id"]),
        sa.ForeignKeyConstraint(["version_id"], ["document_versions.version_id"]),
        sa.ForeignKeyConstraint(["base_version_id"], ["document_versions.version_id"]),
    )
    op.create_index("ix_version_deltas_doc", "document_version_deltas", ["doc_id", "version_id"])


def downgrade() -> None:
    op.drop_index("ix_version_deltas_doc", table_name="document_version_deltas")
    op.drop_table("document_version_deltas")
