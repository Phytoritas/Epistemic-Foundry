"""Fixtures for the O06 search-completeness / novelty / prior-art gate suites.

Every artifact is produced through the *sealed owning surface* the gate
composes, never assembled by hand: the corpus snapshot and prior-art boundary
come from K05, the retrieval plan and lane receipts from O05, the novelty
assessment from K05's boundary-bounded assessor, and the Q05 admissibility
receipt from the sealed Q05 gate driven by the sealed evaluation, firewall and
statistics builders.  A hand-written shape would only ever test itself, and
building through the owners means a canonical change breaks these fixtures
instead of letting them drift.

The happy-path certificate deliberately leaves external sources unsearched, so
its novelty ceiling is the search-conditional rung rather than the corpus-novel
one, and the novelty assessment it grounds states a claimable novelty status.
The degraded-receipt helpers craft the schema-valid PARTIAL/BLOCKED/FAILED
receipts O05's emitters never produce, which is the only way to exercise the
non-passing completion branches the certificate reconciliation derives.
"""

from __future__ import annotations

from typing import Any

from epistemic_foundry.evaluation.fitness import (
    FITNESS_DIMENSIONS,
    build_fitness_vector,
)
from epistemic_foundry.evaluation.v4_q05 import gate as q05
from epistemic_foundry.evidence.v4_k05 import (
    assess_novelty_within_boundary,
    declare_prior_art_boundary,
    pin_corpus_snapshot,
)
from epistemic_foundry.retrieval.v4_o05 import (
    SELECTED_DISPOSITION_POSITION,
    adversarial_lanes,
    build_evolution_retrieval_plan,
    canonical_lane_order,
    emit_searched_lane_receipt,
    emit_unsearched_lane_receipt,
    plan_disposition_vocabulary,
    statement_digest,
)
from epistemic_foundry.retrieval.v4_o06 import (
    build_search_completeness_certificate,
)
from epistemic_foundry.statistics.multiplicity import build_multiplicity_adjustment
from epistemic_foundry.statistics.search_record import build_search_statistics_record
from epistemic_foundry.statistics.selective import build_selective_inference_report
from epistemic_foundry.statistics.sequential import build_sequential_ledger
from epistemic_foundry.verifier_firewall.firewall import (
    build_evaluator_bundle,
    build_holdout_manifest,
)

CORPUS_ID = "CORPUS-O06"
PINNED_AT = "2026-08-02T00:00:00Z"
STARTED_AT = "2026-08-02T01:00:00Z"
FINISHED_AT = "2026-08-02T01:05:00Z"
ASSESSED_AT = "2026-08-02T02:00:00Z"
CREATED_AT = "2026-08-02T03:00:00+00:00"
AS_OF_DATE = "2026-01-01"

RUN_ID = "ER-O06-1"
QUERY_PLAN_ID = "QP-O06-1"
SUBJECT_REF = "HY-O06-1"
CANDIDATE_ID = "EC-O06-1"
ASSESSOR_REF = "novelty-examiner-1"
WORK_CLASS = "E3"
GENERATED_AT = "2026-08-02T02:30:00+00:00"
STATEMENT_HASH = statement_digest("the mechanism the candidate proposes")

SEARCHED_SOURCES = ("pinned-local-corpus",)
UNSEARCHED_SOURCES = ("patent-registers", "paywalled-journals")

MECHANISM_ID = "DOC-MECHANISM"
COUNTER_ID = "DOC-COUNTER"
LATE_ID = "DOC-LATE"

EVIDENCE_DECISION_IDS = ("LDE-O06-1",)
INDEX_VERSIONS = {"pinned-local-corpus": "1.4.0"}
QUERY_TEXT = "mechanism and its counter-evidence within the pinned corpus"

