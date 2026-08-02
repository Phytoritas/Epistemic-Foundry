#!/usr/bin/env python3
"""Activate the bounded O02-SG001 resolving sequence without rewriting history."""

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


EXPECTED_PARENT = "000084-a48e395d"
EXPECTED_PARENT_MANIFEST_SHA256 = (
    "728c23f5c22e11ee2be247b300cc83a8113b5f3c0b945ee28cc9a3dfbd9da54a"
)
EXPECTED_GENERATION_COUNT = 84
EXPECTED_EVIDENCE_ID = "E0085"
DECISION_ID = "HD-EF4-O02-SG001-20260731-001"
DECISION_HASH = "sha256:3695c59b67788b0f144f033627a9ef3294b75418f78dfb15fcebccc14a8ef221"
DECISION_FILE_SHA256 = (
    "5e986212a409db12121d15ab936998d15478037fa06bcb8c0b2480292b4b29fe"
)
O02_0001_HASHES = {
    "report.json": "2aee2cd75ef0b9be3e9218ca3aa719811b2990cc987dbf863207950ca5dc7feb",
    "shared-contract-gap-verification.json": (
        "87bc834f5ce4007d322865837b7ebfe37227ba965153fd16f87e1e1807f13b50"
    ),
    "dependency-status.json": (
        "0a78b1ca310fc33b55aeecba1b47ba796cbe16dd8edaf9f170e70bab50069434"
    ),
    "review.md": "84d84896d893af52606943ad3e6bd5a9fe6ff9e233bfcf9577370738263609bf",
    "commands.jsonl": "2a10519dac032ee1a69b9d231bafeabd23a545eb2b45f86eb6d5959a614e9ac3",
    "rah-core-integrity.json": (
        "e8cf46d70f4b0fedff7d99a24146fa753d9a3ff764b71333353f6feea0b9b5e4"
    ),
}
APPROVAL_DOCUMENT_SHA256 = (
    "42ce69cccab50419082f33670060c42b41f2d4c0b4f53aed2a21fbb84d9f94c9"
)
OBJECTIVE = (
    "Implement the complete Epistemic Foundry v4.0.0 specification from "
    "MASTER_EXECUTION_PROMPT.md and MASTER_SPEC.md under product-owner decision "
    f"{DECISION_ID}. Preserve O02-0001 as immutable SPEC_GAP history and "
    "preserve every prior attempt, HumanDecision, RAH evidence and generation, "
    "report, review, receipt, command record, and the dirty worktree. In the "
    "primary session without Fleet or subagents, execute serially C01-0008 "
    "canonical RetrievalCandidate migration to 127 schemas and 127 examples, "
    "C02-0004 generated projection, B04-0009 pre-O02 projection to 128 canonical "
    "resources, O02-0002 retrieval implementation and exact acceptance oracles, "
    "C04-0004 full conformance, and the next-unused final B04 packaging attempt; "
    "then recompute the 156-package DAG and continue the next dependency-ready "
    "package. Treat source coverage and the source-bound PRD as mandatory "
    "completion gates and keep completion_ready false until every objective gate "
    "is actually satisfied."
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


def verify_decision_and_history() -> None:
    decision_path = (
        ROOT / f"artifacts/authority_decisions/{DECISION_ID}.human-decision.json"
    )
    if not decision_path.is_file() or sha256(decision_path) != DECISION_FILE_SHA256:
        raise SystemExit("HumanDecision file hash mismatch")
    decision = read_json(decision_path)
    asserted = decision.pop("decision_hash", None)
    canonical = json.dumps(
        decision, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    computed = "sha256:" + hashlib.sha256(canonical).hexdigest()
    if asserted != DECISION_HASH or computed != DECISION_HASH:
        raise SystemExit("HumanDecision canonical hash mismatch")
    if (
        decision.get("decision_id") != DECISION_ID
        or decision.get("subject_id") != "O02-SG001"
        or decision.get("decision_type") != "correct"
        or decision.get("authority_role") != "product_owner"
        or decision.get("non_mutation_acknowledgement") is not True
    ):
        raise SystemExit("HumanDecision identity or authority mismatch")

    attempt = ROOT / "artifacts/work_packages/O02/attempts/0001"
    for name, expected in O02_0001_HASHES.items():
        if sha256(attempt / name) != expected:
            raise SystemExit(f"O02-0001 immutable artifact hash mismatch: {name}")
    approval_document = ROOT / "O02-SG001_무엇을_승인해야_하는가.md"
    if sha256(approval_document) != APPROVAL_DOCUMENT_SHA256:
        raise SystemExit("O02-SG001 approval document hash mismatch")


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
                key: value for key, value in authority.items() if key != "state_generation"
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
    verify_decision_and_history()
    ralph_root = ROOT / ".rah/ralph"
    current = state_store.read_current(ralph_root)
    if current is None:
        raise SystemExit("no committed RAH generation")
    parent, payloads = current
    if parent != EXPECTED_PARENT:
        raise SystemExit(f"unexpected parent generation: {parent}")
    parent_manifest = ralph_root / "generations" / parent / "generation-manifest.json"
    if sha256(parent_manifest) != EXPECTED_PARENT_MANIFEST_SHA256:
        raise SystemExit("O02 parent generation manifest hash mismatch")
    verify_store(ralph_root, EXPECTED_GENERATION_COUNT, EXPECTED_PARENT)
    if evidence_ids(payloads) != [f"E{index:04d}" for index in range(1, 85)]:
        raise SystemExit("activation requires preserved E0001-E0084")
    ledger_before = payloads["evidence_ledger.json"]
    if ledger_before.get("issued_id_high_water") != 84:
        raise SystemExit("activation requires evidence high-water E0084")
    loop_before = payloads["loop_state.json"]
    if (
        loop_before.get("status") != "blocked"
        or "O02-SG001" not in str(loop_before.get("blocked_reason"))
        or loop_before.get("completion_readiness", {}).get("ready") is not False
    ):
        raise SystemExit("activation requires the exact blocked O02-SG001 state")

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
            f"O02-SG001 resolved_by {DECISION_ID} ({DECISION_HASH}), which "
            "prospectively authorizes the bounded C01-0008 -> C02-0004 -> "
            "B04-0009 -> O02-0002 -> C04-0004 -> next-unused B04 sequence. "
            "It freezes strict RetrievalCandidate identity and provenance, "
            "provider-neutral request binding, lane/query-family mapping, six "
            "relation directions, exact dedupe and RRF(k=60) ordering, immutable "
            "snapshot integrity and typed failure semantics, the non-vector-only "
            "guard, O01/O02/O03 authority boundaries, and exact network-free "
            "quality thresholds. O02-0001 and E0084 remain immutable; all 84 "
            "prior generations and evidence, reports, and the dirty worktree are "
            "preserved. Fleet/subagents remain forbidden and completion_ready=false."
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
            "implementation_gate": "pass",
            "current_stage": "ralph-active",
            "harness_phase": "execution",
            "blocked_reason": None,
            "checkpoint_required": False,
            "mark_done_rejected": False,
            "source_coverage": source_coverage,
            "prd_projection": prd_projection,
            "completion_readiness": completion_readiness,
            "next_actions": [
                "Apply only the exact O02-SG001 HumanDecision manifest correction.",
                "Execute C01-0008, C02-0004, B04-0009, O02-0002, C04-0004, and final B04 serially, stopping after any non-PASS result.",
                "Preserve source/PRD gates and keep completion_ready false while downstream packages remain.",
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
        "used_evidence": [evidence_id, "E0083", "E0084"],
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
    status["implementation_gate"] = "pass"
    status["implementation_gate_note"] = (
        f"{DECISION_ID} authorizes only the bounded O02 resolving sequence. "
        "Mandatory source/PRD coverage and downstream packages remain incomplete; "
        "completion_ready remains false."
    )
    gates["implementation_gate"] = {
        "status": "pass",
        "note": (
            "The O02-SG001 resolving sequence is active within its exact product-owner "
            "contract; this bounded authorization is not global completion."
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
        raise SystemExit("latest evidence is not E0085")
    live_goal = current_after[1]["goal.json"]
    live_loop = current_after[1]["loop_state.json"]
    if (
        live_goal.get("source_coverage_required") is not True
        or live_goal.get("prd_required") is not True
    ):
        raise SystemExit("mandatory source/PRD flags were not persisted")
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
                "implementation_gate": loop["implementation_gate"],
                "source_coverage_required": True,
                "source_coverage_total_rows": source_coverage["total_rows"],
                "source_coverage_incomplete_rows": len(
                    source_coverage.get("missing_ids", [])
                ),
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
