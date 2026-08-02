"""unit_and_contract_tests — the gate admits an honest run and composes its deps.

The happy case is a run every composed surface accepts: F05 walks its lifecycle,
I05 admits its seeds, R05 declares its operators, and its own replay report shows
a strict, exact reproduction.  These tests pin what admitting it means — the
decision, the receipt it produces, that the receipt is a pure re-derivable
function of the inputs, that the inputs are never mutated, and that the gate's
verdict is genuinely the composed verdict of F05, I05 and R05 rather than a
restatement.
"""

from __future__ import annotations

import pytest

from epistemic_foundry.domain.hashing import hash_excluding
from epistemic_foundry.evolution.v4_f06 import (
    ADMIT,
    LifecycleReplayRefused,
    derive_lifecycle_replay,
    evaluate_lifecycle_replay,
)
from fixtures import GATE_AT, RUN_ID, RUN_SPEC_ID, deep_copy_case, happy_case


def test_the_gate_admits_a_consistent_replayable_run() -> None:
    receipt = evaluate_lifecycle_replay(**happy_case())
    assert receipt["decision"] == ADMIT
    assert receipt["finding_code"] is None
    assert receipt["evolution_run_id"] == RUN_ID
    assert receipt["run_spec_id"] == RUN_SPEC_ID


def test_the_receipt_is_re_derivable_from_its_own_content() -> None:
    receipt = derive_lifecycle_replay(**happy_case())
    assert hash_excluding(receipt, "receipt_hash") == receipt["receipt_hash"]
    assert receipt["gate_id"].startswith("FELR-")


def test_the_decision_is_a_pure_function_of_the_inputs() -> None:
    first = derive_lifecycle_replay(**happy_case())
    second = derive_lifecycle_replay(**happy_case())
    assert first == second


def test_the_gate_mutates_none_of_its_inputs() -> None:
    case = happy_case()
    before_session = dict(case["forge_session"])
    before_replay = dict(case["replay_report"])
    before_run = dict(case["run"])
    derive_lifecycle_replay(**case)
    assert case["forge_session"] == before_session
    assert case["replay_report"] == before_replay
    assert case["run"] == before_run


def test_the_receipt_reports_the_composed_f05_lifecycle_account() -> None:
    receipt = derive_lifecycle_replay(**happy_case())
    # The two committed return edges the F05 machine counted are surfaced here,
    # so the gate's account is the machine's account and not a second copy.
    assert receipt["lifecycle_valid"] is True
    assert receipt["return_edges"] == 2


def test_the_receipt_reports_the_composed_r05_operators() -> None:
    receipt = derive_lifecycle_replay(**happy_case())
    assert receipt["operator_ids"] == ["mechanism-refinement"]


def test_the_receipt_reports_the_reconciled_candidate_set() -> None:
    receipt = derive_lifecycle_replay(**happy_case())
    assert receipt["seed_genome_ids"] == ["HG-1"]
    assert receipt["candidate_genome_ids"] == ["HG-1", "HG-CHILD-1"]


def test_the_receipt_binds_the_session_and_replay_report_by_hash() -> None:
    case = happy_case()
    receipt = derive_lifecycle_replay(**case)
    from epistemic_foundry.domain.hashing import sha256_of_payload

    assert receipt["forge_session_hash"] == sha256_of_payload(case["forge_session"])
    assert receipt["replay_report_hash"] == sha256_of_payload(case["replay_report"])
    assert receipt["source_run_id"] == RUN_ID


def test_a_refusal_raises_and_carries_the_receipt() -> None:
    case = deep_copy_case(happy_case())
    case["replay_report"]["mode"] = "semantic"
    case["replay_report"]["event_equivalence"] = "SEMANTICALLY_EQUIVALENT"
    with pytest.raises(LifecycleReplayRefused) as caught:
        evaluate_lifecycle_replay(**case)
    assert caught.value.code == "REPLAY_NOT_BYTE_FOR_BYTE"
    receipt = caught.value.context["receipt"]
    assert receipt["decision"] != ADMIT
    assert receipt["finding_code"] == "REPLAY_NOT_BYTE_FOR_BYTE"
    assert hash_excluding(receipt, "receipt_hash") == receipt["receipt_hash"]


def test_the_derivation_records_a_refusal_without_raising() -> None:
    case = deep_copy_case(happy_case())
    case["run"]["candidate_genome_ids"] = ["HG-1", "HG-CHILD-1", "HG-EXTRA"]
    receipt = derive_lifecycle_replay(**case)
    assert receipt["decision"] != ADMIT
    assert receipt["finding_code"] == "CANDIDATE_SET_UNRECONCILED"
    # A refusal is still a complete, re-derivable receipt.
    assert hash_excluding(receipt, "receipt_hash") == receipt["receipt_hash"]


def test_created_at_is_carried_not_invented() -> None:
    receipt = derive_lifecycle_replay(**happy_case())
    assert receipt["created_at"] == GATE_AT
