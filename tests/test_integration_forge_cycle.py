"""End-to-end: the components must compose into one honest research cycle.

Unit tests prove each refusal in isolation. This file proves the refusals still
hold when the components are wired together, which is where a boundary usually
leaks: a cascade that reports PARTIAL must actually stop promotion, and a
session must not reach Export on gates the Parliament never saw.
"""

from __future__ import annotations

import pytest

from epistemic_foundry.domain.status import ForgePhase, WorkClass
from epistemic_foundry.evidence_parliament import build_adjudication
from epistemic_foundry.foundry_kernel import ForgeKernel, TransitionRejected
from epistemic_foundry.foundry_kernel.gates import GateSpec, evaluate_gate, gate_decision
from epistemic_foundry.governance import PromotionRequest, decide_promotion
from epistemic_foundry.noetic_ledger import NoeticLedger
from epistemic_foundry.red_queen_lab import build_challenge_result, survived_challenges
from epistemic_foundry.validation_bay import (
    aggregate_cascade_status,
    build_cascade_plan,
    build_stage_result,
)
from epistemic_foundry.verifier_firewall import (
    VerifierFirewall,
    build_evaluator_bundle,
    build_holdout_manifest,
)

POLICY_HASH = "sha256:" + "c" * 64
CORPUS_HASH = "sha256:" + "d" * 64

STAGES = (
    {
        "stage_id": "S0",
        "stage_class": "contract",
        "entry_rule": "always",
        "pass_rule": "contracts valid",
        "failure_action": "reject",
        "budget_fraction": 0.1,
    },
    {
        "stage_id": "S5",
        "stage_class": "holdout",
        "entry_rule": "after S0",
        "pass_rule": "preregistered threshold met",
        "failure_action": "restrict",
        "budget_fraction": 0.5,
    },
)


@pytest.fixture()
def kernel(tmp_path) -> ForgeKernel:
    return ForgeKernel(NoeticLedger(tmp_path / "ledger.jsonl"))


@pytest.fixture()
def firewall() -> VerifierFirewall:
    holdout = build_holdout_manifest(
        dataset_or_fixture_ids=["DS-hidden"],
        split_strategy="temporal",
        selection_cutoff="2026-01-01",
        access_principal_ids=["PRIN-validator"],
        unblinding_policy="post-promotion only",
        rotation_policy="rotate on leak",
    )
    bundle = build_evaluator_bundle(
        version="1.0.0",
        evaluator_artifact_ids=["EVAL-1"],
        metric_ids=["METRIC-1"],
        holdout_manifest_id=holdout["holdout_manifest_id"],
        environment_manifest_id="ENV-1",
        policy_bundle_id="POL-1",
    )
    return VerifierFirewall(bundle, holdout)


def _advance(kernel: ForgeKernel, state: dict, to_phase: ForgePhase, **kwargs) -> dict:
    request = kernel.build_request(
        state,
        to_phase=to_phase,
        actor_id="AG-1",
        actor_role="bounded_maker",
        reason=f"advance to {to_phase}",
        gate_result_ids=kwargs.get("gate_result_ids", ()),
    )
    return kernel.apply_transition(state, request, gate_decisions=kwargs.get("gate_decisions", ()))


def _reach_gate(kernel: ForgeKernel) -> dict:
    state = kernel.open_session(
        workspace_id="WS-1",
        run_spec_id="RUN-1",
        work_class=WorkClass.E3,
        policy_hash=POLICY_HASH,
        corpus_snapshot_hash=CORPUS_HASH,
    )
    for phase in (ForgePhase.FRAME, ForgePhase.OBSERVE, ForgePhase.REASON, ForgePhase.GATE):
        state = _advance(kernel, state, phase)
    return state


