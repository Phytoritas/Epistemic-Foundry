"""Fixtures for the Q05 selective-inference admissibility gate suites.

Every fitness vector, evaluator bundle, holdout manifest, statistical record and
selective-inference report here is built by the *sealed owning surface* that the
gate composes — ``evaluation.fitness``, ``verifier_firewall.firewall`` and the
``statistics`` family — never assembled by hand.  A fixture the owner would
refuse would test the fixture rather than the gate, and building through the
owners means a canonical change breaks these fixtures instead of letting them
drift.  The fifteen fitness dimensions and the passing hard-gate token are read
out of the surfaces that declare them for the same reason.
"""

from __future__ import annotations

from typing import Any

from epistemic_foundry.evaluation.fitness import (
    FITNESS_DIMENSIONS,
    build_fitness_vector,
)
from epistemic_foundry.evaluation.v4_q05 import gate as engine
from epistemic_foundry.statistics.multiplicity import build_multiplicity_adjustment
from epistemic_foundry.statistics.search_record import build_search_statistics_record
from epistemic_foundry.statistics.selective import build_selective_inference_report
from epistemic_foundry.statistics.sequential import build_sequential_ledger
from epistemic_foundry.verifier_firewall.firewall import (
    build_evaluator_bundle,
    build_holdout_manifest,
)

CANDIDATE_ID = "HG-1"
FAMILY_ID = "FAM-Q05-1"
EVALUATOR_ID = "EVAL-Q05-1"
CREATED_AT = "2026-08-02T00:00:00+00:00"
A_HASH = "sha256:" + "a" * 64
B_HASH = "sha256:" + "b" * 64

#: A governor principal and role that are *not* candidate-generating, so the
#: gate's authority guard permits them to drive the decision.
GOVERNOR_ID = "gov-1"
GOVERNOR_ROLE = "statistical_governor"

#: A hidden holdout handle the leakage fixtures reference by name.
HIDDEN_HANDLE = "HID-Q05-1"


def fitness_vector(
    *,
    candidate_id: str = CANDIDATE_ID,
    hard_gate_status: str | None = None,
    hard_gate_failures: list[str] | None = None,
    dimension_value: float = 0.9,
    **overrides: Any,
) -> dict[str, Any]:
    """A schema-valid, fully-scored multi-objective fitness vector.

    The passing status is read from the fitness schema through the gate, so the
    happy-path vector passes its own hard gate without restating the token.
    """
    status = hard_gate_status or engine.hard_gate_pass_token()
    document = build_fitness_vector(
        candidate_id=candidate_id,
        hard_gate_status=status,
        hard_gate_failures=hard_gate_failures or [],
        dimensions={name: dimension_value for name in FITNESS_DIMENSIONS},
        uncertainty={name: 0.05 for name in FITNESS_DIMENSIONS},
        evidence_receipt_ids=["ER-Q05-1"],
        pareto_rank=0,
        domination_count=0,
        fitness_vector_id="FV-Q05-1",
        computed_at=CREATED_AT,
    )
    document.update(overrides)
    return document


def scalar_fitness() -> dict[str, Any]:
    """A fitness that carries a single score and no separate dimensions."""
    return {
        "candidate_id": CANDIDATE_ID,
        "fitness_vector_id": "FV-Q05-1",
        "score": 0.97,
    }


