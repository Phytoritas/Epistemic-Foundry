"""evidence_acl_test — roles cannot see forbidden evidence.

Exit criterion under test: "roles cannot see forbidden evidence".  Each role's
ACL is read from the declaring registry, the assembled context carries only the
permitted classes, what was withheld is named so its existence is visible, and a
brief citing evidence its own context never contained is refused.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from .contracts import (
    ACL_WILDCARD,
    MINIMUM_DISPATCHED_ROLES,
    BriefRole,
    ParliamentBlindError,
    Verdict,
    assemble_context,
    cited_evidence,
    evidence_acl,
    measure_asymmetry,
    seal_brief,
    seal_dispatch,
    validate_context_manifest,
)

ROOT = Path(__file__).resolve().parents[4]
CREATED_AT = "2026-08-01T13:00:00Z"
RUN = "RUN-1"


def brief_schema_validator() -> Draft202012Validator:
    schema = json.loads(
        (ROOT / "schemas" / "council-brief.schema.json").read_text(encoding="utf-8")
    )
    return Draft202012Validator(schema)


def unit(evidence_id: str, evidence_class: str) -> dict[str, object]:
    return {
        "evidence_class": evidence_class,
        "evidence_id": evidence_id,
        "provenance_ref": f"prov:{evidence_id}",
        "summary": f"summary for {evidence_id}",
    }


def corpus() -> list[dict[str, object]]:
    return [
        unit("EVN-support", "support"),
        unit("EVN-counter", "counter"),
        unit("EVN-null", "null"),
        unit("EVN-boundary", "boundary"),
        unit("EVN-method", "method"),
        unit("EVN-mechanism", "mechanism"),
    ]


def context_for(role: str, *, round_number: int = 1) -> dict[str, object]:
    return assemble_context(
        ROOT,
        role,
        corpus(),
        created_at=CREATED_AT,
        round_number=round_number,
        run_id=RUN,
    ).payload


def assertion(
    assertion_id: str, evidence_ids: list[str], *, confidence: float = 0.6
) -> dict[str, object]:
    return {
        "argument_node_ids": [],
        "assertion_id": assertion_id,
        "confidence": confidence,
        "evidence_ids": list(evidence_ids),
        "scope_limitations": ["greenhouse only"],
        "text": f"assertion {assertion_id}",
    }


def brief(
    brief_id: str,
    role: str,
    context: dict[str, object],
    *,
    evidence_ids: list[str] | None = None,
    blind: bool = True,
    round_number: int = 1,
    verdict: str = Verdict.CONDITIONAL.value,
    conditions: list[str] | None = None,
) -> dict[str, object]:
    cited = (
        list(evidence_ids)
        if evidence_ids is not None
        else list(context["included_evidence_ids"])[:1]
    )
    return seal_brief(
        {
            "assertions": [assertion(f"{brief_id}-A1", cited)],
            "blind": blind,
            "brief_hash": "sha256:" + "0" * 64,
            "brief_id": brief_id,
            "conditions_that_change_verdict": (
                list(conditions) if conditions is not None else ["a replication fails"]
            ),
            "context_manifest_id": context["context_manifest_id"],
            "created_at": CREATED_AT,
            "missing_evidence": [],
            "role": role,
            "round": round_number,
            "run_id": RUN,
            "schema_version": "4.0.0",
            "strongest_counterargument": "the effect may be seasonal",
            "verdict_candidate": verdict,
        }
    )


def adversarial_panel() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    defender_context = context_for(BriefRole.DEFENDER.value)
    prosecutor_context = context_for(BriefRole.PROSECUTOR.value)
    return (
        [defender_context, prosecutor_context],
        [
            brief("CB-defender", BriefRole.DEFENDER.value, defender_context),
            brief("CB-prosecutor", BriefRole.PROSECUTOR.value, prosecutor_context),
        ],
    )


def test_the_acl_is_read_from_the_declaring_registry() -> None:
    assert evidence_acl(ROOT, "defender") == ("mechanism", "support")
    assert evidence_acl(ROOT, "prosecutor") == ("boundary", "counter", "method", "null")
    assert evidence_acl(ROOT, "minority_reporter") == (ACL_WILDCARD,)


def test_an_unregistered_role_has_no_acl_and_fails_closed() -> None:
    with pytest.raises(ParliamentBlindError) as caught:
        evidence_acl(ROOT, "self_appointed_expert")

    assert caught.value.code == "ROLE_UNKNOWN"


def test_a_context_carries_only_the_permitted_classes() -> None:
    context = context_for(BriefRole.DEFENDER.value)

    assert context["included_evidence_ids"] == ["EVN-mechanism", "EVN-support"]
    assert context["permitted_classes"] == ["mechanism", "support"]


def test_what_was_withheld_is_named_so_its_existence_is_visible() -> None:
    context = context_for(BriefRole.DEFENDER.value)

    assert context["withheld_evidence_ids"] == [
        "EVN-boundary",
        "EVN-counter",
        "EVN-method",
        "EVN-null",
    ]
    assert context["withheld_class_counts"] == {
        "boundary": 1,
        "counter": 1,
        "method": 1,
        "null": 1,
    }


def test_the_prosecutor_sees_the_complement_of_the_defender() -> None:
    defender = set(context_for(BriefRole.DEFENDER.value)["included_evidence_ids"])
    prosecutor = set(context_for(BriefRole.PROSECUTOR.value)["included_evidence_ids"])

    assert defender & prosecutor == set()
    assert "EVN-counter" in prosecutor
    assert "EVN-support" in defender


def test_a_wildcard_acl_sees_everything_and_withholds_nothing() -> None:
    context = assemble_context(
        ROOT,
        "minority_reporter",
        corpus(),
        created_at=CREATED_AT,
        round_number=1,
        run_id=RUN,
    ).payload

    assert context["withheld_evidence_ids"] == []
    assert len(context["included_evidence_ids"]) == len(corpus())


def test_a_duplicate_evidence_id_is_refused() -> None:
    with pytest.raises(ParliamentBlindError) as caught:
        assemble_context(
            ROOT,
            BriefRole.DEFENDER.value,
            [unit("EVN-1", "support"), unit("EVN-1", "mechanism")],
            created_at=CREATED_AT,
            round_number=1,
            run_id=RUN,
        )

    assert caught.value.code == "DUPLICATE_EVIDENCE"


def test_citing_withheld_evidence_is_an_acl_violation() -> None:
    contexts, briefs = adversarial_panel()
    briefs[0] = brief(
        "CB-defender",
        BriefRole.DEFENDER.value,
        contexts[0],
        evidence_ids=["EVN-counter"],
    )

    with pytest.raises(ParliamentBlindError) as caught:
        seal_dispatch(
            contexts, briefs, created_at=CREATED_AT, round_number=1, run_id=RUN
        )

    assert caught.value.code == "EVIDENCE_ACL_VIOLATION"
    assert caught.value.context["cited_withheld"] == ["EVN-counter"]
    assert caught.value.context["role"] == "defender"


def test_citing_evidence_no_context_ever_held_is_an_acl_violation() -> None:
    contexts, briefs = adversarial_panel()
    briefs[1] = brief(
        "CB-prosecutor",
        BriefRole.PROSECUTOR.value,
        contexts[1],
        evidence_ids=["EVN-invented"],
    )

    with pytest.raises(ParliamentBlindError) as caught:
        seal_dispatch(
            contexts, briefs, created_at=CREATED_AT, round_number=1, run_id=RUN
        )

    assert caught.value.code == "EVIDENCE_ACL_VIOLATION"
    assert caught.value.context["evidence_ids"] == ["EVN-invented"]


def test_using_another_roles_context_is_refused() -> None:
    contexts, briefs = adversarial_panel()
    briefs[0] = brief("CB-defender", BriefRole.DEFENDER.value, contexts[1])

    with pytest.raises(ParliamentBlindError) as caught:
        seal_dispatch(
            contexts, briefs, created_at=CREATED_AT, round_number=1, run_id=RUN
        )

    assert caught.value.code == "CONTEXT_ROLE_MISMATCH"


def test_a_brief_naming_an_unassembled_context_is_refused() -> None:
    contexts, briefs = adversarial_panel()
    briefs[0]["context_manifest_id"] = "CM-ghost"
    briefs[0] = seal_brief(briefs[0])

    with pytest.raises(ParliamentBlindError) as caught:
        seal_dispatch(
            contexts, briefs, created_at=CREATED_AT, round_number=1, run_id=RUN
        )

    assert caught.value.code == "CONTEXT_UNRESOLVED"


def test_a_dispatched_role_that_returns_no_brief_is_refused() -> None:
    contexts, briefs = adversarial_panel()

    with pytest.raises(ParliamentBlindError) as caught:
        seal_dispatch(
            contexts, briefs[:1], created_at=CREATED_AT, round_number=1, run_id=RUN
        )

    assert caught.value.code == "BRIEF_MISSING"
    assert caught.value.context["roles"] == ["prosecutor"]


def test_a_compliant_panel_seals_with_its_role_class_matrix() -> None:
    contexts, briefs = adversarial_panel()

    record = seal_dispatch(
        contexts, briefs, created_at=CREATED_AT, round_number=1, run_id=RUN
    ).payload

    assert record["role_class_matrix"] == {
        "defender": ["mechanism", "support"],
        "prosecutor": ["boundary", "counter", "method", "null"],
    }
    assert record["dispatch_id"].startswith("PD-")


def test_a_symmetric_panel_is_refused_as_one_opinion_repeated() -> None:
    context = context_for(BriefRole.DEFENDER.value)
    twin = dict(context)
    twin["role"] = BriefRole.PROSECUTOR.value
    twin["context_manifest_id"] = "CM-twin"
    from .contracts import _hash_excluding

    twin["manifest_hash"] = _hash_excluding(twin, "manifest_hash")
    briefs = [
        brief("CB-a", BriefRole.DEFENDER.value, context),
        brief("CB-b", BriefRole.PROSECUTOR.value, twin),
    ]

    with pytest.raises(ParliamentBlindError) as caught:
        seal_dispatch(
            [context, twin], briefs, created_at=CREATED_AT, round_number=1, run_id=RUN
        )

    assert caught.value.code == "DISPATCH_SYMMETRIC"


def test_a_single_role_is_not_a_parliament() -> None:
    contexts, briefs = adversarial_panel()

    with pytest.raises(ParliamentBlindError) as caught:
        seal_dispatch(
            contexts[:1], briefs[:1], created_at=CREATED_AT, round_number=1, run_id=RUN
        )

    assert caught.value.code == "DISPATCH_TOO_NARROW"
    assert MINIMUM_DISPATCHED_ROLES == 2


def test_asymmetry_is_measured_over_what_each_role_actually_received() -> None:
    contexts, _ = adversarial_panel()

    asymmetry = measure_asymmetry(contexts)

    assert asymmetry["symmetric"] is False
    assert asymmetry["distinct_context_count"] == 2
    assert asymmetry["role_count"] == 2


def test_a_context_cannot_both_include_and_withhold_one_unit() -> None:
    from .contracts import _hash_excluding

    context = context_for(BriefRole.DEFENDER.value)
    context["withheld_evidence_ids"] = sorted(
        [*context["withheld_evidence_ids"], "EVN-support"]
    )
    context["manifest_hash"] = _hash_excluding(context, "manifest_hash")

    with pytest.raises(ParliamentBlindError) as caught:
        validate_context_manifest(context)

    assert caught.value.code == "CONTEXT_INCOHERENT"


def test_a_tampered_context_manifest_is_rejected() -> None:
    context = context_for(BriefRole.DEFENDER.value)
    context["role"] = BriefRole.PROSECUTOR.value

    with pytest.raises(ParliamentBlindError) as caught:
        validate_context_manifest(context)

    assert caught.value.code == "MANIFEST_HASH_MISMATCH"


def test_the_brief_fixtures_satisfy_the_canonical_schema() -> None:
    validator = brief_schema_validator()
    _, briefs = adversarial_panel()

    for candidate in briefs:
        assert sorted(validator.iter_errors(candidate), key=str) == []


def test_a_brief_with_no_falsifying_condition_is_refused() -> None:
    contexts, briefs = adversarial_panel()
    briefs[0] = brief(
        "CB-defender", BriefRole.DEFENDER.value, contexts[0], conditions=[]
    )

    with pytest.raises(ParliamentBlindError) as caught:
        seal_dispatch(
            contexts, briefs, created_at=CREATED_AT, round_number=1, run_id=RUN
        )

    assert caught.value.code == "BRIEF_UNFALSIFIABLE"


def test_cited_evidence_collects_across_every_assertion() -> None:
    contexts, _ = adversarial_panel()
    candidate = brief(
        "CB-defender",
        BriefRole.DEFENDER.value,
        contexts[0],
        evidence_ids=["EVN-support"],
    )
    candidate["assertions"].append(assertion("CB-defender-A2", ["EVN-mechanism"]))

    assert cited_evidence(candidate) == {"EVN-support", "EVN-mechanism"}
