"""Fixtures for the Q06 calibration / winner's-curse / governance gate suites.

Every verdict the gate composes is built by the *sealed owning surface* — the
Q05 statistical-admissibility gate and the V05 validation-advancement gate over
the fitness, firewall, statistics, cascade, Red Queen and replication surfaces —
never assembled by hand.  A single Q05 clearance is threaded through both V05 and
Q06 so the advancement receipt's hash binding and the selective-report binding
the gate enforces are real rather than staged.  The calibration report is the one
composed artifact with no owning builder in scope, so it is constructed here and
sealed with its own content hash; its passing status is read from the schema.

Test modules may import the ``validation`` component directly: the component
import-boundary check scans ``src/epistemic_foundry`` only, so building genuine
V05 receipts here does not create the ``evaluation``↔``validation`` cycle the
gate itself is careful to avoid.
"""

from __future__ import annotations

from typing import Any

from epistemic_foundry.contracts import default_registry
from epistemic_foundry.domain.hashing import hash_excluding
from epistemic_foundry.domain.vocabularies import PROMOTION_LADDER
from epistemic_foundry.evaluation.fitness import (
    FITNESS_DIMENSIONS,
    build_fitness_vector,
)
from epistemic_foundry.evaluation.v4_q05 import gate as q05
from epistemic_foundry.evaluation.v4_q06 import gate as engine
from epistemic_foundry.red_queen_lab import challenges as rq
from epistemic_foundry.statistics.multiplicity import build_multiplicity_adjustment
from epistemic_foundry.statistics.search_record import build_search_statistics_record
from epistemic_foundry.statistics.selective import build_selective_inference_report
from epistemic_foundry.statistics.sequential import build_sequential_ledger
from epistemic_foundry.validation.v4_v05 import cascade_gate as v05
from epistemic_foundry.validation_bay.cascade import (
    build_cascade_plan,
    build_stage_result,
)
from epistemic_foundry.validation_bay.replication import build_replication_plan
from epistemic_foundry.verifier_firewall.firewall import (
    build_evaluator_bundle,
    build_holdout_manifest,
)

CANDIDATE_ID = "HG-1"
EVALUATION_ID = "EVAL-RUN-Q06-1"
CREATED_AT = "2026-08-02T00:00:00+00:00"
A_HASH = "sha256:" + "a" * 64
B_HASH = "sha256:" + "b" * 64

#: A governor principal/role that is *not* candidate-generating, so the gate's
#: authority guard permits it to drive the decision.
GOVERNOR_ID = "gov-1"
GOVERNOR_ROLE = "statistical_governor"

#: A candidate-generating role the authority guard must refuse.
GENERATOR_ROLE = "hypothesis_mutator"

FAMILY_ID = "FAM-Q06-1"
EVALUATOR_ID = "EVAL-Q06-1"
HIDDEN_HANDLE = "HID-Q06-1"


# --------------------------------------------------------------------------- #
# Statistical artifacts, fitness, evaluator, holdout
# --------------------------------------------------------------------------- #
def selective_report(
    *,
    candidate_id: str = CANDIDATE_ID,
    replication_count: int = 2,
    report_id: str = "SIR-Q06-1",
) -> dict[str, Any]:
    """A selective-inference report; ALLOW (winner's-curse controlled) by default.

    ``replication_count`` two makes the winner's-curse risk low and the
    recommendation ALLOW; dropping it forces a non-permissive recommendation.
    """
    return build_selective_inference_report(
        candidate_id=candidate_id,
        selection_mechanism="argmax_over_generation",
        selection_events=["SE-1"],
        naive_estimate=0.5,
        bias_corrected_estimate=0.4,
        correction_method="conditional_shrinkage",
        uncertainty_interval=[0.2, 0.6],
        candidates_considered=3,
        replication_count=replication_count,
        report_id=report_id,
    )


def _fitness_vector(
    *, candidate_id: str = CANDIDATE_ID, passing: bool = True
) -> dict[str, Any]:
    status = q05.hard_gate_pass_token() if passing else _failing_hard_gate_status()
    failures = [] if passing else ["novelty_veto"]
    return build_fitness_vector(
        candidate_id=candidate_id,
        hard_gate_status=status,
        hard_gate_failures=failures,
        dimensions={name: 0.9 for name in FITNESS_DIMENSIONS},
        uncertainty={name: 0.05 for name in FITNESS_DIMENSIONS},
        evidence_receipt_ids=["ER-Q06-1"],
        pareto_rank=0,
        domination_count=0,
        fitness_vector_id="FV-Q06-1" if passing else "FV-Q06-REFUSED",
        computed_at=CREATED_AT,
    )


def _failing_hard_gate_status() -> str:
    document = default_registry().document("fitness-vector")
    statuses = document["properties"]["hard_gate_status"]["enum"]
    passing = q05.hard_gate_pass_token()
    return next(status for status in statuses if status != passing)


