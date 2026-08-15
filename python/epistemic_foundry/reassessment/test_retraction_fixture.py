"""retraction_fixture_test — a correction or retraction actually propagates."""

from __future__ import annotations

import pytest

from .contracts import (
    ReassessmentError,
    apply_passport_states,
    assess_update,
    validate_plan,
)

CREATED_AT = "2026-08-01T00:00:00Z"
RUN_ID = "RUN-W03-1"


def graph() -> list[dict[str, object]]:
    """Canonical seven-class dependency chain plus one unrelated branch."""

    return [
        {"artifact_class": "document", "artifact_id": "DOC-1", "depends_on": []},
        {"artifact_class": "document", "artifact_id": "DOC-2", "depends_on": []},
        {"artifact_class": "span", "artifact_id": "SPAN-1", "depends_on": ["DOC-1"]},
        {"artifact_class": "span", "artifact_id": "SPAN-2", "depends_on": ["DOC-2"]},
        {"artifact_class": "claim", "artifact_id": "CLM-1", "depends_on": ["SPAN-1"]},
        {"artifact_class": "claim", "artifact_id": "CLM-2", "depends_on": ["SPAN-2"]},
        {"artifact_class": "evidence", "artifact_id": "EV-1", "depends_on": ["CLM-1"]},
        {"artifact_class": "evidence", "artifact_id": "EV-2", "depends_on": ["CLM-2"]},
        {"artifact_class": "pack", "artifact_id": "PACK-1", "depends_on": ["EV-1"]},
        {"artifact_class": "pack", "artifact_id": "PACK-2", "depends_on": ["EV-2"]},
        {"artifact_class": "decision", "artifact_id": "DEC-1", "depends_on": ["PACK-1"]},
        {"artifact_class": "decision", "artifact_id": "DEC-2", "depends_on": ["PACK-2"]},
        {"artifact_class": "passport", "artifact_id": "HP-1", "depends_on": ["DEC-1"]},
        {"artifact_class": "passport", "artifact_id": "HP-2", "depends_on": ["DEC-2"]},
    ]


def assess(**overrides):
    values = {
        "created_at": CREATED_AT,
        "graph": graph(),
        "run_id": RUN_ID,
        "trigger_artifact_ids": ["DOC-1"],
        "trigger_event_id": "EVT-W03-1",
        "trigger_type": "document_retraction",
    }
    values.update(overrides)
    return assess_update(**values)


def test_retraction_fixture_test_retraction_reaches_the_whole_chain() -> None:
    plan = assess().payload

    assert plan["affected_evidence_ids"] == ["EV-1"]
    assert plan["affected_claim_ids"] == ["CLM-1"]
    assert plan["affected_pack_ids"] == ["PACK-1"]
    assert plan["affected_passport_ids"] == ["HP-1"]
    assert plan["invalidated_artifact_ids"] == [
        "CLM-1",
        "DEC-1",
        "EV-1",
        "HP-1",
        "PACK-1",
        "SPAN-1",
    ]
    assert plan["passport_states"] == {"HP-1": "INVALIDATED"}
    assert plan["priority"] == "P0"
    assert "human_review" in plan["required_actions"]


def test_retraction_fixture_test_the_unrelated_branch_is_untouched() -> None:
    plan = assess().payload

    for artifact_id in (
        "DOC-2",
        "SPAN-2",
        "CLM-2",
        "EV-2",
        "PACK-2",
        "DEC-2",
        "HP-2",
    ):
        assert artifact_id not in plan["invalidated_artifact_ids"]
    assert "HP-2" not in plan["passport_states"]


def test_retraction_fixture_test_correction_is_weaker_than_retraction() -> None:
    correction = assess(trigger_type="document_correction").payload
    retraction = assess().payload

    assert correction["passport_states"] == {"HP-1": "STALE"}
    assert retraction["passport_states"] == {"HP-1": "INVALIDATED"}
    assert (
        correction["invalidated_artifact_ids"] == retraction["invalidated_artifact_ids"]
    )
    assert correction["priority"] == "P1"


