#!/usr/bin/env python3
"""Seal E02 evidence while retaining every historical RAH generation."""

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
PACKAGE = ROOT / "artifacts" / "work_packages" / "E02"
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


CORE_PARENT = "000024-b726715c"
CORE_SOURCE_HASHES = {
    "packages/foundry-kernel/src/effects/effect-coordinator.mjs": (
        "a4d2b9b851f9055869db842d10702e6017a61c18fcc637521fdec398b5abc1f2"
    ),
    "packages/foundry-kernel/src/effects/effect-test-support.mjs": (
        "df45bdec72a2ed2ffda922189e21f1102cc1cdcf2c50d661f9ac1e98051c0a4a"
    ),
    "packages/foundry-kernel/src/effects/effect-reconciliation.test.mjs": (
        "998a962b3e193e3b497aa60078f5f3d650332d88f973d81d3b167be025a13402"
    ),
    "packages/foundry-kernel/src/effects/idempotency.test.mjs": (
        "0d386c1eb2ded877423979838d604e1270ec4112b82f162d2d2222924fda5dec"
    ),
    "artifacts/work_packages/E02/review.md": (
        "70f02559453c7b43a4ff14d84bdf82d2f707e391616cd87d90249d21fcf6c1bb"
    ),
    "artifacts/work_packages/E02/e02-verification.json": (
        "a4d5ad7662aad057064e42c5ae3b31d908e688636b28da92c30d19a880927f3c"
    ),
    "artifacts/work_packages/E01/report.json": (
        "beddc2a3019fcf680435ea6d5f907b5e7b50b0fa8a384673917c6198f49f32e1"
    ),
    "schemas/action-intent.schema.json": (
        "acaf9861436d3217c579f7eed518f2f138261a4a8cc1cb750c97a52ad908b0b1"
    ),
    "schemas/effect-receipt.schema.json": (
        "2fc5f33eaea8dd86ebbdb59c2c9d6075d4b2d7c9f03bab304c550dfd80d1a4cc"
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
                f"E02 source/dependency hash mismatch for {relative}: {actual} != {expected}"
            )
    review = (PACKAGE / "review.md").read_text(encoding="utf-8")
    normalized_review = " ".join(review.split())
    if "PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_ADVERSARIAL_REVIEW" not in review:
        raise SystemExit("E02 review does not record the authorized PASS status")
    if "not external actor-independent certification" not in normalized_review:
        raise SystemExit("E02 review omits the assurance limitation")
    if "blocking findings: 0" not in review:
        raise SystemExit("E02 review has unresolved blocking findings")
    verification = json.loads((PACKAGE / "e02-verification.json").read_text(encoding="utf-8"))
    if verification.get("status") != "PASS":
        raise SystemExit("E02 verification artifact is not PASS")


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
        raise SystemExit("E02 cannot seal an already completion-ready goal")
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
        "E02-0001 PASS core: ActionIntent and EffectReceipt are canonical-hash "
        "verified; Attempt is a private D01 projection. Immutable operation journal "
        "and idempotency bindings serialize same-key and same-attempt races, while "
        "UNKNOWN or missing receipts block retry until evidence-bound reconciliation. "
        "D01 commit, D03/E01 publication, and the D01 publication checkpoint form a "
        "replayable outbox boundary; narrative results, missing receipts, unconfirmed "
        "ledger events, external-operation IDs alone, or unverified artifacts cannot "
        "prove completion. Final hashes: coordinator sha256:"
        f"{CORE_SOURCE_HASHES['packages/foundry-kernel/src/effects/effect-coordinator.mjs']}; "
        "reconciliation tests sha256:"
        f"{CORE_SOURCE_HASHES['packages/foundry-kernel/src/effects/effect-reconciliation.test.mjs']}; "
        "idempotency tests sha256:"
        f"{CORE_SOURCE_HASHES['packages/foundry-kernel/src/effects/idempotency.test.mjs']}; "
        "verification sha256:"
        f"{CORE_SOURCE_HASHES['artifacts/work_packages/E02/e02-verification.json']}; "
        "review sha256:"
        f"{CORE_SOURCE_HASHES['artifacts/work_packages/E02/review.md']}. Required checks "
        "pass 19/19, five repeats pass 95/95, Python passes 913/913, and blocking "
        "findings=0. Final repository-wide Node passes 189/190 with only existing "
        "S04-TM004; the earlier D03 Windows EPERM observation and existing double-build "
        "staged scripts omission remain preserved outside E02. completion_ready=false."
    )


