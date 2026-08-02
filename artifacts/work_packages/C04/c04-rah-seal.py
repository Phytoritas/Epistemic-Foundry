#!/usr/bin/env python3
"""Seal C04 evidence while retaining every prior RAH generation."""

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
PACKAGE = ROOT / "artifacts" / "work_packages" / "C04"
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


CORE_PARENT = "000010-1f48c0b3"
STABLE_HASHES = {
    "c04-conformance-verification.json": (
        "17ba27252b163696a5a41cafaf4594b6c83faf699354e072a01bbfd6eaae3a13"
    ),
    "c04-conformance-verifier.py": (
        "1f0c1eb5ee093204210b0eaca29d91ae10192f4c3532d465ef127bc564a702fc"
    ),
    "full-python-conformance.junit.xml": (
        "c26d83ac45f678ac7045c4381ffae7a46b818c1f7479bdd6bd97f438053b5627"
    ),
    "targeted-contract-conformance.junit.xml": (
        "a2c47d02c0e447f935773aff2a10af393094b283490bf1962d5283ee84b908c8"
    ),
}
SOURCE_HASHES = {
    "manifests/development_manifest.yaml": (
        "a0a0db29da459d29c655827eaa0f7253d1becc3e75106f369850335ac7b88345"
    ),
    "artifacts/authority_decisions/HD-EF4-C01-SG003-20260728-001.human-decision.json": (
        "bcce9f20f59712c78032a846e1ac368e8d0cf27141731df31478a1f7e976d38e"
    ),
    "artifacts/work_packages/C01/attempts/0004/report.json": (
        "424f40396e93bd6826bf5ad85c3580cac7bd4ea8171b93f24816bc6a78c4a5d6"
    ),
    "artifacts/work_packages/C02/report.json": (
        "2f9a92ead5a97ecc47d2a70d2101bb4a302a6868710621511869c6e6f202d2e1"
    ),
    "artifacts/work_packages/C03/report.json": (
        "8bc497806e76a1faa0761e945c74f539e7fe4d44a03d9d162cbfee1c44400ad5"
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
                f"C04 evidence hash mismatch for {relative}: {actual} != {expected}"
            )
    for relative, expected in SOURCE_HASHES.items():
        actual = sha256(ROOT / relative)
        if actual != expected:
            raise SystemExit(
                f"C04 source hash mismatch for {relative}: {actual} != {expected}"
            )
    verification = json.loads(
        (PACKAGE / "c04-conformance-verification.json").read_text(encoding="utf-8")
    )
    if verification.get("status") != "PASS" or verification.get("failures") != []:
        raise SystemExit("C04 deterministic verification is not a clean PASS")
    if verification.get("completion_ready") is not False:
        raise SystemExit("C04 verification must keep completion_ready=false")
    review = (PACKAGE / "review.md").read_text(encoding="utf-8")
    if "PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_REVIEW" not in review:
        raise SystemExit("C04 review does not record the authorized PASS status")
    if "not actor-independent assurance" not in review:
        raise SystemExit("C04 review omits the required assurance limitation")
    if "C04-RF001" not in review or "C04-RF002" not in review:
        raise SystemExit("C04 review omits resolved verifier findings")


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
        raise SystemExit("C04 cannot seal an already completion-ready goal")
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
        "C04 PASS: the artifact-only C-phase conformance gate verifies 124 "
        "schemas and examples, OpenAPI 3.1.1 with 33 operations, nine generated "
        "contract files, strict resolved refs and promotion semantics, and the "
        "receipt-bound FORGE promotion path. Verification sha256:"
        f"{STABLE_HASHES['c04-conformance-verification.json']}; targeted JUnit "
        f"sha256:{STABLE_HASHES['targeted-contract-conformance.junit.xml']} "
        "records 163 passed; full-suite JUnit sha256:"
        f"{STABLE_HASHES['full-python-conformance.junit.xml']} records 898 passed, "
        f"zero failed and zero skipped; review sha256:{review_hash}. All 24 C01 "
        "migration-debt nodes pass, the residual allowlist is empty, B04 is "
        "next, and completion_ready=false."
    )


