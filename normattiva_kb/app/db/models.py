from __future__ import annotations

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, JSON, Float
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
import datetime as dt


class Base(DeclarativeBase):
    pass


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"
    run_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="running")
    input_dir: Mapped[str] = mapped_column(Text)
    stats_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class RawFile(Base):
    __tablename__ = "raw_files"
    raw_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(32), default="normattiva")
    original_path: Mapped[str] = mapped_column(Text)
    derived_from_raw_id: Mapped[int | None] = mapped_column(ForeignKey("raw_files.raw_id"), nullable=True)
    is_from_zip: Mapped[bool] = mapped_column(Boolean, default=False)
    sha256: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(Integer)
    mtime: Mapped[dt.datetime] = mapped_column(DateTime)
    discovered_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    status: Mapped[str] = mapped_column(String(32), default="new")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("sha256", name="uq_raw_files_sha256"),
        UniqueConstraint("derived_from_raw_id", "original_path", name="uq_raw_files_derived"),
    )


class Document(Base):
    __tablename__ = "documents"
    doc_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source: Mapped[str] = mapped_column(String(32), default="normattiva")
    canonical_doc: Mapped[str] = mapped_column(String(128))
    doc_type: Mapped[str] = mapped_column(String(32))
    number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    subtitle: Mapped[str | None] = mapped_column(Text, nullable=True)
    publication_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    entry_into_force_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    last_seen_raw_id: Mapped[int | None] = mapped_column(ForeignKey("raw_files.raw_id"), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    version_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doc_id: Mapped[str] = mapped_column(ForeignKey("documents.doc_id"))
    version_tag: Mapped[str] = mapped_column(String(128))
    valid_from: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    is_current: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    source_raw_id: Mapped[int | None] = mapped_column(ForeignKey("raw_files.raw_id"), nullable=True)
    checksum_text: Mapped[str] = mapped_column(String(64))
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (UniqueConstraint("doc_id", "version_tag", name="uq_document_version"),)


class Node(Base):
    __tablename__ = "nodes"
    node_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    doc_id: Mapped[str] = mapped_column(ForeignKey("documents.doc_id"))
    version_id: Mapped[int] = mapped_column(ForeignKey("document_versions.version_id"))
    node_type: Mapped[str] = mapped_column(String(32))
    label: Mapped[str] = mapped_column(String(128))
    canonical_path: Mapped[str] = mapped_column(String(256))
    hierarchy_string: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_key: Mapped[str] = mapped_column(String(256))
    ordinal: Mapped[int | None] = mapped_column(Integer, nullable=True)
    heading: Mapped[str | None] = mapped_column(Text, nullable=True)
    text_raw: Mapped[str] = mapped_column(Text)
    text_clean: Mapped[str] = mapped_column(Text)
    text_hash: Mapped[str] = mapped_column(String(64))
    language: Mapped[str] = mapped_column(String(8), default="it")
    valid_from: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    is_current_law: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    flags_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (UniqueConstraint("version_id", "canonical_path", name="uq_nodes_path"),)


class ReferenceExtracted(Base):
    __tablename__ = "references_extracted"
    ref_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_node_id: Mapped[str] = mapped_column(ForeignKey("nodes.node_id"))
    raw_snippet: Mapped[str] = mapped_column(Text)
    match_text: Mapped[str] = mapped_column(Text)
    relation_type: Mapped[str] = mapped_column(String(32), default="CITES")
    target_canonical_doc: Mapped[str | None] = mapped_column(String(128), nullable=True)
    target_article: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_comma: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_letter: Mapped[str | None] = mapped_column(String(8), nullable=True)
    target_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_canonical_node: Mapped[str | None] = mapped_column(String(256), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    method: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


class ReferenceResolved(Base):
    __tablename__ = "references_resolved"
    source_node_id: Mapped[str] = mapped_column(ForeignKey("nodes.node_id"), primary_key=True)
    target_node_id: Mapped[str | None] = mapped_column(ForeignKey("nodes.node_id"), nullable=True)
    target_canonical_node: Mapped[str] = mapped_column(String(256), primary_key=True)
    relation_type: Mapped[str] = mapped_column(String(32), primary_key=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)


class UrnResolutionLog(Base):
    __tablename__ = "urn_resolution_log"
    log_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    original_text: Mapped[str] = mapped_column(Text)
    resolved_urn: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    resolution_method: Mapped[str] = mapped_column(String(32))
    document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.doc_id"), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


class ConflictEvent(Base):
    __tablename__ = "conflict_events"
    event_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doc_id: Mapped[str] = mapped_column(ForeignKey("documents.doc_id"))
    canonical_path: Mapped[str] = mapped_column(String(256))
    node_id_a: Mapped[str] = mapped_column(ForeignKey("nodes.node_id"))
    node_id_b: Mapped[str] = mapped_column(ForeignKey("nodes.node_id"))
    version_id_a: Mapped[int] = mapped_column(ForeignKey("document_versions.version_id"))
    version_id_b: Mapped[int] = mapped_column(ForeignKey("document_versions.version_id"))
    valid_from_a: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    valid_to_a: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    valid_from_b: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    valid_to_b: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    severity: Mapped[str] = mapped_column(String(16), default="warning")
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)


class DocumentVersionDelta(Base):
    __tablename__ = "document_version_deltas"
    delta_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doc_id: Mapped[str] = mapped_column(ForeignKey("documents.doc_id"))
    version_id: Mapped[int] = mapped_column(ForeignKey("document_versions.version_id"))
    base_version_id: Mapped[int | None] = mapped_column(ForeignKey("document_versions.version_id"), nullable=True)
    delta_text: Mapped[str] = mapped_column(Text)
    compression_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
