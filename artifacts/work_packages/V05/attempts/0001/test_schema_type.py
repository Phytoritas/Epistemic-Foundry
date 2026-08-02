"""Schema and type checks for the V05 advancement gate.

The gate reads two canonical enum tokens — the out-of-distribution challenge
class and the passing cascade status — from the schemas rather than restating
them, and reduces a bundle of composed artifacts to one immutable receipt. These
tests pin the vocabulary reads to the schemas and pin the receipt's shape and
identifier formats, so a schema reshape or a receipt-field drift fails here.
"""

from __future__ import annotations

import fixtures as fx
from epistemic_foundry.contracts import default_registry
from epistemic_foundry.domain.vocabularies import PROMOTION_LADDER
from epistemic_foundry.validation.v4_v05 import cascade_gate as engine


def test_ood_token_is_read_from_the_challenge_genome_schema() -> None:
    document = default_registry().document("challenge-genome")
    classes = document["properties"]["challenge_class"]["enum"]
    token = engine.ood_challenge_class_token()
    assert token in classes
    assert "ood" in token.lower()


def test_cascade_pass_token_is_the_schema_hard_gate_first_rung() -> None:
    document = default_registry().document("promotion-decision")
    statuses = document["properties"]["hard_gate_status"]["enum"]
    assert engine.cascade_pass_status() == statuses[0]


def test_every_finding_code_carries_a_reason() -> None:
    assert engine.FINDING_CODES
    for code, reason in engine.FINDING_CODES.items():
        assert code.isupper()
        assert isinstance(reason, str) and reason.strip()


def test_advance_receipt_has_the_expected_shape_and_types() -> None:
    receipt = engine.derive_validation_advancement(**fx.gate_arguments())
    assert receipt["gate"] == engine.GATE_NAME
    assert receipt["decision"] == engine.ADVANCE
    assert receipt["advanced"] is True
    assert receipt["finding_code"] is None
    assert receipt["candidate_id"] == fx.CANDIDATE_ID
    assert receipt["cascade_status"] == engine.cascade_pass_status()
    assert receipt["ood_challenge_class"] == engine.ood_challenge_class_token()
    assert receipt["ood_survived"] is True
    assert receipt["statistical_admitted"] is True
    assert receipt["replication_ceiling"] in PROMOTION_LADDER
    assert isinstance(receipt["ood_challenge_result_ids"], list)


def test_receipt_identifiers_have_stable_formats() -> None:
    receipt = engine.derive_validation_advancement(**fx.gate_arguments())
    assert receipt["gate_id"].startswith(engine.GATE_ID_PREFIX)
    assert receipt["receipt_hash"].startswith("sha256:")
    assert len(receipt["receipt_hash"]) == len("sha256:") + 64


def test_refuse_receipt_names_a_declared_finding_code() -> None:
    receipt = engine.derive_validation_advancement(
        **fx.gate_arguments(replication_plan=None)
    )
    assert receipt["decision"] == engine.REFUSE
    assert receipt["finding_code"] in engine.FINDING_CODES
    assert receipt["advanced"] is False
