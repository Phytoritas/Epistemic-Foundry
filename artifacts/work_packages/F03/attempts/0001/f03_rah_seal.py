#!/usr/bin/env python3
"""Append F03-0001 core and closeout evidence without rewriting RAH history."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any


ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/F03/attempts/0001"
AUTOMATION = ROOT / ".rah/helpers/recursive-architecture-refactoring-auto/automation"
sys.path.insert(0, str(ATTEMPT))
sys.path.insert(0, str(AUTOMATION))

import f03_evidence as evidence  # noqa: E402
import ralph_harness as rh  # noqa: E402
import state_store  # noqa: E402


CORE_PARENT = "000045-c5959ddb"
CORE_EVIDENCE_ID = "E0048"
FINAL_EVIDENCE_ID = "E0049"
NEXT_ACTIONS = [
    "Start F04, the earliest manifest-order dependency-ready package, in the primary session.",
    "Keep G01, K01, and A06 dependency-ready but unstarted during serial F04 handling.",
    "Keep completion_ready false until the entire product objective is actually complete.",
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


def evidence_ids(payloads: dict[str, Any]) -> list[str]:
    ledger = payloads.get("evidence_ledger.json")
    if not isinstance(ledger, dict) or not isinstance(ledger.get("entries"), list):
        raise SystemExit("invalid RAH evidence ledger")
    return [str(row.get("id")) for row in ledger["entries"] if isinstance(row, dict)]


def numbered_generations(ralph_root: Path) -> list[str]:
    return sorted(
        path.name
        for path in (ralph_root / "generations").iterdir()
        if path.is_dir() and re.fullmatch(r"\d{6}-[0-9a-f]{8}", path.name)
    )


def current_state() -> tuple[Path, str, dict[str, Any]]:
    ralph_root = ROOT / ".rah/ralph"
    current = state_store.read_current(ralph_root)
    if current is None:
        raise SystemExit("no committed RAH generation")
    generation, payloads = current
    verified = state_store.verify_current(ralph_root)
    if verified.get("generation") != generation:
        raise SystemExit("RAH current pointer and generation verification disagree")
    return ralph_root, generation, payloads


def core_summary() -> str:
    names = (
        "transition-receipt-verification.json",
        "override-provenance-verification.json",
        "full-regression-impact.json",
        "preexisting-debt-reconciliation.json",
        "phase-artifact-reconciliation.json",
        "dependency-status.json",
        "transition-receipt-verification.artifact-receipt.json",
        "targeted-node-suite.junit.xml",
        "full-node-suite.junit.xml",
        "full-python-suite.junit.xml",
        "review.md",
    )
    hashes = {name: sha256(ATTEMPT / name) for name in names}
    return (
        "F03-0001 PASS: deterministic transition admission requires byte-verified "
        "ArtifactReceipts, canonical IDLE classification evidence or a complete "
        "current PhaseArtifactSet, resolving GateDecisions, and explicit human "
        "provenance for waivable overrides. FAIL/BLOCK and non-waivable WAIVE "
        "remain fail-closed; admitted results are immutable FTA identities and do "
        "not mutate F02 state. F03 targeted Node is 21/21, combined F01/F02/F03 "
        "is 68/68, and full Python is 947/947; full Node is 305 passed plus only "
        "exact unchanged S04-TM004, with zero F03-caused failures or skips. "
        "Transition verification sha256:"
        f"{hashes['transition-receipt-verification.json']}; override verification sha256:"
        f"{hashes['override-provenance-verification.json']}; regression sha256:"
        f"{hashes['full-regression-impact.json']}; receipt sha256:"
        f"{hashes['transition-receipt-verification.artifact-receipt.json']}; review sha256:"
        f"{hashes['review.md']}. Primary-session separate contract review has zero "
        "blocking findings and is not actor-independent certification. All prior "
        "attempts, generations, and dirty-worktree content are preserved. The "
        "156-package DAG yields F04/G01/K01/A06 ready with F04 next; "
        "completion_ready=false."
    )


def final_summary(parent: str) -> tuple[str, dict[str, str]]:
    names = (
        "report.json",
        "review.md",
        "commands.jsonl",
        "transition-receipt-verification.json",
        "override-provenance-verification.json",
        "full-regression-impact.json",
        "preexisting-debt-reconciliation.json",
        "phase-artifact-reconciliation.json",
        "dependency-status.json",
        "transition-receipt-verification.artifact-receipt.json",
        "rah-core-integrity.json",
        "f03_evidence.py",
        "f03_rah_seal.py",
    )
    hashes = {name: sha256(ATTEMPT / name) for name in names}
    summary = (
        f"F03-0001 PASS closeout is hash-sealed after core generation {parent}: "
        f"report sha256:{hashes['report.json']}; review sha256:{hashes['review.md']}; "
        f"commands sha256:{hashes['commands.jsonl']}; transition verification sha256:"
        f"{hashes['transition-receipt-verification.json']}; override verification sha256:"
        f"{hashes['override-provenance-verification.json']}; regression sha256:"
        f"{hashes['full-regression-impact.json']}; dependency status sha256:"
        f"{hashes['dependency-status.json']}; receipt sha256:"
        f"{hashes['transition-receipt-verification.artifact-receipt.json']}; core RAH "
        f"integrity sha256:{hashes['rah-core-integrity.json']}; builder sha256:"
        f"{hashes['f03_evidence.py']}; sealer sha256:{hashes['f03_rah_seal.py']}. "
        "F03 is PASS; F01/F02 and all earlier history remain immutable; S04-TM004 "
        "remains separate S04-owned debt. F04/G01/K01/A06 are ready in manifest "
        "order with F04 next; completion_ready=false."
    )
    return summary, hashes


def commit_active_generation(
    *, payloads: dict[str, Any], summary: str, expected_evidence_id: str
) -> str:
    now = rh.utc_now()
    goal = copy.deepcopy(payloads["goal.json"])
    loop = copy.deepcopy(payloads["loop_state.json"])
    ledger = copy.deepcopy(payloads["evidence_ledger.json"])
    objective = str(goal.get("goal") or loop.get("goal") or "Continue Epistemic Foundry v4")
    identifier = rh.add_evidence_entry(
        ledger,
        now=now,
        goal_id=goal["goal_id"],
        iteration=int(loop.get("current_iteration") or 1),
        kind="evidence",
        summary=summary,
    )
    if identifier != expected_evidence_id:
        raise SystemExit(f"unexpected evidence ID {identifier}; expected {expected_evidence_id}")
    goal.update({"goal": objective, "status": "active", "updated_at_utc": now})
    loop.update(
        {
            "blocked_reason": None,
            "checkpoint_required": False,
            "current_stage": "ralph-active",
            "done": False,
            "generated_at_utc": now,
            "goal": objective,
            "harness_phase": "execution",
            "implementation_gate": "pass",
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
        "used_evidence": [identifier, "E0047", "E0046"],
    }
    plan = rh.build_plan_graph(goal, loop, payloads["plan_graph.json"], now)
    bridge = rh.build_goal_bridge(
        ROOT,
        goal,
        loop,
        payloads["goal_bridge.json"],
        SimpleNamespace(goal_status="paused", goal_objective=objective),
        now,
    )
    review = copy.deepcopy(payloads["review_gate.json"])
    review["updated_at_utc"] = now
    state_store.KEEP_GENERATIONS = 10_000
    generation = state_store.commit_generation(
        ROOT / ".rah/ralph",
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
        "F03-0001 is evidence-sealed PASS with receipt-bound transition admission "
        "and explicit override provenance; F04 is next and completion_ready remains false."
    )
    status["implementation_gate"] = "pass"
    status["implementation_gate_note"] = note
    status["next_recommended_action"] = NEXT_ACTIONS[0]
    gates["implementation_gate"] = {
        "evidence_ids": [CORE_EVIDENCE_ID, FINAL_EVIDENCE_ID]
        if expected_evidence_id == FINAL_EVIDENCE_ID
        else [CORE_EVIDENCE_ID],
        "note": note,
        "status": "pass",
    }
    rh.write_json(status_path, status)
    rh.write_json(gates_path, gates)
    rh.refresh_status_for_ralph(ROOT, ROOT / ".rah", goal, loop, now)
    rh.upsert_current_loop(
        ROOT / ".rah/plans/current_loop.md", rh.render_managed_current_loop(goal, loop)
    )
    rh.write_text(ROOT / ".rah/ralph/blockers.md", rh.render_blockers(goal, loop, now))
    return generation


def run_preflight() -> dict[str, Any]:
    evidence.verify_pre_core()
    ralph_root, generation, payloads = current_state()
    if generation != CORE_PARENT:
        raise SystemExit(f"unexpected F03 core parent: {generation}")
    if evidence_ids(payloads) != [f"E{index:04d}" for index in range(1, 48)]:
        raise SystemExit("preflight requires preserved E0001-E0047")
    generations = numbered_generations(ralph_root)
    if len(generations) != 45 or generations[-1] != generation:
        raise SystemExit("preflight requires all 45 prior RAH generations")
    if payloads["loop_state.json"].get("status") != "active":
        raise SystemExit("preflight requires active RAH status")
    return {
        "mode": "preflight",
        "generation": generation,
        "latest_evidence_id": "E0047",
        "retained_generation_count": len(generations),
        "completion_ready": False,
    }


def run_core() -> dict[str, Any]:
    run_preflight()
    ralph_root, parent, payloads = current_state()
    before = numbered_generations(ralph_root)
    generation = commit_active_generation(
        payloads=payloads, summary=core_summary(), expected_evidence_id=CORE_EVIDENCE_ID
    )
    _, current, sealed = current_state()
    if current != generation:
        raise SystemExit("F03 core generation pointer mismatch")
    if evidence_ids(sealed) != [f"E{index:04d}" for index in range(1, 49)]:
        raise SystemExit("F03 core seal did not append exactly E0048")
    if sealed["evidence_ledger.json"]["entries"][-1].get("summary") != core_summary():
        raise SystemExit("E0048 does not match the F03 core summary")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("F03 core seal did not preserve every prior generation")
    return {
        "mode": "core",
        "parent_generation": parent,
        "generation": generation,
        "evidence_id": CORE_EVIDENCE_ID,
        "state_verification": evidence.generation_integrity(46, CORE_EVIDENCE_ID),
        "status": "active",
        "completion_ready": False,
    }


def run_final() -> dict[str, Any]:
    evidence.verify_post_core()
    ralph_root, parent, payloads = current_state()
    if not re.fullmatch(r"000046-[0-9a-f]{8}", parent):
        raise SystemExit(f"unexpected F03 final parent: {parent}")
    if evidence_ids(payloads) != [f"E{index:04d}" for index in range(1, 49)]:
        raise SystemExit("final seal requires preserved E0001-E0048")
    if payloads["evidence_ledger.json"]["entries"][-1].get("summary") != core_summary():
        raise SystemExit("E0048 changed before final sealing")
    report = read_json(ATTEMPT / "report.json")
    rah = report.get("rah_state")
    if not isinstance(rah, dict) or rah.get("core_generation") != parent:
        raise SystemExit("F03 report does not bind the core generation")
    if rah.get("core_evidence_id") != CORE_EVIDENCE_ID:
        raise SystemExit("F03 report does not bind E0048")
    if rah.get("final_closeout_evidence_id") != FINAL_EVIDENCE_ID:
        raise SystemExit("F03 report does not reserve E0049")
    summary, hashes = final_summary(parent)
    before = numbered_generations(ralph_root)
    generation = commit_active_generation(
        payloads=payloads, summary=summary, expected_evidence_id=FINAL_EVIDENCE_ID
    )
    _, current, sealed = current_state()
    if current != generation:
        raise SystemExit("F03 final generation pointer mismatch")
    if evidence_ids(sealed) != [f"E{index:04d}" for index in range(1, 50)]:
        raise SystemExit("F03 final seal did not append exactly E0049")
    if sealed["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
        raise SystemExit("E0049 does not match the F03 closeout hash seal")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("F03 final seal did not preserve every prior generation")
    return {
        "mode": "final",
        "parent_generation": parent,
        "generation": generation,
        "evidence_id": FINAL_EVIDENCE_ID,
        "artifact_hashes": hashes,
        "state_verification": evidence.generation_integrity(47, FINAL_EVIDENCE_ID),
        "status": "active",
        "completion_ready": False,
    }


def run_verify() -> dict[str, Any]:
    ralph_root, generation, payloads = current_state()
    generations = numbered_generations(ralph_root)
    if len(generations) == 45:
        return run_preflight()
    if len(generations) == 46:
        evidence.verify_post_core()
        return evidence.generation_integrity(46, CORE_EVIDENCE_ID)
    if len(generations) != 47 or not re.fullmatch(r"000047-[0-9a-f]{8}", generation):
        raise SystemExit(f"unexpected F03 verification generation: {generation}")
    integrity = evidence.generation_integrity(47, FINAL_EVIDENCE_ID)
    core_generation = str(read_json(ATTEMPT / "report.json")["rah_state"]["core_generation"])
    summary, _ = final_summary(core_generation)
    if payloads["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
        raise SystemExit("stored E0049 summary differs from final F03 artifact hashes")
    evidence.verify_pre_core()
    for name in ("report.json", "commands.jsonl", "review.md"):
        if (ATTEMPT / name).read_bytes() != (ROOT / "artifacts/work_packages/F03" / name).read_bytes():
            raise SystemExit(f"F03 root projection mismatch after final seal: {name}")
    return {**integrity, "mode": "final-verify", "status": "PASS"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("preflight", "core", "final", "verify"))
    args = parser.parse_args()
    result = {
        "preflight": run_preflight,
        "core": run_core,
        "final": run_final,
        "verify": run_verify,
    }[args.mode]()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
