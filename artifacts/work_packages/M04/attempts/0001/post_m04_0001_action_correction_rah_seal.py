#!/usr/bin/env python3
"""Append-only correction of the post-M04 live action description."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/M04/attempts/0001"
AUTOMATION = ROOT / ".rah/helpers/recursive-architecture-refactoring-auto/automation"
sys.path.insert(0, str(ATTEMPT))
sys.path.insert(0, str(AUTOMATION))

import m04_0001_rah_seal as m04_seal  # noqa: E402
import post_m04_0001_dag_reconciliation as reconciliation  # noqa: E402
import ralph_harness as rh  # noqa: E402
import state_store  # noqa: E402


EXPECTED_PARENT = "000064-e2ab95f2"
EXPECTED_PARENT_MANIFEST_HASH = (
    "2b1db7f809c9ec7d66ee8fac03f03f5d2c2c498192ca98e43c41737a40d2e088"
)
EXPECTED_EVIDENCE_ID = "E0065"
NEXT_ACTIONS = [
    "Execute N01-0001 Canonical RoleSpec and evidence/tool ACLs under its exact manifest scope.",
    "Run N01 role_schema_test and acl_test with regressions and separate primary-session review.",
    "Seal N01 evidence and recompute the live 156-package DAG without setting completion_ready=true.",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"JSON artifact is not an object: {path}")
    return value


def correction_summary() -> str:
    stored = read_json(ATTEMPT / "post-m04-0001-dag-reconciliation.json")
    live = reconciliation.reconcile()
    if stored != live:
        raise SystemExit("post-M04 DAG artifact differs from live recomputation")
    n01 = stored.get("ready_packages", {}).get("N01")
    if not (
        stored.get("next_package") == "N01"
        and stored.get("ready_packages_manifest_order") == ["N01", "O01", "T01", "A06"]
        and isinstance(n01, dict)
        and n01.get("title") == "Canonical RoleSpec and evidence/tool ACLs"
    ):
        raise SystemExit("post-M04 reconciliation no longer selects the canonical N01 contract")
    return (
        "Append-only correction to post-M04 live execution guidance: E0064 and its "
        "DAG artifact remain valid and immutable; both correctly select N01 from the "
        "manifest-order READY set N01, O01, T01, A06. The E0064 generation's "
        "loop_state.next_actions incorrectly described N01 as a scientific claim "
        "store and named claim_link_integrity/passport_query_test. The authoritative "
        "development manifest defines N01 as Canonical RoleSpec and evidence/tool "
        "ACLs, with exact write scope packages/role-router/src/contracts/** and "
        "required checks role_schema_test and acl_test. This E0065 evidence supersedes "
        "only those live action-description strings; it does not alter E0064, the "
        "57 PASS / 4 READY / 95 WAITING calculation, any prior report, or any prior "
        "generation. Global implementation_gate=fail and completion_ready=false."
    )


def commit(summary: str) -> str:
    base = m04_seal.sealed_base
    ralph_root, parent, payloads = base.current_state()
    if parent != EXPECTED_PARENT:
        raise SystemExit(f"unexpected RAH parent {parent}; expected {EXPECTED_PARENT}")
    parent_manifest = ralph_root / "generations" / parent / "generation-manifest.json"
    if sha256(parent_manifest) != EXPECTED_PARENT_MANIFEST_HASH:
        raise SystemExit("sealed E0064 parent generation manifest hash changed")
    identifiers = base.evidence_ids(payloads)
    if identifiers[-1] != "E0064" or len(base.numbered_generations(ralph_root)) != 64:
        raise SystemExit("action correction requires exact E0064 / 64-generation state")

    ledger = copy.deepcopy(payloads["evidence_ledger.json"])
    goal = copy.deepcopy(payloads["goal.json"])
    loop = copy.deepcopy(payloads["loop_state.json"])
    now = rh.utc_now()
    identifier = rh.add_evidence_entry(
        ledger,
        now=now,
        goal_id=goal["goal_id"],
        iteration=int(loop.get("current_iteration") or 1),
        kind="evidence",
        summary=summary,
    )
    if identifier != EXPECTED_EVIDENCE_ID:
        raise SystemExit(f"unexpected evidence ID {identifier}")

    objective = str(goal["goal"])
    goal.update({"status": "active", "updated_at_utc": now})
    loop.update(
        {
            "blocked_reason": None,
            "checkpoint_required": False,
            "current_stage": "ralph-active",
            "done": False,
            "generated_at_utc": now,
            "harness_phase": "execution",
            "implementation_gate": "fail",
            "loop_phase": "bounded-implementation",
            "mark_done_rejected": False,
            "next_actions": NEXT_ACTIONS,
            "status": "active",
            "updated_at_utc": now,
        }
    )
    readiness = loop.get("completion_readiness")
    if not isinstance(readiness, dict) or readiness.get("ready") is not False:
        raise SystemExit("completion readiness must remain explicitly false")
    readiness["evidence_count"] = len(ledger["entries"])
    loop["progress_update"] = {
        "created_evidence": [identifier],
        "missing_acceptance_ids": [],
        "missing_closeout_ids": [],
        "missing_evidence_ids": [],
        "missing_validation_ids": [],
        "used_evidence": list(dict.fromkeys([*identifiers, identifier])),
    }
    plan = rh.build_plan_graph(goal, loop, payloads["plan_graph.json"], now)
    bridge = rh.build_goal_bridge(
        ROOT,
        goal,
        loop,
        payloads["goal_bridge.json"],
        SimpleNamespace(goal_status="active", goal_objective=objective),
        now,
    )
    review = copy.deepcopy(payloads["review_gate.json"])
    review["updated_at_utc"] = now
    state_store.KEEP_GENERATIONS = 10_000
    generation = state_store.commit_generation(
        ralph_root,
        {
            "evidence_ledger.json": ledger,
            "goal.json": goal,
            "goal_bridge.json": bridge,
            "loop_state.json": loop,
            "plan_graph.json": plan,
            "review_gate.json": review,
        },
    )

    status_path = ROOT / ".rah/state/status.json"
    gates_path = ROOT / ".rah/state/gates.json"
    status = read_json(status_path)
    gates = read_json(gates_path)
    note = (
        "The corrected post-M04 action executes N01 Canonical RoleSpec and "
        "evidence/tool ACLs. Downstream work remains; implementation_gate=fail "
        "and completion_ready=false."
    )
    status["implementation_gate"] = "fail"
    status["implementation_gate_note"] = note
    status["next_recommended_action"] = NEXT_ACTIONS[0]
    existing = gates.get("implementation_gate", {}).get("evidence_ids", [])
    gates["implementation_gate"] = {
        "evidence_ids": list(dict.fromkeys([*existing, identifier])),
        "note": note,
        "status": "fail",
    }
    rh.write_json(status_path, status)
    rh.write_json(gates_path, gates)
    rh.refresh_status_for_ralph(ROOT, ROOT / ".rah", goal, loop, now)
    rh.upsert_current_loop(
        ROOT / ".rah/plans/current_loop.md", rh.render_managed_current_loop(goal, loop)
    )
    rh.write_text(ROOT / ".rah/ralph/blockers.md", rh.render_blockers(goal, loop, now))
    return generation


def main() -> int:
    summary = correction_summary()
    base = m04_seal.sealed_base
    ralph_root, current, payloads = base.current_state()
    identifiers = base.evidence_ids(payloads)
    if current == EXPECTED_PARENT and identifiers[-1] == "E0064":
        before = base.numbered_generations(ralph_root)
        generation = commit(summary)
        after = base.numbered_generations(ralph_root)
        if after[:-1] != before or after[-1] != generation:
            raise SystemExit("correction seal did not preserve every prior generation")
    else:
        if identifiers[-1] != EXPECTED_EVIDENCE_ID:
            raise SystemExit("RAH state is neither pre-correction nor exact corrected state")
        generation = current
        if payloads["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
            raise SystemExit("stored E0065 summary differs from current correction")
    result = m04_seal.verify_generation_store(65)
    if result["latest_evidence_id"] != EXPECTED_EVIDENCE_ID:
        raise SystemExit("correction evidence is not the live RAH tail")
    result["generation"] = generation
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