# -- Q05 admissibility inputs ---------------------------------------------
FAMILY_ID = "FAM-O06-1"
EVALUATOR_ID = "EVAL-O06-1"
GOVERNOR_ID = "gov-1"
GOVERNOR_ROLE = "statistical_governor"
HIDDEN_HANDLE = "HID-O06-1"
A_HASH = "sha256:" + "a" * 64
B_HASH = "sha256:" + "b" * 64


# -- K05 corpus, boundary and novelty --------------------------------------


def _document(document_id: str, *, fill: str, source_date: str) -> dict[str, Any]:
    return {
        "content_hash": "sha256:" + fill * 64,
        "document_id": document_id,
        "license_status": "open_access",
        "source_date": source_date,
        "source_uri": None,
    }


def documents() -> list[dict[str, Any]]:
    return [
        _document(MECHANISM_ID, fill="1", source_date="2024-01-02"),
        _document(COUNTER_ID, fill="2", source_date="2024-05-06"),
        _document(LATE_ID, fill="5", source_date="2026-09-09"),
    ]


def snapshot(**overrides: Any) -> dict[str, Any]:
    keywords: dict[str, Any] = {
        "corpus_id": CORPUS_ID,
        "documents": documents(),
        "pinned_at": PINNED_AT,
    }
    keywords.update(overrides)
    return pin_corpus_snapshot(**keywords)


def boundary(pinned: dict[str, Any] | None = None, **overrides: Any) -> dict[str, Any]:
    keywords: dict[str, Any] = {
        "snapshot": pinned if pinned is not None else snapshot(),
        "as_of_date": AS_OF_DATE,
        "searched_sources": list(SEARCHED_SOURCES),
        "unsearched_sources": list(UNSEARCHED_SOURCES),
    }
    keywords.update(overrides)
    return declare_prior_art_boundary(**keywords)


# -- O05 plan and lane receipts --------------------------------------------


def _selecting() -> str:
    return plan_disposition_vocabulary()[SELECTED_DISPOSITION_POSITION]


def _sentinel() -> str:
    return plan_disposition_vocabulary()[SELECTED_DISPOSITION_POSITION + 1]


def lane_dispositions(**overrides: str) -> dict[str, str]:
    """Select every adversarial lane; sentinel the rest."""
    selected = set(adversarial_lanes())
    dispositions = {
        lane: _selecting() if lane in selected else _sentinel()
        for lane in canonical_lane_order()
    }
    dispositions.update(overrides)
    return dispositions


def scope_filter() -> dict[str, Any]:
    return {
        "comparator": None,
        "conditions": {},
        "domain": "epistemic-foundry",
        "domain_extensions": {},
        "entity_subtype": None,
        "entity_type": None,
        "exclusion_criteria": [],
        "geography": None,
        "inclusion_criteria": [],
        "intervention_or_exposure": None,
        "jurisdiction": None,
        "language": None,
        "lifecycle_stage": None,
        "measurement_time": None,
        "population": None,
        "setting": None,
        "spatial_scale": None,
        "temporal_scale": None,
        "time_period": None,
        "unit_of_analysis": None,
    }


def plan(pinned: dict[str, Any] | None = None, **overrides: Any) -> dict[str, Any]:
    pinned = pinned if pinned is not None else snapshot()
    keywords: dict[str, Any] = {
        "snapshot": pinned,
        "boundary": boundary(pinned),
        "run_id": RUN_ID,
        "query_plan_id": QUERY_PLAN_ID,
        "subject_document_ids": [MECHANISM_ID, COUNTER_ID],
        "lane_dispositions": lane_dispositions(),
    }
    keywords.update(overrides)
    return build_evolution_retrieval_plan(**keywords)


def searched_receipt(
    declared: dict[str, Any], pinned: dict[str, Any], lane: str, **overrides: Any
) -> dict[str, Any]:
    keywords: dict[str, Any] = {
        "plan": declared,
        "snapshot": pinned,
        "lane": lane,
        "query_text": QUERY_TEXT,
        "scope_filter": scope_filter(),
        "index_versions": dict(INDEX_VERSIONS),
        "result_document_ids": [MECHANISM_ID],
        "lane_decision_evidence_ids": list(EVIDENCE_DECISION_IDS),
        "started_at": STARTED_AT,
        "finished_at": FINISHED_AT,
    }
    keywords.update(overrides)
    return emit_searched_lane_receipt(**keywords)


