#!/usr/bin/env python3
"""Append the verified post-M03-0001 DAG reconciliation to active RAH state."""

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
ATTEMPT = ROOT / "artifacts/work_packages/M03/attempts/0001"
AUTOMATION = ROOT / ".rah/helpers/recursive-architecture-refactoring-auto/automation"
sys.path.insert(0, str(ATTEMPT))
sys.path.insert(0, str(AUTOMATION))

import m03_0001_rah_seal as m03_seal  # noqa: E402
import post_m03_0001_dag_reconciliation as reconciliation  # noqa: E402
import ralph_harness as rh  # noqa: E402
import state_store  # noqa: E402


EXPECTED_PARENT = "000060-6cff73cc"
EXPECTED_PARENT_MANIFEST_HASH = (
    "0a503a37430b4532cd08e37af1a42754deafe2f9ab4b73d36acda5de35aaaffe"
)
EXPECTED_EVIDENCE_ID = "E0061"
NEXT_ACTIONS = [
    "Execute M04-0001 map UI and ranking-claim gate under its exact manifest scope.",
    "Run M04 map_ui_test and ranking_claim_audit with upstream regressions and separate primary-session review.",
    "Seal M04 evidence and recompute the live 156-package DAG without setting completion_ready=true.",
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
    path = ATTEMPT / "post-m03-0001-dag-reconciliation.json"
    stored = read_json(path)
    if stored != expected:
        raise SystemExit("stored DAG reconciliation differs from live recomputation")
    if not (
        stored.get("status") == "PASS"
        and stored.get("manifest", {}).get("work_package_count") == 156
        and stored.get("completed_package_count") == 56
        and stored.get("waiting_package_count") == 96
        and stored.get("ready_packages_manifest_order") == ["M04", "N01", "T01", "A06"]
        and stored.get("next_package") == "M04"
        and stored.get("completion_ready") is False
        and stored.get("external_resume_inspection", {}).get("status") == "PASS"
        and stored.get("external_resume_inspection", {}).get("parse_errors") == {}
    ):
        raise SystemExit("DAG reconciliation does not identify the expected next step")
    review_path = ATTEMPT / "post-m03-0001-dag-review.md"
    if review_path.read_text(encoding="utf-8") != reconciliation.review_text(stored):
        raise SystemExit("DAG reconciliation review differs from deterministic rendering")
    hashes = {
        "dag": sha256(path),
        "review": sha256(review_path),
        "reconciler": sha256(ATTEMPT / "post_m03_0001_dag_reconciliation.py"),
        "sealer": sha256(Path(__file__)),
    }
    summary = (
        "Post-M03-0001 live DAG reconciliation PASS is append-only bound to sealed "
        "M03-0001 final evidence E0060 / 000060-6cff73cc. The canonical external "
        "resume inspection exited 0 with parse_errors empty and active/fail/"
        "completion_ready=false. The development manifest has 156 unique packages, "
        "no unknown dependency and no cycle; 56 packages are PASS, 4 are "
        "dependency-ready, and 96 wait on unmet dependencies. Manifest-order READY "
        "is M04, N01, T01, A06, so M04 is next. Highest numeric attempt selection "
        "prevents older PASS evidence from hiding a newer non-PASS or incomplete "
        f"attempt. DAG sha256:{hashes['dag']}; review sha256:{hashes['review']}; "
        f"reconciler sha256:{hashes['reconciler']}; sealer sha256:{hashes['sealer']}. "
        "This selects work only; implementation_gate=fail and completion_ready=false."
    )
    return stored, summary


def commit(summary: str) -> str:
    base = m03_seal.sealed_base
    ralph_root, parent, payloads = base.current_state()
    if parent != EXPECTED_PARENT:
        raise SystemExit(f"unexpected RAH parent {parent}; expected {EXPECTED_PARENT}")
    parent_manifest = ralph_root / "generations" / parent / "generation-manifest.json"
    if sha256(parent_manifest) != EXPECTED_PARENT_MANIFEST_HASH:
        raise SystemExit("sealed M03 parent generation manifest hash changed")
    identifiers = base.evidence_ids(payloads)
    if identifiers[-1] != "E0060" or len(base.numbered_generations(ralph_root)) != 60:
        raise SystemExit("post-M03 DAG seal requires exact E0060 / 60-generation state")
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
        "The sealed post-M03 DAG selects M04 as the earliest dependency-ready "
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
    base = m03_seal.sealed_base
    ralph_root, current, payloads = base.current_state()
    identifiers = base.evidence_ids(payloads)
    if current == EXPECTED_PARENT and identifiers[-1] == "E0060":
        before = base.numbered_generations(ralph_root)
        generation = commit(summary)
        after = base.numbered_generations(ralph_root)
        if after[:-1] != before or after[-1] != generation:
            raise SystemExit("DAG evidence seal did not preserve every prior generation")
    else:
        if identifiers[-1] != EXPECTED_EVIDENCE_ID:
            raise SystemExit("RAH state is neither pre-seal nor the exact sealed result")
        generation = current
        if payloads["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
            raise SystemExit("stored E0061 summary differs from current DAG artifacts")
    result = m03_seal.verify_generation_store(61)
    if result["latest_evidence_id"] != EXPECTED_EVIDENCE_ID:
        raise SystemExit("DAG evidence is not the live RAH tail")
    result["generation"] = generation
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
