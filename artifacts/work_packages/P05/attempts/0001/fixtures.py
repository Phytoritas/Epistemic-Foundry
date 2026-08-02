"""Fixtures for the P05 evolution-promotion Parliament gate suites.

Every docket component here is built through the *sealed owning surface* the gate
composes — the Q05 selective-admissibility receipt through
``evaluation.v4_q05``'s own gate and its statistics/firewall/fitness builders, the
adjudication through ``evidence_parliament``, the Red Queen results through
``red_queen_lab``, the adversarial lanes through ``retrieval.v4_o05`` — never
asserted by hand where an owner exists.  A component the owner would refuse would
test the fixture rather than the gate, and building through the owners means a
canonical change breaks these fixtures instead of letting them drift.  The two
artifacts with no builder in the source tree, the minority report and the
replication result, are assembled to their canonical schema and sealed with the
same hashing helper the runtime uses.
"""

from __future__ import annotations

from typing import Any

from epistemic_foundry.domain.hashing import hash_excluding
from epistemic_foundry.evaluation.fitness import (
    FITNESS_DIMENSIONS,
    build_fitness_vector,
)
from epistemic_foundry.evaluation.v4_q05 import gate as q05
from epistemic_foundry.evidence_parliament.adjudication import build_adjudication
from epistemic_foundry.red_queen_lab.challenges import build_challenge_result
from epistemic_foundry.retrieval.v4_o05 import adversarial_lanes
from epistemic_foundry.statistics.multiplicity import build_multiplicity_adjustment
from epistemic_foundry.statistics.search_record import build_search_statistics_record
from epistemic_foundry.statistics.selective import build_selective_inference_report
from epistemic_foundry.statistics.sequential import build_sequential_ledger
from epistemic_foundry.validation_bay.replication import build_replication_plan
from epistemic_foundry.verifier_firewall.firewall import (
    build_evaluator_bundle,
    build_holdout_manifest,
)

CANDIDATE_ID = "CAND-P05-1"
CANDIDATE_REVISION = 1
REQUESTED_LEVEL = "EMPIRICALLY_TESTED"
RUN_ID = "RUN-P05-1"
FAMILY_ID = "FAM-P05-1"
EVALUATOR_ID = "EVAL-P05-1"
CREATED_AT = "2026-08-02T00:00:00+00:00"
A_HASH = "sha256:" + "a" * 64
B_HASH = "sha256:" + "b" * 64

#: A governor principal and role that are *not* candidate-generating, so the
#: gate's authority guard permits them to drive the convening decision.
GOVERNOR_ID = "gov-p05-1"
GOVERNOR_ROLE = "evolution_governor"

#: A candidate-generating role the authority guard must refuse.
CANDIDATE_ROLE = "hypothesis_mutator"


# -- lineage (composes reasoning.v4_r05 LINEAGE_KIND) ----------------------


