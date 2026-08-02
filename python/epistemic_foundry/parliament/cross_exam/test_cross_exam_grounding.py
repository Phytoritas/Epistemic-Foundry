"""cross_exam_grounding_test — attacks cite IDs.

Exit criterion under test: "attacks cite IDs".  A challenge must name a brief
this round carries, an assertion inside that brief, and evidence its own
attacker context actually contained.  A challenge that cites nothing, or cites
what was withheld from it, is refused rather than recorded as scrutiny.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from blind.test_evidence_acl import RUN, adversarial_panel
from blind.contracts import BriefRole

from .contracts import (
    OPEN_STATUS,
    CrossExamError,
    ResolutionStatus,
    attack_types,
    resolution_statuses,
    seal_cross_exam_round,
    seal_record,
    validate_cross_exam_round,
)

ROOT = Path(__file__).resolve().parents[4]
CREATED_AT = "2026-08-01T17:00:00Z"
ROUND = 2


def exam_schema_validator() -> Draft202012Validator:
    schema = json.loads(
        (ROOT / "schemas" / "cross-examination.schema.json").read_text(encoding="utf-8")
    )
    return Draft202012Validator(schema)


def panel():
    contexts, briefs = adversarial_panel()
    return contexts, briefs


def challenge(
    exam_id: str,
    attacker: str,
    target_brief: str,
    target_assertion: str,
    *,
    evidence_ids: list[str] | None = None,
    attack_type: str = "evidence_attack",
    status: str = ResolutionStatus.ANSWERED.value,
    response: str | None = "the effect held after reanalysis",
) -> dict[str, object]:
    return seal_record(
        {
            "attack_type": attack_type,
            "attacker_role": attacker,
            "challenge": f"challenge {exam_id}",
            "created_at": CREATED_AT,
            "cross_exam_id": exam_id,
            "evidence_ids": (
                ["EVN-counter"] if evidence_ids is None else list(evidence_ids)
            ),
            "record_hash": "sha256:" + "0" * 64,
            "resolution_condition": "a preregistered replication reports the same sign",
            "resolution_status": status,
            "response": None if status == OPEN_STATUS else response,
            "run_id": RUN,
            "target_assertion_id": target_assertion,
            "target_brief_id": target_brief,
        },
        "record_hash",
    )


def prosecutor_attacks_defender(**kwargs) -> dict[str, object]:
    return challenge(
        "CX-1",
        BriefRole.PROSECUTOR.value,
        "CB-defender",
        "CB-defender-A1",
        **kwargs,
    )


def seal(exams=None, reports=None, contexts=None, briefs=None, **kwargs):
    default_contexts, default_briefs = panel()
    options = {"created_at": CREATED_AT, "round_number": ROUND, "run_id": RUN}
    options.update(kwargs)
    return seal_cross_exam_round(
        ROOT,
        briefs if briefs is not None else default_briefs,
        contexts if contexts is not None else default_contexts,
        exams if exams is not None else [prosecutor_attacks_defender()],
        reports if reports is not None else [],
        **options,
    )


def test_the_vocabularies_are_read_from_the_declaring_schemas() -> None:
    assert attack_types(ROOT) == (
        "premise_attack",
        "evidence_attack",
        "scope_attack",
        "method_attack",
        "causal_attack",
        "dependency_attack",
        "bias_attack",
        "alternative_explanation",
    )
    assert resolution_statuses(ROOT) == (
        "unanswered",
        "answered",
        "sustained",
        "overruled",
        "partially_sustained",
    )


def test_a_grounded_attack_seals_with_its_targets_recorded() -> None:
    record = seal().payload

    assert record["grounding"]["attack_count"] == 1
    assert record["grounding"]["targeted_brief_ids"] == ["CB-defender"]
    assert record["grounding"]["targeted_assertion_ids"] == ["CB-defender-A1"]
    assert record["cross_exam_round_id"].startswith("CX-")


def test_the_fixture_challenge_satisfies_the_canonical_schema() -> None:
    validator = exam_schema_validator()

    assert sorted(validator.iter_errors(prosecutor_attacks_defender()), key=str) == []


def test_an_attack_citing_no_evidence_is_refused() -> None:
    with pytest.raises(CrossExamError) as caught:
        seal([prosecutor_attacks_defender(evidence_ids=[])])

    assert caught.value.code == "ATTACK_UNGROUNDED"


def test_an_attack_on_a_brief_this_round_does_not_carry_is_refused() -> None:
    stray = challenge("CX-1", BriefRole.PROSECUTOR.value, "CB-ghost", "CB-defender-A1")

    with pytest.raises(CrossExamError) as caught:
        seal([stray])

    assert caught.value.code == "ATTACK_TARGET_UNRESOLVED"
    assert caught.value.context["target_brief_id"] == "CB-ghost"


def test_an_attack_on_an_assertion_outside_its_target_is_refused() -> None:
    misaimed = challenge(
        "CX-1", BriefRole.PROSECUTOR.value, "CB-defender", "CB-prosecutor-A1"
    )

    with pytest.raises(CrossExamError) as caught:
        seal([misaimed])

    assert caught.value.code == "ATTACK_ASSERTION_UNRESOLVED"


def test_citing_evidence_withheld_from_the_attacker_is_refused() -> None:
    with pytest.raises(CrossExamError) as caught:
        seal([prosecutor_attacks_defender(evidence_ids=["EVN-support"])])

    assert caught.value.code == "ATTACK_EVIDENCE_UNGROUNDED"
    assert caught.value.context["cited_withheld"] == ["EVN-support"]


def test_citing_evidence_no_context_ever_held_is_refused() -> None:
    with pytest.raises(CrossExamError) as caught:
        seal([prosecutor_attacks_defender(evidence_ids=["EVN-invented"])])

    assert caught.value.code == "ATTACK_EVIDENCE_UNGROUNDED"
    assert caught.value.context["evidence_ids"] == ["EVN-invented"]


def test_an_attacker_with_no_context_this_round_is_refused() -> None:
    contexts, briefs = panel()

    with pytest.raises(CrossExamError) as caught:
        seal([prosecutor_attacks_defender()], contexts=contexts[:1])

    assert caught.value.code == "ATTACKER_CONTEXT_MISSING"


def test_a_role_may_not_cross_examine_its_own_brief() -> None:
    self_attack = challenge(
        "CX-1", BriefRole.DEFENDER.value, "CB-defender", "CB-defender-A1"
    )

    with pytest.raises(CrossExamError) as caught:
        seal([self_attack])

    assert caught.value.code == "SELF_ATTACK_FORBIDDEN"


def test_a_non_canonical_attack_type_is_refused() -> None:
    with pytest.raises(CrossExamError) as caught:
        seal([prosecutor_attacks_defender(attack_type="vibes_attack")])

    assert caught.value.code == "ATTACK_TYPE_INVALID"


def test_a_non_canonical_resolution_status_is_refused() -> None:
    with pytest.raises(CrossExamError) as caught:
        seal([prosecutor_attacks_defender(status="probably_fine")])

    assert caught.value.code == "RESOLUTION_STATUS_INVALID"


def test_an_unanswered_challenge_stays_open_and_carries_no_response() -> None:
    record = seal([prosecutor_attacks_defender(status=OPEN_STATUS)]).payload

    assert record["grounding"]["open_challenge_ids"] == ["CX-1"]
    assert record["cross_examinations"][0]["response"] is None


def test_an_unanswered_challenge_may_not_carry_a_response() -> None:
    forged = prosecutor_attacks_defender(status=OPEN_STATUS)
    forged["response"] = "answered after all"
    forged = seal_record(forged, "record_hash")

    with pytest.raises(CrossExamError) as caught:
        seal([forged])

    assert caught.value.code == "RESPONSE_UNEXPECTED"


def test_an_answered_challenge_must_carry_a_response() -> None:
    with pytest.raises(CrossExamError) as caught:
        seal([prosecutor_attacks_defender(response=None)])

    assert caught.value.code == "INPUT_INVALID"


def test_a_duplicate_challenge_id_is_refused() -> None:
    with pytest.raises(CrossExamError) as caught:
        seal([prosecutor_attacks_defender(), prosecutor_attacks_defender()])

    assert caught.value.code == "DUPLICATE_CROSS_EXAM"


def test_cross_examination_may_not_run_in_the_blind_first_round() -> None:
    with pytest.raises(CrossExamError) as caught:
        seal(round_number=1)

    assert caught.value.code == "ROUND_INVALID"


def test_a_challenge_from_another_run_cannot_join_this_round() -> None:
    foreign = prosecutor_attacks_defender()
    foreign["run_id"] = "RUN-other"
    foreign = seal_record(foreign, "record_hash")

    with pytest.raises(CrossExamError) as caught:
        seal([foreign])

    assert caught.value.code == "ROUND_INCOHERENT"


def test_a_sealed_round_may_not_carry_an_attack_that_cites_nothing() -> None:
    from .contracts import _hash_excluding

    payload = seal().payload
    payload["cross_examinations"][0]["evidence_ids"] = []
    payload["round_hash"] = _hash_excluding(payload, "round_hash")

    with pytest.raises(CrossExamError) as caught:
        validate_cross_exam_round(ROOT, payload)

    assert caught.value.code == "ATTACK_UNGROUNDED"


def test_a_sealed_round_must_count_every_attack_as_grounded() -> None:
    from .contracts import _hash_excluding

    payload = seal().payload
    payload["grounding"]["attacks_citing_evidence"] = 0
    payload["round_hash"] = _hash_excluding(payload, "round_hash")

    with pytest.raises(CrossExamError) as caught:
        validate_cross_exam_round(ROOT, payload)

    assert caught.value.code == "GROUNDING_MISMATCH"


def test_a_tampered_round_is_rejected() -> None:
    payload = seal().payload
    payload["run_id"] = "RUN-other"

    with pytest.raises(CrossExamError) as caught:
        validate_cross_exam_round(ROOT, payload)

    assert caught.value.code == "ROUND_HASH_MISMATCH"


def test_the_round_is_deterministic_and_content_addressed() -> None:
    first = seal()
    second = seal()

    assert first.canonical_bytes == second.canonical_bytes
    assert (
        validate_cross_exam_round(ROOT, first.payload).canonical_bytes
        == first.canonical_bytes
    )


def test_the_defender_may_answer_back_within_its_own_context() -> None:
    counter = challenge(
        "CX-2",
        BriefRole.DEFENDER.value,
        "CB-prosecutor",
        "CB-prosecutor-A1",
        attack_type="alternative_explanation",
        evidence_ids=["EVN-mechanism"],
    )

    record = seal([prosecutor_attacks_defender(), counter]).payload

    assert record["grounding"]["attack_count"] == 2
    assert record["grounding"]["targeted_brief_ids"] == ["CB-defender", "CB-prosecutor"]
