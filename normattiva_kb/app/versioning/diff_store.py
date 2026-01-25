from __future__ import annotations

from dataclasses import dataclass

from diff_match_patch import diff_match_patch


@dataclass(frozen=True)
class DeltaResult:
    delta_text: str
    compression_ratio: float


def build_delta(base_text: str, updated_text: str) -> DeltaResult:
    dmp = diff_match_patch()
    diffs = dmp.diff_main(base_text, updated_text)
    dmp.diff_cleanupEfficiency(diffs)
    delta_text = dmp.diff_toDelta(diffs)
    ratio = _compression_ratio(base_text, delta_text)
    return DeltaResult(delta_text=delta_text, compression_ratio=ratio)


def apply_delta(base_text: str, delta_text: str) -> str:
    dmp = diff_match_patch()
    diffs = dmp.diff_fromDelta(base_text, delta_text)
    return dmp.diff_text2(diffs)


def _compression_ratio(base_text: str, delta_text: str) -> float:
    if not base_text:
        return 0.0
    return max(0.0, 1 - (len(delta_text) / len(base_text)))
