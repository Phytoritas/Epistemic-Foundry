"""provenance_and_receipt_audit — every decision is an immutable, replayable receipt.

A gate whose decisions could not be reproduced would be a record of trust, not
of evidence.  These tests prove three things about every receipt the gate emits:
it re-derives its own identifier and hash from its content, two runs over equal
inputs produce byte-equal receipts, and producing it mutates none of the sealed
inputs.  They also prove the gate stays inside its authority: no receipt carries
a score, a fitness value or a promotion decision, and the embedded leakage audit
still validates against its canonical schema.
"""

from __future__ import annotations

import copy

from epistemic_foundry.contracts import validate_artifact
from epistemic_foundry.domain.hashing import (
    hash_excluding,
    is_schema_digest,
    sha256_of_payload,
)
from epistemic_foundry.evidence.v4_k06 import (
    admit_candidate_execution_against_version,
    admit_evaluator_feedback_against_version,
    admit_retrieval_against_version,
    admit_search_results_against_version,
    bind_evidence_holdout_version,
)
from fixtures import (
    VIS_1,
    execution_arguments,
    feedback_arguments,
    plan,
    searched_receipt,
    snapshot,
    version_arguments,
)

#: Words a promotion/scoring authority would introduce; the gate owns none of
#: them, so no receipt it emits may carry one.
FORBIDDEN_AUTHORITY_KEYS = (
    "score",
    "fitness",
    "reward",
    "promotion",
    "promoted",
    "rank",
    "verdict",
    "decision_score",
)


#: Each receipt the gate emits, named by its own identifier and hash fields, so
#: the re-derivation test does not have to guess which pair a receipt carries.
def _labelled_receipts():
    """One of every receipt, each as (receipt, id_field, hash_field)."""
    pinned = snapshot()
    arguments = version_arguments(pinned)
    version = bind_evidence_holdout_version(**arguments)
    declared = plan(pinned)
    firewall = arguments["firewall"]
    return [
        (version, "version_id", "version_hash"),
        (
            admit_retrieval_against_version(version=version, plan=declared),
            "receipt_id",
            "receipt_hash",
        ),
        (
            admit_search_results_against_version(
                version=version, receipt=searched_receipt(declared, pinned)
            ),
            "receipt_id",
            "admission_hash",
        ),
        (
            admit_candidate_execution_against_version(
                **execution_arguments(version, firewall)
            ),
            "receipt_id",
            "admission_hash",
        ),
        (
            admit_evaluator_feedback_against_version(
                **feedback_arguments(version, firewall)
            ),
            "receipt_id",
            "admission_hash",
        ),
    ]


def _all_receipts():
    """The version plus every admission receipt, for whole-record assertions."""
    labelled = _labelled_receipts()
    return labelled[0][0], [receipt for receipt, _, _ in labelled]


def test_every_receipt_re_derives_its_identifier_and_hash() -> None:
    for receipt, id_field, hash_field in _labelled_receipts():
        assert is_schema_digest(receipt[hash_field]), id_field
        body = {k: v for k, v in receipt.items() if k not in {id_field, hash_field}}
        prefix = str(receipt[id_field]).split("-", 1)[0] + "-"
        expected_id = prefix + sha256_of_payload(body).removeprefix("sha256:")
        assert receipt[id_field] == expected_id, id_field
        assert receipt[hash_field] == hash_excluding(receipt, hash_field), hash_field


def test_receipts_are_byte_equal_across_two_runs() -> None:
    _, first = _all_receipts()
    _, second = _all_receipts()
    assert first == second


def test_binding_a_version_mutates_none_of_its_inputs() -> None:
    arguments = version_arguments()
    snapshots = {
        key: copy.deepcopy(value)
        for key, value in arguments.items()
        if key != "firewall"
    }
    sealed_hash_before = arguments["firewall"].sealed_hash
    bind_evidence_holdout_version(**arguments)
    for key, before in snapshots.items():
        assert arguments[key] == before, key
    assert arguments["firewall"].sealed_hash == sealed_hash_before


def test_admissions_mutate_none_of_their_inputs() -> None:
    pinned = snapshot()
    arguments = version_arguments(pinned)
    version = bind_evidence_holdout_version(**arguments)
    declared = plan(pinned)
    receipt = searched_receipt(declared, pinned)
    version_before = copy.deepcopy(version)
    plan_before = copy.deepcopy(declared)
    receipt_before = copy.deepcopy(receipt)
    admit_retrieval_against_version(version=version, plan=declared)
    admit_search_results_against_version(version=version, receipt=receipt)
    assert version == version_before
    assert declared == plan_before
    assert receipt == receipt_before


def test_no_receipt_carries_a_scoring_or_promotion_field() -> None:
    _, receipts = _all_receipts()
    for receipt in receipts:
        for key in _flatten_keys(receipt):
            lowered = key.lower()
            assert not any(bad in lowered for bad in FORBIDDEN_AUTHORITY_KEYS), key


def test_the_embedded_leakage_audit_validates_against_its_schema() -> None:
    pinned = snapshot()
    arguments = version_arguments(pinned)
    version = bind_evidence_holdout_version(**arguments)
    admission = admit_evaluator_feedback_against_version(
        **feedback_arguments(version, arguments["firewall"])
    )
    # The gate embeds the S05 audit verbatim rather than paraphrasing it, so it
    # must still be the canonical artifact its own owner would accept.
    validate_artifact("leakage-audit", admission["leakage_audit"])
    assert admission["leakage_audit"]["status"] == "PASS"


def test_admitted_results_never_include_a_concealed_document() -> None:
    pinned = snapshot()
    arguments = version_arguments(pinned)
    version = bind_evidence_holdout_version(**arguments)
    admission = admit_search_results_against_version(
        version=version,
        receipt=searched_receipt(plan(pinned), pinned, result_document_ids=[VIS_1]),
    )
    assert set(admission["admitted_result_ids"]).isdisjoint(
        set(version["concealed_document_ids"])
    )


def _flatten_keys(value, prefix=""):
    """Yield every mapping key in a nested receipt, including embedded records."""
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _flatten_keys(item, prefix)
    elif isinstance(value, list):
        for item in value:
            yield from _flatten_keys(item, prefix)
