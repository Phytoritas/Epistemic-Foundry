#!/usr/bin/env python3
"""Append M01-0001 core and closeout evidence to the active RAH state."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/M01/attempts/0001"
L03_ATTEMPT = ROOT / "artifacts/work_packages/L03/attempts/0001"
ATTEMPT_ID = "M01-0001"

sys.path.insert(0, str(ATTEMPT))
sys.path.insert(0, str(L03_ATTEMPT))

import build_m01_0001_evidence as evidence  # noqa: E402
import l03_0001_rah_seal as sealed_base  # noqa: E402


EXPECTED_INITIAL_PARENT = "000052-701ded75"
EXPECTED_INITIAL_PARENT_MANIFEST_SHA256 = (
    "610cb34a5910f13e364dbf639eb7ff6cdf5d58cd6db2753bf8075569b58ef281"
)
EXPECTED_INITIAL_EVIDENCE = "E0052"
EXPECTED_INITIAL_GENERATION_COUNT = 52
EXPECTED_CORE_EVIDENCE = "E0053"
EXPECTED_FINAL_EVIDENCE = "E0054"
NEXT_ACTIONS = [
    "Recompute and seal the live 156-package DAG after M01-0001 PASS.",
    "Execute the resulting earliest dependency-ready package serially.",
    "Keep implementation_gate=fail and completion_ready=false until every package-level objective gate passes.",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_hashes(names: tuple[str, ...]) -> dict[str, str]:
    result: dict[str, str] = {}
    for name in names:
        path = ATTEMPT / name
        if not path.is_file():
            raise SystemExit(f"required M01 artifact is missing: {name}")
        result[name] = sha256(path)
    return result


def core_summary() -> str:
    names = (
        "typed-inventory-edge-verification.json",
        "typed-inventory-edge-verification.artifact-receipt.json",
        "inventory-verification.json",
        "edge-resolution-verification.json",
        "full-regression-impact.json",
        "dependency-status.json",
        "write-scope-verification.json",
        "syntax-verification.json",
        "targeted-m01-node.junit.xml",
        "full-node-suite.junit.xml",
        "full-python-suite.junit.xml",
        "node-test-inventory.json",
        "review.md",
        "attempt-metadata.json",
        "run_m01_0001_checks.py",
        "build_m01_0001_evidence.py",
        "m01_0001_rah_seal.py",
    )
    hashes = artifact_hashes(names)
    return (
        "M01-0001 PASS: a pure deterministic mapper indexes explicit CODE, "
        "RESEARCH, and ARTIFACT layers from a frozen logical snapshot while "
        "separating SOURCE, DIST, GENERATED, VENDOR, TEST, RESEARCH, and "
        "ARTIFACT source classes. Portable paths, locators, hashes, unreadable "
        "paths, duplicate identities, hostile wrappers, and cyclic canonical "
        "input are fail-closed. Typed dependency and provenance edges retain "
        "direction, owner, source locator, identity namespace, and explicit "
        "resolved/unresolved partitions; missing targets remain TARGET_NOT_FOUND "
        "or MISSING_TARGET_LOCATOR and are never suppressed. Hashes, IDs, "
        "immutability, permutation stability, and tamper rejection pass. M01 "
        "emits no ranking, centrality, personalization, or score. Targeted M01 "
        "is 22/22 (inventory 11/11 and edges 11/11); syntax is 4/4; full Node "
        "is 635/635 over 65 files; full Python is 1064/1064; codegen is 126/126. "
        f"Combined verification sha256:{hashes['typed-inventory-edge-verification.json']}; "
        f"receipt sha256:{hashes['typed-inventory-edge-verification.artifact-receipt.json']}; "
        f"inventory sha256:{hashes['inventory-verification.json']}; edge sha256:"
        f"{hashes['edge-resolution-verification.json']}; regression sha256:"
        f"{hashes['full-regression-impact.json']}; dependency sha256:"
        f"{hashes['dependency-status.json']}; scope sha256:"
        f"{hashes['write-scope-verification.json']}; syntax sha256:"
        f"{hashes['syntax-verification.json']}; targeted JUnit sha256:"
        f"{hashes['targeted-m01-node.junit.xml']}; Node JUnit sha256:"
        f"{hashes['full-node-suite.junit.xml']}; Python JUnit sha256:"
        f"{hashes['full-python-suite.junit.xml']}; inventory-list sha256:"
        f"{hashes['node-test-inventory.json']}; review sha256:{hashes['review.md']}; "
        f"metadata sha256:{hashes['attempt-metadata.json']}; runner sha256:"
        f"{hashes['run_m01_0001_checks.py']}; builder sha256:"
        f"{hashes['build_m01_0001_evidence.py']}; sealer sha256:"
        f"{hashes['m01_0001_rah_seal.py']}. Review is primary-session separate "
        "with actor_independence=false under the product-owner no-subagent "
        "constraint. Global implementation_gate=fail and completion_ready=false."
    )


def final_summary(parent: str) -> tuple[str, dict[str, str]]:
    names = (
        "report.json",
        "commands.jsonl",
        "review.md",
        "typed-inventory-edge-verification.json",
        "typed-inventory-edge-verification.artifact-receipt.json",
        "inventory-verification.json",
        "edge-resolution-verification.json",
        "full-regression-impact.json",
        "dependency-status.json",
        "write-scope-verification.json",
        "syntax-verification.json",
        "targeted-m01-node.junit.xml",
        "full-node-suite.junit.xml",
        "full-python-suite.junit.xml",
        "rah-core-integrity.json",
        "build_m01_0001_evidence.py",
        "m01_0001_rah_seal.py",
    )
    hashes = artifact_hashes(names)
    summary = (
        f"M01-0001 PASS closeout is hash-sealed after core generation {parent}: "
        f"report sha256:{hashes['report.json']}; commands sha256:"
        f"{hashes['commands.jsonl']}; review sha256:{hashes['review.md']}; "
        f"combined verification sha256:{hashes['typed-inventory-edge-verification.json']}; "
        f"receipt sha256:{hashes['typed-inventory-edge-verification.artifact-receipt.json']}; "
        f"inventory sha256:{hashes['inventory-verification.json']}; edge sha256:"
        f"{hashes['edge-resolution-verification.json']}; regression sha256:"
        f"{hashes['full-regression-impact.json']}; dependency sha256:"
        f"{hashes['dependency-status.json']}; scope sha256:"
        f"{hashes['write-scope-verification.json']}; syntax sha256:"
        f"{hashes['syntax-verification.json']}; RAH integrity sha256:"
        f"{hashes['rah-core-integrity.json']}; builder sha256:"
        f"{hashes['build_m01_0001_evidence.py']}; sealer sha256:"
        f"{hashes['m01_0001_rah_seal.py']}. Every prior attempt, report, and "
        "generation is preserved. M01-0001 is immutable PASS and the live "
        "156-package DAG must now be recomputed. Global implementation_gate=fail "
        "and completion_ready=false."
    )
    return summary, hashes


_base_verify_generation_store = sealed_base.verify_generation_store
_base_run_preflight = sealed_base.run_preflight


def verify_generation_store(expected_count: int | None = None) -> dict[str, Any]:
    result = _base_verify_generation_store(expected_count)
    result["attempt_id"] = ATTEMPT_ID
    result["work_package_id"] = "M01"
    return result


def run_preflight() -> dict[str, Any]:
    result = _base_run_preflight()
    manifest = (
        ROOT
        / ".rah/ralph/generations"
        / EXPECTED_INITIAL_PARENT
        / "generation-manifest.json"
    )
    if sha256(manifest) != EXPECTED_INITIAL_PARENT_MANIFEST_SHA256:
        raise SystemExit("M01 parent generation manifest hash changed")
    if result.get("next_evidence_id") != EXPECTED_CORE_EVIDENCE:
        raise SystemExit("M01 preflight does not allocate E0053")
    result["parent_generation_manifest_sha256"] = (
        "sha256:" + EXPECTED_INITIAL_PARENT_MANIFEST_SHA256
    )
    return result


sealed_base.ROOT = ROOT
sealed_base.ATTEMPT = ATTEMPT
sealed_base.ATTEMPT_ID = ATTEMPT_ID
sealed_base.evidence = evidence
sealed_base.EXPECTED_INITIAL_PARENT = EXPECTED_INITIAL_PARENT
sealed_base.EXPECTED_INITIAL_EVIDENCE = EXPECTED_INITIAL_EVIDENCE
sealed_base.EXPECTED_INITIAL_GENERATION_COUNT = EXPECTED_INITIAL_GENERATION_COUNT
sealed_base.NEXT_ACTIONS = NEXT_ACTIONS
sealed_base.core_summary = core_summary
sealed_base.final_summary = final_summary
sealed_base.verify_generation_store = verify_generation_store
sealed_base.run_preflight = run_preflight


def run_core() -> dict[str, Any]:
    result = sealed_base.run_core()
    if not (
        result.get("evidence_id") == EXPECTED_CORE_EVIDENCE
        and result.get("final_closeout_evidence_id") == EXPECTED_FINAL_EVIDENCE
    ):
        raise SystemExit("M01 core evidence allocation changed")
    return result


def run_final() -> dict[str, Any]:
    result = sealed_base.run_final()
    if result.get("evidence_id") != EXPECTED_FINAL_EVIDENCE:
        raise SystemExit("M01 final evidence allocation changed")
    return result


def run_verify() -> dict[str, Any]:
    result = sealed_base.run_verify()
    if result.get("latest_evidence_id") != EXPECTED_FINAL_EVIDENCE:
        raise SystemExit("M01 verification did not end at E0054")
    return result


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
