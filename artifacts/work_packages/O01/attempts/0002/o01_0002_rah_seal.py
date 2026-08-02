#!/usr/bin/env python3
"""Append O01-0002 core and closeout evidence to the active RAH state."""

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
ATTEMPT = ROOT / "artifacts/work_packages/O01/attempts/0002"
AUTOMATION = ROOT / ".rah/helpers/recursive-architecture-refactoring-auto/automation"
sys.path.insert(0, str(ATTEMPT))
sys.path.insert(0, str(AUTOMATION))

import build_o01_0002_evidence as evidence  # noqa: E402
import ralph_harness as rh  # noqa: E402
import state_store  # noqa: E402


ATTEMPT_ID = "O01-0002"
EXPECTED_INITIAL_PARENT = "000080-62efd6bc"
EXPECTED_INITIAL_PARENT_MANIFEST_SHA256 = (
    "3ccaaca630b4acad5e9f13e31f1e75885249098a0ec6ccab2f35b910337625f9"
)
EXPECTED_INITIAL_EVIDENCE = "E0080"
EXPECTED_INITIAL_GENERATION_COUNT = 80
EXPECTED_CORE_EVIDENCE = "E0081"
EXPECTED_FINAL_EVIDENCE = "E0082"
NEXT_ACTIONS = [
    "Recompute and seal the live 156-package DAG after O01-0002 PASS.",
    "Execute the resulting earliest dependency-ready package serially.",
    "Keep implementation_gate=fail and completion_ready=false until every source and objective gate passes.",
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
    return ralph_root, current[0], current[1]


def evidence_ids(payloads: dict[str, Any]) -> list[str]:
    entries = payloads.get("evidence_ledger.json", {}).get("entries")
    if not isinstance(entries, list):
        raise SystemExit("invalid RAH evidence ledger")
    return [str(row.get("id")) for row in entries if isinstance(row, dict)]


def next_evidence_id(payloads: dict[str, Any]) -> str:
    identifiers = evidence_ids(payloads)
    if not identifiers:
        return "E0001"
    return f"E{int(identifiers[-1][1:]) + 1:04d}"


def increment_evidence_id(identifier: str) -> str:
    return f"E{int(identifier[1:]) + 1:04d}"


def generation_number(generation: str) -> int:
    return int(generation.split("-", 1)[0])


def artifact_hashes(names: tuple[str, ...]) -> dict[str, str]:
    result: dict[str, str] = {}
    for name in names:
        path = ATTEMPT / name
        if not path.is_file():
            raise SystemExit(f"required O01 artifact missing: {name}")
        result[name] = sha256(path)
    return result


def core_summary() -> str:
    names = (
        "query-plan-verification.json",
        "query-plan-verification.artifact-receipt.json",
        "receipt-completeness-verification.json",
        "schema-example-workflow-verification.json",
        "full-regression-impact.json",
        "c02-projection-verification.json",
        "b04-projection-verification.json",
        "dependency-status.json",
        "write-scope-verification.json",
        "targeted-o01-python.junit.xml",
        "full-python-suite.junit.xml",
        "full-node-suite.junit.xml",
        "node-test-inventory.json",
        "review.md",
        "attempt-metadata.json",
        "generate_o01_examples.py",
        "build_o01_0002_evidence.py",
        "o01_0002_rah_seal.py",
    )
    hashes = artifact_hashes(names)
    return (
        "O01-0002 PASS: the closed eleven-lane vocabulary and canonical order, "
        "exact non-waivable E0-E5 class floors, monotonic optional selection, "
        "immutable request/classification/policy binding, plan hashing, six typed "
        "receipt states, selected execution versus unselected sentinel exclusivity, "
        "all-eleven reconciliation, exact query-text hashing, run precedence, and "
        "scope-bounded absence/novelty ceilings pass. The workflow has 20 unique "
        "nodes with selected-only dispatch/fan-in and no missing dependency. "
        "Targeted O01 is 41/41; full Python is 1064/1064; full Node is 819/819 "
        "across 79 files; C02 is current at 126/126 and nine generated files; B04 "
        "is current at 127 resources plus registry. Query verification sha256:"
        f"{hashes['query-plan-verification.json']}; receipt verification sha256:"
        f"{hashes['receipt-completeness-verification.json']}; artifact receipt sha256:"
        f"{hashes['query-plan-verification.artifact-receipt.json']}; schema/workflow "
        f"sha256:{hashes['schema-example-workflow-verification.json']}; regression "
        f"sha256:{hashes['full-regression-impact.json']}; C02 sha256:"
        f"{hashes['c02-projection-verification.json']}; B04 sha256:"
        f"{hashes['b04-projection-verification.json']}; dependency sha256:"
        f"{hashes['dependency-status.json']}; scope sha256:"
        f"{hashes['write-scope-verification.json']}; targeted JUnit sha256:"
        f"{hashes['targeted-o01-python.junit.xml']}; Python JUnit sha256:"
        f"{hashes['full-python-suite.junit.xml']}; Node JUnit sha256:"
        f"{hashes['full-node-suite.junit.xml']}; review sha256:{hashes['review.md']}; "
        f"builder sha256:{hashes['build_o01_0002_evidence.py']}; sealer sha256:"
        f"{hashes['o01_0002_rah_seal.py']}. Review is primary-session separate with "
        "actor_independence=false under the product-owner no-subagent constraint. "
        "Global implementation_gate=fail and completion_ready=false."
    )


def final_summary(parent: str) -> tuple[str, dict[str, str]]:
    names = (
        "report.json",
        "commands.jsonl",
        "review.md",
        "query-plan-verification.json",
        "query-plan-verification.artifact-receipt.json",
        "receipt-completeness-verification.json",
        "schema-example-workflow-verification.json",
        "full-regression-impact.json",
        "c02-projection-verification.json",
        "b04-projection-verification.json",
        "dependency-status.json",
        "write-scope-verification.json",
        "rah-core-integrity.json",
        "build_o01_0002_evidence.py",
        "o01_0002_rah_seal.py",
    )
    hashes = artifact_hashes(names)
    summary = (
        f"O01-0002 PASS closeout is hash-sealed after core generation {parent}: "
        f"report sha256:{hashes['report.json']}; commands sha256:"
        f"{hashes['commands.jsonl']}; review sha256:{hashes['review.md']}; query "
        f"verification sha256:{hashes['query-plan-verification.json']}; receipt "
        f"verification sha256:{hashes['receipt-completeness-verification.json']}; "
        f"artifact receipt sha256:{hashes['query-plan-verification.artifact-receipt.json']}; "
        f"schema/workflow sha256:{hashes['schema-example-workflow-verification.json']}; "
        f"regression sha256:{hashes['full-regression-impact.json']}; C02 sha256:"
        f"{hashes['c02-projection-verification.json']}; B04 sha256:"
        f"{hashes['b04-projection-verification.json']}; dependency sha256:"
        f"{hashes['dependency-status.json']}; scope sha256:"
        f"{hashes['write-scope-verification.json']}; RAH integrity sha256:"
        f"{hashes['rah-core-integrity.json']}; builder sha256:"
        f"{hashes['build_o01_0002_evidence.py']}; sealer sha256:"
        f"{hashes['o01_0002_rah_seal.py']}. O01-0001 remains immutable SPEC_GAP "
        "history and every prior generation is preserved. O01-0002 is immutable "
        "PASS; the live 156-package DAG must now be recomputed. Global "
        "implementation_gate=fail and completion_ready=false."
    )
    return summary, hashes


def assert_active_state(payloads: dict[str, Any], *, allow_bounded_pass: bool) -> None:
    identifiers = evidence_ids(payloads)
    if identifiers != [f"E{index:04d}" for index in range(1, len(identifiers) + 1)]:
        raise SystemExit("O01 requires a contiguous evidence ledger")
    loop = payloads["loop_state.json"]
    allowed = {"pass", "fail"} if allow_bounded_pass else {"fail"}
    if not (
        loop.get("status") == "active"
        and loop.get("blocked_reason") is None
        and loop.get("implementation_gate") in allowed
        and loop.get("completion_readiness", {}).get("ready") is False
    ):
        raise SystemExit("O01 RAH state is not active with completion_ready=false")


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
        raise SystemExit(f"unexpected evidence ID {identifier}")
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
        raise SystemExit("completion readiness must remain false")
    readiness["evidence_count"] = len(ledger["entries"])
    previous = loop.get("progress_update", {}).get("used_evidence", [])
    loop["progress_update"] = {
        "created_evidence": [identifier],
        "missing_acceptance_ids": [],
        "missing_closeout_ids": [],
        "missing_evidence_ids": [],
        "missing_validation_ids": [],
        "used_evidence": list(dict.fromkeys([*previous, *evidence_ids(payloads), identifier])),
    }
    loop["state_machine"] = {
        "allowed_next_states": ["verify", "plan", "blocked", "failed"],
        "current_state": "act",
        "states": [
            "intake", "plan", "act", "verify", "review", "decide", "done",
            "blocked", "cancelled", "failed",
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
        "O01-0002 QueryPlan, SearchLaneReceipt and completeness contracts are "
        "evidence-sealed PASS. Downstream packages and source/PRD coverage remain; "
        "implementation_gate=fail and completion_ready=false."
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
        directory = ralph_root / "generations" / generation
        manifest = read_json(directory / "generation-manifest.json")
        files = manifest.get("files")
        if manifest.get("generation") != generation or not isinstance(files, dict):
            raise SystemExit(f"invalid generation manifest: {generation}")
        if set(files) != set(state_store.GENERATION_FILES):
            raise SystemExit(f"generation file inventory changed: {generation}")
        for name in state_store.GENERATION_FILES:
            if sha256(directory / name) != files[name]:
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
            authority = {key: value for key, value in authority.items() if key != "state_generation"}
        if state_store._dump(stripped) == state_store._dump(authority):
            matches += 1
    assert_active_state(payloads, allow_bounded_pass=False)
    identifiers = evidence_ids(payloads)
    if stamps != 6 or matches != 6:
        raise SystemExit("RAH flat snapshot verification mismatch")
    return {
        "attempt_id": ATTEMPT_ID,
        "completion_ready": False,
        "current_generation": current,
        "evidence_count": len(identifiers),
        "flat_snapshot_content_matches": matches,
        "flat_snapshot_stamps_verified": stamps,
        "generation_file_hashes_verified": checked,
        "generation_manifest_sha256": "sha256:" + sha256(
            ralph_root / "generations" / current / "generation-manifest.json"
        ),
        "implementation_gate": "fail",
        "latest_evidence_id": identifiers[-1],
        "parse_errors": {},
        "ralph_status": "active",
        "retained_generation_count": len(generations),
        "retained_generations": generations,
        "status": "PASS",
        "work_package_id": "O01",
    }


def run_preflight() -> dict[str, Any]:
    evidence.verify()
    ralph_root, generation, payloads = current_state()
    assert_active_state(payloads, allow_bounded_pass=True)
    report = read_json(ATTEMPT / "report.json")
    if "rah_state" in report:
        raise SystemExit("O01 report already RAH-bound; use verify")
    identifiers = evidence_ids(payloads)
    manifest = ralph_root / "generations" / generation / "generation-manifest.json"
    if not (
        generation == EXPECTED_INITIAL_PARENT
        and sha256(manifest) == EXPECTED_INITIAL_PARENT_MANIFEST_SHA256
        and identifiers[-1] == EXPECTED_INITIAL_EVIDENCE
        and len(numbered_generations(ralph_root)) == EXPECTED_INITIAL_GENERATION_COUNT
        and payloads["loop_state.json"].get("implementation_gate") == "pass"
    ):
        raise SystemExit("O01 preflight is not at exact bounded E0080 state")
    return {
        "completion_ready": False,
        "generation": generation,
        "latest_evidence_id": identifiers[-1],
        "mode": "preflight",
        "next_evidence_id": next_evidence_id(payloads),
        "parent_generation_manifest_sha256": "sha256:" + sha256(manifest),
        "retained_generation_count": len(numbered_generations(ralph_root)),
        "status": "PASS",
    }


def run_core() -> dict[str, Any]:
    preflight = run_preflight()
    ralph_root, parent, payloads = current_state()
    before = numbered_generations(ralph_root)
    prior_ids = evidence_ids(payloads)
    core_id = next_evidence_id(payloads)
    final_id = increment_evidence_id(core_id)
    if core_id != EXPECTED_CORE_EVIDENCE or final_id != EXPECTED_FINAL_EVIDENCE:
        raise SystemExit("O01 evidence allocation changed")
    summary = core_summary()
    generation = commit_generation(
        payloads=payloads, summary=summary, expected_evidence_id=core_id
    )
    _, current, sealed = current_state()
    if current != generation or generation_number(current) != generation_number(parent) + 1:
        raise SystemExit("O01 core generation pointer mismatch")
    if evidence_ids(sealed) != [*prior_ids, core_id]:
        raise SystemExit("O01 core did not append exactly one evidence row")
    if sealed["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
        raise SystemExit("O01 core summary mismatch")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("O01 core did not preserve every prior generation")
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
    assert_active_state(payloads, allow_bounded_pass=False)
    report = read_json(ATTEMPT / "report.json")
    rah = report.get("rah_state")
    if not isinstance(rah, dict) or rah.get("core_generation") != parent:
        raise SystemExit("O01 report does not bind current core generation")
    core_id = str(rah.get("core_evidence_id"))
    final_id = str(rah.get("final_closeout_evidence_id"))
    if evidence_ids(payloads)[-1] != core_id or next_evidence_id(payloads) != final_id:
        raise SystemExit("O01 evidence identifiers differ from live ledger")
    if payloads["evidence_ledger.json"]["entries"][-1].get("summary") != core_summary():
        raise SystemExit("O01 core summary changed before final seal")
    before = numbered_generations(ralph_root)
    prior_ids = evidence_ids(payloads)
    summary, hashes = final_summary(parent)
    generation = commit_generation(
        payloads=payloads, summary=summary, expected_evidence_id=final_id
    )
    _, current, sealed = current_state()
    if current != generation or generation_number(current) != generation_number(parent) + 1:
        raise SystemExit("O01 final generation pointer mismatch")
    if evidence_ids(sealed) != [*prior_ids, final_id]:
        raise SystemExit("O01 final did not append exactly one evidence row")
    if sealed["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
        raise SystemExit("O01 final summary mismatch")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("O01 final did not preserve every prior generation")
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
    assert_active_state(payloads, allow_bounded_pass=False)
    report = read_json(ATTEMPT / "report.json")
    rah = report.get("rah_state")
    if not isinstance(rah, dict):
        raise SystemExit("O01 report is not RAH-bound")
    core_generation = str(rah.get("core_generation"))
    core_id = str(rah.get("core_evidence_id"))
    final_id = str(rah.get("final_closeout_evidence_id"))
    if [core_id, final_id] != [EXPECTED_CORE_EVIDENCE, EXPECTED_FINAL_EVIDENCE]:
        raise SystemExit("O01 report RAH IDs changed")
    if evidence_ids(payloads)[-2:] != [core_id, final_id]:
        raise SystemExit("RAH ledger does not end with O01 core/final evidence")
    if generation_number(generation) != generation_number(core_generation) + 1:
        raise SystemExit("O01 final generation does not follow core")
    summary, hashes = final_summary(core_generation)
    if payloads["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
        raise SystemExit("stored O01 final summary differs from artifacts")
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