def run_core() -> dict[str, object]:
    assert_core_hashes()
    ralph_root, parent, payloads = current_state()
    if parent != CORE_PARENT:
        raise SystemExit(f"Unexpected E02 core parent {parent}; expected {CORE_PARENT}")
    expected_ids = [f"E{index:04d}" for index in range(1, 26)]
    if evidence_ids(payloads) != expected_ids:
        raise SystemExit("E02 core seal requires the preserved E0001-E0025 ledger")
    before = numbered_generations(ralph_root)
    if len(before) != 24 or before[-1] != parent:
        raise SystemExit("E02 core seal requires all 24 prior generations")
    generation = invoke_ralph(core_summary())
    _, _, sealed = current_state()
    if evidence_ids(sealed) != [f"E{index:04d}" for index in range(1, 27)]:
        raise SystemExit("E02 core seal did not append exactly E0026")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("E02 core seal did not preserve every prior generation")
    return {
        "mode": "core",
        "parent_generation": parent,
        "generation": generation,
        "evidence_id": "E0026",
        "retained_generation_count": len(after),
        "completion_ready": False,
    }


def run_final() -> dict[str, object]:
    assert_core_hashes()
    ralph_root, parent, payloads = current_state()
    if not re.fullmatch(r"000025-[0-9a-f]{8}", parent):
        raise SystemExit(f"Unexpected E02 final parent generation: {parent}")
    if evidence_ids(payloads) != [f"E{index:04d}" for index in range(1, 27)]:
        raise SystemExit("E02 final seal requires the preserved E0001-E0026 ledger")
    ledger = payloads["evidence_ledger.json"]
    if ledger["entries"][-1].get("summary") != core_summary():
        raise SystemExit("E0026 does not match the E02 core evidence summary")

    report = json.loads((PACKAGE / "report.json").read_text(encoding="utf-8"))
    rah_state = report.get("rah_state")
    if not isinstance(rah_state, dict):
        raise SystemExit("E02 report has no rah_state closeout record")
    if report.get("status") != "PASS" or report.get("package_status") != "PASS":
        raise SystemExit("E02 report is not PASS")
    if report.get("completion_ready") is not False:
        raise SystemExit("E02 report must keep completion_ready=false")
    if rah_state.get("core_generation") != parent:
        raise SystemExit("E02 report core_generation does not match RAH authority")
    if rah_state.get("core_evidence_id") != "E0026":
        raise SystemExit("E02 report does not bind core evidence E0026")
    if rah_state.get("final_closeout_evidence_id") != "E0027":
        raise SystemExit("E02 report does not reserve final evidence E0027")

    commands = [
        json.loads(raw)
        for raw in (PACKAGE / "commands.jsonl").read_text(encoding="utf-8").splitlines()
        if raw.strip()
    ]
    command_ids = [row.get("command_id") for row in commands]
    if len(command_ids) != len(set(command_ids)):
        raise SystemExit("E02 commands.jsonl has duplicate command IDs")
    required_command_ids = {
        "E02-0001-C027",
        "E02-0001-C028",
        "E02-0001-C029",
        "E02-0001-C030",
    }
    if not required_command_ids.issubset(command_ids):
        raise SystemExit("E02 core seal, integrity, inspect, and DAG commands are missing")

    dependency = json.loads(
        (PACKAGE / "dependency-status.json").read_text(encoding="utf-8")
    )
    if dependency.get("status") != "PASS" or dependency.get("next_package") != "E03":
        raise SystemExit("E02 dependency reconciliation does not select E03")
    core_integrity = json.loads(
        (PACKAGE / "rah-core-integrity.json").read_text(encoding="utf-8")
    )
    if (
        core_integrity.get("status") != "PASS"
        or core_integrity.get("latest_evidence_id") != "E0026"
    ):
        raise SystemExit("E02 core RAH integrity evidence is not PASS")

    closeout_hashes = {
        name: sha256(PACKAGE / name)
        for name in (
            "report.json",
            "review.md",
            "commands.jsonl",
            "e02-verification.json",
            "dependency-status.json",
            "rah-core-integrity.json",
            "e02-rah-seal.py",
        )
    }
    ready = "/".join(dependency["ready_packages_manifest_order"])
    summary = (
        "E02-0001 closeout is hash-sealed after core RAH generation "
        f"{parent}: report sha256:{closeout_hashes['report.json']}; review sha256:"
        f"{closeout_hashes['review.md']}; commands sha256:"
        f"{closeout_hashes['commands.jsonl']}; verification sha256:"
        f"{closeout_hashes['e02-verification.json']}; dependency status sha256:"
        f"{closeout_hashes['dependency-status.json']}; core RAH integrity sha256:"
        f"{closeout_hashes['rah-core-integrity.json']}; preservation wrapper sha256:"
        f"{closeout_hashes['e02-rah-seal.py']}. E02 package status PASS; blocking "
        "findings=0; all prior generations, reports, failed and intermittent probes, "
        "and dirty worktree remain preserved. The 156-package DAG has unknown "
        f"dependencies=0 and cycles=0; READY manifest order is {ready}; next package "
        "E03. completion_ready=false."
    )
    before = numbered_generations(ralph_root)
    generation = invoke_ralph(summary)
    _, _, sealed = current_state()
    if evidence_ids(sealed) != [f"E{index:04d}" for index in range(1, 28)]:
        raise SystemExit("E02 final seal did not append exactly E0027")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("E02 final seal did not preserve every prior generation")
    return {
        "mode": "final",
        "parent_generation": parent,
        "generation": generation,
        "evidence_id": "E0027",
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