def _holdout_manifest() -> dict[str, Any]:
    return build_holdout_manifest(
        evaluator_id=EVALUATOR_ID,
        split_strategy="fixed_nested_holdout",
        public_partition_refs=["PUB-1"],
        hidden_partition_handles=[HIDDEN_HANDLE],
        ood_partition_handles=["OOD-Q06-1"],
        adversarial_partition_handles=["ADV-Q06-1"],
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
        code_artifact_id="CA-Q06-1",
        code_hash=A_HASH,
        metric_contract_hash=A_HASH,
        environment_digest=A_HASH,
        dependency_lock_hash=A_HASH,
        data_contract_hash=A_HASH,
        policy_bundle_hash=A_HASH,
        qualification_report_id="QR-Q06-1",
        holdout_manifest_id=EVALUATOR_ID,
        evaluator_id=EVALUATOR_ID,
        sealed_at=CREATED_AT,
    )


def _search_statistics(
    report: dict[str, Any], *, candidate_id: str = CANDIDATE_ID
) -> dict[str, Any]:
    ledger = build_sequential_ledger(
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
        ledger_id="STL-Q06-1",
    )
    multiplicity = build_multiplicity_adjustment(
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
        adjustment_id="MTA-Q06-1",
    )
    return build_search_statistics_record(
        evolution_run_id="RUN-Q06-1",
        family_id=FAMILY_ID,
        candidate_id=candidate_id,
        sequential_ledger=ledger,
        multiplicity_adjustment=multiplicity,
        selective_report=report,
        hidden_exposure_log_id="HEL-Q06-1",
        candidate_lineage_id="LIN-Q06-1",
        replication_result_id="RR-Q06-1",
        record_id="SSR-Q06-1",
        created_at=CREATED_AT,
    )


# --------------------------------------------------------------------------- #
# Q05 statistical-admissibility receipt
# --------------------------------------------------------------------------- #
def admissibility_receipt(
    *,
    candidate_id: str = CANDIDATE_ID,
    report: dict[str, Any] | None = None,
    passing: bool = True,
) -> dict[str, Any]:
    """A Q05 receipt built over the shared selective report.

    Passing ``report`` lets a caller thread the *same* selective report through
    Q05 and Q06, so the selective-report hash binding the gate enforces is real.
    """
    resolved = (
        report if report is not None else selective_report(candidate_id=candidate_id)
    )
    return q05.derive_selective_admissibility(
        candidate_id=candidate_id,
        fitness_vector=_fitness_vector(candidate_id=candidate_id, passing=passing),
        evaluator_bundle=_evaluator_bundle(),
        holdout_manifest=_holdout_manifest(),
        search_statistics=_search_statistics(resolved, candidate_id=candidate_id),
        selective_report=resolved,
        requesting_principal_id=GOVERNOR_ID,
        requesting_role=GOVERNOR_ROLE,
        holdout_read_principal_ids=[GOVERNOR_ID],
        created_at=CREATED_AT,
    )


# --------------------------------------------------------------------------- #
# V05 validation-advancement receipt
# --------------------------------------------------------------------------- #
def _stage_specs() -> list[dict[str, Any]]:
    return [
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
    ]


def _cascade_plan() -> dict[str, Any]:
    return build_cascade_plan(
        candidate_class="hypothesis",
        stages=_stage_specs(),
        max_total_budget=100.0,
        early_stop_policy="stop_on_first_hard_failure",
        cascade_plan_id="VCP-Q06-1",
    )


def _stage_results(
    plan: dict[str, Any],
    *,
    candidate_id: str = CANDIDATE_ID,
    final_status: str | None = None,
) -> list[dict[str, Any]]:
    passing = v05.cascade_pass_status()
    specs = list(plan["stages"])
    built: list[dict[str, Any]] = []
    for index, spec in enumerate(specs):
        status = passing
        if final_status is not None and index == len(specs) - 1:
            status = final_status
        built.append(
            build_stage_result(
                cascade_plan_id=str(plan["cascade_plan_id"]),
                candidate_id=candidate_id,
                stage_id=str(spec["stage_id"]),
                status=status,
                metric_values={"score": 0.9},
                uncertainty_summary="within tolerance",
                started_at=CREATED_AT,
                completed_at=CREATED_AT,
                stage_result_id=f"SER-Q06-{index}",
            )
        )
    return built


def _ood_genome(*, candidate_id: str = CANDIDATE_ID) -> dict[str, Any]:
    return rq.build_challenge_genome(
        target_genome_id=candidate_id,
        challenge_class=v05.ood_challenge_class_token(),
        construction="shift the covariate distribution beyond the training support",
        success_criterion="candidate prediction degrades below threshold",
        required_capabilities=[],
        lineage_id="LIN-Q06-OOD",
        safety_class="safe",
        challenge_genome_id="CG-Q06-OOD",
    )


