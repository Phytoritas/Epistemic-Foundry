"""Memory recall scoping and workspace isolation.

* EF4-I18: recall occurs only within allowed memory classes, purpose, consent,
  retention, and workspace scope.
* EF4-I19: cross-workspace state, memory, and artifacts are denied by default
  below the model layer. "Below the model layer" matters — the enforcement is in
  the retrieval path, not in a prompt asking the model to behave.
"""

from __future__ import annotations

from .policy import (
    MemoryScopeViolation,
    build_memory_policy,
    build_retrieval_receipt,
    require_recall_permitted,
)

__all__ = [
    "MemoryScopeViolation",
    "build_memory_policy",
    "build_retrieval_receipt",
    "require_recall_permitted",
]
