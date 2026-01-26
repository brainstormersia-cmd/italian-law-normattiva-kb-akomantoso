from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Iterable

from app.db import models


@dataclass(frozen=True)
class ConflictCandidate:
    doc_id: str
    canonical_path: str
    node_id_a: str
    node_id_b: str
    version_id_a: int
    version_id_b: int
    valid_from_a: dt.date | None
    valid_to_a: dt.date | None
    valid_from_b: dt.date | None
    valid_to_b: dt.date | None
    severity: str


def detect_temporal_conflicts(nodes: Iterable[models.Node]) -> list[ConflictCandidate]:
    conflicts: list[ConflictCandidate] = []
    current_doc = None
    current_path = None
    active: list[tuple[dt.date, models.Node]] = []

    for node in nodes:
        if (node.doc_id, node.canonical_path) != (current_doc, current_path):
            current_doc = node.doc_id
            current_path = node.canonical_path
            active = []

        node_start = node.valid_from or dt.date.min
        node_end = node.valid_to or dt.date.max

        active = [(end, active_node) for end, active_node in active if end >= node_start]

        for end, active_node in active:
            if _ranges_overlap(
                active_node.valid_from,
                active_node.valid_to,
                node.valid_from,
                node.valid_to,
            ):
                severity = _severity_for_overlap(active_node, node)
                conflicts.append(
                    ConflictCandidate(
                        doc_id=node.doc_id,
                        canonical_path=node.canonical_path,
                        node_id_a=active_node.node_id,
                        node_id_b=node.node_id,
                        version_id_a=active_node.version_id,
                        version_id_b=node.version_id,
                        valid_from_a=active_node.valid_from,
                        valid_to_a=active_node.valid_to,
                        valid_from_b=node.valid_from,
                        valid_to_b=node.valid_to,
                        severity=severity,
                    )
                )

        active.append((node_end, node))

    return conflicts


def _ranges_overlap(
    start_a: dt.date | None,
    end_a: dt.date | None,
    start_b: dt.date | None,
    end_b: dt.date | None,
) -> bool:
    start_a_val = start_a or dt.date.min
    end_a_val = end_a or dt.date.max
    start_b_val = start_b or dt.date.min
    end_b_val = end_b or dt.date.max
    return start_a_val <= end_b_val and start_b_val <= end_a_val


def _severity_for_overlap(node_a: models.Node, node_b: models.Node) -> str:
    if node_a.is_current_law and node_b.is_current_law:
        return "critical"
    if node_a.valid_to is None and node_b.valid_to is None:
        return "critical"
    return "warning"