def holdout_manifest(
    *,
    evaluator_id: str = EVALUATOR_ID,
    holdout_id: str = EVALUATOR_ID,
    hidden_partition_handles: list[str] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    """A sealed holdout manifest, candidate-unreadable by construction."""
    document = build_holdout_manifest(
        evaluator_id=evaluator_id,
        split_strategy="fixed_nested_holdout",
        public_partition_refs=["PUB-1"],
        hidden_partition_handles=hidden_partition_handles or [HIDDEN_HANDLE],
        ood_partition_handles=["OOD-Q05-1"],
        adversarial_partition_handles=["ADV-Q05-1"],
        content_hashes=[A_HASH],
        acl_policy_hash=B_HASH,
        log_redaction_policy="redact_all_hidden",
        cache_isolation_policy="per_run_isolated",
        holdout_id=holdout_id,
        sealed_at=CREATED_AT,
    )
    document.update(overrides)
    return document


def evaluator_bundle(
    *,
    evaluator_id: str = EVALUATOR_ID,
    holdout_manifest_id: str = EVALUATOR_ID,
    **overrides: Any,
) -> dict[str, Any]:
    """A sealed evaluator bundle, candidate-unreadable and run-immutable."""
    document = build_evaluator_bundle(
        evaluator_version="1.0.0",
        code_artifact_id="CA-Q05-1",
        code_hash=A_HASH,
        metric_contract_hash=A_HASH,
        environment_digest=A_HASH,
        dependency_lock_hash=A_HASH,
        data_contract_hash=A_HASH,
        policy_bundle_hash=A_HASH,
        qualification_report_id="QR-Q05-1",
        holdout_manifest_id=holdout_manifest_id,
        evaluator_id=evaluator_id,
        sealed_at=CREATED_AT,
    )
    document.update(overrides)
    return document


def selective_report(
    *,
    candidate_id: str = CANDIDATE_ID,
    replication_count: int = 2,
    candidates_considered: int = 3,
    selection_events: list[str] | None = None,
    naive_estimate: float = 0.5,
    bias_corrected_estimate: float = 0.4,
    **overrides: Any,
) -> dict[str, Any]:
    """A selective-inference report; its verdict is derived, not asserted.

    The defaults (two independent replications, few candidates) drive the owning
    surface to a ``low`` winner's-curse risk and an ``ALLOW`` recommendation, so
    the happy path clears; the negative suite widens the selection pressure to
    produce a non-clearing verdict.
    """
    document = build_selective_inference_report(
        candidate_id=candidate_id,
        selection_mechanism="argmax_over_generation",
        selection_events=selection_events or ["SE-1"],
        naive_estimate=naive_estimate,
        bias_corrected_estimate=bias_corrected_estimate,
        correction_method="conditional_shrinkage",
        uncertainty_interval=[0.2, 0.6],
        candidates_considered=candidates_considered,
        replication_count=replication_count,
        report_id="SIR-Q05-1",
    )
    document.update(overrides)
    return document


def _sequential_ledger() -> dict[str, Any]:
    return build_sequential_ledger(
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
        ledger_id="STL-Q05-1",
    )


def _multiplicity_adjustment() -> dict[str, Any]:
    return build_multiplicity_adjustment(
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
        adjustment_id="MTA-Q05-1",
    )


def search_statistics(
    *,
    candidate_id: str = CANDIDATE_ID,
    report: dict[str, Any] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    """The complete adaptive-search statistical record, built through its owner.

    Passing ``overrides`` mutates the sealed record after the fact; the gate
    re-derives the record hash, so an override that changes content without
    re-sealing is exactly the tampered record the integrity check must catch.
    """
    document = build_search_statistics_record(
        evolution_run_id="RUN-Q05-1",
        family_id=FAMILY_ID,
        candidate_id=candidate_id,
        sequential_ledger=_sequential_ledger(),
        multiplicity_adjustment=_multiplicity_adjustment(),
        selective_report=report
        if report is not None
        else selective_report(candidate_id=candidate_id),
        hidden_exposure_log_id="HEL-Q05-1",
        candidate_lineage_id="LIN-Q05-1",
        replication_result_id="RR-Q05-1",
        record_id="SSR-Q05-1",
        created_at=CREATED_AT,
    )
    document.update(overrides)
    return document


def gate_arguments(**overrides: Any) -> dict[str, Any]:
    """A fully-bound, admissible candidate the gate should forward to review.

    A passing multi-objective fitness vector, a sealed hidden evaluation, a
    complete corrected statistical record whose verdict is ``ALLOW``, and a
    non-candidate governor principal on the holdout access list.
    """
    report = selective_report()
    arguments: dict[str, Any] = {
        "candidate_id": CANDIDATE_ID,
        "fitness_vector": fitness_vector(),
        "evaluator_bundle": evaluator_bundle(),
        "holdout_manifest": holdout_manifest(),
        "search_statistics": search_statistics(report=report),
        "selective_report": report,
        "requesting_principal_id": GOVERNOR_ID,
        "requesting_role": GOVERNOR_ROLE,
        "holdout_read_principal_ids": [GOVERNOR_ID],
        "created_at": CREATED_AT,
    }
    arguments.update(overrides)
    return arguments
