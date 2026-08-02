#!/usr/bin/env python3
"""Append L02-0001 core and closeout evidence to the active RAH state."""

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
ATTEMPT = ROOT / "artifacts/work_packages/L02/attempts/0001"
AUTOMATION = ROOT / ".rah/helpers/recursive-architecture-refactoring-auto/automation"
ATTEMPT_ID = "L02-0001"
sys.path.insert(0, str(ATTEMPT))
sys.path.insert(0, str(AUTOMATION))

import build_l02_0001_evidence as evidence  # noqa: E402
import ralph_harness as rh  # noqa: E402
import state_store  # noqa: E402


EXPECTED_INITIAL_PARENT = "000043-8eda1b40"
EXPECTED_INITIAL_EVIDENCE = "E0043"
EXPECTED_INITIAL_GENERATION_COUNT = 43
NEXT_ACTIONS = [
    "Recompute and seal the live 156-package DAG after L02-0001 PASS.",
    "Execute the resulting earliest dependency-ready package serially.",
    "Keep implementation_gate=fail and completion_ready=false until every package-level objective gate passes.",
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
        raise SystemExit("RAH pointer and generation verification disagree")
    return ralph_root, generation, payloads


def evidence_ids(payloads: dict[str, Any]) -> list[str]:
    ledger = payloads.get("evidence_ledger.json")
    if not isinstance(ledger, dict) or not isinstance(ledger.get("entries"), list):
        raise SystemExit("invalid RAH evidence ledger")
    identifiers = [
        str(row.get("id")) for row in ledger["entries"] if isinstance(row, dict)
    ]
    if any(re.fullmatch(r"E\d{4,}", value) is None for value in identifiers):
        raise SystemExit("RAH evidence ledger contains malformed IDs")
    return identifiers


def next_evidence_id(payloads: dict[str, Any]) -> str:
    identifiers = evidence_ids(payloads)
    high_water = int(payloads["evidence_ledger.json"].get("issued_id_high_water", 0))
    observed = max((int(value[1:]) for value in identifiers), default=0)
    if high_water != observed:
        raise SystemExit("RAH evidence high-water mark differs from ledger")
    return f"E{high_water + 1:04d}"


def increment_evidence_id(identifier: str) -> str:
    return f"E{int(identifier[1:]) + 1:04d}"


def generation_number(generation: str) -> int:
    if re.fullmatch(r"\d{6}-[0-9a-f]{8}", generation) is None:
        raise SystemExit(f"malformed generation: {generation}")
    return int(generation.split("-", 1)[0])


def artifact_hashes(names: tuple[str, ...]) -> dict[str, str]:
    result: dict[str, str] = {}
    for name in names:
        path = ATTEMPT / name
        if not path.is_file():
            raise SystemExit(f"required L02 artifact is missing: {name}")
        result[name] = sha256(path)
    return result


def core_summary() -> str:
    names = (
        "memory-index-retrieval-verification.json",
        "memory-index-retrieval-verification.artifact-receipt.json",
        "full-regression-impact.json",
        "write-scope-verification.json",
        "dependency-status.json",
        "syntax-verification.json",
        "schema-runtime-verification.json",
        "targeted-l02-node.junit.xml",
        "targeted-l02-coverage.stdout.log",
        "predecessor-l02-node.junit.xml",
        "full-node-suite.junit.xml",
        "full-python-suite.junit.xml",
        "node-test-inventory.json",
        "review.md",
        "build_l02_0001_evidence.py",
        "l02_0001_rah_seal.py",
    )
    hashes = artifact_hashes(names)
    return (
        "L02-0001 PASS: L01 policy admission occurs before index access and each "
        "selected record is retention-rechecked with its actual timestamp. The "
        "workflow searches only SESSION, WORKSPACE, USER, and EVIDENCE; allowed "
        "but non-retrievable EPHEMERAL/REGULATED stores fail closed before index "
        "access. Unicode NFKC token-overlap rank, result cap, searched/excluded "
        "partition, SEARCHED_NONE, source provenance, receipt identity/hash, "
        "replay, and tamper rejection are deterministic. Raw search text is not "
        "emitted. L03 retains redaction, dedupe, forget, deletion, and legal-hold "
        "ownership. Targeted L02 is 41/41 with memory-index.mjs coverage 91.49% "
        "lines, 75.97% branches, and 97.73% functions; canonical receipt schema "
        "validation has zero errors; L01 predecessor is 27/27; full Node is "
        "544/544 over 59 files; full Python is 1064/1064; codegen is 126/126. "
        f"Verification sha256:{hashes['memory-index-retrieval-verification.json']}; "
        f"receipt sha256:{hashes['memory-index-retrieval-verification.artifact-receipt.json']}; "
        f"regression sha256:{hashes['full-regression-impact.json']}; scope "
        f"sha256:{hashes['write-scope-verification.json']}; dependency sha256:"
        f"{hashes['dependency-status.json']}; syntax sha256:"
        f"{hashes['syntax-verification.json']}; schema runtime sha256:"
        f"{hashes['schema-runtime-verification.json']}; targeted JUnit sha256:"
        f"{hashes['targeted-l02-node.junit.xml']}; coverage sha256:"
        f"{hashes['targeted-l02-coverage.stdout.log']}; predecessor JUnit sha256:"
        f"{hashes['predecessor-l02-node.junit.xml']}; Node JUnit sha256:"
        f"{hashes['full-node-suite.junit.xml']}; Python JUnit sha256:"
        f"{hashes['full-python-suite.junit.xml']}; inventory sha256:"
        f"{hashes['node-test-inventory.json']}; review sha256:{hashes['review.md']}; "
        f"builder sha256:{hashes['build_l02_0001_evidence.py']}; sealer sha256:"
        f"{hashes['l02_0001_rah_seal.py']}. Review is primary-session separate "
        "with actor_independence=false under the product-owner no-subagent "
        "constraint. Global implementation_gate=fail and completion_ready=false."
    )


def final_summary(parent: str) -> tuple[str, dict[str, str]]:
    names = (
        "report.json",
        "commands.jsonl",
        "review.md",
        "memory-index-retrieval-verification.json",
        "memory-index-retrieval-verification.artifact-receipt.json",
        "full-regression-impact.json",
        "write-scope-verification.json",
        "dependency-status.json",
        "syntax-verification.json",
        "schema-runtime-verification.json",
        "targeted-l02-node.junit.xml",
        "predecessor-l02-node.junit.xml",
        "full-node-suite.junit.xml",
        "full-python-suite.junit.xml",
        "rah-core-integrity.json",
        "build_l02_0001_evidence.py",
        "l02_0001_rah_seal.py",
    )
    hashes = artifact_hashes(names)
    summary = (
        f"L02-0001 PASS closeout is hash-sealed after core generation {parent}: "
        f"report sha256:{hashes['report.json']}; commands sha256:"
        f"{hashes['commands.jsonl']}; review sha256:{hashes['review.md']}; "
        f"verification sha256:{hashes['memory-index-retrieval-verification.json']}; "
        f"receipt sha256:{hashes['memory-index-retrieval-verification.artifact-receipt.json']}; "
        f"regression sha256:{hashes['full-regression-impact.json']}; scope "
        f"sha256:{hashes['write-scope-verification.json']}; dependency sha256:"
        f"{hashes['dependency-status.json']}; syntax sha256:"
        f"{hashes['syntax-verification.json']}; schema runtime sha256:"
        f"{hashes['schema-runtime-verification.json']}; RAH integrity sha256:"
        f"{hashes['rah-core-integrity.json']}; builder sha256:"
        f"{hashes['build_l02_0001_evidence.py']}; sealer sha256:"
        f"{hashes['l02_0001_rah_seal.py']}. Every prior attempt, report, and "
        "generation is preserved. L02-0001 is immutable PASS and the live "
        "156-package DAG must now be recomputed. Global implementation_gate=fail "
        "and completion_ready=false."
    )
    return summary, hashes


def assert_active_preflight(payloads: dict[str, Any]) -> None:
    identifiers = evidence_ids(payloads)
    expected = [f"E{index:04d}" for index in range(1, len(identifiers) + 1)]
    loop = payloads["loop_state.json"]
    if identifiers != expected:
        raise SystemExit("L02 requires a contiguous evidence ledger")
    if not (
        loop.get("status") == "active"
        and loop.get("blocked_reason") is None
        and loop.get("implementation_gate") == "fail"
        and loop.get("completion_readiness", {}).get("ready") is False
    ):
        raise SystemExit("L02 preflight requires active/fail/completion_ready=false")


def commit_generation(
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
    previous = loop.get("progress_update", {}).get("used_evidence", [])
    loop["progress_update"] = {
        "created_evidence": [identifier],
        "missing_acceptance_ids": [],
        "missing_closeout_ids": [],
        "missing_evidence_ids": [],
        "missing_validation_ids": [],
        "used_evidence": list(
            dict.fromkeys([*previous, *evidence_ids(payloads), identifier])
        ),
    }
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
        "L02-0001 memory indexing and scoped retrieval is evidence-sealed PASS. "
        "The live DAG and downstream packages remain; implementation_gate=fail "
        "and completion_ready=false."
    )
    status["implementation_gate"] = "fail"
    status["implementation_gate_note"] = note
    status["next_recommended_action"] = NEXT_ACTIONS[0]
    existing = gates.get("implementation_gate", {}).get("evidence_ids", [])
    gates["implementation_gate"] = {
        "evidence_ids": list(dict.fromkeys([*existing, identifier])),
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
        raise SystemExit(f"expected {expected_count} generations, found {len(generations)}")
    if not generations or generations[-1] != current:
        raise SystemExit("generation inventory does not end at current")
    checked = 0
    for generation in generations:
        generation_root = ralph_root / "generations" / generation
        manifest = read_json(generation_root / "generation-manifest.json")
        files = manifest.get("files")
        if manifest.get("generation") != generation or not isinstance(files, dict):
            raise SystemExit(f"invalid generation manifest: {generation}")
        if set(files) != set(state_store.GENERATION_FILES):
            raise SystemExit(f"generation file inventory changed: {generation}")
        for name in state_store.GENERATION_FILES:
            if sha256(generation_root / name) != files[name]:
                raise SystemExit(f"generation hash mismatch: {generation}/{name}")
            checked += 1
    stamps = 0
    matches = 0
    for name in state_store.GENERATION_FILES:
        flat = read_json(ralph_root / name)
        if flat.get("state_generation") == current:
            stamps += 1
        stripped = {key: value for key, value in flat.items() if key != "state_generation"}
        authority = payloads[name]
        if isinstance(authority, dict):
            authority = {
                key: value
                for key, value in authority.items()
                if key != "state_generation"
            }
        if state_store._dump(stripped) == state_store._dump(authority):
            matches += 1
    loop = payloads["loop_state.json"]
    if not (
        stamps == matches == 6
        and loop.get("status") == "active"
        and loop.get("implementation_gate") == "fail"
        and loop.get("completion_readiness", {}).get("ready") is False
    ):
        raise SystemExit("RAH did not remain active/fail/completion_ready=false")
    identifiers = evidence_ids(payloads)
    expected_ids = [f"E{index:04d}" for index in range(1, len(identifiers) + 1)]
    if identifiers != expected_ids:
        raise SystemExit("RAH evidence ledger is not contiguous")
    return {
        "attempt_id": ATTEMPT_ID,
        "completion_ready": False,
        "current_generation": current,
        "evidence_count": len(identifiers),
        "flat_snapshot_content_matches": matches,
        "flat_snapshot_stamps_verified": stamps,
        "generation_file_hashes_verified": checked,
        "generation_manifest_sha256": "sha256:"
        + sha256(ralph_root / "generations" / current / "generation-manifest.json"),
        "implementation_gate": "fail",
        "latest_evidence_id": identifiers[-1],
        "parse_errors": {},
        "ralph_status": "active",
        "retained_generation_count": len(generations),
        "retained_generations": generations,
        "status": "PASS",
        "work_package_id": "L02",
    }


def run_preflight() -> dict[str, Any]:
    evidence.verify()
    ralph_root, generation, payloads = current_state()
    assert_active_preflight(payloads)
    report = read_json(ATTEMPT / "report.json")
    if "rah_state" in report:
        raise SystemExit("L02 report is already RAH-bound; use verify")
    identifiers = evidence_ids(payloads)
    if not (
        generation == EXPECTED_INITIAL_PARENT
        and identifiers[-1] == EXPECTED_INITIAL_EVIDENCE
        and len(numbered_generations(ralph_root)) == EXPECTED_INITIAL_GENERATION_COUNT
    ):
        raise SystemExit("L02 preflight is not at the sealed post-L01 DAG state")
    return {
        "completion_ready": False,
        "generation": generation,
        "latest_evidence_id": identifiers[-1],
        "mode": "preflight",
        "next_evidence_id": next_evidence_id(payloads),
        "retained_generation_count": EXPECTED_INITIAL_GENERATION_COUNT,
        "status": "PASS",
    }


def run_core() -> dict[str, Any]:
    preflight = run_preflight()
    ralph_root, parent, payloads = current_state()
    before = numbered_generations(ralph_root)
    prior_ids = evidence_ids(payloads)
    core_id = next_evidence_id(payloads)
    final_id = increment_evidence_id(core_id)
    summary = core_summary()
    generation = commit_generation(
        payloads=payloads,
        summary=summary,
        expected_evidence_id=core_id,
    )
    _, current, sealed = current_state()
    if current != generation or generation_number(current) != generation_number(parent) + 1:
        raise SystemExit("L02 core generation pointer mismatch")
    if evidence_ids(sealed) != [*prior_ids, core_id]:
        raise SystemExit("L02 core did not append exactly one evidence row")
    if sealed["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
        raise SystemExit("L02 core evidence summary mismatch")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("L02 core did not preserve every prior generation")
    integrity = verify_generation_store(len(before) + 1)
    write_json(ATTEMPT / "rah-core-integrity.json", integrity)
    evidence.bind_rah_state(
        core_generation=generation,
        core_evidence_id=core_id,
        final_closeout_evidence_id=final_id,
    )
    evidence.verify()
    return {
        "completion_ready": False,
        "evidence_id": core_id,
        "final_closeout_evidence_id": final_id,
        "generation": generation,
        "mode": "core",
        "parent_generation": parent,
        "preflight": preflight,
        "state_verification": integrity,
        "status": "active",
    }


def run_final() -> dict[str, Any]:
    evidence.verify()
    ralph_root, parent, payloads = current_state()
    assert_active_preflight(payloads)
    report = read_json(ATTEMPT / "report.json")
    rah = report.get("rah_state")
    if not isinstance(rah, dict) or rah.get("core_generation") != parent:
        raise SystemExit("L02 report does not bind the current core generation")
    core_id = str(rah.get("core_evidence_id"))
    final_id = str(rah.get("final_closeout_evidence_id"))
    if evidence_ids(payloads)[-1] != core_id or next_evidence_id(payloads) != final_id:
        raise SystemExit("L02 evidence identifiers differ from the live ledger")
    if payloads["evidence_ledger.json"]["entries"][-1].get("summary") != core_summary():
        raise SystemExit("L02 core summary changed before final sealing")
    before = numbered_generations(ralph_root)
    prior_ids = evidence_ids(payloads)
    summary, hashes = final_summary(parent)
    generation = commit_generation(
        payloads=payloads,
        summary=summary,
        expected_evidence_id=final_id,
    )
    _, current, sealed = current_state()
    if current != generation or generation_number(current) != generation_number(parent) + 1:
        raise SystemExit("L02 final generation pointer mismatch")
    if evidence_ids(sealed) != [*prior_ids, final_id]:
        raise SystemExit("L02 final did not append exactly one evidence row")
    if sealed["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
        raise SystemExit("L02 final evidence summary mismatch")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("L02 final did not preserve every prior generation")
    return {
        "artifact_hashes": hashes,
        "completion_ready": False,
        "evidence_id": final_id,
        "generation": generation,
        "mode": "final",
        "parent_generation": parent,
        "state_verification": verify_generation_store(len(before) + 1),
        "status": "active",
    }


def run_verify() -> dict[str, Any]:
    evidence.verify()
    _, generation, payloads = current_state()
    assert_active_preflight(payloads)
    report = read_json(ATTEMPT / "report.json")
    rah = report.get("rah_state")
    if not isinstance(rah, dict):
        raise SystemExit("L02 report is not RAH-bound")
    core_generation = str(rah.get("core_generation"))
    core_id = str(rah.get("core_evidence_id"))
    final_id = str(rah.get("final_closeout_evidence_id"))
    if evidence_ids(payloads)[-2:] != [core_id, final_id]:
        raise SystemExit("RAH ledger does not end with L02 core/final evidence")
    if generation_number(generation) != generation_number(core_generation) + 1:
        raise SystemExit("L02 final generation does not follow core")
    summary, hashes = final_summary(core_generation)
    if payloads["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
        raise SystemExit("stored L02 final summary differs from artifacts")
    return {
        "artifact_hashes": hashes,
        "completion_ready": False,
        "generation": generation,
        "latest_evidence_id": final_id,
        "mode": "verify",
        "state_verification": verify_generation_store(),
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
