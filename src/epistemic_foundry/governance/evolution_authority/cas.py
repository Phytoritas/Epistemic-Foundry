"""The A05 provider-neutral promotion-commit port.

A05 declares what a promotion commit *is*; it never decides that a lease is
authoritative and never persists anything.  The concrete adapter that composes
E02 effects, E03 leases, and the Foundry Kernel lease-protected transaction is
owned by E05 and injected here.  Without a trusted binding this module fails
closed: there is no in-memory fallback committer, because a fabricated commit
would be indistinguishable from a real one to every downstream receipt.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Final, Protocol, runtime_checkable

from .errors import EvolutionAuthorityError
from .models import (
    COMMIT_CAPABILITY,
    COMMIT_OPERATION,
    COMMIT_DISPOSITIONS,
    OUTCOME_UNKNOWN,
    RESOLVED_DISPOSITIONS,
    PromotionCommitOutcome,
    PromotionCommitRequest,
)
from ...domain.hashing import hash_excluding

#: Canonical contract kind for the operation binding.  The strict schema is
#: proposed at ``docs/v4_a05/proposed_contracts/promotion-commit-operation.schema.json``
#: and is not yet registered, because raising the canonical schema inventory
#: requires an explicit product-owner decision (see R71/R99).  Until C01
#: ratifies it, this module validates the binding structurally and refuses to
#: pretend a canonical contract already governs it.
COMMIT_OPERATION_KIND = "promotion-commit-operation"

#: Canonical content-hash shape used across the v4 contracts.
_SHA256: Final = re.compile(r"^sha256:[0-9a-f]{64}$")

#: Fields the result must carry for a resolved Kernel transaction.  ``result_hash``
#: is deliberately absent: it is the digest of the answer itself, so an honest
#: "we do not know" is still a hashable record.
_RESOLVED_RESULT_FIELDS = (
    "lease_use_id",
    "lease_use_hash",
    "promotion_decision_id",
    "promotion_decision_hash",
    "passport_revision_id",
    "passport_revision_hash",
    "event_record_id",
    "event_record_hash",
    "committed_candidate_revision",
    "committed_passport_revision",
)

#: Fields every invocation binding must carry before anything is dispatched.
_REQUIRED_INVOCATION_FIELDS: Final = (
    "operation_id",
    "operation",
    "run_id",
    "node_id",
    "attempt",
    "action_intent_id",
    "action_intent_hash",
    "attempt_id",
    "capability_lease_id",
    "capability_lease_hash",
    "fencing_token",
    "principal_id",
    "capability",
    "resource_scopes",
    "promotion_pack_artifact_set_id",
    "promotion_pack_hash",
    "candidate_id",
    "expected_candidate_revision",
    "passport_id",
    "expected_passport_revision",
    "idempotency_key",
    "port_binding_id",
    "port_binding_hash",
    "request_hash",
)

#: Process-local registry of ports an operator explicitly trusted, keyed by
#: binding ID and pinned to the exact binding hash that was registered.
_TRUSTED_PORTS: dict[str, tuple[str, "PromotionCommitPort"]] = {}


@runtime_checkable
class PromotionCommitPort(Protocol):
    """The three closed operations A05 may ask a trusted adapter to perform."""

    def acquire_commit_lease(
        self, request: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...

    def commit_promotion(
        self, invocation: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...

    def reconcile_promotion(
        self, identity: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...


def register_commit_port(binding_id: str, binding_hash: str, port: object) -> None:
    """Register one E05 adapter under an explicit, stable binding ID.

    Registration is how a deployment states which adapter it trusts.  A payload
    cannot introduce a port, so a caller who controls node input still cannot
    supply the object that decides whether a promotion committed.

    The binding hash is pinned here rather than accepted from node input.  If a
    caller could assert it, the hash would only echo the request instead of
    identifying the adapter that was actually trusted.
    """

    if not isinstance(binding_id, str) or not binding_id.strip():
        raise EvolutionAuthorityError(
            "COMMIT_PORT_INVALID", "a port binding ID must be a non-empty string"
        )
    if not isinstance(binding_hash, str) or not _SHA256.fullmatch(binding_hash):
        raise EvolutionAuthorityError(
            "COMMIT_PORT_INVALID",
            "a port binding hash must be a canonical sha256 digest",
        )
    missing = [
        name
        for name in ("acquire_commit_lease", "commit_promotion", "reconcile_promotion")
        if not callable(getattr(port, name, None))
    ]
    if missing:
        raise EvolutionAuthorityError(
            "COMMIT_PORT_INVALID",
            f"promotion-commit port lacks required operations: {sorted(missing)}",
        )
    existing = _TRUSTED_PORTS.get(binding_id)
    if existing is not None and (existing[0] != binding_hash or existing[1] is not port):
        raise EvolutionAuthorityError(
            "COMMIT_PORT_CONFLICT",
            f"port binding {binding_id!r} is already bound to another adapter",
        )
    _TRUSTED_PORTS[binding_id] = (binding_hash, port)  # type: ignore[assignment]


def require_commit_port(
    binding_id: object, binding_hash: object
) -> PromotionCommitPort:
    """Resolve the registered adapter for one binding, or refuse.

    Both the ID and the hash must match what was registered, so a caller cannot
    point a real binding ID at a different claimed adapter identity.
    """

    if not isinstance(binding_id, str) or not binding_id.strip():
        raise EvolutionAuthorityError(
            "COMMIT_PORT_UNBOUND",
            "the node payload does not name a promotion-commit port binding",
        )
    registered = _TRUSTED_PORTS.get(binding_id)
    if registered is None:
        raise EvolutionAuthorityError(
            "COMMIT_PORT_UNBOUND",
            f"no trusted promotion-commit port is registered as {binding_id!r}; "
            "A05 cannot commit a promotion without the E05 adapter",
        )
    if registered[0] != binding_hash:
        raise EvolutionAuthorityError(
            "COMMIT_PORT_UNBOUND",
            f"port binding {binding_id!r} does not have the claimed identity",
        )
    return registered[1]


def validate_commit_operation(
    invocation: Mapping[str, Any], result: Mapping[str, Any] | None
) -> dict[str, Any]:
    """Structurally validate one operation binding.

    An unknown outcome may not carry any committed record: that is the exact
    difference between "we do not know" and "it committed", and collapsing it
    would let an interrupted dispatch be reported as a promotion.
    """

    record = {
        "invocation": dict(invocation),
        "result": None if result is None else dict(result),
    }
    binding = record["invocation"]
    absent = [field for field in _REQUIRED_INVOCATION_FIELDS if binding.get(field) is None]
    if absent:
        raise EvolutionAuthorityError(
            "COMMIT_OPERATION_INVALID",
            f"the commit invocation lacks required bindings: {sorted(absent)}",
        )
    if binding["operation"] != COMMIT_OPERATION:
        raise EvolutionAuthorityError(
            "COMMIT_OPERATION_INVALID",
            f"only {COMMIT_OPERATION} may be requested",
        )
    if binding["capability"] != COMMIT_CAPABILITY:
        raise EvolutionAuthorityError(
            "COMMIT_OPERATION_INVALID",
            f"the commit operation requires {COMMIT_CAPABILITY}",
        )
    if record["result"] is None:
        return record
    reported = record["result"]
    disposition = reported.get("disposition")
    if disposition not in COMMIT_DISPOSITIONS:
        raise EvolutionAuthorityError(
            "COMMIT_OPERATION_INVALID",
            f"unknown commit disposition {disposition!r}",
        )
    # Every answer carries its own digest, including an unresolved one, so a
    # result cannot be edited in transit without the change being visible.
    if reported.get("result_hash") != hash_excluding(dict(reported), "result_hash"):
        raise EvolutionAuthorityError(
            "COMMIT_OPERATION_INVALID",
            "the commit result result_hash does not cover the reported result",
        )
    if disposition == OUTCOME_UNKNOWN:
        asserted = [
            field for field in _RESOLVED_RESULT_FIELDS if reported.get(field) is not None
        ]
        if asserted:
            raise EvolutionAuthorityError(
                "COMMIT_OPERATION_INVALID",
                "an unknown outcome cannot assert committed records: "
                f"{sorted(asserted)}",
            )
    else:
        missing = [
            field for field in _RESOLVED_RESULT_FIELDS if reported.get(field) is None
        ]
        if missing:
            raise EvolutionAuthorityError(
                "COMMIT_OPERATION_INVALID",
                f"a {disposition} transaction must resolve: {sorted(missing)}",
            )
    return record


def require_commit_outcome(
    request: PromotionCommitRequest, reported: Mapping[str, Any]
) -> PromotionCommitOutcome:
    """Bind a port result to the exact request that authorized it.

    An adapter that answers about a different operation, request, or port
    binding is refused rather than trusted, so a stale or foreign transaction
    can never be reported as this promotion's outcome.
    """

    if not isinstance(reported, Mapping):
        raise EvolutionAuthorityError(
            "COMMIT_RESULT_INVALID", "the commit port must return an object"
        )
    result = dict(reported)
    invocation = request.as_invocation()
    validate_commit_operation(invocation, result)
    for field, expected in (
        ("operation_id", request.operation_id),
        ("request_hash", request.request_hash),
        ("port_binding_id", request.port_binding_id),
        ("port_binding_hash", request.port_binding_hash),
    ):
        if result.get(field) != expected:
            raise EvolutionAuthorityError(
                "COMMIT_RESULT_UNBOUND",
                f"commit result {field} does not resolve the authorized request",
            )
    disposition = str(result["disposition"])
    if disposition != OUTCOME_UNKNOWN:
        if result.get("capability_lease_id") != request.capability_lease_id:
            raise EvolutionAuthorityError(
                "COMMIT_RESULT_UNBOUND",
                "commit result does not resolve the acquired capability lease",
            )
        if result.get("fencing_token") != request.fencing_token:
            raise EvolutionAuthorityError(
                "COMMIT_RESULT_UNBOUND",
                "commit result does not resolve the acquired fencing token",
            )
        if result.get("observed_candidate_revision") != request.expected_candidate_revision:
            raise EvolutionAuthorityError(
                "COMMIT_REVISION_MISMATCH",
                "committed transaction observed a different candidate revision",
            )
        if result.get("observed_passport_revision") != request.expected_passport_revision:
            raise EvolutionAuthorityError(
                "COMMIT_REVISION_MISMATCH",
                "committed transaction observed a different Passport revision",
            )
    return PromotionCommitOutcome(
        disposition=disposition,
        operation_id=request.operation_id,
        request_hash=request.request_hash,
        port_binding_id=request.port_binding_id,
        port_binding_hash=request.port_binding_hash,
        result=result,
    )
