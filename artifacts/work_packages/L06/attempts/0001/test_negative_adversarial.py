"""negative_and_adversarial_tests — every way a deletion can lie, refused.

A deletion is the effect that cannot be re-derived, so the attacks staged here
are the ones that would leave no trace: a regulated erasure executed straight
through a preservation order, a runtime that reports more destruction than the
plan authorised, a runtime that reports the plan finished when it did not, a
sweep whose survivors can no longer be assembled into an ancestry, and a
protected tombstone quietly emptied of the facts it existed to keep.

Each input is wrong in exactly one way and must be refused by its own code.
"""

from __future__ import annotations

import pytest

from epistemic_foundry.domain.hashing import hash_excluding
from epistemic_foundry.memory.v4_l05 import EvolutionMemoryError, LineageMemory
from epistemic_foundry.memory.v4_l06 import (
    LegalHoldRegister,
    MemoryGateError,
    audit_retention_sweep,
    place_legal_hold,
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
    OTHER_MATTER_AUTHORITY,
    RECORDED_AT,
    REGULATED_ERASURE,
    VERIFIED_AT,
    archive_entry,
    chain_records,
    execution,
    forged_plan,
    forget_plan,
    hold,
    lineage_record,
    sweep_arguments,
    tombstone,
)


def register(*records: dict) -> LegalHoldRegister:
    return LegalHoldRegister(list(records))


def refused(**overrides: object) -> MemoryGateError:
    arguments: dict = {
        "plan": forget_plan(),
        "execution": execution(),
        "verified_at": VERIFIED_AT,
        "receipt_id": "EDX-L06-N",
    }
    arguments.update(overrides)
    with pytest.raises(MemoryGateError) as caught:
        verify_deletion_execution(**arguments)
    return caught.value


# --- legal hold outranks every ground -------------------------------------


def test_a_hold_refuses_a_forget_that_would_erase_held_memory() -> None:
    holds = register(hold(candidate_ids=["C4"]))

    with pytest.raises(MemoryGateError) as caught:
        require_forget_permitted(plan=forget_plan(), register=holds)
    assert caught.value.code == "LEGAL_HOLD_ACTIVE"
    assert caught.value.context["hold_id"] == "LH-L06-1"
    assert caught.value.context["conflicts"] == {"LH-L06-1": ["C4"]}


def test_a_hold_refuses_a_forget_that_would_only_tombstone_held_memory() -> None:
    # A tombstone is not an erasure, but it still destroys the payload, so a
    # preservation order reaches it too.
    holds = register(hold(candidate_ids=["C2"]))

    with pytest.raises(MemoryGateError) as caught:
        require_forget_permitted(plan=forget_plan(), register=holds)
    assert caught.value.code == "LEGAL_HOLD_ACTIVE"
    assert caught.value.context["conflicts"] == {"LH-L06-1": ["C2"]}


def test_a_hold_outranks_a_regulated_erasure_being_executed() -> None:
    plan = forget_plan(
        authority={**FORGET_AUTHORITY, "ground": REGULATED_ERASURE},
        plan_id="EFP-L06-REG",
    )
    holds = register(hold(candidate_ids=["C4"]))

    with pytest.raises(MemoryGateError) as caught:
        require_forget_permitted(plan=plan, register=holds)
    assert caught.value.code == "LEGAL_HOLD_ACTIVE"
    assert caught.value.context["forget_ground"] == REGULATED_ERASURE


@pytest.mark.parametrize("ground", ["capacity_pressure", "consent_withdrawal"])
def test_no_forget_ground_survives_a_standing_hold(ground: str) -> None:
    plan = forget_plan(
        candidate_ids=["C4"],
        authority={**FORGET_AUTHORITY, "ground": ground},
        plan_id="EFP-L06-G",
    )
    holds = register(hold(candidate_ids=["C4"]))

    with pytest.raises(MemoryGateError) as caught:
        require_forget_permitted(plan=plan, register=holds)
    assert caught.value.code == "LEGAL_HOLD_ACTIVE"