def _cascade(statuses: dict[str, str]) -> tuple[dict, str]:
    plan = build_cascade_plan(
        candidate_class="hypothesis",
        stages=STAGES,
        max_total_budget=100.0,
        early_stop_policy="stop on hard failure",
    )
    results = [
        build_stage_result(
            cascade_plan_id=plan["cascade_plan_id"],
            candidate_id="CAND-1",
            stage_id=stage_id,
            status=status,
            metric_values={"m": 1.0},
            uncertainty_summary="95% CI [0.9, 1.1]",
            started_at="2026-07-27T00:00:00+00:00",
        )
        for stage_id, status in statuses.items()
    ]
    return plan, aggregate_cascade_status(plan, results)


def test_full_cycle_promotes_only_with_complete_evidence(kernel: ForgeKernel, firewall: VerifierFirewall) -> None:
    """The honest happy path, end to end."""
    firewall.verify_self()
    gated = _reach_gate(kernel)

    _, cascade_status = _cascade({"S0": "PASS", "S5": "PASS"})
    assert cascade_status == "PASS"

    passing_gate = gate_decision(
        evaluate_gate(GateSpec("evidence_grounding", ("evidence_ids",)), {"evidence_ids": ["EV-1"]}),
        run_id="RUN-1",
        policy_version="4.0.0",
        inputs={"evidence_ids": ["EV-1"]},
    )
    adjudication = build_adjudication(
        run_id="RUN-1",
        hypothesis_id="HYP-1",
        gate_decisions=[passing_gate],
        brief_ids=["CB-1"],
        cross_examination_ids=["CX-1"],
        verdict="SUPPORTED",
        promotion_recommendation="CANDIDATE",
        rationale="support survives cross-examination",
        strongest_support_id="EV-1",
        strongest_counterevidence_id="EV-2",
    )

    exported = _advance(
        kernel,
        gated,
        ForgePhase.EXPORT,
        gate_result_ids=[passing_gate["gate_id"]],
        gate_decisions=[passing_gate],
    )
    assert exported["phase"] == "E"

    decision = decide_promotion(
        PromotionRequest(
            candidate_id="CAND-1",
            requested_level="SUPPORTED",
            hard_gate_status=cascade_status,
            fitness_vector_id="FV-1",
            parliament_adjudication_id=adjudication["adjudication_id"],
            selective_inference_report_id="SIR-1",
            replication_result_ids=("REP-1",),
            approval_record_ids=("APR-1",),
            grounded_evidence_ids=("EV-1",),
            dependency_cluster_ids=("EDC-1",),
            challenge_survived=True,
        )
    )
    assert decision["decision"] == "PROMOTE"
    kernel.ledger.verify()


def test_partial_cascade_blocks_promotion_end_to_end(kernel: ForgeKernel) -> None:
    """An unfinished cascade must not yield promotion, however good the rest is."""
    _, cascade_status = _cascade({"S0": "PASS"})
    assert cascade_status == "PARTIAL"

    decision = decide_promotion(
        PromotionRequest(
            candidate_id="CAND-1",
            requested_level="SUPPORTED",
            hard_gate_status=cascade_status,
            fitness_vector_id="FV-1",
            parliament_adjudication_id="ADJ-1",
            selective_inference_report_id="SIR-1",
            replication_result_ids=("REP-1",),
            approval_record_ids=("APR-1",),
            grounded_evidence_ids=("EV-1",),
            dependency_cluster_ids=("EDC-1",),
            challenge_survived=True,
        )
    )
    assert decision["decision"] == "CONDITIONAL"
    assert decision["granted_level"] == "NONE"


def test_failed_cascade_blocks_promotion_end_to_end() -> None:
    _, cascade_status = _cascade({"S0": "FAIL"})
    assert cascade_status == "FAIL"
    decision = decide_promotion(
        PromotionRequest(
            candidate_id="CAND-1",
            requested_level="SUPPORTED",
            hard_gate_status=cascade_status,
            fitness_vector_id="FV-1",
            parliament_adjudication_id="ADJ-1",
            selective_inference_report_id="SIR-1",
            replication_result_ids=("REP-1",),
            approval_record_ids=("APR-1",),
            grounded_evidence_ids=("EV-1",),
            dependency_cluster_ids=("EDC-1",),
            challenge_survived=True,
        )
    )
    assert decision["decision"] == "BLOCKED"


