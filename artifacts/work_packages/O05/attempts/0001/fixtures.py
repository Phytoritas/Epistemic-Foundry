"""Fixtures for the O05 retrieval, novelty and acquisition suites.

Every fixture is produced through a sealed builder rather than hand-written:
the corpus snapshot and the prior-art boundary come from K05, the niches from
the M05 mapper, and the lane dispositions and novelty layers are derived from
the canonical vocabularies this package reads rather than restated here.  A
hand-written shape would only ever test itself.

The corpus deliberately holds one document dated after the prior-art as-of
bound, because "pinned but outside the searched window" is the case the plan
has to distinguish from "not pinned at all"; and one niche deliberately carries
a higher coverage debt than the others, because a ranking over equal debts
would not show whether the ordering is real.
"""

from __future__ import annotations

from typing import Any

from epistemic_foundry.evidence.v4_k05 import (
    declare_prior_art_boundary,
    pin_corpus_snapshot,
)
from epistemic_foundry.cartography.v4_m05 import axis_vocabulary, build_niche
from epistemic_foundry.retrieval.v4_o05 import (
    SELECTED_DISPOSITION_POSITION,
    adversarial_lanes,
    build_evolution_retrieval_plan,
    canonical_lane_order,
    emit_searched_lane_receipt,
    emit_unsearched_lane_receipt,
    novelty_layer_vocabulary,
    plan_disposition_vocabulary,
    statement_digest,
)

CORPUS_ID = "CORPUS-O05"
PINNED_AT = "2026-08-02T00:00:00Z"
STARTED_AT = "2026-08-02T01:00:00Z"
FINISHED_AT = "2026-08-02T01:05:00Z"
ASSESSED_AT = "2026-08-02T02:00:00Z"
AS_OF_DATE = "2026-01-01"

RUN_ID = "ER-O05-1"
QUERY_PLAN_ID = "QP-O05-1"
CERTIFICATE_ID = "SCC-O05-1"
CANDIDATE_ID = "EC-O05-1"
SUBJECT_REF = "HY-O05-1"
ASSESSOR_REF = "novelty-examiner-1"
EVOLUTION_RUN_ID = "EVO-O05-1"
GENERATION = 3
STATEMENT_HASH = statement_digest("the mechanism the candidate proposes")

SEARCHED_SOURCES = ("pinned-local-corpus",)
UNSEARCHED_SOURCES = ("patent-registers", "paywalled-journals")

MECHANISM_ID = "DOC-MECHANISM"
COUNTER_ID = "DOC-COUNTER"
NULL_ID = "DOC-NULL"
BOUNDARY_ID = "DOC-BOUNDARY"
LATE_ID = "DOC-LATE"

EVIDENCE_DECISION_IDS = ("LDE-O05-1",)
INDEX_VERSIONS = {"pinned-local-corpus": "1.4.0"}
QUERY_TEXT = "mechanism and its counter-evidence within the pinned corpus"


