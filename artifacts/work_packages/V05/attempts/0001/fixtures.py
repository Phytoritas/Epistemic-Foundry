"""Fixtures for the V05 validation-cascade advancement gate suites.

Every artifact the gate composes is built by the *sealed owning surface* — the
validation cascade, the Red Queen Lab, the replication surface, and (for the
statistical-admissibility receipt) the Q05 gate over the fitness, firewall and
statistics surfaces — never assembled by hand.  A fixture the owner would refuse
would test the fixture rather than the gate, and building through the owners
means a canonical change breaks these fixtures instead of letting them drift.
The out-of-distribution challenge class and the passing cascade status are read
out of the gate that reads them from the schema, for the same reason.
"""

from __future__ import annotations

from typing import Any

from epistemic_foundry.evaluation.fitness import (
    FITNESS_DIMENSIONS,
    build_fitness_vector,
)
from epistemic_foundry.evaluation.v4_q05 import gate as q05
from epistemic_foundry.red_queen_lab import challenges as rq
from epistemic_foundry.statistics.multiplicity import build_multiplicity_adjustment
from epistemic_foundry.statistics.search_record import build_search_statistics_record
from epistemic_foundry.statistics.selective import build_selective_inference_report
from epistemic_foundry.statistics.sequential import build_sequential_ledger
from epistemic_foundry.validation.v4_v05 import cascade_gate as engine
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
CREATED_AT = "2026-08-02T00:00:00+00:00"
A_HASH = "sha256:" + "a" * 64
B_HASH = "sha256:" + "b" * 64

#: A governor role that is *not* candidate-generating, so the gate's authority
#: guard permits it to drive the decision.
GOVERNOR_ID = "gov-1"
GOVERNOR_ROLE = "statistical_governor"

#: A candidate-generating role the authority guard must refuse.
GENERATOR_ROLE = "hypothesis_mutator"

FAMILY_ID = "FAM-V05-1"
EVALUATOR_ID = "EVAL-V05-1"
HIDDEN_HANDLE = "HID-V05-1"


# --------------------------------------------------------------------------- #
# Validation cascade
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


def cascade_plan(**overrides: Any) -> dict[str, Any]:
    """A schema-valid three-stage cascade plan."""
    plan = build_cascade_plan(
        candidate_class="hypothesis",
        stages=_stage_specs(),
        max_total_budget=100.0,
        early_stop_policy="stop_on_first_hard_failure",
        cascade_plan_id="VCP-V05-1",
    )
    plan.update(overrides)
    return plan


def stage_results(
    *,
    plan: dict[str, Any] | None = None,
    candidate_id: str = CANDIDATE_ID,
    final_status: str | None = None,
) -> list[dict[str, Any]]:
    """One passing result per stage, with an optional override on the last stage.

    ``final_status`` replaces the last stage's status so a caller can drive the
    cascade to a non-passing aggregate without inventing an out-of-order run.
    """
    plan_record = plan or cascade_plan()
    passing = engine.cascade_pass_status()
    specs = list(plan_record["stages"])
    built: list[dict[str, Any]] = []
    for index, spec in enumerate(specs):
        status = passing
        if final_status is not None and index == len(specs) - 1:
            status = final_status
        built.append(
            build_stage_result(
                cascade_plan_id=str(plan_record["cascade_plan_id"]),
                candidate_id=candidate_id,
                stage_id=str(spec["stage_id"]),
                status=status,
                metric_values={"score": 0.9},
                uncertainty_summary="within tolerance",
                started_at=CREATED_AT,
                completed_at=CREATED_AT,
                stage_result_id=f"SER-V05-{index}",
            )
        )
    return built


# --------------------------------------------------------------------------- #
# Out-of-distribution challenge
# --------------------------------------------------------------------------- #
def ood_genome(**overrides: Any) -> dict[str, Any]:
    """An out-of-distribution challenge genome, class read from the gate."""
    genome = rq.build_challenge_genome(
        target_genome_id=CANDIDATE_ID,
        challenge_class=engine.ood_challenge_class_token(),
        construction="shift the covariate distribution beyond the training support",
        success_criterion="candidate prediction degrades below threshold",
        required_capabilities=[],
        lineage_id="LIN-V05-OOD",
        safety_class="safe",
        challenge_genome_id="CG-V05-OOD",
    )
    genome.update(overrides)
    return genome


