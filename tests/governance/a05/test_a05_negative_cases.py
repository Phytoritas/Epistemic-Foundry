"""The 24 A05 negative/adversarial contract cases (docs/v4_a05 registry)."""

from __future__ import annotations


import pytest

from epistemic_foundry.governance.promotion import PromotionLevel
from epistemic_foundry.governance.evolution_authority import (
    EvolutionAuthorityError,
    resolve_references,
    verify_approval_independence,
    verify_attestor_independence,
)
from epistemic_foundry.governance.promotion import (
    MissingEffectReceipt,
    PromotionCommitter,
    PromotionIdempotencyConflict,
    PromotionRefused,
    PromotionRevisionConflict,
    decide_promotion,
)
from epistemic_foundry.verifier_firewall import build_holdout_manifest
from tests.governance.a05.test_a05_gate_registry import resolved_refs
from tests.test_integration_forge_cycle import (
    _candidate,
    _decision_and_effect,
    _promotion_gate_decisions,
    _promotion_request,
)


def _failed_gate_decisions(failed_gate: str) -> tuple[dict, ...]:
    from epistemic_foundry.domain.hashing import hash_excluding

    decisions = []
    for decision in _promotion_gate_decisions():
        record = dict(decision)
        if record["name"] == failed_gate:
            record["status"] = "FAIL"
            record["decision"] = "FAIL"
            record["reasons"] = ["substantive gate evidence failed"]
            record["decision_hash"] = hash_excluding(record, "decision_hash")
        decisions.append(record)
    return tuple(decisions)


def _refused_or_blocked(request) -> None:
    """A non-waivable failure must refuse or emit a non-granting decision."""

    try:
        decision = decide_promotion(request)
    except PromotionRefused:
        return
    assert decision["decision"] in {"BLOCKED", "REJECT", "UNDERDETERMINED"}
    assert decision["granted_level"] is None


def test_a05_neg_001_floating_workflow_reference_fails() -> None:
    outcome = resolve_references(
        resolved_refs(workflow={"exact_version_or_revision": "main"})
    )
    assert outcome["status"] == "FAIL"
    assert any("floating reference 'main'" in reason for reason in outcome["reasons"])
    assert not any("HEAD resolved" in reason for reason in outcome["reasons"])


def test_a05_neg_002_content_hash_mismatch_fails() -> None:
    outcome = resolve_references(
        resolved_refs(schema_bundle={"content_hash_matches": False})
    )
    assert outcome["status"] == "FAIL"
    assert any("do not match the sealed content_hash" in r for r in outcome["reasons"])


def test_a05_neg_003_unavailable_licensed_snapshot_blocks() -> None:
    outcome = resolve_references(
        resolved_refs(corpus_evidence_snapshot={"resolved_bytes_available": False})
    )
    assert outcome["status"] == "BLOCKED"
    assert any("no replacement is selected" in r for r in outcome["reasons"])


def test_a05_neg_004_undeclared_set_sort_is_spec_gap() -> None:
    outcome = resolve_references(
        resolved_refs(statistical_plan={"set_semantic_sort_declared": False})
    )
    assert outcome["status"] == "SPEC_GAP"


def test_a05_neg_005_prompt_bundle_mutation_under_same_run_fails() -> None:
    outcome = resolve_references(
        resolved_refs(prompt_bundle={"content_hash_matches": False})
    )
    assert outcome["status"] == "FAIL"


def test_a05_neg_006_evaluator_mutation_is_a_non_waivable_g02_failure() -> None:
    request = _promotion_request(
        gate_decisions=_failed_gate_decisions("G02_EVALUATOR_HOLDOUT_FIREWALL")
    )
    _refused_or_blocked(request)


def test_a05_neg_007_candidate_holdout_access_is_denied() -> None:
    with pytest.raises(Exception) as raised:
        build_holdout_manifest(
            dataset_or_fixture_ids=("DATA-HIDDEN-1",),
            split_strategy="sealed-fixture",
            selection_cutoff="2026-01-01",
            access_principal_ids=("PRIN-VALIDATOR",),
            unblinding_policy="never during candidate generation",
            rotation_policy="rotate after exposure",
            candidate_access=True,
            holdout_manifest_id="HO-NEG-007",
        )
    assert not isinstance(raised.value, AssertionError)