def receipts(
    declared: dict[str, Any] | None = None, pinned: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """One receipt per canonical lane, matching the plan's own dispositions."""
    pinned = pinned if pinned is not None else snapshot()
    declared = declared if declared is not None else plan(pinned)
    selected = set(declared["selected_lanes"])
    rows: list[dict[str, Any]] = []
    for lane in canonical_lane_order():
        if lane in selected:
            rows.append(searched_receipt(declared, pinned, lane))
        else:
            rows.append(
                emit_unsearched_lane_receipt(
                    plan=declared,
                    lane=lane,
                    lane_decision_evidence_ids=list(EVIDENCE_DECISION_IDS),
                )
            )
    return rows


def partial_receipt(base: dict[str, Any]) -> dict[str, Any]:
    """A schema-valid PARTIAL execution receipt derived from a searched one.

    O05's emitter derives SEARCHED_* states from results, so a PARTIAL receipt —
    the state that drives a required lane to a non-passing completion — is
    produced here by re-shaping one to the PARTIAL branch the receipt schema
    permits.
    """
    return dict(base, search_state="PARTIAL", stop_reason="budget_exhausted")


def failed_receipt(base: dict[str, Any]) -> dict[str, Any]:
    """A schema-valid FAILED execution receipt derived from a searched one."""
    return dict(
        base,
        search_state="FAILED",
        stop_reason="provider_failure",
        result_ids=None,
        result_count=None,
        excluded_count=None,
        recall_proxy=None,
        errors=["the provider failed mid-search"],
    )


def blocked_receipt(base: dict[str, Any]) -> dict[str, Any]:
    """A schema-valid BLOCKED execution receipt derived from a searched one."""
    return dict(
        base,
        search_state="BLOCKED",
        stop_reason="policy_blocked",
        result_ids=None,
        result_count=None,
        excluded_count=None,
        recall_proxy=None,
        errors=["a policy blocked the lane"],
    )


# -- O06 certificate -------------------------------------------------------


def required_lanes() -> list[str]:
    """The lanes this work class requires: every selected adversarial lane."""
    return list(adversarial_lanes())


def certificate_arguments(
    declared: dict[str, Any] | None = None,
    pinned: dict[str, Any] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    pinned = pinned if pinned is not None else snapshot()
    declared = declared if declared is not None else plan(pinned)
    arguments: dict[str, Any] = {
        "plan": declared,
        "receipts": receipts(declared, pinned),
        "work_class": WORK_CLASS,
        "required_lanes": required_lanes(),
        "subject_ref": SUBJECT_REF,
        "generated_at": GENERATED_AT,
    }
    arguments.update(overrides)
    return arguments


def certificate(
    declared: dict[str, Any] | None = None,
    pinned: dict[str, Any] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    return build_search_completeness_certificate(
        **certificate_arguments(declared, pinned, **overrides)
    )


# -- K05 novelty assessment citing the certificate -------------------------


def novelty_assessment(
    certificate_id: str,
    pinned: dict[str, Any] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    pinned = pinned if pinned is not None else snapshot()
    keywords: dict[str, Any] = {
        "boundary": boundary(pinned),
        "run_id": RUN_ID,
        "subject_ref": SUBJECT_REF,
        "statement_hash": STATEMENT_HASH,
        "search_completeness_certificate_id": certificate_id,
        "novelty_dimensions": ["MECHANISM"],
        "closest_prior_art_refs": [],
        "distinguishing_features": ["a mechanism the pinned corpus does not state"],
        "assessor_ref": ASSESSOR_REF,
        "assessed_at": ASSESSED_AT,
    }
    keywords.update(overrides)
    return assess_novelty_within_boundary(**keywords)


# -- Q05 admissibility receipt ---------------------------------------------


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
        report_id="SIR-O06-1",
    )


def _search_statistics(candidate_id: str, report: dict[str, Any]) -> dict[str, Any]:
    return build_search_statistics_record(
        evolution_run_id="RUN-O06-1",
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
            ledger_id="STL-O06-1",
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
            adjustment_id="MTA-O06-1",
        ),
        selective_report=report,
        hidden_exposure_log_id="HEL-O06-1",
        candidate_lineage_id="LIN-O06-1",
        replication_result_id="RR-O06-1",
        record_id="SSR-O06-1",
        created_at=CREATED_AT,
    )


def _fitness_vector(candidate_id: str = CANDIDATE_ID) -> dict[str, Any]:
    return build_fitness_vector(
        candidate_id=candidate_id,
        hard_gate_status=q05.hard_gate_pass_token(),
        hard_gate_failures=[],
        dimensions={name: 0.9 for name in FITNESS_DIMENSIONS},
        uncertainty={name: 0.05 for name in FITNESS_DIMENSIONS},
        evidence_receipt_ids=["ER-O06-1"],
        pareto_rank=0,
        domination_count=0,
        fitness_vector_id="FV-O06-1",
        computed_at=CREATED_AT,
    )


def _holdout_manifest() -> dict[str, Any]:
    return build_holdout_manifest(
        evaluator_id=EVALUATOR_ID,
        split_strategy="fixed_nested_holdout",
        public_partition_refs=["PUB-1"],
        hidden_partition_handles=[HIDDEN_HANDLE],
        ood_partition_handles=["OOD-O06-1"],
        adversarial_partition_handles=["ADV-O06-1"],
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
        code_artifact_id="CA-O06-1",
        code_hash=A_HASH,
        metric_contract_hash=A_HASH,
        environment_digest=A_HASH,
        dependency_lock_hash=A_HASH,
        data_contract_hash=A_HASH,
        policy_bundle_hash=A_HASH,
        qualification_report_id="QR-O06-1",
        holdout_manifest_id=EVALUATOR_ID,
        evaluator_id=EVALUATOR_ID,
        sealed_at=CREATED_AT,
    )


def admissibility_receipt(candidate_id: str = CANDIDATE_ID) -> dict[str, Any]:
    """A sealed Q05 ADMIT receipt forwarding the candidate to promotion review."""
    report = _selective_report(candidate_id)
    return q05.evaluate_selective_admissibility(
        candidate_id=candidate_id,
        fitness_vector=_fitness_vector(candidate_id),
        evaluator_bundle=_evaluator_bundle(),
        holdout_manifest=_holdout_manifest(),
        search_statistics=_search_statistics(candidate_id, report),
        selective_report=report,
        requesting_principal_id=GOVERNOR_ID,
        requesting_role=GOVERNOR_ROLE,
        holdout_read_principal_ids=[GOVERNOR_ID],
        created_at=CREATED_AT,
    )


# -- gate arguments --------------------------------------------------------


def gate_arguments(**overrides: Any) -> dict[str, Any]:
    """A fully-bound, admissible novelty claim the gate should forward to review."""
    pinned = snapshot()
    declared = plan(pinned)
    cert = certificate(declared, pinned)
    arguments: dict[str, Any] = {
        "candidate_id": CANDIDATE_ID,
        "subject_ref": SUBJECT_REF,
        "certificate": cert,
        "novelty_assessment": novelty_assessment(cert["certificate_id"], pinned),
        "admissibility_receipt": admissibility_receipt(),
        "requesting_role": GOVERNOR_ROLE,
        "required_source_ids": list(SEARCHED_SOURCES),
        "created_at": CREATED_AT,
    }
    arguments.update(overrides)
    return arguments
