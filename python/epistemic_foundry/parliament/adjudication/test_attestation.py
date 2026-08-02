"""attestation_test — the attestor sees a structured pack.

Exit criterion under test: "attestor sees structured pack".  Persuasion is
exactly what an independent reviewer must not receive, so the pack carries ids,
hashes, statuses, ceilings, and counts and refuses any field carrying brief or
challenge prose.  The attestor must be a different actor from the judge and must
attest to exactly the pack it was given.
"""

from __future__ import annotations

import json

import pytest
from jsonschema import Draft202012Validator

from .contracts import (
    PACK_FIELDS,
    PERSUASIVE_FIELDS,
    AdjudicationError,
    assert_structured,
    attestation_statuses,
    build_attestation_pack,
    validate_attestation,
    validate_attestation_pack,
    validate_judgment,
)
from .test_majority_independence import (
    ATTESTOR,
    CREATED_AT,
    JUDGE,
    ROOT,
    adjudication,
    attestation,
    seal,
)


def attestation_schema_validator() -> Draft202012Validator:
    schema = json.loads(
        (ROOT / "schemas" / "attestation.schema.json").read_text(encoding="utf-8")
    )
    return Draft202012Validator(schema)


def pack(**kwargs):
    options = {
        "audit_id": "PA-1",
        "combined_ceiling": "EMPIRICALLY_TESTED",
        "created_at": CREATED_AT,
        "cross_exam_round_id": "CX-round-1",
        "open_challenge_ids": [],
        "strongest_dissent_id": "MR-1",
        "veto_sustained_by": [],
    }
    options.update(kwargs)
    return build_attestation_pack(ROOT, adjudication(), **options).payload


def test_the_status_vocabulary_is_read_from_the_declaring_schema() -> None:
    assert attestation_statuses(ROOT) == ("PASS", "FAIL", "BLOCK")


def test_the_pack_carries_only_structured_fields() -> None:
    record = pack()

    assert sorted(record) == sorted(PACK_FIELDS)
    for field in PERSUASIVE_FIELDS:
        assert field not in record, field


def test_the_pack_carries_the_ids_an_attestor_needs_to_re_verify() -> None:
    record = pack()

    assert record["adjudication_id"] == "ADJ-1"
    assert record["audit_id"] == "PA-1"
    assert record["cross_exam_round_id"] == "CX-round-1"
    assert record["brief_ids"] == ["CB-defender", "CB-prosecutor"]
    assert record["gate_decision_ids"] == ["GD-1"]
    assert record["combined_ceiling"] == "EMPIRICALLY_TESTED"
    assert record["strongest_dissent_id"] == "MR-1"


def test_the_pack_never_carries_the_judges_rationale() -> None:
    record = pack()

    assert "rationale" not in record
    assert json.dumps(record).find("survives cross-examination") == -1


@pytest.mark.parametrize("field", list(PERSUASIVE_FIELDS))
def test_any_persuasive_field_is_refused_anywhere_in_the_pack(field: str) -> None:
    with pytest.raises(AdjudicationError) as caught:
        assert_structured({"nested": [{"ok": 1, field: "persuade me"}]})

    assert caught.value.code == "PERSUASIVE_TRANSCRIPT_INCLUDED"
    assert caught.value.context["field"] == field


def test_a_structured_pack_passes_the_prose_scan() -> None:
    assert_structured(pack())


def test_a_sealed_pack_with_prose_added_is_refused() -> None:
    from .contracts import _hash_excluding

    record = pack()
    record["rationale"] = "trust me"
    record["pack_hash"] = _hash_excluding(record, "pack_hash")

    with pytest.raises(AdjudicationError) as caught:
        validate_attestation_pack(record)

    assert caught.value.code == "FIELD_SET_INVALID"


def test_a_tampered_pack_is_rejected() -> None:
    record = pack()
    record["combined_ceiling"] = "REPLICATED"

    with pytest.raises(AdjudicationError) as caught:
        validate_attestation_pack(record)

    assert caught.value.code == "PACK_HASH_MISMATCH"


def test_the_fixture_attestation_satisfies_the_canonical_schema() -> None:
    validator = attestation_schema_validator()

    assert (
        sorted(
            validator.iter_errors(attestation(pack()["attestation_pack_id"])), key=str
        )
        == []
    )


def test_the_judge_may_not_attest_to_its_own_adjudication() -> None:
    record = pack()

    with pytest.raises(AdjudicationError) as caught:
        validate_attestation(
            ROOT,
            attestation(record["attestation_pack_id"], attestor=JUDGE),
            record,
            judge_id=JUDGE,
        )

    assert caught.value.code == "ATTESTOR_NOT_INDEPENDENT"


