from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ingestion_runs",
        sa.Column("run_id", sa.Integer(), primary_key=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("input_dir", sa.Text(), nullable=False),
        sa.Column("stats_json", sa.JSON(), nullable=True),
    )
    op.create_table(
        "raw_files",
        sa.Column("raw_id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("original_path", sa.Text(), nullable=False),
        sa.Column("derived_from_raw_id", sa.Integer(), nullable=True),
        sa.Column("is_from_zip", sa.Boolean(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("mtime", sa.DateTime(), nullable=False),
        sa.Column("discovered_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["derived_from_raw_id"], ["raw_files.raw_id"]),
    )
    op.create_unique_constraint("uq_raw_files_sha256", "raw_files", ["sha256"])
    op.create_unique_constraint("uq_raw_files_derived", "raw_files", ["derived_from_raw_id", "original_path"])
    op.create_table(
        "documents",
        sa.Column("doc_id", sa.String(length=64), primary_key=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("canonical_doc", sa.String(length=128), nullable=False),
        sa.Column("doc_type", sa.String(length=32), nullable=False),
        sa.Column("number", sa.Integer(), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("subtitle", sa.Text(), nullable=True),
        sa.Column("publication_date", sa.Date(), nullable=True),
        sa.Column("entry_into_force_date", sa.Date(), nullable=True),
        sa.Column("last_seen_raw_id", sa.Integer(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["last_seen_raw_id"], ["raw_files.raw_id"]),
    )
    op.create_table(
        "document_versions",
        sa.Column("version_id", sa.Integer(), primary_key=True),
        sa.Column("doc_id", sa.String(length=64), nullable=False),
        sa.Column("version_tag", sa.String(length=128), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=True),
        sa.Column("source_raw_id", sa.Integer(), nullable=True),
        sa.Column("checksum_text", sa.String(length=64), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["doc_id"], ["documents.doc_id"]),
        sa.ForeignKeyConstraint(["source_raw_id"], ["raw_files.raw_id"]),
    )
    op.create_unique_constraint("uq_document_version", "document_versions", ["doc_id", "version_tag"])
    op.create_table(
        "nodes",
        sa.Column("node_id", sa.String(length=64), primary_key=True),
        sa.Column("doc_id", sa.String(length=64), nullable=False),
        sa.Column("version_id", sa.Integer(), nullable=False),
        sa.Column("node_type", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=128), nullable=False),
        sa.Column("canonical_path", sa.String(length=256), nullable=False),
        sa.Column("sort_key", sa.String(length=256), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=True),
        sa.Column("heading", sa.Text(), nullable=True),
        sa.Column("text_raw", sa.Text(), nullable=False),
        sa.Column("text_clean", sa.Text(), nullable=False),
        sa.Column("text_hash", sa.String(length=64), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("flags_json", sa.JSON(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["doc_id"], ["documents.doc_id"]),
        sa.ForeignKeyConstraint(["version_id"], ["document_versions.version_id"]),
    )
    op.create_unique_constraint("uq_nodes_path", "nodes", ["version_id", "canonical_path"])
    op.create_table(
        "references_extracted",
        sa.Column("ref_id", sa.Integer(), primary_key=True),
        sa.Column("source_node_id", sa.String(length=64), nullable=False),
        sa.Column("raw_snippet", sa.Text(), nullable=False),
        sa.Column("match_text", sa.Text(), nullable=False),
        sa.Column("relation_type", sa.String(length=32), nullable=False),
        sa.Column("target_canonical_doc", sa.String(length=128), nullable=True),
        sa.Column("target_article", sa.String(length=32), nullable=True),
        sa.Column("target_comma", sa.String(length=32), nullable=True),
        sa.Column("target_letter", sa.String(length=8), nullable=True),
        sa.Column("target_number", sa.String(length=32), nullable=True),
        sa.Column("target_canonical_node", sa.String(length=256), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("method", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["source_node_id"], ["nodes.node_id"]),
    )
    op.create_index("ix_refs_source", "references_extracted", ["source_node_id"])
    op.create_index("ix_refs_target_doc", "references_extracted", ["target_canonical_doc"])
    op.create_index("ix_refs_target_node", "references_extracted", ["target_canonical_node"])
    op.create_table(
        "references_resolved",
        sa.Column("source_node_id", sa.String(length=64), primary_key=True),
        sa.Column("target_node_id", sa.String(length=64), nullable=True),
        sa.Column("target_canonical_node", sa.String(length=256), primary_key=True),
        sa.Column("relation_type", sa.String(length=32), primary_key=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["source_node_id"], ["nodes.node_id"]),
        sa.ForeignKeyConstraint(["target_node_id"], ["nodes.node_id"]),
    )


def downgrade() -> None:
    op.drop_table("references_resolved")
    op.drop_index("ix_refs_target_node", table_name="references_extracted")
    op.drop_index("ix_refs_target_doc", table_name="references_extracted")
    op.drop_index("ix_refs_source", table_name="references_extracted")
    op.drop_table("references_extracted")
    op.drop_constraint("uq_nodes_path", "nodes", type_="unique")
    op.drop_table("nodes")
    op.drop_constraint("uq_document_version", "document_versions", type_="unique")
    op.drop_table("document_versions")
    op.drop_table("documents")
    op.drop_constraint("uq_raw_files_derived", "raw_files", type_="unique")
    op.drop_constraint("uq_raw_files_sha256", "raw_files", type_="unique")
    op.drop_table("raw_files")
    op.drop_table("ingestion_runs")
