#!/usr/bin/env python3
"""Recover and finish the C01-0008 RAH seal without rewriting generation 86.

The original core invocation durably committed E0086/E0087 and the exact
C01-SG005 blocker in generation 000086, then its post-commit assertion failed
because the RAH harness retained the previously-authorized implementation gate
as ``pass``.  This script preserves that committed generation, records the
recovery as E0088 while changing the gate to ``fail``, binds the report to the
recovered core generation, and appends the final artifact hash seal as E0089.
"""

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
ATTEMPT = ROOT / "artifacts/work_packages/C01/attempts/0008"
AUTOMATION = ROOT / ".rah/helpers/recursive-architecture-refactoring-auto/automation"
sys.path.insert(0, str(ATTEMPT))
sys.path.insert(0, str(AUTOMATION))

import build_c01_0008_evidence as evidence  # noqa: E402
import c01_0008_rah_seal as original  # noqa: E402
import ralph_harness as rh  # noqa: E402
import state_store  # noqa: E402


INITIAL_CORE_GENERATION = "000086-e7895494"
RECOVERY_EVIDENCE_ID = "E0088"
FINAL_EVIDENCE_ID = "E0089"
RECOVERY_ARTIFACT = ATTEMPT / "rah-seal-recovery.json"
NEXT_ACTIONS = [
    "Obtain a product-owner HumanDecision resolving C01-SG005 with exact J02-0004 and S04-0004 correction authority.",
    "Do not start C02-0004 or any later ordered attempt until J02-0004, S04-0004, and C01-0009 all PASS.",
    "Preserve C01-0008, every prior generation, and the dirty worktree; keep completion_ready=false.",
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
        raise SystemExit("RAH evidence ledger contains a malformed evidence ID")
    return identifiers


def expected_ids(high_water: int) -> list[str]:
    return [f"E{index:04d}" for index in range(1, high_water + 1)]


def recovery_summary() -> str:
    manifest = (
        ROOT
        / ".rah/ralph/generations"
        / INITIAL_CORE_GENERATION
        / "generation-manifest.json"
    )
    return (
        "C01-0008 append-only RAH seal recovery: generation "
        f"{INITIAL_CORE_GENERATION} already durably records exact contract audit "
        "E0086, documented gap E0087, blocked goal/loop state, exact C01-SG005 "
        "reason, and completion_ready=false. The original core command returned "
        "1 only because its post-commit assertion expected implementation_gate=fail "
        "while the harness retained the prior bounded O02 authorization as pass. "
        "No committed generation is rewritten. This recovery prospectively sets "
        "implementation_gate=fail while preserving the blocker and every prior "
        f"generation. Initial core manifest sha256:{sha256(manifest)}; original "
        f"sealer sha256:{sha256(ATTEMPT / 'c01_0008_rah_seal.py')}; "
        "completion_ready=false."
    )


def final_summary(core_generation: str) -> tuple[str, dict[str, str]]:
    names = (
        "report.json",
        "commands.jsonl",
        "review.md",
        "canonical-contract-verification.json",
        "retrieval-candidate-verification.json",
        "full-regression-impact.json",
        "write-scope-verification.json",
        "phase-artifact-reconciliation.json",
        "dependency-status.json",
        "junit-normalization-verification.json",
        "targeted-contracts.junit.xml",
        "full-python-suite.junit.xml",
        "full-node-suite.junit.xml",
        "rah-core-integrity.json",
        "rah-seal-recovery.json",
        "build_c01_0008_evidence.py",
        "c01_0008_rah_seal.py",
        "c01_0008_rah_recover.py",
    )
    hashes: dict[str, str] = {}
    for name in names:
        path = ATTEMPT / name
        if not path.is_file():
            raise SystemExit(f"required C01-0008 artifact is missing: {name}")
        hashes[name] = sha256(path)
    summary = (
        f"C01-0008 SPEC_GAP closeout is append-only hash-sealed after recovered "
        f"core generation {core_generation}: report sha256:{hashes['report.json']}; "
        f"commands sha256:{hashes['commands.jsonl']}; review sha256:"
        f"{hashes['review.md']}; contract sha256:"
        f"{hashes['canonical-contract-verification.json']}; candidate sha256:"
        f"{hashes['retrieval-candidate-verification.json']}; regression sha256:"
        f"{hashes['full-regression-impact.json']}; scope sha256:"
        f"{hashes['write-scope-verification.json']}; phase sha256:"
        f"{hashes['phase-artifact-reconciliation.json']}; dependency sha256:"
        f"{hashes['dependency-status.json']}; normalization sha256:"
        f"{hashes['junit-normalization-verification.json']}; targeted JUnit sha256:"
        f"{hashes['targeted-contracts.junit.xml']}; Python JUnit sha256:"
        f"{hashes['full-python-suite.junit.xml']}; Node JUnit sha256:"
        f"{hashes['full-node-suite.junit.xml']}; RAH core integrity sha256:"
        f"{hashes['rah-core-integrity.json']}; recovery receipt sha256:"
        f"{hashes['rah-seal-recovery.json']}; builder sha256:"
        f"{hashes['build_c01_0008_evidence.py']}; original sealer sha256:"
        f"{hashes['c01_0008_rah_seal.py']}; recovery sealer sha256:"
        f"{hashes['c01_0008_rah_recover.py']}. C01-0008 remains immutable SPEC_GAP "
        "C01-SG005 with implementation VERIFIED and contract CONFORMANT. All 86 "
        "pre-recovery generations, prior attempts, and dirty-worktree content are "
        "preserved. C02-0004 and later attempts remain waiting; "
        "implementation_gate=fail and completion_ready=false."
    )
    return summary, hashes


def blocked_payloads(
    payloads: dict[str, Any], *, summary: str, expected_evidence_id: str
) -> dict[str, Any]:
    now = rh.utc_now()
    goal = copy.deepcopy(payloads["goal.json"])
    loop = copy.deepcopy(payloads["loop_state.json"])
    ledger = copy.deepcopy(payloads["evidence_ledger.json"])
    identifier = rh.add_evidence_entry(
        ledger,
        now=now,
        goal_id=str(goal["goal_id"]),
        iteration=int(loop.get("current_iteration") or 1),
        kind="evidence",
        summary=summary,
    )
    if identifier != expected_evidence_id:
        raise SystemExit(
            f"unexpected recovery evidence ID {identifier}; expected {expected_evidence_id}"
        )
    goal.update({"status": "blocked", "updated_at_utc": now})
    loop.update(
        {
            "blocked_reason": original.BLOCK_REASON,
            "checkpoint_required": False,
            "current_stage": "ralph-blocked",
            "done": False,
            "generated_at_utc": now,
            "harness_phase": "blocked",
            "implementation_gate": "fail",
            "loop_phase": "bounded-implementation",
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
        "allowed_next_states": [],
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
    previous_used = loop.get("progress_update", {}).get("used_evidence", [])
    loop["progress_update"] = {
        "created_evidence": [identifier],
        "missing_acceptance_ids": [],
        "missing_closeout_ids": [],
        "missing_evidence_ids": [],
        "missing_validation_ids": [],
        "used_evidence": list(
            dict.fromkeys([*previous_used, *evidence_ids(payloads), identifier])
        ),
    }
    plan = rh.build_plan_graph(goal, loop, payloads["plan_graph.json"], now)
    bridge = rh.build_goal_bridge(
        ROOT,
        goal,
        loop,
        payloads["goal_bridge.json"],
        SimpleNamespace(goal_status="blocked", goal_objective=str(goal["goal"])),
        now,
    )
    review = copy.deepcopy(payloads["review_gate.json"])
    review["updated_at_utc"] = now
    return {
        "evidence_ledger.json": ledger,
        "goal.json": goal,
        "goal_bridge.json": bridge,
        "loop_state.json": loop,
        "plan_graph.json": plan,
        "review_gate.json": review,
    }


def sync_sidecars(
    *, generation: str, payloads: dict[str, Any], evidence_ids_to_add: list[str]
) -> None:
    now = rh.utc_now()
    status_path = ROOT / ".rah/state/status.json"
    gates_path = ROOT / ".rah/state/gates.json"
    status = read_json(status_path)
    gates = read_json(gates_path)
    note = (
        "C01-0008 is SPEC_GAP C01-SG005. Its contract implementation is VERIFIED, "
        "but J02-0004 and S04-0004 require a new product-owner HumanDecision; "
        "C02-0004 and later attempts remain waiting and completion_ready=false."
    )
    status["implementation_gate"] = "fail"
    status["implementation_gate_note"] = note
    status["next_recommended_action"] = NEXT_ACTIONS[0]
    existing_ids = gates.get("implementation_gate", {}).get("evidence_ids", [])
    gates["implementation_gate"] = {
        "evidence_ids": list(dict.fromkeys([*existing_ids, *evidence_ids_to_add])),
        "note": note,
        "status": "fail",
    }
    rh.write_json(status_path, status)
    rh.write_json(gates_path, gates)
    goal = payloads["goal.json"]
    loop = payloads["loop_state.json"]
    rh.refresh_status_for_ralph(ROOT, ROOT / ".rah", goal, loop, now)
    rh.upsert_current_loop(
        ROOT / ".rah/plans/current_loop.md", rh.render_managed_current_loop(goal, loop)
    )
    rh.write_text(
        ROOT / ".rah/ralph/blockers.md", rh.render_blockers(goal, loop, now)
    )
    pointer = read_json(ROOT / ".rah/ralph/current.json")
    if pointer.get("generation") != generation:
        raise SystemExit("sidecar refresh changed the RAH generation pointer")


def verify_generation_store(
    *, expected_count: int, expected_latest: str
) -> dict[str, Any]:
    ralph_root, current, payloads = current_state()
    generations = numbered_generations(ralph_root)
    if len(generations) != expected_count or generations[-1] != current:
        raise SystemExit(
            f"expected {expected_count} retained generations ending at {current}, "
            f"found {len(generations)}"
        )
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
    goal = payloads["goal.json"]
    identifiers = evidence_ids(payloads)
    if (
        flat_stamps != 6
        or flat_matches != 6
        or loop.get("status") != "blocked"
        or goal.get("status") != "blocked"
        or loop.get("blocked_reason") != original.BLOCK_REASON
        or loop.get("implementation_gate") != "fail"
        or loop.get("completion_readiness", {}).get("ready") is not False
        or identifiers != expected_ids(int(expected_latest.removeprefix("E")))
    ):
        raise SystemExit("recovered C01-0008 RAH state is inconsistent")
    status = read_json(ROOT / ".rah/state/status.json")
    gates = read_json(ROOT / ".rah/state/gates.json")
    if (
        status.get("implementation_gate") != "fail"
        or gates.get("implementation_gate", {}).get("status") != "fail"
    ):
        raise SystemExit("RAH sidecar implementation gate is not fail-closed")
    return {
        "attempt_id": "C01-0008",
        "completion_ready": False,
        "current_generation": current,
        "evidence_count": len(identifiers),
        "flat_snapshot_content_matches": flat_matches,
        "flat_snapshot_stamps_verified": flat_stamps,
        "generation_file_hashes_verified": checked,
        "generation_manifest_sha256": "sha256:"
        + sha256(ralph_root / "generations" / current / "generation-manifest.json"),
        "implementation_gate": "fail",
        "latest_evidence_id": identifiers[-1],
        "ralph_goal_status": goal.get("status"),
        "ralph_status": loop.get("status"),
        "retained_generation_count": len(generations),
        "retained_generations": generations,
        "spec_gap_id": original.SPEC_GAP_ID,
        "status": "PASS",
        "work_package_id": "C01",
    }


def recover() -> dict[str, Any]:
    evidence.verify()
    ralph_root, parent, payloads = current_state()
    if parent != INITIAL_CORE_GENERATION:
        raise SystemExit(
            f"unexpected recovery parent {parent}; expected {INITIAL_CORE_GENERATION}"
        )
    if len(numbered_generations(ralph_root)) != 86:
        raise SystemExit("C01-0008 recovery requires all 86 prior generations")
    if evidence_ids(payloads) != expected_ids(87):
        raise SystemExit("C01-0008 recovery requires preserved E0001-E0087")
    entries = payloads["evidence_ledger.json"]["entries"]
    loop = payloads["loop_state.json"]
    goal = payloads["goal.json"]
    if (
        entries[-2].get("summary") != original.audit_summary()
        or entries[-1].get("summary") != original.gap_summary()
        or loop.get("status") != "blocked"
        or goal.get("status") != "blocked"
        or loop.get("blocked_reason") != original.BLOCK_REASON
        or loop.get("implementation_gate") != "pass"
        or loop.get("completion_readiness", {}).get("ready") is not False
    ):
        raise SystemExit("generation 86 is not the exact recoverable C01-0008 state")
    state_store.KEEP_GENERATIONS = 10_000
    generation = state_store.commit_generation(
        ralph_root,
        blocked_payloads(
            payloads,
            summary=recovery_summary(),
            expected_evidence_id=RECOVERY_EVIDENCE_ID,
        ),
    )
    if not re.fullmatch(r"000087-[0-9a-f]{8}", generation):
        raise SystemExit(f"unexpected C01-0008 recovery generation: {generation}")
    _, _, recovered = current_state()
    sync_sidecars(
        generation=generation,
        payloads=recovered,
        evidence_ids_to_add=["E0086", "E0087", RECOVERY_EVIDENCE_ID],
    )
    integrity = verify_generation_store(
        expected_count=87, expected_latest=RECOVERY_EVIDENCE_ID
    )
    write_json(ATTEMPT / "rah-core-integrity.json", integrity)
    evidence.bind_rah_state(
        core_generation=generation,
        contract_audit_evidence_id="E0086",
        documented_gap_evidence_id="E0087",
        final_closeout_evidence_id=FINAL_EVIDENCE_ID,
    )
    report = read_json(ATTEMPT / "report.json")
    rah_state = report["rah_state"]
    rah_state.update(
        {
            "gate_recovery_evidence_id": RECOVERY_EVIDENCE_ID,
            "gate_recovery_generation": generation,
            "initial_block_generation": INITIAL_CORE_GENERATION,
        }
    )
    write_json(ATTEMPT / "report.json", report)
    recovery_artifact = {
        "attempt_id": "C01-0008",
        "cause": "POST_COMMIT_IMPLEMENTATION_GATE_EXPECTATION_MISMATCH",
        "completion_ready": False,
        "failed_core_command_exit_code": 1,
        "failed_core_command_message": "C01-0008 blocked RAH state is inconsistent",
        "final_evidence_id_reserved": FINAL_EVIDENCE_ID,
        "initial_block_generation": INITIAL_CORE_GENERATION,
        "initial_generation_manifest_sha256": "sha256:"
        + sha256(
            ralph_root
            / "generations"
            / INITIAL_CORE_GENERATION
            / "generation-manifest.json"
        ),
        "initial_implementation_gate": "pass",
        "prior_generations_rewritten": 0,
        "recovered_implementation_gate": "fail",
        "recovery_evidence_id": RECOVERY_EVIDENCE_ID,
        "recovery_generation": generation,
        "recovery_generation_manifest_sha256": integrity[
            "generation_manifest_sha256"
        ],
        "spec_gap_id": original.SPEC_GAP_ID,
        "status": "PASS_APPEND_ONLY_RECOVERY",
    }
    write_json(RECOVERY_ARTIFACT, recovery_artifact)
    evidence.verify()
    return {
        "completion_ready": False,
        "generation": generation,
        "mode": "recover",
        "parent_generation": parent,
        "recovery_evidence_id": RECOVERY_EVIDENCE_ID,
        "state_verification": integrity,
        "status": "blocked",
    }


def final() -> dict[str, Any]:
    evidence.verify()
    ralph_root, parent, payloads = current_state()
    if not re.fullmatch(r"000087-[0-9a-f]{8}", parent):
        raise SystemExit(f"unexpected C01-0008 final parent: {parent}")
    if evidence_ids(payloads) != expected_ids(88):
        raise SystemExit("C01-0008 final requires preserved E0001-E0088")
    if payloads["evidence_ledger.json"]["entries"][-1].get(
        "summary"
    ) != recovery_summary():
        raise SystemExit("E0088 is not the exact append-only recovery evidence")
    report = read_json(ATTEMPT / "report.json")
    rah_state = report.get("rah_state")
    if (
        not isinstance(rah_state, dict)
        or rah_state.get("core_generation") != parent
        or rah_state.get("gate_recovery_evidence_id") != RECOVERY_EVIDENCE_ID
        or rah_state.get("final_closeout_evidence_id") != FINAL_EVIDENCE_ID
    ):
        raise SystemExit("C01-0008 report does not bind the recovered core")
    summary, hashes = final_summary(parent)
    state_store.KEEP_GENERATIONS = 10_000
    generation = state_store.commit_generation(
        ralph_root,
        blocked_payloads(
            payloads,
            summary=summary,
            expected_evidence_id=FINAL_EVIDENCE_ID,
        ),
    )
    if not re.fullmatch(r"000088-[0-9a-f]{8}", generation):
        raise SystemExit(f"unexpected C01-0008 final generation: {generation}")
    _, _, sealed = current_state()
    sync_sidecars(
        generation=generation,
        payloads=sealed,
        evidence_ids_to_add=[FINAL_EVIDENCE_ID],
    )
    verification = verify_generation_store(
        expected_count=88, expected_latest=FINAL_EVIDENCE_ID
    )
    if sealed["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
        raise SystemExit("E0089 does not match the C01-0008 closeout hash seal")
    return {
        "artifact_hashes": hashes,
        "completion_ready": False,
        "evidence_id": FINAL_EVIDENCE_ID,
        "generation": generation,
        "mode": "final",
        "parent_generation": parent,
        "state_verification": verification,
        "status": "blocked",
    }


def verify() -> dict[str, Any]:
    generations = numbered_generations(ROOT / ".rah/ralph")
    if len(generations) == 86:
        _, generation, payloads = current_state()
        if (
            generation != INITIAL_CORE_GENERATION
            or evidence_ids(payloads) != expected_ids(87)
        ):
            raise SystemExit("generation 86 is not ready for C01-0008 recovery")
        return {
            "completion_ready": False,
            "generation": generation,
            "latest_evidence_id": "E0087",
            "mode": "recovery-required",
            "status": "PASS_RECOVERABLE",
        }
    if len(generations) == 87:
        result = evidence.verify()
        integrity = verify_generation_store(
            expected_count=87, expected_latest=RECOVERY_EVIDENCE_ID
        )
        if not RECOVERY_ARTIFACT.is_file():
            raise SystemExit("C01-0008 recovery receipt is missing")
        return {**result, "mode": "recovery-verify", "state_verification": integrity}
    if len(generations) != 88:
        raise SystemExit(f"unexpected C01-0008 generation count: {len(generations)}")
    result = evidence.verify()
    integrity = verify_generation_store(
        expected_count=88, expected_latest=FINAL_EVIDENCE_ID
    )
    report = read_json(ATTEMPT / "report.json")
    parent = str(report["rah_state"]["core_generation"])
    summary, hashes = final_summary(parent)
    _, _, payloads = current_state()
    if payloads["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
        raise SystemExit("stored E0089 differs from current C01-0008 artifact hashes")
    return {
        **result,
        "artifact_hashes": hashes,
        "mode": "final-verify",
        "state_verification": integrity,
        "status": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("recover", "final", "verify"))
    args = parser.parse_args()
    result = {"recover": recover, "final": final, "verify": verify}[args.mode]()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
