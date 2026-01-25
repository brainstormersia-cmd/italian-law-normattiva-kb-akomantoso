from __future__ import annotations

import datetime as dt
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, Text, UniqueConstraint, JSON, Float
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"
    doc_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    urn: Mapped[str | None] = mapped_column(Text, nullable=True)
    doc_type: Mapped[str] = mapped_column(String(32))
    number: Mapped[int | None] = mapped_column(nullable=True)
    year: Mapped[int | None] = mapped_column(nullable=True)


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    version_id: Mapped[int] = mapped_column(primary_key=True)
    doc_id: Mapped[str] = mapped_column(ForeignKey("documents.doc_id"))
    version_tag: Mapped[str] = mapped_column(String(128))
    version_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    publication_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    checksum_text: Mapped[str] = mapped_column(String(64))

    __table_args__ = (UniqueConstraint("doc_id", "version_tag", name="uq_document_version"),)


class Node(Base):
    __tablename__ = "nodes"
    node_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("document_versions.version_id"))
    eId: Mapped[str | None] = mapped_column(String(128), nullable=True)
    canonical_path: Mapped[str] = mapped_column(String(256))
    text_content: Mapped[str] = mapped_column(Text)
    text_xml_fragment: Mapped[str | None] = mapped_column(Text, nullable=True)
    level: Mapped[int] = mapped_column()

    __table_args__ = (UniqueConstraint("version_id", "canonical_path", name="uq_nodes_path"),)


class Reference(Base):
    __tablename__ = "references_extracted"
    ref_id: Mapped[int] = mapped_column(primary_key=True)
    source_node_id: Mapped[str] = mapped_column(ForeignKey("nodes.node_id"))
    destination_urn: Mapped[str | None] = mapped_column(Text, nullable=True)
    text_surrogate: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
