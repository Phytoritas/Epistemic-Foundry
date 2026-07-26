"""Optional, pinned, fail-closed ShinkaEvolve backend adapter.

MASTER_EXECUTION_PROMPT section 9: use ShinkaEvolve only through the adapter
contract. Pin an exact revision/digest, record Apache-2.0 obligations, map every
backend event to Foundry artifacts, and qualify semantic equivalence. Backend
scores, novelty, archive, islands, lineage, and bandit state are search signals,
never promotion authority. On missing capability or ambiguous mapping, fail
closed.

`fail closed` is the whole point: an unqualified or ambiguously mapped backend
must stop the run, not degrade into a best-effort translation whose outputs look
like Foundry evidence.
"""

from __future__ import annotations

from .backend import (
    BackendNotQualified,
    UnmappableBackendSignal,
    ADVISORY_BACKEND_SIGNALS,
    build_backend_manifest,
    build_qualification,
    map_backend_signals,
)

__all__ = [
    "ADVISORY_BACKEND_SIGNALS",
    "BackendNotQualified",
    "UnmappableBackendSignal",
    "build_backend_manifest",
    "build_qualification",
    "map_backend_signals",
]
