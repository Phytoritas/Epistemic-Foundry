from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from ..planning.contracts import (
    PlanningContractError,
    reconcile_search_run,
    seal_search_lane_receipt,
)
from ..planning.test_query_plan import HASH_A, HASH_B
from ..planning.test_receipt_completeness import (
    complete_receipts,
    plan_for,
    receipt_proposal,
)
from .contracts import (
    EvidencePackContractError,
    assemble_evidence_pack,
    validate_evidence_pack,
)
from .test_dependency_cluster import CREATED_AT, unit

ROOT = Path(__file__).resolve().parents[4]

SWR_LANES = ("lexical", "semantic", "counterevidence", "null", "boundary", "method")


def pack_schema_validator() -> Draft202012Validator:
    schema = json.loads(
        (ROOT / "schemas" / "evidence-pack.schema.json").read_text(encoding="utf-8")
    )
    return Draft202012Validator(schema)


def sealed_run(overrides: dict[str, str] | None = None, *, extra_lexical: bool = True):
    plan = plan_for("E2")
    lane_overrides = {lane: "SEARCHED_WITH_RESULTS" for lane in SWR_LANES}
    lane_overrides.update(overrides or {})
    receipts = complete_receipts(plan, lane_overrides)
    if extra_lexical:
        receipts.append(
            seal_search_lane_receipt(
                receipt_proposal(plan, "lexical", "SEARCHED_WITH_RESULTS", suffix="2")
            )
        )
    certificate = reconcile_search_run(
        plan,
        receipts,
        certificate_id="SCC-1",
        run_id="RUN-1",
        subject_ref="INS-1",
        generated_at="2026-07-31T00:02:00Z",
    )
    return plan, receipts, certificate


def default_units() -> list[dict[str, object]]:
    return [
        unit(
            "EVN-0001",
            peer_review_status="PREPRINT",
            publication_family_id="FAM-1",
            dataset_ids=["D1"],
            origin_result_ids=["EV-lexical-1"],
        ),
        unit(
            "EVN-0002",
            publication_family_id="FAM-1",
            dataset_ids=["D1"],
            origin_result_ids=["EV-lexical-2"],
        ),
        unit("EVN-0003", dataset_ids=["D2"], origin_result_ids=["EV-semantic-1"]),
        unit("EVN-0101", origin_result_ids=["EV-counterevidence-1"]),
        unit("EVN-0201", origin_result_ids=["EV-null-1"]),
        unit("EVN-0301", origin_result_ids=["EV-boundary-1"]),
        unit("EVN-0401", origin_result_ids=["EV-method-1"]),
    ]


def default_assignments() -> dict[str, list[str]]:
    return {
        "supporting": ["EVN-0001", "EVN-0002", "EVN-0003"],
        "counter": ["EVN-0101"],
        "null": ["EVN-0201"],
        "boundary": ["EVN-0301"],
        "method": ["EVN-0401"],
        "alternative": [],
    }


def pack_inputs(**overrides: object) -> dict[str, object]:
    plan, receipts, certificate = overrides.pop("run", None) or sealed_run()
    value: dict[str, object] = {
        "insight_id": "INS-1",
        "corpus_snapshot_hash": HASH_A,
        "retrieval_manifest_id": "RM-1",
        "bias_risk_register_id": "BRR-1",
        "lane_assignments": default_assignments(),
        "query_plan": plan,
        "receipts": receipts,
        "certificate": certificate,
        "created_at": CREATED_AT,
    }
    value.update(overrides)
    return value


def test_pack_diversity_test_assembly_keeps_counter_null_boundary_visible() -> None:
    inputs = pack_inputs()
    pack, clusters = assemble_evidence_pack(default_units(), **inputs)
    payload = pack.payload

    assert payload["supporting_ids"] == ["EVN-0001", "EVN-0002", "EVN-0003"]
    assert payload["counter_ids"] == ["EVN-0101"]
    assert payload["null_ids"] == ["EVN-0201"]
    assert payload["boundary_ids"] == ["EVN-0301"]
    assert payload["method_ids"] == ["EVN-0401"]
    assert payload["alternative_ids"] == []
    assert payload["dependency_clusters"] == [["EVN-0001", "EVN-0002"]]
    assert payload["effective_independent_count"] == 6.0
    assert payload["retrieval_run_id"] == "RUN-1"
    assert len(clusters) == 1

    certificate_payload = inputs["certificate"].payload
    assert payload["search_lane_receipt_ids"] == certificate_payload["lane_receipt_ids"]
    assert payload["unsearched_scopes"] == certificate_payload["unsearched_scope"]
    assert payload["unsearched_scopes"] != []
    assert (
        payload["completeness_certificate_hash"]
        == certificate_payload["certificate_hash"]
    )

    assert payload["completeness"] == {
        "support_lane_complete": True,
        "counter_lane_complete": True,
        "null_lane_complete": True,
        "boundary_lane_complete": True,
        "method_lane_complete": True,
        "novelty_lane_complete": False,
    }
    assert payload["role_quota_report"]["supporting"] == {
        "required": 0,
        "found": 3,
        "independent_units": 2.0,
    }
    assert payload["role_quota_report"]["counter"] == {
        "required": 0,
        "found": 1,
        "independent_units": 1.0,
    }


