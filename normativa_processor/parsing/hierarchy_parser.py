from __future__ import annotations

import re
from typing import Optional

from normativa_processor.core.models import ArticleSection
from normativa_processor.core.types import NLPModelType

HIERARCHY_PATTERNS = {
    "titolo": re.compile(r"^Titolo\s+[IVXLC\d]+", re.IGNORECASE),
    "capo": re.compile(r"^Capo\s+[IVXLC\d]+", re.IGNORECASE),
    "sezione": re.compile(r"^Sezione\s+[\w\d\-]+", re.IGNORECASE),
    "articolo": re.compile(r"^(Articolo|Art\.|Art)\s*(\d+[\w\-]*)", re.IGNORECASE),
    "comma": re.compile(r"^(Comma|co\.|c\.)\s*(\d+[\w\-]*)", re.IGNORECASE),
    "lettera": re.compile(r"^[a-z]\)", re.IGNORECASE),
    "punto": re.compile(r"^(Punto|Punto\s+|punto\s+)?\d+(\.\d+)*\)", re.IGNORECASE),
    "numero": re.compile(r"^numero\s*\d+", re.IGNORECASE),
    "tabella": re.compile(r"^Tabella\s+\d+", re.IGNORECASE),
    "allegato": re.compile(r"^Allegato\s+[A-Z0-9]+", re.IGNORECASE),
    "annesso": re.compile(r"^Annesso\s+[A-Z0-9IVXLC]+", re.IGNORECASE),
    "disposizioni_finali": re.compile(r"^Disposizioni\s+finali", re.IGNORECASE),
    "abrogazioni": re.compile(r"^Abrogazioni", re.IGNORECASE),
}


def parse_hierarchy(text: str, nlp: NLPModelType) -> tuple[list[ArticleSection], list[str]]:
    stack: list[str] = []
    sections: list[ArticleSection] = []
    current_article_id = ""
    current_title = ""
    current_lines: list[str] = []
    warnings: list[str] = []
    current_is_annex = False

    def flush_article() -> None:
        nonlocal current_article_id, current_title, current_lines, current_is_annex
        if current_article_id and current_lines:
            sections.append(
                ArticleSection(
                    article_id=current_article_id,
                    section_title=current_title,
                    hierarchy=list(stack),
                    text="\n".join(current_lines).strip(),
                    is_annex=current_is_annex,
                )
            )
        current_article_id = ""
        current_title = ""
        current_lines = []
        current_is_annex = False

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            if current_lines:
                current_lines.append("")
            continue

        matched = False
        for level, pattern in HIERARCHY_PATTERNS.items():
            match = pattern.match(line)
            if not match:
                continue
            matched = True
            if level in {"titolo", "capo", "sezione", "disposizioni_finali", "abrogazioni"}:
                flush_article()
                stack = adjust_stack(stack, level, line)
            elif level in {"allegato", "annesso", "tabella"}:
                flush_article()
                stack = adjust_stack(stack, level, line)
                current_is_annex = True
                current_article_id = line
                current_title = line
                current_lines.append(line)
            elif level == "articolo":
                flush_article()
                current_article_id = f"Art. {match.group(2)}"
                current_title = line
                current_lines.append(line)
            elif level in {"comma", "lettera", "punto", "numero"}:
                if current_article_id:
                    current_lines.append(line)
                else:
                    current_article_id = "Preambolo"
                    current_title = "Preambolo"
                    current_lines = [line]
            break

        if matched:
            continue

        if current_lines:
            current_lines.append(line)
        else:
            current_article_id = "Preambolo"
            current_title = "Preambolo"
            current_lines = [line]

    flush_article()
    if not sections:
        warnings.append("Possibile allegato non parsificato")

    if nlp is not None:
        for section in sections:
            if "Art." not in section.article_id and "Articolo" in section.section_title:
                warnings.append(f"Sezione ambigua: {section.section_title}")
    return sections, warnings


def adjust_stack(stack: list[str], level: str, line: str) -> list[str]:
    order = [
        "titolo",
        "capo",
        "sezione",
        "disposizioni_finali",
        "abrogazioni",
        "allegato",
        "annesso",
        "tabella",
    ]
    if level not in order:
        return stack
    idx = order.index(level)
    new_stack = stack[:idx]
    new_stack.append(line)
    return new_stack


def is_subsection_marker(line: str) -> bool:
    markers = [
        HIERARCHY_PATTERNS["comma"],
        HIERARCHY_PATTERNS["lettera"],
        HIERARCHY_PATTERNS["punto"],
        HIERARCHY_PATTERNS["numero"],
    ]
    return any(pattern.match(line) for pattern in markers)


def split_by_subsections(text: str) -> list[str]:
    lines = text.splitlines()
    units: list[str] = []
    current: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            current.append("")
            continue
        if is_subsection_marker(stripped) and current:
            units.append("\n".join(current).strip())
            current = [stripped]
        else:
            current.append(stripped)
    if current:
        units.append("\n".join(current).strip())
    if not units:
        return [text]
    return units


def extract_subsection_label(text: str) -> Optional[str]:
    for line in text.splitlines():
        if HIERARCHY_PATTERNS["comma"].match(line):
            return line
        if HIERARCHY_PATTERNS["lettera"].match(line):
            return line
        if HIERARCHY_PATTERNS["punto"].match(line):
            return line
        if HIERARCHY_PATTERNS["numero"].match(line):
            return line
    return None
