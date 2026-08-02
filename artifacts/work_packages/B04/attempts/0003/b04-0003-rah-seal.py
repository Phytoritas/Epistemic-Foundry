#!/usr/bin/env python3
"""Seal B04-0003 FAIL evidence without rewriting prior RAH history."""

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
ATTEMPT = ROOT / "artifacts" / "work_packages" / "B04" / "attempts" / "0003"
AUTOMATION = (
    ROOT
    / ".rah"
    / "helpers"
    / "recursive-architecture-refactoring-auto"
    / "automation"
)
sys.path.insert(0, str(AUTOMATION))

import ralph_harness as rh  # noqa: E402
import state_store  # noqa: E402


CORE_PARENT = "000036-2428c22d"
CORE_EVIDENCE_ID = "E0039"
FINAL_EVIDENCE_ID = "E0040"
DECISION_ID = "HD-EF4-F01-SG002-20260729-001"
OBJECTIVE = (
    "Continue Epistemic Foundry v4.0.0 under product-owner decision "
    "HD-EF4-F01-SG002-20260729-001. Preserve F01-0002 SPEC_GAP, all prior "
    "B04 attempts, HumanDecisions, RAH evidence and generations, reports, "
    "reviews, commands, and the dirty worktree. In the primary session without "
    "Fleet or subagents, execute B04-0003 as the bounded canonical projection "
    "correction. Start F01-0003 only after verified B04 PASS; start F02 or F03 "
    "only after verified F01 PASS. Keep S04-TM004 separate and completion_ready "
    "false until the full external goal is actually complete."
)
BLOCK_REASON = (
    "B04-0003 is a verified implementation FAIL: the existing canonical "
    "projection mechanism violates six non-waivable requirements covering "
    "canonical-JSON source-bundle hashing, projected snapshot hashing, distinct "
    "source/package paths, projection-tool identity/version, atomic tree "
    "replacement, and SOURCE_CHANGED_DURING_PROJECTION fail-closed handling. "
    "The current correction decision makes the generator, packaging tests, and "
    "pyproject read-only for B04-0003, so repairing these known defects requires "
    "a new product-owner correction decision and a new B04 attempt. F01-0003, "
    "F02, and F03 remain unstarted; completion_ready=false."
)
NEXT_ACTIONS = [
    "Record a product-owner correction decision authorizing the exact canonical projection generator and related packaging-test paths for a new B04 attempt.",
    "Preserve B04-0003 as immutable FAIL history; do not relabel it or weaken projection, atomicity, packaging, or receipt gates.",
    "After a new B04 attempt produces a verified matching projection receipt and PASS, run F01-0003; keep F02/F03 waiting until F01 PASS.",
]

