"""unit_and_contract_tests — memory that is asked to forget honestly.

The happy paths are the ones a real workspace takes: walk a lineage, plan a
forget whose grounds outrank retention, and export a record that carries its
negative knowledge with it.  Each outcome — erased, tombstoned, refused — is
exercised where it is the correct one, because a forget that can only refuse
would make erasure obligations unsatisfiable.
"""

from __future__ import annotations

import pytest

from epistemic_foundry.memory.v4_l05 import (
    FORGET_GROUNDS,
    LineageMemory,
    build_export_manifest,
    plan_forget,
    require_executable_forget,
)
from fixtures import (
    A_PROTECTED_CLASS,
    AUTHORITY,
    RECORDED_AT,
    archive_entry,
    chain_entries,
    chain_memory,
    export_arguments,
    lineage_record,
)


def forget(**overrides: object) -> dict:
    arguments: dict = {
        "entries": chain_entries(),
        "lineage": chain_memory(),
        "candidate_ids": ["C1", "C2", "C3", "C4"],
        "authority": dict(AUTHORITY),
        "requested_at": RECORDED_AT,
        "plan_id": "EFP-L05-1",
    }
    arguments.update(overrides)
    return plan_forget(**arguments)


def test_a_lineage_memory_walks_both_directions() -> None:
    memory = chain_memory()

    assert memory.candidates() == ("C1", "C2", "C3", "C4")
    assert memory.parents_of("C3") == ("C2",)
    assert memory.ancestors_of("C4") == ("C1", "C2", "C3")
    assert memory.children_of("C1") == ("C2",)
    assert memory.descendants_of("C2") == ("C3", "C4")
    assert memory.generation_of("C4") == 4


def test_a_root_has_no_ancestors_and_a_leaf_no_descendants() -> None:
    memory = chain_memory()

    assert memory.ancestors_of("C1") == ()
    assert memory.descendants_of("C4") == ()


def test_a_branching_lineage_reports_every_descendant() -> None:
    memory = LineageMemory(
        [
            lineage_record("R", [], 1),
            lineage_record("A", ["R"], 2),
            lineage_record("B", ["R"], 2),
            lineage_record("AB", ["A", "B"], 3),
        ]
    )

    assert memory.descendants_of("R") == ("A", "AB", "B")
    assert memory.ancestors_of("AB") == ("A", "B", "R")


def test_forgetting_the_whole_chain_stops_at_the_protected_entry() -> None:
    # C2 is protected, so it survives as a tombstone that keeps its lineage
    # record — which means its ancestor C1 cannot be erased either.  Only the
    # descendants below the tombstone actually disappear.
    plan = forget()

    assert plan["erased"] == ["C3", "C4"]
    assert [row["candidate_id"] for row in plan["tombstoned"]] == ["C1", "C2"]
    assert plan["refusals"] == []
    assert plan["counts"] == {
        "erased": 2,
        "refused": 0,
        "requested": 4,
        "tombstoned": 2,
    }
    require_executable_forget(plan)
    ancestor = plan["tombstoned"][0]
    assert ancestor["code"] == "LINEAGE_ORPHANED"
    assert ancestor["retained_descendants"] == ["C2"]


def test_a_protected_entry_is_tombstoned_not_erased() -> None:
    plan = forget()
    tombstone = next(row for row in plan["tombstoned"] if row["candidate_id"] == "C2")
    assert tombstone["code"] == "PROTECTED_MEMORY_ERASED"
    assert tombstone["entry_class"] == "null"
    assert tombstone["artifact_hash"] == "sha256:" + "b" * 64
    assert tombstone["lineage_id"] == "LIN-C2"
    assert tombstone["generation"] == 2


@pytest.mark.parametrize(
    "ground", [g for g in FORGET_GROUNDS if g != FORGET_GROUNDS[0]]
)
def test_every_external_obligation_ground_is_accepted(ground: str) -> None:
    plan = forget(authority={**AUTHORITY, "ground": ground})

    assert plan["authority"]["ground"] == ground
    require_executable_forget(plan)


