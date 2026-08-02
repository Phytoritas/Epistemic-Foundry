"""negative_and_adversarial_tests — every way memory can be damaged, refused.

Forgetting is where a record dies quietly: a capacity sweep that takes the
counterexamples with it, an erasure that strands the ancestry of what remains,
an export that ships the winners and leaves the failures.  Each attack is
staged as an input that is wrong in exactly one way and must be refused by its
own code.
"""

from __future__ import annotations

import pytest

from epistemic_foundry.epistemic_species_archive.archive import (
    PROTECTED_ENTRY_CLASSES,
)
from epistemic_foundry.memory.v4_l05 import (
    CAPACITY_GROUND,
    EvolutionMemoryError,
    LineageMemory,
    build_export_manifest,
    plan_forget,
    require_executable_forget,
)
from fixtures import (
    AUTHORITY,
    RECORDED_AT,
    archive_entry,
    chain_entries,
    chain_memory,
    export_arguments,
    lineage_record,
    workspace_policy,
)


def forget(**overrides: object) -> dict:
    arguments: dict = {
        "entries": chain_entries(),
        "lineage": chain_memory(),
        "candidate_ids": ["C4"],
        "authority": dict(AUTHORITY),
        "requested_at": RECORDED_AT,
    }
    arguments.update(overrides)
    return plan_forget(**arguments)


def refused(run, code: str) -> EvolutionMemoryError:
    with pytest.raises(EvolutionMemoryError) as caught:
        run()
    assert caught.value.code == code, caught.value.code
    return caught.value


def test_a_lineage_naming_an_absent_ancestor_is_refused() -> None:
    error = refused(
        lambda: LineageMemory([lineage_record("C2", ["C-GONE"], 2)]),
        "LINEAGE_BROKEN",
    )
    assert error.context["unknown_parents"] == ["C-GONE"]


def test_a_lineage_cycle_is_refused() -> None:
    refused(
        lambda: LineageMemory(
            [lineage_record("C1", ["C2"], 1), lineage_record("C2", ["C1"], 2)]
        ),
        "LINEAGE_BROKEN",
    )


def test_a_candidate_recorded_twice_is_refused() -> None:
    refused(
        lambda: LineageMemory(
            [lineage_record("C1", [], 1), lineage_record("C1", [], 1)]
        ),
        "INPUT_INVALID",
    )


def test_a_lineage_record_the_schema_rejects_is_refused() -> None:
    from epistemic_foundry.contracts import ContractViolation

    record = lineage_record("C1", [], 1)
    del record["ancestor_hashes"]

    with pytest.raises(ContractViolation):
        LineageMemory([record])


def test_walking_an_unknown_candidate_is_refused() -> None:
    memory = chain_memory()

    for walk in (memory.ancestors_of, memory.descendants_of, memory.parents_of):
        error = refused(lambda run=walk: run("C-GONE"), "CANDIDATE_UNKNOWN")
        assert error.context["candidate_id"] == "C-GONE"


@pytest.mark.parametrize("entry_class", sorted(PROTECTED_ENTRY_CLASSES))
def test_capacity_pressure_cannot_erase_any_protected_class(entry_class: str) -> None:
    entries = [archive_entry("C4", entry_class)]
    plan = forget(entries=entries, authority={**AUTHORITY, "ground": CAPACITY_GROUND})

    assert plan["erased"] == []
    assert plan["tombstoned"] == []
    assert plan["refusals"][0]["code"] == "PROTECTED_MEMORY_ERASED"
    refused(lambda: require_executable_forget(plan), "PROTECTED_MEMORY_ERASED")


def test_capacity_pressure_may_still_erase_an_evictable_leaf() -> None:
    plan = forget(authority={**AUTHORITY, "ground": CAPACITY_GROUND})

    assert plan["erased"] == ["C4"]
    require_executable_forget(plan)


def test_a_forget_naming_an_unarchived_candidate_is_refused() -> None:
    plan = forget(candidate_ids=["C-GONE"])

    assert plan["refusals"][0]["code"] == "CANDIDATE_UNKNOWN"
    refused(lambda: require_executable_forget(plan), "CANDIDATE_UNKNOWN")


def test_an_entry_without_a_lineage_record_is_refused() -> None:
    entries = [*chain_entries(), archive_entry("C9", "elite")]

    error = refused(lambda: forget(entries=entries), "LINEAGE_BROKEN")
    assert error.context["missing_lineage"] == ["C9"]


def test_erasing_the_ancestor_of_a_tombstone_is_prevented() -> None:
    # C2 is protected: it survives as a tombstone whose lineage record still
    # names C1, so erasing C1 would strand it even though every candidate was
    # named in the same request.
    plan = forget(candidate_ids=["C1", "C2", "C3", "C4"])
    outcomes = {row["candidate_id"]: row["code"] for row in plan["tombstoned"]}

    assert outcomes["C1"] == "LINEAGE_ORPHANED"
    assert "C1" not in plan["erased"]


