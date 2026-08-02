#!/usr/bin/env python3
"""Atomically resume the retained RALPH ledger after C01-SG003 resolution.

This transition is intentionally fail-closed. It accepts only the exact
blocked generation produced after E0005 was appended, preserves every prior
generation by disabling pruning for this commit, and changes no historical
evidence entry. The product-owner decision authorizes the blocked-to-active
transition; it does not make the overall goal completion-ready.
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


EXPECTED_PARENT = "000003-42a86d6d"
EXPECTED_EVIDENCE_IDS = ["E0001", "E0002", "E0003", "E0004", "E0005"]
DECISION_ID = "HD-EF4-C01-SG003-20260728-001"
OBJECTIVE = (
    "Resume Epistemic Foundry v4.0.0 under product-owner decision "
    "HD-EF4-C01-SG003-20260728-001. Preserve every prior A05/C01 SPEC_GAP, "
    "HumanDecision, RAH evidence and generation, report, review, command, and "
    "the dirty worktree. Execute serially in the primary session without Fleet "
    "or subagents: C01-0004, C01 contract review and PASS, C02 generation and "
    "review, C03 runtime migration and review, C04 full-suite conformance review "
    "and PASS, B04 packaging review and PASS, full 156-package DAG recomputation, "
    "then continue dependency-ready packages under MASTER_SPEC.md and the "
    "manifests until verified RALPH terminal."
)


def main() -> int:
    ralph_root = ROOT / ".rah" / "ralph"
    current = state_store.read_current(ralph_root)
    if current is None:
        raise SystemExit("No committed RALPH generation")
    previous_generation, payloads = current
    if previous_generation != EXPECTED_PARENT:
        raise SystemExit(
            f"Unexpected RALPH parent generation: {previous_generation}; "
            f"expected {EXPECTED_PARENT}"
        )

    ledger = payloads["evidence_ledger.json"]
    evidence_ids = [entry.get("id") for entry in ledger.get("entries", [])]
    if evidence_ids != EXPECTED_EVIDENCE_IDS:
        raise SystemExit(
            f"Unexpected evidence ledger {evidence_ids!r}; refusing transition"
        )
    if DECISION_ID not in str(ledger["entries"][-1].get("summary")):
        raise SystemExit("C01-SG003 resolution evidence is missing")
    if ledger.get("issued_id_high_water") != 5:
        raise SystemExit("Evidence high-water mark must be E0005")

    now = rh.utc_now()
    goal = copy.deepcopy(payloads["goal.json"])
    goal.update({"goal": OBJECTIVE, "status": "active", "updated_at_utc": now})

    loop = copy.deepcopy(payloads["loop_state.json"])
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
                "Execute C01-0004 within the exact C01 canonical-contract write scope.",
                "Record the identical 24 runtime migration failures as C03-owned expected debt; fail C01 on any new or changed fingerprint.",
                "Complete C01 review and evidence before starting C02; do not start B04 before C04 PASS.",
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
    loop["stagnation"] = {
        "last_loop_phase": "bounded-implementation",
        "same_phase_without_evidence_count": 0,
        "pivot_required": False,
        "pivot_reason": None,
    }
    loop["progress_update"] = {
        "created_evidence": [],
        "used_evidence": ["E0005"],
        "missing_evidence_ids": [],
        "missing_acceptance_ids": [],
        "missing_validation_ids": [],
        "missing_closeout_ids": [],
    }

    external = loop.get("external_driver_contract")
    if isinstance(external, dict):
        external["command"] = (
            f'python <active-skill-root>/automation/rah.py drive "{ROOT}" '
            f'--goal "{OBJECTIVE}" --completion-mode exhaustive'
        )
    recipes = loop.get("command_recipes")
    if isinstance(recipes, dict):
        recipes["ralph"] = (
            f'python <active-skill-root>/automation/rah.py ralph "{ROOT}" '
            f'--goal "{OBJECTIVE}"'
        )

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
    review["updated_at_utc"] = now

    # The product owner requires all prior RAH generations to remain available.
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
        "C01-SG003 resolved by HD-EF4-C01-SG003-20260728-001; "
        "C01-0004 is ready and completion_ready remains false."
    )
    gates["implementation_gate"] = {
        "status": "pass",
        "note": (
            "C01-0004 authorized by HD-EF4-C01-SG003-20260728-001; "
            "the exact C01/C02/C03/C04/B04 ordering remains mandatory."
        ),
        "evidence_ids": ["E0005"],
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
        if path.is_dir()
    )
    expected_retained = [
        "000001-8cce4954",
        "000002-e90aad20",
        "000003-42a86d6d",
        generation,
    ]
    if retained != expected_retained:
        raise SystemExit(
            f"Generation preservation failed: {retained!r} != {expected_retained!r}"
        )

    print(
        json.dumps(
            {
                "previous_generation": previous_generation,
                "new_generation": generation,
                "generation_store": verified,
                "goal_status": goal["status"],
                "loop_status": loop["status"],
                "completion_ready": loop["completion_readiness"]["ready"],
                "evidence_high_water": ledger["issued_id_high_water"],
                "retained_generations": retained,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
