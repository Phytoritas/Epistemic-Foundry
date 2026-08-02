#!/usr/bin/env python3
"""Seal C02 evidence while retaining every prior RAH generation.

The product-owner decisions require immutable preservation of all historical
generations. The generic state store retains three by default, so this
package-local closeout wrapper raises the limit only for the C02 evidence
transitions. Both modes validate the current parent, ledger high-water mark,
stable evidence, and overall non-completion state before committing.
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


ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "artifacts" / "work_packages" / "C02"
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


CORE_PARENT = "000006-6dc736b8"
STABLE_HASHES = {
    "c02-contract-codegen-verification.json": (
        "df55f11d6c3650868c67f73a1d67b0d586598bba10c4740888815255fbb516bf"
    ),
    "full-python-regression.junit.xml": (
        "13ca652d4efad7ff290781a42834d9b61a0cb82a8f81fece852c356beea6f5bc"
    ),
}
SOURCE_HASHES = {
    "packages/contracts/package.json": (
        "faceda59bc5539bc75d13dbc2bb11ba04220164a92e0fb98fc8752f47c108c1b"
    ),
    "packages/contracts/codegen/generate.py": (
        "76a1a37e54c3dcb9edab3dfe79f493c475ca779f0d8afeae7409ce894ce8d6b1"
    ),
    "packages/contracts/codegen/verify.py": (
        "747a5dd41aaecac4b4fab8f54ae0fcffcf3a3cd0106e763a428042a01a2afe11"
    ),
    "packages/contracts/codegen/cross_language_fixture.mjs": (
        "395344864b15057c8acd16e2b4535e01ba5fa0bcaa1582606804a7ff120b8dff"
    ),
    "package-lock.json": (
        "32d30423475de0cadc8d5fe04802b0833f396d9bb36f78ee156d5a4306f2616a"
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


def assert_hashes() -> None:
    for relative, expected in STABLE_HASHES.items():
        actual = sha256(PACKAGE / relative)
        if actual != expected:
            raise SystemExit(
                f"C02 evidence hash mismatch for {relative}: {actual} != {expected}"
            )
    for relative, expected in SOURCE_HASHES.items():
        actual = sha256(ROOT / relative)
        if actual != expected:
            raise SystemExit(
                f"C02 source hash mismatch for {relative}: {actual} != {expected}"
            )
    review = (PACKAGE / "review.md").read_text(encoding="utf-8")
    if "PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_REVIEW" not in review:
        raise SystemExit("C02 review does not record the authorized PASS status")
    if "not actor-independent assurance" not in review:
        raise SystemExit("C02 review omits the required assurance limitation")


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
        raise SystemExit("C02 cannot seal an already completion-ready goal")
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
        "C02 PASS: 124 canonical schemas and 124 examples generate nine "
        "deterministic TypeScript, Python, and UI projections with byte-equal "
        "manifests and cross-language fixture parity. Verification sha256:"
        f"{STABLE_HASHES['c02-contract-codegen-verification.json']}; full-suite "
        f"JUnit sha256:{STABLE_HASHES['full-python-regression.junit.xml']}; review "
        f"sha256:{review_hash}. The full suite remains 831 passed and exactly 24 "
        "C03-owned expected migration failures; C03 is next and "
        "completion_ready=false."
    )


def run_core() -> dict[str, object]:
    assert_hashes()
    ralph_root, parent, payloads = current_state()
    if parent != CORE_PARENT:
        raise SystemExit(f"Unexpected C02 core parent {parent}; expected {CORE_PARENT}")
    if evidence_ids(payloads) != [f"E{index:04d}" for index in range(1, 8)]:
        raise SystemExit("C02 core seal requires the preserved E0001-E0007 ledger")
    before = numbered_generations(ralph_root)
    generation = invoke_ralph(core_summary())
    _, _, sealed = current_state()
    if evidence_ids(sealed) != [f"E{index:04d}" for index in range(1, 9)]:
        raise SystemExit("C02 core seal did not append exactly E0008")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("C02 core seal did not preserve every prior generation")
    return {
        "mode": "core",
        "parent_generation": parent,
        "generation": generation,
        "evidence_id": "E0008",
        "retained_generations": after,
        "completion_ready": False,
    }


def run_final() -> dict[str, object]:
    assert_hashes()
    ralph_root, parent, payloads = current_state()
    if not re.fullmatch(r"000007-[0-9a-f]{8}", parent):
        raise SystemExit(f"Unexpected C02 final parent generation: {parent}")
    ids = evidence_ids(payloads)
    if ids != [f"E{index:04d}" for index in range(1, 9)]:
        raise SystemExit("C02 final seal requires the preserved E0001-E0008 ledger")
    ledger = payloads["evidence_ledger.json"]
    if ledger["entries"][-1].get("summary") != core_summary():
        raise SystemExit("E0008 does not match the C02 core evidence summary")

    report = json.loads((PACKAGE / "report.json").read_text(encoding="utf-8"))
    rah_state = report.get("rah_state")
    if not isinstance(rah_state, dict):
        raise SystemExit("C02 report has no rah_state closeout record")
    if rah_state.get("core_generation") != parent:
        raise SystemExit("C02 report core_generation does not match RAH authority")
    if rah_state.get("core_evidence_id") != "E0008":
        raise SystemExit("C02 report does not bind the core evidence ID")
    if rah_state.get("final_closeout_evidence_id") != "E0009":
        raise SystemExit("C02 report does not reserve final evidence E0009")
    if report.get("completion_ready") is not False:
        raise SystemExit("C02 report must keep completion_ready=false")

    commands = [
        json.loads(raw)
        for raw in (PACKAGE / "commands.jsonl").read_text(encoding="utf-8").splitlines()
        if raw.strip()
    ]
    command_ids = [row.get("command_id") for row in commands]
    if len(command_ids) != len(set(command_ids)):
        raise SystemExit("C02 commands.jsonl has duplicate command IDs")
    if command_ids[-2:] != ["C02-0001-C014", "C02-0001-C015"]:
        raise SystemExit("C02 core RAH append and verification commands are missing")

    closeout_hashes = {
        name: sha256(PACKAGE / name)
        for name in (
            "report.json",
            "review.md",
            "commands.jsonl",
            "dependency-status.json",
            "c02-rah-seal.py",
        )
    }
    summary = (
        "C02 closeout artifacts are hash-sealed after core RAH generation "
        f"{parent}: report sha256:{closeout_hashes['report.json']}; review sha256:"
        f"{closeout_hashes['review.md']}; commands sha256:"
        f"{closeout_hashes['commands.jsonl']}; dependency status sha256:"
        f"{closeout_hashes['dependency-status.json']}; preservation wrapper sha256:"
        f"{closeout_hashes['c02-rah-seal.py']}. C02=PASS, C03=READY, all prior "
        "generations and C01 history remain retained, and completion_ready=false."
    )
    before = numbered_generations(ralph_root)
    generation = invoke_ralph(summary)
    _, _, sealed = current_state()
    if evidence_ids(sealed) != [f"E{index:04d}" for index in range(1, 10)]:
        raise SystemExit("C02 final seal did not append exactly E0009")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("C02 final seal did not preserve every prior generation")
    return {
        "mode": "final",
        "parent_generation": parent,
        "generation": generation,
        "evidence_id": "E0009",
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
