#!/usr/bin/env python3
"""Seal C01-0004 evidence without pruning retained RAH generations.

The product-owner decisions require every prior RAH generation to remain
available.  The generic state store keeps three generations by default, so
this package-local wrapper raises the retention limit only for the two C01
closeout commits.  Both modes validate their exact parent state and artifact
hashes before delegating the state transition to the canonical RAH harness.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts" / "work_packages" / "C01" / "attempts" / "0004"
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


CORE_PARENT = "000004-d7a75c37"
CORE_SUMMARY = (
    "C01-0004 PASS is limited to the canonical-contract package under "
    "HD-EF4-C01-SG003-20260728-001: 124 schemas and 124 examples validate, "
    "OpenAPI 3.1.1 has 33 unique operations, and 71 targeted tests pass. "
    "Deterministic verification sha256:"
    "c60a154ff342a802de5f8333b3cbad8bdfdc4c15a4f6c735a51c47e0ef7abc64; "
    "runtime migration impact sha256:"
    "3c35cc5cfe003055f2e039a4837e74527a843c4ed6795eee1d28b56954d36877. "
    "The full suite remains 831 passed and the exact 24 expected C03-owned "
    "migration failures; completion_ready=false and C02 is next."
)

EXPECTED_STABLE_HASHES = {
    "c01-contract-verification.json": (
        "c60a154ff342a802de5f8333b3cbad8bdfdc4c15a4f6c735a51c47e0ef7abc64"
    ),
    "runtime-migration-impact.json": (
        "3c35cc5cfe003055f2e039a4837e74527a843c4ed6795eee1d28b56954d36877"
    ),
    "review.md": "0ef71039bd87cf04c4dc6fcf127f61b18b8e9482483d50ce87e3f00cbce6a2bc",
    "targeted-contracts.junit.xml": (
        "cd9b7bddd532e924ec56c8f54ae30582e88007ce8f82a9332d5dcab656e90ddc"
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


def assert_hashes(expected: dict[str, str]) -> None:
    for relative, digest in expected.items():
        actual = sha256(ATTEMPT / relative)
        if actual != digest:
            raise SystemExit(
                f"Artifact hash mismatch for {relative}: {actual} != {digest}"
            )


def current_state() -> tuple[Path, str, dict[str, object]]:
    ralph_root = ROOT / ".rah" / "ralph"
    current = state_store.read_current(ralph_root)
    if current is None:
        raise SystemExit("No committed RAH generation")
    generation, payloads = current
    verified = state_store.verify_current(ralph_root)
    if verified.get("generation") != generation:
        raise SystemExit("RAH generation verification disagrees with current pointer")
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
    # The explicit product-owner preservation rule overrides the generic
    # three-generation housekeeping limit for this closeout only.
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
        raise SystemExit("Committed RAH generation is not retained")
    return generation


def run_core() -> dict[str, object]:
    assert_hashes(EXPECTED_STABLE_HASHES)
    ralph_root, parent, payloads = current_state()
    if parent != CORE_PARENT:
        raise SystemExit(f"Unexpected core parent {parent}; expected {CORE_PARENT}")
    if evidence_ids(payloads) != [f"E{index:04d}" for index in range(1, 6)]:
        raise SystemExit("Core seal requires the preserved E0001-E0005 ledger")
    before = numbered_generations(ralph_root)
    generation = invoke_ralph(CORE_SUMMARY)
    _, _, sealed = current_state()
    if evidence_ids(sealed) != [f"E{index:04d}" for index in range(1, 7)]:
        raise SystemExit("Core seal did not append exactly E0006")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("Core seal did not preserve every prior generation")
    return {
        "mode": "core",
        "parent_generation": parent,
        "generation": generation,
        "evidence_id": "E0006",
        "retained_generations": after,
        "completion_ready": sealed["loop_state.json"]["completion_readiness"][
            "ready"
        ],
    }


def run_final() -> dict[str, object]:
    assert_hashes(EXPECTED_STABLE_HASHES)
    ralph_root, parent, payloads = current_state()
    if not re.fullmatch(r"000005-[0-9a-f]{8}", parent):
        raise SystemExit(f"Unexpected final-seal parent generation: {parent}")
    ids = evidence_ids(payloads)
    if ids != [f"E{index:04d}" for index in range(1, 7)]:
        raise SystemExit("Final seal requires the preserved E0001-E0006 ledger")
    ledger = payloads["evidence_ledger.json"]
    if ledger["entries"][-1].get("summary") != CORE_SUMMARY:
        raise SystemExit("E0006 does not match the C01 core evidence summary")

    report = json.loads((ATTEMPT / "report.json").read_text(encoding="utf-8"))
    rah_state = report.get("rah_state")
    if not isinstance(rah_state, dict):
        raise SystemExit("C01 report has no rah_state closeout record")
    if rah_state.get("core_generation") != parent:
        raise SystemExit("C01 report core_generation does not match RAH authority")
    if rah_state.get("core_evidence_id") != "E0006":
        raise SystemExit("C01 report does not bind the core evidence ID")
    if rah_state.get("final_closeout_evidence_id") != "E0007":
        raise SystemExit("C01 report does not reserve the final closeout evidence ID")

    commands = []
    for raw in (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8").splitlines():
        if raw.strip():
            commands.append(json.loads(raw))
    command_ids = [row.get("command_id") for row in commands]
    if len(command_ids) != len(set(command_ids)):
        raise SystemExit("C01 commands.jsonl has duplicate command IDs")
    if command_ids[-2:] != ["C01-0004-C016", "C01-0004-C017"]:
        raise SystemExit("C01 core RAH append and verification commands are missing")

    closeout_hashes = {
        name: sha256(ATTEMPT / name)
        for name in (
            "report.json",
            "review.md",
            "commands.jsonl",
            "dependency-status.json",
            "c01-rah-seal.py",
        )
    }
    summary = (
        "C01-0004 closeout artifacts are hash-sealed after core RAH generation "
        f"{parent}: report sha256:{closeout_hashes['report.json']}; review sha256:"
        f"{closeout_hashes['review.md']}; commands sha256:"
        f"{closeout_hashes['commands.jsonl']}; dependency status sha256:"
        f"{closeout_hashes['dependency-status.json']}; preservation wrapper sha256:"
        f"{closeout_hashes['c01-rah-seal.py']}. C01=PASS, C02=READY, all prior "
        "generations and SPEC_GAP history remain retained, and "
        "completion_ready=false."
    )
    before = numbered_generations(ralph_root)
    generation = invoke_ralph(summary)
    _, _, sealed = current_state()
    if evidence_ids(sealed) != [f"E{index:04d}" for index in range(1, 8)]:
        raise SystemExit("Final seal did not append exactly E0007")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("Final seal did not preserve every prior generation")
    if sealed["loop_state.json"]["completion_readiness"]["ready"]:
        raise SystemExit("C01 closeout must not make the overall goal ready")
    return {
        "mode": "final",
        "parent_generation": parent,
        "generation": generation,
        "evidence_id": "E0007",
        "artifact_hashes": closeout_hashes,
        "retained_generations": after,
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