def _ood_result(*, candidate_id: str = CANDIDATE_ID) -> dict[str, Any]:
    surviving = sorted(rq.SURVIVING_OUTCOMES)[0]
    return rq.build_challenge_result(
        challenge_genome_id="CG-Q06-OOD",
        target_candidate_id=candidate_id,
        stage_result_id="SER-Q06-2",
        outcome=surviving,
        severity="minor",
        observed_effect="prediction held under distribution shift",
        reproduction_artifact_ids=[],
        challenge_result_id="CR-Q06-OOD",
    )


def _replication_plan(*, candidate_id: str = CANDIDATE_ID) -> dict[str, Any]:
    return build_replication_plan(
        candidate_id=candidate_id,
        replication_class="independent_team",
        executor_independence="independent_team",
        environment_ids=["ENV-Q06-1"],
        data_ids=["DATA-Q06-1"],
        seeds=[1, 2, 3],
        preregistered_metrics=["effect_size"],
        success_rule="effect_size within CI on independent data",
        failure_rule="effect_size outside CI or sign flip",
        replication_plan_id="RP-Q06-1",
    )


def advancement_receipt(
    *,
    candidate_id: str = CANDIDATE_ID,
    admissibility: dict[str, Any] | None = None,
    advanced: bool = True,
) -> dict[str, Any]:
    """A V05 advancement receipt bound to the supplied Q05 clearance.

    ``advanced`` false drops the replication plan so the ceiling caps below the
    top rung and V05 records a genuine REFUSE, letting the gate exercise its
    ADVANCEMENT_NOT_ADVANCED path over a real, hash-bound advancement receipt.
    """
    clearance = (
        admissibility
        if admissibility is not None
        else admissibility_receipt(candidate_id=candidate_id)
    )
    plan = _cascade_plan()
    return v05.derive_validation_advancement(
        candidate_id=candidate_id,
        cascade_plan=plan,
        stage_results=_stage_results(plan, candidate_id=candidate_id),
        challenge_genomes=[_ood_genome(candidate_id=candidate_id)],
        challenge_results=[_ood_result(candidate_id=candidate_id)],
        admissibility_receipt=clearance,
        adaptive_search_used=True,
        required_promotion_level=PROMOTION_LADDER[-1],
        requesting_role=GOVERNOR_ROLE,
        replication_plan=_replication_plan(candidate_id=candidate_id)
        if advanced
        else None,
        created_at=CREATED_AT,
    )


# --------------------------------------------------------------------------- #
# Calibration report (no owning builder in scope; sealed here)
# --------------------------------------------------------------------------- #
def calibration_report(
    *,
    evaluation_id: str = EVALUATION_ID,
    status: str | None = None,
    calibration_report_id: str = "CAL-Q06-1",
) -> dict[str, Any]:
    """A schema-valid calibration report; passing status by default."""
    resolved = status if status is not None else engine.calibration_pass_status()
    report: dict[str, Any] = {
        "calibration_report_id": calibration_report_id,
        "evaluation_id": evaluation_id,
        "target": "verdict",
        "sample_count": 200,
        "brier_score": 0.08,
        "expected_calibration_error": 0.03,
        "reliability_bins": [
            {
                "lower": 0.0,
                "upper": 0.5,
                "count": 100,
                "mean_confidence": 0.25,
                "empirical_accuracy": 0.24,
            },
            {
                "lower": 0.5,
                "upper": 1.0,
                "count": 100,
                "mean_confidence": 0.75,
                "empirical_accuracy": 0.77,
            },
        ],
        "abstention_curve_artifact_id": None,
        "calibration_status": resolved,
        "created_at": CREATED_AT,
    }
    report["report_hash"] = hash_excluding(report, "report_hash")
    return report


def _non_passing_calibration_status() -> str:
    document = default_registry().document("calibration-report")
    statuses = document["properties"]["calibration_status"]["enum"]
    passing = engine.calibration_pass_status()
    return next(status for status in statuses if status != passing)


# --------------------------------------------------------------------------- #
# Full gate arguments
# --------------------------------------------------------------------------- #
def gate_arguments(**overrides: Any) -> dict[str, Any]:
    """A fully-bound selection the gate should govern as cleared for review.

    A single selective report and a single Q05 clearance are threaded through the
    admissibility receipt, the V05 advancement receipt and the winner's-curse
    binding, so every cross-artifact binding the gate enforces is genuine.
    """
    report = selective_report()
    clearance = admissibility_receipt(report=report)
    arguments: dict[str, Any] = {
        "candidate_id": CANDIDATE_ID,
        "evaluation_id": EVALUATION_ID,
        "admissibility_receipt": clearance,
        "advancement_receipt": advancement_receipt(admissibility=clearance),
        "calibration_report": calibration_report(),
        "selective_report": report,
        "requesting_role": GOVERNOR_ROLE,
        "requesting_principal_id": GOVERNOR_ID,
        "created_at": CREATED_AT,
    }
    arguments.update(overrides)
    return arguments
