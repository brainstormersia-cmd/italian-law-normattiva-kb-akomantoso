from __future__ import annotations

import datetime as dt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models
from app.core.utils_ids import canonical_node_id


def upsert_raw_file(session: Session, data: dict) -> models.RawFile:
    existing = session.execute(
        select(models.RawFile).where(models.RawFile.sha256 == data["sha256"])
    ).scalar_one_or_none()
    if existing:
        return existing
    raw = models.RawFile(**data)
    session.add(raw)
    session.flush()
    return raw


def upsert_document(session: Session, data: dict) -> models.Document:
    existing = session.get(models.Document, data["doc_id"])
    if existing:
        for key, value in data.items():
            setattr(existing, key, value)
        existing.updated_at = dt.datetime.utcnow()
        session.flush()
        return existing
    doc = models.Document(**data)
    session.add(doc)
    session.flush()
    return doc


def upsert_document_version(session: Session, data: dict) -> models.DocumentVersion:
    existing = session.execute(
        select(models.DocumentVersion)
        .where(models.DocumentVersion.doc_id == data["doc_id"])
        .where(models.DocumentVersion.version_tag == data["version_tag"])
    ).scalar_one_or_none()
    if existing:
        for key, value in data.items():
            setattr(existing, key, value)
        session.flush()
        return existing
    version = models.DocumentVersion(**data)
    session.add(version)
    session.flush()
    return version


def upsert_node(session: Session, node_data: dict) -> models.Node:
    existing = session.execute(
        select(models.Node)
        .where(models.Node.version_id == node_data["version_id"])
        .where(models.Node.canonical_path == node_data["canonical_path"])
    ).scalar_one_or_none()
    if existing:
        for key, value in node_data.items():
            setattr(existing, key, value)
        session.flush()
        return existing
    node = models.Node(**node_data)
    session.add(node)
    session.flush()
    return node
