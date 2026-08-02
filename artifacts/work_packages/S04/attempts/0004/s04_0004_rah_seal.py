#!/usr/bin/env python3
"""Append S04-0004 SPEC_GAP evidence while preserving every RAH generation."""

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


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/S04/attempts/0004"
AUTOMATION = ROOT / ".rah/helpers/recursive-architecture-refactoring-auto/automation"
sys.path.insert(0, str(ATTEMPT))
sys.path.insert(0, str(AUTOMATION))

import build_s04_0004_evidence as evidence  # noqa: E402
import ralph_harness as rh  # noqa: E402
import state_store  # noqa: E402


EXPECTED_PARENT = "000091-0bdab228"
EXPECTED_PARENT_EVIDENCE = "E0092"
EXPECTED_PARENT_GENERATIONS = 91
AUDIT_EVIDENCE_ID = "E0093"
GAP_EVIDENCE_ID = "E0094"
FINAL_EVIDENCE_ID = "E0095"
BLOCK_REASON = (
    "S04-SG001 requires a product-owner HumanDecision authorizing the exact path "
    "tests/security/s04-threat-model-traceability.test.mjs and a new immutable "
    "manifest patch-plan artifact path, and defining the next binding ID, supersedes "
    "lineage, authorizing-decision list, and active-revision validation semantics. "
    "HD-EF4-C01-SG005-20260731-001 authorizes only the active binding file and S04 "
    "attempt evidence. Binding-only correction is unsatisfiable because S04-TM004 "
    "also requires the immutable prior patch-plan successor, fixed binding ID, and "
    "fixed authorizing-decision list. C01-0009 and all later ordered attempts remain "
    "unstarted; completion_ready=false."
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"JSON artifact is not an object: {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def generation_names(root: Path) -> list[str]:
    return sorted(
        path.name
        for path in (root / "generations").iterdir()
        if path.is_dir() and re.fullmatch(r"\d{6}-[0-9a-f]{8}", path.name)
    )


def current_state() -> tuple[Path, str, dict[str, Any]]:
    root = ROOT / ".rah/ralph"
    current = state_store.read_current(root)
    if current is None:
        raise SystemExit("no committed RAH generation")
    generation, payloads = current
    verified = state_store.verify_current(root)
    if verified.get("generation") != generation:
        raise SystemExit("RAH pointer and verified generation disagree")
    return root, generation, payloads


def evidence_ids(payloads: dict[str, Any]) -> list[str]:
    ledger = payloads.get("evidence_ledger.json")
    if not isinstance(ledger, dict) or not isinstance(ledger.get("entries"), list):
        raise SystemExit("invalid RAH evidence ledger")
    values = [str(row.get("id")) for row in ledger["entries"] if isinstance(row, dict)]
    if any(re.fullmatch(r"E\d{4,}", value) is None for value in values):
        raise SystemExit("malformed RAH evidence ID")
    return values


def invoke_ralph(arguments: list[str]) -> tuple[int, str]:
    state_store.KEEP_GENERATIONS = 10_000
    saved = sys.argv
    captured = io.StringIO()
    try:
        sys.argv = ["ralph_harness.py", str(ROOT), *arguments, "--json"]
        with contextlib.redirect_stdout(captured):
            result = rh.main()
    finally:
        sys.argv = saved
    return result, captured.getvalue()


def audit_summary() -> str:
    names = (
        "binding-only-impossibility-verification.json",
        "dependency-status.json",
        "targeted-source-binding.junit.xml",
        "junit-normalization-verification.json",
        "review.md",
        "build_s04_0004_evidence.py",
        "s04_0004_rah_seal.py",
    )
    hashes = {name: sha256(ATTEMPT / name) for name in names}
    return (
        "S04-0004 binding-only contract audit: S04-TM001 through TM003 pass and "
        "S04-TM004 alone fails because current manifest sha256:"
        "6ccf07571c34c9010a10605ba201ba698a09f6343a281565520d392e4c77e063 "
        "differs from immutable patch-plan/binding successor sha256:"
        "5dd99d2aae1e9ef662b9b8242b5fa921621434c6600c9c06e3a573d03079bb12. "
        "The active test also freezes binding ID DMB-EF4-20260730-002 and the prior "
        "authorizing-decision list. The product-owner decision authorizes only the "
        "binding file and S04 attempt evidence, so no binding-only solution exists. "
        + "; ".join(f"{name}=sha256:{value}" for name, value in hashes.items())
        + ". Product mutation count=0; completion_ready=false."
    )


def gap_summary() -> str:
    return (
        "S04-0004 SPEC_GAP S04-SG001: creating the required new immutable binding "
        "revision would necessarily disagree with at least one non-editable S04-TM004 "
        "constraint: the old patch plan's successor, fixed active binding ID, or fixed "
        "authorizing-decision list. A product-owner decision must authorize the exact "
        "S04-TM004 test path and a new immutable patch-plan path, then define the next "
        "binding revision, supersedes linkage, authorizing-decision binding, and active "
        "revision validation. This is not FAIL because the requested solution is outside "
        "the exact authorized contract, and not BLOCKED because no external capability "
        "is missing. C01-0009 and all later attempts are unstarted; completion_ready=false."
    )


def final_summary(core_generation: str) -> tuple[str, dict[str, str]]:
    names = (
        "report.json",
        "commands.jsonl",
        "review.md",
        "binding-only-impossibility-verification.json",
        "dependency-status.json",
        "targeted-source-binding.junit.xml",
        "junit-normalization-verification.json",
        "rah-core-integrity.json",
        "build_s04_0004_evidence.py",
        "s04_0004_rah_seal.py",
    )
    hashes = {name: sha256(ATTEMPT / name) for name in names}
    summary = (
        f"S04-0004 SPEC_GAP closeout is hash-sealed after core generation "
        f"{core_generation}: "
        + "; ".join(f"{name}=sha256:{value}" for name, value in hashes.items())
        + ". Product mutation count=0; S04-0002, S04-0003, J02-0004 and every prior "
        "RAH generation remain preserved. C01-0009 and later ordered attempts were not "
        "started; implementation_gate=fail and completion_ready=false."
    )
    return summary, hashes


def verify_store(expected_count: int) -> dict[str, Any]:
    root, current, payloads = current_state()
    generations = generation_names(root)
    if len(generations) != expected_count or generations[-1] != current:
        raise SystemExit("RAH generation inventory mismatch")
    checked = 0
    for generation in generations:
        directory = root / "generations" / generation
        manifest = read_json(directory / "generation-manifest.json")
        files = manifest.get("files")
        if manifest.get("generation") != generation or not isinstance(files, dict):
            raise SystemExit(f"invalid generation manifest: {generation}")
        if set(files) != set(state_store.GENERATION_FILES):
            raise SystemExit(f"generation file set mismatch: {generation}")
        for name in state_store.GENERATION_FILES:
            if sha256(directory / name) != files[name]:
                raise SystemExit(f"generation hash mismatch: {generation}/{name}")
            checked += 1
    stamps = 0
    matches = 0
    for name in state_store.GENERATION_FILES:
        flat = read_json(root / name)
        if flat.get("state_generation") == current:
            stamps += 1
        stripped = {key: value for key, value in flat.items() if key != "state_generation"}
        authority = payloads[name]
        if isinstance(authority, dict):
            authority = {
                key: value for key, value in authority.items() if key != "state_generation"
            }
        if state_store._dump(stripped) == state_store._dump(authority):
            matches += 1
    loop = payloads["loop_state.json"]
    if (
        stamps != 6
        or matches != 6
        or loop.get("status") != "blocked"
        or loop.get("blocked_reason") != BLOCK_REASON
        or loop.get("implementation_gate") != "fail"
        or loop.get("completion_readiness", {}).get("ready") is not False
    ):
        raise SystemExit("RAH blocker or flat snapshot mismatch")
    identifiers = evidence_ids(payloads)
    return {
        "attempt_id": evidence.ATTEMPT_ID,
        "work_package_id": "S04",
        "status": "PASS",
        "mode": "READ_ONLY",
        "current_generation": current,
        "latest_evidence_id": identifiers[-1],
        "evidence_count": len(identifiers),
        "retained_generation_count": len(generations),
        "generation_file_hashes_verified": checked,
        "generation_manifest_sha256": "sha256:"
        + sha256(root / "generations" / current / "generation-manifest.json"),
        "flat_snapshot_stamps_verified": stamps,
        "flat_snapshot_content_matches": matches,
        "ralph_status": "blocked",
        "implementation_gate": "fail",
        "completion_ready": False,
        "parse_errors": {},
    }


def preflight() -> dict[str, Any]:
    evidence.verify()
    root, generation, payloads = current_state()
    if generation != EXPECTED_PARENT:
        raise SystemExit(f"unexpected S04-0004 parent generation: {generation}")
    if len(generation_names(root)) != EXPECTED_PARENT_GENERATIONS:
        raise SystemExit("unexpected S04-0004 parent generation count")
    if evidence_ids(payloads)[-1] != EXPECTED_PARENT_EVIDENCE:
        raise SystemExit("unexpected S04-0004 parent evidence tail")
    loop = payloads["loop_state.json"]
    if (
        loop.get("status") != "active"
        or loop.get("blocked_reason") is not None
        or loop.get("implementation_gate") != "fail"
        or loop.get("completion_readiness", {}).get("ready") is not False
    ):
        raise SystemExit("S04-0004 preflight requires active/fail/completion_ready=false")
    return {
        "mode": "preflight",
        "status": "PASS",
        "generation": generation,
        "latest_evidence_id": EXPECTED_PARENT_EVIDENCE,
        "retained_generation_count": EXPECTED_PARENT_GENERATIONS,
        "completion_ready": False,
    }


def core() -> dict[str, Any]:
    preflight()
    root, parent, _ = current_state()
    before = generation_names(root)
    result, output = invoke_ralph(
        [
            "--record-evidence",
            audit_summary(),
            "--record-gap",
            gap_summary(),
            "--block",
            BLOCK_REASON,
            "--no-increment",
        ]
    )
    if result != 0:
        raise SystemExit(f"RAH S04-0004 core append failed ({result}): {output}")
    _, generation, payloads = current_state()
    if evidence_ids(payloads)[-2:] != [AUDIT_EVIDENCE_ID, GAP_EVIDENCE_ID]:
        raise SystemExit("S04-0004 core evidence IDs mismatch")
    entries = payloads["evidence_ledger.json"]["entries"]
    if entries[-2].get("kind") != "evidence" or entries[-2].get("summary") != audit_summary():
        raise SystemExit("S04 audit evidence mismatch")
    if entries[-1].get("kind") != "documented_gap" or entries[-1].get("summary") != gap_summary():
        raise SystemExit("S04 documented gap evidence mismatch")
    after = generation_names(root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("S04 core did not preserve prior generations")
    integrity = verify_store(EXPECTED_PARENT_GENERATIONS + 1)
    write_json(ATTEMPT / "rah-core-integrity.json", integrity)
    report = read_json(ATTEMPT / "report.json")
    report["rah_state"] = {
        "core_generation": generation,
        "audit_evidence_id": AUDIT_EVIDENCE_ID,
        "documented_gap_evidence_id": GAP_EVIDENCE_ID,
        "final_closeout_evidence_id": FINAL_EVIDENCE_ID,
        "status": "blocked",
        "completion_ready": False,
    }
    write_json(ATTEMPT / "report.json", report)
    evidence.verify()
    return {
        "mode": "core",
        "status": "blocked",
        "parent_generation": parent,
        "generation": generation,
        "audit_evidence_id": AUDIT_EVIDENCE_ID,
        "documented_gap_evidence_id": GAP_EVIDENCE_ID,
        "state_verification": integrity,
        "completion_ready": False,
    }


def final() -> dict[str, Any]:
    evidence.verify()
    root, parent, payloads = current_state()
    report = read_json(ATTEMPT / "report.json")
    rah = report.get("rah_state")
    if not isinstance(rah, dict) or rah.get("core_generation") != parent:
        raise SystemExit("S04 report does not bind current core generation")
    if evidence_ids(payloads)[-2:] != [AUDIT_EVIDENCE_ID, GAP_EVIDENCE_ID]:
        raise SystemExit("S04 final requires exact core evidence tail")
    summary, hashes = final_summary(parent)
    before = generation_names(root)
    result, output = invoke_ralph(
        ["--record-evidence", summary, "--no-increment", "--no-update-current-loop"]
    )
    if result != 0:
        raise SystemExit(f"RAH S04-0004 final append failed ({result}): {output}")
    _, generation, sealed = current_state()
    if evidence_ids(sealed)[-1] != FINAL_EVIDENCE_ID:
        raise SystemExit("S04 final evidence ID mismatch")
    if sealed["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
        raise SystemExit("S04 final evidence summary mismatch")
    after = generation_names(root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("S04 final did not preserve prior generations")
    return {
        "mode": "final",
        "status": "blocked",
        "parent_generation": parent,
        "generation": generation,
        "evidence_id": FINAL_EVIDENCE_ID,
        "artifact_hashes": hashes,
        "state_verification": verify_store(EXPECTED_PARENT_GENERATIONS + 2),
        "completion_ready": False,
    }


def verify() -> dict[str, Any]:
    generations = generation_names(ROOT / ".rah/ralph")
    if len(generations) == EXPECTED_PARENT_GENERATIONS:
        return preflight()
    evidence.verify()
    if len(generations) == EXPECTED_PARENT_GENERATIONS + 1:
        integrity = verify_store(len(generations))
        if integrity["latest_evidence_id"] != GAP_EVIDENCE_ID:
            raise SystemExit("S04 core evidence tail mismatch")
        return {**integrity, "mode": "core-verify"}
    if len(generations) != EXPECTED_PARENT_GENERATIONS + 2:
        raise SystemExit("unexpected S04-0004 generation count")
    integrity = verify_store(len(generations))
    if integrity["latest_evidence_id"] != FINAL_EVIDENCE_ID:
        raise SystemExit("S04 final evidence tail mismatch")
    report = read_json(ATTEMPT / "report.json")
    core_generation = str(report["rah_state"]["core_generation"])
    summary, _ = final_summary(core_generation)
    _, _, payloads = current_state()
    if payloads["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
        raise SystemExit("stored S04 closeout differs from current artifact hashes")
    return {**integrity, "mode": "final-verify"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("preflight", "core", "final", "verify"))
    args = parser.parse_args()
    result = {
        "preflight": preflight,
        "core": core,
        "final": final,
        "verify": verify,
    }[args.mode]()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
