"""Memory policy evaluation and retrieval receipts.

Contract sources: `schemas/memory-policy.schema.json` and
`schemas/memory-retrieval-receipt.schema.json`.

`require_recall_permitted` is the enforcement point. It checks class membership,
retention window, consent, purpose, and workspace in one place so a caller
cannot satisfy three of five conditions and proceed. Cross-workspace recall is
denied unless the policy explicitly permits it, and `EXPLICIT_ONLY` additionally
requires the caller to name the foreign workspace rather than reaching it by
omission.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..contracts import validate_artifact
from ..domain.hashing import hash_excluding, sha256_of_payload
from ..domain.ids import new_id
from ..domain.time import utc_now_iso


class MemoryScopeViolation(PermissionError):
    """A recall request falls outside its permitted scope."""


#: Canonical memory classes from `memory-policy.schema.json`. Named here so a
#: caller does not invent a plausible-sounding class the policy cannot express.
MEMORY_CLASSES: tuple[str, ...] = (
    "EPHEMERAL",
    "SESSION",
    "WORKSPACE",
    "USER",
    "EVIDENCE",
    "REGULATED",
)


def build_memory_policy(
    *,
    workspace_id: str,
    allowed_classes: Sequence[str],
    default_retention_days: int,
    class_rules: Sequence[Mapping[str, Any]],
    effective_at: str,
    cross_workspace_retrieval: str = "DENY",
    policy_id: str | None = None,
) -> dict[str, Any]:
    """Seal a workspace memory policy.

    An empty `allowed_classes` list is refused: a policy that permits nothing is
    almost always a construction bug, and treating it as "deny all" would hide
    the misconfiguration behind correct-looking behavior.
    """
    if not allowed_classes:
        raise MemoryScopeViolation(
            "a memory policy must list at least one allowed class; an empty list is a "
            "construction bug rather than a deny-all policy"
        )
    if default_retention_days < 0:
        raise MemoryScopeViolation("default_retention_days cannot be negative")
    unknown = sorted(set(allowed_classes) - set(MEMORY_CLASSES))
    if unknown:
        raise MemoryScopeViolation(
            f"unknown memory class(es) {unknown}; the policy can only express "
            f"{list(MEMORY_CLASSES)}"
        )

    policy: dict[str, Any] = {
        "policy_id": policy_id or new_id("MP"),
        "workspace_id": workspace_id,
        "allowed_classes": list(allowed_classes),
        "default_retention_days": int(default_retention_days),
        "class_rules": [dict(rule) for rule in class_rules],
        "cross_workspace_retrieval": cross_workspace_retrieval,
        "effective_at": effective_at,
    }
    policy["policy_hash"] = hash_excluding(policy, "policy_hash")
    validate_artifact("memory-policy", policy)
    return policy


def require_recall_permitted(
    policy: Mapping[str, Any],
    *,
    workspace_id: str,
    requested_classes: Sequence[str],
    purpose: str,
    consent_id: str | None,
    age_days: int = 0,
    target_workspace_id: str | None = None,
) -> None:
    """Raise `MemoryScopeViolation` unless every scope condition holds.

    All five conditions are checked together. Splitting them across call sites is
    how a recall path ends up honoring classes but ignoring retention.
    """
    if not purpose.strip():
        raise MemoryScopeViolation(
            "recall requires a stated purpose; purpose-free retrieval cannot be scoped or audited"
        )
    if not consent_id:
        raise MemoryScopeViolation(
            "recall requires a consent id; retrieving without recorded consent is out of scope "
            "regardless of class permissions"
        )

    allowed = set(policy["allowed_classes"])
    forbidden = sorted(set(requested_classes) - allowed)
    if forbidden:
        raise MemoryScopeViolation(
            f"memory class(es) {forbidden} are not in the policy allowed set for workspace "
            f"{policy['workspace_id']}"
        )

    retention = int(policy["default_retention_days"])
    if age_days > retention:
        raise MemoryScopeViolation(
            f"requested memory is {age_days} days old, beyond the {retention}-day retention "
            "window; expired memory is out of scope even for an allowed class"
        )

    effective_target = target_workspace_id or workspace_id
    if effective_target != policy["workspace_id"]:
        mode = str(policy["cross_workspace_retrieval"])
        if mode == "DENY":
            raise MemoryScopeViolation(
                f"cross-workspace recall from {policy['workspace_id']} to {effective_target} is "
                "denied by policy"
            )
        if mode == "EXPLICIT_ONLY" and target_workspace_id is None:
            raise MemoryScopeViolation(
                "cross-workspace recall requires the foreign workspace to be named explicitly; "
                "reaching it by omission is denied"
            )


def build_retrieval_receipt(
    *,
    query: str,
    workspace_id: str,
    purpose: str,
    searched_classes: Sequence[str],
    excluded_classes: Sequence[str],
    hits: Sequence[Mapping[str, Any]] | int,
    consent_id: str,
    context_capsule_id: str,
    redaction_count: int = 0,
    receipt_id: str | None = None,
    retrieved_at: str | None = None,
) -> dict[str, Any]:
    """Record what a recall actually searched, excluded, and returned.

    `excluded_classes` is recorded alongside `searched_classes` so a reader can
    see the boundary of the search rather than only its yield.
    """
    receipt: dict[str, Any] = {
        "receipt_id": receipt_id or new_id("MRR"),
        "query": query,
        "workspace_id": workspace_id,
        "purpose": purpose,
        "searched_classes": list(searched_classes),
        "excluded_classes": list(excluded_classes),
        "hits": hits if isinstance(hits, int) else [dict(hit) for hit in hits],
        "redaction_count": int(redaction_count),
        "consent_id": consent_id,
        "context_capsule_id": context_capsule_id,
        "retrieved_at": retrieved_at or utc_now_iso(),
    }
    receipt["result_hash"] = sha256_of_payload(
        {key: value for key, value in receipt.items() if key != "result_hash"}
    )
    validate_artifact("memory-retrieval-receipt", receipt)
    return receipt
