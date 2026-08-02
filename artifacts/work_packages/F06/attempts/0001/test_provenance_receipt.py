"""provenance_and_receipt_audit — every decision resolves to an immutable receipt.

The gate's output is a receipt, and a receipt only counts as evidence if a later
reader can re-derive it and trust that it granted no authority it was not owed.
So this audit checks that both an admit and a refuse produce a self-hashed,
content-addressed receipt; that the gate neither scores, selects nor promotes a
candidate; that a resume point named by a stop certificate must be one the run
actually committed (crash/resume honesty); and that the evaluator authority the
run was judged against is pinned immutably across the run's checkpoints.
"""

from __future__ import annotations

import pytest

from epistemic_foundry.domain.hashing import canonical_json, hash_excluding, sha256_hex
from epistemic_foundry.evolution.v4_f06 import (
    ADMIT,
    REFUSE,
    LifecycleReplayRefused,
    derive_lifecycle_replay,
    evaluate_lifecycle_replay,
)
from fixtures import EVALUATOR_HASH, deep_copy_case, happy_case

#: Substrings that would signal the gate had leaked into scoring, selection or
#: promotion authority it must never hold (EF4-I41, EF4-I45).
_FORBIDDEN_FRAGMENTS = ("fitness", "score", "promot", "rank", "holdout", "elevate")


def _receipt_strings(value: object) -> list[str]:
    """Every key and string value reachable in a receipt, for an authority scan."""
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            found.append(str(key))
            found.extend(_receipt_strings(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_receipt_strings(child))
    elif isinstance(value, str):
        found.append(value)
    return found


def test_an_admit_produces_a_re_derivable_receipt() -> None:
    receipt = derive_lifecycle_replay(**happy_case())
    assert receipt["decision"] == ADMIT
    assert hash_excluding(receipt, "receipt_hash") == receipt["receipt_hash"]


def test_a_refusal_produces_a_re_derivable_receipt() -> None:
    case = deep_copy_case(happy_case())
    case["forge_session"]["run_spec_id"] = "RS-DIVERGENT"
    receipt = derive_lifecycle_replay(**case)
    assert receipt["decision"] == REFUSE
    assert hash_excluding(receipt, "receipt_hash") == receipt["receipt_hash"]


def test_the_gate_id_is_derived_from_the_published_content() -> None:
    receipt = derive_lifecycle_replay(**happy_case())
    expected = (
        "FELR-"
        + sha256_hex(
            canonical_json(
                {
                    "created_at": receipt["created_at"],
                    "decision": receipt["decision"],
                    "evolution_run_id": receipt["evolution_run_id"],
                    "forge_session_hash": receipt["forge_session_hash"],
                    "replay_report_hash": receipt["replay_report_hash"],
                    "run_spec_id": receipt["run_spec_id"],
                }
            )
        )[len("sha256:") :]
    )
    assert receipt["gate_id"] == expected


def test_the_decision_is_only_ever_admit_or_refuse() -> None:
    admit = derive_lifecycle_replay(**happy_case())
    case = deep_copy_case(happy_case())
    case["run"]["candidate_genome_ids"] = ["HG-1", "HG-CHILD-1", "HG-STRAY"]
    refuse = derive_lifecycle_replay(**case)
    assert {admit["decision"], refuse["decision"]} == {ADMIT, REFUSE}


def test_the_receipt_grants_no_scoring_or_promotion_authority() -> None:
    receipt = derive_lifecycle_replay(**happy_case())
    strings = [text.lower() for text in _receipt_strings(receipt)]
    for text in strings:
        for fragment in _FORBIDDEN_FRAGMENTS:
            assert fragment not in text, (fragment, text)


def test_the_receipt_pins_the_single_evaluator_bundle_the_run_was_judged_by() -> None:
    receipt = derive_lifecycle_replay(**happy_case())
    # EF4-I43: one evaluator bundle across the run's committed checkpoints.
    assert receipt["evaluator_bundle_hashes"] == [EVALUATOR_HASH]


def test_a_resume_point_never_committed_is_refused() -> None:
    # Crash/resume honesty: a stop certificate that names a checkpoint the run
    # never committed would restore a state the run never reached, so the F05
    # machine refuses it and the gate surfaces a stop-certificate finding.
    case = deep_copy_case(happy_case())
    case["run"]["stop_certificate"]["checkpoint_id"] = "CP-NEVER-COMMITTED"
    receipt = derive_lifecycle_replay(**case)
    assert receipt["decision"] == REFUSE
    assert receipt["finding_code"] == "STOP_CERTIFICATE_INCONSISTENT"


def test_the_refusal_exception_carries_the_same_receipt_it_derived() -> None:
    case = deep_copy_case(happy_case())
    case["run"]["stop_certificate"]["checkpoint_id"] = "CP-NEVER-COMMITTED"
    derived = derive_lifecycle_replay(**case)
    with pytest.raises(LifecycleReplayRefused) as caught:
        evaluate_lifecycle_replay(**case)
    assert caught.value.context["receipt"] == derived


def test_the_forge_and_replay_bindings_are_content_hashes() -> None:
    from epistemic_foundry.domain.hashing import sha256_of_payload

    case = happy_case()
    receipt = derive_lifecycle_replay(**case)
    assert receipt["forge_session_hash"] == sha256_of_payload(case["forge_session"])
    assert receipt["replay_report_hash"] == sha256_of_payload(case["replay_report"])
    assert receipt["forge_session_hash"].startswith("sha256:")
    assert receipt["replay_report_hash"].startswith("sha256:")
