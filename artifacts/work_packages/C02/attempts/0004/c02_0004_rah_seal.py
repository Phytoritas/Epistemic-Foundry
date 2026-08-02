#!/usr/bin/env python3
"""Append C02-0004 PASS evidence to the active RAH state."""

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
ATTEMPT = ROOT / "artifacts/work_packages/C02/attempts/0004"
AUTOMATION = ROOT / ".rah/helpers/recursive-architecture-refactoring-auto/automation"
ATTEMPT_ID = "C02-0004"
EXPECTED_PARENT = "000098-c18c1114"
EXPECTED_PARENT_EVIDENCE = "E0100"
CORE_EVIDENCE_ID = "E0101"
FINAL_EVIDENCE_ID = "E0102"
sys.path.insert(0, str(ATTEMPT))
sys.path.insert(0, str(AUTOMATION))

import build_c02_0004_evidence as evidence  # noqa: E402
import ralph_harness as rh  # noqa: E402
import state_store  # noqa: E402


NEXT_ACTIONS = [
    "Execute B04-0009 deterministic canonical projection after C02-0004 PASS.",
    "Start O02-0002 only after B04-0009 PASS, then C04-0004 and final B04 packaging in order.",
    "Keep completion_ready=false until every remaining objective and closeout gate passes.",
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
        encoding="utf-8", newline="\n",
    )


def numbered_generations(ralph_root: Path) -> list[str]:
    return sorted(
        path.name for path in (ralph_root / "generations").iterdir()
        if path.is_dir() and re.fullmatch(r"\d{6}-[0-9a-f]{8}", path.name)
    )


def current_state() -> tuple[Path, str, dict[str, Any]]:
    ralph_root = ROOT / ".rah/ralph"
    current = state_store.read_current(ralph_root)
    if current is None:
        raise SystemExit("no committed RAH generation")
    generation, payloads = current
    if state_store.verify_current(ralph_root).get("generation") != generation:
        raise SystemExit("RAH current pointer and verified generation disagree")
    return ralph_root, generation, payloads


def evidence_ids(payloads: dict[str, Any]) -> list[str]:
    ledger = payloads.get("evidence_ledger.json")
    if not isinstance(ledger, dict) or not isinstance(ledger.get("entries"), list):
        raise SystemExit("invalid RAH evidence ledger")
    identifiers = [str(row.get("id")) for row in ledger["entries"] if isinstance(row, dict)]
    expected = [f"E{index:04d}" for index in range(1, len(identifiers) + 1)]
    if identifiers != expected or int(ledger.get("issued_id_high_water", 0)) != len(identifiers):
        raise SystemExit("RAH evidence ledger is not contiguous")
    return identifiers


def generation_number(generation: str) -> int:
    if re.fullmatch(r"\d{6}-[0-9a-f]{8}", generation) is None:
        raise SystemExit(f"malformed RAH generation: {generation}")
    return int(generation.split("-", 1)[0])


def artifact_hashes(names: tuple[str, ...]) -> dict[str, str]:
    result: dict[str, str] = {}
    for name in names:
        path = ATTEMPT / name
        if not path.is_file():
            raise SystemExit(f"required C02-0004 artifact missing: {name}")
        result[name] = sha256(path)
    return result


def core_summary() -> str:
    names = (
        "c02-contract-codegen-verification.json", "full-regression-impact.json",
        "preexisting-debt-reconciliation.json", "dependency-status.json",
        "write-scope-verification.json", "junit-normalization-verification.json",
        "c02-verification.artifact-receipt.json", "full-python-regression.junit.xml",
        "full-node-regression.junit.xml", "review.md", "build_c02_0004_evidence.py",
        "c02_0004_rah_seal.py",
    )
    hashes = artifact_hashes(names)
    return (
        "C02-0004 PASS core verification: the canonical generator projects "
        "127 schemas and 127 examples into nine deterministic Python, "
        "TypeScript, and UI artifacts. Seven stale generated files were "
        "refreshed only through the generator; manifest, model, fixture, "
        "strict TypeScript, and legacy-enum checks pass. Full Node is 819/819. "
        "Full Python is 1056 passed with exactly 17 order-independent, "
        "multiplicity-preserving matches to sealed C01-0009, all owned by "
        "B04-0009; C02-owned and new failures are zero. "
        + "; ".join(f"{name}=sha256:{digest}" for name, digest in hashes.items())
        + ". Review is primary-session separate with actor_independence=false. "
        "B04-0009 is next; implementation_gate=fail and completion_ready=false."
    )


