#!/usr/bin/env python3
"""Seal D04 evidence while retaining every historical RAH generation."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "artifacts" / "work_packages" / "D04"
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


CORE_PARENT = "000020-e527ff54"
SOURCE_HASHES = {
    "tests/recovery/state/recovery-fixtures.mjs": (
        "a09eca4e977092e99500a8e146196831fb64a155e6b04a23e0c576f81b034b66"
    ),
    "tests/recovery/state/crash-recovery.test.mjs": (
        "73ec38611cd9cb8e93ea531065ff8e885c044f0c8a11a4dcb8a5500e85729cdf"
    ),
    "tests/recovery/state/backup-restore.test.mjs": (
        "f7e780cf3f3a4b15bfd70054bcf06c91ee9ccaa131cc4d7cadc98372a3f6ac66"
    ),
    "tests/recovery/state/test_postgres_backup_restore.py": (
        "877fd187e1f2360fe0afec008e2cec9bb4e85733206e4d61089386ad83ad6141"
    ),
    "packages/foundry-kernel/src/state/sqlite/sqlite-state-store.mjs": (
        "6619dccb72f40e92fdaae3d023a2d6591f8d63bdfe789ba5c36b53ce7dbe1380"
    ),
    "migrations/postgres/0001_team_store.sql": (
        "21f349f098a03b8e7e2f4a82cef69f5df0fe2e73d88224ab197191260e316682"
    ),
    "packages/foundry-kernel/src/artifacts/content-addressed-artifact-store.mjs": (
        "75e69756d30ab5b5112fd908f3fec312660f30e603fe1201566db2ad263c8c8e"
    ),
    "artifacts/work_packages/D02/report.json": (
        "b843adb04258b3e72d3a2f21591441bd94f2a16ea409b014c8b49f1200eb004b"
    ),
    "artifacts/work_packages/D03/report.json": (
        "10f6c29d27bbd68ace5a86fa21d019037b8a7bcec82c92c9f0922d66106eaf33"
    ),
    "manifests/development_manifest.yaml": (
        "a0a0db29da459d29c655827eaa0f7253d1becc3e75106f369850335ac7b88345"
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def numbered_generations(ralph_root: Path) -> list[str]:
    return sorted(
        path.name
        for path in (ralph_root / "generations").iterdir()
        if path.is_dir() and re.fullmatch(r"\d{6}-[0-9a-f]{8}", path.name)
    )


def assert_source_hashes() -> None:
    for relative, expected in SOURCE_HASHES.items():
        actual = sha256(ROOT / relative)
        if actual != expected:
            raise SystemExit(
                f"D04 source/dependency hash mismatch for {relative}: "
                f"{actual} != {expected}"
            )
    review = (PACKAGE / "review.md").read_text(encoding="utf-8")
    if "PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_ADVERSARIAL_REVIEW" not in review:
        raise SystemExit("D04 review does not record the authorized PASS status")
    if "not external" not in review or "actor-independent certification" not in review:
        raise SystemExit("D04 review omits the assurance limitation")
    for finding in ("D04-RF001", "D04-RF002"):
        if finding not in review:
            raise SystemExit(f"D04 review omits resolved finding {finding}")


def current_state() -> tuple[Path, str, dict[str, object]]:
    ralph_root = ROOT / ".rah" / "ralph"
    current = state_store.read_current(ralph_root)
    if current is None:
        raise SystemExit("No committed RAH generation")
    generation, payloads = current
    verified = state_store.verify_current(ralph_root)
    if verified.get("generation") != generation:
        raise SystemExit("RAH generation verification disagrees with current pointer")
    readiness = payloads["loop_state.json"]["completion_readiness"]["ready"]
    if readiness:
        raise SystemExit("D04 cannot seal an already completion-ready goal")
    return ralph_root, generation, payloads


def evidence_ids(payloads: dict[str, object]) -> list[str]:
    ledger = payloads["evidence_ledger.json"]
    if not isinstance(ledger, dict):
        raise SystemExit("RAH evidence ledger is not an object")
    entries = ledger.get("entries")
    if not isinstance(entries, list):
        raise SystemExit("RAH evidence ledger entries are not a list")
    return [str(entry.get("id")) for entry in entries if isinstance(entry, dict)]


def invoke_ralph(summary: str) -> str:
    state_store.KEEP_GENERATIONS = 10_000
    saved_argv = sys.argv
    captured = io.StringIO()
    try:
        sys.argv = [
            "ralph_harness.py",
            str(ROOT),
            "--record-evidence",
            summary,
            "--no-increment",
            "--no-update-current-loop",
            "--json",
        ]
        with contextlib.redirect_stdout(captured):
            result = rh.main()
    finally:
        sys.argv = saved_argv
    if result != 0:
        raise SystemExit(
            f"RAH evidence append failed with exit {result}: {captured.getvalue()}"
        )
    ralph_root, generation, _ = current_state()
    if generation not in numbered_generations(ralph_root):
        raise SystemExit("Committed RAH generation was not retained")
    return generation


def core_summary() -> str:
    review_hash = sha256(PACKAGE / "review.md")
    return (
        "D04-0001 PASS core: real abrupt-process fixtures verify committed SQLite "
        "WAL replay, interrupted-transaction rollback, corruption SAFE_MODE, and "
        "artifact staging quarantine without reset. Hash-bound SQLite and artifact "
        "snapshots restore through sibling staging, copied-byte/inventory integrity "
        "revalidation, and atomic publication; validation-to-publish mutation is "
        "rejected with the target absent and forensic stage preserved. A pinned "
        "PostgreSQL 16.13 disposable container verifies custom-format dump, TOC "
        "preflight, single-transaction staging restore, forced RLS, owner/functions, "
        "runtime access, source-corruption preservation, and corrupt-archive denial. "
        "Final D04 hashes: fixtures sha256:"
        f"{SOURCE_HASHES['tests/recovery/state/recovery-fixtures.mjs']}; crash tests "
        f"sha256:{SOURCE_HASHES['tests/recovery/state/crash-recovery.test.mjs']}; "
        "backup tests sha256:"
        f"{SOURCE_HASHES['tests/recovery/state/backup-restore.test.mjs']}; PostgreSQL "
        "test sha256:"
        f"{SOURCE_HASHES['tests/recovery/state/test_postgres_backup_restore.py']}. "
        "Required targeted checks pass 7/7; final repetitions pass 10/10 Node runs "
        "(60 executions) and 3/3 PostgreSQL runs; Python passes 913/913; review "
        f"sha256:{review_hash} with blocking findings=0. Repository-wide Node retains "
        "only the existing S04-TM004 stale-hash failure and double-build retains its "
        "existing scripts staging omission, both outside D04. completion_ready=false."
    )


def run_core() -> dict[str, object]:
    assert_source_hashes()
    ralph_root, parent, payloads = current_state()
    if parent != CORE_PARENT:
        raise SystemExit(f"Unexpected D04 core parent {parent}; expected {CORE_PARENT}")
    expected_ids = [f"E{index:04d}" for index in range(1, 22)]
    if evidence_ids(payloads) != expected_ids:
        raise SystemExit("D04 core seal requires the preserved E0001-E0021 ledger")
    before = numbered_generations(ralph_root)
    if len(before) != 20 or before[-1] != parent:
        raise SystemExit("D04 core seal requires all 20 prior generations")
    generation = invoke_ralph(core_summary())
    _, _, sealed = current_state()
    if evidence_ids(sealed) != [f"E{index:04d}" for index in range(1, 23)]:
        raise SystemExit("D04 core seal did not append exactly E0022")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("D04 core seal did not preserve every prior generation")
    return {
        "mode": "core",
        "parent_generation": parent,
        "generation": generation,
        "evidence_id": "E0022",
        "retained_generation_count": len(after),
        "completion_ready": False,
    }


def run_final() -> dict[str, object]:
    assert_source_hashes()
    ralph_root, parent, payloads = current_state()
    if not re.fullmatch(r"000021-[0-9a-f]{8}", parent):
        raise SystemExit(f"Unexpected D04 final parent generation: {parent}")
    if evidence_ids(payloads) != [f"E{index:04d}" for index in range(1, 23)]:
        raise SystemExit("D04 final seal requires the preserved E0001-E0022 ledger")
    ledger = payloads["evidence_ledger.json"]
    if ledger["entries"][-1].get("summary") != core_summary():
        raise SystemExit("E0022 does not match the D04 core evidence summary")

    report = json.loads((PACKAGE / "report.json").read_text(encoding="utf-8"))
    rah_state = report.get("rah_state")
    if not isinstance(rah_state, dict):
        raise SystemExit("D04 report has no rah_state closeout record")
    if report.get("status") != "PASS" or report.get("package_status") != "PASS":
        raise SystemExit("D04 report is not PASS")
    if report.get("completion_ready") is not False:
        raise SystemExit("D04 report must keep completion_ready=false")
    if rah_state.get("core_generation") != parent:
        raise SystemExit("D04 report core_generation does not match RAH authority")
    if rah_state.get("core_evidence_id") != "E0022":
        raise SystemExit("D04 report does not bind core evidence E0022")
    if rah_state.get("final_closeout_evidence_id") != "E0023":
        raise SystemExit("D04 report does not reserve final evidence E0023")

    commands = [
        json.loads(raw)
        for raw in (PACKAGE / "commands.jsonl").read_text(encoding="utf-8").splitlines()
        if raw.strip()
    ]
    command_ids = [row.get("command_id") for row in commands]
    if len(command_ids) != len(set(command_ids)):
        raise SystemExit("D04 commands.jsonl has duplicate command IDs")
    if command_ids[-4:] != [
        "D04-0001-C029",
        "D04-0001-C030",
        "D04-0001-C031",
        "D04-0001-C032",
    ]:
        raise SystemExit("D04 core seal, integrity, inspect, and DAG commands are missing")

    dependency = json.loads(
        (PACKAGE / "dependency-status.json").read_text(encoding="utf-8")
    )
    if dependency.get("status") != "PASS" or dependency.get("next_package") != "E01":
        raise SystemExit("D04 dependency reconciliation does not select E01")

    closeout_hashes = {
        name: sha256(PACKAGE / name)
        for name in (
            "report.json",
            "review.md",
            "commands.jsonl",
            "dependency-status.json",
            "d04-rah-seal.py",
        )
    }
    ready = "/".join(dependency["ready_packages_manifest_order"])
    summary = (
        "D04-0001 closeout is hash-sealed after core RAH generation "
        f"{parent}: report sha256:{closeout_hashes['report.json']}; review sha256:"
        f"{closeout_hashes['review.md']}; commands sha256:"
        f"{closeout_hashes['commands.jsonl']}; dependency status sha256:"
        f"{closeout_hashes['dependency-status.json']}; preservation wrapper sha256:"
        f"{closeout_hashes['d04-rah-seal.py']}. D04 package status PASS; blocking "
        "findings=0; all prior generations, reports, failed probes, and dirty "
        "worktree remain preserved. The 156-package DAG has unknown dependencies=0 "
        f"and cycles=0; READY manifest order is {ready}; next package E01. "
        "completion_ready=false."
    )
    before = numbered_generations(ralph_root)
    generation = invoke_ralph(summary)
    _, _, sealed = current_state()
    if evidence_ids(sealed) != [f"E{index:04d}" for index in range(1, 24)]:
        raise SystemExit("D04 final seal did not append exactly E0023")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("D04 final seal did not preserve every prior generation")
    return {
        "mode": "final",
        "parent_generation": parent,
        "generation": generation,
        "evidence_id": "E0023",
        "artifact_hashes": closeout_hashes,
        "retained_generation_count": len(after),
        "completion_ready": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("core", "final"))
    args = parser.parse_args()
    result = run_core() if args.mode == "core" else run_final()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