def test_a_class_scoped_hold_refuses_a_forget_of_that_class() -> None:
    holds = register(hold(candidate_ids=[], memory_classes=[A_MEMORY_CLASS]))

    with pytest.raises(MemoryGateError) as caught:
        require_forget_permitted(
            plan=forget_plan(),
            register=holds,
            candidate_classes={
                "C1": ANOTHER_MEMORY_CLASS,
                "C2": ANOTHER_MEMORY_CLASS,
                "C3": ANOTHER_MEMORY_CLASS,
                "C4": A_MEMORY_CLASS,
            },
        )
    assert caught.value.code == "LEGAL_HOLD_ACTIVE"
    assert caught.value.context["conflicts"] == {"LH-L06-1": ["C4"]}


def test_an_undeclared_memory_class_fails_closed_under_a_class_hold() -> None:
    # Assuming unclassified memory falls outside a class-scoped hold is exactly
    # the assumption that erases held memory.
    holds = register(hold(candidate_ids=[], memory_classes=[A_MEMORY_CLASS]))

    with pytest.raises(MemoryGateError) as caught:
        require_forget_permitted(plan=forget_plan(), register=holds)
    assert caught.value.code == "INPUT_INVALID"
    assert caught.value.context["undeclared"] == ["C1", "C2", "C3", "C4"]


def test_the_deletion_gate_refuses_while_the_hold_stands() -> None:
    error = refused(register=register(hold(candidate_ids=["C3"])))

    assert error.code == "LEGAL_HOLD_ACTIVE"


# --- hold placement and release -------------------------------------------


@pytest.mark.parametrize(
    "field", ["approved_by", "hold_authority_id", "legal_matter_id"]
)
def test_placing_a_hold_without_full_authority_is_refused(field: str) -> None:
    authority = {key: value for key, value in HOLD_AUTHORITY.items() if key != field}

    with pytest.raises(MemoryGateError) as caught:
        place_legal_hold(
            hold_id="LH-X",
            authority=authority,
            placed_at=RECORDED_AT,
            candidate_ids=["C4"],
        )
    assert caught.value.code == "HOLD_AUTHORITY_MISSING"
    assert caught.value.context["missing"] == [field]


@pytest.mark.parametrize(
    "field", ["approved_by", "hold_authority_id", "legal_matter_id"]
)
def test_releasing_a_hold_needs_the_same_authority_shape(field: str) -> None:
    authority = {key: value for key, value in HOLD_AUTHORITY.items() if key != field}

    with pytest.raises(MemoryGateError) as caught:
        release_legal_hold(
            register=register(hold()),
            hold_id="LH-L06-1",
            authority=authority,
            released_at=EXECUTED_AT,
        )
    assert caught.value.code == "HOLD_AUTHORITY_MISSING"
    assert caught.value.context["missing"] == [field]


def test_releasing_a_hold_under_another_matter_is_refused() -> None:
    with pytest.raises(MemoryGateError) as caught:
        release_legal_hold(
            register=register(hold()),
            hold_id="LH-L06-1",
            authority=dict(OTHER_MATTER_AUTHORITY),
            released_at=EXECUTED_AT,
        )
    assert caught.value.code == "HOLD_AUTHORITY_MISMATCHED"
    assert caught.value.context["placed_under"] == HOLD_AUTHORITY["legal_matter_id"]


def test_releasing_a_hold_that_was_never_placed_is_refused() -> None:
    with pytest.raises(MemoryGateError) as caught:
        release_legal_hold(
            register=register(hold()),
            hold_id="LH-NOT-PLACED",
            authority=dict(HOLD_AUTHORITY),
            released_at=EXECUTED_AT,
        )
    assert caught.value.code == "HOLD_UNKNOWN"
    assert caught.value.context["known"] == ["LH-L06-1"]


def test_releasing_an_empty_register_is_refused() -> None:
    with pytest.raises(MemoryGateError) as caught:
        release_legal_hold(
            register=register(),
            hold_id="LH-L06-1",
            authority=dict(HOLD_AUTHORITY),
            released_at=EXECUTED_AT,
        )
    assert caught.value.code == "HOLD_UNKNOWN"