def other_genome(**overrides: Any) -> dict[str, Any]:
    """A non-OOD challenge genome, so the gate must not count it as OOD coverage."""
    classes = _non_ood_classes()
    genome = rq.build_challenge_genome(
        target_genome_id=CANDIDATE_ID,
        challenge_class=classes[0],
        construction="inject a known confounder",
        success_criterion="association vanishes under control",
        required_capabilities=[],
        lineage_id="LIN-V05-OTHER",
        safety_class="safe",
        challenge_genome_id="CG-V05-OTHER",
    )
    genome.update(overrides)
    return genome


def _non_ood_classes() -> list[str]:
    from epistemic_foundry.contracts import default_registry

    document = default_registry().document("challenge-genome")
    classes = document["properties"]["challenge_class"]["enum"]
    ood = engine.ood_challenge_class_token()
    return [token for token in classes if token != ood]


def _surviving_outcome() -> str:
    return sorted(rq.SURVIVING_OUTCOMES)[0]


def _adverse_outcome() -> str:
    return sorted(rq.ADVERSE_OUTCOMES)[0]


def _unresolved_outcome() -> str:
    return sorted(rq.UNRESOLVED_OUTCOMES)[0]


def ood_result(
    *,
    genome_id: str = "CG-V05-OOD",
    candidate_id: str = CANDIDATE_ID,
    outcome: str | None = None,
    result_id: str = "CR-V05-OOD",
    reproduction_artifact_ids: list[str] | None = None,
) -> dict[str, Any]:
    """One OOD challenge match; survival by default."""
    resolved = outcome or _surviving_outcome()
    reproduction = reproduction_artifact_ids
    if reproduction is None and resolved in rq.ADVERSE_OUTCOMES:
        reproduction = ["REPRO-V05-1"]
    return rq.build_challenge_result(
        challenge_genome_id=genome_id,
        target_candidate_id=candidate_id,
        stage_result_id="SER-V05-2",
        outcome=resolved,
        severity="minor",
        observed_effect="prediction held under distribution shift",
        reproduction_artifact_ids=reproduction or [],
        challenge_result_id=result_id,
    )


# --------------------------------------------------------------------------- #
# Independent replication
# --------------------------------------------------------------------------- #
def replication_plan(
    *,
    candidate_id: str = CANDIDATE_ID,
    replication_class: str = "independent_team",
    executor_independence: str = "independent_team",
    **overrides: Any,
) -> dict[str, Any]:
    """A qualifying independent, preregistered replication plan."""
    plan = build_replication_plan(
        candidate_id=candidate_id,
        replication_class=replication_class,
        executor_independence=executor_independence,
        environment_ids=["ENV-V05-1"],
        data_ids=["DATA-V05-1"],
        seeds=[1, 2, 3],
        preregistered_metrics=["effect_size"],
        success_rule="effect_size within CI on independent data",
        failure_rule="effect_size outside CI or sign flip",
        replication_plan_id="RP-V05-1",
    )
    plan.update(overrides)
    return plan


# --------------------------------------------------------------------------- #
# Statistical-admissibility receipt (composed from the Q05 gate)
# --------------------------------------------------------------------------- #
def _fitness_vector(candidate_id: str = CANDIDATE_ID) -> dict[str, Any]:
    return build_fitness_vector(
        candidate_id=candidate_id,
        hard_gate_status=q05.hard_gate_pass_token(),
        hard_gate_failures=[],
        dimensions={name: 0.9 for name in FITNESS_DIMENSIONS},
        uncertainty={name: 0.05 for name in FITNESS_DIMENSIONS},
        evidence_receipt_ids=["ER-V05-1"],
        pareto_rank=0,
        domination_count=0,
        fitness_vector_id="FV-V05-1",
        computed_at=CREATED_AT,
    )


def _holdout_manifest() -> dict[str, Any]:
    return build_holdout_manifest(
        evaluator_id=EVALUATOR_ID,
        split_strategy="fixed_nested_holdout",
        public_partition_refs=["PUB-1"],
        hidden_partition_handles=[HIDDEN_HANDLE],
        ood_partition_handles=["OOD-V05-1"],
        adversarial_partition_handles=["ADV-V05-1"],
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
        code_artifact_id="CA-V05-1",
        code_hash=A_HASH,
        metric_contract_hash=A_HASH,
        environment_digest=A_HASH,
        dependency_lock_hash=A_HASH,
        data_contract_hash=A_HASH,
        policy_bundle_hash=A_HASH,
        qualification_report_id="QR-V05-1",
        holdout_manifest_id=EVALUATOR_ID,
        evaluator_id=EVALUATOR_ID,
        sealed_at=CREATED_AT,
    )


