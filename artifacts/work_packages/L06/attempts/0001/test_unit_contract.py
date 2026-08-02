"""unit_and_contract_tests — a deletion that can be answered for afterwards.

The happy paths are the ones a governed workspace takes: place a preservation
order and have it honoured, lift it under the authority that placed it, execute
a plan faithfully and have the execution verified against it, and audit a
sweep of executed plans by rebuilding the memory they left behind.

Each of the three gates is exercised where passing is the correct outcome,
because a gate that could only refuse would make an erasure obligation
unsatisfiable — which is its own kind of failure.
"""

from __future__ import annotations

from epistemic_foundry.memory.v4_l05 import LineageMemory, plan_forget
from epistemic_foundry.memory.v4_l06 import (
    LegalHoldRegister,
    audit_retention_sweep,
    hold_placement_hash,
    release_legal_hold,
    require_clean_sweep,
    require_forget_permitted,
    verify_deletion_execution,
    verify_plan_hash,
)
from fixtures import (
    ANOTHER_MEMORY_CLASS,
    A_MEMORY_CLASS,
    A_PROTECTED_CLASS,
    EXECUTED_AT,
    FORGET_AUTHORITY,
    HOLD_AUTHORITY,
    RECORDED_AT,
    VERIFIED_AT,
    archive_entry,
    chain_entries,
    chain_records,
    execution,
    forget_plan,
    hold,
    lineage_record,
    sweep_arguments,
)


def register(*records: dict) -> LegalHoldRegister:
    return LegalHoldRegister(list(records))


def verify(**overrides: object) -> dict:
    arguments: dict = {
        "plan": forget_plan(),
        "execution": execution(),
        "verified_at": VERIFIED_AT,
        "receipt_id": "EDX-L06-1",
    }
    arguments.update(overrides)
    return verify_deletion_execution(**arguments)


# --- legal hold -----------------------------------------------------------


def test_a_hold_records_its_scope_authority_and_hash() -> None:
    record = hold()

    assert record["hold_id"] == "LH-L06-1"
    assert record["held_candidate_ids"] == ["C4"]
    assert record["held_memory_classes"] == []
    assert record["hold_authority"] == HOLD_AUTHORITY
    assert record["placed_at"] == RECORDED_AT
    assert record["hold_hash"] == hold_placement_hash(record)


def test_a_hold_may_be_scoped_by_memory_class() -> None:
    record = hold(candidate_ids=[], memory_classes=[ANOTHER_MEMORY_CLASS])

    assert record["held_candidate_ids"] == []
    assert record["held_memory_classes"] == [ANOTHER_MEMORY_CLASS]


def test_a_hold_may_be_scoped_by_both_candidates_and_classes() -> None:
    record = hold(candidate_ids=["C4", "C3"], memory_classes=[A_MEMORY_CLASS])

    assert record["held_candidate_ids"] == ["C3", "C4"]
    assert record["held_memory_classes"] == [A_MEMORY_CLASS]


def test_placing_a_hold_is_deterministic() -> None:
    assert hold() == hold()


def test_the_register_reports_what_is_standing() -> None:
    holds = register(hold(), hold(hold_id="LH-L06-2", candidate_ids=["C1"]))

    assert holds.hold_ids() == ("LH-L06-1", "LH-L06-2")
    assert holds.standing_ids() == ("LH-L06-1", "LH-L06-2")
    assert holds.hold("LH-L06-2")["held_candidate_ids"] == ["C1"]


def test_the_register_names_which_hold_reaches_which_candidate() -> None:
    holds = register(hold(), hold(hold_id="LH-L06-2", candidate_ids=["C1", "C3"]))

    assert holds.covering(candidate_ids=["C1", "C4"]) == {
        "LH-L06-1": ("C4",),
        "LH-L06-2": ("C1",),
    }


def test_a_class_scoped_hold_reaches_candidates_of_that_class() -> None:
    holds = register(hold(candidate_ids=[], memory_classes=[A_MEMORY_CLASS]))

    covered = holds.covering(
        candidate_ids=["C1", "C2"],
        candidate_classes={"C1": A_MEMORY_CLASS, "C2": ANOTHER_MEMORY_CLASS},
    )
    assert covered == {"LH-L06-1": ("C1",)}


