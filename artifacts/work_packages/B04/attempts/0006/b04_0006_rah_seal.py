#!/usr/bin/env python3
"""Seal B04-0006 projection PASS and package SPEC_GAP in append-only RAH."""

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
ATTEMPT = ROOT / "artifacts/work_packages/B04/attempts/0006"
AUTOMATION = ROOT / ".rah/helpers/recursive-architecture-refactoring-auto/automation"
sys.path.insert(0, str(ATTEMPT))
sys.path.insert(0, str(AUTOMATION))

import build_b04_0006_evidence as evidence  # noqa: E402
import ralph_harness as rh  # noqa: E402
import state_store  # noqa: E402


CORE_PARENT = "000097-8bdfaab8"
AUDIT_EVIDENCE_ID = "E0106"
GAP_EVIDENCE_ID = "E0107"
FINAL_EVIDENCE_ID = "E0108"
PRESERVED_GENERATIONS = [
    "000079-fadeffe1",
    "000080-cccce3eb",
    "000081-843d5565",
    "000082-b49a186b",
    "000083-85fd47c1",
    "000084-016aba75",
    "000085-44f41b7e",
    "000086-8fc2cce9",
    "000087-db6c1b44",
    "000088-a4a7294e",
    "000089-555278db",
    "000090-a3e0bace",
    "000091-2a6ee23b",
    "000092-0e642e4a",
    "000093-d788a6f7",
    "000094-4a1a5233",
    "000095-fba392da",
    "000096-ffc48194",
    "000097-8bdfaab8",
]
BLOCK_REASON = (
    "B04-SG002 requires a product-owner HumanDecision assigning bounded runtime "
    "migration ownership and exact write scope for "
    "src/epistemic_foundry/foundry_kernel/gates.py, "
    "src/epistemic_foundry/verifier_firewall/firewall.py, and related tests, "
    "and authorizing pre-C04 correction attempts for F04 fixtures, J02 sealed "
    "inventory, and S04 manifest binding. B04-0006 projection is verified PASS, "
    "but Python has 52 failures and 15 errors and Node TAP has 11 failures. "
    "C04-0002 and final B04 cannot start; completion_ready=false."
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


def artifact_hashes(names: tuple[str, ...]) -> dict[str, str]:
    result: dict[str, str] = {}
    for name in names:
        path = ATTEMPT / name
        if not path.is_file():
            raise SystemExit(f"required B04-0006 artifact is missing: {name}")
        result[name] = sha256(path)
    return result


def audit_summary() -> str:
    names = (
        "canonical-projection-verification.json",
        "projection.artifact-receipt.json",
        "source-inventory.json",
        "snapshot-inventory.json",
        "installed-wheel-verification.json",
        "full-regression-impact.json",
        "node-failure-inventory.json",
        "dependency-status.json",
        "review.md",
    )
    hashes = artifact_hashes(names)
    return (
        "B04-0006 projection/regression audit under "
        "HD-EF4-C01-SG004-20260730-001: deterministic projection reconciles "
        "126 root schemas plus OpenAPI 3.1.1/33 operations to 127 package "
        f"resources at {evidence.EXPECTED_SOURCE_BUNDLE_HASH}, "
        f"{evidence.EXPECTED_SNAPSHOT_BUNDLE_HASH}, and "
        f"{evidence.EXPECTED_REGISTRY_HASH}; missing/extra/hash mismatch/duplicate "
        "ID counts are zero; targeted tests are 41/41; clean wheel/sdist, "
        "sdist-to-wheel, installed-only, arbitrary-cwd, deterministic rebuild, "
        "tamper/missing rejection and zero fallback success pass. Projection "
        f"verification sha256:{hashes['canonical-projection-verification.json']}; "
        f"receipt sha256:{hashes['projection.artifact-receipt.json']}; installed "
        f"verification sha256:{hashes['installed-wheel-verification.json']}; "
        f"regression sha256:{hashes['full-regression-impact.json']}; Node inventory "
        f"sha256:{hashes['node-failure-inventory.json']}; dependency status "
        f"sha256:{hashes['dependency-status.json']}; review sha256:"
        f"{hashes['review.md']}. Full Python is 916 pass, 52 fail, 15 errors; "
        "Node TAP is 447/458 pass with 11 failures. Projection status PASS; "
        "package status SPEC_GAP; completion_ready=false."
    )


def gap_summary() -> str:
    return (
        "B04-0006 documented SPEC_GAP B04-SG002: the canonical projection is "
        "verified PASS, but the active development manifest assigns no migration "
        "owner or exact scope to the GateDecision producer "
        "src/epistemic_foundry/foundry_kernel/gates.py or the HoldoutManifest "
        "producer src/epistemic_foundry/verifier_firewall/firewall.py, and the "
        "current product decision does not authorize a pre-C04 correction sequence "
        "for the F04 fixtures, J02 sealed inventory, and S04 manifest binding now "
        "failing against the activated contract. B04 cannot broaden another "
        "package's authority or invert the fixed gate order. C04-0002 and final "
        "B04 remain prohibited. A product-owner HumanDecision is required; "
        "completion_ready=false."
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
                key: value for key, value in authority.items() if key != "state_generation"
            }
        if state_store._dump(stripped) == state_store._dump(authority):
            flat_matches += 1
    loop = payloads["loop_state.json"]
    if (
        flat_stamps != 6
        or flat_matches != 6
        or loop.get("status") != "blocked"
        or loop.get("blocked_reason") != BLOCK_REASON
        or loop.get("implementation_gate") != "fail"
        or loop.get("completion_readiness", {}).get("ready") is not False
    ):
        raise SystemExit("RAH blocker state or flat projections are not exact")
    return {
        "attempt_id": evidence.ATTEMPT_ID,
        "completion_ready": False,
        "current_generation": current,
        "evidence_count": len(evidence_ids(payloads)),
        "flat_snapshot_content_matches": flat_matches,
        "flat_snapshot_stamps_verified": flat_stamps,
        "generation_file_hashes_verified": verified_hashes,
        "generation_manifest_sha256": "sha256:"
        + sha256(ralph_root / "generations" / current / "generation-manifest.json"),
        "implementation_gate": "fail",
        "latest_evidence_id": evidence_ids(payloads)[-1],
        "mode": "READ_ONLY",
        "parse_errors": {},
        "ralph_status": "blocked",
        "retained_generation_count": len(generations),
        "retained_generations": generations,
        "status": "PASS",
        "work_package_id": "B04",
    }


def run_preflight() -> dict[str, Any]:
    evidence.verify_evidence(require_closeout=False)
    ralph_root, generation, payloads = current_state()
    if generation != CORE_PARENT:
        raise SystemExit(f"unexpected B04-0006 parent {generation}; expected {CORE_PARENT}")
    if numbered_generations(ralph_root) != PRESERVED_GENERATIONS:
        raise SystemExit("B04-0006 preflight retained-generation inventory changed")
    if evidence_ids(payloads) != [f"E{index:04d}" for index in range(1, 106)]:
        raise SystemExit("B04-0006 preflight requires contiguous E0001-E0105")
    loop = payloads["loop_state.json"]
    if (
        loop.get("status") != "active"
        or loop.get("implementation_gate") != "fail"
        or loop.get("completion_readiness", {}).get("ready") is not False
    ):
        raise SystemExit("preflight requires active/fail/completion_ready=false")
    return {
        "completion_ready": False,
        "generation": generation,
        "latest_evidence_id": "E0105",
        "mode": "preflight",
        "retained_generation_count": len(PRESERVED_GENERATIONS),
        "status": "PASS",
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
        raise SystemExit(f"RAH B04-0006 core append failed ({result}): {output}")
    _, generation, payloads = current_state()
    if not re.fullmatch(r"000098-[0-9a-f]{8}", generation):
        raise SystemExit(f"unexpected B04-0006 core generation: {generation}")
    if evidence_ids(payloads) != [f"E{index:04d}" for index in range(1, 108)]:
        raise SystemExit("B04-0006 core did not append exactly E0106 and E0107")
    entries = payloads["evidence_ledger.json"]["entries"]
    if entries[-2].get("kind") != "evidence" or entries[-2].get("summary") != audit_summary():
        raise SystemExit("E0106 is not the exact projection/regression audit")
    if entries[-1].get("kind") != "documented_gap" or entries[-1].get("summary") != gap_summary():
        raise SystemExit("E0107 is not the exact B04-SG002 documented gap")
    loop = payloads["loop_state.json"]
    if loop.get("status") != "blocked" or loop.get("blocked_reason") != BLOCK_REASON:
        raise SystemExit("RAH did not persist the exact B04-SG002 blocker")
    if loop.get("completion_readiness", {}).get("ready") is not False:
        raise SystemExit("RAH advanced completion_ready during blocker seal")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("B04 core seal did not preserve every prior generation")
    integrity = verify_generation_store(20)
    evidence.build_closeout()
    return {
        "audit_evidence_id": AUDIT_EVIDENCE_ID,
        "completion_ready": False,
        "documented_gap_evidence_id": GAP_EVIDENCE_ID,
        "generation": generation,
        "mode": "core",
        "parent_generation": parent,
        "spec_gap_id": evidence.SPEC_GAP_ID,
        "state_verification": integrity,
        "status": "blocked",
    }


def final_summary(parent: str) -> tuple[str, dict[str, str]]:
    names = (
        "report.json",
        "commands.jsonl",
        "review.md",
        "canonical-projection-verification.json",
        "projection.artifact-receipt.json",
        "source-inventory.json",
        "snapshot-inventory.json",
        "installed-wheel-verification.json",
        "full-regression-impact.json",
        "node-failure-inventory.json",
        "dependency-status.json",
        "rah-core-integrity.json",
        "build_b04_0006_evidence.py",
        "b04_0006_rah_seal.py",
    )
    hashes = artifact_hashes(names)
    summary = (
        f"B04-0006 projection PASS/package SPEC_GAP closeout is hash-sealed "
        f"after core generation {parent}: report sha256:{hashes['report.json']}; "
        f"commands sha256:{hashes['commands.jsonl']}; review sha256:"
        f"{hashes['review.md']}; projection verification sha256:"
        f"{hashes['canonical-projection-verification.json']}; receipt sha256:"
        f"{hashes['projection.artifact-receipt.json']}; regression sha256:"
        f"{hashes['full-regression-impact.json']}; Node inventory sha256:"
        f"{hashes['node-failure-inventory.json']}; dependency status sha256:"
        f"{hashes['dependency-status.json']}; core RAH integrity sha256:"
        f"{hashes['rah-core-integrity.json']}; builder sha256:"
        f"{hashes['build_b04_0006_evidence.py']}; sealer sha256:"
        f"{hashes['b04_0006_rah_seal.py']}. B04-0006 projection remains PASS; "
        "package remains SPEC_GAP B04-SG002; C04-0002 and final B04 are not "
        "started; all prior attempts, RAH evidence/generations and dirty-worktree "
        "changes are preserved; completion_ready=false."
    )
    return summary, hashes


def run_final() -> dict[str, Any]:
    evidence.verify_evidence(require_closeout=True)
    ralph_root, parent, payloads = current_state()
    if not re.fullmatch(r"000098-[0-9a-f]{8}", parent):
        raise SystemExit(f"unexpected B04-0006 final parent: {parent}")
    if evidence_ids(payloads) != [f"E{index:04d}" for index in range(1, 108)]:
        raise SystemExit("B04-0006 final requires preserved E0001-E0107")
    entries = payloads["evidence_ledger.json"]["entries"]
    if entries[-2].get("summary") != audit_summary() or entries[-1].get("summary") != gap_summary():
        raise SystemExit("B04-0006 core summaries changed before final seal")
    report = read_json(ATTEMPT / "report.json")
    rah_state = report.get("rah_state")
    if not isinstance(rah_state, dict) or rah_state.get("core_generation") != parent:
        raise SystemExit("B04-0006 report does not bind the core generation")
    if rah_state.get("audit_evidence_id") != AUDIT_EVIDENCE_ID:
        raise SystemExit("B04-0006 report does not bind E0106")
    if rah_state.get("documented_gap_evidence_id") != GAP_EVIDENCE_ID:
        raise SystemExit("B04-0006 report does not bind E0107")
    if rah_state.get("final_closeout_evidence_id") != FINAL_EVIDENCE_ID:
        raise SystemExit("B04-0006 report does not reserve E0108")
    summary, hashes = final_summary(parent)
    before = numbered_generations(ralph_root)
    result, output = invoke_ralph(
        ["--record-evidence", summary, "--no-increment", "--no-update-current-loop"]
    )
    if result != 0:
        raise SystemExit(f"RAH B04-0006 final append failed ({result}): {output}")
    _, generation, sealed = current_state()
    if not re.fullmatch(r"000099-[0-9a-f]{8}", generation):
        raise SystemExit(f"unexpected B04-0006 final generation: {generation}")
    if evidence_ids(sealed) != [f"E{index:04d}" for index in range(1, 109)]:
        raise SystemExit("B04-0006 final did not append exactly E0108")
    if sealed["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
        raise SystemExit("E0108 does not match the B04-0006 closeout hash seal")
    loop = sealed["loop_state.json"]
    if loop.get("status") != "blocked" or loop.get("blocked_reason") != BLOCK_REASON:
        raise SystemExit("final seal did not preserve the exact B04-SG002 blocker")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("B04 final seal did not preserve every prior generation")
    verification = verify_generation_store(21)
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
    if len(generations) == len(PRESERVED_GENERATIONS):
        return run_preflight()
    if len(generations) == 20:
        result = evidence.verify_evidence(require_closeout=True)
        integrity = verify_generation_store(20)
        if integrity["latest_evidence_id"] != GAP_EVIDENCE_ID:
            raise SystemExit("B04 core latest evidence is not E0107")
        return {**result, "mode": "core-verify", "state_verification": integrity}
    if len(generations) != 21:
        raise SystemExit(f"unexpected B04-0006 generation count: {len(generations)}")
    result = evidence.verify_evidence(require_closeout=True)
    integrity = verify_generation_store(21)
    if integrity["latest_evidence_id"] != FINAL_EVIDENCE_ID:
        raise SystemExit("B04 final latest evidence is not E0108")
    report = read_json(ATTEMPT / "report.json")
    parent = str(report["rah_state"]["core_generation"])
    summary, _ = final_summary(parent)
    _, _, payloads = current_state()
    if payloads["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
        raise SystemExit("stored E0108 differs from current artifact hashes")
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
