"""Provenance and receipt audit for the V05 advancement gate.

Every advance-or-refuse decision resolves to one immutable receipt that is a pure
function of its inputs. These tests confirm the receipt re-derives its own hash,
that its identifier is a deterministic function of the decision's binding fields,
that it binds the composed statistical clearance by hash, and that a tampered
receipt is detected rather than trusted.
"""

from __future__ import annotations

import fixtures as fx
from epistemic_foundry.domain.hashing import hash_excluding
from epistemic_foundry.validation.v4_v05 import cascade_gate as engine


def test_receipt_re_derives_its_own_hash() -> None:
    receipt = engine.derive_validation_advancement(**fx.gate_arguments())
    assert engine.advancement_hash_matches(receipt)
    assert hash_excluding(dict(receipt), "receipt_hash") == receipt["receipt_hash"]


def test_refuse_receipt_re_derives_its_own_hash() -> None:
    receipt = engine.derive_validation_advancement(
        **fx.gate_arguments(replication_plan=None)
    )
    assert engine.advancement_hash_matches(receipt)


def test_gate_id_is_deterministic_across_runs() -> None:
    first = engine.derive_validation_advancement(**fx.gate_arguments())
    second = engine.derive_validation_advancement(**fx.gate_arguments())
    assert first["gate_id"] == second["gate_id"]
    assert first["receipt_hash"] == second["receipt_hash"]


def test_receipt_binds_the_statistical_clearance_by_hash() -> None:
    receipt = engine.derive_validation_advancement(**fx.gate_arguments())
    clearance = fx.admissibility_receipt()
    assert (
        receipt["statistical_admissibility_receipt_hash"] == clearance["receipt_hash"]
    )
    assert receipt["statistical_admissibility_gate_id"] == clearance["gate_id"]


def test_receipt_records_the_replication_ceiling_and_configured_level() -> None:
    receipt = engine.derive_validation_advancement(**fx.gate_arguments())
    assert receipt["required_promotion_level"] == fx.required_replicated_level()
    assert receipt["replication_plan_id"] == "RP-V05-1"
    assert receipt["adaptive_search_used"] is True


def test_a_tampered_receipt_fails_the_hash_check() -> None:
    receipt = engine.derive_validation_advancement(**fx.gate_arguments())
    tampered = dict(receipt)
    tampered["decision"] = engine.ADVANCE
    tampered["advanced"] = True
    tampered["finding_code"] = None
    # The stored hash still covers the original content, so tampering is caught.
    if receipt["decision"] == engine.ADVANCE:
        tampered["candidate_id"] = "HG-INJECTED"
    assert not engine.advancement_hash_matches(tampered)


def test_gate_id_changes_with_the_decision_binding() -> None:
    advanced = engine.derive_validation_advancement(**fx.gate_arguments())
    refused = engine.derive_validation_advancement(
        **fx.gate_arguments(replication_plan=None)
    )
    assert advanced["gate_id"] != refused["gate_id"]