def test_a_hold_over_untouched_memory_does_not_block_a_forget() -> None:
    holds = register(hold(hold_id="LH-L06-9", candidate_ids=["C9"]))

    assert require_forget_permitted(plan=forget_plan(), register=holds) == ("LH-L06-9",)


def test_an_empty_register_permits_the_forget() -> None:
    assert require_forget_permitted(plan=forget_plan(), register=register()) == ()


def test_releasing_a_hold_records_the_authority_that_lifted_it() -> None:
    released = release_legal_hold(
        register=register(hold()),
        hold_id="LH-L06-1",
        authority=dict(HOLD_AUTHORITY),
        released_at=EXECUTED_AT,
    )

    assert released["released_at"] == EXECUTED_AT
    assert released["release_authority"] == HOLD_AUTHORITY
    assert released["hold_hash"] == hold_placement_hash(released)
    assert released["release_hash"].startswith("sha256:")


def test_a_released_hold_no_longer_stands() -> None:
    released = release_legal_hold(
        register=register(hold()),
        hold_id="LH-L06-1",
        authority=dict(HOLD_AUTHORITY),
        released_at=EXECUTED_AT,
    )
    holds = register(released)

    assert holds.hold_ids() == ("LH-L06-1",)
    assert holds.standing_ids() == ()
    assert holds.covering(candidate_ids=["C4"]) == {}


def test_a_forget_blocked_by_a_hold_proceeds_once_it_is_released() -> None:
    released = release_legal_hold(
        register=register(hold()),
        hold_id="LH-L06-1",
        authority=dict(HOLD_AUTHORITY),
        released_at=EXECUTED_AT,
    )

    assert (
        require_forget_permitted(plan=forget_plan(), register=register(released)) == ()
    )


def test_releasing_a_hold_is_deterministic() -> None:
    def lift() -> dict:
        return release_legal_hold(
            register=register(hold()),
            hold_id="LH-L06-1",
            authority=dict(HOLD_AUTHORITY),
            released_at=EXECUTED_AT,
        )

    assert lift() == lift()


# --- deletion execution ---------------------------------------------------


def test_the_plan_hash_re_derives_from_the_plan() -> None:
    plan = forget_plan()

    assert verify_plan_hash(plan) == plan["plan_hash"]


def test_a_faithful_execution_produces_a_receipt() -> None:
    receipt = verify()

    assert receipt["plan_id"] == "EFP-L06-1"
    assert receipt["erased"] == ["C3", "C4"]
    assert receipt["tombstoned"] == ["C1", "C2"]
    assert receipt["deferred"] == []
    assert receipt["executed_at"] == EXECUTED_AT
    assert receipt["verified_at"] == VERIFIED_AT


def test_the_receipt_counts_reconcile_with_the_plan() -> None:
    plan = forget_plan()
    receipt = verify(plan=plan)

    assert receipt["counts"] == {
        "deferred": 0,
        "erased": 2,
        "planned": 4,
        "tombstoned": 2,
    }
    assert receipt["counts"]["planned"] == (
        plan["counts"]["erased"] + plan["counts"]["tombstoned"]
    )