def test_pack_diversity_test_output_and_canonical_example_are_schema_valid() -> None:
    validator = pack_schema_validator()
    pack, _clusters = assemble_evidence_pack(default_units(), **pack_inputs())
    validator.validate(pack.payload)

    example = json.loads(
        (ROOT / "examples" / "sample_evidence_pack.json").read_text(encoding="utf-8")
    )
    validator.validate(example)


def test_pack_diversity_test_silent_counterevidence_drop_fails_closed() -> None:
    units = [entry for entry in default_units() if entry["evidence_id"] != "EVN-0101"]
    assignments = default_assignments()
    assignments["counter"] = []

    with pytest.raises(EvidencePackContractError) as raised:
        assemble_evidence_pack(units, **pack_inputs(lane_assignments=assignments))
    assert raised.value.code == "RESULT_SILENTLY_DROPPED"
    assert "EV-counterevidence-1" in raised.value.details["result_ids"]


def test_pack_diversity_test_typed_unresolved_counter_result_is_visible_not_silent() -> (
    None
):
    units = [entry for entry in default_units() if entry["evidence_id"] != "EVN-0101"]
    assignments = default_assignments()
    assignments["counter"] = []

    pack, _clusters = assemble_evidence_pack(
        units,
        **pack_inputs(
            lane_assignments=assignments,
            unresolved_results=[
                {"result_id": "EV-counterevidence-1", "reason": "GROUNDING_FAILED"}
            ],
        ),
    )

    payload = pack.payload
    assert payload["counter_ids"] == []
    assert payload["completeness"]["counter_lane_complete"] is True
    assert payload["effective_independent_count"] == 5.0


def test_pack_diversity_test_searched_none_counter_lane_is_honestly_empty() -> None:
    run = sealed_run({"counterevidence": "SEARCHED_NONE"})
    units = [entry for entry in default_units() if entry["evidence_id"] != "EVN-0101"]
    assignments = default_assignments()
    assignments["counter"] = []

    pack, _clusters = assemble_evidence_pack(
        units, **pack_inputs(run=run, lane_assignments=assignments)
    )

    payload = pack.payload
    assert payload["counter_ids"] == []
    assert payload["completeness"]["counter_lane_complete"] is True


def test_pack_diversity_test_blocked_counter_lane_is_incomplete_not_complete() -> None:
    run = sealed_run({"counterevidence": "BLOCKED"})
    units = [entry for entry in default_units() if entry["evidence_id"] != "EVN-0101"]
    assignments = default_assignments()
    assignments["counter"] = []

    pack, _clusters = assemble_evidence_pack(
        units, **pack_inputs(run=run, lane_assignments=assignments)
    )

    assert pack.payload["completeness"]["counter_lane_complete"] is False


def test_pack_diversity_test_metadata_only_evidence_is_rejected() -> None:
    units = default_units()
    units[3] = unit(
        "EVN-0101",
        source_span_id=None,
        origin_result_ids=["EV-counterevidence-1"],
    )

    with pytest.raises(EvidencePackContractError) as raised:
        assemble_evidence_pack(units, **pack_inputs())
    assert raised.value.code == "METADATA_ONLY_EVIDENCE"


def test_pack_diversity_test_invented_evidence_fails_closed() -> None:
    units = default_units()
    units[6] = unit("EVN-0401", origin_result_ids=["EV-fabricated-9"])

    with pytest.raises(EvidencePackContractError) as raised:
        assemble_evidence_pack(units, **pack_inputs())
    assert raised.value.code == "EVIDENCE_NOT_RETRIEVED"


def test_pack_diversity_test_snapshot_mismatch_fails_closed() -> None:
    with pytest.raises(EvidencePackContractError) as raised:
        assemble_evidence_pack(
            default_units(), **pack_inputs(corpus_snapshot_hash=HASH_B)
        )
    assert raised.value.code == "STALE_RETRIEVAL_SNAPSHOT"


