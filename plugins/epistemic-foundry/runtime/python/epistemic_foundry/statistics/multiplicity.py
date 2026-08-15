"""Multiple-testing adjustment.

Contract source: `schemas/multiple-testing-adjustment.schema.json`.

`effective_test_count` is deliberately not just the raw count. Correlated tests
carry less independent information than their number suggests, so treating fifty
correlated tests as fifty independent ones over-corrects and buries a real effect,
while treating them as one under-corrects and admits noise. The effective count
interpolates by correlation and is clamped to `[1, raw]` so it can never exceed
the tests actually run.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..contracts import validate_artifact
from ..domain.hashing import hash_excluding
from ..domain.ids import new_id


def effective_test_count(raw_test_count: int, mean_correlation: float = 0.0) -> int:
    """Independent-equivalent number of tests.

    At zero correlation this is the raw count; at perfect correlation it is one.
    Clamped to `[1, raw_test_count]`, because an effective count above the number
    of tests run would correct for comparisons nobody made.
    """
    if raw_test_count < 1:
        raise ValueError("raw_test_count must be at least 1")
    correlation = min(max(mean_correlation, 0.0), 1.0)
    effective = 1 + (raw_test_count - 1) * (1.0 - correlation)
    return int(min(max(round(effective), 1), raw_test_count))


def build_multiplicity_adjustment(
    *,
    family_id: str,
    method: str,
    raw_test_count: int,
    target_error_rate: float,
    adjusted_results: Sequence[Mapping[str, Any]],
    assumptions: Sequence[str],
    mean_correlation: float = 0.0,
    adjustment_id: str | None = None,
) -> dict[str, Any]:
    """Record a multiplicity adjustment over one test family.

    `assumptions` is required: every correction method rests on assumptions about
    dependence, and an unstated assumption cannot be checked by a reviewer.
    """
    if not assumptions:
        raise ValueError(
            "a multiplicity adjustment must state its assumptions; every method rests on a "
            "dependence assumption a reviewer needs to check"
        )
    if not 0.0 < target_error_rate < 1.0:
        raise ValueError("target_error_rate must lie strictly between 0 and 1")

    adjustment: dict[str, Any] = {
        "adjustment_id": adjustment_id or new_id("MTA"),
        "family_id": family_id,
        "method": method,
        "raw_test_count": int(raw_test_count),
        "effective_test_count": effective_test_count(raw_test_count, mean_correlation),
        "target_error_rate": float(target_error_rate),
        "adjusted_results": [dict(result) for result in adjusted_results],
        "assumptions": list(assumptions),
    }
    adjustment["adjustment_hash"] = hash_excluding(adjustment, "adjustment_hash")
    validate_artifact("multiple-testing-adjustment", adjustment)
    return adjustment