def test_retraction_fixture_test_new_document_prompts_without_invalidating() -> None:
    plan = assess(trigger_type="new_document").payload

    assert plan["invalidated_artifact_ids"] == []
    assert plan["affected_passport_ids"] == ["HP-1"]
    assert plan["passport_states"] == {"HP-1": "STALE"}
    assert plan["required_actions"] == ["reretrieve"]


def test_retraction_fixture_test_invalidation_needs_remediation() -> None:
    with pytest.raises(ReassessmentError) as raised:
        assess(required_actions=["no_action"])
    assert raised.value.code == "INVALIDATION_WITHOUT_REMEDIATION"

    plan = assess(trigger_type="new_document", required_actions=["no_action"]).payload
    assert plan["required_actions"] == ["no_action"]


def test_retraction_fixture_test_graph_and_trigger_contracts_fail_closed() -> None:
    with pytest.raises(ReassessmentError) as raised:
        assess(trigger_artifact_ids=["DOC-GHOST"])
    assert raised.value.code == "TRIGGER_ARTIFACT_UNKNOWN"

    with pytest.raises(ReassessmentError) as raised:
        assess(trigger_type="rumour")
    assert raised.value.code == "TRIGGER_TYPE_UNKNOWN"

    broken = graph()
    broken[2]["depends_on"] = ["DOC-MISSING"]
    with pytest.raises(ReassessmentError) as raised:
        assess(graph=broken)
    assert raised.value.code == "GRAPH_DEPENDENCY_UNKNOWN"

    self_dep = graph()
    self_dep[2]["depends_on"] = ["SPAN-1"]
    with pytest.raises(ReassessmentError) as raised:
        assess(graph=self_dep)
    assert raised.value.code == "GRAPH_SELF_DEPENDENCY"

    duplicated = [*graph(), graph()[0]]
    with pytest.raises(ReassessmentError) as raised:
        assess(graph=duplicated)
    assert raised.value.code == "GRAPH_DUPLICATE_ARTIFACT"

    unknown_class = graph()
    unknown_class[0]["artifact_class"] = "rumour"
    with pytest.raises(ReassessmentError) as raised:
        assess(graph=unknown_class)
    assert raised.value.code == "ARTIFACT_CLASS_UNKNOWN"


def test_retraction_fixture_test_roundtrip_and_tamper_fail_closed() -> None:
    sealed = assess()
    rebuilt = validate_plan(sealed.payload, graph=graph())
    assert rebuilt.canonical_bytes == sealed.canonical_bytes

    tampered = sealed.payload
    tampered["invalidated_artifact_ids"] = []
    with pytest.raises(ReassessmentError) as raised:
        validate_plan(tampered, graph=graph())
    assert raised.value.code == "PLAN_HASH_MISMATCH"

    from .contracts import _hash_excluding

    rehashed = sealed.payload
    rehashed["invalidated_artifact_ids"] = []
    rehashed["plan_hash"] = _hash_excluding(rehashed, "plan_hash")
    with pytest.raises(ReassessmentError) as raised:
        validate_plan(rehashed, graph=graph())
    assert raised.value.code == "PLAN_RECONSTRUCTION_MISMATCH"


def test_retraction_fixture_test_assessment_is_deterministic() -> None:
    assert assess().canonical_bytes == assess().canonical_bytes
    assert assess().payload["plan_id"].startswith("RSP-")


def test_retraction_fixture_test_passport_marking_binds_the_plan() -> None:
    sealed = assess()
    passports = [
        {"passport_id": "HP-1", "revision": 3, "verdict": "SUPPORTED"},
        {"passport_id": "HP-2", "revision": 1, "verdict": "SUPPORTED"},
    ]

    marked = apply_passport_states(passports, sealed.payload)

    touched = next(row for row in marked if row["passport_id"] == "HP-1")
    untouched = next(row for row in marked if row["passport_id"] == "HP-2")
    assert touched["revision"] == 4
    assert touched["staleness_state"] == "INVALIDATED"
    assert touched["staleness_plan_hash"] == sealed.payload["plan_hash"]
    assert touched["staleness_trigger_event_id"] == "EVT-W03-1"
    assert untouched == {"passport_id": "HP-2", "revision": 1, "verdict": "SUPPORTED"}
