#!/usr/bin/env python3
"""Seal C01-0008 SPEC_GAP evidence without rewriting any prior RAH state."""

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
ATTEMPT = ROOT / "artifacts/work_packages/C01/attempts/0008"
AUTOMATION = ROOT / ".rah/helpers/recursive-architecture-refactoring-auto/automation"
sys.path.insert(0, str(ATTEMPT))
sys.path.insert(0, str(AUTOMATION))

import build_c01_0008_evidence as evidence  # noqa: E402
import ralph_harness as rh  # noqa: E402
import state_store  # noqa: E402


EXPECTED_PARENT = "000085-3604c349"
EXPECTED_PARENT_EVIDENCE = "E0085"
EXPECTED_PARENT_GENERATION_COUNT = 85
AUDIT_EVIDENCE_ID = "E0086"
GAP_EVIDENCE_ID = "E0087"
FINAL_EVIDENCE_ID = "E0088"
SPEC_GAP_ID = "C01-SG005"
BLOCK_REASON = (
    "C01-SG005 requires a product-owner HumanDecision authorizing a new J02 "
    "correction attempt for plugins/epistemic-foundry/skills/skill-inventory.json, "
    "a new S04 correction attempt for manifests/source_bindings/development-"
    "manifest.binding.json, and a following C01 revalidation attempt. C01-0008 "
    "verified the strict RetrievalCandidate contract at 127 schemas/examples, but "
    "the full Node gate now has two stale J02 MASTER_SPEC authority bindings and "
    "one stale S04 development-manifest successor binding. C01 owns neither file "
    "and the active serial decision does not authorize J02-0004 or S04-0004. "
    "C02-0004 and all later attempts remain waiting; completion_ready=false."
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
    identifiers = [
        str(row.get("id")) for row in ledger["entries"] if isinstance(row, dict)
    ]
    if any(re.fullmatch(r"E\d{4,}", value) is None for value in identifiers):
        raise SystemExit("RAH evidence ledger contains a malformed evidence ID")
    return identifiers


def expected_ids(high_water: int) -> list[str]:
    return [f"E{index:04d}" for index in range(1, high_water + 1)]


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


def artifact_hashes(names: tuple[str, ...]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for name in names:
        path = ATTEMPT / name
        if not path.is_file():
            raise SystemExit(f"required C01-0008 artifact is missing: {name}")
        hashes[name] = sha256(path)
    return hashes


def audit_summary() -> str:
    names = (
        "canonical-contract-verification.json",
        "retrieval-candidate-verification.json",
        "full-regression-impact.json",
        "write-scope-verification.json",
        "phase-artifact-reconciliation.json",
        "dependency-status.json",
        "junit-normalization-verification.json",
        "targeted-contracts.junit.xml",
        "full-python-suite.junit.xml",
        "full-node-suite.junit.xml",
        "review.md",
        "build_c01_0008_evidence.py",
        "c01_0008_rah_seal.py",
    )
    hashes = artifact_hashes(names)
    return (
        "C01-0008 contract audit: the strict RetrievalCandidate migration is "
        "VERIFIED and the canonical contract is CONFORMANT at 127 Draft 2020-12 "
        "schemas, 127 one-to-one validating examples, OpenAPI 3.1.1 and 33 unique "
        "operations. Candidate ID, query hash and content hash recompute; missing, "
        "unknown and tampered fields fail closed. Targeted contracts are 104/104. "
        "Full Python is 1056 pass and exactly 17 expected B04-0009 projection "
        "failures. Full Node is 817 pass and exactly three new cross-package "
        "authority-projection failures: J02 x2 and S04 x1. Contract sha256:"
        f"{hashes['canonical-contract-verification.json']}; RetrievalCandidate "
        f"sha256:{hashes['retrieval-candidate-verification.json']}; regression "
        f"sha256:{hashes['full-regression-impact.json']}; write scope sha256:"
        f"{hashes['write-scope-verification.json']}; phase reconciliation sha256:"
        f"{hashes['phase-artifact-reconciliation.json']}; dependency sha256:"
        f"{hashes['dependency-status.json']}; normalization sha256:"
        f"{hashes['junit-normalization-verification.json']}; targeted JUnit sha256:"
        f"{hashes['targeted-contracts.junit.xml']}; Python JUnit sha256:"
        f"{hashes['full-python-suite.junit.xml']}; Node JUnit sha256:"
        f"{hashes['full-node-suite.junit.xml']}; review sha256:{hashes['review.md']}; "
        f"builder sha256:{hashes['build_c01_0008_evidence.py']}; sealer sha256:"
        f"{hashes['c01_0008_rah_seal.py']}. Review is primary-session separate "
        "with actor_independence=false under the no-subagent contract. "
        "completion_ready=false."
    )


def gap_summary() -> str:
    regression = read_json(ATTEMPT / "full-regression-impact.json")
    j02 = regression["authority_projection_drift"]["J02"]
    s04 = regression["authority_projection_drift"]["S04"]
    return (
        "C01-0008 SPEC_GAP C01-SG005: implementation_status=VERIFIED and "
        "contract_status=CONFORMANT, but package_status=SPEC_GAP. J02's sealed "
        "skill inventory still binds MASTER_SPEC sha256:"
        f"{j02['stale_master_spec_sha256'].removeprefix('sha256:')} while current "
        f"MASTER_SPEC is {j02['current_master_spec_sha256']}; S04's binding still "
        "records development-manifest successor sha256:"
        f"{s04['stale_successor_sha256'].removeprefix('sha256:')} while the current "
        f"manifest is {s04['current_manifest_sha256']}. The unchanged J02 and S04 "
        "files exactly match their prior PASS attempt hashes, proving C01 did not "
        "write outside scope. Resolving them requires prospectively authorized "
        "J02-0004 and S04-0004 corrections followed by C01-0009 revalidation; "
        "C01 cannot invent that cross-package sequence. This is not FAIL because "
        "the C01 contract implementation passes, and not BLOCKED because no "
        "external resource is unavailable. C02 and later attempts remain waiting; "
        "completion_ready=false."
    )


def final_summary(parent: str) -> tuple[str, dict[str, str]]:
    names = (
        "report.json",
        "commands.jsonl",
        "review.md",
        "canonical-contract-verification.json",
        "retrieval-candidate-verification.json",
        "full-regression-impact.json",
        "write-scope-verification.json",
        "phase-artifact-reconciliation.json",
        "dependency-status.json",
        "junit-normalization-verification.json",
        "targeted-contracts.junit.xml",
        "full-python-suite.junit.xml",
        "full-node-suite.junit.xml",
        "rah-core-integrity.json",
        "build_c01_0008_evidence.py",
        "c01_0008_rah_seal.py",
    )
    hashes = artifact_hashes(names)
    summary = (
        f"C01-0008 SPEC_GAP closeout is hash-sealed after core generation {parent}: "
        f"report sha256:{hashes['report.json']}; commands sha256:"
        f"{hashes['commands.jsonl']}; review sha256:{hashes['review.md']}; contract "
        f"sha256:{hashes['canonical-contract-verification.json']}; candidate "
        f"sha256:{hashes['retrieval-candidate-verification.json']}; regression "
        f"sha256:{hashes['full-regression-impact.json']}; scope sha256:"
        f"{hashes['write-scope-verification.json']}; phase sha256:"
        f"{hashes['phase-artifact-reconciliation.json']}; dependency sha256:"
        f"{hashes['dependency-status.json']}; normalization sha256:"
        f"{hashes['junit-normalization-verification.json']}; targeted JUnit sha256:"
        f"{hashes['targeted-contracts.junit.xml']}; Python JUnit sha256:"
        f"{hashes['full-python-suite.junit.xml']}; Node JUnit sha256:"
        f"{hashes['full-node-suite.junit.xml']}; RAH core integrity sha256:"
        f"{hashes['rah-core-integrity.json']}; builder sha256:"
        f"{hashes['build_c01_0008_evidence.py']}; sealer sha256:"
        f"{hashes['c01_0008_rah_seal.py']}. C01-0008 remains immutable SPEC_GAP "
        "C01-SG005 with implementation VERIFIED; all 85 prior generations, prior "
        "attempts and dirty-worktree content are preserved. C02-0004 and later "
        "attempts remain waiting; completion_ready=false."
    )
    return summary, hashes


def verify_generation_store(expected_count: int) -> dict[str, Any]:
    ralph_root, current, payloads = current_state()
    generations = numbered_generations(ralph_root)
    if len(generations) != expected_count or generations[-1] != current:
        raise SystemExit(
            f"expected {expected_count} retained generations ending at {current}, "
            f"found {len(generations)}"
        )
    checked = 0
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
            checked += 1
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
    goal = payloads["goal.json"]
    if flat_stamps != 6 or flat_matches != 6:
        raise SystemExit("RAH flat projection does not match current authority")
    if loop.get("completion_readiness", {}).get("ready") is not False:
        raise SystemExit("C01-0008 must retain completion_ready=false")
    if expected_count > EXPECTED_PARENT_GENERATION_COUNT:
        if (
            loop.get("status") != "blocked"
            or goal.get("status") != "blocked"
            or loop.get("blocked_reason") != BLOCK_REASON
            or loop.get("implementation_gate") != "fail"
        ):
            raise SystemExit("C01-0008 blocked RAH state is inconsistent")
    identifiers = evidence_ids(payloads)
    return {
        "attempt_id": "C01-0008",
        "completion_ready": False,
        "current_generation": current,
        "evidence_count": len(identifiers),
        "flat_snapshot_content_matches": flat_matches,
        "flat_snapshot_stamps_verified": flat_stamps,
        "generation_file_hashes_verified": checked,
        "generation_manifest_sha256": "sha256:"
        + sha256(ralph_root / "generations" / current / "generation-manifest.json"),
        "implementation_gate": loop.get("implementation_gate"),
        "latest_evidence_id": identifiers[-1],
        "ralph_goal_status": goal.get("status"),
        "ralph_status": loop.get("status"),
        "retained_generation_count": len(generations),
        "retained_generations": generations,
        "spec_gap_id": SPEC_GAP_ID,
        "status": "PASS",
        "work_package_id": "C01",
    }


def preflight() -> dict[str, Any]:
    checked = evidence.verify()
    ralph_root, generation, payloads = current_state()
    if generation != EXPECTED_PARENT:
        raise SystemExit(
            f"unexpected C01-0008 parent {generation}; expected {EXPECTED_PARENT}"
        )
    if evidence_ids(payloads) != expected_ids(85):
        raise SystemExit("C01-0008 preflight requires preserved E0001-E0085")
    generations = numbered_generations(ralph_root)
    if (
        len(generations) != EXPECTED_PARENT_GENERATION_COUNT
        or generations[-1] != generation
    ):
        raise SystemExit("C01-0008 preflight requires all 85 prior generations")
    loop = payloads["loop_state.json"]
    goal = payloads["goal.json"]
    if loop.get("status") != "active" or goal.get("status") != "active":
        raise SystemExit("C01-0008 preflight requires active goal and loop")
    if loop.get("completion_readiness", {}).get("ready") is not False:
        raise SystemExit("C01-0008 preflight requires completion_ready=false")
    report = read_json(ATTEMPT / "report.json")
    if "rah_state" in report:
        raise SystemExit("C01-0008 report is already RAH-bound")
    return {
        **checked,
        "generation": generation,
        "latest_evidence_id": EXPECTED_PARENT_EVIDENCE,
        "mode": "preflight",
        "retained_generation_count": len(generations),
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
        raise SystemExit(f"RAH C01-0008 core append failed ({result}): {output}")
    _, generation, payloads = current_state()
    if not re.fullmatch(r"000086-[0-9a-f]{8}", generation):
        raise SystemExit(f"unexpected C01-0008 core generation: {generation}")
    if evidence_ids(payloads) != expected_ids(87):
        raise SystemExit("C01-0008 core did not append exactly E0086 and E0087")
    entries = payloads["evidence_ledger.json"]["entries"]
    if (
        entries[-2].get("kind") != "evidence"
        or entries[-2].get("summary") != audit_summary()
    ):
        raise SystemExit("E0086 is not the exact C01-0008 contract audit")
    if (
        entries[-1].get("kind") != "documented_gap"
        or entries[-1].get("summary") != gap_summary()
    ):
        raise SystemExit("E0087 is not the exact C01-SG005 documented gap")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("C01-0008 core did not preserve every prior generation")
    integrity = verify_generation_store(86)
    write_json(ATTEMPT / "rah-core-integrity.json", integrity)
    evidence.bind_rah_state(
        core_generation=generation,
        contract_audit_evidence_id=AUDIT_EVIDENCE_ID,
        documented_gap_evidence_id=GAP_EVIDENCE_ID,
        final_closeout_evidence_id=FINAL_EVIDENCE_ID,
    )
    evidence.verify()
    return {
        "completion_ready": False,
        "contract_audit_evidence_id": AUDIT_EVIDENCE_ID,
        "documented_gap_evidence_id": GAP_EVIDENCE_ID,
        "final_closeout_evidence_id": FINAL_EVIDENCE_ID,
        "generation": generation,
        "mode": "core",
        "parent_generation": parent,
        "spec_gap_id": SPEC_GAP_ID,
        "state_verification": integrity,
        "status": "blocked",
    }


def final() -> dict[str, Any]:
    evidence.verify()
    ralph_root, parent, payloads = current_state()
    if not re.fullmatch(r"000086-[0-9a-f]{8}", parent):
        raise SystemExit(f"unexpected C01-0008 final parent: {parent}")
    if evidence_ids(payloads) != expected_ids(87):
        raise SystemExit("C01-0008 final requires preserved E0001-E0087")
    entries = payloads["evidence_ledger.json"]["entries"]
    if entries[-2].get("summary") != audit_summary():
        raise SystemExit("C01-0008 audit summary changed before final seal")
    if entries[-1].get("summary") != gap_summary():
        raise SystemExit("C01-0008 gap summary changed before final seal")
    report = read_json(ATTEMPT / "report.json")
    rah_state = report.get("rah_state")
    if not isinstance(rah_state, dict) or rah_state.get("core_generation") != parent:
        raise SystemExit("C01-0008 report does not bind the core generation")
    if rah_state.get("contract_audit_evidence_id") != AUDIT_EVIDENCE_ID:
        raise SystemExit("C01-0008 report does not bind E0086")
    if rah_state.get("documented_gap_evidence_id") != GAP_EVIDENCE_ID:
        raise SystemExit("C01-0008 report does not bind E0087")
    if rah_state.get("final_closeout_evidence_id") != FINAL_EVIDENCE_ID:
        raise SystemExit("C01-0008 report does not reserve E0088")
    summary, hashes = final_summary(parent)
    before = numbered_generations(ralph_root)
    result, output = invoke_ralph(
        ["--record-evidence", summary, "--no-increment", "--no-update-current-loop"]
    )
    if result != 0:
        raise SystemExit(f"RAH C01-0008 final append failed ({result}): {output}")
    _, generation, sealed = current_state()
    if not re.fullmatch(r"000087-[0-9a-f]{8}", generation):
        raise SystemExit(f"unexpected C01-0008 final generation: {generation}")
    if evidence_ids(sealed) != expected_ids(88):
        raise SystemExit("C01-0008 final did not append exactly E0088")
    if sealed["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
        raise SystemExit("E0088 does not match the C01-0008 closeout hash seal")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("C01-0008 final did not preserve every prior generation")
    verification = verify_generation_store(87)
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


def verify() -> dict[str, Any]:
    generations = numbered_generations(ROOT / ".rah/ralph")
    if len(generations) == 85:
        return preflight()
    if len(generations) == 86:
        result = evidence.verify()
        integrity = verify_generation_store(86)
        if integrity["latest_evidence_id"] != GAP_EVIDENCE_ID:
            raise SystemExit("C01-0008 core tail is not E0087")
        return {**result, "mode": "core-verify", "state_verification": integrity}
    if len(generations) != 87:
        raise SystemExit(f"unexpected C01-0008 generation count: {len(generations)}")
    result = evidence.verify()
    integrity = verify_generation_store(87)
    if integrity["latest_evidence_id"] != FINAL_EVIDENCE_ID:
        raise SystemExit("C01-0008 final tail is not E0088")
    report = read_json(ATTEMPT / "report.json")
    parent = str(report["rah_state"]["core_generation"])
    summary, hashes = final_summary(parent)
    _, _, payloads = current_state()
    if payloads["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
        raise SystemExit("stored E0088 differs from current C01-0008 artifact hashes")
    return {
        **result,
        "artifact_hashes": hashes,
        "mode": "final-verify",
        "state_verification": integrity,
        "status": "PASS",
    }


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
