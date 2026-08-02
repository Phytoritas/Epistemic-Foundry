#!/usr/bin/env python3
"""Seal C01-0005 SPEC_GAP evidence while preserving every RAH generation."""

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
ATTEMPT = ROOT / "artifacts/work_packages/C01/attempts/0005"
AUTOMATION = ROOT / ".rah/helpers/recursive-architecture-refactoring-auto/automation"
sys.path.insert(0, str(ATTEMPT))
sys.path.insert(0, str(AUTOMATION))

import c01_0005_evidence as evidence  # noqa: E402
import ralph_harness as rh  # noqa: E402
import state_store  # noqa: E402


CORE_PARENT = "000088-a4a7294e"
AUDIT_EVIDENCE_ID = "E0096"
GAP_EVIDENCE_ID = "E0097"
FINAL_EVIDENCE_ID = "E0098"
BLOCK_REASON = (
    "C01-SG004 requires a product-owner HumanDecision assigning exact correction "
    "owners and write scope for MASTER_SPEC.md, manifests/acceptance_matrix.yaml, "
    "tests/contracts/openapi/test_scientific_contracts.py, tests/contracts/openapi/"
    "test_openapi_contract.py, tests/test_contracts.py, tests/test_cli.py, tests/"
    "test_f01_epistemic_work_classifier.py, and tests/packaging/"
    "test_canonical_registry.py, and fixing gate timing so 126-schema oracle and "
    "projection corrections occur before the C01 targeted and C04 full-suite gates "
    "that consume them. C01 cannot infer broad test authority or invert the fixed "
    "C04/B04 order. No product implementation was started; C02 and later packages "
    "remain waiting; completion_ready=false."
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
        raise SystemExit(
            f"expected {expected_count} retained generations ending at {current}, "
            f"found {len(generations)}"
        )
    verified_hashes = 0
    for generation in generations:
        generation_root = ralph_root / "generations" / generation
        manifest = read_json(generation_root / "generation-manifest.json")
        files = manifest.get("files")
        if manifest.get("generation") != generation or not isinstance(files, dict):
            raise SystemExit(f"invalid generation manifest: {generation}")
        if set(files) != set(state_store.GENERATION_FILES):
            raise SystemExit(f"generation file set mismatch: {generation}")
        for name in state_store.GENERATION_FILES:
            if sha256(generation_root / name) != files[name]:
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
            authority = {
                key: value
                for key, value in authority.items()
                if key != "state_generation"
            }
        if state_store._dump(stripped) == state_store._dump(authority):
            flat_matches += 1
    loop = payloads["loop_state.json"]
    if flat_stamps != 6 or flat_matches != 6:
        raise SystemExit("RAH flat projection does not match current authority")
    if loop.get("completion_readiness", {}).get("ready") is not False:
        raise SystemExit("C01-0005 must retain completion_ready=false")
    return {
        "completion_ready": False,
        "current_generation": current,
        "evidence_count": len(evidence_ids(payloads)),
        "flat_snapshot_content_matches": flat_matches,
        "flat_snapshot_stamps_verified": flat_stamps,
        "generation_file_hashes_verified": verified_hashes,
        "generation_manifest_sha256": "sha256:"
        + sha256(ralph_root / "generations" / current / "generation-manifest.json"),
        "latest_evidence_id": evidence_ids(payloads)[-1],
        "ralph_status": loop.get("status"),
        "retained_generation_count": len(generations),
        "retained_generations": generations,
        "status": "PASS",
    }


def audit_summary() -> str:
    return (
        "C01-0005 contract audit under HD-EF4-K01-SG001-20260730-001: the "
        "authoritative attachment, HumanDecision, active binding and successor "
        "manifest hashes pass; the approved target is 126 schemas/examples, while "
        "the untouched pre-implementation tree remains 124/124 and all four newly "
        "authorized schema/example paths are absent. Eight gate-relevant authority/"
        "test surfaces retain 124-era assertions; four have no manifest owner and "
        "four are owned only outside the executable pre-C04 sequence. The current "
        "targeted OpenAPI baseline is 66/66. Audit sha256:"
        f"{sha256(ATTEMPT / 'c01-shared-contract-gap-verification.json')}; "
        f"dependency status sha256:{sha256(ATTEMPT / 'dependency-status.json')}; "
        f"review sha256:{sha256(ATTEMPT / 'review.md')}. Product changes=0; "
        "completion_ready=false."
    )


def gap_summary() -> str:
    return (
        "C01-0005 SPEC_GAP C01-SG004: the 126-schema object contract is defined, "
        "but correction ownership and gate timing for active 124-era authority and "
        "acceptance oracles are not. C01's exact scope excludes those paths; C04 "
        "requires the full Python suite before B04 may repair its projection; and "
        "unowned registry/CLI tests remain stale after projection. Partially applying "
        "the schemas would knowingly make mandatory gates unreachable. This is not "
        "FAIL because implementation was not started against an invented oracle, and "
        "not BLOCKED because no external resource is unavailable. C02 and later "
        "packages remain waiting; completion_ready=false."
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


def run_preflight() -> dict[str, Any]:
    checked = evidence.verify_pre_core(run_regression=True)
    ralph_root, generation, payloads = current_state()
    if generation != CORE_PARENT:
        raise SystemExit(f"unexpected C01-0005 parent {generation}; expected {CORE_PARENT}")
    if evidence_ids(payloads) != [f"E{index:04d}" for index in range(1, 96)]:
        raise SystemExit("C01-0005 preflight requires preserved E0001-E0095")
    generations = numbered_generations(ralph_root)
    if len(generations) != 10 or generations[-1] != generation:
        raise SystemExit("C01-0005 preflight requires all ten retained generations")
    loop = payloads["loop_state.json"]
    if (
        loop.get("status") != "active"
        or loop.get("implementation_gate") != "fail"
        or loop.get("completion_readiness", {}).get("ready") is not False
    ):
        raise SystemExit("C01-0005 preflight requires active/fail/not-ready state")
    return {
        **checked,
        "generation": generation,
        "latest_evidence_id": "E0095",
        "mode": "preflight",
        "retained_generation_count": len(generations),
    }


def run_core() -> dict[str, Any]:
    run_preflight()
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
        raise SystemExit(f"RAH C01-0005 core append failed ({result}): {output}")
    _, generation, payloads = current_state()
    if not re.fullmatch(r"000089-[0-9a-f]{8}", generation):
        raise SystemExit(f"unexpected C01-0005 core generation: {generation}")
    if evidence_ids(payloads) != [f"E{index:04d}" for index in range(1, 98)]:
        raise SystemExit("C01-0005 core did not append exactly E0096 and E0097")
    entries = payloads["evidence_ledger.json"]["entries"]
    if entries[-2].get("kind") != "evidence" or entries[-2].get("summary") != audit_summary():
        raise SystemExit("E0096 is not the exact C01 contract audit")
    if entries[-1].get("kind") != "documented_gap" or entries[-1].get("summary") != gap_summary():
        raise SystemExit("E0097 is not the exact C01-SG004 documented gap")
    loop = payloads["loop_state.json"]
    if loop.get("status") != "blocked" or loop.get("blocked_reason") != BLOCK_REASON:
        raise SystemExit("RAH did not persist the exact C01-SG004 blocker")
    if loop.get("completion_readiness", {}).get("ready") is not False:
        raise SystemExit("RAH advanced completion_ready during C01 blocker seal")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("C01 core seal did not preserve every prior generation")
    integrity = verify_generation_store(11)
    evidence.build_post_core(integrity)
    return {
        "contract_audit_evidence_id": AUDIT_EVIDENCE_ID,
        "documented_gap_evidence_id": GAP_EVIDENCE_ID,
        "generation": generation,
        "mode": "core",
        "parent_generation": parent,
        "spec_gap_id": evidence.SPEC_GAP_ID,
        "state_verification": integrity,
        "status": "blocked",
        "completion_ready": False,
    }


def final_summary(parent: str) -> tuple[str, dict[str, str]]:
    names = (
        "report.json",
        "commands.jsonl",
        "review.md",
        "c01-shared-contract-gap-verification.json",
        "dependency-status.json",
        "rah-core-integrity.json",
        "c01_0005_evidence.py",
        "c01_0005_rah_seal.py",
    )
    hashes = {name: sha256(ATTEMPT / name) for name in names}
    summary = (
        f"C01-0005 SPEC_GAP closeout is hash-sealed after core generation {parent}: "
        f"report sha256:{hashes['report.json']}; commands sha256:"
        f"{hashes['commands.jsonl']}; review sha256:{hashes['review.md']}; audit "
        f"sha256:{hashes['c01-shared-contract-gap-verification.json']}; dependency "
        f"status sha256:{hashes['dependency-status.json']}; core RAH integrity "
        f"sha256:{hashes['rah-core-integrity.json']}; builder sha256:"
        f"{hashes['c01_0005_evidence.py']}; sealer sha256:"
        f"{hashes['c01_0005_rah_seal.py']}. C01 remains SPEC_GAP C01-SG004; "
        "product changes=0; C02 and later packages remain waiting; every prior "
        "attempt, RAH generation and dirty-worktree change is preserved; "
        "completion_ready=false."
    )
    return summary, hashes


def run_final() -> dict[str, Any]:
    evidence.verify_post_core(run_regression=True)
    ralph_root, parent, payloads = current_state()
    if not re.fullmatch(r"000089-[0-9a-f]{8}", parent):
        raise SystemExit(f"unexpected C01-0005 final parent: {parent}")
    if evidence_ids(payloads) != [f"E{index:04d}" for index in range(1, 98)]:
        raise SystemExit("C01-0005 final requires preserved E0001-E0097")
    entries = payloads["evidence_ledger.json"]["entries"]
    if entries[-2].get("summary") != audit_summary() or entries[-1].get("summary") != gap_summary():
        raise SystemExit("C01-0005 core summaries changed before final seal")
    report = read_json(ATTEMPT / "report.json")
    rah_state = report.get("rah_state")
    if not isinstance(rah_state, dict) or rah_state.get("core_generation") != parent:
        raise SystemExit("C01-0005 report does not bind the core generation")
    if rah_state.get("contract_audit_evidence_id") != AUDIT_EVIDENCE_ID:
        raise SystemExit("C01-0005 report does not bind E0096")
    if rah_state.get("documented_gap_evidence_id") != GAP_EVIDENCE_ID:
        raise SystemExit("C01-0005 report does not bind E0097")
    if rah_state.get("final_closeout_evidence_id") != FINAL_EVIDENCE_ID:
        raise SystemExit("C01-0005 report does not reserve E0098")
    summary, hashes = final_summary(parent)
    before = numbered_generations(ralph_root)
    result, output = invoke_ralph(
        ["--record-evidence", summary, "--no-increment", "--no-update-current-loop"]
    )
    if result != 0:
        raise SystemExit(f"RAH C01-0005 final append failed ({result}): {output}")
    _, generation, sealed = current_state()
    if not re.fullmatch(r"000090-[0-9a-f]{8}", generation):
        raise SystemExit(f"unexpected C01-0005 final generation: {generation}")
    if evidence_ids(sealed) != [f"E{index:04d}" for index in range(1, 99)]:
        raise SystemExit("C01-0005 final did not append exactly E0098")
    if sealed["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
        raise SystemExit("E0098 does not match the C01-0005 closeout hash seal")
    loop = sealed["loop_state.json"]
    if loop.get("status") != "blocked" or loop.get("blocked_reason") != BLOCK_REASON:
        raise SystemExit("C01-0005 final seal did not preserve the exact blocker")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("C01 final seal did not preserve every prior generation")
    verification = verify_generation_store(12)
    return {
        "artifact_hashes": hashes,
        "completion_ready": False,
        "evidence_id": FINAL_EVIDENCE_ID,
        "generation": generation,
        "mode": "final",
        "parent_generation": parent,
        "state_verification": verification,
        "status": "blocked",
    }


def run_verify() -> dict[str, Any]:
    generations = numbered_generations(ROOT / ".rah/ralph")
    if len(generations) == 10:
        return run_preflight()
    if len(generations) == 11:
        result = evidence.verify_post_core(run_regression=True)
        integrity = verify_generation_store(11)
        if integrity["latest_evidence_id"] != GAP_EVIDENCE_ID:
            raise SystemExit("C01 core latest evidence is not E0097")
        return {**result, "mode": "core-verify", "state_verification": integrity}
    if len(generations) != 12:
        raise SystemExit(f"unexpected C01-0005 generation count: {len(generations)}")
    result = evidence.verify_post_core(run_regression=True)
    integrity = verify_generation_store(12)
    if integrity["latest_evidence_id"] != FINAL_EVIDENCE_ID:
        raise SystemExit("C01 final latest evidence is not E0098")
    report = read_json(ATTEMPT / "report.json")
    parent = str(report["rah_state"]["core_generation"])
    summary, _ = final_summary(parent)
    _, _, payloads = current_state()
    if payloads["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
        raise SystemExit("stored E0098 differs from current artifact hashes")
    return {
        **result,
        "mode": "final-verify",
        "state_verification": integrity,
        "status": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("preflight", "core", "final", "verify"))
    args = parser.parse_args()
    result = {
        "preflight": run_preflight,
        "core": run_core,
        "final": run_final,
        "verify": run_verify,
    }[args.mode]()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
