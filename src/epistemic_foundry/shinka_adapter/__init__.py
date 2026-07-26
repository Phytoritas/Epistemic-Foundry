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

EF4-I63 adds the boundary itself: the Foundry runs without any backend, a RunSpec
may not declare one required, and imported backend state is a translation record
rather than Foundry history.
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
from .isolation import (
    FOUNDRY_AUTHORITY_SURFACES,
    BackendAuthorityRefused,
    foundry_runs_without_backend,
    import_backend_state,
    imported_state_is_authoritative,
    require_no_authority_routing,
    require_optional,
)

__all__ = [
    "ADVISORY_BACKEND_SIGNALS",
    "BackendAuthorityRefused",
    "BackendNotQualified",
    "FOUNDRY_AUTHORITY_SURFACES",
    "UnmappableBackendSignal",
    "build_backend_manifest",
    "build_qualification",
    "foundry_runs_without_backend",
    "import_backend_state",
    "imported_state_is_authoritative",
    "map_backend_signals",
    "require_no_authority_routing",
    "require_optional",
]
