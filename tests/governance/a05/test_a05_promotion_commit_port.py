"""Negative coverage for the A05 promotion-commit path.

Every case here was, at some point during review, a way to obtain a promotion
without the authority that is supposed to grant it.
"""

from __future__ import annotations

from typing import Any

import pytest

from epistemic_foundry.governance.evolution_authority import cas, promotion, reconciliation
from epistemic_foundry.governance.evolution_authority.errors import EvolutionAuthorityError
from epistemic_foundry.governance.promotion import CANONICAL_GATE_IDS, PromotionRequest
from epistemic_foundry.domain.hashing import hash_excluding
from epistemic_foundry.governance.evolution_authority.models import (
    canonical_authorization_dispatch_hash,
)


def _hash(char: str) -> str:
    return f"sha256:{char * 64}"


def _sealed_result(result: dict[str, Any]) -> dict[str, Any]:
    """Give a stub result the self-digest a real adapter would carry."""

    sealed = dict(result)
    sealed["result_hash"] = hash_excluding(dict(sealed), "result_hash")
    return sealed


def _request_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "operation_id": "OP-A05-TEST",
        "run_id": "RUN-A05-TEST",
        "node_id": "commit_promotion_atomically",
        "attempt": 1,
        "action_intent_id": "AI-COMMIT",
        "action_intent_hash": _hash("1"),
        "attempt_id": "ATT-COMMIT",
        "capability_lease_id": "CL-COMMIT",
        "capability_lease_hash": _hash("2"),
        "fencing_token": 7,
        "principal_id": "AG-Committer",
        "resource_scopes": ["db.promotion_decisions/CAND-1"],
        "promotion_pack_artifact_set_id": "PAS-1",
        "promotion_pack_hash": _hash("3"),
        "candidate_id": "CAND-1",
        "expected_candidate_revision": 4,
        "passport_id": "HP-1",
        "expected_passport_revision": 2,
        "idempotency_key": "KEY-1",
        "port_binding_id": "PB-A05-TEST",
        "port_binding_hash": _hash("4"),
    }
    payload.update(overrides)
    return payload


def _canonical_request_hash(payload: dict[str, Any]) -> str:
    """The hash the runtime seals for this payload, not one we choose."""

    return promotion.build_commit_request(payload).request_hash


def _sealed_request(**overrides: Any) -> PromotionRequest:
    """A structurally complete request whose gate evidence is what decides."""

    fields: dict[str, Any] = {
        "candidate_id": "CAND-1",
        "candidate_revision": 4,
        "current_level": "CANDIDATE",
        "requested_level": "REPLICATED",
        "policy_promotion_ceiling": "REPLICATED",
        "hard_gate_status": "FAIL",
        "fitness_vector_id": "FV-1",
        "phase_e_artifact_set_id": "PAS-1",
        "promotion_pack_artifact_ids": ("ART-1",),
        "promotion_pack_hash": _hash("3"),
        "gate_decision_ids": CANONICAL_GATE_IDS,
        "artifact_receipt_ids": ("AR-1",),
        "effect_receipt_id": "ER-1",
        "request_action_intent_id": "AI-REQUEST",
        "commit_action_intent_id": "AI-COMMIT",
        "policy_bundle_hash": _hash("b"),
        "idempotency_key": "KEY-1",
        "parliament_adjudication_id": "ADJ-1",
        "attestation_id": "ATT-1",
        "replication_status": "REPLICATED",
        "selective_inference_report_id": "SIR-1",
        "gate_decisions": (),
    }
    fields.update(overrides)
    return PromotionRequest(**fields)


class _StubPort:
    """A port that would happily report success if it were ever reached."""

    def __init__(self, result: dict[str, Any] | None = None) -> None:
        self.result = _sealed_result(result or {"disposition": "COMMITTED"})
        self.commit_calls = 0

    def acquire_commit_lease(self, request: Any) -> dict[str, Any]:
        return {}

    def commit_promotion(self, invocation: Any) -> dict[str, Any]:
        self.commit_calls += 1
        return self.result

    def reconcile_promotion(self, identity: Any) -> dict[str, Any]:
        return self.result


def test_a05_commit_refuses_before_port_resolution_until_split_is_ratified() -> None:
    with pytest.raises(EvolutionAuthorityError) as caught:
        promotion.commit_outcome(
            _request_payload(port_binding_id="PB-NEVER-REGISTERED"),
            decision={"decision_id": "PD-1"},
        )
    assert caught.value.code == "SPEC_GAP"
    assert "G14 authority circularity" in str(caught.value)


