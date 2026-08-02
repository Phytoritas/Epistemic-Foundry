"""provenance_and_receipt_audit — an eligibility report can prove itself.

A screening decision is what a later validation plan will rest on, so the
report has to carry enough to re-derive that decision without this module: each
record binds the exact manifest it screened by digest and re-derives its own
hash, the report re-derives its own hash over exactly the fields it publishes,
and both bind the canonical vocabulary they ran under so a schema edit is
visible rather than silent.

Nothing here carries a clock or a random draw: every id and timestamp comes
from the caller, and the same target set screened twice produces byte-identical
canonical JSON.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from .contracts import (
    SCOPE_SCHEMA_PATH,
    TARGET_SCHEMA_PATH,
    build_eligibility_report,
    digest,
    hash_excluding,
    screen_target,
)
from .fixtures import REPORT_ID, ROOT, SCREENED_AT, empty_scope, target_manifest


def report(*manifests: object, **overrides: str) -> dict:
    arguments = {"report_id": REPORT_ID, "screened_at": SCREENED_AT}
    arguments.update(overrides)
    return build_eligibility_report(ROOT, list(manifests), **arguments)


def canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def test_a_record_re_derives_its_own_hash() -> None:
    record = screen_target(ROOT, target_manifest())

    assert record["record_hash"] == hash_excluding(record, "record_hash")


def test_a_report_re_derives_its_own_hash() -> None:
    result = report(target_manifest())

    assert result["report_hash"] == hash_excluding(result, "report_hash")


def test_a_record_binds_the_exact_manifest_it_screened() -> None:
    manifest = target_manifest()
    record = screen_target(ROOT, manifest)

    assert record["manifest_hash"] == digest(manifest)


def test_a_changed_manifest_changes_the_record_and_the_report_hash() -> None:
    first = report(target_manifest())
    second = report(target_manifest(version="1.4.1"))

    assert first["records"][0]["manifest_hash"] != second["records"][0]["manifest_hash"]
    assert first["records"][0]["record_hash"] != second["records"][0]["record_hash"]
    assert first["report_hash"] != second["report_hash"]


def test_an_ineligible_outcome_changes_the_record_hash() -> None:
    eligible = screen_target(ROOT, target_manifest())
    ineligible = screen_target(ROOT, target_manifest(validation_scope=empty_scope()))

    assert eligible["record_hash"] != ineligible["record_hash"]
    assert ineligible["reason_codes"] == ["SCOPE_VACUOUS"]


def test_the_report_binds_the_vocabulary_it_screened_under(tmp_path: Path) -> None:
    schemas = tmp_path / "schemas"
    schemas.mkdir()
    for relative in (TARGET_SCHEMA_PATH, SCOPE_SCHEMA_PATH):
        shutil.copyfile(ROOT / relative, tmp_path / relative)
    scope = json.loads((tmp_path / SCOPE_SCHEMA_PATH).read_text(encoding="utf-8"))
    scope["description"] = "an edited copy of the canonical scope vector"
    (tmp_path / SCOPE_SCHEMA_PATH).write_text(
        json.dumps(scope, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    edited = build_eligibility_report(
        tmp_path,
        [target_manifest()],
        report_id=REPORT_ID,
        screened_at=SCREENED_AT,
    )

    assert edited["vocabulary_hash"] != report(target_manifest())["vocabulary_hash"]
    assert edited["counts"]["eligible"] == 1


def test_the_same_target_set_screened_twice_is_byte_identical() -> None:
    manifests = [target_manifest(), target_manifest(target_id="vt-second")]

    assert canonical(report(*manifests)) == canonical(report(*manifests))


def test_a_different_caller_supplied_identity_changes_only_that_field() -> None:
    first = report(target_manifest())
    second = report(target_manifest(), report_id="VTER-V01-2")

    assert first["records"] == second["records"]
    assert first["report_hash"] != second["report_hash"]
    assert second["report_id"] == "VTER-V01-2"


def test_the_reason_totals_reconcile_with_the_records() -> None:
    result = report(
        target_manifest(),
        target_manifest(target_id="vt-no-action", supported_actions=[]),
        target_manifest(target_id="vt-no-scope", validation_scope=empty_scope()),
        target_manifest(
            target_id="vt-unapproved",
            safety_class="high_risk",
            approval_policy="none",
            supported_actions=[],
        ),
    )

    counted: dict[str, int] = {}
    for record in result["records"]:
        for code in record["reason_codes"]:
            counted[code] = counted.get(code, 0) + 1

    assert result["reason_totals"] == counted
    assert result["counts"] == {"eligible": 1, "ineligible": 3, "screened": 4}
    assert result["eligible_target_ids"] == ["vt-reservoir-sim"]


def test_every_reported_code_carries_the_reason_that_declares_it() -> None:
    result = report(target_manifest(target_id="vt-no-action", supported_actions=[]))
    record = result["records"][0]

    assert set(record["reasons"]) == set(record["reason_codes"])
    for reason in record["reasons"].values():
        assert len(reason) > 50


def test_screening_does_not_mutate_the_manifests_it_was_handed() -> None:
    manifests = [target_manifest(), target_manifest(target_id="vt-second")]
    before = [digest(manifest) for manifest in manifests]

    report(*manifests)

    assert [digest(manifest) for manifest in manifests] == before


def test_a_report_record_is_a_fresh_document() -> None:
    result = report(target_manifest())
    result["records"][0]["reason_codes"].append("MUTATED")

    assert report(target_manifest())["records"][0]["reason_codes"] == []
