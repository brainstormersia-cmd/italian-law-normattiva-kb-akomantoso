from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.schemas import DocumentOut, NodeOut
from app.db import models
from app.parsing.references import extract_references

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/docs", response_model=list[DocumentOut])
def list_docs(doc_type: str | None = None, year: int | None = None, number: int | None = None, db: Session = Depends(get_db)):
    query = select(models.Document)
    if doc_type:
        query = query.where(models.Document.doc_type == doc_type)
    if year:
        query = query.where(models.Document.year == year)
    if number:
        query = query.where(models.Document.number == number)
    docs = db.execute(query).scalars().all()
    return [DocumentOut(**doc.__dict__) for doc in docs]


@router.get("/doc/{canonical_doc}")
def doc_detail(canonical_doc: str, db: Session = Depends(get_db)):
    doc = db.execute(select(models.Document).where(models.Document.canonical_doc == canonical_doc)).scalar_one_or_none()
    if not doc:
        return {"error": "not_found"}
    versions = db.execute(select(models.DocumentVersion).where(models.DocumentVersion.doc_id == doc.doc_id)).scalars().all()
    return {"document": doc.__dict__, "versions": [v.__dict__ for v in versions]}


@router.get("/doc/{canonical_doc}/tree")
def doc_tree(canonical_doc: str, version_tag: str | None = None, db: Session = Depends(get_db)):
    doc = db.execute(select(models.Document).where(models.Document.canonical_doc == canonical_doc)).scalar_one_or_none()
    if not doc:
        return {"error": "not_found"}
    version_query = select(models.DocumentVersion).where(models.DocumentVersion.doc_id == doc.doc_id)
    if version_tag:
        version_query = version_query.where(models.DocumentVersion.version_tag == version_tag)
    version = db.execute(version_query).scalars().first()
    if not version:
        return {"error": "version_not_found"}
    nodes = db.execute(
        select(models.Node).where(models.Node.version_id == version.version_id).order_by(models.Node.sort_key)
    ).scalars().all()
    return {"nodes": [NodeOut(**node.__dict__).model_dump() for node in nodes]}


@router.get("/node/{node_id}")
def node_detail(node_id: str, db: Session = Depends(get_db)):
    node = db.get(models.Node, node_id)
    if not node:
        return {"error": "not_found"}
    refs = db.execute(select(models.ReferenceExtracted).where(models.ReferenceExtracted.source_node_id == node_id)).scalars().all()
    resolved = db.execute(select(models.ReferenceResolved).where(models.ReferenceResolved.source_node_id == node_id)).scalars().all()
    return {
        "node": node.__dict__,
        "references_extracted": [r.__dict__ for r in refs],
        "references_resolved": [r.__dict__ for r in resolved],
    }


@router.get("/search")
def search(q: str, db: Session = Depends(get_db)):
    if db.bind and db.bind.dialect.name == "sqlite":
        rows = db.execute(select(models.Node).where(models.Node.text_clean.like(f"%{q}%"))).scalars().all()
        return {"results": [{"node_id": row.node_id, "text_clean": row.text_clean} for row in rows]}
    query = text("SELECT node_id, text_clean FROM nodes WHERE text_clean @@ plainto_tsquery(:q) LIMIT 20")
    results = db.execute(query, {"q": q}).fetchall()
    return {"results": [{"node_id": row[0], "text_clean": row[1]} for row in results]}


@router.post("/extract_references")
def extract_references_endpoint(payload: dict):
    text = payload.get("text", "")
    return {"references": extract_references(text)}
