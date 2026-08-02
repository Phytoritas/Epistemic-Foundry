"""provenance_and_receipt_audit — the gate can prove what it verified.

A deletion cannot be re-derived once it has happened, so the records around it
have to be: every hold, receipt and audit report re-derives its own digest from
exactly the fields it publishes, binds the plan it acted on by hash, and
carries only times the caller supplied.  The source is scanned for a clock and
for randomness because a receipt that quietly stamped itself would replay
differently every time it was checked.

Nothing here mutates its inputs either: a gate that edited the plan or the
execution report it was handed would be verifying a record only it could see.
"""

from __future__ import annotations

import ast
import copy
import json
from pathlib import Path

from epistemic_foundry.domain.hashing import hash_excluding
from epistemic_foundry.memory.v4_l06 import (
    HOLD_PLACEMENT_FIELDS,
    LegalHoldRegister,
    audit_retention_sweep,
    hold_placement_hash,
    place_legal_hold,
    release_legal_hold,
    verify_deletion_execution,
)
from fixtures import (
    EXECUTED_AT,
    HOLD_AUTHORITY,
    RECORDED_AT,
    VERIFIED_AT,
    execution,
    forget_plan,
    hold,
    sweep_arguments,
)

ROOT = Path(__file__).resolve().parents[5]
ENGINE = ROOT / "src/epistemic_foundry/memory/v4_l06/gate.py"


def receipt(**overrides: object) -> dict:
    arguments: dict = {
        "plan": forget_plan(),
        "execution": execution(),
        "verified_at": VERIFIED_AT,
        "receipt_id": "EDX-L06-P",
    }
    arguments.update(overrides)
    return verify_deletion_execution(**arguments)


def released_hold() -> dict:
    return release_legal_hold(
        register=LegalHoldRegister([hold()]),
        hold_id="LH-L06-1",
        authority=dict(HOLD_AUTHORITY),
        released_at=EXECUTED_AT,
    )


# --- digests re-derive ----------------------------------------------------


def test_the_hold_digest_re_derives_from_the_fields_it_covers() -> None:
    record = hold()
    placement = {field: record[field] for field in HOLD_PLACEMENT_FIELDS}

    assert record["hold_hash"] == hash_excluding(placement, "hold_hash")
    assert record["hold_hash"] == hold_placement_hash(record)


def test_the_release_digest_re_derives_and_leaves_the_placement_intact() -> None:
    record = released_hold()

    assert record["release_hash"] == hash_excluding(record, "release_hash")
    assert record["hold_hash"] == hold_placement_hash(record)


def test_a_release_can_be_verified_without_the_register_that_produced_it() -> None:
    record = released_hold()
    rebuilt = {key: value for key, value in record.items() if key != "release_hash"}

    assert hash_excluding(rebuilt, "release_hash") == record["release_hash"]


def test_the_execution_receipt_re_derives_its_own_hash() -> None:
    record = receipt()
    rebuilt = {key: value for key, value in record.items() if key != "receipt_hash"}

    assert hash_excluding(rebuilt, "receipt_hash") == record["receipt_hash"]


def test_the_receipt_binds_the_plan_it_verified_by_hash() -> None:
    plan = forget_plan()
    record = receipt(plan=plan)

    assert record["plan_hash"] == plan["plan_hash"]
    assert record["plan_id"] == plan["plan_id"]


def test_a_different_plan_produces_a_different_receipt_hash() -> None:
    first = receipt()
    second = receipt(
        plan=forget_plan(candidate_ids=["C4"], plan_id="EFP-L06-ALT"),
        execution=execution(erased=["C4"], tombstoned=[]),
    )

    assert first["receipt_hash"] != second["receipt_hash"]


def test_the_sweep_report_re_derives_its_own_hash() -> None:
    report = audit_retention_sweep(**sweep_arguments())
    rebuilt = {key: value for key, value in report.items() if key != "audit_hash"}

    assert hash_excluding(rebuilt, "audit_hash") == report["audit_hash"]


def test_the_sweep_report_names_every_plan_hash_it_audited() -> None:
    plan = forget_plan()
    report = audit_retention_sweep(**sweep_arguments(executed_plans=[plan]))

    assert report["plan_hashes"] == [plan["plan_hash"]]


