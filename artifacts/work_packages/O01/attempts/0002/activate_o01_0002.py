#!/usr/bin/env python3
"""Activate O01-0002 after the O01-SG001 product-owner decision.

This transition is deliberately fail-closed.  It accepts only the exact
sealed O01-0001 RAH state, verifies the product-owner decision and immutable
attempt artifacts, appends one decision evidence record, enables the durable
source/PRD completion gates, preserves every generation, and keeps global
completion false while the bounded O01 implementation runs.
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


EXPECTED_PARENT = "000079-344cd519"
EXPECTED_PARENT_MANIFEST_SHA256 = (
    "ba09d5ae424d1c5943e764eeb34b37c664fb163cc7aeb624d1f374b0803474c7"
)
EXPECTED_GENERATION_COUNT = 79
EXPECTED_EVIDENCE_ID = "E0080"
DECISION_ID = "HD-EF4-O01-SG001-20260731-001"
DECISION_HASH = "sha256:7147e54c609744ff4f043be9f0407382e36636e3afc2a4dbfa59afc19e1a6265"
DECISION_FILE_SHA256 = (
    "a0c60a09df0f77b2d7d0d7284cdaf8d8d950310c77194929476821617e5f5324"
)
O01_0001_HASHES = {
    "report.json": "dd0dde5f427ea625e28c2f86c2000f24f45aa13186e3ed2fcc7be297fa5840df",
    "shared-contract-gap-verification.json": (
        "25eec4945ebfe09d8155c6a805a8c694485aa2ef1cf6ffcae55c337a34c279bc"
    ),
    "dependency-status.json": (
        "98db84df175ae4daa93556285bc2199c8859761e597b866f202c44a3eed66d41"
    ),
    "review.md": "70d495094cd6d3e6818f536dc7552fca27584832c0d94f7cdf7d4ead010ad4e7",
}
OBJECTIVE = (
    "Implement the complete Epistemic Foundry v4.0.0 specification from "
    "MASTER_EXECUTION_PROMPT.md and MASTER_SPEC.md under product-owner decision "
    f"{DECISION_ID}. Preserve O01-0001 as immutable SPEC_GAP history and "
    "preserve every prior attempt, HumanDecision, RAH evidence and generation, "
    "report, review, command record, and the dirty worktree. In the primary "
    "session without Fleet or subagents, execute O01-0002 within the exact "
    "canonical retrieval-lane, QueryPlan, SearchLaneReceipt, completeness, "
    "runtime, test, projection-reconciliation, and evidence boundaries; then "
    "recompute the 156-package DAG and continue the next dependency-ready "
    "package serially. Treat source coverage and the source-bound PRD as "
    "mandatory completion gates and keep completion_ready false until all "
    "source rows and objective gates are actually satisfied."
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
    if decision.get("decision_id") != DECISION_ID or decision.get("subject_id") != "O01-SG001":
        raise SystemExit("HumanDecision identity mismatch")

    attempt = ROOT / "artifacts/work_packages/O01/attempts/0001"
    for name, expected in O01_0001_HASHES.items():
        if sha256(attempt / name) != expected:
            raise SystemExit(f"O01-0001 immutable artifact hash mismatch: {name}")


def verify_store(
    ralph_root: Path, expected_count: int, expected_current: str
) -> dict[str, Any]:
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
    if sha256(ralph_root / "generations" / parent / "generation-manifest.json") != (
        EXPECTED_PARENT_MANIFEST_SHA256
    ):
        raise SystemExit("O01 parent generation manifest hash mismatch")
    verify_store(ralph_root, EXPECTED_GENERATION_COUNT, EXPECTED_PARENT)
    if evidence_ids(payloads) != [f"E{index:04d}" for index in range(1, 80)]:
        raise SystemExit("activation requires preserved E0001-E0079")
    ledger_before = payloads["evidence_ledger.json"]
    if ledger_before.get("issued_id_high_water") != 79:
        raise SystemExit("activation requires evidence high-water E0079")
    loop_before = payloads["loop_state.json"]
    if (
        loop_before.get("status") != "blocked"
        or "O01-SG001" not in str(loop_before.get("blocked_reason"))
        or loop_before.get("completion_readiness", {}).get("ready") is not False
    ):
        raise SystemExit("activation requires the exact blocked O01-SG001 state")

    now = rh.utc_now()
    goal = copy.deepcopy(payloads["goal.json"])
    loop = copy.deepcopy(loop_before)
    ledger = copy.deepcopy(ledger_before)
    review = copy.deepcopy(payloads["review_gate.json"])
    evidence_id = rh.add_evidence_entry(
        ledger,
        now=now,
        goal_id=goal["goal_id"],
        iteration=int(loop.get("current_iteration") or 1),
        kind="decision",
        summary=(
            f"O01-SG001 resolved_by {DECISION_ID} ({DECISION_HASH}), which "
            "prospectively authorizes only O01-0002 and freezes the eleven "
            "canonical retrieval lanes, exact monotonic E0-E5 class floors, "
            "non-waivable floor semantics, immutable classification binding, "
            "all-lane receipt reconciliation, six truthful receipt states, "
            "run-status precedence, and absence/novelty ceilings. O01-0001, "
            "E0079, all 79 prior generations and evidence, prior reports, and "
            "the dirty worktree remain immutable. Source coverage and the "
            "source-bound PRD are now mandatory completion gates; O02/O03 wait "
            "for O01 PASS, Fleet/subagents remain forbidden, and "
            "completion_ready=false."
        ),
    )
    if evidence_id != EXPECTED_EVIDENCE_ID:
        raise SystemExit(f"unexpected evidence ID: {evidence_id}")

    goal.update(
        {
            "goal": OBJECTIVE,
            "status": "active",
            "source_coverage_required": True,
            "prd_required": True,
            "updated_at_utc": now,
        }
    )
    review.update({"status": "not_requested", "attempts": [], "updated_at_utc": now})
    review.pop("current_attempt", None)
    review.pop("review_snapshot", None)

    source_coverage = rh.assess_source_coverage(ROOT, required=True)
    prd_projection = rh.assess_prd_projection(
        ROOT, required=True, source_coverage=source_coverage
    )
    completion_readiness = rh.assess_completion_readiness(
        goal, ledger, review, source_coverage, prd_projection
    )
    if not (
        source_coverage.get("present") is True
        and source_coverage.get("required") is True
        and source_coverage.get("ready") is False
        and source_coverage.get("total_rows") == 509
        and len(source_coverage.get("missing_ids", [])) == 509
        and not source_coverage.get("invalid_row_ids")
    ):
        raise SystemExit("unexpected mandatory source-coverage assessment")
    if not (
        prd_projection.get("present") is True
        and prd_projection.get("required") is True
        and prd_projection.get("audit_ready") is True
        and prd_projection.get("ready") is False
        and not prd_projection.get("unmapped_source_row_ids")
        and not prd_projection.get("unmapped_required_atom_ids")
    ):
        raise SystemExit("unexpected mandatory PRD assessment")
    if completion_readiness.get("ready") is not False:
        raise SystemExit("activation must not advance global completion")

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
            "source_coverage": source_coverage,
            "prd_projection": prd_projection,
            "completion_readiness": completion_readiness,
            "next_actions": [
                "Implement O01-0002 only within the exact product-owner-authorized surfaces.",
                "Run query-plan, receipt-completeness, schema/example, workflow, projection-reconciliation, regression, and separate-review gates.",
                "Do not start O02 or O03 until O01 passes; keep source/PRD gates required and completion_ready false.",
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
    loop["stagnation"] = {
        "last_loop_phase": "bounded-implementation",
        "same_phase_without_evidence_count": 0,
        "pivot_required": False,
        "pivot_reason": None,
    }
    loop["progress_update"] = {
        "created_evidence": [evidence_id],
        "used_evidence": [evidence_id, "E0078", "E0079"],
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
        f"{DECISION_ID} authorizes bounded O01-0002 implementation. Mandatory "
        "source/PRD coverage and all downstream packages remain incomplete; "
        "completion_ready remains false."
    )
    gates["implementation_gate"] = {
        "status": "pass",
        "note": (
            "O01-0002 is active within the exact product-owner contract; this "
            "bounded package authorization is not global completion."
        ),
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
    current_after = state_store.read_current(ralph_root)
    if current_after is None or evidence_ids(current_after[1])[-1] != EXPECTED_EVIDENCE_ID:
        raise SystemExit("latest evidence is not E0080")
    live_goal = current_after[1]["goal.json"]
    live_loop = current_after[1]["loop_state.json"]
    if live_goal.get("source_coverage_required") is not True or live_goal.get("prd_required") is not True:
        raise SystemExit("mandatory source/PRD flags were not persisted")
    if live_loop.get("completion_readiness", {}).get("ready") is not False:
        raise SystemExit("completion readiness was incorrectly promoted")
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
                "implementation_gate": loop["implementation_gate"],
                "source_coverage_required": True,
                "source_coverage_total_rows": source_coverage["total_rows"],
                "source_coverage_incomplete_rows": len(source_coverage["missing_ids"]),
                "prd_required": True,
                "prd_audit_ready": prd_projection["audit_ready"],
                "prd_ready": prd_projection["ready"],
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
