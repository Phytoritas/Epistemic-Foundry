#!/usr/bin/env python3
"""Resume retained RAH state after HD-EF4-F01-SG002-20260729-001.

This prospective transition appends one decision relation, preserves every
prior generation and evidence row, marks the external goal active/resumable,
and keeps completion readiness false. It does not start or pass B04-0003.
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


EXPECTED_PARENT = "000035-80b64468"
EXPECTED_EVIDENCE_IDS = [f"E{index:04d}" for index in range(1, 38)]
DECISION_ID = "HD-EF4-F01-SG002-20260729-001"
DECISION_HASH = "sha256:923e5b94303626de6aceb41cedfbf405c3037828fb160e2645ac4ac4fc564eea"
OBJECTIVE = (
    "Continue Epistemic Foundry v4.0.0 under product-owner decision "
    "HD-EF4-F01-SG002-20260729-001. Preserve F01-0002 SPEC_GAP, all prior "
    "B04 attempts, HumanDecisions, RAH evidence and generations, reports, "
    "reviews, commands, and the dirty worktree. In the primary session without "
    "Fleet or subagents, execute B04-0003 as the bounded canonical projection "
    "correction. Start F01-0003 only after verified B04 PASS; start F02 or F03 "
    "only after verified F01 PASS. Keep S04-TM004 separate and completion_ready "
    "false until the full external goal is actually complete."
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
    if ledger.get("issued_id_high_water") != 37:
        raise SystemExit("Evidence high-water must be E0037")
    if "F01-SG002" not in str(ledger["entries"][-1].get("summary")):
        raise SystemExit("F01-SG002 closeout is not the expected retained history")

    now = rh.utc_now()
    goal = copy.deepcopy(payloads["goal.json"])
    loop = copy.deepcopy(payloads["loop_state.json"])
    evidence_id = rh.add_evidence_entry(
        ledger,
        now=now,
        goal_id=goal["goal_id"],
        iteration=int(loop.get("iteration") or loop.get("current_iteration") or 1),
        kind="decision",
        summary=(
            f"F01-SG002 resolved_by {DECISION_ID} ({DECISION_HASH}); the decision "
            "assigns canonical projection ownership to B04, binds root authority "
            "to schemas/** and openapi/**, records F01-0002 requires_correction "
            "B04-0003 and B04-0003 unblocks F01-0003 only on PASS, preserves the "
            "package-level DAG and S04-TM004 separation, and leaves F02/F03 "
            "waiting on F01. All prior evidence remains immutable; "
            "completion_ready=false."
        ),
    )
    if evidence_id != "E0038":
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
                "Execute B04-0003 within the exact correction boundary and preserve root canonical sources.",
                "Require the deterministic projection, registry, atomicity, packaging, regression, receipt, and review gates before B04 PASS.",
                "Start F01-0003 only after B04 PASS; keep F02 and F03 waiting until F01 PASS.",
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
        "allowed_next_states": ["verify", "plan", "blocked", "failed"],
    }
    loop["progress_update"] = {
        "created_evidence": [evidence_id],
        "used_evidence": [evidence_id, "E0036", "E0037"],
        "missing_evidence_ids": [],
        "missing_acceptance_ids": [],
        "missing_validation_ids": [],
        "missing_closeout_ids": [],
    }

    readiness = loop.get("completion_readiness")
    if not isinstance(readiness, dict) or readiness.get("ready") is not False:
        raise SystemExit("Completion readiness must remain explicitly false")

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
        f"F01-SG002 resolved by {DECISION_ID}; B04-0003 is ready, F01 waits "
        "for projection PASS, and completion_ready remains false."
    )
    gates["implementation_gate"] = {
        "status": "pass",
        "note": (
            f"B04-0003 authorized by {DECISION_ID}; B04 correction must PASS "
            "before F01-0003 and F01 must PASS before F02/F03."
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
    if len(retained) != 36 or retained[-1] != generation:
        raise SystemExit("RAH generation preservation failed")
    if any(item not in retained for item in [EXPECTED_PARENT, generation]):
        raise SystemExit("Expected parent or new generation is missing")

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
