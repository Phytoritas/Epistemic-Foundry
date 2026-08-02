#!/usr/bin/env python3
"""Append B04-0004 PASS and closeout evidence without rewriting RAH history."""

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
ATTEMPT = ROOT / "artifacts/work_packages/B04/attempts/0004"
AUTOMATION = ROOT / ".rah/helpers/recursive-architecture-refactoring-auto/automation"
sys.path.insert(0, str(ATTEMPT))
sys.path.insert(0, str(AUTOMATION))

import build_b04_0004_evidence as evidence  # noqa: E402
import ralph_harness as rh  # noqa: E402
import state_store  # noqa: E402


CORE_PARENT = "000039-0913b42a"
CORE_EVIDENCE_ID = "E0042"
FINAL_EVIDENCE_ID = "E0043"
OBJECTIVE = (
    "Continue Epistemic Foundry v4.0.0 after B04-0004 canonical projection "
    "correction under HD-EF4-B04-MECH-CORRECTION-20260729-001. Preserve all "
    "prior B04/F01 attempts, decisions, RAH generations, reports, reviews, "
    "commands, and the dirty worktree. Keep completion_ready false. Start "
    "F01-0003 only after B04-0004 is evidence-sealed PASS, then revalidate "
    "the classifier, projection freshness, full Python suite, and the bounded "
    "pre-existing S04-TM004 Node debt. Start F02/F03 only after F01 PASS."
)
NEXT_ACTIONS = [
    "Start F01-0003 and update only its authorized exact required-check expectation for canonical_projection_freshness.",
    "Rerun F01 targeted classifier, monotonicity, projection freshness, full Python, and full Node reconciliation gates.",
    "After F01 PASS, recalculate the 156-package DAG and mark F02/F03 dependency-ready without adding an artificial edge.",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"cannot read JSON {path}: {error}")
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


def verify_generation_store(expected_count: int) -> dict[str, Any]:
    ralph_root, current, payloads = current_state()
    generations = numbered_generations(ralph_root)
    if len(generations) != expected_count or generations[-1] != current:
        raise SystemExit(
            f"expected {expected_count} retained generations ending at {current}, "
            f"found {len(generations)}"
        )
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
                key: value
                for key, value in authority.items()
                if key != "state_generation"
            }
        if state_store._dump(stripped) == state_store._dump(authority):
            flat_matches += 1
    if flat_stamps != 6 or flat_matches != 6:
        raise SystemExit(
            f"flat RAH projections mismatch: stamps={flat_stamps}, matches={flat_matches}"
        )
    loop = payloads["loop_state.json"]
    return {
        "completion_ready": loop.get("completion_readiness", {}).get("ready"),
        "current_generation": current,
        "flat_snapshot_content_matches": flat_matches,
        "flat_snapshot_stamps_verified": flat_stamps,
        "generation_file_hashes_verified": checked,
        "generation_manifest_sha256": sha256(
            ralph_root / "generations" / current / "generation-manifest.json"
        ),
        "latest_evidence_id": evidence_ids(payloads)[-1],
        "retained_generation_count": len(generations),
        "status": loop.get("status"),
    }