def test_releasing_a_hold_twice_is_refused() -> None:
    released = release_legal_hold(
        register=register(hold()),
        hold_id="LH-L06-1",
        authority=dict(HOLD_AUTHORITY),
        released_at=EXECUTED_AT,
    )

    with pytest.raises(MemoryGateError) as caught:
        release_legal_hold(
            register=register(released),
            hold_id="LH-L06-1",
            authority=dict(HOLD_AUTHORITY),
            released_at=VERIFIED_AT,
        )
    assert caught.value.code == "HOLD_RELEASED_ALREADY"


def test_a_hold_that_names_nothing_is_refused() -> None:
    with pytest.raises(MemoryGateError) as caught:
        place_legal_hold(
            hold_id="LH-EMPTY", authority=dict(HOLD_AUTHORITY), placed_at=RECORDED_AT
        )
    assert caught.value.code == "HOLD_SCOPE_EMPTY"


def test_a_hold_naming_an_unknown_memory_class_is_refused() -> None:
    with pytest.raises(MemoryGateError) as caught:
        place_legal_hold(
            hold_id="LH-X",
            authority=dict(HOLD_AUTHORITY),
            placed_at=RECORDED_AT,
            memory_classes=["CONFIDENTIAL"],
        )
    assert caught.value.code == "INPUT_INVALID"
    assert caught.value.context["unknown"] == ["CONFIDENTIAL"]


def test_two_holds_under_one_id_are_refused() -> None:
    with pytest.raises(MemoryGateError) as caught:
        register(hold(), hold(candidate_ids=["C1"]))
    assert caught.value.code == "HOLD_DUPLICATED"


def test_a_hold_whose_scope_was_edited_after_placement_is_refused() -> None:
    # Widening or narrowing a hold in place is the one edit that could quietly
    # change what a deletion may touch, so the digest is re-derived.
    tampered = {**hold(), "held_candidate_ids": []}

    with pytest.raises(MemoryGateError) as caught:
        register(tampered)
    assert caught.value.code == "INPUT_INVALID"
    assert caught.value.context["hold_id"] == "LH-L06-1"


def test_a_hold_record_missing_a_placement_field_is_refused() -> None:
    partial = {key: value for key, value in hold().items() if key != "placed_at"}

    with pytest.raises(MemoryGateError) as caught:
        register(partial)
    assert caught.value.code == "INPUT_INVALID"
    assert caught.value.context["missing"] == ["placed_at"]


# --- deletion execution divergence ----------------------------------------


def test_an_erasure_the_plan_never_authorised_is_refused() -> None:
    error = refused(execution=execution(erased=["C3", "C4", "C9"]))

    assert error.code == "DELETION_UNPLANNED"
    assert error.context["erased_without_plan"] == ["C9"]


def test_tombstoning_memory_the_plan_never_named_is_refused() -> None:
    error = refused(execution=execution(tombstoned=["C1", "C2", "C9"]))

    assert error.code == "DELETION_UNPLANNED"
    assert error.context["tombstoned_without_plan"] == ["C9"]


def test_erasing_what_the_plan_only_authorised_tombstoning_is_refused() -> None:
    error = refused(execution=execution(erased=["C2", "C3", "C4"], tombstoned=["C1"]))

    assert error.code == "DELETION_UNPLANNED"
    assert error.context["erased_without_plan"] == ["C2"]


def test_a_planned_erasure_left_undone_without_a_reason_is_refused() -> None:
    error = refused(execution=execution(erased=["C3"]))

    assert error.code == "DELETION_INCOMPLETE"
    assert error.context["unfinished_erasures"] == ["C4"]


def test_a_planned_tombstone_left_undone_without_a_reason_is_refused() -> None:
    error = refused(execution=execution(tombstoned=["C1"]))

    assert error.code == "DELETION_INCOMPLETE"
    assert error.context["unfinished_tombstones"] == ["C2"]


def test_a_blank_reason_does_not_count_as_a_recorded_reason() -> None:
    error = refused(
        execution=execution(
            erased=["C3"], not_executed=[{"candidate_id": "C4", "reason": "   "}]
        )
    )

    assert error.code == "DELETION_INCOMPLETE"
    assert error.context["incomplete"] == ["C4"]


