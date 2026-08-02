#!/usr/bin/env python3
"""Build and verify the evidence set for B02-0002.

The verifier proves attribution from the preserved pre-correction hashes,
keeps the historical B02 and J02 artifacts immutable, and records the stale
production double-build helper as an explicit B04 integration handoff rather
than hiding it or changing it outside B02's correction scope.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/B02/attempts/0002"
RALPH_ROOT = ROOT / ".rah/ralph"

ATTEMPT_ID = "B02-0002"
WORK_PACKAGE_ID = "B02"
DECISION_ID = "HD-EF4-J02-SG002-20260730-001"
EXPECTED_MANIFEST_SHA256 = (
    "7d1d3248dc3e2ca56d8f08ec282aa3d95bea9466ba6b7580fccff81e0f639319"
)
EXPECTED_OLD_PYPROJECT_SHA256 = (
    "29d7a25d530884a4a2dff3d8ca2d9878717a43a4dc3c2710fc5317f533a7be44"
)
EXPECTED_NEW_PYPROJECT_SHA256 = (
    "31cf5dffa4703052d70536dbbb6e64d917900c70d52b039f9c9cbf09920353db"
)
EXPECTED_OLD_LOCK_SHA256 = (
    "728e9d36f966b38a0f86ea5300210760b889110ba5adce5e646efa439ea2efac"
)
EXPECTED_NEW_LOCK_SHA256 = (
    "5c3798ff0323f9352d73f17fa93913590d7dbb5382dd0de26b1619e775b58caa"
)
EXPECTED_PRODUCTION_HELPER_SHA256 = (
    "99f223bd8d4a3d397cf9c560274c498a3a51c15116e094f9896278640aca32df"
)
EXPECTED_HISTORICAL_HASHES = {
    "artifacts/work_packages/B02/report.json":
        "98abe689dbfb9399d2f50f87a18376ca9a85ed4a50c938513778e312e3e67dad",
    "artifacts/work_packages/B02/review.md":
        "4e400b8809e1f5b44fb053c150865472c4017818ed2f5683a34160821e8ed228",
    "artifacts/work_packages/B02/commands.jsonl":
        "4512079c4e3fee831c8bfb65b352ac072eb546496b94b331bf75f50ce46b6fae",
    "artifacts/work_packages/B02/lockfile-check.json":
        "99892d026a647f9014f38767729d4078790e66288daba52a079b54570c630aa1",
    "artifacts/work_packages/B02/double-build-comparison.json":
        "21996791c01780f611d8906ab1e8a3ec241a866c77eb8fea3954573abaffd1ba",
    "artifacts/work_packages/J02/attempts/0002/report.json":
        "17e342ae7f54707ebc0acc17f695507397b9d300a54cef741b2ab3ed05ffbd0c",
    "artifacts/work_packages/J02/attempts/0002/review.md":
        "91dc7869e0443883acf17c3974ae2b1dd1fb3ea484926dba267d2cea75b586de",
}
CORE_EVIDENCE_ID = "E0090"
FINAL_EVIDENCE_ID = "E0091"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON artifact is not an object: {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def current_generation() -> tuple[str, dict[str, Any]]:
    pointer = read_json(RALPH_ROOT / "current.json")
    generation = str(pointer.get("generation") or "")
    if not re.fullmatch(r"\d{6}-[0-9a-f]{8}", generation):
        raise RuntimeError("invalid RAH current generation")
    root = RALPH_ROOT / "generations" / generation
    manifest = read_json(root / "generation-manifest.json")
    if manifest.get("generation") != generation:
        raise RuntimeError("RAH generation manifest identity mismatch")
    payloads: dict[str, Any] = {}
    files = manifest.get("files")
    if not isinstance(files, dict) or len(files) != 6:
        raise RuntimeError("RAH generation manifest does not bind six files")
    for name, expected in files.items():
        path = root / name
        if sha256(path) != expected:
            raise RuntimeError(f"RAH generation hash mismatch: {generation}/{name}")
        payloads[name] = read_json(path)
    return generation, payloads


def evidence_ids(payloads: dict[str, Any]) -> list[str]:
    entries = payloads["evidence_ledger.json"].get("entries")
    if not isinstance(entries, list):
        raise RuntimeError("RAH evidence ledger is invalid")
    return [str(row.get("id")) for row in entries if isinstance(row, dict)]


def verify_fixed_evidence() -> dict[str, Any]:
    if sha256(ROOT / "pyproject.toml") != EXPECTED_NEW_PYPROJECT_SHA256:
        raise RuntimeError("B02 pyproject.toml hash changed after verification")
    if sha256(ROOT / "uv.lock") != EXPECTED_NEW_LOCK_SHA256:
        raise RuntimeError("B02 uv.lock hash changed after verification")
    if sha256(ROOT / "manifests/development_manifest.yaml") != EXPECTED_MANIFEST_SHA256:
        raise RuntimeError("authorized development manifest hash changed")
    if sha256(ROOT / "scripts/build/double_build.py") != EXPECTED_PRODUCTION_HELPER_SHA256:
        raise RuntimeError("production double-build helper changed during B02 correction")

    for relative, expected in EXPECTED_HISTORICAL_HASHES.items():
        if sha256(ROOT / relative) != expected:
            raise RuntimeError(f"immutable history changed: {relative}")

    decision = read_json(
        ROOT
        / "artifacts/authority_decisions/HD-EF4-J02-SG002-20260730-001.human-decision.json"
    )
    if decision.get("decision_id") != DECISION_ID or decision.get("subject_id") != "J02-SG002":
        raise RuntimeError("B02 authorizing HumanDecision identity mismatch")

    lock = read_json(ATTEMPT / "lock-diff-verification-final.json")
    if (
        lock.get("final_status") != "PASS"
        or lock.get("old_pyproject_hash") != "sha256:" + EXPECTED_OLD_PYPROJECT_SHA256
        or lock.get("old_lock_hash") != "sha256:" + EXPECTED_OLD_LOCK_SHA256
        or lock.get("new_lock_hash") != "sha256:" + EXPECTED_NEW_LOCK_SHA256
        or lock.get("installed_tiktoken_version") != "0.13.0"
        or lock.get("tokenizer_encoding") != "o200k_base"
        or lock.get("tokenizer_vector_pass_count") != 7
        or lock.get("unrelated_dependency_change_count") != 0
        or lock.get("runtime_dependency_exposure") is not False
        or lock.get("frozen_sync_result") != "PASS"
    ):
        raise RuntimeError("B02 lock-diff verification is not the exact PASS contract")

    lockfile = read_json(ATTEMPT / "lockfile-check-final.json")
    if (
        lockfile.get("status") != "PASS"
        or lockfile.get("uv_lock_check") != "PASS"
        or lockfile.get("python", {}).get("packages") != 21
        or lockfile.get("python", {}).get("registry_packages") != 20
    ):
        raise RuntimeError("B02 lockfile check is not PASS")

    current_build = read_json(ATTEMPT / "double-build-comparison-current-inputs.json")
    wheel = current_build.get("artifacts", {}).get(
        "epistemic_foundry-4.0.0-py3-none-any.whl", {}
    )
    if (
        current_build.get("status") != "PASS"
        or current_build.get("harness_mode") != "ATTEMPT_LOCAL_CURRENT_INPUT_ADAPTER"
        or current_build.get("artifact_count") != 11
        or current_build.get("mismatches") != []
        or current_build.get("artifact_inventory_equal") is not True
        or current_build.get("source_snapshots_equal") is not True
        or current_build.get("production_helper_modified") is not False
        or wheel.get("sha256")
        != "cc3aa468f09092134a4bc8448f4bf60822a4d2ff8df6df16bcbc86483238cb7a"
    ):
        raise RuntimeError("B02 current-input double-build evidence is not PASS")

    for name in ("double-build-comparison.json", "double-build-comparison-rerun.json"):
        historical = read_json(ATTEMPT / name)
        if historical.get("status") != "FAIL" or "build backend returned an error" not in str(
            historical.get("error")
        ):
            raise RuntimeError(f"historical production-helper failure changed: {name}")
    diagnostic = read_json(ATTEMPT / "staged-build-diagnostic.json")
    if diagnostic.get("exit_code") != 2 or "No module named 'scripts'" not in str(
        diagnostic.get("stderr")
    ):
        raise RuntimeError("production-helper staging diagnostic changed")

    return {
        "current_build": current_build,
        "lock": lock,
        "lockfile": lockfile,
        "production_diagnostic": diagnostic,
    }


def scratch_residue() -> list[str]:
    candidates = (
        ATTEMPT / "__pycache__/run_double_build_current_inputs.cpython-312.pyc",
        ATTEMPT / "__pycache__/verify_lock_correction.cpython-312.pyc",
        ROOT / ".rah/tmp/b02-build-debug/.gitignore",
        ROOT / ".rah/tmp/b02-build-debug/epistemic_foundry-4.0.0-py3-none-any.whl",
    )
    return [path.relative_to(ROOT).as_posix() for path in candidates if path.is_file()]


def build_write_scope() -> dict[str, Any]:
    fixed = verify_fixed_evidence()
    return {
        "attempt_id": ATTEMPT_ID,
        "attribution_method": (
            "The exact dependency-group block is removed from the current pyproject "
            "to reconstruct the sealed pre-B02 hash, then uv 0.7.21 reconstructs the "
            "sealed pre-B02 lock and a structural old/new comparison proves that only "
            "tiktoken 0.13.0 plus its mandatory transitive closure was added."
        ),
        "authorized_product_paths": [
            "pyproject.toml",
            "uv.lock",
            "artifacts/work_packages/B02/**",
        ],
        "attributed_product_changes": ["pyproject.toml", "uv.lock"],
        "product_write_scope_violation_count": 0,
        "product_write_scope_violations": [],
        "hashes": {
            "old_pyproject": "sha256:" + EXPECTED_OLD_PYPROJECT_SHA256,
            "new_pyproject": "sha256:" + EXPECTED_NEW_PYPROJECT_SHA256,
            "old_uv_lock": "sha256:" + EXPECTED_OLD_LOCK_SHA256,
            "new_uv_lock": "sha256:" + EXPECTED_NEW_LOCK_SHA256,
            "production_double_build_helper": "sha256:" + EXPECTED_PRODUCTION_HELPER_SHA256,
        },
        "preservation": {
            "historical_b02_root_artifacts_immutable": True,
            "j02_0002_fail_history_immutable": True,
            "production_helper_modified": False,
            "reset_clean_stash_commit_push_performed": False,
            "subagents_or_fleet_used": False,
            "dirty_worktree_preserved": True,
        },
        "operational_scratch_residue": scratch_residue(),
        "operational_scratch_note": (
            "The listed cache/diagnostic leaves are not product-change attribution. "
            "Two exact cleanup attempts were rejected before execution by the Windows "
            "safety hook; no destructive workaround was used."
        ),
        "runtime_dependency_exposure": fixed["lock"]["runtime_dependency_exposure"],
        "status": "PASS",
    }


def build_commands() -> list[dict[str, Any]]:
    stamp = "2026-07-30T05:12:29.749Z"
    return [
        {"command_id": "B02-0002-C001", "command": 'uv add --group skill-context "tiktoken==0.13.0"', "exit_code": 0, "result": "PASS: exact dependency group added and uv.lock generated", "recorded_at_utc": stamp},
        {"command_id": "B02-0002-C002", "command": "uv lock --check", "exit_code": 0, "result": "PASS: Resolved 21 packages", "recorded_at_utc": stamp},
        {"command_id": "B02-0002-C003", "command": "uv sync --frozen --extra dev --group skill-context", "exit_code": 0, "result": "PASS: 21 packages audited; tiktoken 0.13.0 installed", "recorded_at_utc": stamp},
        {"command_id": "B02-0002-C004", "command": "python artifacts/work_packages/B02/attempts/0002/verify_lock_correction.py --report artifacts/work_packages/B02/attempts/0002/lock-diff-verification-final.json", "exit_code": 0, "result": "PASS: old hashes reconstructed; unrelated changes 0; vectors 7/7", "recorded_at_utc": stamp},
        {"command_id": "B02-0002-C005", "command": "uv run --frozen --extra dev --group skill-context pytest tests/test_j02_context_budget.py::test_pinned_tokenizer_vectors_are_exact_and_repeatable -q -p no:cacheprovider", "exit_code": 0, "result": "PASS: 1 passed", "recorded_at_utc": stamp},
        {"command_id": "B02-0002-C006", "command": "python scripts/build/check_locks.py --report artifacts/work_packages/B02/attempts/0002/lockfile-check-final.json", "exit_code": 0, "result": "PASS: 21 packages, 20 registry packages, uv lock current", "recorded_at_utc": stamp},
        {"command_id": "B02-0002-C007", "command": "python scripts/build/double_build.py --report artifacts/work_packages/B02/attempts/0002/double-build-comparison-rerun.json", "exit_code": 2, "expected_failure": True, "result": "PRESERVED FAIL: historical staging omits the scripts build-hook package", "recorded_at_utc": stamp},
        {"command_id": "B02-0002-C008", "command": "python artifacts/work_packages/B02/attempts/0002/diagnose_staged_build.py", "exit_code": 2, "expected_failure": True, "result": "DIAGNOSTIC: ModuleNotFoundError for scripts in historical staging", "recorded_at_utc": stamp},
        {"command_id": "B02-0002-C009", "command": "python artifacts/work_packages/B02/attempts/0002/run_double_build_current_inputs.py --report artifacts/work_packages/B02/attempts/0002/double-build-comparison-current-inputs.json", "exit_code": 0, "result": "PASS: 11 artifacts byte-identical; mismatches 0", "recorded_at_utc": stamp},
        {"command_id": "B02-0002-C010", "command": "git diff --check -- pyproject.toml uv.lock artifacts/work_packages/B02/attempts/0002", "exit_code": 0, "result": "PASS; line-ending notice only", "recorded_at_utc": stamp},
        {"command_id": "B02-0002-C011", "command": "git diff --check", "exit_code": 0, "result": "PASS; pre-existing line-ending notices only", "recorded_at_utc": stamp},
        {"command_id": "B02-0002-C012", "command": "primary-session separate adversarial review", "exit_code": 0, "result": "PASS_WITH_B04_HANDOFF; actor_independence=false", "recorded_at_utc": stamp},
    ]


def render_review() -> str:
    return """# B02-0002 exact dependency-lock correction review

