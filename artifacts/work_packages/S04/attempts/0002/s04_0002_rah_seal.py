#!/usr/bin/env python3
"""Append S04-0002 PASS evidence while the global repair goal stays active."""

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
ATTEMPT = ROOT / "artifacts/work_packages/S04/attempts/0002"
AUTOMATION = ROOT / ".rah/helpers/recursive-architecture-refactoring-auto/automation"
sys.path.insert(0, str(ATTEMPT))
sys.path.insert(0, str(AUTOMATION))

import ralph_harness as rh  # noqa: E402
import s04_0002_evidence as evidence  # noqa: E402
import state_store  # noqa: E402


CORE_PARENT = "000086-8fc2cce9"
CORE_EVIDENCE_ID = "E0094"
FINAL_EVIDENCE_ID = "E0095"
PRESERVED_GENERATIONS = [
    "000079-fadeffe1",
    "000080-cccce3eb",
    "000081-843d5565",
    "000082-b49a186b",
    "000083-85fd47c1",
    "000084-016aba75",
    "000085-44f41b7e",
    "000086-8fc2cce9",
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
    "Resume the fixed sequence with C01 contract revalidation against the approved successor manifest.",
    "Continue C02, C03, C04, and B04 canonical correction only after each predecessor passes.",
    "Then run A05 correction, A06 audit, J02-0003, K01-0002, T01-0002, and recompute the 156-package DAG.",
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
            raise SystemExit(f"required S04-0002 artifact is missing: {name}")
        result[name] = sha256(path)
    return result


def core_summary() -> str:
    names = (
        "active-source-binding-verification.json",
        "full-regression-impact.json",
        "junit-normalization-verification.json",
        "targeted-security-suite.junit.xml",
        "full-node-suite.junit.xml",
        "full-python-suite.junit.xml",
        "review.md",
        "s04_0002_evidence.py",
        "s04_0002_rah_seal.py",
    )
    hashes = artifact_hashes(names)
    return (
        "S04-0002 PASS under HD-EF4-UNBLOCK-SET-20260730-001: active binding "
        f"{evidence.BINDING_ID} validates current successor sha256:"
        f"{evidence.SUCCESSOR_MANIFEST_HASH}; binding self-hash "
        f"{evidence.BINDING_HASH}; patch-plan self-hash {evidence.PATCH_PLAN_HASH}; "
        "31/31 replacement hashes and five HumanDecision self-hashes reconcile; "
        "EF4-I31 references the binding; immutable S04 root history and eight "
        "non-manifest source bindings remain exact. Targeted security is 67/67 "
        "and full Node is 458/458, resolving S04-TM004. Full Python is not green: "
        "963 pass plus exactly one J02-owned exact-tiktoken migration debt. "
        f"Binding evidence sha256:{hashes['active-source-binding-verification.json']}; "
        f"regression evidence sha256:{hashes['full-regression-impact.json']}; "
        f"normalization evidence sha256:{hashes['junit-normalization-verification.json']}; "
        f"review sha256:{hashes['review.md']}; builder sha256:"
        f"{hashes['s04_0002_evidence.py']}; sealer sha256:"
        f"{hashes['s04_0002_rah_seal.py']}. S04-owned failures are zero. Review "
        "is primary-session separate with actor_independence=false, not external "
        "certification. Global implementation_gate remains fail; C01 is next; "
        "completion_ready=false."
    )


def final_summary(parent: str) -> tuple[str, dict[str, str]]:
    names = (
        "report.json",
        "commands.jsonl",
        "review.md",
        "active-source-binding-verification.json",
        "full-regression-impact.json",
        "junit-normalization-verification.json",
        "rah-core-integrity.json",
        "s04_0002_evidence.py",
        "s04_0002_rah_seal.py",
    )
    hashes = artifact_hashes(names)
    summary = (
        f"S04-0002 PASS closeout is hash-sealed after core generation {parent}: "
        f"report sha256:{hashes['report.json']}; commands sha256:"
        f"{hashes['commands.jsonl']}; review sha256:{hashes['review.md']}; "
        f"binding evidence sha256:{hashes['active-source-binding-verification.json']}; "
        f"regression evidence sha256:{hashes['full-regression-impact.json']}; "
        f"normalization evidence sha256:{hashes['junit-normalization-verification.json']}; "
        f"core RAH integrity sha256:{hashes['rah-core-integrity.json']}; builder "
        f"sha256:{hashes['s04_0002_evidence.py']}; sealer sha256:"
        f"{hashes['s04_0002_rah_seal.py']}. S04-0002 is PASS, S04-TM004 is "
        "resolved, all prior S04 and RAH history remains immutable, the global "
        "implementation gate remains failed, C01 is next, and "
        "completion_ready=false."
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
    used = ["E0092", "E0093", identifier]
    if expected_evidence_id == FINAL_EVIDENCE_ID:
        used.insert(2, CORE_EVIDENCE_ID)
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
        "S04-0002 active source-binding correction is evidence-sealed PASS; "
        "S04-TM004 is resolved. C01 is next; global implementation_gate "
        "remains fail and completion_ready=false."
    )
    status["implementation_gate"] = "fail"
    status["implementation_gate_note"] = note
    status["next_recommended_action"] = NEXT_ACTIONS[0]
    existing_ids = gates.get("implementation_gate", {}).get("evidence_ids", [])
    gate_ids = list(dict.fromkeys([*existing_ids, CORE_EVIDENCE_ID]))
    if expected_evidence_id == FINAL_EVIDENCE_ID:
        gate_ids.append(FINAL_EVIDENCE_ID)
    gates["implementation_gate"] = {
        "evidence_ids": list(dict.fromkeys(gate_ids)),
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


def verify_generation_store(expected_count: int) -> dict[str, Any]:
    ralph_root, current, payloads = current_state()
    generations = numbered_generations(ralph_root)
    if len(generations) != expected_count or generations[-1] != current:
        raise SystemExit("retained generation inventory mismatch")
    checked = 0
    for generation in generations:
        root = ralph_root / "generations" / generation
        manifest = read_json(root / "generation-manifest.json")
        files = manifest.get("files")
        if manifest.get("generation") != generation or not isinstance(files, dict):
            raise SystemExit(f"invalid generation manifest: {generation}")
        if set(files) != set(state_store.GENERATION_FILES):
            raise SystemExit(f"generation file set mismatch: {generation}")
        for name in state_store.GENERATION_FILES:
            if sha256(root / name) != files[name]:
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
                key: value for key, value in authority.items() if key != "state_generation"
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
    return {
        "completion_ready": False,
        "current_generation": current,
        "flat_snapshot_content_matches": flat_matches,
        "flat_snapshot_stamps_verified": flat_stamps,
        "generation_file_hashes_verified": checked,
        "generation_manifest_sha256": "sha256:"
        + sha256(ralph_root / "generations" / current / "generation-manifest.json"),
        "latest_evidence_id": evidence_ids(payloads)[-1],
        "retained_generation_count": len(generations),
        "retained_generations": generations,
        "status": "active",
    }


def run_preflight() -> dict[str, Any]:
    evidence.verify_evidence(require_closeout=False)
    ralph_root, generation, payloads = current_state()
    if generation != CORE_PARENT:
        raise SystemExit(f"unexpected S04-0002 core parent: {generation}")
    if numbered_generations(ralph_root) != PRESERVED_GENERATIONS:
        raise SystemExit("S04-0002 preflight retained-generation inventory changed")
    if evidence_ids(payloads) != [f"E{index:04d}" for index in range(1, 94)]:
        raise SystemExit("S04-0002 preflight requires contiguous E0001-E0093")
    loop = payloads["loop_state.json"]
    if (
        loop.get("status") != "active"
        or loop.get("implementation_gate") != "fail"
        or loop.get("completion_readiness", {}).get("ready") is not False
    ):
        raise SystemExit("preflight requires active/fail/completion_ready=false")
    return {
        "completion_ready": False,
        "generation": generation,
        "latest_evidence_id": "E0093",
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
    if current != generation or not re.fullmatch(r"000087-[0-9a-f]{8}", current):
        raise SystemExit("S04-0002 core generation pointer mismatch")
    if evidence_ids(sealed) != [f"E{index:04d}" for index in range(1, 95)]:
        raise SystemExit("core seal did not append exactly E0094")
    if sealed["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
        raise SystemExit("E0094 does not match the S04-0002 core summary")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("core seal did not preserve every prior generation")
    return {
        "completion_ready": False,
        "evidence_id": CORE_EVIDENCE_ID,
        "generation": generation,
        "mode": "core",
        "parent_generation": parent,
        "state_verification": verify_generation_store(9),
        "status": "active",
    }


def run_final() -> dict[str, Any]:
    evidence.verify_evidence(require_closeout=True)
    ralph_root, parent, payloads = current_state()
    if not re.fullmatch(r"000087-[0-9a-f]{8}", parent):
        raise SystemExit(f"unexpected S04-0002 final parent: {parent}")
    if evidence_ids(payloads) != [f"E{index:04d}" for index in range(1, 95)]:
        raise SystemExit("final seal requires contiguous E0001-E0094")
    if payloads["evidence_ledger.json"]["entries"][-1].get("summary") != core_summary():
        raise SystemExit("E0094 changed before final sealing")
    report = read_json(ATTEMPT / "report.json")
    rah = report.get("rah_state")
    if not isinstance(rah, dict) or rah.get("core_generation") != parent:
        raise SystemExit("report does not bind the core RAH generation")
    if rah.get("core_evidence_id") != CORE_EVIDENCE_ID:
        raise SystemExit("report does not bind E0094")
    if rah.get("final_closeout_evidence_id") != FINAL_EVIDENCE_ID:
        raise SystemExit("report does not reserve E0095")
    summary, hashes = final_summary(parent)
    before = numbered_generations(ralph_root)
    generation = commit_active_failed_generation(
        payloads=payloads, summary=summary, expected_evidence_id=FINAL_EVIDENCE_ID
    )
    _, current, sealed = current_state()
    if current != generation or not re.fullmatch(r"000088-[0-9a-f]{8}", current):
        raise SystemExit("S04-0002 final generation pointer mismatch")
    if evidence_ids(sealed) != [f"E{index:04d}" for index in range(1, 96)]:
        raise SystemExit("final seal did not append exactly E0095")
    if sealed["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
        raise SystemExit("E0095 does not match the closeout hash seal")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("final seal did not preserve every prior generation")
    return {
        "artifact_hashes": hashes,
        "completion_ready": False,
        "evidence_id": FINAL_EVIDENCE_ID,
        "generation": generation,
        "mode": "final",
        "parent_generation": parent,
        "state_verification": verify_generation_store(10),
        "status": "active",
    }


def run_verify() -> dict[str, Any]:
    report_present = (ATTEMPT / "report.json").is_file()
    evidence.verify_evidence(require_closeout=report_present)
    ralph_root, generation, payloads = current_state()
    generations = numbered_generations(ralph_root)
    if generations[: len(PRESERVED_GENERATIONS)] != PRESERVED_GENERATIONS:
        raise SystemExit("S04-0002 verification lost a preserved generation")
    latest = evidence_ids(payloads)[-1]
    expected_count = {"E0093": 8, CORE_EVIDENCE_ID: 9, FINAL_EVIDENCE_ID: 10}.get(
        latest
    )
    if expected_count is None or len(generations) != expected_count:
        raise SystemExit("unexpected S04-0002 RAH seal state")
    return {
        "completion_ready": False,
        "evidence": "PASS",
        "generation": generation,
        "latest_evidence_id": latest,
        "mode": "verify",
        "state_verification": verify_generation_store(expected_count),
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