def lineage(*, candidate_id: str = CANDIDATE_ID, **overrides: Any) -> dict[str, Any]:
    """A schema-valid candidate lineage naming the candidate under review."""
    document: dict[str, Any] = {
        "lineage_id": "LIN-P05-1",
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
    document.update(overrides)
    return document


# -- adjudication (composes evidence_parliament / P04) ---------------------


def _gate_decisions(*, all_pass: bool = True) -> list[dict[str, Any]]:
    decisions = [
        {"gate_id": "G11_PARLIAMENT", "name": "parliament", "status": "PASS"},
        {"gate_id": "G09_RED_QUEEN", "name": "red_queen", "status": "PASS"},
    ]
    if not all_pass:
        decisions.append(
            {"gate_id": "G07_VALIDATION_LEAKAGE", "name": "leakage", "status": "FAIL"}
        )
    return decisions


def adjudication(
    *,
    hypothesis_id: str = CANDIDATE_ID,
    minority_report_ids: list[str] | None = None,
    promotion_recommendation: str = "INBOX",
    all_gates_pass: bool = True,
    refuse_override: bool = True,
    **overrides: Any,
) -> dict[str, Any]:
    """A Parliament adjudication bound to its deterministic gate results.

    Built through the owning surface, which derives the override flag from the
    gate decisions rather than trusting a caller.  ``all_gates_pass=False`` with
    an advancing recommendation and ``refuse_override=False`` yields the recorded
    override-attempt fixture the negative suite needs.
    """
    record = build_adjudication(
        run_id=RUN_ID,
        hypothesis_id=hypothesis_id,
        gate_decisions=_gate_decisions(all_pass=all_gates_pass),
        brief_ids=["BRIEF-1"],
        cross_examination_ids=["CX-1"],
        verdict="SUPPORTED",
        promotion_recommendation=promotion_recommendation,
        rationale="the deliberation, recorded for review",
        strongest_support_id="EV-SUP-1",
        strongest_counterevidence_id="EV-CNT-1",
        minority_report_ids=minority_report_ids or [],
        adjudication_id="ADJ-P05-1",
        created_at=CREATED_AT,
        refuse_override=refuse_override,
    )
    record.update(overrides)
    return record


# -- minority report (no source builder; sealed to schema) -----------------


def minority_report(
    *,
    minority_report_id: str = "MIN-P05-1",
    preservation_status: str = "preserved",
    **overrides: Any,
) -> dict[str, Any]:
    """A schema-valid minority report, sealed with the runtime hashing helper."""
    document: dict[str, Any] = {
        "minority_report_id": minority_report_id,
        "run_id": RUN_ID,
        "author_role": "minority_reporter",
        "minority_claim": "the majority may overstate the effect outside the tested scope",
        "evidence_ids": ["EV-MIN-1"],
        "why_majority_may_be_wrong": "the strongest support rests on one setting",
        "unresolved_test": "a cross-scope replication that has not been run",
        "expected_information_gain": 0.4,
        "preservation_status": preservation_status,
        "created_at": CREATED_AT,
    }
    document.update(overrides)
    document["report_hash"] = hash_excluding(document, "report_hash")
    return document


# -- Red Queen results (composes red_queen_lab) ----------------------------


def red_queen_results(
    *,
    candidate_id: str = CANDIDATE_ID,
    outcome: str = "SURVIVED",
    genome_id: str = "CG-P05-1",
) -> list[dict[str, Any]]:
    """One challenge match against the candidate, built through the owner.

    ``SURVIVED`` clears; ``REFUTED`` (twice, so the refutation replicates) and the
    unresolved states are produced by passing a different ``outcome``.
    """
    reproduction = ["REPRO-1"] if outcome in {"REFUTED", "SCOPE_RESTRICTED"} else []
    return [
        build_challenge_result(
            challenge_genome_id=genome_id,
            target_candidate_id=candidate_id,
            stage_result_id="SR-1",
            outcome=outcome,
            severity="major",
            observed_effect="the candidate's behaviour under the challenge",
            reproduction_artifact_ids=reproduction,
            challenge_result_id="CR-P05-1",
        )
    ]


def searched_adversarial_lanes() -> list[str]:
    """The full set of adversarial evidence lanes the O05 surface declares."""
    return list(adversarial_lanes())


# -- statistical clearance (composes evaluation.v4_q05 / Q05) --------------


def _fitness_vector(candidate_id: str = CANDIDATE_ID) -> dict[str, Any]:
    return build_fitness_vector(
        candidate_id=candidate_id,
        hard_gate_status=q05.hard_gate_pass_token(),
        hard_gate_failures=[],
        dimensions={name: 0.9 for name in FITNESS_DIMENSIONS},
        uncertainty={name: 0.05 for name in FITNESS_DIMENSIONS},
        evidence_receipt_ids=["ER-P05-1"],
        pareto_rank=0,
        domination_count=0,
        fitness_vector_id="FV-P05-1",
        computed_at=CREATED_AT,
    )


def _holdout_manifest() -> dict[str, Any]:
    return build_holdout_manifest(
        evaluator_id=EVALUATOR_ID,
        split_strategy="fixed_nested_holdout",
        public_partition_refs=["PUB-1"],
        hidden_partition_handles=["HID-P05-1"],
        ood_partition_handles=["OOD-P05-1"],
        adversarial_partition_handles=["ADV-P05-1"],
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
        code_artifact_id="CA-P05-1",
        code_hash=A_HASH,
        metric_contract_hash=A_HASH,
        environment_digest=A_HASH,
        dependency_lock_hash=A_HASH,
        data_contract_hash=A_HASH,
        policy_bundle_hash=A_HASH,
        qualification_report_id="QR-P05-1",
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
        report_id="SIR-P05-1",
    )


def _search_statistics(
    report: dict[str, Any], candidate_id: str = CANDIDATE_ID
) -> dict[str, Any]:
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
            ledger_id="STL-P05-1",
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
            adjustment_id="MTA-P05-1",
        ),
        selective_report=report,
        hidden_exposure_log_id="HEL-P05-1",
        candidate_lineage_id="LIN-P05-1",
        replication_result_id="RR-P05-1",
        record_id="SSR-P05-1",
        created_at=CREATED_AT,
    )


