#!/usr/bin/env python3
"""Seal C03 evidence while retaining every prior RAH generation.

The product-owner decisions require immutable preservation of historical RAH
generations. The generic state store retains three by default, so this
package-local closeout wrapper raises the limit only for the two C03 evidence
transitions. Both modes validate the exact parent, ledger high-water mark,
stable evidence, source bytes, review limitation, and overall non-completion
state before committing.
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
PACKAGE = ROOT / "artifacts" / "work_packages" / "C03"
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


CORE_PARENT = "000008-19dde058"
STABLE_HASHES = {
    "c03-runtime-migration-verification.json": (
        "51c22895ee9f0b8ae8ab44b61af13a1ab9600f5f1a8751efd890c1caacbfd4ff"
    ),
    "c03-runtime-migration-verifier.py": (
        "5cb73f686085f0cab82737203e3bc0a281373da55139260217ee0ac9d648993e"
    ),
    "targeted-runtime-migration.junit.xml": (
        "d768d1268aa29c56f6dceb2e765b5b45ffda0d5aa154f220b50faf72415a972e"
    ),
    "full-python-regression.junit.xml": (
        "b30c079f4b65c92f23974cf6597d5e2ccbb1516b9e45bb4150ad7deccd4114d8"
    ),
}
SOURCE_HASHES = {
    "docs/schema_evolution.md": (
        "e9e89a367e8ff6191552aa97632b00bae7cafbfbd41fd18ec0614872ca7be7ac"
    ),
    "src/epistemic_foundry/evolution_chamber/run_spec.py": (
        "ce6a135dac6fbfb98184ff46448da88222cdb2de5ef31066d2f146bc25a7dc1c"
    ),
    "src/epistemic_foundry/governance/promotion.py": (
        "9078dae66ff527b36915d924e579c49b7937ce78d0c084c2f8b00852e0113f51"
    ),
    "tests/test_evolution_chamber.py": (
        "fa69b90f5d830d0f3552d374733da15a4769aae150fef4ed47ed35d8f19ac59f"
    ),
    "tests/test_governance.py": (
        "e2b83693db1434d88dbafd8c2f71cb5c9f7b89bf29e3a1cc0eb8fdd2bf99184c"
    ),
    "tests/test_integration_forge_cycle.py": (
        "0fbd58c632aaf3a5535b739c624c6deba534aaf2b849fb097cc1b75b0430d42f"
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


def assert_hashes() -> None:
    for relative, expected in STABLE_HASHES.items():
        actual = sha256(PACKAGE / relative)
        if actual != expected:
            raise SystemExit(
                f"C03 evidence hash mismatch for {relative}: {actual} != {expected}"
            )
    for relative, expected in SOURCE_HASHES.items():
        actual = sha256(ROOT / relative)
        if actual != expected:
            raise SystemExit(
                f"C03 source hash mismatch for {relative}: {actual} != {expected}"
            )
    review = (PACKAGE / "review.md").read_text(encoding="utf-8")
    if "PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_REVIEW" not in review:
        raise SystemExit("C03 review does not record the authorized PASS status")
    if "not actor-independent assurance" not in review:
        raise SystemExit("C03 review omits the required assurance limitation")


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
        raise SystemExit("C03 cannot seal an already completion-ready goal")
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
        "C03 PASS: strict resolved EvolutionRunSpec pins, explicit fail-closed "
        "legacy migration, canonical promotion null/grant semantics, receipt-bound "
        "CAS/replay, and hash-bound rollback/backfill are implemented within the "
        "authorized runtime boundary. Verification sha256:"
        f"{STABLE_HASHES['c03-runtime-migration-verification.json']}; targeted "
        f"JUnit sha256:{STABLE_HASHES['targeted-runtime-migration.junit.xml']} "
        "records 92 passed; full-suite JUnit sha256:"
        f"{STABLE_HASHES['full-python-regression.junit.xml']} records 898 passed, "
        f"zero failed and zero skipped; review sha256:{review_hash}. All 24 C01 "
        "migration-debt nodes pass, C04 is next, and completion_ready=false."
    )


def run_core() -> dict[str, object]:
    assert_hashes()
    ralph_root, parent, payloads = current_state()
    if parent != CORE_PARENT:
        raise SystemExit(f"Unexpected C03 core parent {parent}; expected {CORE_PARENT}")
    if evidence_ids(payloads) != [f"E{index:04d}" for index in range(1, 10)]:
        raise SystemExit("C03 core seal requires the preserved E0001-E0009 ledger")
    before = numbered_generations(ralph_root)
    generation = invoke_ralph(core_summary())
    _, _, sealed = current_state()
    if evidence_ids(sealed) != [f"E{index:04d}" for index in range(1, 11)]:
        raise SystemExit("C03 core seal did not append exactly E0010")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("C03 core seal did not preserve every prior generation")
    return {
        "mode": "core",
        "parent_generation": parent,
        "generation": generation,
        "evidence_id": "E0010",
        "retained_generations": after,
        "completion_ready": False,
    }


def run_final() -> dict[str, object]:
    assert_hashes()
    ralph_root, parent, payloads = current_state()
    if not re.fullmatch(r"000009-[0-9a-f]{8}", parent):
        raise SystemExit(f"Unexpected C03 final parent generation: {parent}")
    ids = evidence_ids(payloads)
    if ids != [f"E{index:04d}" for index in range(1, 11)]:
        raise SystemExit("C03 final seal requires the preserved E0001-E0010 ledger")
    ledger = payloads["evidence_ledger.json"]
    if ledger["entries"][-1].get("summary") != core_summary():
        raise SystemExit("E0010 does not match the C03 core evidence summary")

    report = json.loads((PACKAGE / "report.json").read_text(encoding="utf-8"))
    rah_state = report.get("rah_state")
    if not isinstance(rah_state, dict):
        raise SystemExit("C03 report has no rah_state closeout record")
    if rah_state.get("core_generation") != parent:
        raise SystemExit("C03 report core_generation does not match RAH authority")
    if rah_state.get("core_evidence_id") != "E0010":
        raise SystemExit("C03 report does not bind the core evidence ID")
    if rah_state.get("final_closeout_evidence_id") != "E0011":
        raise SystemExit("C03 report does not reserve final evidence E0011")
    if report.get("completion_ready") is not False:
        raise SystemExit("C03 report must keep completion_ready=false")

    commands = [
        json.loads(raw)
        for raw in (PACKAGE / "commands.jsonl").read_text(encoding="utf-8").splitlines()
        if raw.strip()
    ]
    command_ids = [row.get("command_id") for row in commands]
    if len(command_ids) != len(set(command_ids)):
        raise SystemExit("C03 commands.jsonl has duplicate command IDs")
    if command_ids[-2:] != ["C03-0001-C014", "C03-0001-C015"]:
        raise SystemExit("C03 core RAH append and verification commands are missing")

    closeout_hashes = {
        name: sha256(PACKAGE / name)
        for name in (
            "report.json",
            "review.md",
            "commands.jsonl",
            "dependency-status.json",
            "c03-rah-seal.py",
        )
    }
    summary = (
        "C03 closeout artifacts are hash-sealed after core RAH generation "
        f"{parent}: report sha256:{closeout_hashes['report.json']}; review sha256:"
        f"{closeout_hashes['review.md']}; commands sha256:"
        f"{closeout_hashes['commands.jsonl']}; dependency status sha256:"
        f"{closeout_hashes['dependency-status.json']}; preservation wrapper sha256:"
        f"{closeout_hashes['c03-rah-seal.py']}. C03=PASS, C04=READY, all prior "
        "generations and C01/C02 history remain retained, and completion_ready=false."
    )
    before = numbered_generations(ralph_root)
    generation = invoke_ralph(summary)
    _, _, sealed = current_state()
    if evidence_ids(sealed) != [f"E{index:04d}" for index in range(1, 12)]:
        raise SystemExit("C03 final seal did not append exactly E0011")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("C03 final seal did not preserve every prior generation")
    return {
        "mode": "final",
        "parent_generation": parent,
        "generation": generation,
        "evidence_id": "E0011",
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