def test_pack_diversity_test_insight_binding_is_exact() -> None:
    with pytest.raises(EvidencePackContractError) as raised:
        assemble_evidence_pack(default_units(), **pack_inputs(insight_id="INS-2"))
    assert raised.value.code == "PACK_SUBJECT_MISMATCH"


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (lambda roles: roles["counter"].append("EVN-0001"), "ROLE_ASSIGNMENT_CONFLICT"),
        (lambda roles: roles["supporting"].remove("EVN-0003"), "EVIDENCE_UNACCOUNTED"),
        (lambda roles: roles["method"].append("EVN-9999"), "EVIDENCE_UNKNOWN"),
        (lambda roles: roles.pop("null"), "ROLE_SET_INVALID"),
    ],
)
def test_pack_diversity_test_role_assignment_failures(mutate, code: str) -> None:
    assignments = default_assignments()
    mutate(assignments)

    with pytest.raises(EvidencePackContractError) as raised:
        assemble_evidence_pack(
            default_units(), **pack_inputs(lane_assignments=assignments)
        )
    assert raised.value.code == code


def test_pack_diversity_test_alternatives_do_not_count_as_evidence() -> None:
    assignments = default_assignments()
    assignments["method"] = []
    assignments["alternative"] = ["EVN-0401"]

    pack, _clusters = assemble_evidence_pack(
        default_units(), **pack_inputs(lane_assignments=assignments)
    )

    payload = pack.payload
    assert payload["method_ids"] == []
    assert payload["alternative_ids"] == ["EVN-0401"]
    assert payload["effective_independent_count"] == 5.0
    assert payload["role_quota_report"]["alternative"]["independent_units"] == 1.0


def test_pack_diversity_test_role_quotas_are_targets_not_invention() -> None:
    pack, _clusters = assemble_evidence_pack(
        default_units(), **pack_inputs(role_quotas={"counter": 2})
    )

    assert pack.payload["role_quota_report"]["counter"] == {
        "required": 2,
        "found": 1,
        "independent_units": 1.0,
    }

    with pytest.raises(EvidencePackContractError) as raised:
        assemble_evidence_pack(
            default_units(), **pack_inputs(role_quotas={"verdict": 1})
        )
    assert raised.value.code == "ROLE_SET_INVALID"

    with pytest.raises(EvidencePackContractError) as raised:
        assemble_evidence_pack(
            default_units(), **pack_inputs(role_quotas={"counter": -1})
        )
    assert raised.value.code == "INPUT_INVALID"


@pytest.mark.parametrize(
    ("entry", "code"),
    [
        (
            {"result_id": "EV-lexical-1", "reason": "OUT_OF_SCOPE"},
            "UNRESOLVED_CONTRADICTION",
        ),
        (
            {"result_id": "EV-ghost-1", "reason": "OUT_OF_SCOPE"},
            "UNRESOLVED_UNKNOWN_RESULT",
        ),
        (
            {"result_id": "EV-lexical-1", "reason": "NOT_A_REASON"},
            "UNRESOLVED_REASON_INVALID",
        ),
    ],
)
def test_pack_diversity_test_unresolved_entries_are_typed_and_consistent(
    entry: dict[str, str], code: str
) -> None:
    with pytest.raises(EvidencePackContractError) as raised:
        assemble_evidence_pack(
            default_units(), **pack_inputs(unresolved_results=[entry])
        )
    assert raised.value.code == code


def test_pack_diversity_test_validate_roundtrip_and_tamper_fail_closed() -> None:
    inputs = pack_inputs()
    pack, clusters = assemble_evidence_pack(default_units(), **inputs)
    verify_kwargs = {
        "units": default_units(),
        "lane_assignments": default_assignments(),
        "query_plan": inputs["query_plan"],
        "receipts": inputs["receipts"],
        "certificate": inputs["certificate"],
        "created_at": CREATED_AT,
    }

    rebuilt_pack, rebuilt_clusters = validate_evidence_pack(
        pack.payload, [entry.payload for entry in clusters], **verify_kwargs
    )
    assert rebuilt_pack.canonical_bytes == pack.canonical_bytes
    assert [entry.canonical_bytes for entry in rebuilt_clusters] == [
        entry.canonical_bytes for entry in clusters
    ]

    tampered = pack.payload
    tampered["effective_independent_count"] = 11.0
    with pytest.raises(EvidencePackContractError) as raised:
        validate_evidence_pack(
            tampered, [entry.payload for entry in clusters], **verify_kwargs
        )
    assert raised.value.code == "PACK_RECONSTRUCTION_MISMATCH"


def test_pack_diversity_test_certificate_tamper_fails_before_assembly() -> None:
    inputs = pack_inputs()
    broken = inputs["certificate"].payload
    broken["completion_state"] = "NOT_REQUIRED"

    with pytest.raises(PlanningContractError):
        assemble_evidence_pack(default_units(), **{**inputs, "certificate": broken})


def test_pack_diversity_test_assembly_is_deterministic() -> None:
    inputs = pack_inputs()
    first, first_clusters = assemble_evidence_pack(default_units(), **inputs)
    second, second_clusters = assemble_evidence_pack(default_units(), **inputs)

    assert first.canonical_bytes == second.canonical_bytes
    assert [entry.canonical_bytes for entry in first_clusters] == [
        entry.canonical_bytes for entry in second_clusters
    ]