def test_a_finding_changes_the_audit_hash() -> None:
    clean = audit_retention_sweep(**sweep_arguments())
    broken = audit_retention_sweep(**sweep_arguments(tombstones=[]))

    assert clean["audit_hash"] != broken["audit_hash"]


# --- every record is evidence ---------------------------------------------


def test_every_record_is_serialisable_evidence() -> None:
    for record in (
        hold(),
        released_hold(),
        receipt(),
        audit_retention_sweep(**sweep_arguments()),
        audit_retention_sweep(**sweep_arguments(tombstones=[])),
    ):
        assert json.loads(json.dumps(record, ensure_ascii=False, sort_keys=True)) == (
            record
        )


def test_a_broken_sweep_carries_the_upstream_finding_as_evidence() -> None:
    from fixtures import lineage_record

    report = audit_retention_sweep(
        **sweep_arguments(
            lineage_records=[
                lineage_record("C1", [], 1),
                lineage_record("C2", ["C1"], 2),
                lineage_record("C4", ["C3"], 4),
            ]
        )
    )
    finding = report["findings"][0]

    assert finding["upstream_code"] == "LINEAGE_BROKEN"
    assert finding["upstream_context"]["unknown_parents"] == ["C3"]
    assert json.loads(json.dumps(report, sort_keys=True)) == report


def test_the_receipt_records_the_reason_a_planned_erasure_was_deferred() -> None:
    record = receipt(
        execution=execution(
            erased=["C3"],
            not_executed=[
                {
                    "candidate_id": "C4",
                    "reason": "the store transaction was rolled back",
                }
            ],
        )
    )

    assert record["deferred"] == [
        {"candidate_id": "C4", "reason": "the store transaction was rolled back"}
    ]


# --- determinism and non-mutation -----------------------------------------


def test_the_gate_carries_no_clock_and_no_randomness() -> None:
    source = ENGINE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }

    assert "utc_now_iso" not in called
    assert "utc_now_iso" not in imported
    for banned in ("datetime", "time.time", "random", "secrets", "uuid"):
        assert banned not in source, banned


def test_the_only_unsupplied_value_is_a_minted_id() -> None:
    # `new_id` is the one non-deterministic call, and every record accepts a
    # caller-supplied id so a replay can pin it.
    first = receipt()
    second = receipt()
    minted = verify_deletion_execution(
        plan=forget_plan(), execution=execution(), verified_at=VERIFIED_AT
    )

    assert first == second
    assert minted["receipt_id"] != first["receipt_id"]
    assert minted["plan_hash"] == first["plan_hash"]


def test_placing_a_hold_does_not_mutate_its_authority() -> None:
    authority = dict(HOLD_AUTHORITY)
    before = copy.deepcopy(authority)
    candidates = ["C4", "C3"]

    place_legal_hold(
        hold_id="LH-M",
        authority=authority,
        placed_at=RECORDED_AT,
        candidate_ids=candidates,
    )
    assert authority == before
    assert candidates == ["C4", "C3"]


def test_verifying_an_execution_does_not_mutate_the_plan_or_the_report() -> None:
    plan = forget_plan()
    report = execution()
    before = (copy.deepcopy(plan), copy.deepcopy(report))

    verify_deletion_execution(
        plan=plan, execution=report, verified_at=VERIFIED_AT, receipt_id="EDX-M"
    )
    assert (plan, report) == before


def test_auditing_a_sweep_does_not_mutate_its_inputs() -> None:
    arguments = sweep_arguments()
    before = copy.deepcopy(arguments)

    audit_retention_sweep(**arguments)
    assert arguments == before


def test_releasing_a_hold_does_not_mutate_the_placed_record() -> None:
    placed = hold()
    before = copy.deepcopy(placed)
    holds = LegalHoldRegister([placed])

    release_legal_hold(
        register=holds,
        hold_id="LH-L06-1",
        authority=dict(HOLD_AUTHORITY),
        released_at=EXECUTED_AT,
    )
    assert placed == before
    assert holds.standing_ids() == ("LH-L06-1",)


def test_the_register_hands_out_copies_rather_than_its_own_records() -> None:
    holds = LegalHoldRegister([hold()])
    taken = holds.hold("LH-L06-1")
    taken["held_candidate_ids"] = []

    assert holds.hold("LH-L06-1")["held_candidate_ids"] == ["C4"]
    assert holds.standing()[0]["held_candidate_ids"] == ["C4"]
