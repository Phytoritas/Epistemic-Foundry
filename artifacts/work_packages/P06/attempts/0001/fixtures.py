"""Fixtures for the P06 no-majority promotion referral gate suites.

Every organ receipt the gate composes is produced by the *sealed owning gate* —
the P05 evolution-promotion Parliament and the V05 validation-cascade advancement
gate — driven over inputs each in turn built through their own sealed owning
surfaces (Q05 statistical admissibility, the Red Queen Lab, the validation
cascade, the replication surface).  A receipt an owner would refuse would test the
fixture rather than the P06 gate, and building through the owners means a
canonical change breaks these fixtures instead of letting them drift.

Importing ``validation.v4_v05`` *here* is deliberate and safe: the fixtures live
outside ``src/epistemic_foundry`` and so are outside the component import graph
the boundary-cycle check scans, so composing the real V05 gate to mint a genuine
advancement receipt does not create the ``parliament``↔``validation`` cycle the
runtime P06 module is careful to avoid.
"""

from __future__ import annotations

from typing import Any

from epistemic_foundry.domain.hashing import hash_excluding
from epistemic_foundry.domain.vocabularies import PROMOTION_LADDER
from epistemic_foundry.evaluation.fitness import (
    FITNESS_DIMENSIONS,
    build_fitness_vector,
)
from epistemic_foundry.evaluation.v4_q05 import gate as q05
from epistemic_foundry.evidence_parliament.adjudication import build_adjudication
from epistemic_foundry.parliament.v4_p05 import derive_promotion_parliament
from epistemic_foundry.parliament.v4_p06 import gate as p06
from epistemic_foundry.red_queen_lab import challenges as rq
from epistemic_foundry.retrieval.v4_o05 import adversarial_lanes
from epistemic_foundry.statistics.multiplicity import build_multiplicity_adjustment
from epistemic_foundry.statistics.search_record import build_search_statistics_record
from epistemic_foundry.statistics.selective import build_selective_inference_report
from epistemic_foundry.statistics.sequential import build_sequential_ledger
from epistemic_foundry.validation.v4_v05 import derive_validation_advancement
from epistemic_foundry.validation_bay.cascade import (
    build_cascade_plan,
    build_stage_result,
)
from epistemic_foundry.validation_bay.replication import build_replication_plan
from epistemic_foundry.verifier_firewall.firewall import (
    build_evaluator_bundle,
    build_holdout_manifest,
)

CANDIDATE_ID = "CAND-P06-1"
OTHER_CANDIDATE_ID = "CAND-P06-2"
CREATED_AT = "2026-08-02T00:00:00+00:00"
A_HASH = "sha256:" + "a" * 64
B_HASH = "sha256:" + "b" * 64

RUN_ID = "RUN-P06-1"
FAMILY_ID = "FAM-P06-1"
EVALUATOR_ID = "EVAL-P06-1"

#: A governor principal/role that is *not* candidate-generating, so the gate's
#: authority guard permits it to drive the referral.
GOVERNOR_ID = "gov-p06-1"
GOVERNOR_ROLE = "evolution_governor"

#: A candidate-generating role the authority guard must refuse.
CANDIDATE_ROLE = "hypothesis_mutator"

#: The independent attestor and the makers it must be independent of.
ATTESTOR_ID = "attestor-p06-1"
MAKER_ID = "maker-p06-1"

TOP_LEVEL = PROMOTION_LADDER[-1]
REQUESTED_LEVEL = "EMPIRICALLY_TESTED"