def test_an_execution_reporting_nothing_at_all_is_refused() -> None:
    error = refused(execution=execution(erased=[], tombstoned=[]))

    assert error.code == "DELETION_INCOMPLETE"
    assert error.context["incomplete"] == ["C1", "C2", "C3", "C4"]


def test_deferring_a_candidate_the_plan_never_named_is_refused() -> None:
    error = refused(
        execution=execution(
            not_executed=[{"candidate_id": "C9", "reason": "a plausible sounding note"}]
        )
    )

    assert error.code == "INPUT_INVALID"
    assert error.context["candidate_id"] == "C9"


def test_acting_on_and_deferring_the_same_candidate_is_refused() -> None:
    error = refused(
        execution=execution(
            not_executed=[{"candidate_id": "C4", "reason": "left for the next window"}]
        )
    )

    assert error.code == "INPUT_INVALID"
    assert error.context["contradicted"] == ["C4"]


def test_the_same_candidate_reported_under_two_outcomes_is_refused() -> None:
    error = refused(execution=execution(tombstoned=["C1", "C2", "C3"]))

    assert error.code == "INPUT_INVALID"
    assert error.context["overlap"] == ["C3"]


def test_a_duplicated_erasure_in_the_report_is_refused() -> None:
    error = refused(execution=execution(erased=["C3", "C4", "C4"]))

    assert error.code == "INPUT_INVALID"
    assert error.context["duplicate"] == "C4"


def test_an_execution_without_a_recorded_time_is_refused() -> None:
    report = {key: value for key, value in execution().items() if key != "executed_at"}
    error = refused(execution=report)

    assert error.code == "INPUT_INVALID"
    assert error.context["label"] == "execution.executed_at"


def test_a_plan_edited_after_it_was_decided_is_refused() -> None:
    tampered = {**forget_plan(), "erased": ["C1", "C2", "C3", "C4"]}

    with pytest.raises(MemoryGateError) as caught:
        verify_plan_hash(tampered)
    assert caught.value.code == "PLAN_HASH_MISMATCH"
    assert caught.value.context["plan_id"] == "EFP-L06-1"


def test_the_deletion_gate_refuses_a_plan_that_does_not_re_derive() -> None:
    error = refused(plan={**forget_plan(), "erased": ["C4"]})

    assert error.code == "PLAN_HASH_MISMATCH"


def test_a_plan_giving_one_candidate_two_outcomes_is_refused() -> None:
    plan = forged_plan(
        erased=["C3"], tombstoned=[tombstone("C3", A_PROTECTED_CLASS, "X")]
    )
    error = refused(plan=plan)

    assert error.code == "EXECUTION_COUNTS_UNRECONCILED"
    assert error.context["overlap"] == ["C3"]


def test_a_plan_whose_stated_counts_do_not_match_its_lists_is_refused() -> None:
    plan = forged_plan(erased=["C4"])
    plan["counts"]["erased"] = 5
    plan["plan_hash"] = hash_excluding(plan, "plan_hash")
    error = refused(plan=plan)

    assert error.code == "EXECUTION_COUNTS_UNRECONCILED"
    assert error.context["stated"]["erased"] == 5
    assert error.context["listed"]["erased"] == 1


def test_a_plan_whose_counts_are_not_integers_is_refused() -> None:
    plan = forged_plan(erased=["C4"])
    plan["counts"]["erased"] = "1"
    plan["plan_hash"] = hash_excluding(plan, "plan_hash")
    error = refused(plan=plan)

    assert error.code == "INPUT_INVALID"
    assert error.context["field"] == "erased"


def test_a_plan_carrying_refusals_is_not_executable_at_all() -> None:
    # L05 decided one candidate may not be forgotten; executing the rest anyway
    # would act on a plan whose own engine refused it.
    plan = forget_plan(candidate_ids=["C4", "C9"], plan_id="EFP-L06-R")
    error = refused(plan=plan)

    assert plan["refusals"][0]["code"] == "CANDIDATE_UNKNOWN"
    assert error.code == "UPSTREAM_MEMORY_REFUSED"
    assert error.context["upstream_code"] == "CANDIDATE_UNKNOWN"
    assert isinstance(error.__cause__, EvolutionMemoryError)


