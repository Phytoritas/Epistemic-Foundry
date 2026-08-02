#!/usr/bin/env python3
"""Activate the bounded C01-SG005 correction sequence without rewriting history."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any


ROOT = Path(__file__).resolve().parents[5]
AUTOMATION = ROOT / ".rah/helpers/recursive-architecture-refactoring-auto/automation"
sys.dont_write_bytecode = True
sys.path.insert(0, str(AUTOMATION))

import ralph_harness as rh  # noqa: E402
import state_store  # noqa: E402


EXPECTED_PARENT = "000088-768298c8"
EXPECTED_PARENT_MANIFEST_SHA256 = (
    "6798961795ccbdfc41084183cebf4ae53b22dd2c344747a5ea314e854c87e0da"
)
EXPECTED_GENERATION_COUNT = 88
EXPECTED_EVIDENCE_ID = "E0090"
DECISION_ID = "HD-EF4-C01-SG005-20260731-001"
DECISION_HASH = "sha256:b833da71edfd31f8a41da371baad9aa75775d527ded2617b9a0b41d2353e028b"
DECISION_FILE_SHA256 = (
    "c7faa17fab992b701749c7fc492b2aa7d03442cfa6e065d58f154c79c50113ab"
)
APPROVAL_DOCUMENT_SHA256 = (
    "c90851ced019e2f0e65dd652ff222ce91562641caa153fbcac7cb38212b3221f"
)
C01_0008_HASHES = {
    "report.json": "bdbb3760c5799f8835bbe7becb87c8a3ab7c3252ebfb8734266d3106613d7a36",
    "full-regression-impact.json": (
        "5ef986b23928fd8abd70d701fc4546e333e0e152df45fbc866957af7f2c144f3"
    ),
    "review.md": "3fe501fcf9da1094b3eee7fe5eb2a56f3a455255765ac19617ca5f70a31d5c61",
    "rah-core-integrity.json": (
        "42d9141295b667caf2e76ba9073d7ae422da390e7df8bb88a68a3b39e9d98597"
    ),
    "rah-seal-recovery.json": (
        "09eea3e15ad0be39caf65d00e8437266aeff4b0fbcd26140436b4142e2a3060e"
    ),
}
OBJECTIVE = (
    "Implement the complete Epistemic Foundry v4.0.0 specification from "
    "MASTER_EXECUTION_PROMPT.md and MASTER_SPEC.md under product-owner decision "
    f"{DECISION_ID}. Preserve C01-0008 as immutable SPEC_GAP history and preserve "
    "every prior attempt, HumanDecision, RAH evidence and generation, report, "
    "review, receipt, command record, and the dirty worktree. In the primary "
    "session without Fleet or subagents, execute serially J02-0004 authority "
    "inventory correction, S04-0004 development-manifest binding correction, "
    "C01-0009 revalidation, C02-0004 generated projection, B04-0009 canonical "
    "projection, O02-0002 retrieval implementation, C04-0004 full conformance, "
    "and the next-unused final B04 packaging attempt; then recompute the "
    "156-package DAG and continue the next dependency-ready package. Stop after "
    "any non-PASS result and keep completion_ready false until every objective "
    "gate, source-coverage requirement, and source-bound PRD requirement passes."
)


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


def canonical_self_hash(payload: dict[str, Any], field: str) -> str:
    preimage = copy.deepcopy(payload)
    asserted = preimage.pop(field, None)
    canonical = json.dumps(
        preimage, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    computed = "sha256:" + hashlib.sha256(canonical).hexdigest()
    if asserted != computed:
        raise SystemExit(f"canonical self-hash mismatch for {field}")
    return computed


def generation_names(ralph_root: Path) -> list[str]:
    return sorted(
        path.name
        for path in (ralph_root / "generations").iterdir()
        if path.is_dir() and re.fullmatch(r"\d{6}-[0-9a-f]{8}", path.name)
    )


def evidence_ids(payloads: dict[str, Any]) -> list[str]:
    ledger = payloads.get("evidence_ledger.json")
    if not isinstance(ledger, dict) or not isinstance(ledger.get("entries"), list):
        raise SystemExit("invalid RAH evidence ledger")
    return [str(row.get("id")) for row in ledger["entries"] if isinstance(row, dict)]


def verify_authority_and_history() -> None:
    decision_path = (
        ROOT / f"artifacts/authority_decisions/{DECISION_ID}.human-decision.json"
    )
    if not decision_path.is_file() or sha256(decision_path) != DECISION_FILE_SHA256:
        raise SystemExit("HumanDecision file hash mismatch")
    decision = read_json(decision_path)
    if canonical_self_hash(decision, "decision_hash") != DECISION_HASH:
        raise SystemExit("HumanDecision canonical hash mismatch")
    if (
        decision.get("decision_id") != DECISION_ID
        or decision.get("subject_id") != "C01-SG005"
        or decision.get("decision_type") != "correct"
        or decision.get("authority_role") != "product_owner"
        or decision.get("non_mutation_acknowledgement") is not True
    ):
        raise SystemExit("HumanDecision identity or authority mismatch")

    approval = ROOT / "C01-SG005_무엇을_승인해야_하는가.md"
    if sha256(approval) != APPROVAL_DOCUMENT_SHA256:
        raise SystemExit("C01-SG005 approval document hash mismatch")
    attempt = ROOT / "artifacts/work_packages/C01/attempts/0008"
    for name, expected in C01_0008_HASHES.items():
        if sha256(attempt / name) != expected:
            raise SystemExit(f"C01-0008 immutable artifact hash mismatch: {name}")


def verify_store(
    ralph_root: Path, expected_count: int, expected_current: str
) -> dict[str, Any]:
    current = state_store.read_current(ralph_root)
    if current is None or current[0] != expected_current:
        raise SystemExit("RAH current pointer mismatch")
    payloads = current[1]
    generations = generation_names(ralph_root)
    if len(generations) != expected_count or generations[-1] != expected_current:
        raise SystemExit("RAH generation preservation mismatch")

    verified_files = 0
    for generation in generations:
        directory = ralph_root / "generations" / generation
        manifest = read_json(directory / "generation-manifest.json")
        files = manifest.get("files")
        if manifest.get("generation") != generation or not isinstance(files, dict):
            raise SystemExit(f"invalid generation manifest: {generation}")
        if set(files) != set(state_store.GENERATION_FILES):
            raise SystemExit(f"generation file set mismatch: {generation}")
        for name in state_store.GENERATION_FILES:
            if sha256(directory / name) != files[name]:
                raise SystemExit(f"generation content hash mismatch: {generation}/{name}")
            verified_files += 1

    flat_stamps = 0
    flat_matches = 0
    for name in state_store.GENERATION_FILES:
        flat = read_json(ralph_root / name)
        if flat.get("state_generation") == expected_current:
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
        raise SystemExit("RAH flat snapshot verification mismatch")
    return {
        "generation": expected_current,
        "retained_generation_count": len(generations),
        "generation_file_hashes_verified": verified_files,
        "flat_snapshot_stamps_verified": flat_stamps,
        "flat_snapshot_content_matches": flat_matches,
    }


def main() -> int:
    verify_authority_and_history()
    ralph_root = ROOT / ".rah/ralph"
    current = state_store.read_current(ralph_root)
    if current is None:
        raise SystemExit("no committed RAH generation")
    parent, payloads = current
    if parent != EXPECTED_PARENT:
        raise SystemExit(f"unexpected parent generation: {parent}")
    parent_manifest = ralph_root / "generations" / parent / "generation-manifest.json"
    if sha256(parent_manifest) != EXPECTED_PARENT_MANIFEST_SHA256:
        raise SystemExit("C01-SG005 parent generation manifest hash mismatch")
    verify_store(ralph_root, EXPECTED_GENERATION_COUNT, EXPECTED_PARENT)
    if evidence_ids(payloads) != [f"E{index:04d}" for index in range(1, 90)]:
        raise SystemExit("activation requires preserved E0001-E0089")
    ledger_before = payloads["evidence_ledger.json"]
    if ledger_before.get("issued_id_high_water") != 89:
        raise SystemExit("activation requires evidence high-water E0089")
    loop_before = payloads["loop_state.json"]
    if (
        loop_before.get("status") != "blocked"
        or "C01-SG005" not in str(loop_before.get("blocked_reason"))
        or loop_before.get("implementation_gate") != "fail"
        or loop_before.get("completion_readiness", {}).get("ready") is not False
    ):
        raise SystemExit("activation requires the exact blocked C01-SG005 state")

    now = rh.utc_now()
    goal = copy.deepcopy(payloads["goal.json"])
    loop = copy.deepcopy(loop_before)
    ledger = copy.deepcopy(ledger_before)
    review = copy.deepcopy(payloads["review_gate.json"])
    evidence_id = rh.add_evidence_entry(
        ledger,
        now=now,
        goal_id=goal["goal_id"],
        iteration=int(loop.get("current_iteration") or 1),
        kind="decision",
        summary=(
            f"C01-SG005 resolved_by {DECISION_ID} ({DECISION_HASH}), which "
            "prospectively authorizes the exact serial J02-0004 -> S04-0004 -> "
            "C01-0009 -> C02-0004 -> B04-0009 -> O02-0002 -> C04-0004 -> "
            "next-unused B04 final packaging sequence. J02 owns only the current "
            "MASTER_SPEC authority-source rebinding and deterministic inventory "
            "self-hash; S04 owns only a new immutable current development-manifest "
            "binding revision with preserved lineage, authorizing decision, and "
            "self-hash. C01-0008 and E0089 remain immutable; every prior generation, "
            "report, review, receipt, command record, and dirty-worktree change is "
            "preserved. Fleet/subagents, schema weakening, and skip/xfail masking "
            "remain forbidden. implementation_gate=fail and completion_ready=false."
        ),
    )
    if evidence_id != EXPECTED_EVIDENCE_ID:
        raise SystemExit(f"unexpected evidence ID: {evidence_id}")

    goal.update(
        {
            "goal": OBJECTIVE,
            "status": "active",
            "source_coverage_required": True,
            "prd_required": True,
            "updated_at_utc": now,
        }
    )
    review.update({"status": "not_requested", "attempts": [], "updated_at_utc": now})
    review.pop("current_attempt", None)
    review.pop("review_snapshot", None)

    source_coverage = rh.assess_source_coverage(ROOT, required=True)
    prd_projection = rh.assess_prd_projection(
        ROOT, required=True, source_coverage=source_coverage
    )
    completion_readiness = rh.assess_completion_readiness(
        goal, ledger, review, source_coverage, prd_projection
    )
    if not (
        source_coverage.get("present") is True
        and source_coverage.get("required") is True
        and source_coverage.get("ready") is False
        and source_coverage.get("total_rows") == 509
        and not source_coverage.get("invalid_row_ids")
    ):
        raise SystemExit("unexpected mandatory source-coverage assessment")
    if not (
        prd_projection.get("present") is True
        and prd_projection.get("required") is True
        and prd_projection.get("audit_ready") is True
        and prd_projection.get("ready") is False
        and not prd_projection.get("unmapped_source_row_ids")
        and not prd_projection.get("unmapped_required_atom_ids")
    ):
        raise SystemExit("unexpected mandatory PRD assessment")
    if completion_readiness.get("ready") is not False:
        raise SystemExit("activation must not advance global completion")

    loop.update(
        {
            "generated_at_utc": now,
            "updated_at_utc": now,
            "goal": OBJECTIVE,
            "status": "active",
            "done": False,
            "loop_phase": "bounded-implementation",
            "implementation_gate": "fail",
            "current_stage": "ralph-active",
            "harness_phase": "execution",
            "blocked_reason": None,
            "checkpoint_required": False,
            "mark_done_rejected": False,
            "source_coverage": source_coverage,
            "prd_projection": prd_projection,
            "completion_readiness": completion_readiness,
            "next_actions": [
                "Execute J02-0004 only within its exact authority-inventory correction scope.",
                "After J02 PASS, execute S04-0004 and then C01-0009; stop after any non-PASS result.",
                "Preserve source/PRD gates and keep implementation_gate failed and completion_ready false while the ordered objective remains incomplete.",
            ],
        }
    )
    loop["state_machine"] = {
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
        "current_state": "act",
        "allowed_next_states": ["verify", "plan", "blocked", "failed"],
    }
    loop["stagnation"] = {
        "last_loop_phase": "bounded-implementation",
        "same_phase_without_evidence_count": 0,
        "pivot_required": False,
        "pivot_reason": None,
    }
    loop["progress_update"] = {
        "created_evidence": [evidence_id],
        "used_evidence": [evidence_id, "E0086", "E0087", "E0088", "E0089"],
        "missing_evidence_ids": [],
        "missing_acceptance_ids": [],
        "missing_validation_ids": [],
        "missing_closeout_ids": [],
    }

    plan = rh.build_plan_graph(goal, loop, payloads["plan_graph.json"], now)
    bridge = rh.build_goal_bridge(
        ROOT,
        goal,
        loop,
        payloads["goal_bridge.json"],
        SimpleNamespace(goal_status="active", goal_objective=OBJECTIVE),
        now,
    )

    state_store.KEEP_GENERATIONS = 10_000
    generation = state_store.commit_generation(
        ralph_root,
        {
            "goal.json": goal,
            "loop_state.json": loop,
            "evidence_ledger.json": ledger,
            "plan_graph.json": plan,
            "goal_bridge.json": bridge,
            "review_gate.json": review,
        },
    )

    status_path = ROOT / ".rah/state/status.json"
    gates_path = ROOT / ".rah/state/gates.json"
    status = read_json(status_path)
    gates = read_json(gates_path)
    status["implementation_gate"] = "fail"
    status["implementation_gate_note"] = (
        f"{DECISION_ID} resolves C01-SG005 and activates J02-0004, but the ordered "
        "J02/S04/C01/C02/B04/O02/C04/B04 repair objective remains incomplete; "
        "completion_ready remains false."
    )
    gates["implementation_gate"] = {
        "status": "fail",
        "note": (
            "J02-0004 is active within the exact product-owner boundary; the global "
            "implementation gate remains unsatisfied pending verified repair."
        ),
        "evidence_ids": [evidence_id],
    }
    rh.write_json(status_path, status)
    rh.write_json(gates_path, gates)
    rh.refresh_status_for_ralph(ROOT, ROOT / ".rah", goal, loop, now)
    rh.upsert_current_loop(
        ROOT / ".rah/plans/current_loop.md", rh.render_managed_current_loop(goal, loop)
    )
    rh.write_text(ralph_root / "blockers.md", rh.render_blockers(goal, loop, now))

    verified = state_store.verify_current(ralph_root)
    integrity = verify_store(ralph_root, EXPECTED_GENERATION_COUNT + 1, generation)
    current_after = state_store.read_current(ralph_root)
    if current_after is None or evidence_ids(current_after[1])[-1] != EXPECTED_EVIDENCE_ID:
        raise SystemExit("latest evidence is not E0090")
    live_loop = current_after[1]["loop_state.json"]
    if live_loop.get("implementation_gate") != "fail":
        raise SystemExit("global implementation gate was incorrectly promoted")
    if live_loop.get("completion_readiness", {}).get("ready") is not False:
        raise SystemExit("completion readiness was incorrectly promoted")
    print(
        json.dumps(
            {
                "parent_generation": parent,
                "generation": generation,
                "generation_store": verified,
                "integrity": integrity,
                "evidence_id": evidence_id,
                "evidence_high_water": ledger["issued_id_high_water"],
                "rah_status": loop["status"],
                "implementation_gate": "fail",
                "source_coverage_required": True,
                "source_coverage_total_rows": source_coverage["total_rows"],
                "prd_required": True,
                "prd_audit_ready": prd_projection["audit_ready"],
                "prd_ready": prd_projection["ready"],
                "completion_ready": False,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