PRESERVED_HASHES = {
    "artifacts/authority_decisions/HD-EF4-F01-SG002-20260729-001.human-decision.json": "e3d8d2bd5844f71f286bfd02a3fac7a6997d8deebc37b4b378cf90ea134ee8ba",
    "manifests/development_manifest.yaml": "fb9656cce2fd4d0147571bc85726ebbbbb3f26a59ac644c5a12040007475d938",
    "schemas/epistemic-work-classification.schema.json": "dbe8437eae1ec8c956b1290556efa7f2bb89c862134870d80f15e6e49679efa9",
    "openapi/epistemic-foundry-v1.openapi.yaml": "c77aa89918cc33cded07755bbf2cbec7fcb6554e573efbca2ebd9480b78344d7",
    "src/epistemic_foundry/_canonical/canonical-registry.json": "6336a5254f8438c1acf063820ad115a8c911567de37531afe9b76ddd3151e57b",
    "src/epistemic_foundry/_canonical/schemas/epistemic-work-classification.schema.json": "5c0c574605f4d1d2e8ea42385d6bc40ac273d1cbf1319169f6e26db6656d6049",
    "scripts/build/canonical_registry/materialize.py": "14d10a98420384873e4200e6eabd860c5ecd1a7d18a2c095450c0e8628ab818a",
    "tests/packaging/test_canonical_registry.py": "04d7ea2cb5510d8c3206fa2f9ae51809defcfc355e0c94003e38b06d1dfae691",
    "pyproject.toml": "29d7a25d530884a4a2dff3d8ca2d9878717a43a4dc3c2710fc5317f533a7be44",
    "artifacts/work_packages/F01/attempts/0002/report.json": "1c010708ac32a0ea047746f45809055ebec5b0d78b2e92bc6969fe9fce6e28f5",
    "artifacts/work_packages/F01/attempts/0002/commands.jsonl": "984f8ecbbc14f7322dd5627c6e9da4da6515a8a9eb15a7b4a878940879cdbee6",
    "artifacts/work_packages/F01/attempts/0002/review.md": "ffbdec0bb552089bb6e77cb2bf6473d47e2e135d4b44d7ec655246c8ef42dcdd",
    "artifacts/work_packages/B04/attempts/0002/report.json": "a75e724b453bf58ce2745af174e96d7f08616bd09467e3b047b78f31b8add643",
    "artifacts/work_packages/B04/attempts/0002/commands.jsonl": "48486a34959da61a4a56a1a9410dcbf255634940440866de5aa5d4adbad4be98",
    "artifacts/work_packages/B04/attempts/0002/review.md": "d379140efd9ceea2f386fc06af62381434d64ea52deaa202847e241e266cab4d",
}

AUDIT_HASHES = {
    "audit_projection_mechanism.py": "df8869e2b99b9ebc9cd19cc556aa8f2d90a16390a5b6946b32be4e005713fba3",
    "source-inventory.json": "92b7d3d139ea9414025cca96b2554cadc298c7723cbb926708d2551386040d1c",
    "snapshot-inventory.json": "04e826e633f6478a6c3c1e25e46449539aae82c5599aefecf9dacbcf54beeeb2",
    "canonical-projection-verification.json": "6c57abbdc4b68df32f28451c31ff76e8310daf68172a554ec470baec35813b0a",
    "installed-wheel-verification.json": "10c1ac9fb4d1a207b148d55d7582bd3cece520b6038a4880cb98666536f62b4c",
}

DEFECT_CODES = [
    "B04-MECH001_SOURCE_BUNDLE_ALGORITHM_MISMATCH",
    "B04-MECH002_PROJECTED_SNAPSHOT_HASH_MISSING",
    "B04-MECH003_DISTINCT_SOURCE_PACKAGE_PATHS_MISSING",
    "B04-MECH004_PROJECTION_TOOL_IDENTITY_MISSING",
    "B04-MECH005_ATOMIC_TREE_REPLACEMENT_MISSING",
    "B04-MECH006_SOURCE_CHANGE_ERROR_MISSING",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"cannot read JSON evidence {path}: {error}")
    if not isinstance(payload, dict):
        raise SystemExit(f"JSON evidence is not an object: {path}")
    return payload


def read_commands() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    path = ATTEMPT / "commands.jsonl"
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as error:
            raise SystemExit(f"commands.jsonl line {number} is invalid: {error}")
        if not isinstance(row, dict):
            raise SystemExit(f"commands.jsonl line {number} is not an object")
        rows.append(row)
    identifiers = [row.get("command_id") for row in rows]
    if any(not isinstance(value, str) for value in identifiers):
        raise SystemExit("commands.jsonl contains a missing command ID")
    if len(identifiers) != len(set(identifiers)):
        raise SystemExit("commands.jsonl contains duplicate command IDs")
    return rows


def numbered_generations(ralph_root: Path) -> list[str]:
    return sorted(
        entry.name
        for entry in (ralph_root / "generations").iterdir()
        if entry.is_dir() and re.fullmatch(r"\d{6}-[0-9a-f]{8}", entry.name)
    )