def test_a_leaf_with_no_descendants_is_simply_erased() -> None:
    plan = forget(candidate_ids=["C4"])

    assert plan["erased"] == ["C4"]
    assert plan["tombstoned"] == []
    require_executable_forget(plan)


def test_an_ancestor_of_surviving_memory_is_tombstoned() -> None:
    plan = forget(candidate_ids=["C1"])
    tombstone = plan["tombstoned"][0]

    assert plan["erased"] == []
    assert tombstone["code"] == "LINEAGE_ORPHANED"
    assert tombstone["retained_descendants"] == ["C2", "C3", "C4"]


def test_orphan_protection_iterates_to_fixpoint() -> None:
    # C1..C3 requested, C4 stays: nothing in the chain may be erased, because
    # each erasure would strand the next candidate's retained record.
    plan = forget(candidate_ids=["C1", "C3"])

    assert plan["erased"] == []
    codes = {row["candidate_id"]: row["code"] for row in plan["tombstoned"]}
    assert codes == {"C1": "LINEAGE_ORPHANED", "C3": "LINEAGE_ORPHANED"}


def test_duplicate_candidate_ids_are_counted_once() -> None:
    plan = forget(candidate_ids=["C4", "C4", "C4"])

    assert plan["counts"]["requested"] == 1
    assert plan["erased"] == ["C4"]


def test_the_plan_is_deterministic() -> None:
    assert forget() == forget()


def test_the_export_carries_every_class_by_default() -> None:
    manifest = build_export_manifest(**export_arguments())

    assert [row["candidate_id"] for row in manifest["exported_entries"]] == [
        "C1",
        "C2",
        "C3",
        "C4",
    ]
    assert manifest["exported_class_counts"]["null"] == 1
    assert manifest["exported_class_counts"]["elite"] == 1
    assert manifest["external_ancestors"] == []


def test_an_export_of_only_negative_knowledge_is_permitted() -> None:
    manifest = build_export_manifest(
        **export_arguments(included_classes=[A_PROTECTED_CLASS, "null"])
    )

    assert manifest["included_classes"] == sorted({A_PROTECTED_CLASS, "null"})
    assert [row["entry_class"] for row in manifest["exported_entries"]] == ["null"]


def test_the_export_names_the_ancestry_it_does_not_carry() -> None:
    entries = [archive_entry("C3", "diverse"), archive_entry("C4", "superseded")]
    manifest = build_export_manifest(**export_arguments(entries=entries))

    assert [row["candidate_id"] for row in manifest["exported_entries"]] == ["C3", "C4"]
    assert manifest["external_ancestors"] == ["C1", "C2"]


def test_the_export_records_the_policy_rules_it_ran_under() -> None:
    manifest = build_export_manifest(**export_arguments())

    assert manifest["policy_hash"].startswith("sha256:")
    assert [rule["class"] for rule in manifest["class_rules_applied"]] == ["EVIDENCE"]
    assert manifest["class_rules_applied"][0]["external_sync"] == "ALLOW_REDACTED"


def test_a_named_foreign_workspace_is_recorded_when_policy_allows() -> None:
    from fixtures import workspace_policy

    policy = workspace_policy(cross_workspace_retrieval="EXPLICIT_ONLY")
    manifest = build_export_manifest(
        **export_arguments(policy=policy, target_workspace_id="WS-OTHER")
    )

    assert manifest["source_workspace_id"] == policy["workspace_id"]
    assert manifest["target_workspace_id"] == "WS-OTHER"


def test_the_export_is_deterministic() -> None:
    assert build_export_manifest(**export_arguments()) == build_export_manifest(
        **export_arguments()
    )


def test_plan_and_manifest_are_serialisable_evidence() -> None:
    import json

    plan = forget()
    manifest = build_export_manifest(**export_arguments())

    for record in (plan, manifest):
        assert json.loads(json.dumps(record, ensure_ascii=False, sort_keys=True)) == (
            record
        )
