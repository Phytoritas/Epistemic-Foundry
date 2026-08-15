"""Memory recall scoping and workspace isolation.

* EF4-I18: recall occurs only within allowed memory classes, purpose, consent,
  retention, and workspace scope.
* EF4-I19: cross-workspace state, memory, and artifacts are denied by default
  below the model layer. "Below the model layer" matters — the enforcement is in
  the retrieval path, not in a prompt asking the model to behave.
* EF4-I20: compaction and resume context is rebuilt from hash-bound canonical
  artifacts with exclusions and freshness, so a resumed session cannot continue
  from a summary of a state that has since changed.
"""

from __future__ import annotations

from .capsule import (
    CapsuleRefused,
    CapsuleStale,
    build_context_capsule,
    capsule_is_fresh,
    require_rebuildable,
    stale_artifact_ids,
)
from .policy import (
    MemoryScopeViolation,
    build_memory_policy,
    build_retrieval_receipt,
    require_recall_permitted,
)

__all__ = [
    "CapsuleRefused",
    "CapsuleStale",
    "MemoryScopeViolation",
    "build_context_capsule",
    "build_memory_policy",
    "build_retrieval_receipt",
    "capsule_is_fresh",
    "require_recall_permitted",
    "require_rebuildable",
    "stale_artifact_ids",
]
