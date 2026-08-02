#!/usr/bin/env python3
"""Seal E04 evidence while retaining every historical RAH generation."""

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
PACKAGE = ROOT / "artifacts" / "work_packages" / "E04"
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


CORE_PARENT = "000028-2f543628"
CORE_SOURCE_HASHES = {
    "tests/replay/effects/replay-test-support.mjs": (
        "da299cd4d9fd44a30d4851be3c4f7ac5104aadb94de57fe525cb2b1c8a98ca4b"
    ),
    "tests/replay/effects/strict-replay.test.mjs": (
        "b4d930073c16169139ae480a9fca549f6216a538adce5dec5c7da11f3f35adc1"
    ),
    "tests/replay/effects/semantic-replay.test.mjs": (
        "bfb99786cdc201c486fb710ffa973d2c0a241af4e53fb6be2cbb6a0587b036ed"
    ),
    "artifacts/work_packages/E04/review.md": (
        "18cda4135b66486a91151f3c15b68ed90bbcef44d00663b6433dc9341162ef78"
    ),
    "artifacts/work_packages/E04/e04-verification.json": (
        "37e9a9367a6c1bfaf75c2c0e3d93498631e2ff47a9beaebec18d1050738b13dd"
    ),
    "artifacts/work_packages/E02/report.json": (
        "97a308d90bd0f57334a5d9505e672d402b0409adcb17547780b2803f9c417772"
    ),
    "artifacts/work_packages/E03/report.json": (
        "e4737460f2375d46d4b348d79cdfa5c51ee84f1db2bcf34b8a3f5aea1d0091d2"
    ),
    "schemas/replay-report.schema.json": (
        "6828658341f34f5ebf7dee947b3483f79440d68c48b91aa1cae689cbcbd7b798"
    ),
    "packages/foundry-kernel/src/ledger/noetic-ledger.mjs": (
        "58ea9dc0d52d9c20720b33970ee3b8d8d05703ba7dd0fb4f51a483d9f505f1ed"
    ),
    "packages/foundry-kernel/src/effects/effect-coordinator.mjs": (
        "a4d2b9b851f9055869db842d10702e6017a61c18fcc637521fdec398b5abc1f2"
    ),
    "packages/foundry-kernel/src/capabilities/capability-authority.mjs": (
        "a8e3376568350229ca1a997aafbc1c4c138f2f01fbee945c916d390283a3720a"
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
        raise SystemExit(f"cannot read E04 commands: {error}")
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
        raise SystemExit("E04 commands.jsonl has missing or duplicate command IDs")
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
                f"E04 source/dependency hash mismatch for {relative}: {actual} != {expected}"
            )
    review = (PACKAGE / "review.md").read_text(encoding="utf-8")
    normalized_review = " ".join(review.split())
    if "PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_ADVERSARIAL_REVIEW" not in review:
        raise SystemExit("E04 review does not record the authorized PASS status")
    if "not external actor-independent certification" not in normalized_review:
        raise SystemExit("E04 review omits the assurance limitation")
    if "blocking findings: 0" not in review:
        raise SystemExit("E04 review has unresolved blocking findings")
    verification = read_json(PACKAGE / "e04-verification.json")
    if verification.get("status") != "PASS":
        raise SystemExit("E04 verification artifact is not PASS")


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
        raise SystemExit("E04 cannot seal an already completion-ready goal")
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
        "E04-0001 PASS core: the deterministic E-phase reducer rebuilds the exact "
        "E02 intent/attempt/receipt and E03 approval/lease/use/revocation stream, "
        "matches live dependency projections, remains identical across repeated and "
        "reopened-store rebuilds, and rejects missing or tampered payloads, duplicate "
        "logical identities, and event-envelope rebinding. Strict EXACT requires the "
        "same run, all eight exact pins, and non-vacuous event-count/state-hash/tail-"
        "hash identity. Semantic replay distinguishes SEMANTICALLY_EQUIVALENT, DRIFT, "
        "and NOT_COMPARABLE while retaining source and replay pin provenance. Reports "
        "are canonical, self-hash verified, and ReplayReport-schema valid. Final "
        "hashes: support sha256:"
        f"{CORE_SOURCE_HASHES['tests/replay/effects/replay-test-support.mjs']}; strict "
        "tests sha256:"
        f"{CORE_SOURCE_HASHES['tests/replay/effects/strict-replay.test.mjs']}; semantic "
        "tests sha256:"
        f"{CORE_SOURCE_HASHES['tests/replay/effects/semantic-replay.test.mjs']}; "
        "verification sha256:"
        f"{CORE_SOURCE_HASHES['artifacts/work_packages/E04/e04-verification.json']}; "
        "review sha256:"
        f"{CORE_SOURCE_HASHES['artifacts/work_packages/E04/review.md']}. Required checks "
        "pass 18/18, five repeats pass 90/90, Python passes 913/913, and blocking "
        "findings=0. Repository-wide Node passes 237/238 with only existing S04-TM004; "
        "the existing double-build staged scripts omission remains outside E04. "
        "completion_ready=false."
    )