def test_a05_neg_008_scalar_only_promotion_is_refused() -> None:
    request = _promotion_request(
        grounded_evidence_ids=(),
        reasons=("combined fitness score 0.99",),
    )
    decision = decide_promotion(request)
    assert decision["decision"] == "UNDERDETERMINED"
    assert decision["granted_level"] is None
    assert any(
        "grounded source evidence" in r for r in decision["unresolved_limitations"]
    )


def test_a05_neg_009_count_reconciliation_failure_blocks() -> None:
    request = _promotion_request(
        gate_decisions=_failed_gate_decisions("G03_SCHEMA_LINEAGE_COUNT")
    )
    _refused_or_blocked(request)


def test_a05_neg_010_missing_receipts_are_refused() -> None:
    with pytest.raises(PromotionRefused):
        decide_promotion(_promotion_request(artifact_receipt_ids=()))


def test_a05_neg_011_unsearched_relabeling_fails_g05() -> None:
    request = _promotion_request(
        requested_level=PromotionLevel.LITERATURE_GROUNDED,
        gate_decisions=_promotion_gate_decisions(
            not_required=("G05_SEARCH_COVERAGE", "G12_INDEPENDENT_ATTESTATION")
        ),
    )
    with pytest.raises(PromotionRefused) as raised:
        decide_promotion(request)
    assert "G05_SEARCH_COVERAGE" in str(raised.value)


def test_a05_neg_012_missing_adaptive_statistics_cannot_promote() -> None:
    request = _promotion_request(selective_inference_report_id=None)
    decision = decide_promotion(request)
    assert decision["decision"] == "UNDERDETERMINED"
    assert decision["granted_level"] is None

    high = _promotion_request(
        requested_level=PromotionLevel.LITERATURE_GROUNDED,
        gate_decisions=_promotion_gate_decisions(
            not_required=("G08_ADAPTIVE_STATISTICS", "G12_INDEPENDENT_ATTESTATION")
        ),
    )
    with pytest.raises(PromotionRefused):
        decide_promotion(high)


def test_a05_neg_013_replicated_request_without_ceiling_inputs_fails() -> None:
    request = _promotion_request(
        current_level=PromotionLevel.EMPIRICALLY_TESTED,
        requested_level=PromotionLevel.REPLICATED,
        attestation_id="ATT-1",
        replication_status="NOT_RUN",
        replication_result_ids=(),
    )
    decision = decide_promotion(request)
    assert decision["decision"] == "UNDERDETERMINED"
    assert decision["granted_level"] is None
    assert decision["promotion_ceiling"] == PromotionLevel.EMPIRICALLY_TESTED

    with pytest.raises(PromotionRefused):
        decide_promotion(
            _promotion_request(
                replication_status="NOT_RUN", replication_result_ids=("REP-1",)
            )
        )


def test_a05_neg_014_core_replication_failure_rejects_and_lowers() -> None:
    request = _promotion_request(
        current_level=PromotionLevel.EMPIRICALLY_TESTED,
        requested_level=PromotionLevel.REPLICATED,
        attestation_id="ATT-1",
        replication_status="FAILED",
    )
    decision = decide_promotion(request)
    assert decision["decision"] == "REJECT"
    assert decision["granted_level"] is None
    assert decision["promotion_ceiling"] == PromotionLevel.LITERATURE_GROUNDED


def test_a05_neg_015_parliament_majority_cannot_override_a_failed_gate() -> None:
    request = _promotion_request(
        gate_decisions=_failed_gate_decisions("G05_SEARCH_COVERAGE"),
        reasons=("Parliament majority recommends promotion",),
    )
    _refused_or_blocked(request)