def final_summary(parent: str) -> tuple[str, dict[str, str]]:
    names = (
        "report.json", "commands.jsonl", "review.md",
        "c02-contract-codegen-verification.json", "full-regression-impact.json",
        "preexisting-debt-reconciliation.json", "dependency-status.json",
        "write-scope-verification.json", "junit-normalization-verification.json",
        "c02-verification.artifact-receipt.json", "full-python-regression.junit.xml",
        "full-node-regression.junit.xml", "rah-core-integrity.json",
        "build_c02_0004_evidence.py", "c02_0004_rah_seal.py",
    )
    hashes = artifact_hashes(names)
    summary = (
        f"C02-0004 PASS closeout is hash-sealed after core generation {parent}: "
        + "; ".join(f"{name}=sha256:{digest}" for name, digest in hashes.items())
        + ". C01-0009 and all earlier attempts remain immutable. C02-0004 "
        "makes B04-0009 dependency-ready, but the exact 17 projection debts, "
        "O02-0002, C04-0004, final packaging, and the wider DAG remain; "
        "implementation_gate=fail and completion_ready=false."
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
        ledger, now=now, goal_id=goal["goal_id"],
        iteration=int(loop.get("current_iteration") or loop.get("iteration") or 1),
        kind="evidence", summary=summary,
    )
    if identifier != expected_evidence_id:
        raise SystemExit(f"unexpected evidence ID {identifier}; expected {expected_evidence_id}")
    goal.update({"status": "active", "updated_at_utc": now})
    loop.update(
        {
            "blocked_reason": None, "checkpoint_required": False,
            "current_stage": "ralph-active", "done": False,
            "generated_at_utc": now, "harness_phase": "execution",
            "implementation_gate": "fail", "loop_phase": "bounded-implementation",
            "mark_done_rejected": False, "next_actions": NEXT_ACTIONS,
            "status": "active", "updated_at_utc": now,
        }
    )
    readiness = loop.get("completion_readiness")
    if not isinstance(readiness, dict) or readiness.get("ready") is not False:
        raise SystemExit("completion readiness must remain explicitly false")
    readiness["evidence_count"] = len(ledger["entries"])
    loop["state_machine"] = {
        "allowed_next_states": ["verify", "plan", "blocked", "failed"],
        "current_state": "act",
        "states": ["intake", "plan", "act", "verify", "review", "decide", "done", "blocked", "cancelled", "failed"],
    }
    previous_used = loop.get("progress_update", {}).get("used_evidence", [])
    loop["progress_update"] = {
        "created_evidence": [identifier], "missing_acceptance_ids": [],
        "missing_closeout_ids": [], "missing_evidence_ids": [],
        "missing_validation_ids": [],
        "used_evidence": list(dict.fromkeys([*previous_used, *evidence_ids(payloads), identifier])),
    }
    plan = rh.build_plan_graph(goal, loop, payloads["plan_graph.json"], now)
    bridge = rh.build_goal_bridge(
        ROOT, goal, loop, payloads["goal_bridge.json"],
        SimpleNamespace(goal_status="active", goal_objective=str(goal["goal"])), now,
    )
    review = copy.deepcopy(payloads["review_gate.json"])
    review["updated_at_utc"] = now
    state_store.KEEP_GENERATIONS = 10_000
    generation = state_store.commit_generation(
        ROOT / ".rah/ralph",
        {
            "evidence_ledger.json": ledger, "goal.json": goal,
            "goal_bridge.json": bridge, "loop_state.json": loop,
            "plan_graph.json": plan, "review_gate.json": review,
        },
    )
    status_path = ROOT / ".rah/state/status.json"
    gates_path = ROOT / ".rah/state/gates.json"
    status = read_json(status_path)
    gates = read_json(gates_path)
    note = (
        "C02-0004 is evidence-sealed PASS and B04-0009 is next. The global "
        "implementation gate remains failed and completion_ready=false."
    )
    status["implementation_gate"] = "fail"
    status["implementation_gate_note"] = note
    status["next_recommended_action"] = NEXT_ACTIONS[0]
    prior_ids = gates.get("implementation_gate", {}).get("evidence_ids", [])
    gates["implementation_gate"] = {
        "evidence_ids": list(dict.fromkeys([*prior_ids, identifier])),
        "note": note, "status": "fail",
    }
    rh.write_json(status_path, status)
    rh.write_json(gates_path, gates)
    rh.refresh_status_for_ralph(ROOT, ROOT / ".rah", goal, loop, now)
    rh.upsert_current_loop(ROOT / ".rah/plans/current_loop.md", rh.render_managed_current_loop(goal, loop))
    rh.write_text(ROOT / ".rah/ralph/blockers.md", rh.render_blockers(goal, loop, now))
    return generation


