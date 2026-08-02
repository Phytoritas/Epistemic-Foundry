"""provenance_and_receipt_audit — a forget and an export can prove themselves.

A deletion is the one effect that cannot be re-derived afterwards, so its plan
must be: every plan and manifest re-derives its own hash from exactly the
fields it publishes, binds the policy and artifacts it acted under by digest,
and keeps in each tombstone the facts that outlive the payload.  Nothing here
carries a clock the caller did not supply.
"""

from __future__ import annotations

import ast
from pathlib import Path

from epistemic_foundry.domain.hashing import hash_excluding
from epistemic_foundry.memory.policy import build_retrieval_receipt
from epistemic_foundry.memory.v4_l05 import build_export_manifest, plan_forget
from fixtures import (
    AUTHORITY,
    RECORDED_AT,
    chain_entries,
    chain_memory,
    export_arguments,
)

ROOT = Path(__file__).resolve().parents[5]
ENGINE = ROOT / "src/epistemic_foundry/memory/v4_l05/retention.py"


def forget_plan() -> dict:
    return plan_forget(
        entries=chain_entries(),
        lineage=chain_memory(),
        candidate_ids=["C1", "C2", "C3", "C4"],
        authority=dict(AUTHORITY),
        requested_at=RECORDED_AT,
        plan_id="EFP-L05-PROV",
    )


def test_the_plan_re_derives_its_own_hash() -> None:
    plan = forget_plan()

    assert plan["plan_hash"] == hash_excluding(dict(plan), "plan_hash")


def test_the_manifest_re_derives_its_own_hash() -> None:
    manifest = build_export_manifest(**export_arguments())

    assert manifest["manifest_hash"] == hash_excluding(dict(manifest), "manifest_hash")


def test_the_manifest_binds_the_policy_it_ran_under() -> None:
    arguments = export_arguments()
    manifest = build_export_manifest(**arguments)

    assert manifest["policy_hash"] == arguments["policy"]["policy_hash"]


def test_a_different_policy_changes_the_manifest_hash() -> None:
    from fixtures import workspace_policy

    baseline = build_export_manifest(**export_arguments())
    changed = build_export_manifest(
        **export_arguments(policy=workspace_policy(default_retention_days=91))
    )

    assert baseline["manifest_hash"] != changed["manifest_hash"]


def test_every_exported_entry_carries_its_artifact_hash() -> None:
    manifest = build_export_manifest(**export_arguments())

    for row in manifest["exported_entries"]:
        assert row["artifact_hash"].startswith("sha256:")
        assert row["retention_reason"]
        assert row["lineage_id"]


def test_a_tombstone_keeps_what_outlives_the_payload() -> None:
    plan = forget_plan()
    tombstone = next(row for row in plan["tombstoned"] if row["candidate_id"] == "C2")

    assert set(tombstone) == {
        "archive_entry_id",
        "artifact_hash",
        "candidate_id",
        "code",
        "entry_class",
        "generation",
        "lineage_id",
        "reason",
        "retention_reason",
    }
    assert tombstone["reason"]


def test_the_plan_records_the_authority_it_acted_under() -> None:
    plan = forget_plan()

    assert plan["authority"] == {
        "approved_by": AUTHORITY["approved_by"],
        "authority_id": AUTHORITY["authority_id"],
        "ground": AUTHORITY["ground"],
    }


def test_the_counts_reconcile_with_the_lists_exactly() -> None:
    plan = forget_plan()

    assert plan["counts"]["erased"] == len(plan["erased"])
    assert plan["counts"]["tombstoned"] == len(plan["tombstoned"])
    assert plan["counts"]["refused"] == len(plan["refusals"])
    assert plan["counts"]["requested"] == len(plan["requested"])
    assert plan["counts"]["requested"] == (
        plan["counts"]["erased"]
        + plan["counts"]["tombstoned"]
        + plan["counts"]["refused"]
    )


def test_the_inputs_are_not_mutated() -> None:
    entries = chain_entries()
    before = [dict(entry) for entry in entries]
    arguments = export_arguments(entries=entries)
    policy_before = dict(arguments["policy"])

    plan_forget(
        entries=entries,
        lineage=chain_memory(),
        candidate_ids=["C4"],
        authority=dict(AUTHORITY),
        requested_at=RECORDED_AT,
    )
    build_export_manifest(**arguments)

    assert entries == before
    assert arguments["policy"] == policy_before


def test_the_engine_holds_no_clock_and_no_randomness() -> None:
    tree = ast.parse(ENGINE.read_text(encoding="utf-8"))
    called = {
        ast.unparse(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)
    }

    assert "utc_now_iso" not in called
    assert not any(name.startswith("random.") for name in called)
    # `new_id` runs only when the caller declines to supply an identifier, so
    # determinism is in the caller's hands and the hash covers the identifier.
    assert "new_id" in called


def test_a_supplied_identifier_makes_the_records_reproducible() -> None:
    assert forget_plan() == forget_plan()
    assert (
        build_export_manifest(**export_arguments())["manifest_hash"]
        == build_export_manifest(**export_arguments())["manifest_hash"]
    )


def test_an_export_can_be_bound_into_a_canonical_retrieval_receipt() -> None:
    manifest = build_export_manifest(**export_arguments())
    hits = [
        {
            "memory_id": f"MEM-{row['candidate_id']}",
            "class": manifest["memory_classes"][0],
            "score": 1.0,
            "source_hash": row["artifact_hash"],
            "redacted": False,
        }
        for row in manifest["exported_entries"]
    ]
    receipt = build_retrieval_receipt(
        query=f"evolution memory export {manifest['manifest_id']}",
        workspace_id=manifest["source_workspace_id"],
        purpose=manifest["purpose"],
        searched_classes=manifest["memory_classes"],
        excluded_classes=[],
        hits=hits,
        consent_id="CN-L05-1",
        context_capsule_id="CC-L05-1",
        receipt_id="MRR-L05-1",
        retrieved_at=manifest["exported_at"],
    )

    assert len(receipt["hits"]) == 4
    assert receipt["hits"][0]["source_hash"] == "sha256:" + "b" * 64
    assert receipt["result_hash"].startswith("sha256:")