def test_a_capacity_forget_of_protected_memory_is_refused_upstream() -> None:
    plan = forget_plan(
        authority={**FORGET_AUTHORITY, "ground": "capacity_pressure"},
        plan_id="EFP-L06-CAP",
    )
    error = refused(plan=plan)

    assert error.code == "UPSTREAM_MEMORY_REFUSED"
    assert error.context["upstream_code"] == "PROTECTED_MEMORY_ERASED"


# --- retention sweep audit ------------------------------------------------


def test_a_sweep_whose_lineage_cannot_be_rebuilt_reports_that_failure() -> None:
    # C3 was erased but C4's record survived, so the ancestry it names is gone.
    report = audit_retention_sweep(
        **sweep_arguments(
            lineage_records=[
                lineage_record("C1", [], 1),
                lineage_record("C2", ["C1"], 2),
                lineage_record("C4", ["C3"], 4),
            ]
        )
    )

    assert report["lineage_reconstructed"] is False
    codes = [row["code"] for row in report["findings"]]
    assert "RETENTION_SWEEP_BROKEN" in codes
    broken = next(
        row for row in report["findings"] if row["code"] == "RETENTION_SWEEP_BROKEN"
    )
    assert broken["upstream_code"] == "LINEAGE_BROKEN"

    with pytest.raises(MemoryGateError) as caught:
        require_clean_sweep(report)
    assert caught.value.code in set(codes)


def test_an_erased_candidate_that_still_holds_memory_is_a_finding() -> None:
    report = audit_retention_sweep(
        **sweep_arguments(lineage_records=chain_records()[:3])
    )

    finding = next(
        row for row in report["findings"] if row["code"] == "ERASED_MEMORY_RETAINED"
    )
    assert finding["candidate_id"] == "C3"
    assert finding["in_lineage"] is True
    assert finding["in_archive"] is False


def test_an_erased_candidate_still_in_the_archive_is_a_finding() -> None:
    report = audit_retention_sweep(
        **sweep_arguments(entries=[archive_entry("C4", "superseded")])
    )

    finding = next(
        row for row in report["findings"] if row["code"] == "ERASED_MEMORY_RETAINED"
    )
    assert finding["candidate_id"] == "C4"
    assert finding["in_archive"] is True


def test_a_lineage_record_naming_an_erased_ancestor_is_a_finding() -> None:
    # A forged plan erased the root while its descendants survived; L05 would
    # have tombstoned it, and this is the audit that notices it did not.
    report = audit_retention_sweep(
        **sweep_arguments(
            lineage_records=chain_records(),
            executed_plans=[forged_plan(erased=["C1"])],
            tombstones=[],
        )
    )

    orphaned = sorted(
        row["candidate_id"]
        for row in report["findings"]
        if row["code"] == "ERASED_ANCESTOR_REFERENCED"
    )
    assert orphaned == ["C2", "C3", "C4"]
    assert all(
        row["ancestor_id"] == "C1"
        for row in report["findings"]
        if row["code"] == "ERASED_ANCESTOR_REFERENCED"
    )


def test_a_protected_tombstone_missing_from_the_ledger_is_a_finding() -> None:
    report = audit_retention_sweep(**sweep_arguments(tombstones=[]))

    finding = next(
        row for row in report["findings"] if row["code"] == "TOMBSTONE_FACTS_LOST"
    )
    assert finding["candidate_id"] == "C2"
    assert "artifact_hash" in finding["lost_fields"]


def test_a_protected_tombstone_emptied_of_its_facts_is_a_finding() -> None:
    plan = forget_plan()
    hollow = [
        {**row, "artifact_hash": "sha256:" + "0" * 64, "retention_reason": "removed"}
        if row["candidate_id"] == "C2"
        else dict(row)
        for row in plan["tombstoned"]
    ]
    report = audit_retention_sweep(**sweep_arguments(tombstones=hollow))

    finding = next(
        row for row in report["findings"] if row["code"] == "TOMBSTONE_FACTS_LOST"
    )
    assert finding["candidate_id"] == "C2"
    assert finding["lost_fields"] == ["artifact_hash", "retention_reason"]


