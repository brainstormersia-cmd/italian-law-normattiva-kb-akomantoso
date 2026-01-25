from __future__ import annotations

import re
from typing import Optional

from normativa_processor.chunking.overlap import add_overlap
from normativa_processor.chunking.tokenizer import estimate_tokens_accurate
from normativa_processor.core.config import ProcessingConfig
from normativa_processor.core.models import ArticleSection
from normativa_processor.parsing.hierarchy_parser import extract_subsection_label, split_by_subsections
from normativa_processor.parsing.reference_parser import extract_cross_references, extract_references
from normativa_processor.parsing.metadata_parser import extract_dates
from normativa_processor.rag.fields_builder import build_rag_fields
from normativa_processor.rag.summarizer import summarize_advanced
from normativa_processor.rag.tagger import extract_tags


def build_chunk_id(doc_slug: str, article_id: str, index: int) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", article_id.lower()).strip("_")
    return f"{doc_slug}_{slug}_{index}"


def normalize_subsection_label(label: str) -> str:
    lowered = label.lower()
    lowered = lowered.replace("co.", "comma").replace("c.", "comma")
    if re.match(r"^[a-z]\)", lowered):
        lowered = f"lettera {lowered}"
    return lowered.strip()


def build_citation_key(section: ArticleSection, context: dict, subsection: Optional[str]) -> str:
    doc_title = context.get("doc_citation") or context.get("title", "Documento")
    base = f"{doc_title} {section.article_id}"
    if subsection:
        base += f" {normalize_subsection_label(subsection)}"
    return base.strip()


def split_long_chunk(chunk: str, target_tokens: int) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", chunk)
    parts = []
    current = ""
    for sentence in sentences:
        if not current:
            current = sentence
            continue
        if estimate_tokens_accurate(current + " " + sentence) <= target_tokens:
            current = f"{current} {sentence}"
        else:
            parts.append(current)
            current = sentence
    if current:
        parts.append(current)
    return parts


def extract_effective_date(text: str) -> Optional[str]:
    lowered = text.lower()
    phrases = [
        "entra in vigore",
        "vigore dal",
        "ha effetto dal",
        "a decorrere dal",
        "con effetto dal",
        "dal giorno successivo",
    ]
    for phrase in phrases:
        if phrase in lowered:
            snippet = text[lowered.index(phrase) : lowered.index(phrase) + 120]
            dates = extract_dates(snippet)
            return dates[0] if dates else None
    return None


def prepend_context(section: ArticleSection, chunk: str, citation_key: str) -> str:
    hierarchy_text = " > ".join(section.hierarchy) if section.hierarchy else ""
    reform = ", ".join(extract_references(chunk)) or "nessuno"
    cross_refs = extract_cross_references(chunk)
    cross_text = ", ".join(f"{ref['ref_type']}: {ref['target']}" for ref in cross_refs) or "nessuno"
    effective_date = extract_effective_date(chunk) or "null"
    header = (
        f"Citazione normativa: {citation_key} - Titolo sezione: {section.section_title} - "
        f"Gerarchia: {hierarchy_text} - Riferimenti: {reform} - "
        f"Rinvii: {cross_text} - Data vigore: {effective_date}\n[Testo:] "
    )
    return f"{header}{chunk}".strip()


def split_into_chunks(
    section: ArticleSection,
    doc_slug: str,
    context: dict,
    config: ProcessingConfig,
    summary_strategy: str,
) -> list[dict]:
    text = section.text
    units = split_by_subsections(text)
    chunks: list[str] = []
    current = ""
    for unit in units:
        if not current:
            current = unit
            continue
        if estimate_tokens_accurate(current + "\n\n" + unit) <= config.target_chunk_tokens:
            current = f"{current}\n\n{unit}"
        else:
            chunks.append(current)
            current = unit
    if current:
        chunks.append(current)

    normalized_chunks: list[str] = []
    for chunk in chunks:
        if estimate_tokens_accurate(chunk) > config.max_chunk_tokens:
            normalized_chunks.extend(split_long_chunk(chunk, config.target_chunk_tokens))
        else:
            normalized_chunks.append(chunk)

    final_chunks: list[dict] = []
    for idx, chunk in enumerate(normalized_chunks, start=1):
        chunk_text = add_overlap(normalized_chunks, idx - 1, config.overlap_ratio)
        subsection = extract_subsection_label(chunk_text)
        citation_key = build_citation_key(section, context, subsection)
        chunk_text = prepend_context(section, chunk_text, citation_key)
        reform_refs = extract_references(chunk_text)
        cross_refs = extract_cross_references(chunk_text)
        tags = extract_tags(chunk_text, context.get("nlp"))
        summary_50 = summarize_advanced(chunk_text, citation_key, 50, tags, summary_strategy)
        summary_150 = summarize_advanced(chunk_text, citation_key, 150, tags, summary_strategy)
        token_est = estimate_tokens_accurate(chunk_text)
        rag_fields = build_rag_fields(
            citation_key,
            tags,
            summary_50,
            summary_150,
            context,
            reform_refs,
            cross_refs,
            extract_effective_date(chunk_text),
        )

        final_chunks.append(
            {
                "chunk_id": build_chunk_id(doc_slug, section.article_id, idx),
                "citation_key": citation_key,
                "article_id": section.article_id,
                "section_title": section.section_title,
                "parent_hierarchy": section.hierarchy,
                "reform_references": reform_refs,
                "cross_references": cross_refs,
                "effective_date": extract_effective_date(chunk_text),
                "tags": tags,
                "full_chunk_text": chunk_text,
                "summary_50": summary_50,
                "summary_150": summary_150,
                "token_estimate": token_est,
                "rag_optimized_fields": rag_fields,
            }
        )
    return final_chunks