def statistical_clearance(
    *, candidate_id: str = CANDIDATE_ID, admit: bool = True
) -> dict[str, Any]:
    """A genuine Q05 selective-admissibility receipt.

    ``admit=True`` drives the sealed Q05 gate to ADMIT; ``admit=False`` withholds
    the holdout-read principal so Q05 still produces a receipt whose decision is
    not ADMIT — the failed statistical dimension the P05 suite needs, still a real
    Q05 output rather than a hand-forged one.
    """
    report = _selective_report(candidate_id)
    fitness = _fitness_vector(candidate_id)
    if not admit:
        # A non-passing hard gate makes Q05 refuse rather than admit.
        fitness = build_fitness_vector(
            candidate_id=candidate_id,
            hard_gate_status="FAIL",
            hard_gate_failures=["a_failed_dimension"],
            dimensions={name: 0.9 for name in FITNESS_DIMENSIONS},
            uncertainty={name: 0.05 for name in FITNESS_DIMENSIONS},
            evidence_receipt_ids=["ER-P05-1"],
            pareto_rank=0,
            domination_count=0,
            fitness_vector_id="FV-P05-1",
            computed_at=CREATED_AT,
        )
    return q05.derive_selective_admissibility(
        candidate_id=candidate_id,
        fitness_vector=fitness,
        evaluator_bundle=_evaluator_bundle(),
        holdout_manifest=_holdout_manifest(),
        search_statistics=_search_statistics(report, candidate_id),
        selective_report=report,
        requesting_principal_id=GOVERNOR_ID,
        requesting_role=GOVERNOR_ROLE,
        holdout_read_principal_ids=[GOVERNOR_ID],
        created_at=CREATED_AT,
    )


# -- replication (composes validation_bay.replication) ---------------------


def replication_plan(*, candidate_id: str = CANDIDATE_ID) -> dict[str, Any]:
    """A qualifying independent replication plan that lifts the ceiling."""
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
        replication_plan_id="RP-P05-1",
    )


def replication_result(
    *,
    candidate_id: str = CANDIDATE_ID,
    status: str = "REPLICATED",
    promotion_effect: str = "RAISE",
    **overrides: Any,
) -> dict[str, Any]:
    """A schema-valid replication result, sealed with the runtime hashing helper."""
    document: dict[str, Any] = {
        "replication_result_id": "RR-P05-1",
        "replication_plan_id": "RP-P05-1",
        "candidate_id": candidate_id,
        "status": status,
        "metric_summary": {"primary_metric": 0.42},
        "heterogeneity": "low across settings",
        "failure_analysis": [],
        "promotion_effect": promotion_effect,
        "artifact_ids": ["ART-RR-1"],
    }
    document.update(overrides)
    document["result_hash"] = hash_excluding(document, "result_hash")
    return document


# -- the fully-bound convening docket --------------------------------------


def docket(**overrides: Any) -> dict[str, Any]:
    """A complete, clean docket the gate should convene.

    A supported adjudication with all deterministic gates passing, one preserved
    minority report the adjudication references, a survived Red Queen match, full
    adversarial lane coverage, a Q05 ADMIT receipt, a qualifying replication plan
    and a raising replication result, driven by a non-candidate governor.
    """
    minority = minority_report()
    arguments: dict[str, Any] = {
        "candidate_id": CANDIDATE_ID,
        "candidate_revision": CANDIDATE_REVISION,
        "requested_level": REQUESTED_LEVEL,
        "lineage": lineage(),
        "adjudication": adjudication(
            minority_report_ids=[minority["minority_report_id"]]
        ),
        "selective_admissibility": statistical_clearance(),
        "red_queen_results": red_queen_results(),
        "searched_adversarial_lanes": searched_adversarial_lanes(),
        "requesting_principal_id": GOVERNOR_ID,
        "requesting_role": GOVERNOR_ROLE,
        "adaptive_search_used": True,
        "minority_reports": [minority],
        "replication_plan": replication_plan(),
        "replication_results": [replication_result()],
        "created_at": CREATED_AT,
    }
    arguments.update(overrides)
    return arguments