def evidence_ids(payloads: dict[str, Any]) -> list[str]:
    ledger = payloads.get("evidence_ledger.json")
    if not isinstance(ledger, dict) or not isinstance(ledger.get("entries"), list):
        raise SystemExit("RAH evidence ledger is invalid")
    return [
        str(row.get("id"))
        for row in ledger["entries"]
        if isinstance(row, dict)
    ]


def current_state() -> tuple[Path, str, dict[str, Any]]:
    ralph_root = ROOT / ".rah" / "ralph"
    current = state_store.read_current(ralph_root)
    if current is None:
        raise SystemExit("no committed RAH generation")
    generation, payloads = current
    verified = state_store.verify_current(ralph_root)
    if verified.get("generation") != generation:
        raise SystemExit("RAH pointer and verified generation disagree")
    return ralph_root, generation, payloads


def assert_preserved_hashes() -> None:
    for relative, expected in PRESERVED_HASHES.items():
        actual = sha256(ROOT / relative)
        if actual != expected:
            raise SystemExit(
                f"preserved evidence hash mismatch for {relative}: {actual} != {expected}"
            )
    for name, expected in AUDIT_HASHES.items():
        actual = sha256(ATTEMPT / name)
        if actual != expected:
            raise SystemExit(
                f"B04-0003 audit hash mismatch for {name}: {actual} != {expected}"
            )


def assert_text_encoding() -> None:
    for path in sorted(candidate for candidate in ATTEMPT.iterdir() if candidate.is_file()):
        content = path.read_bytes()
        if content.startswith(b"\xef\xbb\xbf"):
            raise SystemExit(f"UTF-8 BOM is forbidden in B04-0003 evidence: {path.name}")
        if b"\x00" in content:
            raise SystemExit(f"NUL byte found in B04-0003 evidence: {path.name}")
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise SystemExit(f"B04-0003 evidence is not UTF-8: {path.name}: {error}")


