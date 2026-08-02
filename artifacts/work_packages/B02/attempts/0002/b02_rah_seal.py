#!/usr/bin/env python3
"""Append B02-0002 PASS evidence while keeping the overall goal active/failing."""

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


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/B02/attempts/0002"
AUTOMATION = ROOT / ".rah/helpers/recursive-architecture-refactoring-auto/automation"
sys.path.insert(0, str(ATTEMPT))
sys.path.insert(0, str(AUTOMATION))

import b02_evidence as evidence  # noqa: E402
import ralph_harness as rh  # noqa: E402
import state_store  # noqa: E402


CORE_PARENT = "000082-b49a186b"
CORE_EVIDENCE_ID = "E0090"
FINAL_EVIDENCE_ID = "E0091"
PRESERVED_GENERATIONS = [
    "000079-fadeffe1",
    "000080-cccce3eb",
    "000081-843d5565",
    "000082-b49a186b",
]
OBJECTIVE = (
    "Continue Epistemic Foundry v4.0.0 under product-owner Decision Set "
    "HD-EF4-UNBLOCK-SET-20260730-001 and its four child HumanDecisions. "
    "Preserve every prior attempt, FAIL/SPEC_GAP result, RAH evidence and "
    "retained generation, report, review, command record, and the dirty "
    "worktree. In the primary session without Fleet or subagents, execute "
    "serially: B02 dependency correction; B04 dependency/build revalidation; "
    "S04-TM004 active source-binding correction; C01, C02, C03, C04 and B04 "
    "canonical correction; A05 correction and A06 audit; J02-0003, K01-0002 "
    "and T01-0002; then recompute the 156-package DAG and continue the earliest "
    "dependency-ready package. Keep implementation_gate failed or pending "
    "repair and completion_ready false until objective evidence passes."
)
NEXT_ACTIONS = [
    "Start the next unused B04 dependency/build revalidation attempt without editing pyproject.toml or uv.lock.",
    "Verify clean dependency sync, wheel/sdist build, runtime metadata non-exposure, lock reproducibility, and canonical projection integrity.",
    "Only after B04 PASS, reconcile S04-TM004 against the active manifest binding; keep J02-0003 unstarted until both gates pass.",
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
    result: dict[str, str] = {}
    for name in names:
        path = ATTEMPT / name
        if not path.is_file():
            raise SystemExit(f"required B02 artifact is missing: {name}")
        result[name] = sha256(path)
    return result


def core_summary() -> str:
    names = (
        "lock-diff-verification-final.json",
        "lockfile-check-final.json",
        "double-build-comparison-current-inputs.json",
        "double-build-comparison.json",
        "double-build-comparison-rerun.json",
        "staged-build-diagnostic.json",
        "write-scope-verification.json",
        "review.md",
    )
    hashes = artifact_hashes(names)
    return (
        "B02-0002 PASS under HD-EF4-J02-SG002-20260730-001: pyproject.toml "
        "declares exactly tiktoken==0.13.0 in dependency-groups.skill-context; "
        "uv 0.7.21 reconstructs the sealed pre-correction pyproject and lock "
        "hashes, resolves 21 packages, and adds only tiktoken plus six mandatory "
        "transitives with unrelated change count 0 and runtime exposure false. "
        "Frozen sync, o200k_base, 7/7 tokenizer vectors, targeted pytest, and "
        "lockfile check pass. The current-input double-build adapter produces 11 "
        "byte-identical artifacts with mismatch count 0. The unchanged production "
        "helper's stale staging failure is preserved, not relabeled, and handed to "
        "the required B04 revalidation. Lock evidence sha256:"
        f"{hashes['lock-diff-verification-final.json']}; lock check sha256:"
        f"{hashes['lockfile-check-final.json']}; current-input build sha256:"
        f"{hashes['double-build-comparison-current-inputs.json']}; production "
        f"failure sha256:{hashes['double-build-comparison-rerun.json']}; diagnostic "
        f"sha256:{hashes['staged-build-diagnostic.json']}; write-scope sha256:"
        f"{hashes['write-scope-verification.json']}; review sha256:"
        f"{hashes['review.md']}. Product write-scope violations and B02-owned "
        "blocking findings are zero. Historical B02 PASS and J02-0002 FAIL remain "
        "immutable; B04 revalidation is next; global implementation_gate remains "
        "fail and completion_ready=false."
    )


def final_summary(parent: str) -> tuple[str, dict[str, str]]:
    names = (
        "report.json",
        "commands.jsonl",
        "review.md",
        "write-scope-verification.json",
        "lock-diff-verification-final.json",
        "lockfile-check-final.json",
        "double-build-comparison-current-inputs.json",
        "double-build-comparison.json",
        "double-build-comparison-rerun.json",
        "staged-build-diagnostic.json",
        "rah-core-integrity.json",
        "verify_lock_correction.py",
        "run_double_build_current_inputs.py",
        "diagnose_staged_build.py",
        "b02_evidence.py",
        "b02_rah_seal.py",
    )
    hashes = artifact_hashes(names)
    summary = (
        f"B02-0002 PASS closeout is hash-sealed after core generation {parent}: "
        f"report sha256:{hashes['report.json']}; commands sha256:"
        f"{hashes['commands.jsonl']}; review sha256:{hashes['review.md']}; "
        f"write-scope sha256:{hashes['write-scope-verification.json']}; lock "
        f"evidence sha256:{hashes['lock-diff-verification-final.json']}; current "
        f"input build sha256:{hashes['double-build-comparison-current-inputs.json']}; "
        f"preserved production failure sha256:{hashes['double-build-comparison-rerun.json']}; "
        f"core RAH integrity sha256:{hashes['rah-core-integrity.json']}; evidence "
        f"builder sha256:{hashes['b02_evidence.py']}; sealer sha256:"
        f"{hashes['b02_rah_seal.py']}. B02 is PASS, B04 revalidation is next, "
        "S04 and J02-0003 remain gated, the overall goal remains active with "
        "implementation_gate=fail, and completion_ready=false."
    )
    return summary, hashes


def commit_active_failed_generation(
    *, payloads: dict[str, Any], summary: str, expected_evidence_id: str
) -> str:
    now = rh.utc_now()
    goal = copy.deepcopy(payloads["goal.json"])
    loop = copy.deepcopy(payloads["loop_state.json"])
    ledger = copy.deepcopy(payloads["evidence_ledger.json"])
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
    goal.update({"goal": OBJECTIVE, "status": "active", "updated_at_utc": now})
    loop.update(
        {
            "blocked_reason": None,
            "checkpoint_required": False,
            "current_stage": "ralph-active",
            "done": False,
            "generated_at_utc": now,
            "goal": OBJECTIVE,
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
            "intake", "plan", "act", "verify", "review", "decide",
            "done", "blocked", "cancelled", "failed",
        ],
    }
    prior_used = ["E0085", "E0086", "E0089"]
    if expected_evidence_id == FINAL_EVIDENCE_ID:
        prior_used.append(CORE_EVIDENCE_ID)
    loop["progress_update"] = {
        "created_evidence": [identifier],
        "missing_acceptance_ids": [],
        "missing_closeout_ids": [],
        "missing_evidence_ids": [],
        "missing_validation_ids": [],
        "used_evidence": prior_used + [identifier],
    }
    plan = rh.build_plan_graph(goal, loop, payloads["plan_graph.json"], now)
    bridge = rh.build_goal_bridge(
        ROOT,
        goal,
        loop,
        payloads["goal_bridge.json"],
        SimpleNamespace(goal_status="paused", goal_objective=OBJECTIVE),
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
        "B02-0002 exact dependency correction is evidence-sealed PASS. "
        "B04 dependency/build revalidation is the next mandatory repair; "
        "the global implementation gate remains failed and completion_ready=false."
    )
    status["implementation_gate"] = "fail"
    status["implementation_gate_note"] = note
    status["next_recommended_action"] = NEXT_ACTIONS[0]
    evidence_set = ["E0085", "E0086", "E0087", "E0088", "E0089", CORE_EVIDENCE_ID]
    if expected_evidence_id == FINAL_EVIDENCE_ID:
        evidence_set.append(FINAL_EVIDENCE_ID)
    gates["implementation_gate"] = {
        "evidence_ids": evidence_set,
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


def run_preflight() -> dict[str, Any]:
    evidence.verify_pre_core()
    ralph_root, generation, payloads = current_state()
    if generation != CORE_PARENT:
        raise SystemExit(f"unexpected B02 core parent: {generation}")
    if numbered_generations(ralph_root) != PRESERVED_GENERATIONS:
        raise SystemExit("B02 preflight retained-generation inventory changed")
    if evidence_ids(payloads) != [f"E{index:04d}" for index in range(1, 90)]:
        raise SystemExit("B02 preflight requires contiguous E0001-E0089")
    loop = payloads["loop_state.json"]
    if (
        loop.get("status") != "active"
        or loop.get("implementation_gate") != "fail"
        or loop.get("completion_readiness", {}).get("ready") is not False
    ):
        raise SystemExit("B02 preflight requires active/fail/completion_ready=false")
    return {
        "completion_ready": False,
        "generation": generation,
        "latest_evidence_id": "E0089",
        "mode": "preflight",
        "retained_generation_count": len(PRESERVED_GENERATIONS),
        "status": "PASS",
    }


def run_core() -> dict[str, Any]:
    run_preflight()
    ralph_root, parent, payloads = current_state()
    before = numbered_generations(ralph_root)
    summary = core_summary()
    generation = commit_active_failed_generation(
        payloads=payloads, summary=summary, expected_evidence_id=CORE_EVIDENCE_ID
    )
    _, current, sealed = current_state()
    if current != generation:
        raise SystemExit("B02 core generation pointer mismatch")
    if evidence_ids(sealed) != [f"E{index:04d}" for index in range(1, 91)]:
        raise SystemExit("B02 core seal did not append exactly E0090")
    if sealed["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
        raise SystemExit("E0090 does not match the exact B02 core summary")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("B02 core seal did not preserve every retained generation")
    return {
        "completion_ready": False,
        "evidence_id": CORE_EVIDENCE_ID,
        "generation": generation,
        "mode": "core",
        "parent_generation": parent,
        "retained_generation_count": len(after),
        "status": "active",
    }


def run_final() -> dict[str, Any]:
    evidence.verify_all()
    ralph_root, parent, payloads = current_state()
    if not re.fullmatch(r"000083-[0-9a-f]{8}", parent):
        raise SystemExit(f"unexpected B02 final parent: {parent}")
    if evidence_ids(payloads) != [f"E{index:04d}" for index in range(1, 91)]:
        raise SystemExit("B02 final seal requires contiguous E0001-E0090")
    if payloads["evidence_ledger.json"]["entries"][-1].get("summary") != core_summary():
        raise SystemExit("E0090 changed before final sealing")
    report = read_json(ATTEMPT / "report.json")
    if report.get("rah_state", {}).get("core_generation") != parent:
        raise SystemExit("B02 report does not bind the core generation")
    if report.get("rah_state", {}).get("final_artifact_seal_evidence_id") != FINAL_EVIDENCE_ID:
        raise SystemExit("B02 report does not reserve E0091")
    summary, hashes = final_summary(parent)
    before = numbered_generations(ralph_root)
    generation = commit_active_failed_generation(
        payloads=payloads, summary=summary, expected_evidence_id=FINAL_EVIDENCE_ID
    )
    _, current, sealed = current_state()
    if current != generation:
        raise SystemExit("B02 final generation pointer mismatch")
    if evidence_ids(sealed) != [f"E{index:04d}" for index in range(1, 92)]:
        raise SystemExit("B02 final seal did not append exactly E0091")
    if sealed["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
        raise SystemExit("E0091 does not match the exact B02 closeout hash seal")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("B02 final seal did not preserve every retained generation")
    return {
        "artifact_hashes": hashes,
        "completion_ready": False,
        "evidence_id": FINAL_EVIDENCE_ID,
        "generation": generation,
        "mode": "final",
        "parent_generation": parent,
        "retained_generation_count": len(after),
        "status": "active",
    }


def run_verify() -> dict[str, Any]:
    result = evidence.verify_all()
    ralph_root, generation, payloads = current_state()
    generations = numbered_generations(ralph_root)
    if generations[: len(PRESERVED_GENERATIONS)] != PRESERVED_GENERATIONS:
        raise SystemExit("B02 verification lost a preserved generation")
    latest = evidence_ids(payloads)[-1]
    expected_count = {"E0089": 4, CORE_EVIDENCE_ID: 5, FINAL_EVIDENCE_ID: 6}.get(latest)
    if expected_count is None or len(generations) != expected_count:
        raise SystemExit("unexpected B02 RAH seal state")
    loop = payloads["loop_state.json"]
    if (
        loop.get("status") != "active"
        or loop.get("implementation_gate") != "fail"
        or loop.get("completion_readiness", {}).get("ready") is not False
    ):
        raise SystemExit("B02 verification did not retain global failed/active state")
    return {
        **result,
        "generation": generation,
        "latest_evidence_id": latest,
        "mode": "verify",
        "retained_generation_count": len(generations),
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