# --------------------------------------------------------------------------- #
# Shared statistical admissibility (one genuine Q05 ADMIT receipt)
# --------------------------------------------------------------------------- #
def _fitness_vector(candidate_id: str, *, admit: bool = True) -> dict[str, Any]:
    if admit:
        return build_fitness_vector(
            candidate_id=candidate_id,
            hard_gate_status=q05.hard_gate_pass_token(),
            hard_gate_failures=[],
            dimensions={name: 0.9 for name in FITNESS_DIMENSIONS},
            uncertainty={name: 0.05 for name in FITNESS_DIMENSIONS},
            evidence_receipt_ids=["ER-P06-1"],
            pareto_rank=0,
            domination_count=0,
            fitness_vector_id="FV-P06-1",
            computed_at=CREATED_AT,
        )
    return build_fitness_vector(
        candidate_id=candidate_id,
        hard_gate_status="FAIL",
        hard_gate_failures=["a_failed_dimension"],
        dimensions={name: 0.9 for name in FITNESS_DIMENSIONS},
        uncertainty={name: 0.05 for name in FITNESS_DIMENSIONS},
        evidence_receipt_ids=["ER-P06-1"],
        pareto_rank=0,
        domination_count=0,
        fitness_vector_id="FV-P06-REFUSED",
        computed_at=CREATED_AT,
    )


def _holdout_manifest() -> dict[str, Any]:
    return build_holdout_manifest(
        evaluator_id=EVALUATOR_ID,
        split_strategy="fixed_nested_holdout",
        public_partition_refs=["PUB-1"],
        hidden_partition_handles=["HID-P06-1"],
        ood_partition_handles=["OOD-P06-1"],
        adversarial_partition_handles=["ADV-P06-1"],
        content_hashes=[A_HASH],
        acl_policy_hash=B_HASH,
        log_redaction_policy="redact_all_hidden",
        cache_isolation_policy="per_run_isolated",
        holdout_id=EVALUATOR_ID,
        sealed_at=CREATED_AT,
    )


def _evaluator_bundle() -> dict[str, Any]:
    return build_evaluator_bundle(
        evaluator_version="1.0.0",
        code_artifact_id="CA-P06-1",
        code_hash=A_HASH,
        metric_contract_hash=A_HASH,
        environment_digest=A_HASH,
        dependency_lock_hash=A_HASH,
        data_contract_hash=A_HASH,
        policy_bundle_hash=A_HASH,
        qualification_report_id="QR-P06-1",
        holdout_manifest_id=EVALUATOR_ID,
        evaluator_id=EVALUATOR_ID,
        sealed_at=CREATED_AT,
    )


def _selective_report(candidate_id: str) -> dict[str, Any]:
    return build_selective_inference_report(
        candidate_id=candidate_id,
        selection_mechanism="argmax_over_generation",
        selection_events=["SE-1"],
        naive_estimate=0.5,
        bias_corrected_estimate=0.4,
        correction_method="conditional_shrinkage",
        uncertainty_interval=[0.2, 0.6],
        candidates_considered=3,
        replication_count=2,
        report_id=f"SIR-P06-{candidate_id}",
    )


def _search_statistics(report: dict[str, Any], candidate_id: str) -> dict[str, Any]:
    return build_search_statistics_record(
        evolution_run_id=RUN_ID,
        family_id=FAMILY_ID,
        candidate_id=candidate_id,
        sequential_ledger=build_sequential_ledger(
            family_id=FAMILY_ID,
            testing_policy="alpha_spending",
            initial_budget=0.05,
            entries=[
                {
                    "test_id": "T1",
                    "generation": 0,
                    "statistic": 2.4,
                    "threshold": 1.96,
                    "spent": 0.01,
                    "decision": "continue",
                }
            ],
            selection_events=["SE-1"],
            ledger_id="STL-P06-1",
        ),
        multiplicity_adjustment=build_multiplicity_adjustment(
            family_id=FAMILY_ID,
            method="BH_FDR",
            raw_test_count=5,
            target_error_rate=0.05,
            adjusted_results=[
                {
                    "test_id": "T1",
                    "raw_value": 0.008,
                    "adjusted_value": 0.04,
                    "decision": "reject_null",
                }
            ],
            assumptions=["positive_regression_dependence"],
            adjustment_id="MTA-P06-1",
        ),
        selective_report=report,
        hidden_exposure_log_id="HEL-P06-1",
        candidate_lineage_id="LIN-P06-1",
        replication_result_id="RR-P06-1",
        record_id=f"SSR-P06-{candidate_id}",
        created_at=CREATED_AT,
    )


