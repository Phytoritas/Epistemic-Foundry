"""Promotion authority and dependency-corrected support."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from epistemic_foundry.governance import (
    PromotionRequest,
    adjusted_support_count,
    build_dependency_cluster,
    decide_promotion,
)
from epistemic_foundry.governance.dependency import corrected_support
from epistemic_foundry.governance.promotion import (
    ABSENT_REFERENCE,
    CANONICAL_GATE_IDS,
    LEGACY_PROMOTION_LEVEL_REVIEW_REQUIRED,
    LegacyPromotionLevelReviewRequired,
    PromotionLevel,
    PromotionRefused,
    ReassessmentRequired,
    migrate_legacy_promotion_level,
    promoted,
    promotion_idempotency_key,
    validate_promotion_decision_semantics,
)
from epistemic_foundry.domain.hashing import hash_excluding, sha256_of_payload

PACK_HASH = "sha256:" + "a" * 64
POLICY_HASH = "sha256:" + "b" * 64


def _gate_decisions(
    *,
    not_required: tuple[str, ...] = (),
    status_overrides: dict[str, str] | None = None,
) -> tuple[dict, ...]:
    status_overrides = status_overrides or {}
    decisions = []
    for index, gate_id in enumerate(CANONICAL_GATE_IDS):
        is_not_required = gate_id in not_required
        status = status_overrides.get(gate_id, "PASS")
        timestamp = "2026-07-28T00:00:00+00:00"
        decision = {
            "gate_id": f"GD-FIXTURE-{index:02d}",
            "gate_version": "4.0.0",
            "run_id": "RUN-PROMOTION-0001",
            "name": gate_id,
            "status": status,
            "reasons": [
                "POLICY_NOT_REQUIRED: sealed PolicyBundle rule PB-RULE-LOW-RISK-0001"
                if is_not_required
                else "substantive gate evidence verified"
            ],
            "evidence_ids": [
                "ART-POLICY-NOT-REQUIRED-0001"
                if is_not_required
                else f"ART-{gate_id}-0001"
            ],
            "input_artifact_ids": [f"ART-{gate_id}-INPUT-0001"],
            "policy_bundle_hash": POLICY_HASH,
            "decision": status,
            "blocker_ids": [] if status == "PASS" else [f"BLK-{gate_id}-0001"],
            "waiver_authority": None,
            "waiver_reason": None,
            "evaluated_at": timestamp,
            "created_at": timestamp,
            "policy_version": "4.0.0-fixture.1",
            "non_waivable": True,
            "evaluator_type": "deterministic",
            "input_hash": "sha256:" + "c" * 64,
        }
        decision["decision_hash"] = hash_excluding(decision, "decision_hash")
        decisions.append(decision)
    return tuple(decisions)


def _complete_request(**overrides) -> PromotionRequest:
    """A request that satisfies every named promotion requirement."""
    values = {
        "candidate_id": "CAND-0001",
        "candidate_revision": 1,
        "current_level": PromotionLevel.INBOX,
        "requested_level": PromotionLevel.CANDIDATE,
        "policy_promotion_ceiling": PromotionLevel.REPLICATED,
        "hard_gate_status": "PASS",
        "fitness_vector_id": "FV-0001",
        "phase_e_artifact_set_id": "PAS-E-0001",
        "promotion_pack_artifact_ids": ("ART-PACK-0001",),
        "promotion_pack_hash": PACK_HASH,
        "gate_decision_ids": CANONICAL_GATE_IDS,
        "artifact_receipt_ids": ("AR-PACK-0001",),
        "effect_receipt_id": "EF-COMMIT-0001",
        "request_action_intent_id": "AI-REQUEST-0001",
        "commit_action_intent_id": "AI-COMMIT-0001",
        "policy_bundle_hash": POLICY_HASH,
        "parliament_adjudication_id": "ADJ-0001",
        "attestation_id": None,
        "replication_status": "REPLICATED",
        "selective_inference_report_id": "SIR-0001",
        "replication_result_ids": ("REP-0001",),
        "approval_record_ids": ("APR-0001",),
        "grounded_evidence_ids": ("EV-0001",),
        "dependency_cluster_ids": ("EDC-0001",),
        "challenge_survived": True,
        "leakage_detected": False,
    }
    values.update(overrides)
    if "gate_decisions" not in overrides:
        not_required = (
            ("G12_INDEPENDENT_ATTESTATION",)
            if values["requested_level"]
            in {
                PromotionLevel.INBOX,
                PromotionLevel.CANDIDATE,
                PromotionLevel.LITERATURE_GROUNDED,
            }
            and values["attestation_id"] is None
            else ()
        )
        values["gate_decisions"] = _gate_decisions(not_required=not_required)
    if "idempotency_key" not in overrides:
        values["idempotency_key"] = promotion_idempotency_key(
            candidate_id=values["candidate_id"],
            candidate_revision=values["candidate_revision"],
            requested_level=values["requested_level"],
            promotion_pack_hash=values["promotion_pack_hash"],
            policy_bundle_hash=values["policy_bundle_hash"],
        )
    return PromotionRequest(**values)


# -- the constitutional rule -------------------------------------------


def test_promotion_request_exposes_no_scalar_score_field() -> None:
    """A scalar must not be representable as promotion input."""
    fields = {f.name for f in dataclasses.fields(PromotionRequest)}
    for forbidden in ("score", "combined_score", "confidence", "novelty", "correct", "votes"):
        assert forbidden not in fields


def test_complete_evidence_promotes() -> None:
    decision = decide_promotion(_complete_request())
    assert decision["decision"] == "PROMOTE"
    assert decision["requested_level"] == "CANDIDATE"
    assert decision["granted_level"] == "CANDIDATE"
    assert decision["gate_decision_ids"] == list(CANONICAL_GATE_IDS)
    assert decision["decision_hash"] == hash_excluding(decision, "decision_hash")
    assert promoted(decision) is True


def test_low_risk_candidate_uses_policy_backed_not_required_gates() -> None:
    not_required = (
        "G05_SEARCH_COVERAGE",
        "G06_METHOD_SCOPE_DEPENDENCY",
        "G07_VALIDATION_LEAKAGE",
        "G08_ADAPTIVE_STATISTICS",
        "G09_RED_QUEEN",
        "G11_PARLIAMENT",
        "G12_INDEPENDENT_ATTESTATION",
        "G13_HUMAN_POLICY_APPROVAL",
    )
    decision = decide_promotion(
        _complete_request(
            gate_decisions=_gate_decisions(not_required=not_required),
            parliament_adjudication_id=None,
            selective_inference_report_id=None,
            dependency_cluster_ids=(),
            challenge_survived=False,
            approval_record_ids=(),
            human_approval_required=False,
        )
    )
    assert decision["decision"] == "PROMOTE"
    assert decision["granted_level"] == "CANDIDATE"
    assert decision["parliament_adjudication_id"] == ABSENT_REFERENCE
    assert decision["selective_inference_report_id"] == ABSENT_REFERENCE


def test_not_required_cannot_replace_a_substantive_higher_level_gate() -> None:
    with pytest.raises(PromotionRefused, match="substantively required"):
        decide_promotion(
            _complete_request(
                current_level=PromotionLevel.CANDIDATE,
                requested_level=PromotionLevel.LITERATURE_GROUNDED,
                gate_decisions=_gate_decisions(not_required=("G11_PARLIAMENT",)),
            )
        )


def test_gate_decisions_are_structured_hash_bound_and_complete() -> None:
    truncated = _gate_decisions()[:-1]
    with pytest.raises(PromotionRefused, match="exactly one structured"):
        decide_promotion(_complete_request(gate_decisions=truncated))

    tampered = list(_gate_decisions())
    tampered[0] = dict(tampered[0], reasons=["tampered after hashing"])
    with pytest.raises(PromotionRefused, match="decision_hash mismatch"):
        decide_promotion(_complete_request(gate_decisions=tuple(tampered)))

    duplicate_ids = [dict(decision) for decision in _gate_decisions()]
    duplicate_ids[1]["gate_id"] = duplicate_ids[0]["gate_id"]
    duplicate_ids[1]["decision_hash"] = hash_excluding(
        duplicate_ids[1], "decision_hash"
    )
    with pytest.raises(PromotionRefused, match="reuses GateDecision artifact ID"):
        decide_promotion(_complete_request(gate_decisions=tuple(duplicate_ids)))

    wrong_semantic_name = [dict(decision) for decision in _gate_decisions()]
    wrong_semantic_name[0]["name"] = "G01_POLICY_AUTHORITY"
    wrong_semantic_name[0]["decision_hash"] = hash_excluding(
        wrong_semantic_name[0], "decision_hash"
    )
    with pytest.raises(PromotionRefused, match="canonical semantic order"):
        decide_promotion(_complete_request(gate_decisions=tuple(wrong_semantic_name)))


def test_missing_grounded_evidence_is_underdetermined() -> None:
    decision = decide_promotion(_complete_request(grounded_evidence_ids=()))
    assert decision["decision"] == "UNDERDETERMINED"
    assert decision["granted_level"] is None
    assert "grounded source evidence" in decision["rationale"]


def test_missing_dependency_correction_is_underdetermined() -> None:
    assert decide_promotion(_complete_request(dependency_cluster_ids=()))["decision"] == "UNDERDETERMINED"


def test_missing_parliament_adjudication_is_underdetermined() -> None:
    assert decide_promotion(_complete_request(parliament_adjudication_id=None))["decision"] == "UNDERDETERMINED"


def test_missing_multiplicity_accounting_is_underdetermined() -> None:
    assert (
        decide_promotion(_complete_request(selective_inference_report_id=None))["decision"]
        == "UNDERDETERMINED"
    )


def test_absent_reference_sentinel_never_accompanies_a_promotion() -> None:
    """The schema forbids null ids, so absence uses a sentinel.

    A sentinel is only safe if it cannot coexist with PROMOTE; otherwise the
    record would assert an adjudication that was never produced.
    """
    for override in ({"parliament_adjudication_id": None}, {"selective_inference_report_id": None}):
        decision = decide_promotion(_complete_request(**override))
        assert ABSENT_REFERENCE in decision.values()
        assert decision["decision"] != "PROMOTE"
    promoted_decision = decide_promotion(_complete_request())
    assert ABSENT_REFERENCE not in promoted_decision.values()


def test_unchallenged_candidate_is_underdetermined() -> None:
    assert decide_promotion(_complete_request(challenge_survived=False))["decision"] == "UNDERDETERMINED"


def test_required_replication_absent_is_underdetermined() -> None:
    decision = decide_promotion(
        _complete_request(replication_status="NOT_RUN", replication_result_ids=())
    )
    assert decision["decision"] == "UNDERDETERMINED"
    assert decision["granted_level"] is None


def test_required_human_approval_absent_is_underdetermined() -> None:
    assert decide_promotion(_complete_request(approval_record_ids=()))["decision"] == "UNDERDETERMINED"


def test_incompatible_method_is_underdetermined() -> None:
    assert decide_promotion(_complete_request(method_compatible=False))["decision"] == "UNDERDETERMINED"


# -- blockers outrank everything ---------------------------------------


def test_leakage_blocks_even_with_complete_evidence() -> None:
    """Leakage invalidates; it is never absorbed as a score penalty."""
    decision = decide_promotion(_complete_request(leakage_detected=True))
    assert decision["decision"] == "BLOCKED"
    assert decision["granted_level"] is None
    assert "INVALIDATED" in decision["rationale"]


def test_failed_hard_cascade_blocks() -> None:
    decision = decide_promotion(_complete_request(hard_gate_status="FAIL"))
    assert decision["decision"] == "BLOCKED"


def test_partial_cascade_is_conditional_not_promotion() -> None:
    decision = decide_promotion(
        _complete_request(
            current_level=PromotionLevel.CANDIDATE,
            requested_level=PromotionLevel.REPLICATED,
            policy_promotion_ceiling=PromotionLevel.EMPIRICALLY_TESTED,
            conditional_grant_level=PromotionLevel.EMPIRICALLY_TESTED,
            hard_gate_status="PARTIAL",
            attestation_id="ATT-0001",
            replication_status="PARTIAL",
            unresolved_limitations=("one replication branch remains unresolved",),
        )
    )
    assert decision["decision"] == "CONDITIONAL"
    assert decision["requested_level"] == "REPLICATED"
    assert decision["granted_level"] == "EMPIRICALLY_TESTED"
    assert decision["promotion_ceiling"] == "EMPIRICALLY_TESTED"
    assert promoted(decision) is True


def test_blocker_outranks_missing_requirements() -> None:
    decision = decide_promotion(
        _complete_request(leakage_detected=True, grounded_evidence_ids=())
    )
    assert decision["decision"] == "BLOCKED"


def test_canonical_promotion_enum_has_exact_order() -> None:
    assert tuple(level.value for level in PromotionLevel) == (
        "INBOX",
        "CANDIDATE",
        "LITERATURE_GROUNDED",
        "VALIDATION_SCREENED",
        "EMPIRICALLY_TESTED",
        "REPLICATED",
    )


def test_promote_requires_requested_and_granted_equality() -> None:
    decision = decide_promotion(_complete_request())
    invalid = dict(decision)
    invalid["granted_level"] = "INBOX"
    invalid["decision_hash"] = hash_excluding(invalid, "decision_hash")
    with pytest.raises(PromotionRefused):
        validate_promotion_decision_semantics(invalid, current_level="INBOX")


def test_conditional_requires_a_non_null_strictly_lower_grant() -> None:
    common = {
        "current_level": PromotionLevel.CANDIDATE,
        "requested_level": PromotionLevel.REPLICATED,
        "policy_promotion_ceiling": PromotionLevel.EMPIRICALLY_TESTED,
        "hard_gate_status": "PARTIAL",
        "attestation_id": "ATT-0001",
        "replication_status": "PARTIAL",
        "unresolved_limitations": ("replication remains partial",),
    }
    decision = decide_promotion(_complete_request(**common))
    assert decision["decision"] == "UNDERDETERMINED"
    assert decision["granted_level"] is None

    with pytest.raises(PromotionRefused, match="current_level < granted_level < requested_level"):
        decide_promotion(
            _complete_request(
                **common,
                conditional_grant_level=PromotionLevel.REPLICATED,
            )
        )


def test_conditional_cannot_exceed_replication_ceiling() -> None:
    with pytest.raises(PromotionRefused, match="exceeds"):
        decide_promotion(
            _complete_request(
                current_level=PromotionLevel.INBOX,
                requested_level=PromotionLevel.REPLICATED,
                policy_promotion_ceiling=PromotionLevel.CANDIDATE,
                conditional_grant_level=PromotionLevel.LITERATURE_GROUNDED,
                hard_gate_status="PARTIAL",
                attestation_id="ATT-0001",
                replication_status="REPLICATED",
                unresolved_limitations=("policy ceiling remains CANDIDATE",),
            )
        )


@pytest.mark.parametrize(
    ("decision_name", "overrides"),
    [
        ("REJECT", {"parliament_rejected": True}),
        ("UNDERDETERMINED", {"grounded_evidence_ids": ()}),
        ("BLOCKED", {"leakage_detected": True}),
    ],
)
def test_non_granting_decisions_require_null(
    decision_name: str, overrides: dict
) -> None:
    decision = decide_promotion(_complete_request(**overrides))
    assert decision["decision"] == decision_name
    assert decision["granted_level"] is None

    invalid = dict(decision)
    invalid["granted_level"] = "CANDIDATE"
    invalid["decision_hash"] = hash_excluding(invalid, "decision_hash")
    with pytest.raises(PromotionRefused):
        validate_promotion_decision_semantics(invalid, current_level="INBOX")


@pytest.mark.parametrize(
    "legacy_level",
    ["PILOT", "HYPOTHESIS_PASSPORT_ONLY", "SUPPORTED", "NONE"],
)
def test_legacy_levels_are_not_runtime_aliases(legacy_level: str) -> None:
    with pytest.raises(PromotionRefused, match="not a canonical"):
        decide_promotion(_complete_request(requested_level=legacy_level))


def test_legacy_level_migration_requires_record_specific_review() -> None:
    with pytest.raises(LegacyPromotionLevelReviewRequired) as excinfo:
        migrate_legacy_promotion_level("PILOT")
    assert LEGACY_PROMOTION_LEVEL_REVIEW_REQUIRED in str(excinfo.value)
    fixture_path = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "contracts"
        / "fixtures"
        / "promotion-level-review.json"
    )
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    migration_schema = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "migrations"
            / "contracts"
            / "migration-record.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(migration_schema)
    errors = list(
        Draft202012Validator(
            migration_schema,
            format_checker=Draft202012Validator.FORMAT_CHECKER,
        ).iter_errors(fixture)
    )
    assert errors == []
    assert fixture["source_value_hash"] == sha256_of_payload(fixture["source_level"])
    assert fixture["target_value_hash"] == sha256_of_payload(fixture["target_level"])
    assert fixture["migration_hash"] == hash_excluding(fixture, "migration_hash")
    assert migrate_legacy_promotion_level(
        fixture["source_level"], migration_record=fixture
    ) == fixture["target_level"]

    tampered = dict(fixture, target_level="CANDIDATE")
    with pytest.raises(LegacyPromotionLevelReviewRequired, match="hash mismatch"):
        migrate_legacy_promotion_level(
            tampered["source_level"], migration_record=tampered
        )


def test_downgrade_or_same_level_requires_separate_reassessment() -> None:
    for requested in (PromotionLevel.CANDIDATE, PromotionLevel.INBOX):
        with pytest.raises(ReassessmentRequired, match="reassessment"):
            decide_promotion(
                _complete_request(
                    current_level=PromotionLevel.CANDIDATE,
                    requested_level=requested,
                )
            )


def test_idempotency_key_must_bind_the_sealed_request() -> None:
    with pytest.raises(PromotionRefused, match="idempotency_key"):
        decide_promotion(_complete_request(idempotency_key="unbound-key"))


# -- dependency correction ---------------------------------------------


def test_correlated_evidence_counts_as_one_unit() -> None:
    """Five reanalyses of one dataset are one independent unit."""
    cluster = build_dependency_cluster(
        run_id="RUN-0001",
        evidence_ids=["EV-1", "EV-2", "EV-3", "EV-4", "EV-5"],
        dependency_types=["SAME_DATASET"],
        representative_evidence_ids=["EV-1"],
        independence_confidence=0.9,
        rationale="all five reanalyze dataset DF-001",
        provenance_refs=["DF-001"],
        independent_unit_count=1,
    )
    assert cluster["support_count_raw"] == 5
    assert cluster["support_count_adjusted"] == 1


def test_adjustment_may_only_reduce_support() -> None:
    with pytest.raises(ValueError):
        build_dependency_cluster(
            run_id="RUN-0001",
            evidence_ids=["EV-1"],
            dependency_types=["SAME_COHORT"],
            representative_evidence_ids=["EV-1"],
            independence_confidence=0.5,
            rationale="inflation attempt",
            provenance_refs=["DF-001"],
            independent_unit_count=1,
            support_count_adjusted=9,
        )


def test_empty_cluster_is_refused() -> None:
    with pytest.raises(ValueError):
        build_dependency_cluster(
            run_id="RUN-0001",
            evidence_ids=[],
            dependency_types=["UNKNOWN"],
            representative_evidence_ids=[],
            independence_confidence=1.0,
            rationale="empty",
            provenance_refs=["DF-001"],
        )


def test_independent_units_are_counted_per_cluster() -> None:
    assert adjusted_support_count([["EV-1", "EV-2"], ["EV-3"], []]) == 2


def test_corrected_support_sums_adjusted_counts() -> None:
    clusters = [
        build_dependency_cluster(
            run_id="RUN-0001",
            evidence_ids=["EV-1", "EV-2"],
            dependency_types=["SAME_TEAM_SERIES"],
            representative_evidence_ids=["EV-1"],
            independence_confidence=0.7,
            rationale="same lab",
            provenance_refs=["DF-001"],
            independent_unit_count=1,
        ),
        build_dependency_cluster(
            run_id="RUN-0001",
            evidence_ids=["EV-3"],
            dependency_types=["UNKNOWN"],
            representative_evidence_ids=["EV-3"],
            independence_confidence=1.0,
            rationale="separate cohort",
            provenance_refs=["DF-002"],
            independent_unit_count=1,
        ),
    ]
    assert corrected_support(clusters) == 2
