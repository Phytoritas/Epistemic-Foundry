"""minority_preservation_test — the strongest dissent is preserved.

Exit criterion under test: "strongest dissent preserved".  A minority report is
most valuable exactly when the majority is comfortable, so the report with the
greatest expected information gain must survive into the record: it may be set
aside only by cited new evidence, and never simply dropped.
"""

from __future__ import annotations

import json

import pytest
from jsonschema import Draft202012Validator

from blind.test_evidence_acl import RUN

from .contracts import (
    SURVIVING_PRESERVATION,
    CrossExamError,
    Preservation,
    preservation_statuses,
    seal_record,
    strongest_dissent,
    validate_cross_exam_round,
    validate_minority_report,
)
from .test_cross_exam_grounding import CREATED_AT, ROOT, seal

REPORT_SCHEMA = ROOT / "schemas" / "minority-report.schema.json"


def report_schema_validator() -> Draft202012Validator:
    return Draft202012Validator(json.loads(REPORT_SCHEMA.read_text(encoding="utf-8")))


def report(
    report_id: str,
    gain: float,
    *,
    author: str = "minority_reporter",
    preservation: str = Preservation.PRESERVED.value,
    evidence_ids: list[str] | None = None,
) -> dict[str, object]:
    return seal_record(
        {
            "author_role": author,
            "created_at": CREATED_AT,
            "evidence_ids": ["EVN-null"]
            if evidence_ids is None
            else list(evidence_ids),
            "expected_information_gain": gain,
            "minority_claim": f"claim for {report_id}",
            "minority_report_id": report_id,
            "preservation_status": preservation,
            "report_hash": "sha256:" + "0" * 64,
            "run_id": RUN,
            "unresolved_test": "run the preregistered null-lane replication",
            "why_majority_may_be_wrong": "the null lane was never searched at depth",
        },
        "report_hash",
    )


def test_the_preservation_vocabulary_is_read_from_the_declaring_schema() -> None:
    assert preservation_statuses(ROOT) == (
        "required",
        "preserved",
        "superseded_by_new_evidence",
    )
    assert SURVIVING_PRESERVATION == ("required", "preserved")


def test_the_fixture_report_satisfies_the_canonical_schema() -> None:
    validator = report_schema_validator()

    assert sorted(validator.iter_errors(report("MR-1", 0.7)), key=str) == []


def test_the_strongest_dissent_is_the_one_with_the_greatest_gain() -> None:
    reports = [report("MR-1", 0.2), report("MR-2", 0.9), report("MR-3", 0.5)]

    assert strongest_dissent(reports) == "MR-2"


def test_ties_are_broken_deterministically_by_id() -> None:
    reports = [report("MR-b", 0.5), report("MR-a", 0.5)]

    assert strongest_dissent(reports) == "MR-a"
    assert strongest_dissent(list(reversed(reports))) == "MR-a"


def test_no_reports_means_no_strongest_dissent() -> None:
    assert strongest_dissent([]) is None


def test_a_round_records_which_dissent_was_strongest() -> None:
    record = seal(reports=[report("MR-1", 0.2), report("MR-2", 0.9)]).payload

    assert record["dissent"]["strongest_report_id"] == "MR-2"
    assert record["dissent"]["report_count"] == 2
    assert record["dissent"]["preserved_report_ids"] == ["MR-1", "MR-2"]


def test_every_report_is_retained_whatever_its_status() -> None:
    record = seal(
        reports=[
            report("MR-1", 0.9),
            report(
                "MR-2",
                0.3,
                preservation=Preservation.SUPERSEDED.value,
                evidence_ids=["EVN-new"],
            ),
        ]
    ).payload

    assert [entry["minority_report_id"] for entry in record["minority_reports"]] == [
        "MR-1",
        "MR-2",
    ]
    assert record["dissent"]["superseded_report_ids"] == ["MR-2"]


def test_the_strongest_dissent_may_be_marked_required() -> None:
    record = seal(
        reports=[report("MR-1", 0.9, preservation=Preservation.REQUIRED.value)]
    ).payload

    assert record["dissent"]["preserved_report_ids"] == ["MR-1"]


def test_the_strongest_dissent_may_be_superseded_only_with_cited_evidence() -> None:
    record = seal(
        reports=[
            report(
                "MR-1",
                0.9,
                preservation=Preservation.SUPERSEDED.value,
                evidence_ids=["EVN-new", "EVN-newer"],
            )
        ]
    ).payload

    assert record["dissent"]["superseded_report_ids"] == ["MR-1"]
    assert record["minority_reports"][0]["evidence_ids"] == ["EVN-new", "EVN-newer"]