def verify_generation_store(expected_count: int) -> dict[str, Any]:
    ralph_root, current, payloads = current_state()
    generations = numbered_generations(ralph_root)
    if len(generations) != expected_count or not generations or generations[-1] != current:
        raise SystemExit(f"expected {expected_count} generations ending at {current}, found {len(generations)}")
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
                raise SystemExit(f"generation payload hash mismatch: {generation}/{name}")
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
            authority = {key: value for key, value in authority.items() if key != "state_generation"}
        if state_store._dump(stripped) == state_store._dump(authority):
            flat_matches += 1
    loop = payloads["loop_state.json"]
    goal = payloads["goal.json"]
    if (
        flat_stamps != 6 or flat_matches != 6 or loop.get("status") != "active"
        or goal.get("status") != "active" or loop.get("implementation_gate") != "fail"
        or loop.get("completion_readiness", {}).get("ready") is not False
    ):
        raise SystemExit("RAH state is not active/fail with six matching flat projections")
    identifiers = evidence_ids(payloads)
    return {
        "attempt_id": ATTEMPT_ID, "status": "PASS", "mode": "READ_ONLY",
        "current_generation": current, "latest_evidence_id": identifiers[-1],
        "evidence_count": len(identifiers), "retained_generation_count": len(generations),
        "generation_file_hashes_verified": checked,
        "generation_manifest_sha256": "sha256:" + sha256(ralph_root / "generations" / current / "generation-manifest.json"),
        "flat_snapshot_stamps_verified": flat_stamps,
        "flat_snapshot_content_matches": flat_matches,
        "ralph_status": "active", "implementation_gate": "fail",
        "completion_ready": False, "parse_errors": {},
    }


def assert_active(payloads: dict[str, Any]) -> None:
    loop = payloads["loop_state.json"]
    goal = payloads["goal.json"]
    if (
        loop.get("status") != "active" or goal.get("status") != "active"
        or loop.get("blocked_reason") is not None or loop.get("implementation_gate") != "fail"
        or loop.get("completion_readiness", {}).get("ready") is not False
    ):
        raise SystemExit("C02-0004 seal requires active/fail/completion_ready=false")


def run_preflight() -> dict[str, Any]:
    checked = evidence.verify()
    ralph_root, generation, payloads = current_state()
    assert_active(payloads)
    if generation != EXPECTED_PARENT or evidence_ids(payloads)[-1] != EXPECTED_PARENT_EVIDENCE:
        raise SystemExit("C02-0004 parent is not generation 98 / E0100")
    generations = numbered_generations(ralph_root)
    if len(generations) != 98 or generations[-1] != generation:
        raise SystemExit("preflight requires exactly 98 preserved generations")
    if "rah_state" in read_json(ATTEMPT / "report.json"):
        raise SystemExit("C02-0004 report is already RAH-bound")
    return {
        **checked, "mode": "preflight", "generation": generation,
        "latest_evidence_id": EXPECTED_PARENT_EVIDENCE,
        "next_evidence_id": CORE_EVIDENCE_ID,
        "retained_generation_count": len(generations), "completion_ready": False,
    }