def test_a_deferred_erasure_with_a_recorded_reason_is_accepted() -> None:
    receipt = verify(
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

    assert receipt["erased"] == ["C3"]
    assert receipt["deferred"] == [
        {"candidate_id": "C4", "reason": "the store transaction was rolled back"}
    ]
    assert receipt["counts"] == {
        "deferred": 1,
        "erased": 1,
        "planned": 4,
        "tombstoned": 2,
    }


def test_a_tombstone_only_plan_executes_with_no_erasure() -> None:
    plan = forget_plan(candidate_ids=["C1"], plan_id="EFP-L06-T")
    receipt = verify(
        plan=plan,
        execution=execution(erased=[], tombstoned=["C1"]),
    )

    assert plan["erased"] == []
    assert receipt["tombstoned"] == ["C1"]
    assert receipt["counts"]["planned"] == 1


def test_a_leaf_only_plan_executes_as_a_plain_erasure() -> None:
    plan = forget_plan(candidate_ids=["C4"], plan_id="EFP-L06-L")
    receipt = verify(plan=plan, execution=execution(erased=["C4"], tombstoned=[]))

    assert receipt["erased"] == ["C4"]
    assert receipt["tombstoned"] == []


def test_the_receipt_records_which_holds_were_checked() -> None:
    holds = register(hold(hold_id="LH-L06-9", candidate_ids=["C9"]))
    receipt = verify(register=holds)

    assert receipt["hold_ids_checked"] == ["LH-L06-9"]


def test_the_receipt_is_deterministic() -> None:
    assert verify() == verify()


# --- retention sweep audit ------------------------------------------------


def test_a_healthy_sweep_reports_no_finding() -> None:
    report = audit_retention_sweep(**sweep_arguments())

    assert report["findings"] == []
    assert report["lineage_reconstructed"] is True
    require_clean_sweep(report)


def test_the_sweep_reconciles_what_survived_with_what_was_erased() -> None:
    report = audit_retention_sweep(**sweep_arguments())

    assert report["erased_candidates"] == ["C3", "C4"]
    assert report["surviving_candidates"] == ["C1", "C2"]
    assert report["counts"] == {
        "erased": 2,
        "findings": 0,
        "protected_tombstones": 1,
        "surviving": 2,
        "tombstoned": 2,
    }


def test_the_sweep_names_the_protected_tombstones_it_required() -> None:
    report = audit_retention_sweep(**sweep_arguments())

    assert report["protected_tombstones"] == ["C2"]
    assert report["plan_hashes"] == [forget_plan()["plan_hash"]]


def test_an_evictable_tombstone_is_not_required_to_survive() -> None:
    # Only protected knowledge must keep its tombstone facts; C1 was tombstoned
    # to protect ancestry, not because its class carries negative knowledge.
    plan = forget_plan()
    kept = [row for row in plan["tombstoned"] if row["candidate_id"] == "C2"]
    report = audit_retention_sweep(**sweep_arguments(tombstones=kept))

    assert [row["entry_class"] for row in kept] == [A_PROTECTED_CLASS]
    assert report["findings"] == []


def test_a_sweep_over_several_plans_reconciles_all_of_them() -> None:
    first = forget_plan(candidate_ids=["C4"], plan_id="EFP-L06-A")
    second = plan_forget(
        entries=chain_entries()[:3],
        lineage=LineageMemory(chain_records()[:3]),
        candidate_ids=["C3"],
        authority=dict(FORGET_AUTHORITY),
        requested_at=RECORDED_AT,
        plan_id="EFP-L06-B",
    )
    report = audit_retention_sweep(
        **sweep_arguments(
            entries=[
                archive_entry("C1", "elite"),
                archive_entry("C2", A_PROTECTED_CLASS),
            ],
            executed_plans=[first, second],
            tombstones=[],
        )
    )

    assert report["erased_candidates"] == ["C3", "C4"]
    assert report["findings"] == []
    require_clean_sweep(report)


def test_a_sweep_that_erased_nothing_is_clean() -> None:
    report = audit_retention_sweep(
        **sweep_arguments(
            entries=chain_entries(),
            lineage_records=chain_records(),
            executed_plans=[],
            tombstones=[],
        )
    )

    assert report["erased_candidates"] == []
    assert report["surviving_candidates"] == ["C1", "C2", "C3", "C4"]
    require_clean_sweep(report)


def test_the_sweep_report_is_deterministic() -> None:
    assert audit_retention_sweep(**sweep_arguments()) == audit_retention_sweep(
        **sweep_arguments()
    )


def test_the_lineage_the_sweep_rebuilds_is_the_engines_own() -> None:
    # The audit's checker is L05's construction, so the surviving records must
    # be walkable by that memory and not merely by this gate's own reading.
    memory = LineageMemory(sweep_arguments()["lineage_records"])

    assert memory.candidates() == ("C1", "C2")
    assert memory.ancestors_of("C2") == ("C1",)
    assert lineage_record("C2", ["C1"], 2)["parent_ids"] == ["C1"]


def test_the_whole_pipeline_runs_end_to_end() -> None:
    plan = forget_plan()
    holds = register(hold(hold_id="LH-L06-9", candidate_ids=["C9"]))
    receipt = verify_deletion_execution(
        plan=plan,
        execution=execution(),
        verified_at=VERIFIED_AT,
        register=holds,
        receipt_id="EDX-L06-E2E",
    )
    report = audit_retention_sweep(**sweep_arguments(executed_plans=[plan]))

    assert receipt["plan_hash"] == plan["plan_hash"] == report["plan_hashes"][0]
    require_clean_sweep(report)
