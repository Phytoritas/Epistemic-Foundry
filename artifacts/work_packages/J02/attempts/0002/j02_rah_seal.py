#!/usr/bin/env python3
"""Append J02-0002 FAIL evidence without rewriting prior RAH history."""

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
ATTEMPT = ROOT / "artifacts/work_packages/J02/attempts/0002"
AUTOMATION = ROOT / ".rah/helpers/recursive-architecture-refactoring-auto/automation"
sys.dont_write_bytecode = True
sys.path.insert(0, str(ATTEMPT))
sys.path.insert(0, str(AUTOMATION))

import j02_evidence as evidence  # noqa: E402
import ralph_harness as rh  # noqa: E402
import state_store  # noqa: E402


CORE_PARENT = "000078-e5a8777f"
CORE_EVIDENCE_ID = "E0082"
FINAL_EVIDENCE_ID = "E0083"
BLOCK_REASON = (
    "J02-0002 implementation is verified but the package FAILS two non-waivable "
    "acceptance gates. The executable repository dependency graph does not lock "
    "exact tiktoken==0.13.0, and the sole S04-TM004 residual no longer matches its "
    "previously bounded failure fingerprint after the authorized J02 manifest "
    "correction. A product-owner decision must assign the tokenizer dependency-lock "
    "owner with exact pyproject.toml and uv.lock write authority, and assign S04 "
    "traceability fingerprint reconciliation/update authority without weakening the "
    "drift gate. J03 and J04 remain unstarted; completion_ready=false."
)
NEXT_ACTIONS = [
    "Obtain a product-owner decision assigning exact tokenizer dependency-lock ownership and pyproject.toml plus uv.lock write authority.",
    "Obtain a product-owner decision assigning S04-TM004 traceability fingerprint reconciliation/update authority without weakening the drift gate.",
    "Run J02 as a new attempt only after both authorities are durable; keep J03 and J04 unstarted and completion_ready false.",
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


def evidence_ids(payloads: dict[str, Any]) -> list[str]:
    ledger = payloads.get("evidence_ledger.json")
    if not isinstance(ledger, dict) or not isinstance(ledger.get("entries"), list):
        raise SystemExit("invalid RAH evidence ledger")
    return [str(row.get("id")) for row in ledger["entries"] if isinstance(row, dict)]


def artifact_hashes(names: tuple[str, ...]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for name in names:
        path = ATTEMPT / name
        if not path.is_file():
            raise SystemExit(f"required J02 artifact is missing: {name}")
        hashes[name] = sha256(path)
    return hashes


def core_summary() -> str:
    names = (
        "metadata-budget-verification.json",
        "tokenizer-verification.json",
        "reference-inventory-verification.json",
        "reference-selection-verification.json",
        "reference-reachability-verification.json",
        "full-regression-impact.json",
        "write-scope-verification.json",
        "concurrency-diagnostic.json",
        "preexisting-debt-reconciliation.json",
        "targeted-python-suite.junit.xml",
        "targeted-node-suite.junit.xml",
        "j01-regression-node-suite.junit.xml",
        "full-python-suite.junit.xml",
        "full-node-suite.junit.xml",
        "review.md",
    )
    hashes = artifact_hashes(names)
    return (
        "J02-0002 FAIL: progressive-reference implementation is verified at canonical "
        "inventory sha256:fe2c8b1814406af0f7cc380ddf95f2edd48f4df4745fc9fadaa9b743ab9961ac; "
        "metadata is 4,767 UTF-8 bytes and 1,112 pinned o200k_base tokens for 29 "
        "skills; all 17 references, maximum closure 11, maximum depth 5, 12 budget "
        "cases, 35 selection cases, 16 adversarial cases, and 100 deterministic "
        "loader repetitions pass. Targeted Node is 25/25 and J01 regression is "
        "19/19. Two non-waivable gates fail: pyproject.toml and uv.lock do not lock "
        "exact tiktoken==0.13.0, producing targeted Python 16/17 and full Python "
        "963/964; and full Node is 436/437 because S04-TM004 changed from bounded "
        "actual fb9656cce2fd4d0147571bc85726ebbbbb3f26a59ac644c5a12040007475d938 "
        "to de457bc4b141aef332d76f16357d4ba44daa663dd15c195d2e9575bc59a79940. "
        f"Metadata verification sha256:{hashes['metadata-budget-verification.json']}; "
        f"tokenizer verification sha256:{hashes['tokenizer-verification.json']}; "
        f"inventory verification sha256:{hashes['reference-inventory-verification.json']}; "
        f"selection verification sha256:{hashes['reference-selection-verification.json']}; "
        f"reachability verification sha256:{hashes['reference-reachability-verification.json']}; "
        f"regression sha256:{hashes['full-regression-impact.json']}; write-scope "
        f"verification sha256:{hashes['write-scope-verification.json']}; concurrency "
        f"diagnostic sha256:{hashes['concurrency-diagnostic.json']}; debt reconciliation "
        f"sha256:{hashes['preexisting-debt-reconciliation.json']}; review sha256:"
        f"{hashes['review.md']}. The transient parallel artifact-mutation lock observation "
        "is reconciled by isolated 5/5 and final serial PASS. J02-0001 and all prior "
        "history remain immutable; J03/J04 remain unstarted; completion_ready=false."
    )


def final_summary(parent: str) -> tuple[str, dict[str, str]]:
    names = (
        "report.json",
        "commands.jsonl",
        "review.md",
        "metadata-budget-verification.json",
        "tokenizer-verification.json",
        "reference-inventory-verification.json",
        "reference-selection-verification.json",
        "reference-reachability-verification.json",
        "full-regression-impact.json",
        "write-scope-verification.json",
        "concurrency-diagnostic.json",
        "preexisting-debt-reconciliation.json",
        "rah-core-integrity.json",
        "targeted-python-suite.junit.xml",
        "targeted-node-suite.junit.xml",
        "j01-regression-node-suite.junit.xml",
        "full-python-suite.junit.xml",
        "full-node-suite.junit.xml",
        "j02_evidence.py",
        "j02_rah_seal.py",
    )
    hashes = artifact_hashes(names)
    summary = (
        f"J02-0002 FAIL closeout is hash-sealed after core blocker generation {parent}: "
        f"report sha256:{hashes['report.json']}; commands sha256:{hashes['commands.jsonl']}; "
        f"review sha256:{hashes['review.md']}; metadata verification sha256:"
        f"{hashes['metadata-budget-verification.json']}; tokenizer verification sha256:"
        f"{hashes['tokenizer-verification.json']}; inventory verification sha256:"
        f"{hashes['reference-inventory-verification.json']}; selection verification "
        f"sha256:{hashes['reference-selection-verification.json']}; reachability "
        f"verification sha256:{hashes['reference-reachability-verification.json']}; "
        f"regression sha256:{hashes['full-regression-impact.json']}; write-scope "
        f"verification sha256:{hashes['write-scope-verification.json']}; concurrency "
        f"diagnostic sha256:{hashes['concurrency-diagnostic.json']}; debt reconciliation "
        f"sha256:{hashes['preexisting-debt-reconciliation.json']}; core RAH integrity "
        f"sha256:{hashes['rah-core-integrity.json']}; targeted Python JUnit sha256:"
        f"{hashes['targeted-python-suite.junit.xml']}; targeted Node JUnit sha256:"
        f"{hashes['targeted-node-suite.junit.xml']}; J01 regression JUnit sha256:"
        f"{hashes['j01-regression-node-suite.junit.xml']}; full Python JUnit sha256:"
        f"{hashes['full-python-suite.junit.xml']}; full Node JUnit sha256:"
        f"{hashes['full-node-suite.junit.xml']}; evidence builder sha256:"
        f"{hashes['j02_evidence.py']}; sealer sha256:{hashes['j02_rah_seal.py']}. "
        "J02 remains FAIL pending exact dependency-lock and S04 traceability ownership "
        "decisions. J03/J04 remain unstarted, every prior generation and dirty-worktree "
        "change is preserved, and completion_ready=false."
    )
    return summary, hashes


def commit_blocked_generation(
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
    goal.update({"goal": objective, "status": "blocked", "updated_at_utc": now})
    loop.update(
        {
            "blocked_reason": BLOCK_REASON,
            "checkpoint_required": False,
            "current_stage": "ralph-blocked",
            "done": False,
            "generated_at_utc": now,
            "goal": objective,
            "harness_phase": "blocked",
            "implementation_gate": "fail",
            "loop_phase": "verification",
            "mark_done_rejected": False,
            "next_actions": NEXT_ACTIONS,
            "status": "blocked",
            "updated_at_utc": now,
        }
    )
    readiness = loop.get("completion_readiness")
    if not isinstance(readiness, dict) or readiness.get("ready") is not False:
        raise SystemExit("completion readiness must remain explicitly false")
    readiness["evidence_count"] = len(ledger["entries"])
    loop["state_machine"] = {
        "allowed_next_states": ["plan", "act", "cancelled"],
        "current_state": "blocked",
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
        "used_evidence": [identifier, "E0081", "E0080"],
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
    status["implementation_gate"] = "fail"
    status["implementation_gate_note"] = BLOCK_REASON
    status["next_recommended_action"] = NEXT_ACTIONS[0]
    gates["implementation_gate"] = {
        "evidence_ids": [
            evidence_id
            for evidence_id in (CORE_EVIDENCE_ID, FINAL_EVIDENCE_ID)
            if evidence_id in evidence_ids({"evidence_ledger.json": ledger})
        ],
        "note": BLOCK_REASON,
        "status": "fail",
    }
    rh.write_json(status_path, status)
    rh.write_json(gates_path, gates)
    rh.refresh_status_for_ralph(ROOT, ROOT / ".rah", goal, loop, now)
    rh.upsert_current_loop(
        ROOT / ".rah/plans/current_loop.md", rh.render_managed_current_loop(goal, loop)
    )
    rh.write_text(
        ROOT / ".rah/ralph/blockers.md", rh.render_blockers(goal, loop, now)
    )
    return generation


def run_preflight() -> dict[str, Any]:
    evidence.verify_pre_core()
    ralph_root, generation, payloads = current_state()
    if generation != CORE_PARENT:
        raise SystemExit(f"unexpected J02-0002 core parent: {generation}")
    if evidence_ids(payloads) != [f"E{index:04d}" for index in range(1, 82)]:
        raise SystemExit("preflight requires preserved E0001-E0081")
    generations = numbered_generations(ralph_root)
    if len(generations) != 78 or generations[-1] != generation:
        raise SystemExit("preflight requires all 78 prior RAH generations")
    loop = payloads["loop_state.json"]
    if loop.get("status") != "active" or loop.get("implementation_gate") != "pass":
        raise SystemExit("preflight requires active/pass RAH state")
    if loop.get("completion_readiness", {}).get("ready") is not False:
        raise SystemExit("preflight requires completion_ready=false")
    return {
        "completion_ready": False,
        "generation": generation,
        "latest_evidence_id": "E0081",
        "mode": "preflight",
        "retained_generation_count": len(generations),
    }


def run_core() -> dict[str, Any]:
    run_preflight()
    ralph_root, parent, payloads = current_state()
    before = numbered_generations(ralph_root)
    summary = core_summary()
    generation = commit_blocked_generation(
        payloads=payloads, summary=summary, expected_evidence_id=CORE_EVIDENCE_ID
    )
    _, current, sealed = current_state()
    if current != generation:
        raise SystemExit("J02 core generation pointer mismatch")
    if evidence_ids(sealed) != [f"E{index:04d}" for index in range(1, 83)]:
        raise SystemExit("J02 core seal did not append exactly E0082")
    if sealed["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
        raise SystemExit("E0082 does not match the exact J02-0002 FAIL summary")
    loop = sealed["loop_state.json"]
    if (
        loop.get("status") != "blocked"
        or loop.get("implementation_gate") != "fail"
        or loop.get("blocked_reason") != BLOCK_REASON
        or loop.get("completion_readiness", {}).get("ready") is not False
    ):
        raise SystemExit("RAH did not persist exact J02 blocked/fail state")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("J02 core seal did not preserve every prior generation")
    return {
        "completion_ready": False,
        "evidence_id": CORE_EVIDENCE_ID,
        "failure_classification": "FAIL",
        "generation": generation,
        "mode": "core",
        "parent_generation": parent,
        "state_verification": evidence.generation_integrity(79, CORE_EVIDENCE_ID),
        "status": "blocked",
    }


def run_final() -> dict[str, Any]:
    evidence.verify_post_core()
    ralph_root, parent, payloads = current_state()
    if not re.fullmatch(r"000079-[0-9a-f]{8}", parent):
        raise SystemExit(f"unexpected J02 final parent: {parent}")
    if evidence_ids(payloads) != [f"E{index:04d}" for index in range(1, 83)]:
        raise SystemExit("final seal requires preserved E0001-E0082")
    if payloads["evidence_ledger.json"]["entries"][-1].get("summary") != core_summary():
        raise SystemExit("E0082 changed before final sealing")
    report = read_json(ATTEMPT / "report.json")
    rah = report.get("rah_state")
    if not isinstance(rah, dict) or rah.get("core_generation") != parent:
        raise SystemExit("J02 report does not bind the core generation")
    if rah.get("core_evidence_id") != CORE_EVIDENCE_ID:
        raise SystemExit("J02 report does not bind E0082")
    if rah.get("final_artifact_seal_evidence_id") != FINAL_EVIDENCE_ID:
        raise SystemExit("J02 report does not reserve E0083")
    integrity = read_json(ATTEMPT / "rah-core-integrity.json")
    if integrity.get("current_generation") != parent:
        raise SystemExit("J02 core integrity artifact does not bind generation 79")
    summary, hashes = final_summary(parent)
    before = numbered_generations(ralph_root)
    generation = commit_blocked_generation(
        payloads=payloads, summary=summary, expected_evidence_id=FINAL_EVIDENCE_ID
    )
    _, current, sealed = current_state()
    if current != generation:
        raise SystemExit("J02 final generation pointer mismatch")
    if evidence_ids(sealed) != [f"E{index:04d}" for index in range(1, 84)]:
        raise SystemExit("J02 final seal did not append exactly E0083")
    if sealed["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
        raise SystemExit("E0083 does not match the J02 artifact hash seal")
    loop = sealed["loop_state.json"]
    if (
        loop.get("status") != "blocked"
        or loop.get("implementation_gate") != "fail"
        or loop.get("blocked_reason") != BLOCK_REASON
        or loop.get("completion_readiness", {}).get("ready") is not False
    ):
        raise SystemExit("final seal did not retain exact J02 blocked/fail state")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("J02 final seal did not preserve every prior generation")
    return {
        "artifact_hashes": hashes,
        "completion_ready": False,
        "evidence_id": FINAL_EVIDENCE_ID,
        "failure_classification": "FAIL",
        "generation": generation,
        "mode": "final",
        "parent_generation": parent,
        "state_verification": evidence.generation_integrity(80, FINAL_EVIDENCE_ID),
        "status": "blocked",
    }


def run_verify() -> dict[str, Any]:
    ralph_root, generation, payloads = current_state()
    generations = numbered_generations(ralph_root)
    if len(generations) == 78:
        return run_preflight()
    if len(generations) == 79:
        integrity = evidence.generation_integrity(79, CORE_EVIDENCE_ID)
        if payloads["evidence_ledger.json"]["entries"][-1].get("summary") != core_summary():
            raise SystemExit("stored E0082 differs from current J02 core evidence")
        return {**integrity, "mode": "core-verify"}
    if len(generations) != 80 or not re.fullmatch(r"000080-[0-9a-f]{8}", generation):
        raise SystemExit(f"unexpected J02 verification generation: {generation}")
    evidence.verify_post_core()
    integrity = evidence.generation_integrity(80, FINAL_EVIDENCE_ID)
    core_generation = str(read_json(ATTEMPT / "report.json")["rah_state"]["core_generation"])
    summary, _ = final_summary(core_generation)
    if payloads["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
        raise SystemExit("stored E0083 differs from current J02 artifact hashes")
    for name in ("report.json", "commands.jsonl", "review.md"):
        if (ATTEMPT / name).read_bytes() != (
            ROOT / "artifacts/work_packages/J02" / name
        ).read_bytes():
            raise SystemExit(f"J02 root projection mismatch after final seal: {name}")
    return {
        **integrity,
        "failure_classification": "FAIL",
        "mode": "final-verify",
        "status": "PASS",
    }


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
