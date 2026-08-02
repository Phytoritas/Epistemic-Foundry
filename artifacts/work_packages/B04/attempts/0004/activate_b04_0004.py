#!/usr/bin/env python3
"""Activate B04-0004 after the product-owner mechanism correction decision."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[5]
AUTOMATION = ROOT / ".rah/helpers/recursive-architecture-refactoring-auto/automation"
sys.path.insert(0, str(AUTOMATION))

import ralph_harness as rh  # noqa: E402
import state_store  # noqa: E402


EXPECTED_PARENT = "000038-73e31b8e"
EXPECTED_EVIDENCE_ID = "E0041"
DECISION_ID = "HD-EF4-B04-MECH-CORRECTION-20260729-001"
DECISION_HASH = "sha256:98b71e0bc2370c08b5f1ef49f173b86ca9b454e907048e32e464ed2b40edf750"
DECISION_FILE_SHA256 = "568952999c5805be9499f9351491483fa3f0ea339e5c971fbfd0731671a9d9b6"
OBJECTIVE = (
    "Continue Epistemic Foundry v4.0.0 under product-owner decision "
    f"{DECISION_ID}. Preserve B04-0003 as immutable FAIL history and preserve "
    "all prior F01/B04 attempts, HumanDecisions, RAH evidence and generations, "
    "reports, reviews, commands, and the dirty worktree. In the primary session "
    "without Fleet or subagents, execute B04-0004 to correct B04-MECH001 through "
    "B04-MECH006 only in the authorized B04 surfaces. Keep schemas/**, openapi/**, "
    "and pyproject.toml read-only. Start F01-0003 only after verified B04-0004 "
    "PASS; start F02 or F03 only after verified F01 PASS. Keep completion_ready "
    "false until the full external goal is actually complete."
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evidence_ids(payloads: dict[str, object]) -> list[str]:
    ledger = payloads["evidence_ledger.json"]
    if not isinstance(ledger, dict) or not isinstance(ledger.get("entries"), list):
        raise SystemExit("invalid evidence ledger")
    return [str(row.get("id")) for row in ledger["entries"] if isinstance(row, dict)]


def verify_decision() -> None:
    path = ROOT / f"artifacts/authority_decisions/{DECISION_ID}.human-decision.json"
    if sha256(path) != DECISION_FILE_SHA256:
        raise SystemExit("HumanDecision file hash mismatch")
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = payload.pop("decision_hash")
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    actual = "sha256:" + hashlib.sha256(canonical).hexdigest()
    if expected != DECISION_HASH or actual != DECISION_HASH:
        raise SystemExit("HumanDecision canonical hash mismatch")


def main() -> int:
    verify_decision()
    ralph_root = ROOT / ".rah/ralph"
    current = state_store.read_current(ralph_root)
    if current is None:
        raise SystemExit("no committed RAH generation")
    parent, payloads = current
    if parent != EXPECTED_PARENT:
        raise SystemExit(f"unexpected parent generation {parent}")
    if evidence_ids(payloads) != [f"E{index:04d}" for index in range(1, 41)]:
        raise SystemExit("expected preserved E0001-E0040")

    now = rh.utc_now()
    goal = copy.deepcopy(payloads["goal.json"])
    loop = copy.deepcopy(payloads["loop_state.json"])
    ledger = copy.deepcopy(payloads["evidence_ledger.json"])
    evidence_id = rh.add_evidence_entry(
        ledger,
        now=now,
        goal_id=goal["goal_id"],
        iteration=int(loop.get("current_iteration") or 1),
        kind="decision",
        summary=(
            f"B04-0003 mechanism blocker resolved prospectively by {DECISION_ID} "
            f"({DECISION_HASH}); the decision authorizes B04-0004 to correct "
            "B04-MECH001 through B04-MECH006 in the exact existing B04 generator, "
            "packaging-test, runtime-registry, derived-snapshot, and evidence "
            "surfaces. Root schemas/openapi and pyproject remain read-only; "
            "B04-0003/E0039/E0040 and all prior history remain immutable; F01-0003 "
            "waits for B04-0004 PASS and F02/F03 wait for F01 PASS; "
            "completion_ready=false."
        ),
    )
    if evidence_id != EXPECTED_EVIDENCE_ID:
        raise SystemExit(f"unexpected evidence ID {evidence_id}")

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
                "Correct all six B04 projection-mechanism defects within the exact authorized surfaces.",
                "Run projection, packaging, installed-wheel, reproducibility, regression, receipt, and separate primary-session review gates before B04-0004 PASS.",
                "Start F01-0003 only after B04-0004 PASS; keep F02/F03 waiting until F01 PASS.",
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
    loop["progress_update"] = {
        "created_evidence": [evidence_id],
        "used_evidence": [evidence_id, "E0039", "E0040"],
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
        SimpleNamespace(goal_status="blocked", goal_objective=OBJECTIVE),
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

    status_path = ROOT / ".rah/state/status.json"
    gates_path = ROOT / ".rah/state/gates.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    gates = json.loads(gates_path.read_text(encoding="utf-8"))
    status["implementation_gate"] = "pass"
    status["implementation_gate_note"] = (
        f"{DECISION_ID} authorizes B04-0004; B04-0003 remains immutable FAIL and "
        "completion_ready remains false."
    )
    gates["implementation_gate"] = {
        "status": "pass",
        "note": "B04-0004 is active within the exact mechanism-correction boundary.",
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
    retained = sorted(
        path.name
        for path in (ralph_root / "generations").iterdir()
        if path.is_dir() and re.fullmatch(r"\d{6}-[0-9a-f]{8}", path.name)
    )
    if len(retained) != 39 or retained[-1] != generation:
        raise SystemExit("generation preservation failed")
    print(
        json.dumps(
            {
                "parent_generation": parent,
                "generation": generation,
                "generation_store": verified,
                "evidence_id": evidence_id,
                "evidence_high_water": ledger["issued_id_high_water"],
                "retained_generation_count": len(retained),
                "rah_status": loop["status"],
                "external_goal_observation": "blocked",
                "completion_ready": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