def run_core() -> dict[str, Any]:
    run_preflight()
    ralph_root, parent, payloads = current_state()
    before = numbered_generations(ralph_root)
    prior_ids = evidence_ids(payloads)
    summary = core_summary()
    generation = commit_active_failed_generation(
        payloads=payloads, summary=summary, expected_evidence_id=CORE_EVIDENCE_ID
    )
    _, current, sealed = current_state()
    if current != generation or generation_number(current) != generation_number(parent) + 1:
        raise SystemExit("core generation pointer mismatch")
    if evidence_ids(sealed) != [*prior_ids, CORE_EVIDENCE_ID]:
        raise SystemExit("core did not append exactly E0101")
    if sealed["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
        raise SystemExit("core evidence summary mismatch")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or len(after) != 99:
        raise SystemExit("core did not preserve all prior generations")
    integrity = verify_generation_store(99)
    write_json(ATTEMPT / "rah-core-integrity.json", integrity)
    evidence.bind_rah_state(
        core_generation=generation, core_evidence_id=CORE_EVIDENCE_ID,
        final_closeout_evidence_id=FINAL_EVIDENCE_ID,
    )
    evidence.verify()
    return {
        "mode": "core", "status": "active", "parent_generation": parent,
        "generation": generation, "evidence_id": CORE_EVIDENCE_ID,
        "final_closeout_evidence_id": FINAL_EVIDENCE_ID,
        "state_verification": integrity, "completion_ready": False,
    }


def run_final() -> dict[str, Any]:
    evidence.verify()
    ralph_root, parent, payloads = current_state()
    assert_active(payloads)
    report = read_json(ATTEMPT / "report.json")
    rah_state = report.get("rah_state")
    if not isinstance(rah_state, dict) or rah_state.get("core_generation") != parent:
        raise SystemExit("C02-0004 report does not bind current core generation")
    if (
        rah_state.get("core_evidence_id") != CORE_EVIDENCE_ID
        or rah_state.get("final_closeout_evidence_id") != FINAL_EVIDENCE_ID
        or evidence_ids(payloads)[-1] != CORE_EVIDENCE_ID
    ):
        raise SystemExit("C02-0004 report and live ledger evidence IDs disagree")
    if payloads["evidence_ledger.json"]["entries"][-1].get("summary") != core_summary():
        raise SystemExit("stored C02-0004 core summary changed before final seal")
    before = numbered_generations(ralph_root)
    prior_ids = evidence_ids(payloads)
    summary, hashes = final_summary(parent)
    generation = commit_active_failed_generation(
        payloads=payloads, summary=summary, expected_evidence_id=FINAL_EVIDENCE_ID
    )
    _, current, sealed = current_state()
    if current != generation or generation_number(current) != generation_number(parent) + 1:
        raise SystemExit("final generation pointer mismatch")
    if evidence_ids(sealed) != [*prior_ids, FINAL_EVIDENCE_ID]:
        raise SystemExit("final did not append exactly E0102")
    if sealed["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
        raise SystemExit("final closeout summary mismatch")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or len(after) != 100:
        raise SystemExit("final did not preserve all prior generations")
    return {
        "mode": "final", "status": "active", "parent_generation": parent,
        "generation": generation, "evidence_id": FINAL_EVIDENCE_ID,
        "artifact_hashes": hashes, "state_verification": verify_generation_store(100),
        "completion_ready": False,
    }


def run_verify() -> dict[str, Any]:
    evidence.verify()
    _, generation, payloads = current_state()
    assert_active(payloads)
    count = len(numbered_generations(ROOT / ".rah/ralph"))
    if count == 98:
        return run_preflight()
    if count == 99:
        integrity = verify_generation_store(99)
        if evidence_ids(payloads)[-1] != CORE_EVIDENCE_ID:
            raise SystemExit("C02-0004 core tail is not E0101")
        return {"mode": "core-verify", "status": "PASS", "state_verification": integrity}
    if count != 100 or generation_number(generation) != 100:
        raise SystemExit(f"unexpected C02-0004 generation count: {count}")
    identifiers = evidence_ids(payloads)
    if identifiers[-2:] != [CORE_EVIDENCE_ID, FINAL_EVIDENCE_ID]:
        raise SystemExit("sealed ledger does not end with C02 core/final evidence")
    report = read_json(ATTEMPT / "report.json")
    parent = str(report["rah_state"]["core_generation"])
    summary, hashes = final_summary(parent)
    if payloads["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
        raise SystemExit("stored final evidence differs from current closeout bytes")
    return {
        "mode": "verify", "status": "PASS", "generation": generation,
        "latest_evidence_id": FINAL_EVIDENCE_ID, "artifact_hashes": hashes,
        "state_verification": verify_generation_store(100), "completion_ready": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("preflight", "core", "final", "verify"))
    args = parser.parse_args()
    result = {
        "preflight": run_preflight, "core": run_core,
        "final": run_final, "verify": run_verify,
    }[args.mode]()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
