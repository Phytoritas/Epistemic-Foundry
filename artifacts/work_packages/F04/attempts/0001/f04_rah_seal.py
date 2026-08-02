#!/usr/bin/env python3
"""Append F04-0001 core and closeout evidence without rewriting RAH history."""

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
ATTEMPT = ROOT / "artifacts/work_packages/F04/attempts/0001"
AUTOMATION = ROOT / ".rah/helpers/recursive-architecture-refactoring-auto/automation"
sys.path.insert(0, str(ATTEMPT))
sys.path.insert(0, str(AUTOMATION))

import f04_evidence as evidence  # noqa: E402
import ralph_harness as rh  # noqa: E402
import state_store  # noqa: E402


CORE_PARENT = "000047-1104a666"
CORE_EVIDENCE_ID = "E0050"
FINAL_EVIDENCE_ID = "E0051"
NEXT_ACTIONS = [
    "Start G01, the earliest manifest-order dependency-ready package, in the primary session.",
    "Keep I01, K01, and A06 dependency-ready but unstarted during serial G01 handling.",
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
        "forge-golden-flow-verification.json",
        "phase-artifact-reconciliation.json",
        "full-regression-impact.json",
        "preexisting-debt-reconciliation.json",
        "dependency-status.json",
        "forge-golden-flow-verification.artifact-receipt.json",
        "targeted-node-suite.junit.xml",
        "full-node-suite.junit.xml",
        "full-python-suite.junit.xml",
        "review.md",
    )
    hashes = {name: sha256(ATTEMPT / name) for name in names}
    return (
        "F04-0001 PASS: three deterministic E1/E3/E5 golden flows compose the "
        "F01 classifier, F02 reducer/replay and F03 receipt admission gate. All "
        "17 transitions and 14 PhaseArtifactSets reconcile across generation, "
        "admission, reduction, replay and persistence with no missing or duplicate "
        "identity. E admission is gate- and receipt-bound; UNDERDETERMINED remains "
        "a successful truthful outcome; classification identity-context mutation "
        "fails closed. F04 targeted Node is 8/8, combined F01/F02/F03/F04 is "
        "76/76, and full Python is 947/947; full Node is 313 passed plus only "
        "exact unchanged S04-TM004, with zero F04-caused failures or skips. Golden "
        f"verification sha256:{hashes['forge-golden-flow-verification.json']}; phase "
        f"reconciliation sha256:{hashes['phase-artifact-reconciliation.json']}; "
        f"regression sha256:{hashes['full-regression-impact.json']}; receipt sha256:"
        f"{hashes['forge-golden-flow-verification.artifact-receipt.json']}; review "
        f"sha256:{hashes['review.md']}. Primary-session separate integration review "
        "has zero blocking findings and is not actor-independent certification. "
        "All prior attempts, generations and dirty-worktree content are preserved. "
        "The 156-package DAG yields G01/I01/K01/A06 ready with G01 next; "
        "completion_ready=false."
    )