def assert_attempt_evidence(*, require_closeout: bool) -> None:
    assert_text_encoding()
    assert_preserved_hashes()
    source = read_json(ATTEMPT / "source-inventory.json")
    snapshot = read_json(ATTEMPT / "snapshot-inventory.json")
    verification = read_json(ATTEMPT / "canonical-projection-verification.json")
    installed = read_json(ATTEMPT / "installed-wheel-verification.json")
    dependency = read_json(ATTEMPT / "dependency-status.json")
    if source.get("status") != "PASS" or source.get("schema_count") != 124:
        raise SystemExit("source inventory is not the expected 124-schema PASS")
    if source.get("source_file_count") != 125 or source.get("duplicate_schema_ids") != []:
        raise SystemExit("source inventory resource or duplicate-ID count is incorrect")
    if source.get("source_bundle_hash") != "sha256:47a8d63daadae502bc3fc91c19cebc1f8f04f885e24d6d409c444748e04fd340":
        raise SystemExit("source inventory hash changed")
    openapi = source.get("openapi")
    if not isinstance(openapi, dict) or openapi.get("version") != "3.1.1":
        raise SystemExit("OpenAPI version evidence is missing")
    if openapi.get("operation_count") != 33 or openapi.get("operation_ids_unique") is not True:
        raise SystemExit("OpenAPI operation evidence is not 33 unique operations")
    comparison = snapshot.get("comparison_to_source")
    if snapshot.get("status") != "STALE" or not isinstance(comparison, dict):
        raise SystemExit("snapshot inventory is not the expected STALE evidence")
    if comparison.get("missing_paths") != [] or comparison.get("extra_paths") != []:
        raise SystemExit("snapshot inventory has unexpected missing or extra paths")
    if comparison.get("hash_mismatches") != [
        "schemas/epistemic-work-classification.schema.json"
    ]:
        raise SystemExit("snapshot inventory does not bind the exact stale schema")
    if verification.get("final_status") != "FAIL":
        raise SystemExit("projection verification is not FAIL")
    defects = verification.get("implementation_defects")
    if not isinstance(defects, list) or [row.get("code") for row in defects] != DEFECT_CODES:
        raise SystemExit("projection verification does not bind all six defects")
    if verification.get("root_source_mutation_count") != 0:
        raise SystemExit("root canonical sources changed during B04-0003")
    if verification.get("live_snapshot_mutation_count") != 0:
        raise SystemExit("live package snapshot changed during B04-0003")
    if verification.get("unrelated_write_count") != 0:
        raise SystemExit("B04-0003 records unrelated writes")
    not_run = "NOT_RUN_NON_WAIVABLE_MECHANISM_FAILURE"
    if verification.get("wheel_resource_load_result") != not_run:
        raise SystemExit("wheel gate was not recorded as deliberately unrun")
    if verification.get("deterministic_rebuild_result") != not_run:
        raise SystemExit("rebuild gate was not recorded as deliberately unrun")
    if installed.get("status") != "NOT_RUN":
        raise SystemExit("installed-wheel evidence must remain NOT_RUN")
    if dependency.get("status") != "FAIL" or dependency.get("failure_classification") != "FAIL":
        raise SystemExit("dependency status does not record B04-0003 FAIL")
    states = dependency.get("package_states")
    if not isinstance(states, dict) or states.get("F01") != "WAITING_ON_B04_PROJECTION":
        raise SystemExit("F01 is not held waiting on B04 projection")
    if dependency.get("downstream_package_started") is not False:
        raise SystemExit("downstream execution was recorded as started")
    review = (ATTEMPT / "review.md").read_text(encoding="utf-8")
    if "Overall package status: `FAIL`" not in review:
        raise SystemExit("review does not record overall FAIL")
    if "not external actor-independent" not in " ".join(review.split()):
        raise SystemExit("review omits the actor-independence limitation")
    for code in DEFECT_CODES:
        if code.split("_", 1)[0] not in review and code not in review:
            raise SystemExit(f"review omits blocking defect {code}")
    read_commands()
    if require_closeout:
        report = read_json(ATTEMPT / "report.json")
        integrity = read_json(ATTEMPT / "rah-core-integrity.json")
        if report.get("status") != "FAIL" or report.get("package_status") != "FAIL":
            raise SystemExit("B04-0003 report is not FAIL")
        if report.get("failure_classification") != "FAIL":
            raise SystemExit("B04-0003 report has the wrong failure classification")
        if report.get("completion_ready") is not False:
            raise SystemExit("B04-0003 report advances completion readiness")
        if integrity.get("status") != "PASS":
            raise SystemExit("core RAH integrity artifact is not PASS")


def verify_generation_store(expected_count: int) -> dict[str, Any]:
    ralph_root, current, payloads = current_state()
    generations = numbered_generations(ralph_root)
    if len(generations) != expected_count or generations[-1] != current:
        raise SystemExit(
            f"expected {expected_count} retained generations ending at {current}, found {len(generations)}"
        )
    verified_hashes = 0
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
            verified_hashes += 1
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
            f"flat snapshot mismatch: stamps={flat_stamps}, matches={flat_matches}"
        )
    loop = payloads["loop_state.json"]
    return {
        "current_generation": current,
        "retained_generation_count": len(generations),
        "generation_file_hashes_verified": verified_hashes,
        "flat_snapshot_stamps_verified": flat_stamps,
        "flat_snapshot_content_matches": flat_matches,
        "generation_manifest_sha256": sha256(
            ralph_root / "generations" / current / "generation-manifest.json"
        ),
        "latest_evidence_id": evidence_ids(payloads)[-1],
        "status": loop.get("status"),
        "completion_ready": loop.get("completion_readiness", {}).get("ready"),
    }


