#!/usr/bin/env python3
"""Seal E03 evidence while retaining every historical RAH generation."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "artifacts" / "work_packages" / "E03"
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


CORE_PARENT = "000026-2804dbd8"
CORE_SOURCE_HASHES = {
    "packages/foundry-kernel/src/capabilities/capability-authority.mjs": (
        "a8e3376568350229ca1a997aafbc1c4c138f2f01fbee945c916d390283a3720a"
    ),
    "packages/foundry-kernel/src/capabilities/capability-test-support.mjs": (
        "6b08085736247a17b3c477617aa820274a09ca8206d616acc44cd12a1358e2fa"
    ),
    "packages/foundry-kernel/src/capabilities/fencing.test.mjs": (
        "e66558d061c74f2c3be7c5a648b1230ad22f566359d608c6135b62f626940884"
    ),
    "packages/foundry-kernel/src/capabilities/lease-expiry.test.mjs": (
        "ec179fea28039c9e53cc1df8d6d39e1b97ce45b8d60edb0193f64f472ac2f640"
    ),
    "artifacts/work_packages/E03/review.md": (
        "7d4d91e6802156bcca2687bbd8e712189dad6e6129766fb1f0ce9f330ba1d428"
    ),
    "artifacts/work_packages/E03/e03-verification.json": (
        "a6dc580028246a49094bd36ad07568cc0073530f33e2c570de01b64fd3ae2e3d"
    ),
    "artifacts/work_packages/E01/report.json": (
        "beddc2a3019fcf680435ea6d5f907b5e7b50b0fa8a384673917c6198f49f32e1"
    ),
    "schemas/capability-lease.schema.json": (
        "c5eb61b41328b055f75466fd4d1d29ed93a535a2d2375a7596fd8a77ba51946c"
    ),
    "schemas/approval-record.schema.json": (
        "0b0554c764c185f75a568dbf308a17bab291896b6a28bd7633c0b2f7aedaa7eb"
    ),
    "packages/foundry-kernel/src/state/sqlite/sqlite-state-store.mjs": (
        "6619dccb72f40e92fdaae3d023a2d6591f8d63bdfe789ba5c36b53ce7dbe1380"
    ),
    "packages/foundry-kernel/src/artifacts/content-addressed-artifact-store.mjs": (
        "75e69756d30ab5b5112fd908f3fec312660f30e603fe1201566db2ad263c8c8e"
    ),
    "packages/foundry-kernel/src/ledger/noetic-ledger.mjs": (
        "58ea9dc0d52d9c20720b33970ee3b8d8d05703ba7dd0fb4f51a483d9f505f1ed"
    ),
    "manifests/development_manifest.yaml": (
        "a0a0db29da459d29c655827eaa0f7253d1becc3e75106f369850335ac7b88345"
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"cannot read JSON {path}: {error}")
    if not isinstance(document, dict):
        raise SystemExit(f"JSON document is not an object: {path}")
    return document


def read_commands() -> list[dict[str, Any]]:
    commands: list[dict[str, Any]] = []
    try:
        lines = (PACKAGE / "commands.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise SystemExit(f"cannot read E03 commands: {error}")
    for number, raw in enumerate(lines, start=1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as error:
            raise SystemExit(f"commands.jsonl line {number} is invalid: {error}")
        if not isinstance(row, dict):
            raise SystemExit(f"commands.jsonl line {number} is not an object")
        commands.append(row)
    ids = [row.get("command_id") for row in commands]
    if len(ids) != len(set(ids)) or any(not isinstance(value, str) for value in ids):
        raise SystemExit("E03 commands.jsonl has missing or duplicate command IDs")
    return commands


def numbered_generations(ralph_root: Path) -> list[str]:
    return sorted(
        path.name
        for path in (ralph_root / "generations").iterdir()
        if path.is_dir() and re.fullmatch(r"\d{6}-[0-9a-f]{8}", path.name)
    )


def assert_core_hashes() -> None:
    for relative, expected in CORE_SOURCE_HASHES.items():
        actual = sha256(ROOT / relative)
        if actual != expected:
            raise SystemExit(
                f"E03 source/dependency hash mismatch for {relative}: {actual} != {expected}"
            )
    review = (PACKAGE / "review.md").read_text(encoding="utf-8")
    normalized_review = " ".join(review.split())
    if "PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_ADVERSARIAL_REVIEW" not in review:
        raise SystemExit("E03 review does not record the authorized PASS status")
    if "not external actor-independent certification" not in normalized_review:
        raise SystemExit("E03 review omits the assurance limitation")
    if "blocking findings: 0" not in review:
        raise SystemExit("E03 review has unresolved blocking findings")
    verification = read_json(PACKAGE / "e03-verification.json")
    if verification.get("status") != "PASS":
        raise SystemExit("E03 verification artifact is not PASS")


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
        raise SystemExit("E03 cannot seal an already completion-ready goal")
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
    return (
        "E03-0001 PASS core: canonical CapabilityLease and ApprovalRecord artifacts "
        "bind exact principals, runs, capabilities, resource scopes, policy projection, "
        "approvals, expiry, and monotonic fencing. Overlapping scopes stale the older "
        "lease; callback mutation, lease use, and outbox commit atomically in D01 with "
        "pre/post authority validation. Self-approval, untrusted privileged identities, "
        "private authority-record access, stale approval heads, clock regression, "
        "same-instant conflicts, and missing promotion approval fail closed. Exact "
        "lease/approval retries return immutable results after expiry, revoked retry "
        "does not mint a fencing token, and E01 publication reconciles idempotently. "
        "Final hashes: authority sha256:"
        f"{CORE_SOURCE_HASHES['packages/foundry-kernel/src/capabilities/capability-authority.mjs']}; "
        "fencing tests sha256:"
        f"{CORE_SOURCE_HASHES['packages/foundry-kernel/src/capabilities/fencing.test.mjs']}; "
        "lease tests sha256:"
        f"{CORE_SOURCE_HASHES['packages/foundry-kernel/src/capabilities/lease-expiry.test.mjs']}; "
        "verification sha256:"
        f"{CORE_SOURCE_HASHES['artifacts/work_packages/E03/e03-verification.json']}; "
        "review sha256:"
        f"{CORE_SOURCE_HASHES['artifacts/work_packages/E03/review.md']}. Required checks "
        "pass 30/30, five repeats pass 150/150, Python passes 913/913, and blocking "
        "findings=0. Repository-wide Node passes 219/220 with only existing S04-TM004; "
        "the existing double-build staged scripts omission remains outside E03. "
        "completion_ready=false."
    )


def run_preflight() -> dict[str, object]:
    assert_core_hashes()
    report = read_json(PACKAGE / "report.json")
    if report.get("status") != "PASS" or report.get("completion_ready") is not False:
        raise SystemExit("E03 report is not a non-terminal PASS candidate")
    commands = read_commands()
    required = {"E03-0001-C023", "E03-0001-C024"}
    if not required.issubset({row["command_id"] for row in commands}):
        raise SystemExit("E03 construction/preflight command records are missing")
    for name in ("e03-rah-integrity.py", "e03-dag-reconciliation.py", "e03-rah-seal.py"):
        if not (PACKAGE / name).is_file():
            raise SystemExit(f"E03 evidence script is missing: {name}")

    ralph_root, generation, payloads = current_state()
    if generation != CORE_PARENT:
        raise SystemExit(f"Unexpected E03 preflight generation: {generation}")
    expected_ids = [f"E{index:04d}" for index in range(1, 28)]
    if evidence_ids(payloads) != expected_ids:
        raise SystemExit("E03 preflight requires the preserved E0001-E0027 ledger")
    generations = numbered_generations(ralph_root)
    if len(generations) != 26 or generations[-1] != generation:
        raise SystemExit("E03 preflight requires all 26 prior generations")
    return {
        "mode": "preflight",
        "generation": generation,
        "latest_evidence_id": "E0027",
        "retained_generation_count": len(generations),
        "commands_parsed": len(commands),
        "completion_ready": False,
    }


def run_core() -> dict[str, object]:
    run_preflight()
    ralph_root, parent, payloads = current_state()
    expected_ids = [f"E{index:04d}" for index in range(1, 28)]
    if evidence_ids(payloads) != expected_ids:
        raise SystemExit("E03 core seal requires the preserved E0001-E0027 ledger")
    before = numbered_generations(ralph_root)
    generation = invoke_ralph(core_summary())
    _, _, sealed = current_state()
    if evidence_ids(sealed) != [f"E{index:04d}" for index in range(1, 29)]:
        raise SystemExit("E03 core seal did not append exactly E0028")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("E03 core seal did not preserve every prior generation")
    return {
        "mode": "core",
        "parent_generation": parent,
        "generation": generation,
        "evidence_id": "E0028",
        "retained_generation_count": len(after),
        "completion_ready": False,
    }


def verify_report_artifact_hashes(report: dict[str, Any]) -> None:
    review = report.get("review")
    if not isinstance(review, dict) or review.get("artifact_sha256") != sha256(PACKAGE / "review.md"):
        raise SystemExit("E03 report review hash does not match final bytes")
    artifacts = report.get("verification_artifacts")
    if not isinstance(artifacts, list):
        raise SystemExit("E03 report verification_artifacts is not a list")
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise SystemExit("E03 report contains an invalid verification artifact")
        relative = artifact.get("path")
        expected = artifact.get("sha256")
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise SystemExit("E03 report contains an unsealed verification artifact")
        if sha256(ROOT / relative) != expected:
            raise SystemExit(f"E03 report artifact hash mismatch: {relative}")


def run_final() -> dict[str, object]:
    assert_core_hashes()
    ralph_root, parent, payloads = current_state()
    if not re.fullmatch(r"000027-[0-9a-f]{8}", parent):
        raise SystemExit(f"Unexpected E03 final parent generation: {parent}")
    if evidence_ids(payloads) != [f"E{index:04d}" for index in range(1, 29)]:
        raise SystemExit("E03 final seal requires the preserved E0001-E0028 ledger")
    ledger = payloads["evidence_ledger.json"]
    if ledger["entries"][-1].get("summary") != core_summary():
        raise SystemExit("E0028 does not match the E03 core evidence summary")

    report = read_json(PACKAGE / "report.json")
    rah_state = report.get("rah_state")
    if not isinstance(rah_state, dict):
        raise SystemExit("E03 report has no rah_state closeout record")
    if report.get("status") != "PASS" or report.get("package_status") != "PASS":
        raise SystemExit("E03 report is not PASS")
    if report.get("completion_ready") is not False:
        raise SystemExit("E03 report must keep completion_ready=false")
    if rah_state.get("core_generation") != parent:
        raise SystemExit("E03 report core_generation does not match RAH authority")
    if rah_state.get("core_evidence_id") != "E0028":
        raise SystemExit("E03 report does not bind core evidence E0028")
    if rah_state.get("final_closeout_evidence_id") != "E0029":
        raise SystemExit("E03 report does not reserve final evidence E0029")
    generation_manifest = ralph_root / "generations" / parent / "generation-manifest.json"
    if rah_state.get("core_generation_manifest_sha256") != sha256(generation_manifest):
        raise SystemExit("E03 report core generation manifest hash is incorrect")

    commands = read_commands()
    command_ids = {row["command_id"] for row in commands}
    required_command_ids = {
        "E03-0001-C025",
        "E03-0001-C026",
        "E03-0001-C027",
        "E03-0001-C028",
    }
    if not required_command_ids.issubset(command_ids):
        raise SystemExit("E03 core seal, integrity, inspect, and DAG commands are missing")

    dependency = read_json(PACKAGE / "dependency-status.json")
    expected_ready = ["E04", "G01", "K01", "A06"]
    if (
        dependency.get("status") != "PASS"
        or dependency.get("next_package") != "E04"
        or dependency.get("ready_packages_manifest_order") != expected_ready
    ):
        raise SystemExit("E03 dependency reconciliation does not select E04")
    core_integrity = read_json(PACKAGE / "rah-core-integrity.json")
    if (
        core_integrity.get("status") != "PASS"
        or core_integrity.get("latest_evidence_id") != "E0028"
        or core_integrity.get("current_generation") != parent
    ):
        raise SystemExit("E03 core RAH integrity evidence is not PASS")
    verify_report_artifact_hashes(report)

    closeout_hashes = {
        name: sha256(PACKAGE / name)
        for name in (
            "report.json",
            "review.md",
            "commands.jsonl",
            "e03-verification.json",
            "dependency-status.json",
            "rah-core-integrity.json",
            "e03-rah-seal.py",
        )
    }
    ready = "/".join(dependency["ready_packages_manifest_order"])
    summary = (
        "E03-0001 closeout is hash-sealed after core RAH generation "
        f"{parent}: report sha256:{closeout_hashes['report.json']}; review sha256:"
        f"{closeout_hashes['review.md']}; commands sha256:"
        f"{closeout_hashes['commands.jsonl']}; verification sha256:"
        f"{closeout_hashes['e03-verification.json']}; dependency status sha256:"
        f"{closeout_hashes['dependency-status.json']}; core RAH integrity sha256:"
        f"{closeout_hashes['rah-core-integrity.json']}; preservation wrapper sha256:"
        f"{closeout_hashes['e03-rah-seal.py']}. E03 package status PASS; blocking "
        "findings=0; all prior generations, reports, failed probes, residual failures, "
        "and dirty worktree remain preserved. The 156-package DAG has unknown "
        f"dependencies=0 and cycles=0; READY manifest order is {ready}; next package "
        "E04. completion_ready=false."
    )
    before = numbered_generations(ralph_root)
    generation = invoke_ralph(summary)
    _, _, sealed = current_state()
    if evidence_ids(sealed) != [f"E{index:04d}" for index in range(1, 30)]:
        raise SystemExit("E03 final seal did not append exactly E0029")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("E03 final seal did not preserve every prior generation")
    return {
        "mode": "final",
        "parent_generation": parent,
        "generation": generation,
        "evidence_id": "E0029",
        "artifact_hashes": closeout_hashes,
        "retained_generation_count": len(after),
        "completion_ready": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("preflight", "core", "final"))
    args = parser.parse_args()
    if args.mode == "preflight":
        result = run_preflight()
    elif args.mode == "core":
        result = run_core()
    else:
        result = run_final()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