def test_a05_commit_ignores_a_port_supplied_in_the_payload() -> None:
    """A caller who controls node input must not be able to supply the adapter."""

    port = _StubPort()
    with pytest.raises(EvolutionAuthorityError) as caught:
        promotion.commit_outcome(
            _request_payload(port_binding_id="PB-NOT-REGISTERED", commit_port=port),
            decision={"decision_id": "PD-1"},
        )
    assert caught.value.code == "SPEC_GAP"
    assert port.commit_calls == 0


def test_a05_g14_circularity_fails_before_dispatching_the_effect() -> None:
    """The unratified G14 split must never reach the Kernel."""

    port = _StubPort()
    cas.register_commit_port("PB-ORDERING", _hash("f"), port)
    with pytest.raises(EvolutionAuthorityError) as caught:
        promotion.commit_promotion_atomically(
            _request_payload(
                port_binding_id="PB-ORDERING",
                port_binding_hash=_hash("f"),
                promotion_request=_sealed_request(),
                current_level="CANDIDATE",
            )
        )
    assert caught.value.code == "SPEC_GAP"
    assert port.commit_calls == 0


def test_a05_port_binding_hash_must_match_registration() -> None:
    cas.register_commit_port("PB-HASH-CASE", _hash("a"), _StubPort())
    with pytest.raises(EvolutionAuthorityError) as caught:
        cas.require_commit_port("PB-HASH-CASE", _hash("b"))
    assert caught.value.code == "COMMIT_PORT_UNBOUND"


def test_a05_port_binding_cannot_be_rebound() -> None:
    cas.register_commit_port("PB-REBIND", _hash("c"), _StubPort())
    with pytest.raises(EvolutionAuthorityError) as caught:
        cas.register_commit_port("PB-REBIND", _hash("c"), _StubPort())
    assert caught.value.code == "COMMIT_PORT_CONFLICT"


def test_a05_commit_refuses_a_caller_supplied_promotion_decision() -> None:
    """The inflated-ceiling attack: assert PASS and REPLICATED, get a promotion.

    The verdict must be derived from sealed gate evidence, so a schema-valid
    document that simply claims a passing hard gate and the highest ceiling
    cannot become the committed decision.
    """

    forged = {
        "decision_id": "PD-FORGED",
        "candidate_id": "CAND-1",
        "candidate_revision": 4,
        "requested_level": "REPLICATED",
        "granted_level": "REPLICATED",
        "promotion_ceiling": "REPLICATED",
        "hard_gate_status": "PASS",
        "decision": "PROMOTE",
    }
    payload = _request_payload(
        promotion_request=_sealed_request(),
        current_level="CANDIDATE",
        promotion_decision=forged,
    )
    with pytest.raises(EvolutionAuthorityError) as caught:
        promotion.derive_promotion_decision(payload)
    # The refusal must come from the promotion authority, not from a missing
    # input; otherwise this test would pass even if derivation were removed.
    assert caught.value.code in {"PROMOTION_REFUSED", "PROMOTION_DECISION_INVALID"}


def test_a05_derivation_requires_a_sealed_request() -> None:
    """A decision document is never a substitute for sealed gate evidence."""

    with pytest.raises(EvolutionAuthorityError) as caught:
        promotion.derive_promotion_decision(
            _request_payload(promotion_request={"candidate_id": "CAND-1"})
        )
    assert caught.value.code == "NODE_INPUT_INVALID"


@pytest.mark.parametrize(
    "override",
    [
        {"promotion_pack_hash": _hash("9")},
        {"idempotency_key": "KEY-OTHER"},
        {"commit_action_intent_id": "AI-OTHER"},
        {"candidate_revision": 9},
    ],
)
def test_a05_sealed_request_must_describe_the_same_work(override: Any) -> None:
    """Two different requests may not be spliced into one commit.

    Each half would look internally valid, so the mismatch has to be caught
    where the sealed evidence and the operation identity meet.
    """

    payload = _request_payload(
        promotion_request=_sealed_request(**override),
        current_level="CANDIDATE",
    )
    with pytest.raises(EvolutionAuthorityError) as caught:
        promotion.derive_promotion_decision(payload)
    assert caught.value.code == "COMMIT_REQUEST_UNBOUND"