def final_summary(parent: str) -> tuple[str, dict[str, str]]:
    names = (
        "report.json",
        "review.md",
        "commands.jsonl",
        "forge-golden-flow-verification.json",
        "phase-artifact-reconciliation.json",
        "full-regression-impact.json",
        "preexisting-debt-reconciliation.json",
        "dependency-status.json",
        "forge-golden-flow-verification.artifact-receipt.json",
        "rah-core-integrity.json",
        "f04_evidence.py",
        "f04_rah_seal.py",
    )
    hashes = {name: sha256(ATTEMPT / name) for name in names}
    summary = (
        f"F04-0001 PASS closeout is hash-sealed after core generation {parent}: "
        f"report sha256:{hashes['report.json']}; review sha256:{hashes['review.md']}; "
        f"commands sha256:{hashes['commands.jsonl']}; golden verification sha256:"
        f"{hashes['forge-golden-flow-verification.json']}; phase reconciliation "
        f"sha256:{hashes['phase-artifact-reconciliation.json']}; regression sha256:"
        f"{hashes['full-regression-impact.json']}; dependency status sha256:"
        f"{hashes['dependency-status.json']}; receipt sha256:"
        f"{hashes['forge-golden-flow-verification.artifact-receipt.json']}; core RAH "
        f"integrity sha256:{hashes['rah-core-integrity.json']}; builder sha256:"
        f"{hashes['f04_evidence.py']}; sealer sha256:{hashes['f04_rah_seal.py']}. "
        "F04 is PASS; F01/F02/F03 and all earlier history remain immutable; "
        "S04-TM004 remains separate S04-owned debt. G01/I01/K01/A06 are ready in "
        "manifest order with G01 next; completion_ready=false."
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
        "used_evidence": [identifier, "E0049", "E0048"],
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
        "F04-0001 is evidence-sealed PASS with exact E1/E3/E5 flow and phase "
        "reconciliation; G01 is next and completion_ready remains false."
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
        raise SystemExit(f"unexpected F04 core parent: {generation}")
    if evidence_ids(payloads) != [f"E{index:04d}" for index in range(1, 50)]:
        raise SystemExit("preflight requires preserved E0001-E0049")
    generations = numbered_generations(ralph_root)
    if len(generations) != 47 or generations[-1] != generation:
        raise SystemExit("preflight requires all 47 prior RAH generations")
    if payloads["loop_state.json"].get("status") != "active":
        raise SystemExit("preflight requires active RAH status")
    return {
        "mode": "preflight",
        "generation": generation,
        "latest_evidence_id": "E0049",
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
        raise SystemExit("F04 core generation pointer mismatch")
    if evidence_ids(sealed) != [f"E{index:04d}" for index in range(1, 51)]:
        raise SystemExit("F04 core seal did not append exactly E0050")
    if sealed["evidence_ledger.json"]["entries"][-1].get("summary") != core_summary():
        raise SystemExit("E0050 does not match the F04 core summary")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("F04 core seal did not preserve every prior generation")
    return {
        "mode": "core",
        "parent_generation": parent,
        "generation": generation,
        "evidence_id": CORE_EVIDENCE_ID,
        "state_verification": evidence.generation_integrity(48, CORE_EVIDENCE_ID),
        "status": "active",
        "completion_ready": False,
    }


def run_final() -> dict[str, Any]:
    evidence.verify_post_core()
    ralph_root, parent, payloads = current_state()
    if not re.fullmatch(r"000048-[0-9a-f]{8}", parent):
        raise SystemExit(f"unexpected F04 final parent: {parent}")
    if evidence_ids(payloads) != [f"E{index:04d}" for index in range(1, 51)]:
        raise SystemExit("final seal requires preserved E0001-E0050")
    if payloads["evidence_ledger.json"]["entries"][-1].get("summary") != core_summary():
        raise SystemExit("E0050 changed before final sealing")
    report = read_json(ATTEMPT / "report.json")
    rah = report.get("rah_state")
    if not isinstance(rah, dict) or rah.get("core_generation") != parent:
        raise SystemExit("F04 report does not bind the core generation")
    if rah.get("core_evidence_id") != CORE_EVIDENCE_ID:
        raise SystemExit("F04 report does not bind E0050")
    if rah.get("final_closeout_evidence_id") != FINAL_EVIDENCE_ID:
        raise SystemExit("F04 report does not reserve E0051")
    summary, hashes = final_summary(parent)
    before = numbered_generations(ralph_root)
    generation = commit_active_generation(
        payloads=payloads, summary=summary, expected_evidence_id=FINAL_EVIDENCE_ID
    )
    _, current, sealed = current_state()
    if current != generation:
        raise SystemExit("F04 final generation pointer mismatch")
    if evidence_ids(sealed) != [f"E{index:04d}" for index in range(1, 52)]:
        raise SystemExit("F04 final seal did not append exactly E0051")
    if sealed["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
        raise SystemExit("E0051 does not match the F04 closeout hash seal")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("F04 final seal did not preserve every prior generation")
    return {
        "mode": "final",
        "parent_generation": parent,
        "generation": generation,
        "evidence_id": FINAL_EVIDENCE_ID,
        "artifact_hashes": hashes,
        "state_verification": evidence.generation_integrity(49, FINAL_EVIDENCE_ID),
        "status": "active",
        "completion_ready": False,
    }


def run_verify() -> dict[str, Any]:
    ralph_root, generation, payloads = current_state()
    generations = numbered_generations(ralph_root)
    if len(generations) == 47:
        return run_preflight()
    if len(generations) == 48:
        evidence.verify_post_core()
        return evidence.generation_integrity(48, CORE_EVIDENCE_ID)
    if len(generations) != 49 or not re.fullmatch(r"000049-[0-9a-f]{8}", generation):
        raise SystemExit(f"unexpected F04 verification generation: {generation}")
    integrity = evidence.generation_integrity(49, FINAL_EVIDENCE_ID)
    core_generation = str(read_json(ATTEMPT / "report.json")["rah_state"]["core_generation"])
    summary, _ = final_summary(core_generation)
    if payloads["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
        raise SystemExit("stored E0051 summary differs from final F04 artifact hashes")
    evidence.verify_pre_core()
    for name in ("report.json", "commands.jsonl", "review.md"):
        if (ATTEMPT / name).read_bytes() != (ROOT / "artifacts/work_packages/F04" / name).read_bytes():
            raise SystemExit(f"F04 root projection mismatch after final seal: {name}")
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
