"""Compute the deterministic C01-0008 RetrievalCandidate fixture hashes.

This helper prints a complete canonical fixture. It is retained as attempt
evidence so the identity and content hashes can be independently reproduced.
"""

from __future__ import annotations

import hashlib
import json


IDENTITY_FIELDS = [
    "plan_hash",
    "lane",
    "query_hash",
    "canonical_source_key",
    "source_version",
    "source_snapshot_hash",
]

CONTENT_FIELDS = [
    "run_id",
    "query_plan_id",
    "plan_hash",
    "lane",
    "query_family",
    "query_text",
    "query_hash",
    "scope_filter",
    "corpus_snapshot_hash",
    "index_versions",
    "backend_id",
    "backend_version",
    "backend_adapter_id",
    "backend_adapter_version",
    "backend_request_hash",
    "backend_response_hash",
    "backend_receipt_id",
    "canonical_source_key",
    "source_record_id",
    "source_artifact_id",
    "source_locator",
    "source_version",
    "source_snapshot_hash",
    "source_span_id",
    "raw_rank",
    "raw_scores",
    "channel_ranks",
    "retrieval_channels",
    "fusion_method",
    "fusion_score",
    "ranking_features",
    "matched_terms",
    "matched_edges",
    "relation_direction",
    "scope_estimate",
    "duplicate_candidate_ids",
    "multi_channel_verified",
    "retrieval_explanation",
]


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


query_batch = {
    "families": [
        {
            "family": "FORWARD",
            "queries": ["spaced retrieval practice delayed recall"],
        },
        {
            "family": "REVERSE",
            "queries": ["spaced retrieval practice impairs delayed recall"],
        },
    ],
    "lane": "counterevidence",
}
query_text = canonical_bytes(query_batch).decode("utf-8")

scope = {
    "comparator": "rereading with matched total study time",
    "conditions": {
        "feedback_available": True,
        "matched_total_study_time": True,
        "retention_interval_days": 14,
    },
    "domain": "learning_science",
    "domain_extensions": {
        "material_type": "expository text",
        "outcome_instrument": "preregistered delayed-recall test",
    },
    "entity_subtype": "university student",
    "entity_type": "participant",
    "exclusion_criteria": ["missing delayed outcome"],
    "geography": None,
    "inclusion_criteria": [
        "completed baseline assessment",
        "completed all assigned sessions",
    ],
    "intervention_or_exposure": {
        "category": "learning intervention",
        "duration": "one week",
        "frequency": "three sessions",
        "max_value": 3,
        "min_value": 3,
        "name": "spaced retrieval practice",
        "rate": None,
        "route_or_delivery": "computer-based practice",
        "unit": "sessions",
    },
    "jurisdiction": None,
    "language": "English",
    "lifecycle_stage": None,
    "measurement_time": "14 days after the final study session",
    "population": "adult learners enrolled in introductory university courses",
    "setting": "controlled course-based study",
    "spatial_scale": "individual",
    "temporal_scale": "14-day delayed outcome",
    "time_period": None,
    "unit_of_analysis": "individual learner",
}

fixture: dict[str, object] = {
    "candidate_id": "",
    "run_id": "RUN-O02-0002",
    "query_plan_id": "QPLAN-O01-E2-0001",
    "plan_hash": "sha256:2bc841e81f5fed0d6108c7a0242547bc96b97bde5593b3c1e4117737d7945406",
    "lane": "counterevidence",
    "query_family": "REVERSE",
    "query_text": query_text,
    "query_hash": "sha256:" + hashlib.sha256(query_text.encode("utf-8")).hexdigest(),
    "scope_filter": scope,
    "corpus_snapshot_hash": "sha256:08e722d513d060c23b41c0ffa93ea63972c4a827458dcf952ca5c7119a54a25b",
    "index_versions": {
        "citation_graph": "fixture-2026-07-31",
        "lexical": "fixture-2026-07-31",
    },
    "backend_id": "fixture-hybrid-retrieval",
    "backend_version": "1.0.0",
    "backend_adapter_id": "epistemic-foundry-fixture-adapter",
    "backend_adapter_version": "1.0.0",
    "backend_request_hash": sha256({"kind": "fixture-backend-request", "query": query_batch}),
    "backend_response_hash": sha256({"kind": "fixture-backend-response", "record": "SRC-O02-0001"}),
    "backend_receipt_id": "BREC-O02-0001",
    "canonical_source_key": "doi:10.5555/ef.fixture.0001",
    "source_record_id": "SRC-O02-0001",
    "source_artifact_id": "ART-SOURCE-O02-0001",
    "source_locator": "doi:10.5555/ef.fixture.0001",
    "source_version": "version:1",
    "source_snapshot_hash": sha256({"source": "doi:10.5555/ef.fixture.0001", "version": "1"}),
    "source_span_id": None,
    "raw_rank": 1,
    "raw_scores": {
        "LEXICAL": 0.92,
        "SEMANTIC": None,
        "CITATION_GRAPH": 0.81,
        "RELATION_GRAPH": None,
        "EXTERNAL_INDEX": None,
    },
    "channel_ranks": {
        "LEXICAL": 1,
        "SEMANTIC": None,
        "CITATION_GRAPH": 2,
        "RELATION_GRAPH": None,
        "EXTERNAL_INDEX": None,
    },
    "retrieval_channels": ["LEXICAL", "CITATION_GRAPH"],
    "fusion_method": "RRF_K60",
    "fusion_score": 1 / 61 + 1 / 62,
    "ranking_features": {
        "scope_overlap": 0.9,
        "relation_direction_match": 0.0,
        "source_directness": 0.6,
        "method_compatibility": 0.8,
        "publication_version_status": 1.0,
        "extraction_grounding_confidence": 0.7,
    },
    "matched_terms": ["delayed recall", "spaced retrieval practice"],
    "matched_edges": ["citation:fixture-seed->SRC-O02-0001"],
    "relation_direction": "REVERSE_DIRECTION",
    "scope_estimate": scope,
    "duplicate_candidate_ids": [],
    "multi_channel_verified": True,
    "retrieval_explanation": "The same versioned source was independently retrieved by lexical and citation-graph channels and preserves reverse-direction provenance.",
    "candidate_hash": "",
}

identity_hash = sha256({field: fixture[field] for field in IDENTITY_FIELDS})
fixture["candidate_id"] = "RC-" + identity_hash.removeprefix("sha256:")
fixture["candidate_hash"] = sha256({field: fixture[field] for field in CONTENT_FIELDS})
print(json.dumps(fixture, ensure_ascii=False, indent=2))