def test_an_attestation_must_rest_on_exactly_the_pack_it_was_given() -> None:
    record = pack()

    with pytest.raises(AdjudicationError) as caught:
        validate_attestation(
            ROOT,
            attestation(record["attestation_pack_id"], inputs=["AP-other"]),
            record,
            judge_id=JUDGE,
        )

    assert caught.value.code == "ATTESTATION_INPUT_MISMATCH"


def test_an_attestation_over_extra_inputs_is_refused() -> None:
    record = pack()

    with pytest.raises(AdjudicationError) as caught:
        validate_attestation(
            ROOT,
            attestation(
                record["attestation_pack_id"],
                inputs=[record["attestation_pack_id"], "CB-defender"],
            ),
            record,
            judge_id=JUDGE,
        )

    assert caught.value.code == "ATTESTATION_INPUT_MISMATCH"


def test_an_attestation_must_name_the_adjudication_its_pack_describes() -> None:
    record = pack()

    with pytest.raises(AdjudicationError) as caught:
        validate_attestation(
            ROOT,
            attestation(record["attestation_pack_id"], subject="ADJ-other"),
            record,
            judge_id=JUDGE,
        )

    assert caught.value.code == "ATTESTATION_SUBJECT_MISMATCH"


def test_an_attestation_must_record_the_checks_it_ran() -> None:
    record = pack()

    with pytest.raises(AdjudicationError) as caught:
        validate_attestation(
            ROOT,
            attestation(record["attestation_pack_id"], checks=[]),
            record,
            judge_id=JUDGE,
        )

    assert caught.value.code == "ATTESTATION_UNCHECKED"


def test_attestation_checks_may_not_smuggle_prose_back_in() -> None:
    record = pack()

    with pytest.raises(AdjudicationError) as caught:
        validate_attestation(
            ROOT,
            attestation(
                record["attestation_pack_id"],
                checks=[
                    {
                        "check_id": "C1",
                        "rationale": "I found it convincing",
                        "status": "PASS",
                    }
                ],
            ),
            record,
            judge_id=JUDGE,
        )

    assert caught.value.code == "PERSUASIVE_TRANSCRIPT_INCLUDED"


def test_a_non_canonical_attestor_type_is_refused() -> None:
    record = pack()
    forged = attestation(record["attestation_pack_id"])
    forged["attestor_type"] = "oracle"

    with pytest.raises(AdjudicationError) as caught:
        validate_attestation(ROOT, forged, record, judge_id=JUDGE)

    assert caught.value.code == "ATTESTOR_TYPE_INVALID"


def test_a_non_canonical_overall_status_is_refused() -> None:
    record = pack()

    with pytest.raises(AdjudicationError) as caught:
        validate_attestation(
            ROOT,
            attestation(record["attestation_pack_id"], status="PROBABLY"),
            record,
            judge_id=JUDGE,
        )

    assert caught.value.code == "ATTESTATION_STATUS_INVALID"


def test_a_failing_attestation_still_seals_and_says_so() -> None:
    record = pack()
    payload = seal(
        att=attestation(record["attestation_pack_id"], status="FAIL")
    ).payload

    assert payload["attestation"]["overall_status"] == "FAIL"
    assert payload["independence"]["attestor_is_judge"] is False


def test_an_attestation_from_another_run_cannot_join_this_gate() -> None:
    from .contracts import seal_record

    record = pack()
    foreign = attestation(record["attestation_pack_id"])
    foreign["run_id"] = "RUN-other"
    foreign = seal_record(foreign, "attestation_hash")

    with pytest.raises(AdjudicationError) as caught:
        seal(att=foreign)

    assert caught.value.code == "GATE_INCOHERENT"


def test_the_sealed_gate_records_who_attested_and_who_judged() -> None:
    payload = seal().payload

    assert payload["independence"] == {
        "attestor_id": ATTESTOR,
        "attestor_is_judge": False,
        "judge_id": JUDGE,
    }
    assert payload["attestation"]["independence_statement"]


def test_a_sealed_gate_cannot_record_the_judge_as_its_attestor() -> None:
    from .contracts import _hash_excluding

    payload = seal().payload
    payload["independence"]["attestor_id"] = JUDGE
    payload["gate_hash"] = _hash_excluding(payload, "gate_hash")

    with pytest.raises(AdjudicationError) as caught:
        validate_judgment(ROOT, payload)

    assert caught.value.code == "ATTESTOR_NOT_INDEPENDENT"


def test_the_sealed_gate_embeds_the_pack_the_attestor_actually_read() -> None:
    payload = seal().payload

    assert payload["attestation"]["input_artifact_ids"] == [
        payload["attestation_pack"]["attestation_pack_id"]
    ]
    validate_attestation_pack(payload["attestation_pack"])


def test_the_pack_is_deterministic_and_content_addressed() -> None:
    assert pack() == pack()
    assert pack()["attestation_pack_id"].startswith("AP-")
