#!/usr/bin/env python3
"""Append J02-0001 SPEC_GAP evidence without rewriting RAH history."""

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


ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/J02/attempts/0001"
AUTOMATION = ROOT / ".rah/helpers/recursive-architecture-refactoring-auto/automation"
sys.dont_write_bytecode = True
sys.path.insert(0, str(ATTEMPT))
sys.path.insert(0, str(AUTOMATION))

import j02_contract_audit as audit  # noqa: E402
import ralph_harness as rh  # noqa: E402
import state_store  # noqa: E402


CORE_PARENT = "000075-b6f3b5e9"
AUDIT_EVIDENCE_ID = "E0078"
GAP_EVIDENCE_ID = "E0079"
FINAL_EVIDENCE_ID = "E0080"
BLOCK_REASON = (
    "J02-SG001 requires a product-owner HumanDecision defining exact initial-metadata "
    "budget profiles and accounting, the canonical installed child-skill/reference "
    "inventory, deterministic selection and reachability semantics, loader/runtime "
    "ownership and exact write paths, and objective fixtures and thresholds for "
    "context_budget_test and reference_reachability_test. J02 cannot invent these "
    "shared contracts or modify SKILL.md/router/runtime/test paths outside its current "
    "scope. J04 remains waiting; later ready packages remain unstarted under serial "
    "execution; completion_ready=false."
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


def numbered_generations(ralph_root: Path) -> list[str]:
    return sorted(
        path.name
        for path in (ralph_root / "generations").iterdir()
        if path.is_dir() and re.fullmatch(r"\d{6}-[0-9a-f]{8}", path.name)
    )


def current_state() -> tuple[Path, str, dict[str, Any]]:
    ralph_root = ROOT / ".rah/ralph"
    current = state_store.read_current(ralph_root)
    if current is None:
        raise SystemExit("no committed RAH generation")
    generation, payloads = current
    verified = state_store.verify_current(ralph_root)
    if verified.get("generation") != generation:
        raise SystemExit("RAH pointer and generation verification disagree")
    return ralph_root, generation, payloads


def evidence_ids(payloads: dict[str, Any]) -> list[str]:
    ledger = payloads.get("evidence_ledger.json")
    if not isinstance(ledger, dict) or not isinstance(ledger.get("entries"), list):
        raise SystemExit("invalid RAH evidence ledger")
    return [str(row.get("id")) for row in ledger["entries"] if isinstance(row, dict)]


def verify_generation_store(expected_count: int) -> dict[str, Any]:
    ralph_root, current, payloads = current_state()
    generations = numbered_generations(ralph_root)
    if len(generations) != expected_count or generations[-1] != current:
        raise SystemExit(f"expected {expected_count} generations ending at {current}, found {len(generations)}")
    verified_hashes = 0
    for generation in generations:
        root = ralph_root / "generations" / generation
        manifest = read_json(root / "generation-manifest.json")
        files = manifest.get("files")
        if manifest.get("generation") != generation or not isinstance(files, dict):
            raise SystemExit(f"invalid generation manifest: {generation}")
        if set(files) != set(state_store.GENERATION_FILES):
            raise SystemExit(f"generation file set mismatch: {generation}")
        for name in state_store.GENERATION_FILES:
            if sha256(root / name) != files[name]:
                raise SystemExit(f"generation hash mismatch: {generation}/{name}")
            verified_hashes += 1
    flat_stamps = 0
    flat_matches = 0
    for name in state_store.GENERATION_FILES:
        flat = read_json(ralph_root / name)
        if flat.get("state_generation") == current:
            flat_stamps += 1
        stripped = {key: value for key, value in flat.items() if key != "state_generation"}
        authority = payloads[name]
        if isinstance(authority, dict):
            authority = {key: value for key, value in authority.items() if key != "state_generation"}
        if state_store._dump(stripped) == state_store._dump(authority):
            flat_matches += 1
    if flat_stamps != 6 or flat_matches != 6:
        raise SystemExit(f"flat snapshot mismatch: stamps={flat_stamps}, matches={flat_matches}")
    latest_ids = evidence_ids(payloads)
    return {
        "schema_version": 1,
        "work_package_id": "J02",
        "attempt_id": "J02-0001",
        "status": "PASS",
        "mode": "READ_ONLY",
        "current_generation": current,
        "generation_manifest_sha256": sha256(
            ralph_root / "generations" / current / "generation-manifest.json"
        ),
        "latest_evidence_id": latest_ids[-1],
        "evidence_count": len(latest_ids),
        "retained_generation_count": len(generations),
        "generation_file_hashes_verified": verified_hashes,
        "flat_snapshot_stamps_verified": flat_stamps,
        "flat_snapshot_content_matches": flat_matches,
        "ralph_status": payloads["loop_state.json"].get("status"),
        "spec_gap_id": "J02-SG001",
        "completion_ready": payloads["loop_state.json"].get("completion_readiness", {}).get("ready"),
        "preservation": {
            "all_prior_generations_retained": True,
            "flat_projection_matches_authority": True,
            "J01_history_preserved": sha256(ROOT / "artifacts/work_packages/J01/report.json") == audit.AUTHORITY_HASHES["artifacts/work_packages/J01/report.json"],
            "dirty_worktree_preserved": True,
            "completion_state_not_advanced": True,
        },
    }


def audit_summary() -> str:
    return (
        "J02-0001 contract audit confirms dependency J01 is evidence-sealed PASS, "
        "but J02 has no operative progressive-reference contract. Installed skill "
        "inventory is 2 files, 1 SKILL.md, 0 references; blueprint skill inventory "
        "is 30 files, 29 SKILL.md, 0 references and remains "
        "REFERENCE_BLUEPRINT_NOT_IMPLEMENTED. No numeric metadata budget, accounting "
        "unit/tokenizer, canonical reference inventory, selection/reachability "
        "mapping, loader owner, authorized test surface, or objective threshold "
        "exists. Required checks are truthfully NOT_DEFINABLE. Contract audit sha256:"
        f"{sha256(ATTEMPT / 'shared-contract-gap-verification.json')}; dependency "
        f"status sha256:{sha256(ATTEMPT / 'dependency-status.json')}; review sha256:"
        f"{sha256(ATTEMPT / 'review.md')}. Product implementation changes=0; "
        "completion_ready=false."
    )


def gap_summary() -> str:
    return (
        "J02-0001 SPEC_GAP J02-SG001: context_budget_test and "
        "reference_reachability_test cannot be defined without a product-owner "
        "decision fixing budget/accounting, installed skill/reference authority, "
        "deterministic selection and reachability semantics, loader/runtime ownership "
        "and exact implementation/test paths and thresholds. This is not FAIL because "
        "no implementation has been attempted against an invented oracle, and not "
        "BLOCKED because no external prerequisite is unavailable. J04 remains waiting; "
        "J03/K01/T01/A06 remain unstarted under serial execution; completion_ready=false."
    )


def invoke_ralph(arguments: list[str]) -> tuple[int, str]:
    state_store.KEEP_GENERATIONS = 10_000
    saved_argv = sys.argv
    captured = io.StringIO()
    try:
        sys.argv = ["ralph_harness.py", str(ROOT), *arguments, "--json"]
        with contextlib.redirect_stdout(captured):
            result = rh.main()
    finally:
        sys.argv = saved_argv
    return result, captured.getvalue()


def preflight() -> dict[str, Any]:
    audit.verify_pre_core(run_regression=True)
    ralph_root, generation, payloads = current_state()
    if generation != CORE_PARENT:
        raise SystemExit(f"unexpected J02 core parent {generation}; expected {CORE_PARENT}")
    if evidence_ids(payloads) != [f"E{index:04d}" for index in range(1, 78)]:
        raise SystemExit("J02 preflight requires preserved E0001-E0077")
    generations = numbered_generations(ralph_root)
    if len(generations) != 75 or generations[-1] != generation:
        raise SystemExit("J02 preflight requires all 75 prior generations")
    loop = payloads["loop_state.json"]
    if loop.get("status") != "active" or loop.get("completion_readiness", {}).get("ready") is not False:
        raise SystemExit("J02 preflight requires active RAH and completion_ready=false")
    return {
        "mode": "preflight",
        "generation": generation,
        "latest_evidence_id": "E0077",
        "retained_generation_count": len(generations),
        "completion_ready": False,
    }


def core() -> dict[str, Any]:
    preflight()
    ralph_root, parent, _ = current_state()
    before = numbered_generations(ralph_root)
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
        raise SystemExit(f"RAH J02 core append failed ({result}): {output}")
    _, generation, payloads = current_state()
    if evidence_ids(payloads) != [f"E{index:04d}" for index in range(1, 80)]:
        raise SystemExit("J02 core did not append exactly E0078 and E0079")
    entries = payloads["evidence_ledger.json"]["entries"]
    if entries[-2].get("kind") != "evidence" or entries[-2].get("summary") != audit_summary():
        raise SystemExit("E0078 is not the exact J02 contract audit")
    if entries[-1].get("kind") != "documented_gap" or entries[-1].get("summary") != gap_summary():
        raise SystemExit("E0079 is not the exact J02 documented gap")
    loop = payloads["loop_state.json"]
    if loop.get("status") != "blocked" or loop.get("blocked_reason") != BLOCK_REASON:
        raise SystemExit("RAH did not persist the exact J02-SG001 blocker")
    if loop.get("completion_readiness", {}).get("ready") is not False:
        raise SystemExit("RAH advanced completion_ready during J02 blocker seal")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("J02 core seal did not preserve every prior generation")
    integrity = verify_generation_store(76)
    audit.build_post_core(integrity)
    return {
        "mode": "core",
        "parent_generation": parent,
        "generation": generation,
        "contract_audit_evidence_id": AUDIT_EVIDENCE_ID,
        "documented_gap_evidence_id": GAP_EVIDENCE_ID,
        "status": "blocked",
        "spec_gap_id": "J02-SG001",
        "state_verification": integrity,
        "completion_ready": False,
    }


def final_summary(parent: str) -> tuple[str, dict[str, str]]:
    names = (
        "report.json",
        "review.md",
        "commands.jsonl",
        "shared-contract-gap-verification.json",
        "dependency-status.json",
        "rah-core-integrity.json",
        "j02_contract_audit.py",
        "j02_rah_seal.py",
    )
    hashes = {name: sha256(ATTEMPT / name) for name in names}
    summary = (
        f"J02-0001 SPEC_GAP closeout is hash-sealed after core blocker generation {parent}: "
        f"report sha256:{hashes['report.json']}; review sha256:{hashes['review.md']}; "
        f"commands sha256:{hashes['commands.jsonl']}; contract audit sha256:"
        f"{hashes['shared-contract-gap-verification.json']}; dependency status sha256:"
        f"{hashes['dependency-status.json']}; core RAH integrity sha256:"
        f"{hashes['rah-core-integrity.json']}; audit builder sha256:"
        f"{hashes['j02_contract_audit.py']}; sealer sha256:{hashes['j02_rah_seal.py']}. "
        "J02 remains SPEC_GAP J02-SG001 with both required checks NOT_DEFINABLE; "
        "product implementation changes=0; J01 and all earlier evidence remain "
        "immutable; later packages remain unstarted; completion_ready=false."
    )
    return summary, hashes


def final() -> dict[str, Any]:
    audit.verify_post_core(run_regression=True)
    ralph_root, parent, payloads = current_state()
    if not re.fullmatch(r"000076-[0-9a-f]{8}", parent):
        raise SystemExit(f"unexpected J02 final parent generation: {parent}")
    if evidence_ids(payloads) != [f"E{index:04d}" for index in range(1, 80)]:
        raise SystemExit("J02 final requires preserved E0001-E0079")
    entries = payloads["evidence_ledger.json"]["entries"]
    if entries[-2].get("summary") != audit_summary() or entries[-1].get("summary") != gap_summary():
        raise SystemExit("J02 core evidence summaries changed before final seal")
    report = read_json(ATTEMPT / "report.json")
    rah_state = report.get("rah_state")
    if not isinstance(rah_state, dict) or rah_state.get("core_generation") != parent:
        raise SystemExit("J02 report does not bind the core generation")
    summary, hashes = final_summary(parent)
    before = numbered_generations(ralph_root)
    result, output = invoke_ralph(
        ["--record-evidence", summary, "--no-increment", "--no-update-current-loop"]
    )
    if result != 0:
        raise SystemExit(f"RAH J02 final append failed ({result}): {output}")
    _, generation, sealed = current_state()
    if evidence_ids(sealed) != [f"E{index:04d}" for index in range(1, 81)]:
        raise SystemExit("J02 final did not append exactly E0080")
    if sealed["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
        raise SystemExit("E0080 does not match the J02 closeout hash seal")
    if sealed["loop_state.json"].get("status") != "blocked" or sealed["loop_state.json"].get("blocked_reason") != BLOCK_REASON:
        raise SystemExit("J02 final seal did not retain the exact blocker")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("J02 final seal did not preserve every prior generation")
    integrity = verify_generation_store(77)
    return {
        "mode": "final",
        "parent_generation": parent,
        "generation": generation,
        "evidence_id": FINAL_EVIDENCE_ID,
        "artifact_hashes": hashes,
        "state_verification": integrity,
        "status": "blocked",
        "completion_ready": False,
    }


def verify() -> dict[str, Any]:
    generations = numbered_generations(ROOT / ".rah/ralph")
    if len(generations) == 75:
        return preflight()
    if len(generations) == 76:
        audit.verify_post_core(run_regression=True)
        integrity = verify_generation_store(76)
        if integrity["latest_evidence_id"] != GAP_EVIDENCE_ID:
            raise SystemExit("J02 core latest evidence is not E0079")
        return {**integrity, "mode": "core-verify"}
    if len(generations) != 77:
        raise SystemExit(f"unexpected J02 generation count: {len(generations)}")
    audit.verify_post_core(run_regression=True)
    integrity = verify_generation_store(77)
    if integrity["latest_evidence_id"] != FINAL_EVIDENCE_ID:
        raise SystemExit("J02 final latest evidence is not E0080")
    report = read_json(ATTEMPT / "report.json")
    parent = str(report["rah_state"]["core_generation"])
    summary, _ = final_summary(parent)
    _, _, payloads = current_state()
    if payloads["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
        raise SystemExit("stored E0080 differs from current J02 artifact hashes")
    return {**integrity, "mode": "final-verify", "status": "PASS"}


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