def test_a05_neg_016_non_independent_attestor_is_rejected() -> None:
    context = {
        "candidate_generator_ids": ("AGENT-GEN-1",),
        "candidate_implementer_ids": ("AGENT-IMPL-1",),
        "first_adjudicator_ids": ("AGENT-JUDGE-1",),
        "prompt_lineage_actor_ids": ("AGENT-PROMPT-1",),
        "promotion_commit_authority_ids": ("SERVICE-COMMIT-1",),
    }
    verify_attestor_independence("AGENT-ATTESTOR-9", context)
    for conflicted in (
        "AGENT-GEN-1",
        "AGENT-IMPL-1",
        "AGENT-JUDGE-1",
        "AGENT-PROMPT-1",
        "SERVICE-COMMIT-1",
    ):
        with pytest.raises(EvolutionAuthorityError) as raised:
            verify_attestor_independence(conflicted, context)
        assert raised.value.code == "ATTESTOR_INDEPENDENCE_VIOLATION"


def test_a05_neg_017_self_approval_is_forbidden() -> None:
    verify_approval_independence("HUMAN-REVIEWER-1", ("AGENT-MAKER-1",))
    with pytest.raises(EvolutionAuthorityError) as raised:
        verify_approval_independence("AGENT-MAKER-1", ("AGENT-MAKER-1",))
    assert raised.value.code == "SELF_APPROVAL_FORBIDDEN"


def test_a05_neg_018_approval_cannot_waive_a_non_waivable_gate() -> None:
    request = _promotion_request(
        gate_decisions=_failed_gate_decisions("G02_EVALUATOR_HOLDOUT_FIREWALL"),
        approval_record_ids=("APR-1", "APR-2"),
    )
    _refused_or_blocked(request)


def test_a05_neg_019_required_approval_cannot_be_silently_absent() -> None:
    request = _promotion_request(human_approval_required=True, approval_record_ids=())
    decision = decide_promotion(request)
    assert decision["decision"] == "UNDERDETERMINED"
    assert decision["granted_level"] is None
    assert any("human approval" in r for r in decision["unresolved_limitations"])


def test_a05_neg_020_commit_without_effect_receipt_fails() -> None:
    decision, _effect = _decision_and_effect()
    with pytest.raises(MissingEffectReceipt):
        PromotionCommitter().commit(
            _candidate(), decision, expected_revision=1, effect_receipt=None
        )


def test_a05_neg_021_idempotency_key_reuse_with_new_request_conflicts() -> None:
    committer = PromotionCommitter()
    decision, effect = _decision_and_effect()
    committer.commit(_candidate(), decision, expected_revision=1, effect_receipt=effect)

    altered = dict(decision)
    altered["rationale"] = "a different canonical request"
    from epistemic_foundry.domain.hashing import hash_excluding

    altered["decision_hash"] = hash_excluding(altered, "decision_hash")
    with pytest.raises(PromotionIdempotencyConflict):
        committer.commit(
            _candidate(), altered, expected_revision=1, effect_receipt=effect
        )


def test_a05_neg_022_same_request_retry_replays_without_a_second_effect() -> None:
    committer = PromotionCommitter()
    decision, effect = _decision_and_effect()
    first = committer.commit(
        _candidate(), decision, expected_revision=1, effect_receipt=effect
    )
    second = committer.commit(
        _candidate(), decision, expected_revision=1, effect_receipt=effect
    )

    assert first["replayed"] is False
    assert second["replayed"] is True
    assert second["candidate"] == first["candidate"]
    assert second["effect_receipt_id"] == first["effect_receipt_id"]


def test_a05_neg_023_crash_between_cas_and_receipt_stays_unknown_then_reconciles() -> (
    None
):
    committer = PromotionCommitter()
    decision, effect = _decision_and_effect()
    candidate = _candidate()

    with pytest.raises(MissingEffectReceipt):
        committer.commit(candidate, decision, expected_revision=1, effect_receipt=None)
    assert candidate == _candidate()

    reconciled = committer.commit(
        candidate, decision, expected_revision=1, effect_receipt=effect
    )
    assert reconciled["state_changed"] is True


def test_a05_neg_024_prior_revisions_cannot_be_overwritten_in_place() -> None:
    decision, effect = _decision_and_effect()
    with pytest.raises(PromotionRevisionConflict):
        PromotionCommitter().commit(
            {**_candidate(), "revision": 2},
            decision,
            expected_revision=2,
            effect_receipt=effect,
        )
