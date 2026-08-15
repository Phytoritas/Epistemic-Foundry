"""A05 promotion commit orchestration.

These are the executable entrypoints for the final commit phase of the
canonical 23-node ``evolution_promotion`` workflow.  A05 decides sequencing,
required evidence, expected revisions, request identity, and when G14 becomes
eligible.  Every authoritative effect - lease validity, fencing, the
compare-and-swap transaction, the ledger event, and the immutable lease-use
record - belongs to the Foundry Kernel behind the injected E05 port.

There is deliberately no in-memory fallback committer.  A fabricated commit is
indistinguishable from a real one once it reaches a receipt, so an unbound port
is a refusal, not a degraded mode.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any, Final

from ...contracts import ContractViolation
from ...contracts.validation import validate_artifact
from ...domain.hashing import hash_excluding, sha256_of_payload
from ..promotion import (
    PromotionRefused,
    PromotionRequest,
    decide_promotion,
    validate_promotion_decision_semantics,
)
from .cas import require_commit_outcome, require_commit_port, validate_commit_operation
from .errors import EvolutionAuthorityError
from .models import (
    COMMIT_CAPABILITY,
    COMMIT_OPERATION,
    OUTCOME_UNKNOWN,
    PromotionCommitOutcome,
    PromotionCommitRequest,
    canonical_request_hash,
)


def _payload(value: Mapping[str, Any], key: str) -> Any:
    if not isinstance(value, Mapping) or key not in value:
        raise EvolutionAuthorityError(
            "NODE_INPUT_INVALID", f"sealed node payload lacks {key}"
        )
    return value[key]


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvolutionAuthorityError(
            "NODE_INPUT_INVALID", f"{label} must be a non-empty string"
        )
    return value


def _revision(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EvolutionAuthorityError(
            "NODE_INPUT_INVALID", f"{label} must be a non-negative integer"
        )
    return value


#: Domain separator so this identifier can never collide with a digest that
#: some other record derives from the same idempotency key.
_DECISION_ID_DOMAIN: Final = "epistemic-foundry/a05/promotion-decision-id/v1"


def _stable_decision_id(idempotency_key: str) -> str:
    """Derive one promotion's decision ID from its idempotency key.

    The shared authority mints a random identifier per call, which is fine for
    a single execution but defeats the retry rule: the same key and the same
    request must return the existing logical result.  A retry that recomputed a
    fresh random ID would disagree with the identifier the Kernel already
    committed and reject its own successful transaction.  Deriving the ID from
    the sealed key makes the second look-up describe the same decision instead
    of a new one.
    """

    digest = sha256_of_payload(
        {"domain": _DECISION_ID_DOMAIN, "idempotency_key": idempotency_key}
    )
    return f"PD-{digest.split(':', 1)[1][:32]}"


def build_commit_request(payload: Mapping[str, Any]) -> PromotionCommitRequest:
    """Project the sealed node payload into one commit-operation identity."""

    scopes = _payload(payload, "resource_scopes")
    if isinstance(scopes, (str, bytes)) or not isinstance(scopes, (list, tuple)):
        raise EvolutionAuthorityError(
            "NODE_INPUT_INVALID", "resource_scopes must be a sequence"
        )
    resolved_scopes = tuple(
        _text(scope, f"resource_scopes[{index}]")
        for index, scope in enumerate(scopes)
    )
    if not resolved_scopes:
        raise EvolutionAuthorityError(
            "NODE_INPUT_INVALID", "a commit operation needs at least one resource scope"
        )
    attempt = _payload(payload, "attempt")
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
        raise EvolutionAuthorityError(
            "NODE_INPUT_INVALID", "attempt must be a positive integer"
        )
    fencing_token = _payload(payload, "fencing_token")
    if (
        isinstance(fencing_token, bool)
        or not isinstance(fencing_token, int)
        or fencing_token < 1
    ):
        raise EvolutionAuthorityError(
            "NODE_INPUT_INVALID", "fencing_token must be a positive integer"
        )
    draft = PromotionCommitRequest(
        operation_id=_text(_payload(payload, "operation_id"), "operation_id"),
        run_id=_text(_payload(payload, "run_id"), "run_id"),
        node_id=_text(_payload(payload, "node_id"), "node_id"),
        attempt=attempt,
        action_intent_id=_text(
            _payload(payload, "action_intent_id"), "action_intent_id"
        ),
        action_intent_hash=_text(
            _payload(payload, "action_intent_hash"), "action_intent_hash"
        ),
        attempt_id=_text(_payload(payload, "attempt_id"), "attempt_id"),
        capability_lease_id=_text(
            _payload(payload, "capability_lease_id"), "capability_lease_id"
        ),
        capability_lease_hash=_text(
            _payload(payload, "capability_lease_hash"), "capability_lease_hash"
        ),
        fencing_token=fencing_token,
        principal_id=_text(_payload(payload, "principal_id"), "principal_id"),
        resource_scopes=resolved_scopes,
        promotion_pack_artifact_set_id=_text(
            _payload(payload, "promotion_pack_artifact_set_id"),
            "promotion_pack_artifact_set_id",
        ),
        promotion_pack_hash=_text(
            _payload(payload, "promotion_pack_hash"), "promotion_pack_hash"
        ),
        candidate_id=_text(_payload(payload, "candidate_id"), "candidate_id"),
        expected_candidate_revision=_revision(
            _payload(payload, "expected_candidate_revision"),
            "expected_candidate_revision",
        ),
        passport_id=_text(_payload(payload, "passport_id"), "passport_id"),
        expected_passport_revision=_revision(
            _payload(payload, "expected_passport_revision"),
            "expected_passport_revision",
        ),
        idempotency_key=_text(
            _payload(payload, "idempotency_key"), "idempotency_key"
        ),
        port_binding_id=_text(
            _payload(payload, "port_binding_id"), "port_binding_id"
        ),
        port_binding_hash=_text(
            _payload(payload, "port_binding_hash"), "port_binding_hash"
        ),
        # Sealed below from the projected binding, never copied from input.
        request_hash="",
    )
    sealed = replace(
        draft, request_hash=canonical_request_hash(draft.as_invocation())
    )
    asserted = payload.get("request_hash")
    if asserted is not None and asserted != sealed.request_hash:
        # A caller may still state the hash it believes it is committing, but a
        # disagreement means the two sides describe different operations, and
        # idempotent replay compares exactly this value.
        raise EvolutionAuthorityError(
            "COMMIT_REQUEST_UNBOUND",
            "the supplied request_hash does not cover this commit invocation",
        )
    return sealed


def acquire_promotion_commit_lease(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Record the commit ActionIntent and acquire the short-lived lease.

    The lease is issued by the Kernel through the trusted port.  A lease object
    that merely satisfies its schema is not authority, so this node never
    accepts a caller-supplied lease as proof.
    """

    port = require_commit_port(
        _payload(payload, "port_binding_id"), _payload(payload, "port_binding_hash")
    )
    intent = dict(_payload(payload, "commit_action_intent"))
    try:
        validate_artifact("action-intent", intent)
    except ContractViolation as error:
        raise EvolutionAuthorityError("ACTION_INTENT_INVALID", str(error)) from error
    if intent["intent_hash"] != hash_excluding(intent, "intent_hash"):
        raise EvolutionAuthorityError(
            "ACTION_INTENT_HASH_MISMATCH",
            "the ActionIntent intent_hash does not match its canonical content",
        )
    if intent.get("action_type") != COMMIT_OPERATION:
        raise EvolutionAuthorityError(
            "ACTION_INTENT_INVALID",
            f"the lease node records action_type={COMMIT_OPERATION}",
        )
    if COMMIT_CAPABILITY not in tuple(intent.get("required_capabilities", ())):
        raise EvolutionAuthorityError(
            "ACTION_INTENT_INVALID",
            f"the commit intent must require {COMMIT_CAPABILITY}",
        )

    granted = port.acquire_commit_lease(
        {
            "action_intent_id": intent["intent_id"],
            "action_intent_hash": intent["intent_hash"],
            "run_id": intent["run_id"],
            "node_id": intent["node_id"],
            "capability": COMMIT_CAPABILITY,
            "idempotency_key": intent["idempotency_key"],
        }
    )
    if not isinstance(granted, Mapping):
        raise EvolutionAuthorityError(
            "CAPABILITY_LEASE_INVALID", "the commit port must return a lease object"
        )
    lease = dict(granted)
    try:
        validate_artifact("capability-lease", lease)
    except ContractViolation as error:
        raise EvolutionAuthorityError("CAPABILITY_LEASE_INVALID", str(error)) from error
    if lease["lease_hash"] != hash_excluding(lease, "lease_hash"):
        raise EvolutionAuthorityError(
            "LEASE_HASH_MISMATCH",
            "the CapabilityLease lease_hash does not match its canonical content",
        )
    if COMMIT_CAPABILITY not in tuple(lease.get("capabilities", ())):
        raise EvolutionAuthorityError(
            "CAPABILITY_LEASE_INVALID",
            f"the issued lease does not carry {COMMIT_CAPABILITY}",
        )
    if lease.get("revoked"):
        raise EvolutionAuthorityError(
            "CAPABILITY_LEASE_INVALID", "a revoked lease cannot authorize a commit"
        )
    return lease