def test_leakage_invalidates_the_cycle(firewall: VerifierFirewall) -> None:
    """Holdout leakage blocks promotion even with a fully passing cascade."""
    touched = firewall.leakage_invalidates(["DS-hidden"])
    assert touched == ["DS-hidden"]
    _, cascade_status = _cascade({"S0": "PASS", "S5": "PASS"})
    decision = decide_promotion(
        PromotionRequest(
            candidate_id="CAND-1",
            requested_level="SUPPORTED",
            hard_gate_status=cascade_status,
            fitness_vector_id="FV-1",
            parliament_adjudication_id="ADJ-1",
            selective_inference_report_id="SIR-1",
            replication_result_ids=("REP-1",),
            approval_record_ids=("APR-1",),
            grounded_evidence_ids=("EV-1",),
            dependency_cluster_ids=("EDC-1",),
            challenge_survived=True,
            leakage_detected=bool(touched),
        )
    )
    assert decision["decision"] == "BLOCKED"


def test_export_is_refused_without_the_gate_the_parliament_saw(kernel: ForgeKernel) -> None:
    """A session cannot leave Gate on evidence nobody adjudicated."""
    gated = _reach_gate(kernel)
    with pytest.raises(TransitionRejected):
        _advance(kernel, gated, ForgePhase.EXPORT)


def _challenge(outcome: str, *, artifacts=("REPRO-1",)) -> dict:
    return build_challenge_result(
        challenge_genome_id="CG-1",
        target_candidate_id="CAND-1",
        stage_result_id="SER-1",
        outcome=outcome,
        severity="major",
        observed_effect=f"observed {outcome.lower()}",
        reproduction_artifact_ids=artifacts,
    )


def _promote_with(challenge_results: list[dict]) -> dict:
    _, cascade_status = _cascade({"S0": "PASS", "S5": "PASS"})
    return decide_promotion(
        PromotionRequest(
            candidate_id="CAND-1",
            requested_level="SUPPORTED",
            hard_gate_status=cascade_status,
            fitness_vector_id="FV-1",
            parliament_adjudication_id="ADJ-1",
            selective_inference_report_id="SIR-1",
            replication_result_ids=("REP-1",),
            approval_record_ids=("APR-1",),
            grounded_evidence_ids=("EV-1",),
            dependency_cluster_ids=("EDC-1",),
            challenge_survived=survived_challenges("CAND-1", challenge_results),
        )
    )


def test_unchallenged_candidate_cannot_promote_end_to_end() -> None:
    """Red Queen survival feeds promotion: no challenge means no credit."""
    decision = _promote_with([])
    assert decision["decision"] == "UNDERDETERMINED"
    assert "Red Queen challenge" in decision["rationale"]


def test_refuted_candidate_cannot_promote_end_to_end() -> None:
    decision = _promote_with([_challenge("SURVIVED"), _challenge("REFUTED")])
    assert decision["decision"] == "UNDERDETERMINED"


def test_inconclusive_challenge_cannot_promote_end_to_end() -> None:
    """A crashed adversary must not be laundered into survival."""
    decision = _promote_with([_challenge("INCONCLUSIVE")])
    assert decision["decision"] == "UNDERDETERMINED"


def test_surviving_every_challenge_promotes_end_to_end() -> None:
    decision = _promote_with([_challenge("SURVIVED"), _challenge("SURVIVED")])
    assert decision["decision"] == "PROMOTE"


def test_every_transition_is_recorded_in_the_ledger(kernel: ForgeKernel) -> None:
    gated = _reach_gate(kernel)
    events = list(kernel.ledger.events())
    # one open_session event plus four phase transitions
    assert len(events) == 5
    assert events[0]["event_type"] == "forge.session.opened"
    assert events[-1]["event_type"] == "forge.phase.r_to_g"
    assert gated["revision"] == 4
    kernel.ledger.verify()