def admissibility_receipt(
    *, candidate_id: str = CANDIDATE_ID, admit: bool = True
) -> dict[str, Any]:
    """A genuine Q05 selective-admissibility receipt (ADMIT by default)."""
    report = _selective_report(candidate_id)
    return q05.derive_selective_admissibility(
        candidate_id=candidate_id,
        fitness_vector=_fitness_vector(candidate_id, admit=admit),
        evaluator_bundle=_evaluator_bundle(),
        holdout_manifest=_holdout_manifest(),
        search_statistics=_search_statistics(report, candidate_id),
        selective_report=report,
        requesting_principal_id=GOVERNOR_ID,
        requesting_role=GOVERNOR_ROLE,
        holdout_read_principal_ids=[GOVERNOR_ID],
        created_at=CREATED_AT,
    )


# --------------------------------------------------------------------------- #
# P05 parliament organ (a genuine CONVENE receipt)
# --------------------------------------------------------------------------- #
def _lineage(candidate_id: str) -> dict[str, Any]:
    return {
        "lineage_id": "LIN-P06-1",
        "candidate_id": candidate_id,
        "parent_ids": ["PARENT-1"],
        "inspiration_ids": [],
        "mutation_operator_ids": ["OP-1"],
        "crossover_parent_ids": [],
        "generation": 3,
        "island_id": "ISLAND-1",
        "ancestor_hashes": [A_HASH],
        "created_at": CREATED_AT,
    }


def _adjudication(candidate_id: str, minority_ids: list[str]) -> dict[str, Any]:
    return build_adjudication(
        run_id=RUN_ID,
        hypothesis_id=candidate_id,
        gate_decisions=[
            {"gate_id": "G11_PARLIAMENT", "name": "parliament", "status": "PASS"},
            {"gate_id": "G09_RED_QUEEN", "name": "red_queen", "status": "PASS"},
        ],
        brief_ids=["BRIEF-1"],
        cross_examination_ids=["CX-1"],
        verdict="SUPPORTED",
        promotion_recommendation="INBOX",
        rationale="the deliberation, recorded for review",
        strongest_support_id="EV-SUP-1",
        strongest_counterevidence_id="EV-CNT-1",
        minority_report_ids=minority_ids,
        adjudication_id="ADJ-P06-1",
        created_at=CREATED_AT,
        refuse_override=True,
    )


def minority_report(
    *, minority_report_id: str = "MIN-P06-1", **overrides: Any
) -> dict[str, Any]:
    document: dict[str, Any] = {
        "minority_report_id": minority_report_id,
        "run_id": RUN_ID,
        "author_role": "minority_reporter",
        "minority_claim": "the majority may overstate the effect outside the tested scope",
        "evidence_ids": ["EV-MIN-1"],
        "why_majority_may_be_wrong": "the strongest support rests on one setting",
        "unresolved_test": "a cross-scope replication that has not been run",
        "expected_information_gain": 0.4,
        "preservation_status": "preserved",
        "created_at": CREATED_AT,
    }
    document.update(overrides)
    document["report_hash"] = hash_excluding(document, "report_hash")
    return document


def _red_queen_results(candidate_id: str) -> list[dict[str, Any]]:
    return [
        rq.build_challenge_result(
            challenge_genome_id="CG-P06-1",
            target_candidate_id=candidate_id,
            stage_result_id="SR-1",
            outcome="SURVIVED",
            severity="major",
            observed_effect="the candidate's behaviour under the challenge",
            reproduction_artifact_ids=[],
            challenge_result_id="CR-P06-1",
        )
    ]


def _replication_plan(candidate_id: str) -> dict[str, Any]:
    return build_replication_plan(
        candidate_id=candidate_id,
        replication_class="independent_team",
        executor_independence="independent_team",
        environment_ids=["ENV-1"],
        data_ids=["DATA-1"],
        seeds=[1, 2, 3],
        preregistered_metrics=["primary_metric"],
        success_rule="effect within preregistered interval",
        failure_rule="effect outside preregistered interval",
        replication_plan_id="RP-P06-1",
    )