def run_preflight() -> dict[str, object]:
    assert_core_hashes()
    report = read_json(PACKAGE / "report.json")
    if report.get("status") != "PASS" or report.get("completion_ready") is not False:
        raise SystemExit("E04 report is not a non-terminal PASS candidate")
    verify_report_artifact_hashes(report)
    commands = read_commands()
    required = {"E04-0001-C023", "E04-0001-C024"}
    if not required.issubset({row["command_id"] for row in commands}):
        raise SystemExit("E04 construction/preflight command records are missing")
    for name in ("e04-rah-integrity.py", "e04-dag-reconciliation.py", "e04-rah-seal.py"):
        if not (PACKAGE / name).is_file():
            raise SystemExit(f"E04 evidence script is missing: {name}")

    ralph_root, generation, payloads = current_state()
    if generation != CORE_PARENT:
        raise SystemExit(f"Unexpected E04 preflight generation: {generation}")
    expected_ids = [f"E{index:04d}" for index in range(1, 30)]
    if evidence_ids(payloads) != expected_ids:
        raise SystemExit("E04 preflight requires the preserved E0001-E0029 ledger")
    generations = numbered_generations(ralph_root)
    if len(generations) != 28 or generations[-1] != generation:
        raise SystemExit("E04 preflight requires all 28 prior generations")
    return {
        "mode": "preflight",
        "generation": generation,
        "latest_evidence_id": "E0029",
        "retained_generation_count": len(generations),
        "commands_parsed": len(commands),
        "completion_ready": False,
    }


def run_core() -> dict[str, object]:
    run_preflight()
    ralph_root, parent, payloads = current_state()
    expected_ids = [f"E{index:04d}" for index in range(1, 30)]
    if evidence_ids(payloads) != expected_ids:
        raise SystemExit("E04 core seal requires the preserved E0001-E0029 ledger")
    before = numbered_generations(ralph_root)
    generation = invoke_ralph(core_summary())
    _, _, sealed = current_state()
    if evidence_ids(sealed) != [f"E{index:04d}" for index in range(1, 31)]:
        raise SystemExit("E04 core seal did not append exactly E0030")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("E04 core seal did not preserve every prior generation")
    return {
        "mode": "core",
        "parent_generation": parent,
        "generation": generation,
        "evidence_id": "E0030",
        "retained_generation_count": len(after),
        "completion_ready": False,
    }


def verify_report_artifact_hashes(report: dict[str, Any]) -> None:
    review = report.get("review")
    if not isinstance(review, dict) or review.get("artifact_sha256") != sha256(PACKAGE / "review.md"):
        raise SystemExit("E04 report review hash does not match final bytes")
    artifacts = report.get("verification_artifacts")
    if not isinstance(artifacts, list):
        raise SystemExit("E04 report verification_artifacts is not a list")
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise SystemExit("E04 report contains an invalid verification artifact")
        relative = artifact.get("path")
        expected = artifact.get("sha256")
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise SystemExit("E04 report contains an unsealed verification artifact")
        if sha256(ROOT / relative) != expected:
            raise SystemExit(f"E04 report artifact hash mismatch: {relative}")