def _selective_report(candidate_id: str = CANDIDATE_ID) -> dict[str, Any]:
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
        report_id="SIR-V05-1",
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
        ledger_id="STL-V05-1",
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
        adjustment_id="MTA-V05-1",
    )
    return build_search_statistics_record(
        evolution_run_id="RUN-V05-1",
        family_id=FAMILY_ID,
        candidate_id=candidate_id,
        sequential_ledger=ledger,
        multiplicity_adjustment=multiplicity,
        selective_report=report,
        hidden_exposure_log_id="HEL-V05-1",
        candidate_lineage_id="LIN-V05-1",
        replication_result_id="RR-V05-1",
        record_id="SSR-V05-1",
        created_at=CREATED_AT,
    )


def admissibility_receipt(*, candidate_id: str = CANDIDATE_ID) -> dict[str, Any]:
    """An ADMIT receipt from the Q05 statistical-admissibility gate."""
    report = _selective_report(candidate_id=candidate_id)
    return q05.derive_selective_admissibility(
        candidate_id=candidate_id,
        fitness_vector=_fitness_vector(candidate_id=candidate_id),
        evaluator_bundle=_evaluator_bundle(),
        holdout_manifest=_holdout_manifest(),
        search_statistics=_search_statistics(report, candidate_id=candidate_id),
        selective_report=report,
        requesting_principal_id=GOVERNOR_ID,
        requesting_role=GOVERNOR_ROLE,
        holdout_read_principal_ids=[GOVERNOR_ID],
        created_at=CREATED_AT,
    )


def _failing_hard_gate_status() -> str:
    from epistemic_foundry.contracts import default_registry

    document = default_registry().document("fitness-vector")
    statuses = document["properties"]["hard_gate_status"]["enum"]
    passing = q05.hard_gate_pass_token()
    return next(status for status in statuses if status != passing)


def refused_admissibility_receipt(
    *, candidate_id: str = CANDIDATE_ID
) -> dict[str, Any]:
    """A genuine REFUSE receipt from Q05 (its fitness hard gate did not pass)."""
    report = _selective_report(candidate_id=candidate_id)
    failing = build_fitness_vector(
        candidate_id=candidate_id,
        hard_gate_status=_failing_hard_gate_status(),
        hard_gate_failures=["novelty_veto"],
        dimensions={name: 0.9 for name in FITNESS_DIMENSIONS},
        uncertainty={name: 0.05 for name in FITNESS_DIMENSIONS},
        evidence_receipt_ids=["ER-V05-1"],
        pareto_rank=0,
        domination_count=0,
        fitness_vector_id="FV-V05-REFUSED",
        computed_at=CREATED_AT,
    )
    return q05.derive_selective_admissibility(
        candidate_id=candidate_id,
        fitness_vector=failing,
        evaluator_bundle=_evaluator_bundle(),
        holdout_manifest=_holdout_manifest(),
        search_statistics=_search_statistics(report, candidate_id=candidate_id),
        selective_report=report,
        requesting_principal_id=GOVERNOR_ID,
        requesting_role=GOVERNOR_ROLE,
        holdout_read_principal_ids=[GOVERNOR_ID],
        created_at=CREATED_AT,
    )


# --------------------------------------------------------------------------- #
# Full gate arguments
# --------------------------------------------------------------------------- #
def gate_arguments(**overrides: Any) -> dict[str, Any]:
    """A fully-bound claim the gate should advance toward promotion review."""
    plan = cascade_plan()
    arguments: dict[str, Any] = {
        "candidate_id": CANDIDATE_ID,
        "cascade_plan": plan,
        "stage_results": stage_results(plan=plan),
        "challenge_genomes": [ood_genome()],
        "challenge_results": [ood_result()],
        "admissibility_receipt": admissibility_receipt(),
        "adaptive_search_used": True,
        "required_promotion_level": required_replicated_level(),
        "requesting_role": GOVERNOR_ROLE,
        "replication_plan": replication_plan(),
        "created_at": CREATED_AT,
    }
    arguments.update(overrides)
    return arguments


def required_replicated_level() -> str:
    """The top promotion level, read from the shared ladder rather than pinned."""
    from epistemic_foundry.domain.vocabularies import PROMOTION_LADDER

    return PROMOTION_LADDER[-1]
