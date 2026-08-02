"""Provenance and receipt discipline for the P05 promotion-Parliament gate.

Every decision resolves to one immutable receipt that is a pure function of its
inputs: no clock, no random draw, the caller supplies ``created_at``, the gate id
and receipt hash re-derive from the receipt's own fields, and no input is mutated.
These tests pin that a convene and a withhold are both re-derivable and that the
docket the caller passed is unchanged afterwards.
"""

from __future__ import annotations

import copy

import fixtures as f

from epistemic_foundry.domain.hashing import canonical_json, hash_excluding, sha256_hex
from epistemic_foundry.parliament.v4_p05 import gate


def test_the_receipt_hash_re_derives_from_the_published_fields() -> None:
    receipt = gate.derive_promotion_parliament(**f.docket())
    recorded = receipt["receipt_hash"]
    assert hash_excluding(receipt, "receipt_hash") == recorded


def test_the_gate_id_re_derives_from_its_stable_subset() -> None:
    receipt = gate.derive_promotion_parliament(**f.docket())
    expected = (
        gate.GATE_ID_PREFIX
        + sha256_hex(
            canonical_json(
                {
                    "candidate_id": receipt["candidate_id"],
                    "candidate_revision": receipt["candidate_revision"],
                    "created_at": receipt["created_at"],
                    "decision": receipt["decision"],
                    "adjudication_hash": receipt["adjudication_hash"],
                    "statistical_receipt_hash": receipt["statistical_receipt_hash"],
                    "requested_level": receipt["requested_level"],
                }
            )
        )[len("sha256:") :]
    )
    assert receipt["gate_id"] == expected


def test_the_same_inputs_re_derive_the_identical_receipt() -> None:
    """No clock and no random draw: two derivations agree byte for byte."""
    docket = f.docket()
    first = gate.derive_promotion_parliament(**docket)
    second = gate.derive_promotion_parliament(**f.docket())
    assert first == second
    assert canonical_json(first) == canonical_json(second)


def test_a_withhold_decision_is_also_re_derivable() -> None:
    docket = f.docket(red_queen_results=[])
    receipt = gate.derive_promotion_parliament(**docket)
    assert receipt["decision"] == gate.WITHHOLD
    assert receipt["finding_code"] == "RED_QUEEN_EVIDENCE_ABSENT"
    assert hash_excluding(receipt, "receipt_hash") == receipt["receipt_hash"]


def test_the_caller_supplied_timestamp_is_echoed_not_a_clock() -> None:
    stamp = "2030-01-02T03:04:05+00:00"
    receipt = gate.derive_promotion_parliament(**f.docket(created_at=stamp))
    assert receipt["created_at"] == stamp


def test_the_inputs_are_not_mutated() -> None:
    docket = f.docket()
    snapshot = copy.deepcopy(docket)
    gate.derive_promotion_parliament(**docket)
    assert docket == snapshot


def test_the_receipt_binds_the_candidate_revision_and_composed_artifacts() -> None:
    docket = f.docket()
    receipt = gate.derive_promotion_parliament(**docket)
    assert receipt["candidate_id"] == f.CANDIDATE_ID
    assert receipt["candidate_revision"] == f.CANDIDATE_REVISION
    assert receipt["adjudication_id"] == docket["adjudication"]["adjudication_id"]
    assert receipt["lineage_id"] == docket["lineage"]["lineage_id"]
    assert receipt["replication_result_hashes"] == [
        docket["replication_results"][0]["result_hash"]
    ]