def run_final() -> dict[str, object]:
    assert_core_hashes()
    ralph_root, parent, payloads = current_state()
    if not re.fullmatch(r"000029-[0-9a-f]{8}", parent):
        raise SystemExit(f"Unexpected E04 final parent generation: {parent}")
    if evidence_ids(payloads) != [f"E{index:04d}" for index in range(1, 31)]:
        raise SystemExit("E04 final seal requires the preserved E0001-E0030 ledger")
    ledger = payloads["evidence_ledger.json"]
    if ledger["entries"][-1].get("summary") != core_summary():
        raise SystemExit("E0030 does not match the E04 core evidence summary")

    report = read_json(PACKAGE / "report.json")
    rah_state = report.get("rah_state")
    if not isinstance(rah_state, dict):
        raise SystemExit("E04 report has no rah_state closeout record")
    if report.get("status") != "PASS" or report.get("package_status") != "PASS":
        raise SystemExit("E04 report is not PASS")
    if report.get("completion_ready") is not False:
        raise SystemExit("E04 report must keep completion_ready=false")
    if rah_state.get("core_generation") != parent:
        raise SystemExit("E04 report core_generation does not match RAH authority")
    if rah_state.get("core_evidence_id") != "E0030":
        raise SystemExit("E04 report does not bind core evidence E0030")
    if rah_state.get("final_closeout_evidence_id") != "E0031":
        raise SystemExit("E04 report does not reserve final evidence E0031")
    generation_manifest = ralph_root / "generations" / parent / "generation-manifest.json"
    if rah_state.get("core_generation_manifest_sha256") != sha256(generation_manifest):
        raise SystemExit("E04 report core generation manifest hash is incorrect")

    commands = read_commands()
    command_ids = {row["command_id"] for row in commands}
    required_command_ids = {
        "E04-0001-C025",
        "E04-0001-C026",
        "E04-0001-C027",
        "E04-0001-C028",
    }
    if not required_command_ids.issubset(command_ids):
        raise SystemExit("E04 core seal, integrity, inspect, and DAG commands are missing")

    dependency = read_json(PACKAGE / "dependency-status.json")
    expected_ready = ["F01", "G01", "K01", "A06"]
    if (
        dependency.get("status") != "PASS"
        or dependency.get("next_package") != "F01"
        or dependency.get("ready_packages_manifest_order") != expected_ready
    ):
        raise SystemExit("E04 dependency reconciliation does not select F01")
    core_integrity = read_json(PACKAGE / "rah-core-integrity.json")
    if (
        core_integrity.get("status") != "PASS"
        or core_integrity.get("latest_evidence_id") != "E0030"
        or core_integrity.get("current_generation") != parent
    ):
        raise SystemExit("E04 core RAH integrity evidence is not PASS")
    verify_report_artifact_hashes(report)

    closeout_hashes = {
        name: sha256(PACKAGE / name)
        for name in (
            "report.json",
            "review.md",
            "commands.jsonl",
            "e04-verification.json",
            "dependency-status.json",
            "rah-core-integrity.json",
            "e04-rah-seal.py",
        )
    }
    ready = "/".join(dependency["ready_packages_manifest_order"])
    summary = (
        "E04-0001 closeout is hash-sealed after core RAH generation "
        f"{parent}: report sha256:{closeout_hashes['report.json']}; review sha256:"
        f"{closeout_hashes['review.md']}; commands sha256:"
        f"{closeout_hashes['commands.jsonl']}; verification sha256:"
        f"{closeout_hashes['e04-verification.json']}; dependency status sha256:"
        f"{closeout_hashes['dependency-status.json']}; core RAH integrity sha256:"
        f"{closeout_hashes['rah-core-integrity.json']}; preservation wrapper sha256:"
        f"{closeout_hashes['e04-rah-seal.py']}. E04 package status PASS; blocking "
        "findings=0; all prior generations, reports, failed probes, residual failures, "
        "and dirty worktree remain preserved. The 156-package DAG has unknown "
        f"dependencies=0 and cycles=0; READY manifest order is {ready}; next package "
        "F01. completion_ready=false."
    )
    before = numbered_generations(ralph_root)
    generation = invoke_ralph(summary)
    _, _, sealed = current_state()
    if evidence_ids(sealed) != [f"E{index:04d}" for index in range(1, 32)]:
        raise SystemExit("E04 final seal did not append exactly E0031")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("E04 final seal did not preserve every prior generation")
    return {
        "mode": "final",
        "parent_generation": parent,
        "generation": generation,
        "evidence_id": "E0031",
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
