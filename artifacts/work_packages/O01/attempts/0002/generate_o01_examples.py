#!/usr/bin/env python3
"""Generate deterministic O01 canonical example payloads for review.

By default the script prints the QueryPlan, one representative
SearchLaneReceipt, the all-eleven receipt set, and the resulting
SearchCompletenessCertificate.  ``--write`` updates only the three authorized
canonical O01 examples after the same generated objects have passed runtime
and JSON Schema validation in the O01 verification workflow.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "python"))

from epistemic_foundry.retrieval.planning import (  # noqa: E402
    CANONICAL_LANES,
    compile_query_plan,
    reconcile_search_run,
    seal_search_lane_receipt,
)


SCOPE = {
    "domain": "learning_science",
    "population": "adult learners enrolled in introductory university courses",
    "entity_type": "participant",
    "entity_subtype": "university student",
    "unit_of_analysis": "individual learner",
    "setting": "controlled course-based study",
    "geography": None,
    "jurisdiction": None,
    "language": "English",
    "lifecycle_stage": None,
    "spatial_scale": "individual",
    "temporal_scale": "14-day delayed outcome",
    "time_period": None,
    "measurement_time": "14 days after the final study session",
    "intervention_or_exposure": {
        "name": "spaced retrieval practice",
        "category": "learning intervention",
        "min_value": 3,
        "max_value": 3,
        "unit": "sessions",
        "duration": "one week",
        "frequency": "three sessions",
        "rate": None,
        "route_or_delivery": "computer-based practice",
    },
    "comparator": "rereading with matched total study time",
    "inclusion_criteria": [
        "completed baseline assessment",
        "completed all assigned sessions",
    ],
    "exclusion_criteria": ["missing delayed outcome"],
    "conditions": {
        "matched_total_study_time": True,
        "feedback_available": True,
        "retention_interval_days": 14,
    },
    "domain_extensions": {
        "material_type": "expository text",
        "outcome_instrument": "preregistered delayed-recall test",
    },
}


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_file(relative_path: str) -> str:
    return sha256_bytes((ROOT / relative_path).read_bytes())


def canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256_bytes(encoded)


def build_plan():
    immutable_request = {
        "request_id": "REQ-O01-E2-0001",
        "request_revision": 1,
        "text": "Synthesize evidence on spaced retrieval practice and delayed recall.",
    }
    proposal = {
        "query_plan_id": "QPLAN-O01-E2-0001",
        "request_id": immutable_request["request_id"],
        "request_revision": immutable_request["request_revision"],
        "request_input_hash": canonical_hash(immutable_request),
        "classification_id": "EWC-O01-E2-0001",
        "classification_revision": 1,
        "classification_hash": canonical_hash(
            {
                "classification_id": "EWC-O01-E2-0001",
                "request_id": immutable_request["request_id"],
                "work_class": "E2",
                "classifier_version": "4.0.1-f01.1",
            }
        ),
        "work_class": "E2",
        "classifier_version": "4.0.1-f01.1",
        "policy_bundle_hash": sha256_file("config/retrieval_policy.example.yaml"),
        "insight_id": "INS-O01-0001",
        "insight_revision": 1,
        "canonical_relation": "spaced retrieval practice improves delayed recall",
        "forward_queries": ["spaced retrieval practice delayed recall"],
        "reverse_queries": ["spaced retrieval practice impairs delayed recall"],
        "null_queries": ["spaced retrieval practice no effect delayed recall"],
        "boundary_queries": ["spaced retrieval practice moderator delayed recall"],
        "method_queries": ["delayed recall measurement reliability spaced practice"],
        "novelty_queries": [],
        "scope_partitions": [deepcopy(SCOPE)],
        "budget": {"max_queries": 40, "max_documents": 80, "max_seconds": 900},
        "stop_rules": [
            "all selected lanes terminal",
            "two consecutive saturation rounds",
        ],
        "planner_prompt_hash": sha256_file(
            "python/epistemic_foundry/retrieval/planning/contracts.py"
        ),
        "created_at": "2026-07-31T00:00:00Z",
    }
    return compile_query_plan(proposal)


def receipt_proposal(plan, lane: str, state: str) -> dict[str, object]:
    payload = plan.payload
    decision = next(row for row in payload["lane_decisions"] if row["lane"] == lane)
    sentinel = state == "UNSEARCHED"
    searched = state in {"SEARCHED_NONE", "SEARCHED_WITH_RESULTS", "PARTIAL"}
    results = [f"EV-O01-{lane.upper()}-0001"] if state == "SEARCHED_WITH_RESULTS" else []
    stops = {
        "SEARCHED_NONE": "exhausted_query_plan",
        "SEARCHED_WITH_RESULTS": "saturation_reached",
        "PARTIAL": "budget_exhausted",
        "BLOCKED": "backend_unavailable",
        "FAILED": "provider_failure",
    }
    return {
        "receipt_id": f"SLR-O01-{lane.upper()}-0001",
        "run_id": "RUN-O01-0001",
        "query_plan_id": payload["query_plan_id"],
        "plan_hash": payload["plan_hash"],
        "lane": lane,
        "receipt_kind": "SENTINEL" if sentinel else "EXECUTION",
        "sentinel_reason": decision["disposition"] if sentinel else None,
        "lane_decision_evidence_ids": list(decision["evidence_ids"]),
        "query_text": None if sentinel else f"spaced retrieval practice {lane}",
        "scope_filter": None if sentinel else deepcopy(SCOPE),
        "corpus_snapshot_hash": (
            sha256_file("examples/sample_document-manifest.json") if searched else None
        ),
        "index_versions": {"fixture-index": "o01-2026-07-31"} if searched else None,
        "result_ids": results if searched else None,
        "result_count": len(results) if searched else None,
        "excluded_count": 0 if searched else None,
        "stop_reason": None if sentinel else stops[state],
        "search_state": state,
        "recall_proxy": 0.8 if searched else None,
        "errors": [] if sentinel or state in {"SEARCHED_NONE", "SEARCHED_WITH_RESULTS"} else [
            f"fixture {state.lower()} reason"
        ],
        "started_at": None if sentinel or state in {"BLOCKED", "FAILED"} else "2026-07-31T00:00:00Z",
        "finished_at": None if sentinel or state in {"BLOCKED", "FAILED"} else "2026-07-31T00:01:00Z",
    }


def build_output() -> dict[str, object]:
    plan = build_plan()
    selected = set(plan.payload["required_lanes"])
    receipts = []
    for lane in CANONICAL_LANES:
        if lane not in selected:
            state = "UNSEARCHED"
        elif lane == "lexical":
            state = "SEARCHED_WITH_RESULTS"
        else:
            state = "SEARCHED_NONE"
        receipts.append(seal_search_lane_receipt(receipt_proposal(plan, lane, state)))
    certificate = reconcile_search_run(
        plan,
        receipts,
        certificate_id="SCC-O01-0001",
        run_id="RUN-O01-0001",
        subject_ref="INS-O01-0001",
        generated_at="2026-07-31T00:02:00Z",
    )
    return {
        "query_plan": plan.payload,
        "representative_receipt": next(
            receipt.payload for receipt in receipts if receipt.payload["lane"] == "counterevidence"
        ),
        "all_receipts": [receipt.payload for receipt in receipts],
        "certificate": certificate.payload,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write",
        action="store_true",
        help="write the three validated canonical O01 examples instead of printing the bundle",
    )
    args = parser.parse_args()
    output = build_output()
    if args.write:
        targets = {
            "query_plan": ROOT / "examples/sample_query-plan.json",
            "representative_receipt": ROOT / "examples/sample_search-lane-receipt.json",
            "certificate": ROOT / "examples/sample_search-completeness-certificate.json",
        }
        for key, path in targets.items():
            path.write_text(
                json.dumps(output[key], ensure_ascii=False, indent=2, sort_keys=False) + "\n",
                encoding="utf-8",
                newline="\n",
            )
        print("wrote " + ", ".join(path.relative_to(ROOT).as_posix() for path in targets.values()))
        return 0
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
