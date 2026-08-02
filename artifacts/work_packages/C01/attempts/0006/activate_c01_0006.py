#!/usr/bin/env python3
"""Activate C01-0006 after the C01-SG004 product-owner decision.

This transition is deliberately fail-closed.  It accepts only the exact
sealed C01-0005 RAH state, verifies the bounded manifest correction and its
authority artifacts, appends one decision evidence record, preserves every
retained generation, and keeps the global implementation and completion gates
unsatisfied while C01-0006 is implemented.
"""

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


EXPECTED_PARENT = "000090-a3e0bace"
EXPECTED_GENERATION_COUNT = 12
EXPECTED_EVIDENCE_ID = "E0099"
DECISION_ID = "HD-EF4-C01-SG004-20260730-001"
DECISION_HASH = "sha256:ebc3434cccdd248b38a36d1a3de5132f4503b4172c1ee11a64dd8f0033f670fd"
DECISION_FILE_SHA256 = "febccd44dce2639c434e9d328655493defb072b2d988138f432b1ad586fb447a"
PATCH_PLAN_HASH = "sha256:3006cc81b9cc451c20c469394c1e0b715bd33e328ae9045c043bb8f73621268a"
PATCH_PLAN_FILE_SHA256 = "5de2c378c02658569187a4f0b3484f097288f898e7a1327f014033fcfd496d64"
BINDING_HASH = "sha256:25466595ff8dcb255b1b7e171ef5b4222f47fa35a42d5c8a28d60fa2126fc6a1"
BINDING_FILE_SHA256 = "d349ccd666570e454a16a09ef542776f5a82fdf2e939548ff68ef68b2cb500b6"
MANIFEST_SHA256 = "8859303ea2fbe8d71655b2c244daf424a9742d4ce700bb93edddc20e3a06f23b"
C01_0005_REPORT_SHA256 = "27574974c492381618f3000b2c03c4f98a8cac00111757adac3a1f5df8bb065f"
C01_0005_GAP_SHA256 = "f60dcbe5a0c643e412c522fde57221c345dfdd051967c8ce9c014c352d72c35c"
OBJECTIVE = (
    "Continue Epistemic Foundry v4.0.0 under product-owner decision "
    f"{DECISION_ID}. Preserve C01-0001 through C01-0005 as immutable history "
    "and preserve every prior attempt, HumanDecision, RAH evidence and retained "
    "generation, report, review, command record, and the dirty worktree. In the "
    "primary session without Fleet or subagents, execute serially: C01-0006; "
    "C02-0002 generated projections; C03-0002 compatibility migration; a "
    "pre-C04 B04-0006 deterministic canonical projection and receipt; C04-0002 "
    "full conformance; final B04-0007 packaging; then recompute the 156-package "
    "DAG and continue the next dependency-ready package. Keep the global "
    "implementation gate failed or pending repair and completion_ready false "
    "until objective evidence satisfies the full external goal."
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
        raise SystemExit("invalid evidence ledger")
    return [str(row.get("id")) for row in ledger["entries"] if isinstance(row, dict)]


def verify_authority_and_history() -> None:
    decision_path = ROOT / f"artifacts/authority_decisions/{DECISION_ID}.human-decision.json"
    patch_plan_path = ROOT / (
        "artifacts/authority_decisions/"
        "HD-EF4-C01-SG004-20260730-001.manifest-patch-plan.json"
    )
    binding_path = ROOT / (
        "artifacts/authority_decisions/"
        "HD-EF4-C01-SG004-20260730-001.manifest-reconciliation-binding.json"
    )
    checks = {
        decision_path: DECISION_FILE_SHA256,
        patch_plan_path: PATCH_PLAN_FILE_SHA256,
        binding_path: BINDING_FILE_SHA256,
        ROOT / "manifests/development_manifest.yaml": MANIFEST_SHA256,
        ROOT / "artifacts/work_packages/C01/attempts/0005/report.json": (
            C01_0005_REPORT_SHA256
        ),
        ROOT
        / "artifacts/work_packages/C01/attempts/0005/"
        "c01-shared-contract-gap-verification.json": C01_0005_GAP_SHA256,
    }
    for path, expected in checks.items():
        if sha256(path) != expected:
            raise SystemExit(f"sealed artifact hash mismatch: {path}")

    decision = read_json(decision_path)
    if canonical_self_hash(decision, "decision_hash") != DECISION_HASH:
        raise SystemExit("HumanDecision canonical hash mismatch")
    if decision.get("decision_id") != DECISION_ID or decision.get("subject_id") != "C01-SG004":
        raise SystemExit("HumanDecision identity mismatch")

    patch_plan = read_json(patch_plan_path)
    if canonical_self_hash(patch_plan, "patch_plan_hash") != PATCH_PLAN_HASH:
        raise SystemExit("manifest patch-plan canonical hash mismatch")
    if patch_plan.get("successor_sha256") != MANIFEST_SHA256:
        raise SystemExit("manifest patch-plan does not bind the current manifest")
    if patch_plan.get("static_dependency_changes") != []:
        raise SystemExit("C01-SG004 must not introduce a static dependency cycle")

    binding = read_json(binding_path)
    if canonical_self_hash(binding, "binding_hash") != BINDING_HASH:
        raise SystemExit("reconciliation binding canonical hash mismatch")
    if binding.get("active_source_binding") is not False:
        raise SystemExit("attempt-level reconciliation must not replace active authority")
    if binding.get("successor_sha256") != MANIFEST_SHA256:
        raise SystemExit("reconciliation binding does not bind the current manifest")


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
    verify_store(ralph_root, EXPECTED_GENERATION_COUNT, EXPECTED_PARENT)
    if evidence_ids(payloads) != [f"E{index:04d}" for index in range(1, 99)]:
        raise SystemExit("activation requires preserved E0001-E0098")
    ledger_before = payloads["evidence_ledger.json"]
    if ledger_before.get("issued_id_high_water") != 98:
        raise SystemExit("activation requires evidence high-water E0098")
    loop_before = payloads["loop_state.json"]
    if (
        loop_before.get("status") != "blocked"
        or "C01-SG004" not in str(loop_before.get("blocked_reason"))
        or loop_before.get("completion_readiness", {}).get("ready") is not False
        or loop_before.get("implementation_gate") != "fail"
    ):
        raise SystemExit("activation requires the exact blocked C01-SG004 state")

    now = rh.utc_now()
    goal = copy.deepcopy(payloads["goal.json"])
    loop = copy.deepcopy(loop_before)
    ledger = copy.deepcopy(ledger_before)
    evidence_id = rh.add_evidence_entry(
        ledger,
        now=now,
        goal_id=goal["goal_id"],
        iteration=int(loop.get("current_iteration") or 1),
        kind="decision",
        summary=(
            f"C01-SG004 resolved_by {DECISION_ID} ({DECISION_HASH}); the "
            "decision authorizes C01-0006 and fixes 126 canonical schemas, "
            "126 matching examples, DocumentRegistrationRequest and "
            "DocumentRegistration authority, exact bounded oracle corrections, "
            "C01/C02/C03 ordering, pre-C04 B04 projection reconciliation with "
            "a matching receipt, C04 full conformance, and a distinct final B04 "
            "packaging gate. C01-0001 through C01-0005, E0001-E0098, every "
            "retained generation, and the dirty worktree remain immutable; "
            "Fleet/subagents remain forbidden, the global implementation gate "
            "remains failed pending repair, and completion_ready=false."
        ),
    )
    if evidence_id != EXPECTED_EVIDENCE_ID:
        raise SystemExit(f"unexpected evidence ID: {evidence_id}")

    goal.update({"goal": OBJECTIVE, "status": "active", "updated_at_utc": now})
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
            "next_actions": [
                "Execute C01-0006 within the exact canonical-contract and oracle write scope.",
                "Pass C01 before C02, C02 before C03, and all three before pre-C04 B04 projection reconciliation.",
                "Keep the global implementation gate failed and completion_ready false until the full ordered objective is verified.",
            ],
        }
    )
    readiness = loop.get("completion_readiness")
    if not isinstance(readiness, dict) or readiness.get("ready") is not False:
        raise SystemExit("completion readiness must remain false")
    readiness["evidence_count"] = len(ledger["entries"])
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
        "used_evidence": [evidence_id, "E0096", "E0097", "E0098"],
        "missing_evidence_ids": [],
        "missing_acceptance_ids": [],
        "missing_validation_ids": [],
        "missing_closeout_ids": [],
    }

    plan = rh.build_plan_graph(goal, loop, payloads["plan_graph.json"], now)
    for node in plan.get("nodes", []):
        if node.get("id") == "N3":
            node["status"] = "active"
        elif node.get("status") == "active":
            node["status"] = "pending"
    plan["active_node"] = "N3"
    bridge = rh.build_goal_bridge(
        ROOT,
        goal,
        loop,
        payloads["goal_bridge.json"],
        SimpleNamespace(goal_status="active", goal_objective=OBJECTIVE),
        now,
    )
    review = copy.deepcopy(payloads["review_gate.json"])
    review.update({"status": "not_requested", "attempts": [], "updated_at_utc": now})

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
        f"{DECISION_ID} resolves C01-SG004 and authorizes C01-0006, but the "
        "ordered C01/C02/C03/B04/C04/B04 repair objective remains pending; "
        "completion_ready remains false."
    )
    gates["implementation_gate"] = {
        "status": "fail",
        "note": (
            "C01-0006 is active within the exact product-owner boundary; the "
            "global implementation gate remains unsatisfied pending verified repair."
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
        raise SystemExit("latest evidence is not E0099")
    if current_after[1]["loop_state.json"].get("implementation_gate") != "fail":
        raise SystemExit("global implementation gate was incorrectly promoted")
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