def core_summary() -> str:
    return (
        "B04-0003 FAIL: a read-only external-staging audit of the existing "
        "canonical projection mechanism found six non-waivable implementation "
        "defects: source-bundle algorithm mismatch, missing projected snapshot "
        "hash, missing distinct source/package paths, missing projection-tool "
        "identity/version, missing atomic tree replacement, and missing "
        "SOURCE_CHANGED_DURING_PROJECTION fail-closed behavior. Verification "
        f"sha256:{sha256(ATTEMPT / 'canonical-projection-verification.json')}; "
        f"source inventory sha256:{sha256(ATTEMPT / 'source-inventory.json')}; "
        f"snapshot inventory sha256:{sha256(ATTEMPT / 'snapshot-inventory.json')}; "
        "124 schemas plus OpenAPI 3.1.1/33 operations are inventoried; root/live "
        "mutations are 0/0; missing/extra paths are 0/0; the stale mismatch is "
        "exactly schemas/epistemic-work-classification.schema.json. Live "
        "projection, builds, and regression suites were not run after the "
        "non-waivable mechanism failure. F01-0003/F02/F03 remain unstarted; "
        "completion_ready=false."
    )


def driver_command(mode: str) -> str:
    return (
        "python <active-skill-root>/automation/rah.py "
        f"{mode} . --goal {json.dumps(OBJECTIVE, ensure_ascii=False)}"
        + (" --completion-mode exhaustive" if mode == "drive" else "")
    )