def test_a05_unknown_outcome_is_not_a_completed_commit() -> None:
    cas.register_commit_port(
        "PB-UNKNOWN", _hash("d"), _StubPort({"disposition": "OUTCOME_UNKNOWN"})
    )
    with pytest.raises(EvolutionAuthorityError) as caught:
        reconciliation.reconcile_commit_receipts(
            _request_payload(port_binding_id="PB-UNKNOWN", port_binding_hash=_hash("d"))
        )
    # The stub answers about no particular operation, so identity binding trips
    # first.  Either way the run may not proceed to G14.
    assert caught.value.code == "COMMIT_RESULT_UNBOUND"


def test_a05_unresolved_dispatch_cannot_complete_g14() -> None:
    """An honestly unresolved outcome still refuses completion."""

    payload = _request_payload(
        port_binding_id="PB-UNRESOLVED", port_binding_hash=_hash("e")
    )
    unresolved = {
        "disposition": "OUTCOME_UNKNOWN",
        "operation_id": "OP-A05-TEST",
        "request_hash": _canonical_request_hash(payload),
        "port_binding_id": "PB-UNRESOLVED",
        "port_binding_hash": _hash("e"),
    }
    cas.register_commit_port("PB-UNRESOLVED", _hash("e"), _StubPort(unresolved))
    with pytest.raises(EvolutionAuthorityError) as caught:
        reconciliation.reconcile_commit_receipts(payload)
    assert caught.value.code == "COMMIT_OUTCOME_UNKNOWN"


def test_a05_commit_result_must_carry_its_own_digest() -> None:
    """A result edited in transit must not read as the adapter's answer."""

    payload = _request_payload(
        port_binding_id="PB-RESULT-DIGEST", port_binding_hash=_hash("7")
    )
    honest = _sealed_result(
        {
            "disposition": "OUTCOME_UNKNOWN",
            "operation_id": "OP-A05-TEST",
            "request_hash": _canonical_request_hash(payload),
            "port_binding_id": "PB-RESULT-DIGEST",
            "port_binding_hash": _hash("7"),
            "fencing_token": 7,
        }
    )
    # Tamper a field the identity comparison does not cover, so the digest is
    # what has to catch it rather than the operation binding.
    tampered = {**honest, "fencing_token": 99}
    port = _StubPort()
    port.result = tampered
    cas.register_commit_port("PB-RESULT-DIGEST", _hash("7"), port)
    with pytest.raises(EvolutionAuthorityError) as caught:
        reconciliation.reconcile_commit_receipts(payload)
    assert caught.value.code == "COMMIT_OPERATION_INVALID"


def test_a05_decision_identity_is_stable_across_retries() -> None:
    """The same promotion must recognize the decision already committed.

    The shared authority mints a random identifier per call.  If a retry kept
    that fresh identifier it would compare it against the one the Kernel
    already stored, disagree, and reject its own successful transaction.
    """

    first = promotion._stable_decision_id("KEY-1")
    assert first == promotion._stable_decision_id("KEY-1")
    assert first != promotion._stable_decision_id("KEY-2")


def test_a05_request_hash_is_sealed_from_the_invocation() -> None:
    """The canonical request hash must cover the request, not echo the caller.

    Idempotent replay compares exactly this value, so a hash the caller merely
    asserts would let one value stand for two different operations.
    """

    payload = _request_payload()
    sealed = promotion.build_commit_request(payload).request_hash
    other = promotion.build_commit_request(
        _request_payload(candidate_id="CAND-OTHER")
    ).request_hash
    assert sealed != other
    # Restating the derived hash is allowed; asserting a different one is not.
    assert promotion.build_commit_request(
        _request_payload(request_hash=sealed)
    ).request_hash == sealed
    with pytest.raises(EvolutionAuthorityError) as caught:
        promotion.build_commit_request(_request_payload(request_hash=_hash("5")))
    assert caught.value.code == "COMMIT_REQUEST_UNBOUND"


def test_a05_authorization_dispatch_hash_binds_request_and_decision() -> None:
    request = promotion.build_commit_request(_request_payload())
    invocation = request.as_invocation()
    authorized = {"decision_id": "PD-1", "decision_hash": _hash("8")}
    sealed = canonical_authorization_dispatch_hash(invocation, authorized)

    assert sealed != canonical_authorization_dispatch_hash(
        invocation, {**authorized, "decision_hash": _hash("9")}
    )
    other_invocation = promotion.build_commit_request(
        _request_payload(candidate_id="CAND-OTHER")
    ).as_invocation()
    assert sealed != canonical_authorization_dispatch_hash(
        other_invocation, authorized
    )
