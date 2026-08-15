"""Immutable A05 promotion-commit operation models.

These models describe how A05 *asks* for a promotion commit and how it reads
the answer.  They carry canonical IDs and hashes only: an A05 caller never
restates an ActionIntent, CapabilityLease, PromotionDecision, or Passport body,
so no canonical artifact is duplicated here (EF4-I22).

The operation binding itself is not yet a canonical schema.  A strict draft is
staged at ``docs/v4_a05/proposed_contracts/`` and stays unregistered until a
product-owner decision raises the frozen canonical inventory; C01 owns that
contract.  Until then these dataclasses are an internal orchestration record,
not a claimed projection of a schema that does not exist.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from ...domain.hashing import hash_excluding, sha256_of_payload
from .registry import PROMOTION_COMMIT_CAPABILITY

#: The one canonical operation A05 may request.
COMMIT_OPERATION: Final = "commit_promotion"
#: The one capability that authorizes it, declared once in the gate registry.
COMMIT_CAPABILITY: Final = PROMOTION_COMMIT_CAPABILITY

#: Kernel dispositions plus the honest adapter state.  ``OUTCOME_UNKNOWN`` is
#: never a Kernel claim that a transaction committed; it only carries request
#: identity into reconciliation.
COMMITTED: Final = "COMMITTED"
EXISTING: Final = "EXISTING"
OUTCOME_UNKNOWN: Final = "OUTCOME_UNKNOWN"
COMMIT_DISPOSITIONS: Final = (COMMITTED, EXISTING, OUTCOME_UNKNOWN)
#: Dispositions that assert a durable, reconcilable transaction.
RESOLVED_DISPOSITIONS: Final = (COMMITTED, EXISTING)


@dataclass(frozen=True, slots=True)
class PromotionCommitRequest:
    """Sealed identity of one promotion-commit operation."""

    operation_id: str
    run_id: str
    node_id: str
    attempt: int
    action_intent_id: str
    action_intent_hash: str
    attempt_id: str
    capability_lease_id: str
    capability_lease_hash: str
    fencing_token: int
    principal_id: str
    resource_scopes: tuple[str, ...]
    promotion_pack_artifact_set_id: str
    promotion_pack_hash: str
    candidate_id: str
    expected_candidate_revision: int
    passport_id: str
    expected_passport_revision: int
    idempotency_key: str
    port_binding_id: str
    port_binding_hash: str
    request_hash: str

    def as_invocation(self) -> dict[str, Any]:
        """Project the canonical invocation binding."""

        return {
            "operation_id": self.operation_id,
            "operation": COMMIT_OPERATION,
            "run_id": self.run_id,
            "node_id": self.node_id,
            "attempt": self.attempt,
            "action_intent_id": self.action_intent_id,
            "action_intent_hash": self.action_intent_hash,
            "attempt_id": self.attempt_id,
            "capability_lease_id": self.capability_lease_id,
            "capability_lease_hash": self.capability_lease_hash,
            "fencing_token": self.fencing_token,
            "principal_id": self.principal_id,
            "capability": COMMIT_CAPABILITY,
            "resource_scopes": list(self.resource_scopes),
            "promotion_pack_artifact_set_id": self.promotion_pack_artifact_set_id,
            "promotion_pack_hash": self.promotion_pack_hash,
            "candidate_id": self.candidate_id,
            "expected_candidate_revision": self.expected_candidate_revision,
            "passport_id": self.passport_id,
            "expected_passport_revision": self.expected_passport_revision,
            "idempotency_key": self.idempotency_key,
            "port_binding_id": self.port_binding_id,
            "port_binding_hash": self.port_binding_hash,
            "request_hash": self.request_hash,
        }


def canonical_request_hash(invocation: Mapping[str, Any]) -> str:
    """Digest the whole invocation binding except its own hash field.

    The charter requires the canonical request hash to cover the entire
    canonical request, because that hash is what idempotent replay compares:
    the same key with a different request must conflict rather than return a
    prior result.  A hash the caller merely asserts cannot do that job, since
    one value could be attached to two different operations and each half
    would still look internally consistent.
    """

    return hash_excluding(dict(invocation), "request_hash")


def canonical_authorization_dispatch_hash(
    invocation: Mapping[str, Any], authorized_promotion_decision: Mapping[str, Any]
) -> str:
    """Digest the exact bytes A05 would authorize for Kernel dispatch.

    ``request_hash`` already seals the invocation.  This second digest also
    covers the derived PromotionDecision that travels with it, preventing a
    port result from binding only the request while leaving the actual
    authorized verdict mutable.  The current canonical port result has no
    ratified field for this digest, so A05 computes the binding definition but
    must not dispatch until C01/C03 ratify that result contract.
    """

    return sha256_of_payload(
        {
            **dict(invocation),
            "authorized_promotion_decision": dict(authorized_promotion_decision),
        }
    )


@dataclass(frozen=True, slots=True)
class PromotionCommitOutcome:
    """What the trusted port reported about one commit operation."""

    disposition: str
    operation_id: str
    request_hash: str
    port_binding_id: str
    port_binding_hash: str
    result: dict[str, Any]

    @property
    def resolved(self) -> bool:
        """True only when a durable transaction is claimed and bound."""

        return self.disposition in RESOLVED_DISPOSITIONS