def test_an_executed_plan_that_does_not_re_derive_is_a_finding() -> None:
    # The outcomes still agree with the plan's own counts; only the record of
    # when it was requested was edited afterwards, which the digest catches.
    plan = {**forget_plan(), "requested_at": "2020-01-01T00:00:00.000Z"}
    report = audit_retention_sweep(**sweep_arguments(executed_plans=[plan]))

    assert report["findings"][0]["code"] == "PLAN_HASH_MISMATCH"
    assert report["findings"][0]["plan_id"] == "EFP-L06-1"


def test_two_plans_tombstoning_one_candidate_differently_are_refused() -> None:
    first = forged_plan(
        erased=[],
        tombstoned=[tombstone("C2", A_PROTECTED_CLASS, "A")],
        plan_id="EFP-L06-D1",
    )
    second = forged_plan(
        erased=[],
        tombstoned=[tombstone("C2", A_PROTECTED_CLASS, "B")],
        plan_id="EFP-L06-D2",
    )

    with pytest.raises(MemoryGateError) as caught:
        audit_retention_sweep(**sweep_arguments(executed_plans=[first, second]))
    assert caught.value.code == "INPUT_INVALID"
    assert caught.value.context["candidate_id"] == "C2"


def test_a_tombstone_ledger_holding_one_candidate_twice_is_refused() -> None:
    plan = forget_plan()
    doubled = [dict(row) for row in plan["tombstoned"]] + [dict(plan["tombstoned"][1])]

    with pytest.raises(MemoryGateError) as caught:
        audit_retention_sweep(**sweep_arguments(tombstones=doubled))
    assert caught.value.code == "INPUT_INVALID"


def test_require_clean_sweep_names_the_first_finding_by_its_own_code() -> None:
    report = audit_retention_sweep(**sweep_arguments(tombstones=[]))

    with pytest.raises(MemoryGateError) as caught:
        require_clean_sweep(report)
    assert caught.value.code == "TOMBSTONE_FACTS_LOST"
    assert caught.value.context["audit_id"] == "ERS-L06-1"
    assert len(caught.value.context["findings"]) == report["counts"]["findings"]


# --- shape refusals -------------------------------------------------------


@pytest.mark.parametrize("value", [None, [], "plan", 7])
def test_a_plan_that_is_not_a_mapping_is_refused(value: object) -> None:
    with pytest.raises(MemoryGateError) as caught:
        verify_plan_hash(value)  # type: ignore[arg-type]
    assert caught.value.code == "INPUT_INVALID"


def test_an_execution_that_is_not_a_mapping_is_refused() -> None:
    error = refused(execution=["C4"])

    assert error.code == "INPUT_INVALID"


def test_a_candidate_id_that_is_blank_is_refused() -> None:
    with pytest.raises(MemoryGateError) as caught:
        place_legal_hold(
            hold_id="LH-X",
            authority=dict(HOLD_AUTHORITY),
            placed_at=RECORDED_AT,
            candidate_ids=["  "],
        )
    assert caught.value.code == "INPUT_INVALID"


def test_a_candidate_id_sequence_given_as_a_string_is_refused() -> None:
    with pytest.raises(MemoryGateError) as caught:
        place_legal_hold(
            hold_id="LH-X",
            authority=dict(HOLD_AUTHORITY),
            placed_at=RECORDED_AT,
            candidate_ids="C4",  # type: ignore[arg-type]
        )
    assert caught.value.code == "INPUT_INVALID"


def test_the_engines_own_refusal_is_never_swallowed() -> None:
    # The gate reports L05's finding under its own code and keeps the upstream
    # code, message and context, so nothing about the refusal has to be guessed.
    with pytest.raises(EvolutionMemoryError):
        LineageMemory([lineage_record("C4", ["C3"], 4)])

    error = refused(plan=forget_plan(candidate_ids=["C9"], plan_id="EFP-L06-U"))
    assert error.code == "UPSTREAM_MEMORY_REFUSED"
    assert error.context["upstream_message"]
    assert error.context["upstream_context"]["refusals"]
    assert error.context["action"]
