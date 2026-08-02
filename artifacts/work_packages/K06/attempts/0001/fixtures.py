"""Fixtures for the K06 evidence/holdout leakage-gate suites.

Every fixture is produced through a sealed builder rather than hand-written: the
snapshot, partition, holdout and prior-art boundary come from K05, the retrieval
plan and lane receipts from O05, and the evaluator bundle and firewall from the
Verifier Firewall.  A hand-written record would only ever test itself; a record
the owning module accepts is the one the gate has to compose.

The corpus is split on purpose.  Two documents are visible and three are
concealed — one hidden, one out-of-distribution, one adversarial — because the
whole point of the gate is that a candidate-facing operation may touch the two
and never the three.  Every document is dated on or before the prior-art bound
so that concealment, not the date, is what keeps a document out of an admission.
"""

from __future__ import annotations

from typing import Any

from epistemic_foundry.evidence.v4_k05 import (
    declare_prior_art_boundary,
    partition_pinned_snapshot,
    pin_corpus_snapshot,
    seal_holdout_boundary,
)
from epistemic_foundry.retrieval.v4_o05 import (
    build_evolution_retrieval_plan,
    canonical_lane_order,
    emit_searched_lane_receipt,
    emit_unsearched_lane_receipt,
    plan_disposition_vocabulary,
)
from epistemic_foundry.verifier_firewall.firewall import (
    VerifierFirewall,
    build_evaluator_bundle,
)

CORPUS_ID = "CORPUS-K06"
PINNED_AT = "2026-08-02T00:00:00Z"
SEALED_AT = "2026-08-02T00:00:00Z"
STARTED_AT = "2026-08-02T01:00:00Z"
FINISHED_AT = "2026-08-02T01:05:00Z"
BOUND_AT = "2026-08-02T02:00:00Z"
AS_OF_DATE = "2026-01-01"

EVALUATOR_ID = "EV-K06-1"
SPLIT_STRATEGY = "hash-partition"
ACL_POLICY_HASH = "sha256:" + "d" * 64
LOG_REDACTION_POLICY = "strip-holdout-refs"
CACHE_ISOLATION_POLICY = "per-run-namespace"
AUDITOR = "auditor-k06-1"

RUN_ID = "ER-K06-1"
QUERY_PLAN_ID = "QP-K06-1"
EVIDENCE_DECISION_IDS = ("LDE-K06-1",)
INDEX_VERSIONS = {"pinned-local-corpus": "1.4.0"}
QUERY_TEXT = "mechanism evidence within the visible partition"

VIS_1 = "DOC-VIS-1"
VIS_2 = "DOC-VIS-2"
HIDDEN_ID = "DOC-HIDDEN"
OOD_ID = "DOC-OOD"
ADVERSARIAL_ID = "DOC-ADVERSARIAL"

SEARCHED_SOURCES = ("pinned-local-corpus",)
UNSEARCHED_SOURCES = ("patent-registers", "paywalled-journals")

TARGET_ID = "vt-k06-target"
CANDIDATE_KIND = "experiment-genome"
EFFECT_RECEIPT_CHANNEL_ID = "ER-CH-K06-1"
HARD_LIMITS = {"tokens": 100_000, "wall_seconds": 600}

RUN_OR_BUNDLE_ID = "RUN-K06-1"
ACCESS_LOG_ARTIFACT_ID = "ACL-K06-1"
LEAKAGE_SURFACES = ("tool", "log", "cache")


def document(
    document_id: str, *, fill: str, license_status: str, source_date: str
) -> dict[str, Any]:
    return {
        "content_hash": "sha256:" + fill * 64,
        "document_id": document_id,
        "license_status": license_status,
        "source_date": source_date,
        "source_uri": None,
    }


def documents() -> list[dict[str, Any]]:
    return [
        document(
            VIS_1, fill="1", license_status="open_access", source_date="2024-01-02"
        ),
        document(VIS_2, fill="2", license_status="licensed", source_date="2024-05-06"),
        document(
            HIDDEN_ID, fill="3", license_status="open_access", source_date="2025-02-03"
        ),
        document(
            OOD_ID,
            fill="4",
            license_status="fair_use_metadata_only",
            source_date="2025-07-08",
        ),
        document(
            ADVERSARIAL_ID,
            fill="5",
            license_status="open_access",
            source_date="2025-09-09",
        ),
    ]


def snapshot(**overrides: Any) -> dict[str, Any]:
    keywords: dict[str, Any] = {
        "corpus_id": CORPUS_ID,
        "documents": documents(),
        "pinned_at": PINNED_AT,
    }
    keywords.update(overrides)
    return pin_corpus_snapshot(**keywords)


def foreign_snapshot(**overrides: Any) -> dict[str, Any]:
    """A snapshot over genuinely different bytes, so its handles and snapshot id
    are disjoint from :func:`snapshot`.  A holdout sealed over it names material
    the primary snapshot cannot derive — the "not drawn from this snapshot" case.
    """
    docs = [
        document(
            "DOC-FOREIGN-1",
            fill="7",
            license_status="open_access",
            source_date="2024-03-04",
        ),
        document(
            "DOC-FOREIGN-2",
            fill="8",
            license_status="licensed",
            source_date="2024-06-07",
        ),
    ]
    keywords: dict[str, Any] = {
        "corpus_id": "CORPUS-K06-FOREIGN",
        "documents": docs,
        "pinned_at": PINNED_AT,
    }
    keywords.update(overrides)
    return pin_corpus_snapshot(**keywords)