def commit_outcome(
    payload: Mapping[str, Any], *, decision: Mapping[str, Any] | None = None
) -> PromotionCommitOutcome:
    """Invoke the Kernel lease-protected transaction through the trusted port.

    Returns the typed outcome, including an unresolved one.  Callers that must
    decide whether the chain may continue use this; the workflow node below
    refuses to report an unresolved dispatch as a completed commit.

    When the caller has already derived the authorized verdict, it is sent with
    the invocation so the Kernel commits that exact decision.
    """

    _raise_unratified_commit_split()
    request = build_commit_request(payload)
    port = require_commit_port(request.port_binding_id, request.port_binding_hash)
    invocation = request.as_invocation()
    validate_commit_operation(invocation, None)
    authorized = (
        dict(decision) if decision is not None else derive_promotion_decision(payload)
    )
    dispatch = {**invocation, "authorized_promotion_decision": authorized}
    return require_commit_outcome(request, port.commit_promotion(dispatch))


def _raise_unratified_commit_split() -> None:
    """Refuse effects until C01/C03 bind authorization and G14 independently.

    The canonical port result can bind ``request_hash`` but has no ratified
    field for the authorization/dispatch digest that also covers the derived
    PromotionDecision.  Dispatching now would therefore leave the bytes that
    actually authorize the effect unbound.  The same unresolved C01/C03 split
    makes the commit authority part of the G14 completion proof it would be
    helping to certify.  A05 may acquire a lease, but it cannot call the commit
    port until both contracts are ratified.
    """

    raise EvolutionAuthorityError(
        "SPEC_GAP",
        "G14 authority circularity and the C01/C03 authorization-dispatch "
        "result binding are not ratified; A05 refuses commit port dispatch",
    )


