"""Fixtures for the V06 experiment/replication end-to-end integration suites.

Every sub-receipt the gate composes is built by the *sealed owning gate* — the
Q05 statistical-admissibility gate, the V05 validation-cascade advancement gate
and the P05 promotion-Parliament gate — over artifacts each of *their* sealed
owning surfaces produce, never assembled by hand.  A receipt an owner would
refuse would test the fixture rather than V06, and building through the owners
means a canonical change breaks these fixtures instead of letting them drift.

The end-to-end path is bound to *one* candidate and *one* Q05 statistical
clearance: the single Q05 receipt is threaded into both the V05 advancement and
the P05 docket, so the coherent fixtures satisfy V06's cross-receipt binding by
construction and the negative fixtures break exactly one link at a time.
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
from epistemic_foundry.red_queen_lab import challenges as rq
from epistemic_foundry.retrieval.v4_o05 import adversarial_lanes
from epistemic_foundry.statistics.multiplicity import build_multiplicity_adjustment
from epistemic_foundry.statistics.search_record import build_search_statistics_record
from epistemic_foundry.statistics.selective import build_selective_inference_report
from epistemic_foundry.statistics.sequential import build_sequential_ledger
from epistemic_foundry.validation.v4_v05 import cascade_gate as v05
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

CANDIDATE_ID = "CAND-V06-1"
OTHER_CANDIDATE_ID = "CAND-V06-OTHER"
CREATED_AT = "2026-08-02T00:00:00+00:00"
A_HASH = "sha256:" + "a" * 64
B_HASH = "sha256:" + "b" * 64

FAMILY_ID = "FAM-V06-1"
EVALUATOR_ID = "EVAL-V06-1"
RUN_ID = "RUN-V06-1"

#: A governor role that is *not* candidate-generating, so V06's authority guard
#: permits it to drive the integration decision.
GOVERNOR_ID = "gov-v06-1"
GOVERNOR_ROLE = "integration_reviewer"

#: A candidate-generating role V06's authority guard must refuse.
CANDIDATE_ROLE = "hypothesis_mutator"


# --------------------------------------------------------------------------- #
# Q05 statistical-admissibility receipt (the one clearance the path rests on)
# --------------------------------------------------------------------------- #
def _fitness_vector(*, candidate_id: str, passing: bool, suffix: str) -> dict[str, Any]:
    status = q05.hard_gate_pass_token() if passing else _failing_hard_gate_status()
    return build_fitness_vector(
        candidate_id=candidate_id,
        hard_gate_status=status,
        hard_gate_failures=[] if passing else ["novelty_veto"],
        dimensions={name: 0.9 for name in FITNESS_DIMENSIONS},
        uncertainty={name: 0.05 for name in FITNESS_DIMENSIONS},
        evidence_receipt_ids=["ER-V06-1"],
        pareto_rank=0,
        domination_count=0,
        fitness_vector_id=f"FV-V06-{suffix}",
        computed_at=CREATED_AT,
    )


def _failing_hard_gate_status() -> str:
    from epistemic_foundry.contracts import default_registry

    document = default_registry().document("fitness-vector")
    statuses = document["properties"]["hard_gate_status"]["enum"]
    passing = q05.hard_gate_pass_token()
    return next(status for status in statuses if status != passing)


def _holdout_manifest() -> dict[str, Any]:
    return build_holdout_manifest(
        evaluator_id=EVALUATOR_ID,
        split_strategy="fixed_nested_holdout",
        public_partition_refs=["PUB-1"],
        hidden_partition_handles=["HID-V06-1"],
        ood_partition_handles=["OOD-V06-1"],
        adversarial_partition_handles=["ADV-V06-1"],
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
        code_artifact_id="CA-V06-1",
        code_hash=A_HASH,
        metric_contract_hash=A_HASH,
        environment_digest=A_HASH,
        dependency_lock_hash=A_HASH,
        data_contract_hash=A_HASH,
        policy_bundle_hash=A_HASH,
        qualification_report_id="QR-V06-1",
        holdout_manifest_id=EVALUATOR_ID,
        evaluator_id=EVALUATOR_ID,
        sealed_at=CREATED_AT,
    )


def _selective_report(*, candidate_id: str, suffix: str) -> dict[str, Any]:
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
        report_id=f"SIR-V06-{suffix}",
    )


def _search_statistics(
    report: dict[str, Any], *, candidate_id: str, suffix: str
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
        ledger_id=f"STL-V06-{suffix}",
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
        adjustment_id=f"MTA-V06-{suffix}",
    )
    return build_search_statistics_record(
        evolution_run_id=RUN_ID,
        family_id=FAMILY_ID,
        candidate_id=candidate_id,
        sequential_ledger=ledger,
        multiplicity_adjustment=multiplicity,
        selective_report=report,
        hidden_exposure_log_id="HEL-V06-1",
        candidate_lineage_id="LIN-V06-1",
        replication_result_id="RR-V06-1",
        record_id=f"SSR-V06-{suffix}",
        created_at=CREATED_AT,
    )


def q05_receipt(
    *, candidate_id: str = CANDIDATE_ID, admit: bool = True, suffix: str = "1"
) -> dict[str, Any]:
    """A genuine Q05 selective-admissibility receipt.

    ``admit=True`` drives the sealed Q05 gate to ADMIT; ``admit=False`` uses a
    non-passing hard gate so Q05 still produces a receipt whose decision is not
    ADMIT — a real REFUSE output rather than a hand-forged one.  ``suffix`` varies
    otherwise-independent ids so two admit receipts hash differently, which the
    statistical-consistency negative needs.
    """
    report = _selective_report(candidate_id=candidate_id, suffix=suffix)
    fitness = _fitness_vector(candidate_id=candidate_id, passing=admit, suffix=suffix)
    return q05.derive_selective_admissibility(
        candidate_id=candidate_id,
        fitness_vector=fitness,
        evaluator_bundle=_evaluator_bundle(),
        holdout_manifest=_holdout_manifest(),
        search_statistics=_search_statistics(
            report, candidate_id=candidate_id, suffix=suffix
        ),
        selective_report=report,
        requesting_principal_id=GOVERNOR_ID,
        requesting_role=GOVERNOR_ROLE,
        holdout_read_principal_ids=[GOVERNOR_ID],
        created_at=CREATED_AT,
    )


# --------------------------------------------------------------------------- #
# V05 validation-cascade advancement receipt
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
        cascade_plan_id="VCP-V06-1",
    )


def _stage_results(plan: dict[str, Any], *, candidate_id: str) -> list[dict[str, Any]]:
    passing = v05.cascade_pass_status()
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
                stage_result_id=f"SER-V06-{index}",
            )
        )
    return built


def _ood_genome(*, candidate_id: str) -> dict[str, Any]:
    return rq.build_challenge_genome(
        target_genome_id=candidate_id,
        challenge_class=v05.ood_challenge_class_token(),
        construction="shift the covariate distribution beyond the training support",
        success_criterion="candidate prediction degrades below threshold",
        required_capabilities=[],
        lineage_id="LIN-V06-OOD",
        safety_class="safe",
        challenge_genome_id="CG-V06-OOD",
    )


def _ood_result(*, candidate_id: str) -> dict[str, Any]:
    outcome = sorted(rq.SURVIVING_OUTCOMES)[0]
    return rq.build_challenge_result(
        challenge_genome_id="CG-V06-OOD",
        target_candidate_id=candidate_id,
        stage_result_id="SER-V06-2",
        outcome=outcome,
        severity="minor",
        observed_effect="prediction held under distribution shift",
        reproduction_artifact_ids=[],
        challenge_result_id="CR-V06-OOD",
    )


def _replication_plan(*, candidate_id: str) -> dict[str, Any]:
    return build_replication_plan(
        candidate_id=candidate_id,
        replication_class="independent_team",
        executor_independence="independent_team",
        environment_ids=["ENV-V06-1"],
        data_ids=["DATA-V06-1"],
        seeds=[1, 2, 3],
        preregistered_metrics=["effect_size"],
        success_rule="effect_size within CI on independent data",
        failure_rule="effect_size outside CI or sign flip",
        replication_plan_id="RP-V06-1",
    )


def _top_level() -> str:
    return PROMOTION_LADDER[-1]


def v05_receipt(
    *,
    candidate_id: str = CANDIDATE_ID,
    admissibility_receipt: dict[str, Any] | None = None,
    advance: bool = True,
) -> dict[str, Any]:
    """A genuine V05 validation-cascade advancement receipt over one Q05 receipt.

    ``advance=True`` yields an ADVANCE receipt; ``advance=False`` withholds the
    out-of-distribution challenge so V05 refuses with OOD_CHALLENGE_ABSENT — a real
    REFUSE output, still bound to the supplied Q05 clearance.
    """
    receipt = admissibility_receipt or q05_receipt(candidate_id=candidate_id)
    plan = _cascade_plan()
    genomes = [_ood_genome(candidate_id=candidate_id)] if advance else []
    results = [_ood_result(candidate_id=candidate_id)] if advance else []
    return derive_validation_advancement(
        candidate_id=candidate_id,
        cascade_plan=plan,
        stage_results=_stage_results(plan, candidate_id=candidate_id),
        challenge_genomes=genomes,
        challenge_results=results,
        admissibility_receipt=receipt,
        adaptive_search_used=True,
        required_promotion_level=_top_level(),
        requesting_role=GOVERNOR_ROLE,
        replication_plan=_replication_plan(candidate_id=candidate_id),
        created_at=CREATED_AT,
    )


# --------------------------------------------------------------------------- #
# P05 promotion-Parliament receipt
# --------------------------------------------------------------------------- #
def _lineage(*, candidate_id: str) -> dict[str, Any]:
    return {
        "lineage_id": "LIN-V06-1",
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


def _adjudication(
    *, candidate_id: str, minority_report_ids: list[str]
) -> dict[str, Any]:
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
        minority_report_ids=minority_report_ids,
        adjudication_id="ADJ-V06-1",
        created_at=CREATED_AT,
        refuse_override=True,
    )


def _minority_report() -> dict[str, Any]:
    document: dict[str, Any] = {
        "minority_report_id": "MIN-V06-1",
        "run_id": RUN_ID,
        "author_role": "minority_reporter",
        "minority_claim": "the majority may overstate the effect outside tested scope",
        "evidence_ids": ["EV-MIN-1"],
        "why_majority_may_be_wrong": "the strongest support rests on one setting",
        "unresolved_test": "a cross-scope replication that has not been run",
        "expected_information_gain": 0.4,
        "preservation_status": "preserved",
        "created_at": CREATED_AT,
    }
    document["report_hash"] = hash_excluding(document, "report_hash")
    return document


def _red_queen_results(*, candidate_id: str) -> list[dict[str, Any]]:
    return [
        rq.build_challenge_result(
            challenge_genome_id="CG-V06-RQ",
            target_candidate_id=candidate_id,
            stage_result_id="SR-1",
            outcome="SURVIVED",
            severity="major",
            observed_effect="the candidate's behaviour under the challenge",
            reproduction_artifact_ids=[],
            challenge_result_id="CR-V06-RQ",
        )
    ]


def _replication_result(*, candidate_id: str) -> dict[str, Any]:
    document: dict[str, Any] = {
        "replication_result_id": "RR-V06-1",
        "replication_plan_id": "RP-V06-1",
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


def p05_receipt(
    *,
    candidate_id: str = CANDIDATE_ID,
    selective_admissibility: dict[str, Any] | None = None,
    convene: bool = True,
) -> dict[str, Any]:
    """A genuine P05 promotion-Parliament receipt over one Q05 receipt.

    ``convene=True`` yields a CONVENE receipt; ``convene=False`` drops the
    referenced minority report so P05 withholds with MINORITY_DISSENT_DROPPED — a
    real WITHHOLD output, still bound to the supplied Q05 clearance.
    """
    clearance = selective_admissibility or q05_receipt(candidate_id=candidate_id)
    minority = _minority_report()
    referenced = [minority["minority_report_id"]]
    supplied = [minority] if convene else []
    return derive_promotion_parliament(
        candidate_id=candidate_id,
        candidate_revision=1,
        requested_level="EMPIRICALLY_TESTED",
        lineage=_lineage(candidate_id=candidate_id),
        adjudication=_adjudication(
            candidate_id=candidate_id, minority_report_ids=referenced
        ),
        selective_admissibility=clearance,
        red_queen_results=_red_queen_results(candidate_id=candidate_id),
        searched_adversarial_lanes=list(adversarial_lanes()),
        requesting_principal_id=GOVERNOR_ID,
        requesting_role=GOVERNOR_ROLE,
        adaptive_search_used=True,
        minority_reports=supplied,
        replication_plan=_replication_plan(candidate_id=candidate_id),
        replication_results=[_replication_result(candidate_id=candidate_id)],
        created_at=CREATED_AT,
    )


# --------------------------------------------------------------------------- #
# V06 integration arguments
# --------------------------------------------------------------------------- #
def integration_arguments(**overrides: Any) -> dict[str, Any]:
    """A fully-bound end-to-end path V06 should integrate.

    One Q05 clearance is threaded into both the V05 advancement and the P05 docket,
    and handed to V06 as the statistical receipt, so all three receipts describe
    the one candidate and rest on the same statistical clearance.
    """
    clearance = q05_receipt()
    arguments: dict[str, Any] = {
        "candidate_id": CANDIDATE_ID,
        "statistical_admissibility_receipt": clearance,
        "validation_advancement_receipt": v05_receipt(admissibility_receipt=clearance),
        "promotion_parliament_receipt": p05_receipt(selective_admissibility=clearance),
        "requesting_role": GOVERNOR_ROLE,
        "created_at": CREATED_AT,
    }
    arguments.update(overrides)
    return arguments
