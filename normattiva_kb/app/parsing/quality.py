from __future__ import annotations

from collections import Counter


def quality_metrics(nodes: list[dict]) -> dict:
    counts = Counter(node["node_type"] for node in nodes)
    empty_nodes = [node for node in nodes if not node.get("text_clean")]
    return {
        "counts": dict(counts),
        "empty_nodes": len(empty_nodes),
        "total_nodes": len(nodes),
    }