def commit_blocked_generation(
    *,
    payloads: dict[str, Any],
    evidence_summary: str,
    expected_evidence_id: str,
    agent_goal_status: str,
) -> tuple[str, dict[str, Any]]:
    now = rh.utc_now()
    goal = copy.deepcopy(payloads["goal.json"])
    loop = copy.deepcopy(payloads["loop_state.json"])
    ledger = copy.deepcopy(payloads["evidence_ledger.json"])
    evidence_id = rh.add_evidence_entry(
        ledger,
        now=now,
        goal_id=goal["goal_id"],
        iteration=int(loop.get("current_iteration") or 1),
        kind="evidence",
        summary=evidence_summary,
    )
    if evidence_id != expected_evidence_id:
        raise SystemExit(f"unexpected evidence ID {evidence_id}; expected {expected_evidence_id}")
    goal.update({"goal": OBJECTIVE, "status": "blocked", "updated_at_utc": now})
    loop.update(
        {
            "generated_at_utc": now,
            "updated_at_utc": now,
            "goal": OBJECTIVE,
            "status": "blocked",
            "done": False,
            "loop_phase": "verification",
            "implementation_gate": "fail",
            "current_stage": "ralph-blocked",
            "harness_phase": "blocked",
            "blocked_reason": BLOCK_REASON,
            "checkpoint_required": False,
            "mark_done_rejected": False,
            "next_actions": NEXT_ACTIONS,
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
        "current_state": "blocked",
        "allowed_next_states": ["plan", "act", "cancelled"],
    }
    loop["progress_update"] = {
        "created_evidence": [evidence_id],
        "used_evidence": [evidence_id, "E0038"],
        "missing_evidence_ids": [],
        "missing_acceptance_ids": [],
        "missing_validation_ids": [],
        "missing_closeout_ids": [],
    }
    readiness = loop.get("completion_readiness")
    if not isinstance(readiness, dict) or readiness.get("ready") is not False:
        raise SystemExit("completion readiness must remain explicitly false")
    readiness["evidence_count"] = len(ledger["entries"])
    loop["external_driver_contract"]["command"] = driver_command("drive")
    loop["command_recipes"]["ralph"] = driver_command("ralph")
    plan = rh.build_plan_graph(goal, loop, payloads["plan_graph.json"], now)
    bridge = rh.build_goal_bridge(
        ROOT,
        goal,
        loop,
        payloads["goal_bridge.json"],
        SimpleNamespace(goal_status=agent_goal_status, goal_objective=OBJECTIVE),
        now,
    )
    review = copy.deepcopy(payloads["review_gate.json"])
    review["updated_at_utc"] = now
    state_store.KEEP_GENERATIONS = 10_000
    ralph_root = ROOT / ".rah" / "ralph"
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
    status_path = ROOT / ".rah" / "state" / "status.json"
    gates_path = ROOT / ".rah" / "state" / "gates.json"
    status = read_json(status_path)
    gates = read_json(gates_path)
    status["implementation_gate"] = "fail"
    status["implementation_gate_note"] = BLOCK_REASON
    gates["implementation_gate"] = {
        "status": "fail",
        "note": BLOCK_REASON,
        "evidence_ids": [
            identifier
            for identifier in (CORE_EVIDENCE_ID, FINAL_EVIDENCE_ID)
            if identifier in evidence_ids({"evidence_ledger.json": ledger})
        ],
    }
    rh.write_json(status_path, status)
    rh.write_json(gates_path, gates)
    rh.refresh_status_for_ralph(ROOT, ROOT / ".rah", goal, loop, now)
    rh.upsert_current_loop(
        ROOT / ".rah" / "plans" / "current_loop.md",
        rh.render_managed_current_loop(goal, loop),
    )
    rh.write_text(ralph_root / "blockers.md", rh.render_blockers(goal, loop, now))
    return generation, ledger


def run_preflight() -> dict[str, Any]:
    assert_attempt_evidence(require_closeout=False)
    ralph_root, generation, payloads = current_state()
    if generation != CORE_PARENT:
        raise SystemExit(f"unexpected B04-0003 core parent {generation}")
    if evidence_ids(payloads) != [f"E{index:04d}" for index in range(1, 39)]:
        raise SystemExit("core preflight requires preserved E0001-E0038")
    if payloads["loop_state.json"].get("status") != "active":
        raise SystemExit("core preflight requires the activated RAH state")
    generations = numbered_generations(ralph_root)
    if len(generations) != 36 or generations[-1] != generation:
        raise SystemExit("core preflight requires all 36 prior generations")
    return {
        "mode": "preflight",
        "generation": generation,
        "latest_evidence_id": "E0038",
        "retained_generation_count": len(generations),
        "commands_parsed": len(read_commands()),
        "completion_ready": False,
    }


def run_core() -> dict[str, Any]:
    run_preflight()
    ralph_root, parent, payloads = current_state()
    before = numbered_generations(ralph_root)
    generation, _ = commit_blocked_generation(
        payloads=payloads,
        evidence_summary=core_summary(),
        expected_evidence_id=CORE_EVIDENCE_ID,
        agent_goal_status="paused",
    )
    _, current, sealed = current_state()
    if current != generation:
        raise SystemExit("core generation pointer mismatch")
    if evidence_ids(sealed) != [f"E{index:04d}" for index in range(1, 40)]:
        raise SystemExit("core seal did not append exactly E0039")
    if sealed["evidence_ledger.json"]["entries"][-1].get("summary") != core_summary():
        raise SystemExit("E0039 does not match the exact B04-0003 FAIL summary")
    loop = sealed["loop_state.json"]
    if loop.get("status") != "blocked" or loop.get("blocked_reason") != BLOCK_REASON:
        raise SystemExit("RAH did not persist the exact B04-0003 blocker")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("core seal did not preserve every prior generation")
    return {
        "mode": "core",
        "parent_generation": parent,
        "generation": generation,
        "evidence_id": CORE_EVIDENCE_ID,
        "status": "blocked",
        "failure_classification": "FAIL",
        "state_verification": verify_generation_store(37),
        "completion_ready": False,
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
        "dependency-status.json",
        "rah-core-integrity.json",
        "audit_projection_mechanism.py",
        "b04-0003-rah-seal.py",
    )
    hashes = {name: sha256(ATTEMPT / name) for name in names}
    summary = (
        "B04-0003 FAIL closeout is hash-sealed after core blocker generation "
        f"{parent}: report sha256:{hashes['report.json']}; review sha256:"
        f"{hashes['review.md']}; commands sha256:{hashes['commands.jsonl']}; "
        "projection verification sha256:"
        f"{hashes['canonical-projection-verification.json']}; source inventory "
        f"sha256:{hashes['source-inventory.json']}; snapshot inventory sha256:"
        f"{hashes['snapshot-inventory.json']}; installed-wheel evidence sha256:"
        f"{hashes['installed-wheel-verification.json']}; dependency status "
        f"sha256:{hashes['dependency-status.json']}; core RAH integrity sha256:"
        f"{hashes['rah-core-integrity.json']}; audit sha256:"
        f"{hashes['audit_projection_mechanism.py']}; seal wrapper sha256:"
        f"{hashes['b04-0003-rah-seal.py']}. B04-0003 remains FAIL, no live "
        "projection/build receipt exists, F01-0003/F02/F03 remain unstarted, all "
        "prior generations and dirty-worktree content remain preserved, and "
        "completion_ready=false."
    )
    return summary, hashes


def run_final(agent_goal_status: str) -> dict[str, Any]:
    assert_attempt_evidence(require_closeout=True)
    ralph_root, parent, payloads = current_state()
    if not re.fullmatch(r"000037-[0-9a-f]{8}", parent):
        raise SystemExit(f"unexpected final parent generation: {parent}")
    if evidence_ids(payloads) != [f"E{index:04d}" for index in range(1, 40)]:
        raise SystemExit("final seal requires preserved E0001-E0039")
    if payloads["evidence_ledger.json"]["entries"][-1].get("summary") != core_summary():
        raise SystemExit("E0039 changed before final sealing")
    report = read_json(ATTEMPT / "report.json")
    rah_state = report.get("rah_state")
    if not isinstance(rah_state, dict) or rah_state.get("core_generation") != parent:
        raise SystemExit("report does not bind the core RAH generation")
    if rah_state.get("core_evidence_id") != CORE_EVIDENCE_ID:
        raise SystemExit("report does not bind E0039")
    if rah_state.get("final_closeout_evidence_id") != FINAL_EVIDENCE_ID:
        raise SystemExit("report does not reserve E0040")
    integrity = read_json(ATTEMPT / "rah-core-integrity.json")
    if integrity.get("current_generation") != parent:
        raise SystemExit("core integrity artifact does not bind the core generation")
    summary, hashes = final_summary(parent)
    before = numbered_generations(ralph_root)
    generation, _ = commit_blocked_generation(
        payloads=payloads,
        evidence_summary=summary,
        expected_evidence_id=FINAL_EVIDENCE_ID,
        agent_goal_status=agent_goal_status,
    )
    _, current, sealed = current_state()
    if current != generation:
        raise SystemExit("final generation pointer mismatch")
    if evidence_ids(sealed) != [f"E{index:04d}" for index in range(1, 41)]:
        raise SystemExit("final seal did not append exactly E0040")
    if sealed["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
        raise SystemExit("E0040 does not match the closeout hash seal")
    if sealed["loop_state.json"].get("status") != "blocked":
        raise SystemExit("final seal did not retain blocked status")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("final seal did not preserve every prior generation")
    return {
        "mode": "final",
        "parent_generation": parent,
        "generation": generation,
        "evidence_id": FINAL_EVIDENCE_ID,
        "artifact_hashes": hashes,
        "status": "blocked",
        "failure_classification": "FAIL",
        "state_verification": verify_generation_store(38),
        "completion_ready": False,
    }


def run_verify() -> dict[str, Any]:
    assert_attempt_evidence(require_closeout=(ATTEMPT / "report.json").is_file())
    generations = numbered_generations(ROOT / ".rah" / "ralph")
    if len(generations) not in (36, 37, 38):
        raise SystemExit(f"unexpected retained generation count: {len(generations)}")
    return {
        "mode": "verify",
        "fixed_evidence": "PASS",
        "state_verification": verify_generation_store(len(generations)),
        "completion_ready": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("preflight", "core", "final", "verify"))
    parser.add_argument(
        "--agent-goal-status",
        choices=("paused", "blocked"),
        default="paused",
    )
    args = parser.parse_args()
    if args.mode == "preflight":
        result = run_preflight()
    elif args.mode == "core":
        result = run_core()
    elif args.mode == "final":
        result = run_final(args.agent_goal_status)
    else:
        result = run_verify()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
