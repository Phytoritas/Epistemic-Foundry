#!/usr/bin/env python3
"""Resume the retained RAH ledger after the F01-SG001 HumanDecision.

The transition is fail-closed and prospective.  It appends one decision
evidence row, retains every prior generation and blocker, moves the external
goal from blocked to active, and leaves completion readiness false.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[5]
AUTOMATION = (
    ROOT
    / ".rah"
    / "helpers"
    / "recursive-architecture-refactoring-auto"
    / "automation"
)
sys.path.insert(0, str(AUTOMATION))

import ralph_harness as rh  # noqa: E402
import state_store  # noqa: E402


EXPECTED_PARENT = "000032-87deb23f"
EXPECTED_EVIDENCE_IDS = [f"E{index:04d}" for index in range(1, 34)]
DECISION_ID = "HD-EF4-F01-SG001-20260729-001"
DECISION_HASH = "sha256:1b6fa81c62d8d34162679496a2459f9634670598f980feecfdc1c957a61e1383"
OBJECTIVE = (
    "Continue Epistemic Foundry v4.0.0 under product-owner decision "
    "HD-EF4-F01-SG001-20260729-001. Preserve F01-0001 SPEC_GAP, every prior "
    "HumanDecision, RAH evidence and generation, report, review, command, and "
    "the dirty worktree. Execute F01-0002 in the primary session without "
    "Fleet or subagents, complete deterministic gold, underprocessing, replay, "
    "override, workflow, full regression and separate review gates, then "
    "recompute the 156-package DAG and continue the earliest dependency-ready "
    "package under MASTER_SPEC.md and the manifests until verified terminal."
)


def main() -> int:
    ralph_root = ROOT / ".rah" / "ralph"
    current = state_store.read_current(ralph_root)
    if current is None:
        raise SystemExit("No committed RAH generation")
    previous_generation, payloads = current
    if previous_generation != EXPECTED_PARENT:
        raise SystemExit(
            f"Unexpected RAH parent {previous_generation}; expected {EXPECTED_PARENT}"
        )

    ledger = copy.deepcopy(payloads["evidence_ledger.json"])
    evidence_ids = [entry.get("id") for entry in ledger.get("entries", [])]
    if evidence_ids != EXPECTED_EVIDENCE_IDS:
        raise SystemExit("Unexpected or non-contiguous evidence ledger")
    if ledger.get("issued_id_high_water") != 33:
        raise SystemExit("Evidence high-water must be E0033")
    if "F01-SG001" not in str(ledger["entries"][-2].get("summary")):
        raise SystemExit("F01-SG001 blocker evidence is not the expected history")

    now = rh.utc_now()
    goal = copy.deepcopy(payloads["goal.json"])
    loop = copy.deepcopy(payloads["loop_state.json"])
    evidence_id = rh.add_evidence_entry(
        ledger,
        now=now,
        goal_id=goal["goal_id"],
        iteration=int(loop.get("iteration") or 1),
        kind="decision",
        summary=(
            f"F01-SG001 resolved_by {DECISION_ID} ({DECISION_HASH}), which "
            "authorizes F01-0002 and fixes deterministic Kernel authority, the "
            "closed signal vocabulary, maximum-floor and monotonic protection "
            "rules, exact projections and Interview routing, hash/retry/replay/"
            "immutable-override semantics, workflow binding, and exact acceptance "
            "oracles. F01-0001 and all prior evidence remain immutable; "
            "completion_ready=false."
        ),
    )
    if evidence_id != "E0034":
        raise SystemExit(f"Unexpected evidence ID {evidence_id}")

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
                "Execute F01-0002 within the exact product-owner-authorized paths.",
                "Pass deterministic gold, exhaustive underprocessing, schema, workflow, replay, override, and regression gates.",
                "Perform a separate primary-session adversarial review, seal F01 evidence, then recompute the 156-package DAG.",
            ],
        }
    )
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
        "allowed_next_states": ["verify", "plan", "blocked"],
    }
    loop["progress_update"] = {
        "created_evidence": [evidence_id],
        "used_evidence": [evidence_id, "E0032", "E0033"],
        "missing_evidence_ids": [],
        "missing_acceptance_ids": [],
        "missing_validation_ids": [],
        "missing_closeout_ids": [],
    }

    plan = rh.build_plan_graph(goal, loop, payloads["plan_graph.json"], now)
    bridge = rh.build_goal_bridge(
        ROOT,
        goal,
        loop,
        payloads["goal_bridge.json"],
        SimpleNamespace(goal_status="active", goal_objective=OBJECTIVE),
        now,
    )
    review = copy.deepcopy(payloads["review_gate.json"])
    review["updated_at_utc"] = now

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

    status_path = ROOT / ".rah" / "state" / "status.json"
    gates_path = ROOT / ".rah" / "state" / "gates.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    gates = json.loads(gates_path.read_text(encoding="utf-8"))
    status["implementation_gate"] = "pass"
    status["implementation_gate_note"] = (
        f"F01-SG001 resolved by {DECISION_ID}; F01-0002 is active and "
        "completion_ready remains false."
    )
    gates["implementation_gate"] = {
        "status": "pass",
        "note": (
            f"F01-0002 authorized by {DECISION_ID}; deterministic F01 gates and "
            "history preservation remain mandatory."
        ),
        "evidence_ids": [evidence_id],
    }
    rh.write_json(status_path, status)
    rh.write_json(gates_path, gates)
    rh.refresh_status_for_ralph(ROOT, ROOT / ".rah", goal, loop, now)
    rh.upsert_current_loop(
        ROOT / ".rah" / "plans" / "current_loop.md",
        rh.render_managed_current_loop(goal, loop),
    )

    verified = state_store.verify_current(ralph_root)
    retained = sorted(
        path.name
        for path in (ralph_root / "generations").iterdir()
        if path.is_dir() and path.name[:6].isdigit()
    )
    if len(retained) != 33 or retained[-1] != generation:
        raise SystemExit("RAH generation preservation failed")

    print(
        json.dumps(
            {
                "previous_generation": previous_generation,
                "new_generation": generation,
                "generation_store": verified,
                "goal_status": goal["status"],
                "loop_status": loop["status"],
                "completion_ready": loop["completion_readiness"]["ready"],
                "evidence_id": evidence_id,
                "evidence_high_water": ledger["issued_id_high_water"],
                "retained_generation_count": len(retained),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
