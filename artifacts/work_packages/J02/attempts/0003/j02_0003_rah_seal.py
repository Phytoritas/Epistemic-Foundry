#!/usr/bin/env python3
"""Append J02-0003 PASS evidence while the global repair goal stays active."""

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
ATTEMPT = ROOT / "artifacts/work_packages/J02/attempts/0003"
AUTOMATION = ROOT / ".rah/helpers/recursive-architecture-refactoring-auto/automation"
ATTEMPT_ID = "J02-0003"
sys.path.insert(0, str(ATTEMPT))
sys.path.insert(0, str(AUTOMATION))

import build_j02_0003_evidence as evidence  # noqa: E402
import ralph_harness as rh  # noqa: E402
import state_store  # noqa: E402


NEXT_ACTIONS = [
    "Run S04-0003 and repair the exact stale development-manifest source binding.",
    "Run B04-0007 only after S04-0003 is evidence-sealed PASS.",
    "Keep implementation_gate=fail and completion_ready=false through C04-0002 and B04-0008.",
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


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


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
    identifiers = [
        str(row.get("id")) for row in ledger["entries"] if isinstance(row, dict)
    ]
    if any(re.fullmatch(r"E\d{4,}", identifier) is None for identifier in identifiers):
        raise SystemExit("RAH evidence ledger contains a malformed evidence ID")
    return identifiers


def next_evidence_id(payloads: dict[str, Any]) -> str:
    ledger = payloads["evidence_ledger.json"]
    identifiers = evidence_ids(payloads)
    high_water = int(ledger.get("issued_id_high_water", 0))
    observed = max((int(identifier[1:]) for identifier in identifiers), default=0)
    if high_water != observed:
        raise SystemExit("RAH evidence high-water mark does not match the ledger")
    return f"E{high_water + 1:04d}"


def increment_evidence_id(identifier: str) -> str:
    if re.fullmatch(r"E\d{4,}", identifier) is None:
        raise SystemExit(f"cannot increment malformed evidence ID: {identifier}")
    width = max(4, len(identifier) - 1)
    return f"E{int(identifier[1:]) + 1:0{width}d}"


def generation_number(generation: str) -> int:
    if re.fullmatch(r"\d{6}-[0-9a-f]{8}", generation) is None:
        raise SystemExit(f"malformed RAH generation: {generation}")
    return int(generation.split("-", 1)[0])


def artifact_hashes(names: tuple[str, ...]) -> dict[str, str]:
    result: dict[str, str] = {}
    for name in names:
        path = ATTEMPT / name
        if not path.is_file():
            raise SystemExit(f"required J02-0003 artifact is missing: {name}")
        result[name] = sha256(path)
    return result


def core_summary() -> str:
    names = (
        "metadata-budget-verification.json",
        "tokenizer-verification.json",
        "inventory-authority-verification.json",
        "reference-selection-verification.json",
        "reference-reachability-verification.json",
        "dependency-status.json",
        "full-regression-impact.json",
        "preexisting-debt-reconciliation.json",
        "write-scope-verification.json",
        "j02-verification.artifact-receipt.json",
        "targeted-python-suite.junit.xml",
        "targeted-node-suite.junit.xml",
        "j01-regression-node-suite.junit.xml",
        "full-python-suite.junit.xml",
        "full-node-suite.junit.xml",
        "review.md",
        "build_j02_0003_evidence.py",
        "j02_0003_rah_seal.py",
    )
    hashes = artifact_hashes(names)
    return (
        "J02-0003 PASS: the exact tiktoken==0.13.0 skill-context dependency "
        "group and uv lock now pass without runtime or optional dependency "
        "exposure. Inventory semantics remain fixed at 29 skills, 17 references, "
        "4,767 UTF-8 metadata bytes, 1,112 pinned o200k_base tokens, maximum "
        "closure 11, and maximum transitive depth 5. All 12 budget cases, 35 "
        "selection cases, 16 adversarial reachability cases, and 100 loader "
        "repetitions pass. Targeted Python is 20/20, targeted Node is 25/25, "
        "J01 Node regression is 19/19, and full Python is 990/990. Full Node is "
        "459/460 with exactly S04-TM004: current development manifest "
        "sha256:5dd99d2aae1e9ef662b9b8242b5fa921621434c6600c9c06e3a573d03079bb12 "
        "versus stale bound successor "
        "sha256:7d1d3248dc3e2ca56d8f08ec282aa3d95bea9466ba6b7580fccff81e0f639319. "
        "HD-EF4-B04-SG002-20260730-001 requires S04-0003 after J02-0003, so "
        "this exact residual remains visible bounded later-attempt debt and "
        "J02-caused failures are zero. Metadata verification sha256:"
        f"{hashes['metadata-budget-verification.json']}; tokenizer verification "
        f"sha256:{hashes['tokenizer-verification.json']}; inventory authority "
        f"sha256:{hashes['inventory-authority-verification.json']}; selection "
        f"sha256:{hashes['reference-selection-verification.json']}; reachability "
        f"sha256:{hashes['reference-reachability-verification.json']}; dependency "
        f"sha256:{hashes['dependency-status.json']}; regression sha256:"
        f"{hashes['full-regression-impact.json']}; debt reconciliation sha256:"
        f"{hashes['preexisting-debt-reconciliation.json']}; write-scope sha256:"
        f"{hashes['write-scope-verification.json']}; receipt sha256:"
        f"{hashes['j02-verification.artifact-receipt.json']}; targeted Python "
        f"JUnit sha256:{hashes['targeted-python-suite.junit.xml']}; targeted Node "
        f"JUnit sha256:{hashes['targeted-node-suite.junit.xml']}; J01 regression "
        f"JUnit sha256:{hashes['j01-regression-node-suite.junit.xml']}; full "
        f"Python JUnit sha256:{hashes['full-python-suite.junit.xml']}; full Node "
        f"JUnit sha256:{hashes['full-node-suite.junit.xml']}; review sha256:"
        f"{hashes['review.md']}; builder sha256:"
        f"{hashes['build_j02_0003_evidence.py']}; sealer sha256:"
        f"{hashes['j02_0003_rah_seal.py']}. Review is primary-session separate "
        "with actor_independence=false. S04-0003 is next; implementation_gate "
        "remains fail and completion_ready=false."
    )


def final_summary(parent: str) -> tuple[str, dict[str, str]]:
    names = (
        "report.json",
        "commands.jsonl",
        "review.md",
        "metadata-budget-verification.json",
        "tokenizer-verification.json",
        "inventory-authority-verification.json",
        "reference-selection-verification.json",
        "reference-reachability-verification.json",
        "dependency-status.json",
        "full-regression-impact.json",
        "preexisting-debt-reconciliation.json",
        "write-scope-verification.json",
        "j02-verification.artifact-receipt.json",
        "targeted-python-suite.junit.xml",
        "targeted-node-suite.junit.xml",
        "j01-regression-node-suite.junit.xml",
        "full-python-suite.junit.xml",
        "full-node-suite.junit.xml",
        "rah-core-integrity.json",
        "build_j02_0003_evidence.py",
        "j02_0003_rah_seal.py",
    )
    hashes = artifact_hashes(names)
    summary = (
        f"J02-0003 PASS closeout is hash-sealed after core generation {parent}: "
        f"report sha256:{hashes['report.json']}; commands sha256:"
        f"{hashes['commands.jsonl']}; review sha256:{hashes['review.md']}; "
        f"metadata verification sha256:{hashes['metadata-budget-verification.json']}; "
        f"tokenizer verification sha256:{hashes['tokenizer-verification.json']}; "
        f"inventory authority sha256:{hashes['inventory-authority-verification.json']}; "
        f"selection sha256:{hashes['reference-selection-verification.json']}; "
        f"reachability sha256:{hashes['reference-reachability-verification.json']}; "
        f"dependency sha256:{hashes['dependency-status.json']}; regression sha256:"
        f"{hashes['full-regression-impact.json']}; debt reconciliation sha256:"
        f"{hashes['preexisting-debt-reconciliation.json']}; write-scope sha256:"
        f"{hashes['write-scope-verification.json']}; receipt sha256:"
        f"{hashes['j02-verification.artifact-receipt.json']}; targeted Python "
        f"JUnit sha256:{hashes['targeted-python-suite.junit.xml']}; targeted Node "
        f"JUnit sha256:{hashes['targeted-node-suite.junit.xml']}; J01 regression "
        f"JUnit sha256:{hashes['j01-regression-node-suite.junit.xml']}; full "
        f"Python JUnit sha256:{hashes['full-python-suite.junit.xml']}; full Node "
        f"JUnit sha256:{hashes['full-node-suite.junit.xml']}; core RAH integrity "
        f"sha256:{hashes['rah-core-integrity.json']}; builder sha256:"
        f"{hashes['build_j02_0003_evidence.py']}; sealer sha256:"
        f"{hashes['j02_0003_rah_seal.py']}. J02-0003 is PASS and S04-0003 is "
        "dependency-ready. Every prior attempt and generation remains preserved; "
        "S04, the C01-owned sample GateDecision hash debt, B04, C04, and final "
        "packaging remain, so implementation_gate=fail and completion_ready=false."
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
        raise SystemExit(
            f"unexpected evidence ID {identifier}; expected {expected_evidence_id}"
        )
    objective = str(goal["goal"])
    goal.update({"status": "active", "updated_at_utc": now})
    loop.update(
        {
            "blocked_reason": None,
            "checkpoint_required": False,
            "current_stage": "ralph-active",
            "done": False,
            "generated_at_utc": now,
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
    previous_used = loop.get("progress_update", {}).get("used_evidence", [])
    used = list(dict.fromkeys([*previous_used, *evidence_ids(payloads), identifier]))
    loop["progress_update"] = {
        "created_evidence": [identifier],
        "missing_acceptance_ids": [],
        "missing_closeout_ids": [],
        "missing_evidence_ids": [],
        "missing_validation_ids": [],
        "used_evidence": used,
    }
    plan = rh.build_plan_graph(goal, loop, payloads["plan_graph.json"], now)
    bridge = rh.build_goal_bridge(
        ROOT,
        goal,
        loop,
        payloads["goal_bridge.json"],
        SimpleNamespace(goal_status="active", goal_objective=objective),
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
        "J02-0003 progressive references and context-budget correction is "
        "evidence-sealed PASS. S04-0003 is next; S04, the C01-owned stale "
        "GateDecision example hash, B04, C04, and final packaging remain, so "
        "implementation_gate=fail and completion_ready=false."
    )
    status["implementation_gate"] = "fail"
    status["implementation_gate_note"] = note
    status["next_recommended_action"] = NEXT_ACTIONS[0]
    existing_ids = gates.get("implementation_gate", {}).get("evidence_ids", [])
    gates["implementation_gate"] = {
        "evidence_ids": list(dict.fromkeys([*existing_ids, identifier])),
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


def verify_generation_store(expected_count: int | None = None) -> dict[str, Any]:
    ralph_root, current, payloads = current_state()
    generations = numbered_generations(ralph_root)
    if expected_count is not None and len(generations) != expected_count:
        raise SystemExit(
            f"expected {expected_count} retained generations, found {len(generations)}"
        )
    if not generations or generations[-1] != current:
        raise SystemExit("retained generation inventory does not end at current")
    checked = 0
    for generation in generations:
        generation_root = ralph_root / "generations" / generation
        manifest = read_json(generation_root / "generation-manifest.json")
        files = manifest.get("files")
        if manifest.get("generation") != generation or not isinstance(files, dict):
            raise SystemExit(f"invalid generation manifest: {generation}")
        if set(files) != set(state_store.GENERATION_FILES):
            raise SystemExit(f"generation file set mismatch: {generation}")
        for name in state_store.GENERATION_FILES:
            if sha256(generation_root / name) != files[name]:
                raise SystemExit(f"generation hash mismatch: {generation}/{name}")
            checked += 1
    flat_stamps = 0
    flat_matches = 0
    for name in state_store.GENERATION_FILES:
        flat = read_json(ralph_root / name)
        if flat.get("state_generation") == current:
            flat_stamps += 1
        stripped = {key: value for key, value in flat.items() if key != "state_generation"}
        authority = payloads[name]
        if isinstance(authority, dict):
            authority = {
                key: value
                for key, value in authority.items()
                if key != "state_generation"
            }
        if state_store._dump(stripped) == state_store._dump(authority):
            flat_matches += 1
    loop = payloads["loop_state.json"]
    if (
        flat_stamps != 6
        or flat_matches != 6
        or loop.get("status") != "active"
        or loop.get("implementation_gate") != "fail"
        or loop.get("completion_readiness", {}).get("ready") is not False
    ):
        raise SystemExit("RAH state did not remain active/fail with six current flats")
    identifiers = evidence_ids(payloads)
    return {
        "attempt_id": ATTEMPT_ID,
        "work_package_id": "J02",
        "status": "PASS",
        "mode": "READ_ONLY",
        "current_generation": current,
        "latest_evidence_id": identifiers[-1],
        "evidence_count": len(identifiers),
        "retained_generation_count": len(generations),
        "retained_generations": generations,
        "generation_file_hashes_verified": checked,
        "generation_manifest_sha256": "sha256:"
        + sha256(ralph_root / "generations" / current / "generation-manifest.json"),
        "flat_snapshot_stamps_verified": flat_stamps,
        "flat_snapshot_content_matches": flat_matches,
        "ralph_status": "active",
        "implementation_gate": "fail",
        "completion_ready": False,
        "parse_errors": {},
    }


def assert_active_preflight(payloads: dict[str, Any]) -> None:
    identifiers = evidence_ids(payloads)
    expected = [f"E{index:04d}" for index in range(1, len(identifiers) + 1)]
    loop = payloads["loop_state.json"]
    if identifiers != expected:
        raise SystemExit("J02-0003 preflight requires a contiguous evidence ledger")
    if (
        loop.get("status") != "active"
        or loop.get("blocked_reason") is not None
        or loop.get("implementation_gate") != "fail"
        or loop.get("completion_readiness", {}).get("ready") is not False
    ):
        raise SystemExit("preflight requires active/fail/completion_ready=false")


def run_preflight() -> dict[str, Any]:
    evidence.verify()
    ralph_root, generation, payloads = current_state()
    assert_active_preflight(payloads)
    report = read_json(ATTEMPT / "report.json")
    if "rah_state" in report:
        raise SystemExit("J02-0003 report is already RAH-bound; use verify")
    generations = numbered_generations(ralph_root)
    if generations[-1] != generation:
        raise SystemExit("J02-0003 preflight generation pointer mismatch")
    return {
        "mode": "preflight",
        "status": "PASS",
        "generation": generation,
        "latest_evidence_id": evidence_ids(payloads)[-1],
        "next_evidence_id": next_evidence_id(payloads),
        "retained_generation_count": len(generations),
        "completion_ready": False,
    }


def run_core() -> dict[str, Any]:
    preflight = run_preflight()
    ralph_root, parent, payloads = current_state()
    before = numbered_generations(ralph_root)
    prior_ids = evidence_ids(payloads)
    core_id = next_evidence_id(payloads)
    final_id = increment_evidence_id(core_id)
    summary = core_summary()
    generation = commit_active_failed_generation(
        payloads=payloads, summary=summary, expected_evidence_id=core_id
    )
    _, current, sealed = current_state()
    if current != generation or generation_number(current) != generation_number(parent) + 1:
        raise SystemExit("J02-0003 core generation pointer mismatch")
    if evidence_ids(sealed) != [*prior_ids, core_id]:
        raise SystemExit("core seal did not append exactly one evidence entry")
    if sealed["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
        raise SystemExit("core evidence does not match the J02-0003 summary")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("core seal did not preserve every prior generation")
    integrity = verify_generation_store(len(before) + 1)
    write_json(ATTEMPT / "rah-core-integrity.json", integrity)
    evidence.bind_rah_state(
        core_generation=generation,
        core_evidence_id=core_id,
        final_closeout_evidence_id=final_id,
    )
    evidence.verify()
    return {
        "mode": "core",
        "status": "active",
        "parent_generation": parent,
        "generation": generation,
        "evidence_id": core_id,
        "final_closeout_evidence_id": final_id,
        "preflight": preflight,
        "state_verification": integrity,
        "completion_ready": False,
    }


def run_final() -> dict[str, Any]:
    evidence.verify()
    ralph_root, parent, payloads = current_state()
    assert_active_preflight(payloads)
    report = read_json(ATTEMPT / "report.json")
    rah = report.get("rah_state")
    if not isinstance(rah, dict) or rah.get("core_generation") != parent:
        raise SystemExit("J02-0003 report does not bind the current core generation")
    core_id = str(rah.get("core_evidence_id"))
    final_id = str(rah.get("final_closeout_evidence_id"))
    if evidence_ids(payloads)[-1] != core_id or next_evidence_id(payloads) != final_id:
        raise SystemExit("J02-0003 report evidence IDs do not match the live ledger")
    if payloads["evidence_ledger.json"]["entries"][-1].get("summary") != core_summary():
        raise SystemExit("J02-0003 core summary changed before final sealing")
    before = numbered_generations(ralph_root)
    prior_ids = evidence_ids(payloads)
    summary, hashes = final_summary(parent)
    generation = commit_active_failed_generation(
        payloads=payloads, summary=summary, expected_evidence_id=final_id
    )
    _, current, sealed = current_state()
    if current != generation or generation_number(current) != generation_number(parent) + 1:
        raise SystemExit("J02-0003 final generation pointer mismatch")
    if evidence_ids(sealed) != [*prior_ids, final_id]:
        raise SystemExit("final seal did not append exactly one evidence entry")
    if sealed["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
        raise SystemExit("final evidence does not match the J02-0003 closeout seal")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("final seal did not preserve every prior generation")
    return {
        "mode": "final",
        "status": "active",
        "parent_generation": parent,
        "generation": generation,
        "evidence_id": final_id,
        "artifact_hashes": hashes,
        "state_verification": verify_generation_store(len(before) + 1),
        "completion_ready": False,
    }


def run_verify() -> dict[str, Any]:
    evidence.verify()
    _, generation, payloads = current_state()
    assert_active_preflight(payloads)
    report = read_json(ATTEMPT / "report.json")
    rah = report.get("rah_state")
    if not isinstance(rah, dict):
        raise SystemExit("J02-0003 report is not RAH-bound")
    core_generation = str(rah.get("core_generation"))
    core_id = str(rah.get("core_evidence_id"))
    final_id = str(rah.get("final_closeout_evidence_id"))
    identifiers = evidence_ids(payloads)
    if identifiers[-2:] != [core_id, final_id]:
        raise SystemExit("sealed ledger does not end with the J02 core/final evidence")
    if generation_number(generation) != generation_number(core_generation) + 1:
        raise SystemExit("sealed J02 final generation does not follow the core generation")
    summary, hashes = final_summary(core_generation)
    if payloads["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
        raise SystemExit("stored J02 final evidence differs from closeout artifacts")
    return {
        "mode": "verify",
        "status": "PASS",
        "generation": generation,
        "latest_evidence_id": final_id,
        "artifact_hashes": hashes,
        "state_verification": verify_generation_store(),
        "completion_ready": False,
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
