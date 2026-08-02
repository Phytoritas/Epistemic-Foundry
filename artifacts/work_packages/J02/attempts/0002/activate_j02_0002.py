#!/usr/bin/env python3
"""Activate J02-0002 after the J02-SG001 product-owner decision.

The transition is deliberately fail-closed: it accepts only the exact sealed
J02-0001 generation and evidence ledger, appends one decision record, preserves
all generations, and keeps the external completion gate false.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any


ROOT = Path(__file__).resolve().parents[5]
AUTOMATION = ROOT / ".rah/helpers/recursive-architecture-refactoring-auto/automation"
sys.dont_write_bytecode = True
sys.path.insert(0, str(AUTOMATION))

import ralph_harness as rh  # noqa: E402
import state_store  # noqa: E402


EXPECTED_PARENT = "000077-1473ad4c"
EXPECTED_GENERATION_COUNT = 77
EXPECTED_EVIDENCE_ID = "E0081"
DECISION_ID = "HD-EF4-J02-SG001-20260729-001"
DECISION_HASH = "sha256:c44c9bb6a398637f3773fcfa6b832215dfd586670a848ad13809a98d7f006d25"
DECISION_FILE_SHA256 = "c075acdf1e1123a4bab7cccb9966db9a5fba88c9f070ca0c91dff69cbef94f1a"
J02_0001_REPORT_SHA256 = "6b0f4f37acbe1014afcf17ef5449fa4ed799e7ca0e7ea7523c014a3a44607688"
J02_0001_DEPENDENCY_SHA256 = "20f5799699aa64091f8e3c971bb47e38a82d5035b949e109ad4939e0810c0783"
OBJECTIVE = (
    "Continue Epistemic Foundry v4.0.0 under product-owner decision "
    f"{DECISION_ID}. Preserve J02-0001 as immutable SPEC_GAP history and "
    "preserve every prior attempt, HumanDecision, RAH evidence and generation, "
    "report, review, command record, and the dirty worktree. In the primary "
    "session without Fleet or subagents, execute J02-0002 within its exact "
    "inventory, production-skill metadata, progressive-reference, skill-context "
    "runtime, token-counter, fixture, test, documentation, manifest, and evidence "
    "scope. Keep J01 routing and J03 ContextCapsule code unchanged. Start J04 "
    "only after both J02 and J03 pass. Keep completion_ready false until the "
    "full external goal is actually complete."
)


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


def generation_names(ralph_root: Path) -> list[str]:
    return sorted(
        path.name
        for path in (ralph_root / "generations").iterdir()
        if path.is_dir() and re.fullmatch(r"\d{6}-[0-9a-f]{8}", path.name)
    )


def evidence_ids(payloads: dict[str, Any]) -> list[str]:
    ledger = payloads.get("evidence_ledger.json")
    if not isinstance(ledger, dict) or not isinstance(ledger.get("entries"), list):
        raise SystemExit("invalid evidence ledger")
    return [str(row.get("id")) for row in ledger["entries"] if isinstance(row, dict)]


def verify_decision_and_history() -> None:
    decision_path = ROOT / f"artifacts/authority_decisions/{DECISION_ID}.human-decision.json"
    if sha256(decision_path) != DECISION_FILE_SHA256:
        raise SystemExit("HumanDecision file hash mismatch")
    decision = read_json(decision_path)
    asserted = decision.pop("decision_hash", None)
    canonical = json.dumps(
        decision, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    computed = "sha256:" + hashlib.sha256(canonical).hexdigest()
    if asserted != DECISION_HASH or computed != DECISION_HASH:
        raise SystemExit("HumanDecision canonical hash mismatch")

    report = ROOT / "artifacts/work_packages/J02/attempts/0001/report.json"
    dependency = ROOT / "artifacts/work_packages/J02/attempts/0001/dependency-status.json"
    if sha256(report) != J02_0001_REPORT_SHA256:
        raise SystemExit("J02-0001 report seal mismatch")
    if sha256(dependency) != J02_0001_DEPENDENCY_SHA256:
        raise SystemExit("J02-0001 dependency seal mismatch")


def verify_store(ralph_root: Path, expected_count: int, expected_current: str) -> dict[str, Any]:
    current = state_store.read_current(ralph_root)
    if current is None or current[0] != expected_current:
        raise SystemExit("RAH current pointer mismatch")
    payloads = current[1]
    generations = generation_names(ralph_root)
    if len(generations) != expected_count or generations[-1] != expected_current:
        raise SystemExit("RAH generation preservation mismatch")

    verified_files = 0
    for generation in generations:
        directory = ralph_root / "generations" / generation
        manifest = read_json(directory / "generation-manifest.json")
        files = manifest.get("files")
        if manifest.get("generation") != generation or not isinstance(files, dict):
            raise SystemExit(f"invalid generation manifest: {generation}")
        if set(files) != set(state_store.GENERATION_FILES):
            raise SystemExit(f"generation file set mismatch: {generation}")
        for name in state_store.GENERATION_FILES:
            if sha256(directory / name) != files[name]:
                raise SystemExit(f"generation content hash mismatch: {generation}/{name}")
            verified_files += 1

    flat_stamps = 0
    flat_matches = 0
    for name in state_store.GENERATION_FILES:
        flat = read_json(ralph_root / name)
        if flat.get("state_generation") == expected_current:
            flat_stamps += 1
        stripped = {key: value for key, value in flat.items() if key != "state_generation"}
        authority = payloads[name]
        if isinstance(authority, dict):
            authority = {
                key: value for key, value in authority.items() if key != "state_generation"
            }
        if state_store._dump(stripped) == state_store._dump(authority):
            flat_matches += 1
    if flat_stamps != 6 or flat_matches != 6:
        raise SystemExit("RAH flat snapshot verification mismatch")
    return {
        "generation": expected_current,
        "retained_generation_count": len(generations),
        "generation_file_hashes_verified": verified_files,
        "flat_snapshot_stamps_verified": flat_stamps,
        "flat_snapshot_content_matches": flat_matches,
    }


def main() -> int:
    verify_decision_and_history()
    ralph_root = ROOT / ".rah/ralph"
    current = state_store.read_current(ralph_root)
    if current is None:
        raise SystemExit("no committed RAH generation")
    parent, payloads = current
    if parent != EXPECTED_PARENT:
        raise SystemExit(f"unexpected parent generation: {parent}")
    verify_store(ralph_root, EXPECTED_GENERATION_COUNT, EXPECTED_PARENT)
    if evidence_ids(payloads) != [f"E{index:04d}" for index in range(1, 81)]:
        raise SystemExit("activation requires preserved E0001-E0080")
    ledger_before = payloads["evidence_ledger.json"]
    if ledger_before.get("issued_id_high_water") != 80:
        raise SystemExit("activation requires evidence high-water E0080")
    loop_before = payloads["loop_state.json"]
    if (
        loop_before.get("status") != "blocked"
        or "J02-SG001" not in str(loop_before.get("blocked_reason"))
        or loop_before.get("completion_readiness", {}).get("ready") is not False
    ):
        raise SystemExit("activation requires the exact blocked J02-SG001 state")

    now = rh.utc_now()
    goal = copy.deepcopy(payloads["goal.json"])
    loop = copy.deepcopy(loop_before)
    ledger = copy.deepcopy(ledger_before)
    evidence_id = rh.add_evidence_entry(
        ledger,
        now=now,
        goal_id=goal["goal_id"],
        iteration=int(loop.get("current_iteration") or 1),
        kind="decision",
        summary=(
            f"J02-SG001 resolved_by {DECISION_ID} ({DECISION_HASH}), which "
            "authorizes only J02-0002 and fixes the exact 29-skill inventory, "
            "metadata and activation budgets, tiktoken 0.13.0 o200k_base "
            "accounting, 17-reference graph, deterministic typed selection and "
            "topological loading, fail-closed filesystem/freshness rules, J02 "
            "runtime ownership, exact fixtures, and acceptance oracles. J02-0001, "
            "E0078-E0080, all earlier generations and evidence, and the dirty "
            "worktree remain immutable; J03 remains independently dependency-ready, "
            "J04 waits on J02 and J03, subagents/Fleet remain forbidden, and "
            "completion_ready=false."
        ),
    )
    if evidence_id != EXPECTED_EVIDENCE_ID:
        raise SystemExit(f"unexpected evidence ID: {evidence_id}")

    goal.update({"goal": OBJECTIVE, "status": "active", "updated_at_utc": now})
    loop.update(
        {
            "generated_at_utc": now,
            "updated_at_utc": now,
            "goal": OBJECTIVE,
            "status": "active",
            "done": False,
            "loop_phase": "bounded-implementation",
            "implementation_gate": "pass",
            "current_stage": "ralph-active",
            "harness_phase": "execution",
            "blocked_reason": None,
            "checkpoint_required": False,
            "mark_done_rejected": False,
            "next_actions": [
                "Implement J02-0002 only within the exact authorized J02 surfaces.",
                "Run the exact budget, reachability, J01 regression, full regression, integrity, write-scope, and separate-review gates.",
                "Do not start J04 until both J02 and J03 independently pass; keep completion_ready false.",
            ],
        }
    )
    readiness = loop.get("completion_readiness")
    if not isinstance(readiness, dict) or readiness.get("ready") is not False:
        raise SystemExit("completion readiness must remain false")
    readiness["evidence_count"] = len(ledger["entries"])
    loop["state_machine"] = {
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
        "current_state": "act",
        "allowed_next_states": ["verify", "plan", "blocked", "failed"],
    }
    loop["stagnation"] = {
        "last_loop_phase": "bounded-implementation",
        "same_phase_without_evidence_count": 0,
        "pivot_required": False,
        "pivot_reason": None,
    }
    loop["progress_update"] = {
        "created_evidence": [evidence_id],
        "used_evidence": [evidence_id, "E0078", "E0079", "E0080"],
        "missing_evidence_ids": [],
        "missing_acceptance_ids": [],
        "missing_validation_ids": [],
        "missing_closeout_ids": [],
    }

    plan = rh.build_plan_graph(goal, loop, payloads["plan_graph.json"], now)
    for node in plan.get("nodes", []):
        if node.get("id") == "N3":
            node["status"] = "active"
        elif node.get("status") == "active":
            node["status"] = "pending"
    plan["active_node"] = "N3"
    bridge = rh.build_goal_bridge(
        ROOT,
        goal,
        loop,
        payloads["goal_bridge.json"],
        SimpleNamespace(goal_status="active", goal_objective=OBJECTIVE),
        now,
    )
    review = copy.deepcopy(payloads["review_gate.json"])
    review.update({"status": "not_requested", "attempts": [], "updated_at_utc": now})

    state_store.KEEP_GENERATIONS = 10_000
    generation = state_store.commit_generation(
        ralph_root,
        {
            "goal.json": goal,
            "loop_state.json": loop,
            "evidence_ledger.json": ledger,
            "plan_graph.json": plan,
            "goal_bridge.json": bridge,
            "review_gate.json": review,
        },
    )

    status_path = ROOT / ".rah/state/status.json"
    gates_path = ROOT / ".rah/state/gates.json"
    status = read_json(status_path)
    gates = read_json(gates_path)
    status["implementation_gate"] = "pass"
    status["implementation_gate_note"] = (
        f"{DECISION_ID} authorizes J02-0002; J02-0001 remains immutable "
        "SPEC_GAP history and completion_ready remains false."
    )
    gates["implementation_gate"] = {
        "status": "pass",
        "note": "J02-0002 is active within the exact product-owner contract.",
        "evidence_ids": [evidence_id],
    }
    rh.write_json(status_path, status)
    rh.write_json(gates_path, gates)
    rh.refresh_status_for_ralph(ROOT, ROOT / ".rah", goal, loop, now)
    rh.upsert_current_loop(
        ROOT / ".rah/plans/current_loop.md", rh.render_managed_current_loop(goal, loop)
    )
    rh.write_text(ralph_root / "blockers.md", rh.render_blockers(goal, loop, now))

    verified = state_store.verify_current(ralph_root)
    integrity = verify_store(ralph_root, EXPECTED_GENERATION_COUNT + 1, generation)
    if evidence_ids(state_store.read_current(ralph_root)[1])[-1] != EXPECTED_EVIDENCE_ID:
        raise SystemExit("latest evidence is not E0081")
    print(
        json.dumps(
            {
                "parent_generation": parent,
                "generation": generation,
                "generation_store": verified,
                "integrity": integrity,
                "evidence_id": evidence_id,
                "evidence_high_water": ledger["issued_id_high_water"],
                "rah_status": loop["status"],
                "completion_ready": False,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
