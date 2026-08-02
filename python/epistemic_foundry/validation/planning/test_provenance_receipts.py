"""provenance_and_receipt_audit — a preregistration can prove itself.

A sealed plan is what a later execution will rest on, so the receipt has to
carry enough to re-derive that seal without this module: the cascade plan and
each register entry re-derive their own hashes, the plan re-derives the
preregistration hash it publishes, the receipt re-derives its own hash over
exactly the fields it publishes, and it binds both the manifest it was screened
against and the canonical vocabulary it ran under so a schema edit is visible
rather than silent.  The verifier re-derives the *derived* fields too, not only
the digests: an edit that moved a criterion and recomputed every hash would
still leave the rendered rule and the endpoint list disagreeing with the
register they claim to come from.

Nothing here carries a clock or a random draw: every id, timestamp and seed
comes from the caller, and the same arguments seal to byte-identical canonical
JSON.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from .contracts import (
    CASCADE_SCHEMA_PATH,
    FALSIFIER_SCHEMA_PATH,
    PLAN_SCHEMA_PATH,
    PREDICTION_SCHEMA_PATH,
    SCOPE_SCHEMA_PATH,
    TARGET_SCHEMA_PATH,
    digest,
    hash_excluding,
    verify_preregistration,
)
from .fixtures import (
    ROOT,
    amendment,
    plan_arguments,
    preregistration,
    target_manifest,
)


def canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def test_a_receipt_re_derives_its_own_hash() -> None:
    receipt = preregistration()

    assert receipt["receipt_hash"] == hash_excluding(receipt, "receipt_hash")


def test_the_cascade_and_register_entries_re_derive_their_hashes() -> None:
    receipt = preregistration()

    cascade = receipt["cascade_plan"]
    assert cascade["plan_hash"] == hash_excluding(cascade, "plan_hash")
    for entry in receipt["prediction_register"]:
        assert entry["entry_hash"] == hash_excluding(entry, "entry_hash")


def test_the_preregistration_hash_is_published_in_two_agreeing_places() -> None:
    receipt = preregistration()

    assert receipt["preregistration_hash"] == receipt["plan"]["preregistration_hash"]
    assert receipt["plan_hash"] == digest(receipt["plan"])


def test_a_receipt_binds_the_exact_manifest_it_screened() -> None:
    manifest = target_manifest()
    receipt = preregistration(target_manifest=manifest)

    assert receipt["target_manifest_hash"] == digest(manifest)
    assert receipt["eligibility_record"]["manifest_hash"] == digest(manifest)


def test_a_changed_manifest_changes_the_seal() -> None:
    first = preregistration()
    second = preregistration(
        target_manifest=target_manifest(version="1.4.1"),
        target_version="1.4.1",
    )

    assert first["target_manifest_hash"] != second["target_manifest_hash"]
    assert first["preregistration_hash"] != second["preregistration_hash"]


def test_a_changed_prediction_changes_the_seal() -> None:
    from .fixtures import falsification, prediction, predictions

    first = preregistration()
    moved = list(predictions())
    moved[0] = prediction(falsification=falsification(threshold=13.0))
    second = preregistration(predictions=moved)

    assert first["preregistration_hash"] != second["preregistration_hash"]


def test_the_receipt_binds_the_vocabulary_it_sealed_under(tmp_path: Path) -> None:
    schemas = tmp_path / "schemas"
    schemas.mkdir()
    for relative in (
        TARGET_SCHEMA_PATH,
        SCOPE_SCHEMA_PATH,
        PLAN_SCHEMA_PATH,
        CASCADE_SCHEMA_PATH,
        PREDICTION_SCHEMA_PATH,
        FALSIFIER_SCHEMA_PATH,
    ):
        shutil.copyfile(ROOT / relative, tmp_path / relative)
    edited = json.loads((tmp_path / PLAN_SCHEMA_PATH).read_text(encoding="utf-8"))
    edited["description"] = "an edited copy of the canonical validation plan"
    (tmp_path / PLAN_SCHEMA_PATH).write_text(
        json.dumps(edited, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    arguments = plan_arguments()
    reference_vocab = preregistration()["vocabulary_hash"]

    from .contracts import preregister_plan

    changed = preregister_plan(tmp_path, **arguments)

    assert changed["vocabulary_hash"] != reference_vocab


def test_the_same_arguments_seal_byte_identically() -> None:
    assert canonical(preregistration()) == canonical(preregistration())


def test_a_different_caller_supplied_identity_changes_only_that_field() -> None:
    first = preregistration()
    second = preregistration(receipt_id="VPREREG-V02-OTHER")

    assert first["plan"] == second["plan"]
    assert first["preregistration_hash"] == second["preregistration_hash"]
    assert first["receipt_hash"] != second["receipt_hash"]
    assert second["receipt_id"] == "VPREREG-V02-OTHER"


def test_a_tampered_receipt_hash_is_reported() -> None:
    receipt = preregistration()
    receipt["preregistered_at"] = "2099-01-01T00:00:00Z"

    assert "receipt_hash" in verify_preregistration(ROOT, receipt)


def test_a_moved_criterion_is_caught_even_if_every_hash_is_recomputed() -> None:
    receipt = preregistration()
    # Rewrite a rendered rule but leave the register it must derive from intact,
    # then recompute the plan and receipt hashes so only the derivation betrays
    # the edit.
    receipt["plan"]["falsification_rule"] = "the claim is falsified if it rains"
    receipt["plan_hash"] = digest(receipt["plan"])
    receipt["receipt_hash"] = hash_excluding(receipt, "receipt_hash")

    mismatches = verify_preregistration(ROOT, receipt)

    assert "falsification_rule" in mismatches


def test_a_dropped_receipt_field_is_reported_without_crashing() -> None:
    receipt = preregistration()
    del receipt["counts"]

    assert verify_preregistration(ROOT, receipt) == ["receipt_fields"]


def test_the_seal_binds_the_amendment_predecessor() -> None:
    first = preregistration()
    second = amendment(first)

    assert second["amends"] == first["preregistration_hash"]
    assert verify_preregistration(ROOT, second) == []
    assert second["preregistration_hash"] != first["preregistration_hash"]


def test_a_report_record_is_a_fresh_document() -> None:
    receipt = preregistration()
    receipt["prediction_register"][0]["prediction_id"] = "MUTATED"

    assert preregistration()["prediction_register"][0]["prediction_id"] == "PRED-V02-1"


def test_every_reason_that_could_be_reported_carries_its_declaration() -> None:
    from .contracts import FINDING_CODES

    assert all(len(reason) > 50 for reason in FINDING_CODES.values())