def foreign_partition(pinned: dict[str, Any] | None = None) -> dict[str, Any]:
    pinned = pinned if pinned is not None else foreign_snapshot()
    return partition_pinned_snapshot(
        snapshot=pinned,
        visible_document_ids=["DOC-FOREIGN-1"],
        hidden_document_ids=["DOC-FOREIGN-2"],
        ood_document_ids=[],
        adversarial_document_ids=[],
    )


def partition(pinned: dict[str, Any] | None = None, **overrides: Any) -> dict[str, Any]:
    keywords: dict[str, Any] = {
        "snapshot": pinned if pinned is not None else snapshot(),
        "visible_document_ids": [VIS_1, VIS_2],
        "hidden_document_ids": [HIDDEN_ID],
        "ood_document_ids": [OOD_ID],
        "adversarial_document_ids": [ADVERSARIAL_ID],
    }
    keywords.update(overrides)
    return partition_pinned_snapshot(**keywords)


def holdout(
    pinned: dict[str, Any] | None = None,
    split: dict[str, Any] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    pinned = pinned if pinned is not None else snapshot()
    split = split if split is not None else partition(pinned)
    keywords: dict[str, Any] = {
        "snapshot": pinned,
        "partition": split,
        "evaluator_id": EVALUATOR_ID,
        "split_strategy": SPLIT_STRATEGY,
        "acl_policy_hash": ACL_POLICY_HASH,
        "log_redaction_policy": LOG_REDACTION_POLICY,
        "cache_isolation_policy": CACHE_ISOLATION_POLICY,
        "sealed_at": SEALED_AT,
    }
    keywords.update(overrides)
    return seal_holdout_boundary(**keywords)


def evaluator_bundle(
    sealed_holdout: dict[str, Any], **overrides: Any
) -> dict[str, Any]:
    keywords: dict[str, Any] = {
        "evaluator_version": "1.0.0",
        "code_artifact_id": "CA-K06-1",
        "code_hash": "sha256:" + "1" * 64,
        "metric_contract_hash": "sha256:" + "2" * 64,
        "environment_digest": "sha256:" + "3" * 64,
        "dependency_lock_hash": "sha256:" + "4" * 64,
        "data_contract_hash": "sha256:" + "5" * 64,
        "policy_bundle_hash": "sha256:" + "6" * 64,
        "qualification_report_id": "EQR-K06-1",
        "holdout_manifest_id": sealed_holdout["holdout_id"],
        "evaluator_id": sealed_holdout["evaluator_id"],
        "sealed_at": SEALED_AT,
    }
    keywords.update(overrides)
    return build_evaluator_bundle(**keywords)


def firewall(
    sealed_holdout: dict[str, Any] | None = None,
    bundle: dict[str, Any] | None = None,
    *,
    holdout_read_principal_ids: list[str] | None = None,
) -> VerifierFirewall:
    sealed_holdout = sealed_holdout if sealed_holdout is not None else holdout()
    bundle = bundle if bundle is not None else evaluator_bundle(sealed_holdout)
    return VerifierFirewall(
        bundle,
        sealed_holdout,
        holdout_read_principal_ids=holdout_read_principal_ids or [AUDITOR],
    )


def boundary(pinned: dict[str, Any] | None = None, **overrides: Any) -> dict[str, Any]:
    keywords: dict[str, Any] = {
        "snapshot": pinned if pinned is not None else snapshot(),
        "as_of_date": AS_OF_DATE,
        "searched_sources": list(SEARCHED_SOURCES),
        "unsearched_sources": list(UNSEARCHED_SOURCES),
    }
    keywords.update(overrides)
    return declare_prior_art_boundary(**keywords)


def version_arguments(
    pinned: dict[str, Any] | None = None, **overrides: Any
) -> dict[str, Any]:
    """Every input the version binder needs, all drawn from one snapshot."""
    pinned = pinned if pinned is not None else snapshot()
    split = partition(pinned)
    sealed = holdout(pinned, split)
    bundle = evaluator_bundle(sealed)
    guard = firewall(sealed, bundle)
    arguments: dict[str, Any] = {
        "snapshot": pinned,
        "partition": split,
        "holdout": sealed,
        "evaluator_bundle": bundle,
        "firewall": guard,
        "boundary": boundary(pinned),
        "bound_at": BOUND_AT,
    }
    arguments.update(overrides)
    return arguments


def selecting_disposition() -> str:
    return plan_disposition_vocabulary()[0]


def sentinel_disposition() -> str:
    return plan_disposition_vocabulary()[1]


def lane_dispositions(**overrides: str) -> dict[str, str]:
    """Select the mechanism lane; sentinel the rest, so one execution receipt exists."""
    dispositions = {lane: sentinel_disposition() for lane in canonical_lane_order()}
    dispositions["mechanism"] = selecting_disposition()
    dispositions.update(overrides)
    return dispositions


def plan(
    pinned: dict[str, Any] | None = None,
    subject_document_ids: list[str] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    pinned = pinned if pinned is not None else snapshot()
    keywords: dict[str, Any] = {
        "snapshot": pinned,
        "boundary": boundary(pinned),
        "run_id": RUN_ID,
        "query_plan_id": QUERY_PLAN_ID,
        "subject_document_ids": subject_document_ids
        if subject_document_ids is not None
        else [VIS_1, VIS_2],
        "lane_dispositions": lane_dispositions(),
    }
    keywords.update(overrides)
    return build_evolution_retrieval_plan(**keywords)


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


def searched_receipt(
    declared: dict[str, Any] | None = None,
    pinned: dict[str, Any] | None = None,
    *,
    lane: str = "mechanism",
    result_document_ids: list[str] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    pinned = pinned if pinned is not None else snapshot()
    declared = declared if declared is not None else plan(pinned)
    keywords: dict[str, Any] = {
        "plan": declared,
        "snapshot": pinned,
        "lane": lane,
        "query_text": QUERY_TEXT,
        "scope_filter": scope_filter(),
        "index_versions": dict(INDEX_VERSIONS),
        "result_document_ids": result_document_ids
        if result_document_ids is not None
        else [VIS_1],
        "lane_decision_evidence_ids": list(EVIDENCE_DECISION_IDS),
        "started_at": STARTED_AT,
        "finished_at": FINISHED_AT,
    }
    keywords.update(overrides)
    return emit_searched_lane_receipt(**keywords)


def sentinel_receipt(
    declared: dict[str, Any] | None = None,
    pinned: dict[str, Any] | None = None,
    *,
    lane: str = "lexical",
    **overrides: Any,
) -> dict[str, Any]:
    pinned = pinned if pinned is not None else snapshot()
    declared = declared if declared is not None else plan(pinned)
    keywords: dict[str, Any] = {
        "plan": declared,
        "lane": lane,
        "lane_decision_evidence_ids": list(EVIDENCE_DECISION_IDS),
    }
    keywords.update(overrides)
    return emit_unsearched_lane_receipt(**keywords)


def target_manifest(**overrides: Any) -> dict[str, Any]:
    scope = {
        key: None
        for key in (
            "domain",
            "population",
            "entity_type",
            "entity_subtype",
            "unit_of_analysis",
            "setting",
            "geography",
            "jurisdiction",
            "language",
            "lifecycle_stage",
            "spatial_scale",
            "temporal_scale",
            "time_period",
            "measurement_time",
            "intervention_or_exposure",
            "comparator",
        )
    }
    scope.update(
        {
            "inclusion_criteria": [],
            "exclusion_criteria": [],
            "conditions": {},
            "domain_extensions": {},
        }
    )
    payload: dict[str, Any] = {
        "allowed_data_classes": ["internal"],
        "approval_policy": "high_risk_only",
        "artifact_hashes": ["sha256:" + "a" * 64],
        "capability_requirements": [],
        "constraints": [],
        "entrypoint": "run.py",
        "identifiability_notes": [],
        "inputs": [],
        "interface_version": "1.0.0",
        "network_policy": "disabled",
        "outputs": [],
        "parameters": [],
        "provenance_manifest_id": "PROV-K06-1",
        "reproducibility_contract": {
            "container_digest_required": True,
            "environment_capture": True,
            "seed_control": True,
        },
        "safety_class": "bounded_compute",
        "sandbox_profile": "bounded_compute",
        "state_variables": [],
        "supply_chain_attestation_artifact_id": "ATT-K06-1",
        "supported_actions": ["simulate"],
        "target_id": TARGET_ID,
        "target_type": "simulation_model",
        "validation_scope": scope,
        "version": "1.0.0",
    }
    payload.update(overrides)
    return payload


def execution_arguments(
    version: dict[str, Any], guard: VerifierFirewall, **overrides: Any
) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "version": version,
        "firewall": guard,
        "candidate_kind": CANDIDATE_KIND,
        "target_manifest": target_manifest(),
        "hard_limits": dict(HARD_LIMITS),
        "effect_receipt_channel_id": EFFECT_RECEIPT_CHANNEL_ID,
        "qualification_id": "EXQ-K06-1",
    }
    arguments.update(overrides)
    return arguments


def feedback_arguments(
    version: dict[str, Any],
    guard: VerifierFirewall,
    *,
    feedback_artifact_ids: list[str] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "version": version,
        "firewall": guard,
        "run_or_bundle_id": RUN_OR_BUNDLE_ID,
        "feedback_artifact_ids": feedback_artifact_ids
        if feedback_artifact_ids is not None
        else ["FB-K06-1", "FB-K06-2"],
        "surfaces_checked": list(LEAKAGE_SURFACES),
        "access_log_artifact_id": ACCESS_LOG_ARTIFACT_ID,
    }
    arguments.update(overrides)
    return arguments