def run_core() -> dict[str, object]:
    assert_hashes()
    ralph_root, parent, payloads = current_state()
    if parent != CORE_PARENT:
        raise SystemExit(f"Unexpected C04 core parent {parent}; expected {CORE_PARENT}")
    if evidence_ids(payloads) != [f"E{index:04d}" for index in range(1, 12)]:
        raise SystemExit("C04 core seal requires the preserved E0001-E0011 ledger")
    before = numbered_generations(ralph_root)
    generation = invoke_ralph(core_summary())
    _, _, sealed = current_state()
    if evidence_ids(sealed) != [f"E{index:04d}" for index in range(1, 13)]:
        raise SystemExit("C04 core seal did not append exactly E0012")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("C04 core seal did not preserve every prior generation")
    return {
        "mode": "core",
        "parent_generation": parent,
        "generation": generation,
        "evidence_id": "E0012",
        "retained_generations": after,
        "completion_ready": False,
    }


def run_final() -> dict[str, object]:
    assert_hashes()
    ralph_root, parent, payloads = current_state()
    if not re.fullmatch(r"000011-[0-9a-f]{8}", parent):
        raise SystemExit(f"Unexpected C04 final parent generation: {parent}")
    if evidence_ids(payloads) != [f"E{index:04d}" for index in range(1, 13)]:
        raise SystemExit("C04 final seal requires the preserved E0001-E0012 ledger")
    ledger = payloads["evidence_ledger.json"]
    if ledger["entries"][-1].get("summary") != core_summary():
        raise SystemExit("E0012 does not match the C04 core evidence summary")

    report = json.loads((PACKAGE / "report.json").read_text(encoding="utf-8"))
    rah_state = report.get("rah_state")
    if not isinstance(rah_state, dict):
        raise SystemExit("C04 report has no rah_state closeout record")
    if report.get("status") != "PASS" or report.get("package_status") != "PASS":
        raise SystemExit("C04 report is not PASS")
    if report.get("completion_ready") is not False:
        raise SystemExit("C04 report must keep completion_ready=false")
    if rah_state.get("core_generation") != parent:
        raise SystemExit("C04 report core_generation does not match RAH authority")
    if rah_state.get("core_evidence_id") != "E0012":
        raise SystemExit("C04 report does not bind the core evidence ID")
    if rah_state.get("final_closeout_evidence_id") != "E0013":
        raise SystemExit("C04 report does not reserve final evidence E0013")

    commands = [
        json.loads(raw)
        for raw in (PACKAGE / "commands.jsonl").read_text(encoding="utf-8").splitlines()
        if raw.strip()
    ]
    command_ids = [row.get("command_id") for row in commands]
    if len(command_ids) != len(set(command_ids)):
        raise SystemExit("C04 commands.jsonl has duplicate command IDs")
    if command_ids[-2:] != ["C04-0001-C018", "C04-0001-C019"]:
        raise SystemExit("C04 core RAH append and verification commands are missing")

    closeout_hashes = {
        name: sha256(PACKAGE / name)
        for name in (
            "report.json",
            "review.md",
            "commands.jsonl",
            "dependency-status.json",
            "c04-rah-seal.py",
        )
    }
    summary = (
        "C04 closeout artifacts are hash-sealed after core RAH generation "
        f"{parent}: report sha256:{closeout_hashes['report.json']}; review sha256:"
        f"{closeout_hashes['review.md']}; commands sha256:"
        f"{closeout_hashes['commands.jsonl']}; dependency status sha256:"
        f"{closeout_hashes['dependency-status.json']}; preservation wrapper sha256:"
        f"{closeout_hashes['c04-rah-seal.py']}. C04=PASS, B04=READY, all prior "
        "generations and C01/C02/C03 history remain retained, and "
        "completion_ready=false."
    )
    before = numbered_generations(ralph_root)
    generation = invoke_ralph(summary)
    _, _, sealed = current_state()
    if evidence_ids(sealed) != [f"E{index:04d}" for index in range(1, 14)]:
        raise SystemExit("C04 final seal did not append exactly E0013")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("C04 final seal did not preserve every prior generation")
    return {
        "mode": "final",
        "parent_generation": parent,
        "generation": generation,
        "evidence_id": "E0013",
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