Overall correction status: `PASS`

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_REVIEW`

Assurance limitation: `actor_independence=false`. This is a procedurally
separate primary-session review, not external or actor-independent
certification. Fleet and subagents were prohibited and were not used.

## Verified correction

- `pyproject.toml` declares only the canonical `skill-context` group with
  exact `tiktoken==0.13.0`; it is absent from runtime and optional dependency
  metadata.
- uv 0.7.21 reconstructs the preserved pre-correction hashes exactly and the
  new lock adds only `tiktoken` plus `certifi`, `charset-normalizer`, `idna`,
  `regex`, `requests`, and `urllib3`. Unrelated upgrade, downgrade, removal,
  source change, editable path, and floating Git dependency counts are zero.
- Frozen sync passes, the installed version is exactly 0.13.0, `o200k_base`
  loads, all 7 tokenizer vectors pass, and the targeted pytest is 1/1.
- The lock checker passes with 21 packages and 20 registry packages.
- The attempt-local current-input build adapter stages `packages`, `src`,
  `toolchains`, `scripts`, `schemas`, and `openapi`; two builds yield the same
  source snapshot and 11 byte-identical artifacts with zero mismatches.

## Preserved integration finding

The production `scripts/build/double_build.py` remains byte-identical at
`sha256:99f223bd8d4a3d397cf9c560274c498a3a51c15116e094f9896278640aca32df`.
It predates the B04 canonical build hook: its historical staging omits
`scripts`, `schemas`, and `openapi`, and its name-only `build` exclusion also
removes `scripts/build/canonical_registry`. The preserved production-helper
run therefore fails with `ModuleNotFoundError: No module named 'scripts'`.
This failure is not relabeled as PASS and the helper is not modified under
B02's narrow write scope. HD-EF4-J02-SG002-20260730-001 assigns the independent
dependency/build revalidation and any integration correction to the next B04
attempt.

Two exact scratch-cleanup commands were rejected before execution by the
Windows safety hook. No destructive workaround was used; the remaining cache
and diagnostic leaves are recorded in `write-scope-verification.json` and are
not treated as product changes.

## Decision

The exact dependency correction satisfies the B02 correction contract with
product write-scope violations 0 and blocking B02-owned findings 0. B02-0002
passes, while B04 revalidation remains mandatory. The historical B02 root PASS,
J02-0002 FAIL, all retained RAH history, and the dirty worktree remain
immutable. J02-0003 has not started and `completion_ready=false`.
"""


def write_pre_core() -> dict[str, Any]:
    fixed = verify_fixed_evidence()
    write_json(ATTEMPT / "write-scope-verification.json", build_write_scope())
    rows = build_commands()
    (ATTEMPT / "commands.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )
    (ATTEMPT / "review.md").write_text(render_review(), encoding="utf-8", newline="\n")
    return {
        "attempt_id": ATTEMPT_ID,
        "double_build_artifact_count": fixed["current_build"]["artifact_count"],
        "mode": "pre-core",
        "status": "PASS",
        "tokenizer_vectors": fixed["lock"]["tokenizer_vector_pass_count"],
    }


def generation_integrity(expected_latest: str) -> dict[str, Any]:
    generation, payloads = current_generation()
    ids = evidence_ids(payloads)
    if ids != [f"E{index:04d}" for index in range(1, int(expected_latest[1:]) + 1)]:
        raise RuntimeError("RAH evidence IDs are not contiguous through the expected seal")
    generations = sorted(
        path.name
        for path in (RALPH_ROOT / "generations").iterdir()
        if path.is_dir() and re.fullmatch(r"\d{6}-[0-9a-f]{8}", path.name)
    )
    verified = 0
    for name in generations:
        root = RALPH_ROOT / "generations" / name
        manifest = read_json(root / "generation-manifest.json")
        files = manifest.get("files")
        if manifest.get("generation") != name or not isinstance(files, dict) or len(files) != 6:
            raise RuntimeError(f"invalid retained generation manifest: {name}")
        for relative, expected in files.items():
            if sha256(root / relative) != expected:
                raise RuntimeError(f"retained generation hash mismatch: {name}/{relative}")
            verified += 1
    flat_stamps = 0
    flat_matches = 0
    for relative, authority in payloads.items():
        flat = read_json(RALPH_ROOT / relative)
        if flat.get("state_generation") == generation:
            flat_stamps += 1
        stripped = {key: value for key, value in flat.items() if key != "state_generation"}
        if json.dumps(stripped, ensure_ascii=False, indent=2) == json.dumps(
            authority, ensure_ascii=False, indent=2
        ):
            flat_matches += 1
    loop = payloads["loop_state.json"]
    if (
        loop.get("status") != "active"
        or loop.get("implementation_gate") != "fail"
        or loop.get("completion_readiness", {}).get("ready") is not False
    ):
        raise RuntimeError("RAH must remain active/fail/completion_ready=false")
    return {
        "attempt_id": ATTEMPT_ID,
        "completion_ready": False,
        "current_generation": generation,
        "evidence_count": len(ids),
        "flat_snapshot_content_matches": flat_matches,
        "flat_snapshot_stamps_verified": flat_stamps,
        "generation_file_hashes_verified": verified,
        "generation_manifest_sha256": "sha256:" + sha256(
            RALPH_ROOT / "generations" / generation / "generation-manifest.json"
        ),
        "implementation_gate": "fail",
        "latest_evidence_id": ids[-1],
        "ralph_status": "active",
        "retained_generation_count": len(generations),
        "retained_generations": generations,
        "status": "PASS",
    }


def build_report(integrity: dict[str, Any]) -> dict[str, Any]:
    fixed = verify_fixed_evidence()
    lock = fixed["lock"]
    current_build = fixed["current_build"]
    return {
        "attempt_id": ATTEMPT_ID,
        "authority_decision_id": DECISION_ID,
        "changed_product_files": ["pyproject.toml", "uv.lock"],
        "completion_ready": False,
        "dependency_effect": {
            "B02": "PASS",
            "B04": "READY_FOR_DEPENDENCY_BUILD_REVALIDATION",
            "S04": "WAITING_ON_B04_REVALIDATION",
            "J02": "WAITING_ON_B04_AND_S04",
        },
        "historical_preservation": {
            "historical_b02_root_pass_immutable": True,
            "j02_0002_fail_immutable": True,
            "dirty_worktree_preserved": True,
            "prior_RAH_evidence_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
            "subagents_or_fleet_used": False,
        },
        "implementation_status": "PASS",
        "integration_handoff": {
            "B04_revalidation_pending": True,
            "current_input_semantic_double_build": "PASS_11_BYTE_IDENTICAL_ARTIFACTS",
            "production_helper": "PRESERVED_STALE_STAGING_FAILURE",
            "production_helper_modified": False,
            "production_helper_owner": "B04_REVALIDATION",
        },
        "lock_correction": {
            "direct_dependency": "tiktoken==0.13.0",
            "dependency_group": "skill-context",
            "installed_version": lock["installed_tiktoken_version"],
            "new_lock_hash": lock["new_lock_hash"],
            "old_lock_hash": lock["old_lock_hash"],
            "runtime_dependency_exposure": False,
            "transitive_additions": lock["transitive_dependency_changes"],
            "unrelated_dependency_change_count": 0,
        },
        "not_claimed": [
            "B04 dependency/build revalidation PASS",
            "production double-build helper correction",
            "S04-TM004 reconciliation",
            "J02-0003 start or PASS",
            "repository-wide conformance or product completion",
            "actor-independent certification",
        ],
        "output_artifacts": [
            f"artifacts/work_packages/B02/attempts/0002/{name}"
            for name in (
                "report.json",
                "commands.jsonl",
                "review.md",
                "write-scope-verification.json",
                "lock-diff-verification-final.json",
                "lockfile-check-final.json",
                "double-build-comparison-current-inputs.json",
                "double-build-comparison.json",
                "double-build-comparison-rerun.json",
                "staged-build-diagnostic.json",
                "rah-core-integrity.json",
            )
        ],
        "package_status": "PASS",
        "rah_state": {
            "completion_ready": False,
            "core_evidence_id": CORE_EVIDENCE_ID,
            "core_generation": integrity["current_generation"],
            "core_generation_manifest_sha256": integrity["generation_manifest_sha256"],
            "final_artifact_seal_evidence_id": FINAL_EVIDENCE_ID,
            "flat_snapshot_content_matches_after_core": integrity["flat_snapshot_content_matches"],
            "flat_snapshot_stamps_verified_after_core": integrity["flat_snapshot_stamps_verified"],
            "generation_file_hashes_verified_after_core": integrity["generation_file_hashes_verified"],
            "implementation_gate": "fail",
            "retained_generation_count_after_core": integrity["retained_generation_count"],
            "status": "active",
        },
        "required_checks": {
            "double_build_comparison": {
                "B02_correction_status": "PASS",
                "artifact_count": current_build["artifact_count"],
                "current_input_adapter": "PASS",
                "mismatch_count": len(current_build["mismatches"]),
                "production_helper": "FAIL_PRESERVED_FOR_B04_REVALIDATION",
            },
            "j02_tokenizer_vector_test": {"passed": 7, "status": "PASS"},
            "lockfile_check": {"status": "PASS"},
            "skill_context_frozen_sync": {"status": "PASS"},
            "tiktoken_exact_lock_check": {"status": "PASS", "version": "0.13.0"},
            "write_scope_audit": {"status": "PASS", "violations": 0},
        },
        "review": {
            "actor_independence": False,
            "artifact": "artifacts/work_packages/B02/attempts/0002/review.md",
            "assurance_limitation": "Primary-session separate review; not external actor-independent certification.",
            "blocking_B02_owned_finding_count": 0,
            "mode": "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_REVIEW",
            "verdict": "PASS_WITH_B04_HANDOFF",
        },
        "status": "PASS",
        "verification": {
            "artifact_count": current_build["artifact_count"],
            "frozen_sync": "PASS",
            "lock_packages": 21,
            "lock_registry_packages": 20,
            "tokenizer_vectors": "7/7",
            "targeted_pytest": "1/1",
            "unrelated_dependency_changes": 0,
            "write_scope_violations": 0,
        },
        "work_package_id": WORK_PACKAGE_ID,
    }


def write_post_core() -> dict[str, Any]:
    verify_pre_core()
    integrity = generation_integrity(CORE_EVIDENCE_ID)
    write_json(ATTEMPT / "rah-core-integrity.json", integrity)
    write_json(ATTEMPT / "report.json", build_report(integrity))
    return {"attempt_id": ATTEMPT_ID, "mode": "post-core", "status": "PASS", **integrity}


def verify_pre_core() -> dict[str, Any]:
    fixed = verify_fixed_evidence()
    expected_scope = build_write_scope()
    if read_json(ATTEMPT / "write-scope-verification.json") != expected_scope:
        raise RuntimeError("stored B02 write-scope evidence differs from recomputation")
    expected_commands = build_commands()
    rows = [
        json.loads(line)
        for line in (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if rows != expected_commands:
        raise RuntimeError("stored B02 command ledger differs from recomputation")
    if (ATTEMPT / "review.md").read_text(encoding="utf-8") != render_review():
        raise RuntimeError("stored B02 review differs from deterministic review")
    return {
        "attempt_id": ATTEMPT_ID,
        "artifact_count": fixed["current_build"]["artifact_count"],
        "mode": "pre-core-verify",
        "status": "PASS",
    }


def verify_all() -> dict[str, Any]:
    verify_pre_core()
    generation, payloads = current_generation()
    latest = evidence_ids(payloads)[-1]
    if latest not in (CORE_EVIDENCE_ID, FINAL_EVIDENCE_ID):
        return {"attempt_id": ATTEMPT_ID, "generation": generation, "mode": "pre-core", "status": "PASS"}
    expected_integrity = generation_integrity(latest)
    if latest == CORE_EVIDENCE_ID:
        if read_json(ATTEMPT / "rah-core-integrity.json") != expected_integrity:
            raise RuntimeError("stored B02 core integrity evidence differs from RAH")
    else:
        stored_integrity = read_json(ATTEMPT / "rah-core-integrity.json")
        if stored_integrity.get("latest_evidence_id") != CORE_EVIDENCE_ID:
            raise RuntimeError("B02 report is not bound to the core evidence seal")
    report = read_json(ATTEMPT / "report.json")
    if report.get("package_status") != "PASS" or report.get("completion_ready") is not False:
        raise RuntimeError("B02 report status is invalid")
    if report.get("rah_state", {}).get("core_evidence_id") != CORE_EVIDENCE_ID:
        raise RuntimeError("B02 report does not bind E0090")
    return {
        "attempt_id": ATTEMPT_ID,
        "completion_ready": False,
        "generation": generation,
        "latest_evidence_id": latest,
        "mode": "verify",
        "package_status": "PASS",
        "status": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("pre-core", "post-core", "verify"))
    args = parser.parse_args()
    result = {
        "pre-core": write_pre_core,
        "post-core": write_post_core,
        "verify": verify_all,
    }[args.mode]()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
