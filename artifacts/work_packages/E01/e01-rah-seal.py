#!/usr/bin/env python3
"""Seal E01 evidence while retaining every historical RAH generation."""

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
PACKAGE = ROOT / "artifacts" / "work_packages" / "E01"
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


CORE_PARENT = "000022-edf53874"
CORE_SOURCE_HASHES = {
    "packages/foundry-kernel/src/ledger/noetic-ledger.mjs": (
        "58ea9dc0d52d9c20720b33970ee3b8d8d05703ba7dd0fb4f51a483d9f505f1ed"
    ),
    "packages/foundry-kernel/src/ledger/ledger-test-support.mjs": (
        "4954d4dd7bc985136d744f0689b91316419fb376e842dba2a428c66c9813d6e9"
    ),
    "packages/foundry-kernel/src/ledger/ledger-hash-chain.test.mjs": (
        "e478e71b48d74a139a10023033b3fd2d73fcbdf92660feeb920a6c3953e4eb82"
    ),
    "packages/foundry-kernel/src/ledger/reducer-replay.test.mjs": (
        "a1f9848e08c1231de29ada86236b6a1ffef19d867ce412d16737a8ce44222029"
    ),
    "artifacts/work_packages/E01/review.md": (
        "41c9f3633a3db7e97c80f7e31a6febfd912822232a0d706ca3aa5f517a9d392a"
    ),
    "artifacts/work_packages/E01/e01-verification.json": (
        "404d7c10ddce5dde2925efc0b6b6c2c0f862763ad64661181a32cf96eb6982bf"
    ),
    "artifacts/work_packages/C04/report.json": (
        "eca4fdd3f10537a2fb5c39643f4dee52bab9bcf5b95f9468ddcd470ffd98592f"
    ),
    "artifacts/work_packages/D04/report.json": (
        "b47c194e230f4b08ab96b6153e9fc0e170eafb1054318cfaedd8e1ddeb4c5fde"
    ),
    "schemas/event-record.schema.json": (
        "538cf66a8d006aa6895dc52fc0761747c9b18bba7ea857eda4f8385364880588"
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
                f"E01 source/dependency hash mismatch for {relative}: {actual} != {expected}"
            )
    review = (PACKAGE / "review.md").read_text(encoding="utf-8")
    normalized_review = " ".join(review.split())
    if "PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_ADVERSARIAL_REVIEW" not in review:
        raise SystemExit("E01 review does not record the authorized PASS status")
    if "not external actor-independent certification" not in normalized_review:
        raise SystemExit("E01 review omits the assurance limitation")
    if "blocking findings: 0" not in review:
        raise SystemExit("E01 review has unresolved blocking findings")
    verification = json.loads((PACKAGE / "e01-verification.json").read_text(encoding="utf-8"))
    if verification.get("status") != "PASS":
        raise SystemExit("E01 verification artifact is not PASS")


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
        raise SystemExit("E01 cannot seal an already completion-ready goal")
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
        "E01-0001 PASS core: the append-only Noetic Ledger stores immutable "
        "revision-zero EventRecords and a revisioned per-run stream in one D01 "
        "transaction, owns contiguous sequence, binds exact D03 payload bytes, and "
        "verifies canonical event hashes, previous links, identities, counts, and "
        "tail reconciliation. Deterministic rebuild performs two isolated reducer "
        "passes over verified events and rejects async, mutating, non-JSON, or "
        "divergent reducers. Final hashes: ledger sha256:"
        f"{CORE_SOURCE_HASHES['packages/foundry-kernel/src/ledger/noetic-ledger.mjs']}; "
        "hash-chain tests sha256:"
        f"{CORE_SOURCE_HASHES['packages/foundry-kernel/src/ledger/ledger-hash-chain.test.mjs']}; "
        "replay tests sha256:"
        f"{CORE_SOURCE_HASHES['packages/foundry-kernel/src/ledger/reducer-replay.test.mjs']}; "
        "verification sha256:"
        f"{CORE_SOURCE_HASHES['artifacts/work_packages/E01/e01-verification.json']}; "
        "review sha256:"
        f"{CORE_SOURCE_HASHES['artifacts/work_packages/E01/review.md']}. Required "
        "checks pass 21/21, ten repeats pass 210/210, Python passes 913/913, "
        "and blocking findings=0. Repository-wide Node retains only existing "
        "S04-TM004 and double-build retains the existing staged scripts omission, "
        "both outside E01. Reducer side effects are not sandboxed. "
        "completion_ready=false."
    )


