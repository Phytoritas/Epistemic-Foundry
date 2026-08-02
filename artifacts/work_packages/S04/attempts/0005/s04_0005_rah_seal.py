#!/usr/bin/env python3
"""Append the S04-SG001 decision and S04-0005 PASS evidence to RAH.

The transition is append-only: generation 93 remains immutable, activation
appends E0096, core verification appends E0097, and final byte closeout appends
E0098.  The wider implementation gate remains fail and completion_ready stays
false because the authorized downstream sequence is not complete.
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
ATTEMPT = ROOT / "artifacts/work_packages/S04/attempts/0005"
AUTOMATION = ROOT / ".rah/helpers/recursive-architecture-refactoring-auto/automation"
ATTEMPT_ID = "S04-0005"
DECISION_ID = "HD-EF4-S04-SG001-20260731-001"
DECISION_HASH = "sha256:38d81158c4e7bedf56eaa24f2199e43e9bc41ef511dd900fb3ff8a3c78c5054c"
PATCH_PLAN_HASH = "sha256:b67f63b0dd1c50869f4ce40f25b25cbec89348ac826c6271071ed3d4222122f3"
EXPECTED_PARENT = "000093-1b501864"
EXPECTED_PARENT_EVIDENCE = "E0095"
ACTIVATION_EVIDENCE_ID = "E0096"
CORE_EVIDENCE_ID = "E0097"
FINAL_EVIDENCE_ID = "E0098"
sys.path.insert(0, str(ATTEMPT))
sys.path.insert(0, str(AUTOMATION))

import build_s04_0005_evidence as evidence  # noqa: E402
import ralph_harness as rh  # noqa: E402
import state_store  # noqa: E402


OBJECTIVE = (
    "Implement the complete Epistemic Foundry v4.0.0 specification under "
    "product-owner decisions including HD-EF4-S04-SG001-20260731-001. "
    "Preserve S04-0004 as immutable SPEC_GAP history and preserve every prior "
    "attempt, HumanDecision, RAH evidence and generation, report, review, "
    "receipt, command record, and the dirty worktree. In the primary session "
    "without Fleet or subagents, seal S04-0005 PASS, then execute serially "
    "C01-0009, C02-0004, B04-0009, O02-0002, C04-0004, and the next-unused "
    "final B04 packaging attempt; recompute the 156-package DAG and continue "
    "the next dependency-ready package. Keep completion_ready false until "
    "every objective, source-coverage, PRD, review, validation, and closeout "
    "gate actually passes."
)
NEXT_ACTIONS = [
    "Execute C01-0009 revalidation under the current active development-manifest binding.",
    "Start C02-0004 only after C01-0009 PASS, then B04-0009 only after C02-0004 PASS.",
    "Keep the exact 17 B04-0009 projection debts visible and completion_ready=false.",
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
        raise SystemExit("RAH current pointer and verified generation disagree")
    return ralph_root, generation, payloads


def evidence_ids(payloads: dict[str, Any]) -> list[str]:
    ledger = payloads.get("evidence_ledger.json")
    if not isinstance(ledger, dict) or not isinstance(ledger.get("entries"), list):
        raise SystemExit("invalid RAH evidence ledger")
    identifiers = [
        str(row.get("id")) for row in ledger["entries"] if isinstance(row, dict)
    ]
    if any(re.fullmatch(r"E\d{4,}", value) is None for value in identifiers):
        raise SystemExit("malformed RAH evidence identifier")
    expected = [f"E{index:04d}" for index in range(1, len(identifiers) + 1)]
    if identifiers != expected:
        raise SystemExit("RAH evidence ledger is not contiguous")
    observed = max((int(value[1:]) for value in identifiers), default=0)
    if int(ledger.get("issued_id_high_water", 0)) != observed:
        raise SystemExit("RAH evidence high-water does not match entries")
    return identifiers


def next_evidence_id(payloads: dict[str, Any]) -> str:
    identifiers = evidence_ids(payloads)
    return f"E{int(identifiers[-1][1:]) + 1:04d}"


def generation_number(generation: str) -> int:
    if re.fullmatch(r"\d{6}-[0-9a-f]{8}", generation) is None:
        raise SystemExit(f"malformed RAH generation: {generation}")
    return int(generation.split("-", 1)[0])


def artifact_hashes(names: tuple[str, ...]) -> dict[str, str]:
    result: dict[str, str] = {}
    for name in names:
        path = ATTEMPT / name
        if not path.is_file():
            raise SystemExit(f"required S04-0005 artifact missing: {name}")
        result[name] = sha256(path)
    return result


def activation_summary() -> str:
    return (
        f"S04-SG001 resolved_by {DECISION_ID} ({DECISION_HASH}); immutable "
        f"patch plan MP-EF4-S04-SG001-20260731-001 ({PATCH_PLAN_HASH}) and "
        "active binding DMB-EF4-20260731-003 prospectively authorize S04-0005. "
        "The binding supersedes revision 002, binds current development manifest "
        "sha256:6ccf07571c34c9010a10605ba201ba698a09f6343a281565520d392e4c77e063, "
        "and preserves S04-0004 SPEC_GAP, all prior artifacts, evidence, "
        "generations, and the dirty worktree. C01-0009 remains waiting until "
        "S04-0005 PASS; implementation_gate=fail and completion_ready=false."
    )


def core_summary() -> str:
    names = (
        "active-source-binding-verification.json",
        "full-regression-impact.json",
        "preexisting-debt-reconciliation.json",
        "write-scope-verification.json",
        "junit-normalization-verification.json",
        "dependency-status.json",
        "targeted-security-suite.junit.xml",
        "full-node-suite.junit.xml",
        "full-python-suite.junit.xml",
        "review.md",
        "build_s04_0005_evidence.py",
        "s04_0005_rah_seal.py",
    )
    hashes = artifact_hashes(names)
    return (
        "S04-0005 PASS core verification: active binding revision 003, its "
        "12 live manifest replacement hashes, two authorizing HumanDecisions, "
        "superseded evidence, reconciliation lineage, self-hashes, and tamper "
        "rejection all pass. Direct TM004 is 4/4, targeted security 67/67, and "
        "full Node 819/819. Full Python is 1056 passed with exactly 17 "
        "fingerprint-matched B04-0009 projection debts and zero S04 causal or "
        "new failures. "
        + "; ".join(f"{name}=sha256:{digest}" for name, digest in hashes.items())
        + ". Review is primary-session separate with actor_independence=false. "
        "The repository is not fully green; implementation_gate=fail and "
        "completion_ready=false."
    )


def final_summary(parent: str) -> tuple[str, dict[str, str]]:
    names = (
        "report.json",
        "commands.jsonl",
        "review.md",
        "active-source-binding-verification.json",
        "full-regression-impact.json",
        "preexisting-debt-reconciliation.json",
        "write-scope-verification.json",
        "junit-normalization-verification.json",
        "dependency-status.json",
        "targeted-security-suite.junit.xml",
        "full-node-suite.junit.xml",
        "full-python-suite.junit.xml",
        "rah-core-integrity.json",
        "build_s04_0005_evidence.py",
        "s04_0005_rah_seal.py",
    )
    hashes = artifact_hashes(names)
    summary = (
        f"S04-0005 PASS closeout is hash-sealed after core generation {parent}: "
        + "; ".join(f"{name}=sha256:{digest}" for name, digest in hashes.items())
        + ". S04-TM004 is resolved, S04 has zero owned residual failures, and "
        "C01-0009 is dependency-ready. Every prior attempt and generation "
        "remains preserved. The exact 17 B04-0009 projection debts and all later "
        "ordered gates remain, so implementation_gate=fail and "
        "completion_ready=false."
    )
    return summary, hashes


def commit_active_failed_generation(
    *,
    payloads: dict[str, Any],
    kind: str,
    summary: str,
    expected_evidence_id: str,
    update_objective: bool,
) -> str:
    now = rh.utc_now()
    goal = copy.deepcopy(payloads["goal.json"])
    loop = copy.deepcopy(payloads["loop_state.json"])
    ledger = copy.deepcopy(payloads["evidence_ledger.json"])
    identifier = rh.add_evidence_entry(
        ledger,
        now=now,
        goal_id=goal["goal_id"],
        iteration=int(loop.get("current_iteration") or loop.get("iteration") or 1),
        kind=kind,
        summary=summary,
    )
    if identifier != expected_evidence_id:
        raise SystemExit(f"unexpected evidence ID {identifier}; expected {expected_evidence_id}")
    if update_objective:
        goal["goal"] = OBJECTIVE
        loop["goal"] = OBJECTIVE
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
            "intake", "plan", "act", "verify", "review", "decide", "done",
            "blocked", "cancelled", "failed",
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
        SimpleNamespace(goal_status="active", goal_objective=str(goal["goal"])),
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
        "S04-SG001 is resolved and S04-0005 is evidence-sealed PASS. C01-0009 "
        "is next; the B04-0009 projection debt and later conformance/package "
        "gates remain, so implementation_gate=fail and completion_ready=false."
    )
    status["implementation_gate"] = "fail"
    status["implementation_gate_note"] = note
    status["next_recommended_action"] = NEXT_ACTIONS[0]
    prior_gate_ids = gates.get("implementation_gate", {}).get("evidence_ids", [])
    gates["implementation_gate"] = {
        "evidence_ids": list(dict.fromkeys([*prior_gate_ids, identifier])),
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
    if (
        flat_stamps != 6
        or flat_matches != 6
        or loop.get("status") != "active"
        or loop.get("implementation_gate") != "fail"
        or loop.get("completion_readiness", {}).get("ready") is not False
    ):
        raise SystemExit("RAH state is not active/fail with six matching flat projections")
    identifiers = evidence_ids(payloads)
    return {
        "attempt_id": ATTEMPT_ID,
        "status": "PASS",
        "mode": "READ_ONLY",
        "current_generation": current,
        "latest_evidence_id": identifiers[-1],
        "evidence_count": len(identifiers),
        "retained_generation_count": len(generations),
        "generation_file_hashes_verified": checked,
        "generation_manifest_sha256": "sha256:" + sha256(
            ralph_root / "generations" / current / "generation-manifest.json"
        ),
        "flat_snapshot_stamps_verified": flat_stamps,
        "flat_snapshot_content_matches": flat_matches,
        "ralph_status": "active",
        "implementation_gate": "fail",
        "completion_ready": False,
        "parse_errors": {},
    }


def assert_blocked_parent(generation: str, payloads: dict[str, Any]) -> None:
    loop = payloads["loop_state.json"]
    if generation != EXPECTED_PARENT or evidence_ids(payloads)[-1] != EXPECTED_PARENT_EVIDENCE:
        raise SystemExit("S04-0005 activation parent is not generation 93 / E0095")
    if (
        loop.get("status") != "blocked"
        or "S04-SG001" not in str(loop.get("blocked_reason"))
        or loop.get("implementation_gate") != "fail"
        or loop.get("completion_readiness", {}).get("ready") is not False
    ):
        raise SystemExit("activation requires the retained S04-SG001 blocked state")


def assert_active(payloads: dict[str, Any]) -> None:
    loop = payloads["loop_state.json"]
    if (
        loop.get("status") != "active"
        or loop.get("blocked_reason") is not None
        or loop.get("implementation_gate") != "fail"
        or loop.get("completion_readiness", {}).get("ready") is not False
    ):
        raise SystemExit("S04-0005 seal requires active/fail/completion_ready=false")


def run_preflight() -> dict[str, Any]:
    evidence.verify()
    ralph_root, generation, payloads = current_state()
    assert_blocked_parent(generation, payloads)
    report = read_json(ATTEMPT / "report.json")
    if "rah_state" in report:
        raise SystemExit("S04-0005 report is already RAH-bound")
    generations = numbered_generations(ralph_root)
    if len(generations) != 93 or generations[-1] != generation:
        raise SystemExit("preflight requires exactly 93 preserved generations")
    return {
        "mode": "preflight",
        "status": "PASS",
        "generation": generation,
        "latest_evidence_id": EXPECTED_PARENT_EVIDENCE,
        "next_evidence_id": ACTIVATION_EVIDENCE_ID,
        "retained_generation_count": len(generations),
        "completion_ready": False,
    }


def run_activate() -> dict[str, Any]:
    preflight = run_preflight()
    ralph_root, parent, payloads = current_state()
    before = numbered_generations(ralph_root)
    prior_ids = evidence_ids(payloads)
    summary = activation_summary()
    generation = commit_active_failed_generation(
        payloads=payloads,
        kind="decision",
        summary=summary,
        expected_evidence_id=ACTIVATION_EVIDENCE_ID,
        update_objective=True,
    )
    _, current, sealed = current_state()
    if current != generation or generation_number(current) != generation_number(parent) + 1:
        raise SystemExit("activation generation pointer mismatch")
    if evidence_ids(sealed) != [*prior_ids, ACTIVATION_EVIDENCE_ID]:
        raise SystemExit("activation did not append exactly E0096")
    if sealed["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
        raise SystemExit("activation evidence summary mismatch")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or len(after) != 94:
        raise SystemExit("activation did not preserve all 93 prior generations")
    return {
        "mode": "activate",
        "status": "active",
        "parent_generation": parent,
        "generation": generation,
        "evidence_id": ACTIVATION_EVIDENCE_ID,
        "preflight": preflight,
        "state_verification": verify_generation_store(94),
        "completion_ready": False,
    }


def run_core() -> dict[str, Any]:
    evidence.verify()
    ralph_root, parent, payloads = current_state()
    assert_active(payloads)
    if (
        generation_number(parent) != 94
        or evidence_ids(payloads)[-1] != ACTIVATION_EVIDENCE_ID
        or payloads["evidence_ledger.json"]["entries"][-1].get("summary")
        != activation_summary()
    ):
        raise SystemExit("core requires the exact S04-SG001 activation generation")
    before = numbered_generations(ralph_root)
    prior_ids = evidence_ids(payloads)
    summary = core_summary()
    generation = commit_active_failed_generation(
        payloads=payloads,
        kind="evidence",
        summary=summary,
        expected_evidence_id=CORE_EVIDENCE_ID,
        update_objective=False,
    )
    _, current, sealed = current_state()
    if current != generation or generation_number(current) != generation_number(parent) + 1:
        raise SystemExit("core generation pointer mismatch")
    if evidence_ids(sealed) != [*prior_ids, CORE_EVIDENCE_ID]:
        raise SystemExit("core did not append exactly E0097")
    if sealed["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
        raise SystemExit("core evidence summary mismatch")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or len(after) != 95:
        raise SystemExit("core did not preserve all prior generations")
    integrity = verify_generation_store(95)
    write_json(ATTEMPT / "rah-core-integrity.json", integrity)
    evidence.bind_rah_state(
        activation_generation=parent,
        activation_evidence_id=ACTIVATION_EVIDENCE_ID,
        core_generation=generation,
        core_evidence_id=CORE_EVIDENCE_ID,
        final_closeout_evidence_id=FINAL_EVIDENCE_ID,
    )
    evidence.verify()
    return {
        "mode": "core",
        "status": "active",
        "parent_generation": parent,
        "generation": generation,
        "evidence_id": CORE_EVIDENCE_ID,
        "final_closeout_evidence_id": FINAL_EVIDENCE_ID,
        "state_verification": integrity,
        "completion_ready": False,
    }


def run_final() -> dict[str, Any]:
    evidence.verify()
    ralph_root, parent, payloads = current_state()
    assert_active(payloads)
    report = read_json(ATTEMPT / "report.json")
    rah_state = report.get("rah_state")
    if not isinstance(rah_state, dict) or rah_state.get("core_generation") != parent:
        raise SystemExit("S04-0005 report does not bind current core generation")
    if (
        rah_state.get("activation_evidence_id") != ACTIVATION_EVIDENCE_ID
        or rah_state.get("core_evidence_id") != CORE_EVIDENCE_ID
        or rah_state.get("final_closeout_evidence_id") != FINAL_EVIDENCE_ID
        or evidence_ids(payloads)[-1] != CORE_EVIDENCE_ID
        or next_evidence_id(payloads) != FINAL_EVIDENCE_ID
    ):
        raise SystemExit("S04-0005 report and live ledger evidence IDs disagree")
    if payloads["evidence_ledger.json"]["entries"][-1].get("summary") != core_summary():
        raise SystemExit("stored S04-0005 core summary changed before final seal")
    before = numbered_generations(ralph_root)
    prior_ids = evidence_ids(payloads)
    summary, hashes = final_summary(parent)
    generation = commit_active_failed_generation(
        payloads=payloads,
        kind="evidence",
        summary=summary,
        expected_evidence_id=FINAL_EVIDENCE_ID,
        update_objective=False,
    )
    _, current, sealed = current_state()
    if current != generation or generation_number(current) != generation_number(parent) + 1:
        raise SystemExit("final generation pointer mismatch")
    if evidence_ids(sealed) != [*prior_ids, FINAL_EVIDENCE_ID]:
        raise SystemExit("final did not append exactly E0098")
    if sealed["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
        raise SystemExit("final closeout summary mismatch")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or len(after) != 96:
        raise SystemExit("final did not preserve all prior generations")
    verification = verify_generation_store(96)
    return {
        "mode": "final",
        "status": "active",
        "parent_generation": parent,
        "generation": generation,
        "evidence_id": FINAL_EVIDENCE_ID,
        "artifact_hashes": hashes,
        "state_verification": verification,
        "completion_ready": False,
    }


def run_verify() -> dict[str, Any]:
    evidence.verify()
    _, generation, payloads = current_state()
    assert_active(payloads)
    if generation_number(generation) != 96:
        raise SystemExit("S04-0005 final generation must be number 96")
    identifiers = evidence_ids(payloads)
    if identifiers[-3:] != [ACTIVATION_EVIDENCE_ID, CORE_EVIDENCE_ID, FINAL_EVIDENCE_ID]:
        raise SystemExit("sealed ledger does not end with S04 activation/core/final evidence")
    report = read_json(ATTEMPT / "report.json")
    rah_state = report.get("rah_state")
    if not isinstance(rah_state, dict):
        raise SystemExit("S04-0005 report lacks RAH binding")
    core_generation = str(rah_state.get("core_generation"))
    if generation_number(generation) != generation_number(core_generation) + 1:
        raise SystemExit("final generation does not directly follow core generation")
    summary, hashes = final_summary(core_generation)
    if payloads["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
        raise SystemExit("stored final evidence differs from current closeout bytes")
    return {
        "mode": "verify",
        "status": "PASS",
        "generation": generation,
        "latest_evidence_id": FINAL_EVIDENCE_ID,
        "artifact_hashes": hashes,
        "state_verification": verify_generation_store(96),
        "completion_ready": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("preflight", "activate", "core", "final", "verify"))
    args = parser.parse_args()
    result = {
        "preflight": run_preflight,
        "activate": run_activate,
        "core": run_core,
        "final": run_final,
        "verify": run_verify,
    }[args.mode]()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