def _replication_result(candidate_id: str) -> dict[str, Any]:
    document: dict[str, Any] = {
        "replication_result_id": "RR-P06-1",
        "replication_plan_id": "RP-P06-1",
        "candidate_id": candidate_id,
        "status": "REPLICATED",
        "metric_summary": {"primary_metric": 0.42},
        "heterogeneity": "low across settings",
        "failure_analysis": [],
        "promotion_effect": "RAISE",
        "artifact_ids": ["ART-RR-1"],
    }
    document["result_hash"] = hash_excluding(document, "result_hash")
    return document


def parliament_receipt(
    *,
    candidate_id: str = CANDIDATE_ID,
    with_minority: bool = True,
    admissibility: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A genuine P05 CONVENE receipt for the candidate.

    ``with_minority=False`` supplies no minority report and an adjudication that
    references none, so the docket still convenes but preserves no dissent — the
    bare-majority receipt the no-majority suite needs.
    """
    minority = [minority_report()] if with_minority else []
    minority_ids = [report["minority_report_id"] for report in minority]
    return derive_promotion_parliament(
        candidate_id=candidate_id,
        candidate_revision=1,
        requested_level=TOP_LEVEL,
        lineage=_lineage(candidate_id),
        adjudication=_adjudication(candidate_id, minority_ids),
        selective_admissibility=admissibility
        or admissibility_receipt(candidate_id=candidate_id),
        red_queen_results=_red_queen_results(candidate_id),
        searched_adversarial_lanes=list(adversarial_lanes()),
        requesting_principal_id=GOVERNOR_ID,
        requesting_role=GOVERNOR_ROLE,
        adaptive_search_used=True,
        minority_reports=minority,
        replication_plan=_replication_plan(candidate_id),
        replication_results=[_replication_result(candidate_id)],
        created_at=CREATED_AT,
    )


def withheld_parliament_receipt(*, candidate_id: str = CANDIDATE_ID) -> dict[str, Any]:
    """A genuine P05 WITHHOLD receipt (its statistical clearance did not admit)."""
    return parliament_receipt(
        candidate_id=candidate_id,
        admissibility=admissibility_receipt(candidate_id=candidate_id, admit=False),
    )


def low_ceiling_parliament_receipt(
    *, candidate_id: str = CANDIDATE_ID
) -> dict[str, Any]:
    """A genuine P05 CONVENE receipt whose ceiling is capped below the top level.

    No independent replication plan is supplied, so the replication surface caps
    the promotion ceiling at ``EMPIRICALLY_TESTED`` while every other dimension
    still clears and the docket convenes.
    """
    minority = [minority_report()]
    return derive_promotion_parliament(
        candidate_id=candidate_id,
        candidate_revision=1,
        requested_level="EMPIRICALLY_TESTED",
        lineage=_lineage(candidate_id),
        adjudication=_adjudication(
            candidate_id, [report["minority_report_id"] for report in minority]
        ),
        selective_admissibility=admissibility_receipt(candidate_id=candidate_id),
        red_queen_results=_red_queen_results(candidate_id),
        searched_adversarial_lanes=list(adversarial_lanes()),
        requesting_principal_id=GOVERNOR_ID,
        requesting_role=GOVERNOR_ROLE,
        adaptive_search_used=True,
        minority_reports=minority,
        replication_plan=None,
        replication_results=[],
        created_at=CREATED_AT,
    )


def low_ceiling_validation_receipt(
    *, candidate_id: str = CANDIDATE_ID
) -> dict[str, Any]:
    """A genuine V05 ADVANCE receipt whose replication ceiling is ``EMPIRICALLY_TESTED``."""
    return validation_receipt(
        candidate_id=candidate_id,
        required_level="EMPIRICALLY_TESTED",
        admissibility=None,
        replication_plan_omitted=True,
    )


# --------------------------------------------------------------------------- #
# V05 validation organ (a genuine ADVANCE receipt)
# --------------------------------------------------------------------------- #
def _cascade_plan() -> dict[str, Any]:
    return build_cascade_plan(
        candidate_class="hypothesis",
        stages=[
            {
                "stage_id": "S-CONTRACT",
                "stage_class": "contract",
                "entry_rule": "always",
                "pass_rule": "schema valid",
                "failure_action": "reject",
                "budget_fraction": 0.1,
            },
            {
                "stage_id": "S-EVIDENCE",
                "stage_class": "evidence",
                "entry_rule": "after contract",
                "pass_rule": "evidence sufficient",
                "failure_action": "reject",
                "budget_fraction": 0.3,
            },
            {
                "stage_id": "S-REPLICATION",
                "stage_class": "replication",
                "entry_rule": "after evidence",
                "pass_rule": "replicated",
                "failure_action": "restrict",
                "budget_fraction": 0.4,
            },
        ],
        max_total_budget=100.0,
        early_stop_policy="stop_on_first_hard_failure",
        cascade_plan_id="VCP-P06-1",
    )


def _stage_results(plan: dict[str, Any], candidate_id: str) -> list[dict[str, Any]]:
    from epistemic_foundry.validation.v4_v05 import cascade_pass_status

    passing = cascade_pass_status()
    built: list[dict[str, Any]] = []
    for index, spec in enumerate(plan["stages"]):
        built.append(
            build_stage_result(
                cascade_plan_id=str(plan["cascade_plan_id"]),
                candidate_id=candidate_id,
                stage_id=str(spec["stage_id"]),
                status=passing,
                metric_values={"score": 0.9},
                uncertainty_summary="within tolerance",
                started_at=CREATED_AT,
                completed_at=CREATED_AT,
                stage_result_id=f"SER-P06-{index}",
            )
        )
    return built


def _ood_genome(candidate_id: str) -> dict[str, Any]:
    from epistemic_foundry.validation.v4_v05 import ood_challenge_class_token

    return rq.build_challenge_genome(
        target_genome_id=candidate_id,
        challenge_class=ood_challenge_class_token(),
        construction="shift the covariate distribution beyond the training support",
        success_criterion="candidate prediction degrades below threshold",
        required_capabilities=[],
        lineage_id="LIN-P06-OOD",
        safety_class="safe",
        challenge_genome_id="CG-P06-OOD",
    )


def _ood_result(candidate_id: str) -> dict[str, Any]:
    return rq.build_challenge_result(
        challenge_genome_id="CG-P06-OOD",
        target_candidate_id=candidate_id,
        stage_result_id="SER-P06-2",
        outcome=sorted(rq.SURVIVING_OUTCOMES)[0],
        severity="minor",
        observed_effect="prediction held under distribution shift",
        reproduction_artifact_ids=[],
        challenge_result_id="CR-P06-OOD",
    )


def validation_receipt(
    *,
    candidate_id: str = CANDIDATE_ID,
    required_level: str = TOP_LEVEL,
    admissibility: dict[str, Any] | None = None,
    replication_plan_omitted: bool = False,
) -> dict[str, Any]:
    """A genuine V05 ADVANCE receipt for the candidate."""
    plan = _cascade_plan()
    return derive_validation_advancement(
        candidate_id=candidate_id,
        cascade_plan=plan,
        stage_results=_stage_results(plan, candidate_id),
        challenge_genomes=[_ood_genome(candidate_id)],
        challenge_results=[_ood_result(candidate_id)],
        admissibility_receipt=admissibility
        or admissibility_receipt(candidate_id=candidate_id),
        adaptive_search_used=True,
        required_promotion_level=required_level,
        requesting_role=GOVERNOR_ROLE,
        replication_plan=None
        if replication_plan_omitted
        else _replication_plan(candidate_id),
        created_at=CREATED_AT,
    )


def refused_validation_receipt(*, candidate_id: str = CANDIDATE_ID) -> dict[str, Any]:
    """A genuine V05 REFUSE receipt (its Q05 admissibility did not admit)."""
    return validation_receipt(
        candidate_id=candidate_id,
        admissibility=admissibility_receipt(candidate_id=candidate_id, admit=False),
    )


# --------------------------------------------------------------------------- #
# Sealed-candidate attestation
# --------------------------------------------------------------------------- #
def independence_context(**overrides: Any) -> dict[str, Any]:
    """A charter-section-6 context in which the attestor is independent."""
    context: dict[str, Any] = {
        "candidate_generator_ids": [MAKER_ID],
        "candidate_implementer_ids": [MAKER_ID],
        "first_adjudicator_ids": ["adj-p06-1"],
        "prompt_lineage_actor_ids": ["prompt-p06-1"],
        "promotion_commit_authority_ids": ["commit-p06-1"],
    }
    context.update(overrides)
    return context


def attestation(
    *,
    candidate_id: str = CANDIDATE_ID,
    parliament: dict[str, Any] | None = None,
    validation: dict[str, Any] | None = None,
    overall_status: str | None = None,
    attestor_id: str = ATTESTOR_ID,
    input_artifact_ids: list[str] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    """A schema-valid attestation over both organ receipts, sealed to its hash.

    By default it names both organ receipt ``gate_id``s as its inputs, so the
    chain is complete; a caller may pass ``input_artifact_ids`` to drop one and
    exercise the incomplete-chain refusal.
    """
    p_receipt = parliament or parliament_receipt(candidate_id=candidate_id)
    v_receipt = validation or validation_receipt(candidate_id=candidate_id)
    inputs = input_artifact_ids or [
        str(p_receipt["gate_id"]),
        str(v_receipt["gate_id"]),
    ]
    status = overall_status or p06.attestation_pass_status()
    document: dict[str, Any] = {
        "attestation_id": "ATT-P06-1",
        "run_id": RUN_ID,
        "subject_artifact_id": candidate_id,
        "attestor_id": attestor_id,
        "attestor_type": "formal_verifier",
        "input_artifact_ids": inputs,
        "checks": [
            {
                "check_id": "parliament_convened",
                "status": status,
                "reason": "the multi-dimensional docket convened with dissent preserved",
            },
            {
                "check_id": "validation_advanced",
                "status": status,
                "reason": "the validation cascade advanced the claim",
            },
        ],
        "overall_status": status,
        "independence_statement": "independent of makers, adjudicators and commit authority",
        "model_or_identity_version": "attestor-1.0.0",
        "created_at": CREATED_AT,
        "signature": None,
    }
    document.update(overrides)
    document["attestation_hash"] = hash_excluding(document, "attestation_hash")
    return document


def _non_pass_status() -> str:
    from epistemic_foundry.contracts import default_registry

    statuses = default_registry().document("attestation")["properties"][
        "overall_status"
    ]["enum"]
    passing = p06.attestation_pass_status()
    return next(status for status in statuses if status != passing)


def failing_attestation(*, candidate_id: str = CANDIDATE_ID) -> dict[str, Any]:
    """A schema-valid attestation whose overall status is not PASS."""
    return attestation(candidate_id=candidate_id, overall_status=_non_pass_status())


# --------------------------------------------------------------------------- #
# Full gate arguments
# --------------------------------------------------------------------------- #
def referral_arguments(**overrides: Any) -> dict[str, Any]:
    """A fully-bound sealed candidate the gate should refer to promotion review."""
    p_receipt = parliament_receipt()
    v_receipt = validation_receipt()
    arguments: dict[str, Any] = {
        "candidate_id": CANDIDATE_ID,
        "requested_level": REQUESTED_LEVEL,
        "parliament_receipt": p_receipt,
        "validation_receipt": v_receipt,
        "attestation": attestation(parliament=p_receipt, validation=v_receipt),
        "attestor_independence_context": independence_context(),
        "requesting_principal_id": GOVERNOR_ID,
        "requesting_role": GOVERNOR_ROLE,
        "created_at": CREATED_AT,
    }
    arguments.update(overrides)
    return arguments