def derive_promotion_decision(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Compute the PromotionDecision from sealed inputs, never accept one.

    This is A05's own deterministic authority and the reason the commit node
    cannot be handed a verdict.  A supplied decision that merely satisfies the
    schema is internally self-consistent: nothing in the document constrains
    where its ``promotion_ceiling`` or ``hard_gate_status`` came from, and its
    self-hash is computed over whatever was supplied.  Recomputing the grant
    from the sealed request is what keeps gates, ceilings, and the replication
    limit binding rather than advisory.

    A caller may still pass ``promotion_decision`` as a cross-check; if it
    disagrees with the derived verdict, the commit is refused instead of
    silently preferring either one.
    """

    request = _payload(payload, "promotion_request")
    if not isinstance(request, PromotionRequest):
        raise EvolutionAuthorityError(
            "NODE_INPUT_INVALID",
            "promotion_request must be a sealed PromotionRequest",
        )
    # The sealed promotion request and the commit operation must describe the
    # same work.  Without this, two different packs, intents, or idempotency
    # keys could be spliced into one commit and each half would look valid.
    operation = build_commit_request(payload)
    for label, sealed, operational in (
        ("candidate_id", request.candidate_id, operation.candidate_id),
        (
            "candidate_revision",
            request.candidate_revision,
            operation.expected_candidate_revision,
        ),
        (
            "promotion_pack_hash",
            request.promotion_pack_hash,
            operation.promotion_pack_hash,
        ),
        (
            "commit_action_intent_id",
            request.commit_action_intent_id,
            operation.action_intent_id,
        ),
        ("idempotency_key", request.idempotency_key, operation.idempotency_key),
    ):
        if sealed != operational:
            raise EvolutionAuthorityError(
                "COMMIT_REQUEST_UNBOUND",
                f"the sealed PromotionRequest and the commit operation disagree "
                f"on {label}",
            )
    try:
        decision = decide_promotion(request)
    except PromotionRefused as error:
        raise EvolutionAuthorityError("PROMOTION_REFUSED", str(error)) from error
    # Normalize the freshly minted random identifier to one derived from the
    # sealed idempotency key, then reseal, so a retry of the same promotion
    # recognizes the decision the Kernel already committed.  This happens
    # before any semantic validation or external record, so the verdict itself
    # is still entirely the shared authority's.
    decision["decision_id"] = _stable_decision_id(request.idempotency_key)
    decision["decision_hash"] = hash_excluding(decision, "decision_hash")
    current_level = _payload(payload, "current_level")
    try:
        validate_promotion_decision_semantics(decision, current_level=str(current_level))
    except PromotionRefused as error:
        raise EvolutionAuthorityError("PROMOTION_REFUSED", str(error)) from error
    asserted = payload.get("promotion_decision")
    if asserted is not None and dict(asserted) != decision:
        raise EvolutionAuthorityError(
            "PROMOTION_DECISION_INVALID",
            "the supplied PromotionDecision does not match the decision derived "
            "from sealed gate evidence",
        )
    return decision


def commit_promotion_atomically(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Execute the commit node.

    Authority is computed before the effect, never after.  Deriving the verdict
    first means a refused promotion is never dispatched; deriving it afterwards
    would leave the Kernel holding a committed transaction that the gates had
    already rejected, which is worse than a clean refusal.

    An unresolved dispatch is also not a completed node.  Reporting it as one
    would let the workflow advance past a transaction nobody has confirmed, so
    the node fails closed and the operation must be reconciled by its bound
    identity instead.
    """

    _raise_unratified_commit_split()
    request = build_commit_request(payload)
    decision = derive_promotion_decision(payload)
    if decision.get("candidate_id") != request.candidate_id:
        raise EvolutionAuthorityError(
            "COMMIT_RESULT_UNBOUND",
            "the PromotionDecision targets a different candidate",
        )
    if decision.get("candidate_revision") != request.expected_candidate_revision:
        raise EvolutionAuthorityError(
            "COMMIT_RESULT_UNBOUND",
            "the PromotionDecision targets a different candidate revision",
        )

    # The authorized decision travels with the dispatch, so the Kernel commits
    # the exact verdict A05 derived rather than one it had to guess.
    outcome = commit_outcome(payload, decision=decision)
    if not outcome.resolved:
        raise EvolutionAuthorityError(
            "COMMIT_OUTCOME_UNKNOWN",
            "the commit dispatch did not resolve; reconcile operation "
            f"{outcome.operation_id!r} before continuing",
        )
    if decision.get("decision_id") != outcome.result.get("promotion_decision_id"):
        raise EvolutionAuthorityError(
            "COMMIT_RESULT_UNBOUND",
            "the committed transaction does not resolve this PromotionDecision",
        )
    if decision.get("decision_hash") != outcome.result.get("promotion_decision_hash"):
        raise EvolutionAuthorityError(
            "COMMIT_RESULT_UNBOUND",
            "the committed transaction bound different PromotionDecision bytes",
        )
    return decision


__all__ = [
    "OUTCOME_UNKNOWN",
    "acquire_promotion_commit_lease",
    "build_commit_request",
    "commit_outcome",
    "commit_promotion_atomically",
    "derive_promotion_decision",
]