def test_a_forget_without_authority_is_refused() -> None:
    for broken in (
        {},
        {**AUTHORITY, "ground": "because_we_want_to"},
        {**AUTHORITY, "approved_by": "  "},
        {**AUTHORITY, "authority_id": ""},
    ):
        refused(
            lambda given=broken: forget(authority=given), "FORGET_AUTHORITY_MISSING"
        )


def test_a_forget_naming_nobody_is_refused() -> None:
    refused(lambda: forget(candidate_ids=[]), "INPUT_INVALID")


def test_two_entries_claiming_one_candidate_are_refused() -> None:
    entries = [archive_entry("C4", "elite"), archive_entry("C4", "diverse")]

    refused(lambda: forget(entries=entries), "INPUT_INVALID")


def test_an_archive_entry_the_schema_rejects_is_refused() -> None:
    from epistemic_foundry.contracts import ContractViolation

    entry = archive_entry("C4", "elite")
    entry["artifact_hash"] = "not-a-hash"

    with pytest.raises(ContractViolation):
        forget(entries=[entry])


def test_a_survivorship_biased_export_is_refused() -> None:
    error = refused(
        lambda: build_export_manifest(
            **export_arguments(included_classes=["diverse", "elite", "superseded"])
        ),
        "EXPORT_SURVIVORSHIP_BIASED",
    )
    assert error.context["dropped_protected"] == ["null"]
    assert error.context["kept_evictable"] == ["diverse", "elite", "superseded"]


def test_dropping_one_protected_class_while_keeping_results_is_still_biased() -> None:
    entries = [*chain_entries(), archive_entry("C5", "unsafe")]
    lineage = LineageMemory(
        [
            lineage_record("C1", [], 1),
            lineage_record("C2", ["C1"], 2),
            lineage_record("C3", ["C2"], 3),
            lineage_record("C4", ["C3"], 4),
            lineage_record("C5", ["C4"], 5),
        ]
    )
    included = ["diverse", "elite", "null", "superseded"]

    error = refused(
        lambda: build_export_manifest(
            **export_arguments(
                entries=entries, lineage=lineage, included_classes=included
            )
        ),
        "EXPORT_SURVIVORSHIP_BIASED",
    )
    assert error.context["dropped_protected"] == ["unsafe"]


def test_an_export_class_outside_the_vocabulary_is_refused() -> None:
    refused(
        lambda: build_export_manifest(**export_arguments(included_classes=["winner"])),
        "ENTRY_CLASS_UNKNOWN",
    )


def test_an_export_without_consent_is_refused() -> None:
    refused(
        lambda: build_export_manifest(**export_arguments(consent_id=None)),
        "EXPORT_SCOPE_DENIED",
    )


def test_an_export_of_a_class_the_policy_does_not_allow_is_refused() -> None:
    refused(
        lambda: build_export_manifest(**export_arguments(memory_classes=["REGULATED"])),
        "EXPORT_SCOPE_DENIED",
    )


def test_an_export_of_a_class_without_a_rule_is_refused() -> None:
    error = refused(
        lambda: build_export_manifest(**export_arguments(memory_classes=["WORKSPACE"])),
        "EXPORT_SCOPE_DENIED",
    )
    assert error.context["ungoverned_classes"] == ["WORKSPACE"]


def test_a_cross_workspace_export_is_denied_by_default() -> None:
    refused(
        lambda: build_export_manifest(
            **export_arguments(target_workspace_id="WS-OTHER")
        ),
        "EXPORT_SCOPE_DENIED",
    )


def test_an_expired_export_is_refused() -> None:
    refused(
        lambda: build_export_manifest(**export_arguments(age_days=400)),
        "EXPORT_SCOPE_DENIED",
    )


def test_an_explicit_only_policy_denies_the_unnamed_foreign_workspace() -> None:
    policy = workspace_policy(cross_workspace_retrieval="EXPLICIT_ONLY")
    manifest = build_export_manifest(**export_arguments(policy=policy))

    assert manifest["target_workspace_id"] == policy["workspace_id"]
    refused(
        lambda: build_export_manifest(
            **export_arguments(
                policy=policy, workspace_id="WS-OTHER", target_workspace_id=None
            )
        ),
        "EXPORT_SCOPE_DENIED",
    )


def test_a_non_mapping_input_is_refused() -> None:
    refused(lambda: forget(entries=["not-a-mapping"]), "INPUT_INVALID")
    refused(lambda: forget(authority="workspace_purge"), "INPUT_INVALID")


def test_the_plan_reports_every_failure_class_at_once() -> None:
    plan = forget(candidate_ids=["C1", "C4", "C-GONE"])

    assert plan["refusals"][0]["code"] == "CANDIDATE_UNKNOWN"
    assert plan["tombstoned"][0]["code"] == "LINEAGE_ORPHANED"
    assert plan["erased"] == ["C4"]
