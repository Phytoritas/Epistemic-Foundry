#!/usr/bin/env python3
"""Append L04-0001 core and closeout evidence to the active RAH state.

The append-only generation mechanics are reused from the already sealed L03
evidence helper.  This wrapper replaces every package-specific authority,
summary, hash inventory, and preflight boundary before any state mutation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/L04/attempts/0001"
L03_ATTEMPT = ROOT / "artifacts/work_packages/L03/attempts/0001"
ATTEMPT_ID = "L04-0001"

sys.path.insert(0, str(ATTEMPT))
sys.path.insert(0, str(L03_ATTEMPT))

import build_l04_0001_evidence as evidence  # noqa: E402
import l03_0001_rah_seal as sealed_base  # noqa: E402


EXPECTED_INITIAL_PARENT = "000049-9c172548"
EXPECTED_INITIAL_PARENT_MANIFEST_SHA256 = (
    "566f10b8e58cab91bdc8c28e205f69dffac9a78f022147afe4115a9f950cc3dd"
)
EXPECTED_INITIAL_EVIDENCE = "E0049"
EXPECTED_INITIAL_GENERATION_COUNT = 49
EXPECTED_CORE_EVIDENCE = "E0050"
EXPECTED_FINAL_EVIDENCE = "E0051"
NEXT_ACTIONS = [
    "Recompute and seal the live 156-package DAG after L04-0001 PASS.",
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
            raise SystemExit(f"required L04 artifact is missing: {name}")
        result[name] = sha256(path)
    return result


def core_summary() -> str:
    names = (
        "recall-quality-privacy-verification.json",
        "recall-quality-privacy-verification.artifact-receipt.json",
        "full-regression-impact.json",
        "dependency-status.json",
        "write-scope-verification.json",
        "syntax-verification.json",
        "targeted-l04-node.junit.xml",
        "predecessor-l01-node.junit.xml",
        "predecessor-l02-node.junit.xml",
        "predecessor-l03-node.junit.xml",
        "full-node-suite.junit.xml",
        "full-python-suite.junit.xml",
        "node-test-inventory.json",
        "review.md",
        "attempt-metadata.json",
        "run_l04_0001_checks.py",
        "build_l04_0001_evidence.py",
        "l04_0001_rah_seal.py",
    )
    hashes = artifact_hashes(names)
    return (
        "L04-0001 PASS: the fixed recall oracle recovers exact required "
        "memory-ID sets while excluding distractor, expired, private, and "
        "cross-workspace records. It traverses canonical L01 policy, L02 "
        "scoped search, L03 redaction/deduplication, and receipt validation; "
        "selection hashes and replay identity are stable. Cross-workspace "
        "access is default-deny and requires exact USER scope, policy, opt-in, "
        "active consent, and target binding. Prompt-injection-shaped memory "
        "remains untrusted data. Targeted L04 is 25/25 (precision 10/10 and "
        "privacy 15/15); L01 is 27/27; L02 is 41/41; L03 is 44/44; full Node "
        "is 613/613 over 63 files; full Python is 1064/1064; codegen is "
        "126/126. "
        f"Verification sha256:{hashes['recall-quality-privacy-verification.json']}; "
        f"receipt sha256:{hashes['recall-quality-privacy-verification.artifact-receipt.json']}; "
        f"regression sha256:{hashes['full-regression-impact.json']}; dependency "
        f"sha256:{hashes['dependency-status.json']}; scope sha256:"
        f"{hashes['write-scope-verification.json']}; syntax sha256:"
        f"{hashes['syntax-verification.json']}; targeted JUnit sha256:"
        f"{hashes['targeted-l04-node.junit.xml']}; L01 JUnit sha256:"
        f"{hashes['predecessor-l01-node.junit.xml']}; L02 JUnit sha256:"
        f"{hashes['predecessor-l02-node.junit.xml']}; L03 JUnit sha256:"
        f"{hashes['predecessor-l03-node.junit.xml']}; Node JUnit sha256:"
        f"{hashes['full-node-suite.junit.xml']}; Python JUnit sha256:"
        f"{hashes['full-python-suite.junit.xml']}; inventory sha256:"
        f"{hashes['node-test-inventory.json']}; review sha256:"
        f"{hashes['review.md']}; metadata sha256:{hashes['attempt-metadata.json']}; "
        f"runner sha256:{hashes['run_l04_0001_checks.py']}; builder sha256:"
        f"{hashes['build_l04_0001_evidence.py']}; sealer sha256:"
        f"{hashes['l04_0001_rah_seal.py']}. Review is primary-session separate "
        "with actor_independence=false under the product-owner no-subagent "
        "constraint. Global implementation_gate=fail and completion_ready=false."
    )


def final_summary(parent: str) -> tuple[str, dict[str, str]]:
    names = (
        "report.json",
        "commands.jsonl",
        "review.md",
        "recall-quality-privacy-verification.json",
        "recall-quality-privacy-verification.artifact-receipt.json",
        "full-regression-impact.json",
        "dependency-status.json",
        "write-scope-verification.json",
        "syntax-verification.json",
        "targeted-l04-node.junit.xml",
        "predecessor-l01-node.junit.xml",
        "predecessor-l02-node.junit.xml",
        "predecessor-l03-node.junit.xml",
        "full-node-suite.junit.xml",
        "full-python-suite.junit.xml",
        "rah-core-integrity.json",
        "build_l04_0001_evidence.py",
        "l04_0001_rah_seal.py",
    )
    hashes = artifact_hashes(names)
    summary = (
        f"L04-0001 PASS closeout is hash-sealed after core generation {parent}: "
        f"report sha256:{hashes['report.json']}; commands sha256:"
        f"{hashes['commands.jsonl']}; review sha256:{hashes['review.md']}; "
        f"verification sha256:{hashes['recall-quality-privacy-verification.json']}; "
        f"receipt sha256:{hashes['recall-quality-privacy-verification.artifact-receipt.json']}; "
        f"regression sha256:{hashes['full-regression-impact.json']}; dependency "
        f"sha256:{hashes['dependency-status.json']}; scope sha256:"
        f"{hashes['write-scope-verification.json']}; syntax sha256:"
        f"{hashes['syntax-verification.json']}; RAH integrity sha256:"
        f"{hashes['rah-core-integrity.json']}; builder sha256:"
        f"{hashes['build_l04_0001_evidence.py']}; sealer sha256:"
        f"{hashes['l04_0001_rah_seal.py']}. Every prior attempt, report, and "
        "generation is preserved. L04-0001 is immutable PASS and the live "
        "156-package DAG must now be recomputed. Global implementation_gate=fail "
        "and completion_ready=false."
    )
    return summary, hashes


_base_verify_generation_store = sealed_base.verify_generation_store
_base_run_preflight = sealed_base.run_preflight


def verify_generation_store(expected_count: int | None = None) -> dict[str, Any]:
    result = _base_verify_generation_store(expected_count)
    result["attempt_id"] = ATTEMPT_ID
    result["work_package_id"] = "L04"
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
        raise SystemExit("L04 parent generation manifest hash changed")
    if result.get("next_evidence_id") != EXPECTED_CORE_EVIDENCE:
        raise SystemExit("L04 preflight does not allocate E0050")
    result["parent_generation_manifest_sha256"] = (
        "sha256:" + EXPECTED_INITIAL_PARENT_MANIFEST_SHA256
    )
    return result


# Bind the trusted append-only implementation to the L04 package authority.
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
        raise SystemExit("L04 core evidence allocation changed")
    return result


def run_final() -> dict[str, Any]:
    result = sealed_base.run_final()
    if result.get("evidence_id") != EXPECTED_FINAL_EVIDENCE:
        raise SystemExit("L04 final evidence allocation changed")
    return result


def run_verify() -> dict[str, Any]:
    result = sealed_base.run_verify()
    if result.get("latest_evidence_id") != EXPECTED_FINAL_EVIDENCE:
        raise SystemExit("L04 verification did not end at E0051")
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