def core_summary() -> str:
    names = (
        "canonical-projection-verification.json",
        "source-inventory.json",
        "snapshot-inventory.json",
        "installed-wheel-verification.json",
        "full-regression-impact.json",
        "projection.artifact-receipt.json",
        "wheel.artifact-receipt.json",
        "sdist.artifact-receipt.json",
        "packaging-verification-run.json",
        "packaging-suite.junit.xml",
        "full-python-suite.junit.xml",
        "full-node-suite.junit.xml",
        "review.md",
    )
    hashes = {name: sha256(ATTEMPT / name) for name in names}
    return (
        "B04-0004 PASS: all six B04 projection-mechanism defects are resolved. "
        f"Root source bundle {evidence.SOURCE_BUNDLE_HASH}, projected snapshot "
        f"bundle {evidence.SNAPSHOT_BUNDLE_HASH}, and registry bytes "
        f"{evidence.REGISTRY_HASH} reconcile 124 schemas plus OpenAPI 3.1.1/33 "
        "operations with zero missing, extra, duplicate-ID, or mismatched "
        "resources. Atomic swap, rollback, pre/post-swap source mutation, "
        "registry binding tamper, missing/tampered resource, two clean builds, "
        "sdist-to-wheel equality, installed-wheel-only loading, arbitrary cwd, "
        "and zero source-fallback success all pass. Projection verification "
        f"sha256:{hashes['canonical-projection-verification.json']}; formal "
        f"packaging verification sha256:{hashes['packaging-verification-run.json']}; "
        f"projection receipt sha256:{hashes['projection.artifact-receipt.json']}; "
        f"packaging JUnit sha256:{hashes['packaging-suite.junit.xml']} records "
        "24 passed. Full Python records 946 passed plus one exact F01-owned "
        "expectation debt; full Node records 267 passed plus unchanged "
        "S04-TM004; B04-caused new failures and new skips/xfails are zero. "
        "Primary-session separate adversarial review has zero blocking findings "
        "and is not external actor-independent certification. B04-0003 and "
        "F01-0002 remain immutable; F01-0003 is next; completion_ready=false."
    )


def commit_active_generation(
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
        "used_evidence": [identifier, "E0041", "E0040", "E0039"],
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
        "B04-0004 is evidence-sealed PASS with a current canonical projection; "
        "F01-0003 is the next required attempt and completion_ready remains false."
    )
    status["implementation_gate"] = "pass"
    status["implementation_gate_note"] = note
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
    evidence.verify_evidence(require_closeout=False)
    ralph_root, generation, payloads = current_state()
    if generation != CORE_PARENT:
        raise SystemExit(f"unexpected B04-0004 core parent: {generation}")
    if evidence_ids(payloads) != [f"E{index:04d}" for index in range(1, 42)]:
        raise SystemExit("preflight requires preserved E0001-E0041")
    generations = numbered_generations(ralph_root)
    if len(generations) != 39 or generations[-1] != generation:
        raise SystemExit("preflight requires all 39 prior RAH generations")
    if payloads["loop_state.json"].get("status") != "active":
        raise SystemExit("preflight requires active RAH status")
    return {
        "completion_ready": False,
        "generation": generation,
        "latest_evidence_id": "E0041",
        "mode": "preflight",
        "retained_generation_count": len(generations),
    }


def run_core() -> dict[str, Any]:
    run_preflight()
    ralph_root, parent, payloads = current_state()
    before = numbered_generations(ralph_root)
    generation = commit_active_generation(
        payloads=payloads,
        summary=core_summary(),
        expected_evidence_id=CORE_EVIDENCE_ID,
    )
    _, current, sealed = current_state()
    if current != generation:
        raise SystemExit("core generation pointer mismatch")
    if evidence_ids(sealed) != [f"E{index:04d}" for index in range(1, 43)]:
        raise SystemExit("core seal did not append exactly E0042")
    if sealed["evidence_ledger.json"]["entries"][-1].get("summary") != core_summary():
        raise SystemExit("E0042 does not match the B04-0004 core summary")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("core seal did not preserve every prior generation")
    return {
        "completion_ready": False,
        "evidence_id": CORE_EVIDENCE_ID,
        "generation": generation,
        "mode": "core",
        "parent_generation": parent,
        "state_verification": verify_generation_store(40),
        "status": "active",
    }