def test_superseding_without_evidence_is_refused() -> None:
    with pytest.raises(CrossExamError) as caught:
        seal(
            reports=[
                report(
                    "MR-1",
                    0.9,
                    preservation=Preservation.SUPERSEDED.value,
                    evidence_ids=[],
                )
            ]
        )

    assert caught.value.code == "SUPERSESSION_UNSUPPORTED"


def test_a_non_canonical_preservation_status_is_refused() -> None:
    with pytest.raises(CrossExamError) as caught:
        validate_minority_report(ROOT, report("MR-1", 0.9, preservation="discarded"))

    assert caught.value.code == "PRESERVATION_STATUS_INVALID"


def test_a_negative_information_gain_is_refused() -> None:
    with pytest.raises(CrossExamError) as caught:
        validate_minority_report(ROOT, report("MR-1", -0.1))

    assert caught.value.code == "INFORMATION_GAIN_INVALID"


def test_a_duplicate_report_id_is_refused() -> None:
    with pytest.raises(CrossExamError) as caught:
        seal(reports=[report("MR-1", 0.9), report("MR-1", 0.2)])

    assert caught.value.code == "DUPLICATE_MINORITY_REPORT"


def test_a_report_from_another_run_cannot_join_this_round() -> None:
    foreign = report("MR-1", 0.9)
    foreign["run_id"] = "RUN-other"
    foreign = seal_record(foreign, "report_hash")

    with pytest.raises(CrossExamError) as caught:
        seal(reports=[foreign])

    assert caught.value.code == "ROUND_INCOHERENT"


def test_dropping_the_strongest_dissent_from_a_rehashed_round_fails_closed() -> None:
    from .contracts import _hash_excluding

    payload = seal(reports=[report("MR-1", 0.2), report("MR-2", 0.9)]).payload
    payload["minority_reports"] = payload["minority_reports"][:1]
    payload["dissent"]["report_count"] = 1
    payload["round_hash"] = _hash_excluding(payload, "round_hash")

    with pytest.raises(CrossExamError) as caught:
        validate_cross_exam_round(ROOT, payload)

    assert caught.value.code == "DISSENT_MISMATCH"
    assert caught.value.context["recorded"] == "MR-2"


def test_renaming_the_strongest_dissent_is_refused() -> None:
    from .contracts import _hash_excluding

    payload = seal(reports=[report("MR-1", 0.2), report("MR-2", 0.9)]).payload
    payload["dissent"]["strongest_report_id"] = "MR-1"
    payload["round_hash"] = _hash_excluding(payload, "round_hash")

    with pytest.raises(CrossExamError) as caught:
        validate_cross_exam_round(ROOT, payload)

    assert caught.value.code == "DISSENT_MISMATCH"


def test_removing_the_strongest_dissent_from_both_lists_fails_closed() -> None:
    from .contracts import _hash_excluding

    payload = seal(reports=[report("MR-1", 0.9)]).payload
    payload["dissent"]["preserved_report_ids"] = []
    payload["round_hash"] = _hash_excluding(payload, "round_hash")

    with pytest.raises(CrossExamError) as caught:
        validate_cross_exam_round(ROOT, payload)

    assert caught.value.code == "DISSENT_DROPPED"


def test_stripping_the_superseding_evidence_from_a_sealed_round_fails_closed() -> None:
    from .contracts import _hash_excluding

    payload = seal(
        reports=[
            report(
                "MR-1",
                0.9,
                preservation=Preservation.SUPERSEDED.value,
                evidence_ids=["EVN-new"],
            )
        ]
    ).payload
    payload["minority_reports"][0]["evidence_ids"] = []
    payload["round_hash"] = _hash_excluding(payload, "round_hash")

    with pytest.raises(CrossExamError) as caught:
        validate_cross_exam_round(ROOT, payload)

    assert caught.value.code == "SUPERSESSION_UNSUPPORTED"


def test_a_round_with_no_dissent_still_seals() -> None:
    record = seal(reports=[]).payload

    assert record["dissent"]["strongest_report_id"] is None
    assert record["dissent"]["report_count"] == 0


def test_a_dissent_round_is_deterministic_and_content_addressed() -> None:
    first = seal(reports=[report("MR-1", 0.9), report("MR-2", 0.2)])
    second = seal(reports=[report("MR-1", 0.9), report("MR-2", 0.2)])

    assert first.canonical_bytes == second.canonical_bytes
    assert (
        validate_cross_exam_round(ROOT, first.payload).canonical_bytes
        == first.canonical_bytes
    )