def document(
    document_id: str,
    *,
    fill: str,
    license_status: str,
    source_date: str,
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
            MECHANISM_ID,
            fill="1",
            license_status="open_access",
            source_date="2024-01-02",
        ),
        document(
            COUNTER_ID, fill="2", license_status="licensed", source_date="2024-05-06"
        ),
        document(
            NULL_ID, fill="3", license_status="open_access", source_date="2025-02-03"
        ),
        document(
            BOUNDARY_ID,
            fill="4",
            license_status="fair_use_metadata_only",
            source_date="2025-07-08",
        ),
        # Pinned by the snapshot, outside the prior-art as-of bound.
        document(
            LATE_ID, fill="5", license_status="open_access", source_date="2026-09-09"
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


def boundary(pinned: dict[str, Any] | None = None, **overrides: Any) -> dict[str, Any]:
    keywords: dict[str, Any] = {
        "snapshot": pinned if pinned is not None else snapshot(),
        "as_of_date": AS_OF_DATE,
        "searched_sources": list(SEARCHED_SOURCES),
        "unsearched_sources": list(UNSEARCHED_SOURCES),
    }
    keywords.update(overrides)
    return declare_prior_art_boundary(**keywords)


def selecting_disposition() -> str:
    return plan_disposition_vocabulary()[SELECTED_DISPOSITION_POSITION]


def sentinel_disposition() -> str:
    """The first disposition that does *not* select a lane."""
    declared = plan_disposition_vocabulary()
    return declared[SELECTED_DISPOSITION_POSITION + 1]


def lane_dispositions(**overrides: str) -> dict[str, str]:
    """Select every adversarial lane; sentinel the rest."""
    selected = set(adversarial_lanes())
    dispositions = {
        lane: selecting_disposition() if lane in selected else sentinel_disposition()
        for lane in canonical_lane_order()
    }
    dispositions.update(overrides)
    return dispositions


def scope_filter() -> dict[str, Any]:
    """A canonical ScopeVector with every declared field explicitly absent.

    Nulls rather than omissions: the schema requires every key, and an omitted
    boundary condition would read as "unconstrained" when it means "unstated".
    """
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


def axis_values(**overrides: str) -> dict[str, str]:
    values = {axis: f"{axis}-a" for axis in axis_vocabulary()}
    values.update(overrides)
    return values


def niches(**overrides: Any) -> list[dict[str, Any]]:
    """Three cells with distinct coordinates and deliberately unequal debt."""
    axes = axis_vocabulary()
    first, second = axes[0], axes[1]
    built = [
        build_niche(
            axis_values=axis_values(**{first: "mechanism-a"}),
            capacity=4,
            occupant_ids=["EC-O05-1", "EC-O05-2"],
            elite_id="EC-O05-1",
            coverage_debt=0.25,
        ),
        build_niche(
            axis_values=axis_values(**{first: "mechanism-b"}),
            capacity=4,
            occupant_ids=[],
            elite_id=None,
            coverage_debt=0.9,
        ),
        build_niche(
            axis_values=axis_values(**{second: "scope-b"}),
            capacity=2,
            occupant_ids=["EC-O05-3"],
            elite_id="EC-O05-3",
            coverage_debt=0.5,
        ),
    ]
    if overrides:
        built = [dict(niche, **overrides) for niche in built]
    return built


def layer_scores(**overrides: float) -> dict[str, float]:
    """A score for exactly the layers the canonical vector schema declares."""
    declared = novelty_layer_vocabulary()
    scores = {layer: 0.4 for layer in declared}
    scores[declared[-1]] = 0.0
    scores.update(overrides)
    return scores


def layered_arguments(
    declared: dict[str, Any] | None = None,
    pinned: dict[str, Any] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    pinned = pinned if pinned is not None else snapshot()
    declared = declared if declared is not None else plan(pinned)
    arguments: dict[str, Any] = {
        "boundary": boundary(pinned),
        "plan": declared,
        "candidate_id": CANDIDATE_ID,
        "subject_ref": SUBJECT_REF,
        "statement_hash": STATEMENT_HASH,
        "search_completeness_certificate_id": CERTIFICATE_ID,
        "layer_scores": layer_scores(),
        "novelty_dimensions": ["MECHANISM"],
        "nearest_candidate_ids": ["EC-O05-2"],
        "closest_prior_art_refs": [],
        "distinguishing_features": ["a mechanism the pinned corpus does not state"],
        "assessor_ref": ASSESSOR_REF,
        "assessed_at": ASSESSED_AT,
    }
    arguments.update(overrides)
    return arguments


def acquisition_arguments(
    declared: dict[str, Any] | None = None,
    pinned: dict[str, Any] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    pinned = pinned if pinned is not None else snapshot()
    declared = declared if declared is not None else plan(pinned)
    arguments: dict[str, Any] = {
        "plan": declared,
        "receipts": receipts(declared, pinned),
        "niches": niches(),
        "target_budget": 2,
        "evolution_run_id": EVOLUTION_RUN_ID,
        "generation": GENERATION,
    }
    arguments.update(overrides)
    return arguments