def final_summary(parent: str) -> tuple[str, dict[str, str]]:
    names = (
        "report.json",
        "review.md",
        "commands.jsonl",
        "canonical-projection-verification.json",
        "source-inventory.json",
        "snapshot-inventory.json",
        "installed-wheel-verification.json",
        "full-regression-impact.json",
        "phase-artifact-reconciliation.json",
        "projection.artifact-receipt.json",
        "wheel.artifact-receipt.json",
        "sdist.artifact-receipt.json",
        "rah-core-integrity.json",
        "build_b04_0004_evidence.py",
        "b04-0004-rah-seal.py",
    )
    hashes = {name: sha256(ATTEMPT / name) for name in names}
    summary = (
        f"B04-0004 PASS closeout is hash-sealed after core generation {parent}: "
        f"report sha256:{hashes['report.json']}; review sha256:{hashes['review.md']}; "
        f"commands sha256:{hashes['commands.jsonl']}; projection verification "
        f"sha256:{hashes['canonical-projection-verification.json']}; projection "
        f"receipt sha256:{hashes['projection.artifact-receipt.json']}; phase "
        f"reconciliation sha256:{hashes['phase-artifact-reconciliation.json']}; "
        f"core RAH integrity sha256:{hashes['rah-core-integrity.json']}; builder "
        f"sha256:{hashes['build_b04_0004_evidence.py']}; sealer sha256:"
        f"{hashes['b04-0004-rah-seal.py']}. B04 is PASS_CURRENT_PROJECTION; "
        "B04-0003 and F01-0002 remain immutable; all prior RAH generations and "
        "dirty-worktree content are preserved; F01-0003 is next; F02/F03 remain "
        "waiting on F01; completion_ready=false."
    )
    return summary, hashes


def run_final() -> dict[str, Any]:
    evidence.verify_evidence(require_closeout=True)
    ralph_root, parent, payloads = current_state()
    if not re.fullmatch(r"000040-[0-9a-f]{8}", parent):
        raise SystemExit(f"unexpected B04-0004 final parent: {parent}")
    if evidence_ids(payloads) != [f"E{index:04d}" for index in range(1, 43)]:
        raise SystemExit("final seal requires preserved E0001-E0042")
    if payloads["evidence_ledger.json"]["entries"][-1].get("summary") != core_summary():
        raise SystemExit("E0042 changed before final sealing")
    report = read_json(ATTEMPT / "report.json")
    rah = report.get("rah_state")
    if not isinstance(rah, dict) or rah.get("core_generation") != parent:
        raise SystemExit("report does not bind the core RAH generation")
    if rah.get("core_evidence_id") != CORE_EVIDENCE_ID:
        raise SystemExit("report does not bind E0042")
    if rah.get("final_closeout_evidence_id") != FINAL_EVIDENCE_ID:
        raise SystemExit("report does not reserve E0043")
    summary, hashes = final_summary(parent)
    before = numbered_generations(ralph_root)
    generation = commit_active_generation(
        payloads=payloads,
        summary=summary,
        expected_evidence_id=FINAL_EVIDENCE_ID,
    )
    _, current, sealed = current_state()
    if current != generation:
        raise SystemExit("final generation pointer mismatch")
    if evidence_ids(sealed) != [f"E{index:04d}" for index in range(1, 44)]:
        raise SystemExit("final seal did not append exactly E0043")
    if sealed["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
        raise SystemExit("E0043 does not match the closeout hash seal")
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
        "state_verification": verify_generation_store(41),
        "status": "active",
    }


def run_verify() -> dict[str, Any]:
    closeout = (ATTEMPT / "report.json").is_file()
    evidence.verify_evidence(require_closeout=closeout)
    generations = numbered_generations(ROOT / ".rah/ralph")
    if len(generations) not in (39, 40, 41):
        raise SystemExit(f"unexpected retained generation count: {len(generations)}")
    return {
        "completion_ready": False,
        "evidence": "PASS",
        "mode": "verify",
        "state_verification": verify_generation_store(len(generations)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("preflight", "core", "final", "verify"))
    args = parser.parse_args()
    if args.mode == "preflight":
        result = run_preflight()
    elif args.mode == "core":
        result = run_core()
    elif args.mode == "final":
        result = run_final()
    else:
        result = run_verify()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
