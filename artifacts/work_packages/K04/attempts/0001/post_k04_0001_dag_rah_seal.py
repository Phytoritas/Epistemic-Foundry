#!/usr/bin/env python3
"""Append the verified post-K04-0001 DAG reconciliation to active RAH state."""

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
ATTEMPT = ROOT / "artifacts/work_packages/K04/attempts/0001"
AUTOMATION = ROOT / ".rah/helpers/recursive-architecture-refactoring-auto/automation"
sys.path.insert(0, str(ATTEMPT))
sys.path.insert(0, str(AUTOMATION))

import k04_0001_rah_seal as k04_seal  # noqa: E402
import post_k04_0001_dag_reconciliation as reconciliation  # noqa: E402
import ralph_harness as rh  # noqa: E402
import state_store  # noqa: E402


EXPECTED_PARENT = "000039-a4a723c4"
EXPECTED_EVIDENCE_ID = "E0040"
NEXT_ACTIONS = [
    "Execute L01-0001 memory classes, consent, and retention policy under its exact manifest scope.",
    "Run L01 required checks, full regressions, and a separate primary-session review.",
    "Seal L01 evidence and recompute the live 156-package DAG without setting completion_ready=true.",
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


def validate_reconciliation() -> tuple[dict[str, Any], str]:
    expected = reconciliation.reconcile()
    path = ATTEMPT / "post-k04-0001-dag-reconciliation.json"
    stored = read_json(path)
    if stored != expected:
        raise SystemExit("stored DAG reconciliation differs from live recomputation")
    if not (
        stored.get("status") == "PASS"
        and stored.get("manifest", {}).get("work_package_count") == 156
        and stored.get("completed_package_count") == 49
        and stored.get("blocked_package_count") == 102
        and stored.get("ready_packages_manifest_order")
        == ["L01", "M01", "N01", "T01", "A06"]
        and stored.get("next_package") == "L01"
        and stored.get("completion_ready") is False
    ):
        raise SystemExit("DAG reconciliation does not identify the expected next step")
    review_path = ATTEMPT / "post-k04-0001-dag-review.md"
    if review_path.read_text(encoding="utf-8") != reconciliation.review_text(stored):
        raise SystemExit("DAG reconciliation review differs from deterministic rendering")
    hashes = {
        "dag": sha256(path),
        "review": sha256(review_path),
        "reconciler": sha256(ATTEMPT / "post_k04_0001_dag_reconciliation.py"),
        "sealer": sha256(Path(__file__)),
    }
    summary = (
        "Post-K04-0001 live DAG reconciliation PASS is append-only bound to sealed "
        "K04-0001 final evidence E0039 / 000039-a4a723c4. The active development "
        "manifest has 156 unique packages, no unknown dependency and no cycle; "
        "49 packages are currently PASS, 5 are dependency-ready, and 102 wait on "
        "unmet dependencies. Manifest-order READY is L01, M01, N01, T01, A06, so "
        "L01 is the next bounded package. Package state is selected from the "
        "highest numeric attempt, preventing an older PASS from hiding a newer "
        f"non-PASS or incomplete attempt. DAG sha256:{hashes['dag']}; review "
        f"sha256:{hashes['review']}; reconciler sha256:{hashes['reconciler']}; "
        f"sealer sha256:{hashes['sealer']}. This selects work only; downstream "
        "packages remain, implementation_gate=fail, and completion_ready=false."
    )
    return stored, summary


def commit(summary: str) -> str:
    ralph_root, parent, payloads = k04_seal.current_state()
    if parent != EXPECTED_PARENT:
        raise SystemExit(f"unexpected RAH parent {parent}; expected {EXPECTED_PARENT}")
    identifiers = k04_seal.evidence_ids(payloads)
    if identifiers[-1] != "E0039" or len(k04_seal.numbered_generations(ralph_root)) != 39:
        raise SystemExit("post-K04 DAG seal requires exact E0039 / 39-generation state")
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
    loop["state_machine"] = {
        "allowed_next_states": ["verify", "plan", "blocked", "failed"],
        "current_state": "act",
        "states": [
            "intake",
            "plan",
            "act",
            "verify",
            "review",
            "decide",
            "done",
            "blocked",
            "cancelled",
            "failed",
        ],
    }
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
        "The sealed post-K04 DAG selects L01 as the earliest dependency-ready "
        "package. Downstream work remains; implementation_gate=fail and "
        "completion_ready=false."
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
    _, summary = validate_reconciliation()
    ralph_root, current, payloads = k04_seal.current_state()
    identifiers = k04_seal.evidence_ids(payloads)
    if current == EXPECTED_PARENT and identifiers[-1] == "E0039":
        before = k04_seal.numbered_generations(ralph_root)
        generation = commit(summary)
        after = k04_seal.numbered_generations(ralph_root)
        if after[:-1] != before or after[-1] != generation:
            raise SystemExit("DAG evidence seal did not preserve every prior generation")
    else:
        if identifiers[-1] != EXPECTED_EVIDENCE_ID:
            raise SystemExit("RAH state is neither pre-seal nor the exact sealed result")
        generation = current
        if payloads["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
            raise SystemExit("stored E0040 summary differs from current DAG artifacts")
    result = k04_seal.verify_generation_store(40)
    if result["latest_evidence_id"] != EXPECTED_EVIDENCE_ID:
        raise SystemExit("DAG evidence is not the live RAH tail")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