def run_core() -> dict[str, object]:
    assert_core_hashes()
    ralph_root, parent, payloads = current_state()
    if parent != CORE_PARENT:
        raise SystemExit(f"Unexpected E01 core parent {parent}; expected {CORE_PARENT}")
    expected_ids = [f"E{index:04d}" for index in range(1, 24)]
    if evidence_ids(payloads) != expected_ids:
        raise SystemExit("E01 core seal requires the preserved E0001-E0023 ledger")
    before = numbered_generations(ralph_root)
    if len(before) != 22 or before[-1] != parent:
        raise SystemExit("E01 core seal requires all 22 prior generations")
    generation = invoke_ralph(core_summary())
    _, _, sealed = current_state()
    if evidence_ids(sealed) != [f"E{index:04d}" for index in range(1, 25)]:
        raise SystemExit("E01 core seal did not append exactly E0024")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("E01 core seal did not preserve every prior generation")
    return {
        "mode": "core",
        "parent_generation": parent,
        "generation": generation,
        "evidence_id": "E0024",
        "retained_generation_count": len(after),
        "completion_ready": False,
    }


def run_final() -> dict[str, object]:
    assert_core_hashes()
    ralph_root, parent, payloads = current_state()
    if not re.fullmatch(r"000023-[0-9a-f]{8}", parent):
        raise SystemExit(f"Unexpected E01 final parent generation: {parent}")
    if evidence_ids(payloads) != [f"E{index:04d}" for index in range(1, 25)]:
        raise SystemExit("E01 final seal requires the preserved E0001-E0024 ledger")
    ledger = payloads["evidence_ledger.json"]
    if ledger["entries"][-1].get("summary") != core_summary():
        raise SystemExit("E0024 does not match the E01 core evidence summary")

    report = json.loads((PACKAGE / "report.json").read_text(encoding="utf-8"))
    rah_state = report.get("rah_state")
    if not isinstance(rah_state, dict):
        raise SystemExit("E01 report has no rah_state closeout record")
    if report.get("status") != "PASS" or report.get("package_status") != "PASS":
        raise SystemExit("E01 report is not PASS")
    if report.get("completion_ready") is not False:
        raise SystemExit("E01 report must keep completion_ready=false")
    if rah_state.get("core_generation") != parent:
        raise SystemExit("E01 report core_generation does not match RAH authority")
    if rah_state.get("core_evidence_id") != "E0024":
        raise SystemExit("E01 report does not bind core evidence E0024")
    if rah_state.get("final_closeout_evidence_id") != "E0025":
        raise SystemExit("E01 report does not reserve final evidence E0025")

    commands = [
        json.loads(raw)
        for raw in (PACKAGE / "commands.jsonl").read_text(encoding="utf-8").splitlines()
        if raw.strip()
    ]
    command_ids = [row.get("command_id") for row in commands]
    if len(command_ids) != len(set(command_ids)):
        raise SystemExit("E01 commands.jsonl has duplicate command IDs")
    required_command_ids = {
        "E01-0001-C025",
        "E01-0001-C026",
        "E01-0001-C027",
        "E01-0001-C028",
    }
    if not required_command_ids.issubset(command_ids):
        raise SystemExit("E01 core seal, integrity, inspect, and DAG commands are missing")

    dependency = json.loads(
        (PACKAGE / "dependency-status.json").read_text(encoding="utf-8")
    )
    if dependency.get("status") != "PASS" or dependency.get("next_package") != "E02":
        raise SystemExit("E01 dependency reconciliation does not select E02")
    core_integrity = json.loads(
        (PACKAGE / "rah-core-integrity.json").read_text(encoding="utf-8")
    )
    if (
        core_integrity.get("status") != "PASS"
        or core_integrity.get("latest_evidence_id") != "E0024"
    ):
        raise SystemExit("E01 core RAH integrity evidence is not PASS")

    closeout_hashes = {
        name: sha256(PACKAGE / name)
        for name in (
            "report.json",
            "review.md",
            "commands.jsonl",
            "e01-verification.json",
            "dependency-status.json",
            "rah-core-integrity.json",
            "e01-rah-seal.py",
        )
    }
    ready = "/".join(dependency["ready_packages_manifest_order"])
    summary = (
        "E01-0001 closeout is hash-sealed after core RAH generation "
        f"{parent}: report sha256:{closeout_hashes['report.json']}; review sha256:"
        f"{closeout_hashes['review.md']}; commands sha256:"
        f"{closeout_hashes['commands.jsonl']}; verification sha256:"
        f"{closeout_hashes['e01-verification.json']}; dependency status sha256:"
        f"{closeout_hashes['dependency-status.json']}; core RAH integrity sha256:"
        f"{closeout_hashes['rah-core-integrity.json']}; preservation wrapper sha256:"
        f"{closeout_hashes['e01-rah-seal.py']}. E01 package status PASS; blocking "
        "findings=0; all prior generations, reports, failed probes, and dirty "
        "worktree remain preserved. The 156-package DAG has unknown dependencies=0 "
        f"and cycles=0; READY manifest order is {ready}; next package E02. "
        "completion_ready=false."
    )
    before = numbered_generations(ralph_root)
    generation = invoke_ralph(summary)
    _, _, sealed = current_state()
    if evidence_ids(sealed) != [f"E{index:04d}" for index in range(1, 26)]:
        raise SystemExit("E01 final seal did not append exactly E0025")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("E01 final seal did not preserve every prior generation")
    return {
        "mode": "final",
        "parent_generation": parent,
        "generation": generation,
        "evidence_id": "E0025",
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
