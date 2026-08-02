#!/usr/bin/env python3
"""Append M03-0001 core and closeout evidence to the active RAH state."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/M03/attempts/0001"
L03_ATTEMPT = ROOT / "artifacts/work_packages/L03/attempts/0001"
ATTEMPT_ID = "M03-0001"

sys.path.insert(0, str(ATTEMPT))
sys.path.insert(0, str(L03_ATTEMPT))

import build_m03_0001_evidence as evidence  # noqa: E402
import l03_0001_rah_seal as sealed_base  # noqa: E402


EXPECTED_INITIAL_PARENT = "000058-887bab24"
EXPECTED_INITIAL_PARENT_MANIFEST_SHA256 = (
    "97239ee2b5ee41e35cd26ddfce3e5901e96e9753e7a15b71430b8cee82ec4cce"
)
EXPECTED_INITIAL_EVIDENCE = "E0058"
EXPECTED_INITIAL_GENERATION_COUNT = 58
EXPECTED_CORE_EVIDENCE = "E0059"
EXPECTED_FINAL_EVIDENCE = "E0060"
NEXT_ACTIONS = [
    "Recompute and seal the live 156-package DAG after M03-0001 PASS.",
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
            raise SystemExit(f"required M03 artifact is missing: {name}")
        result[name] = sha256(path)
    return result


def core_summary() -> str:
    names = (
        "query-risk-change-impact-verification.json",
        "query-risk-change-impact-verification.artifact-receipt.json",
        "personalization-verification.json",
        "risk-change-impact-verification.json",
        "full-regression-impact.json",
        "dependency-status.json",
        "write-scope-verification.json",
        "syntax-verification.json",
        "targeted-m03-node.junit.xml",
        "combined-m01-m02-m03-node.junit.xml",
        "full-node-suite.junit.xml",
        "full-python-suite.junit.xml",
        "node-test-inventory.json",
        "review.md",
        "attempt-metadata.json",
        "run_m03_0001_checks.py",
        "build_m03_0001_evidence.py",
        "m03_0001_rah_seal.py",
    )
    hashes = artifact_hashes(names)
    return (
        "M03-0001 PASS: deterministic field-weighted Unicode query relevance "
        "is a content-bound artifact over M01 inventory and extraction identities. "
        "Absent query yields null personalization and zero relevance; semantic score "
        "remains explicit null/NOT_COMPUTED. Relevance, intrinsic risk, baseline "
        "centrality, and blast radius remain separate dimensions. Intrinsic risk uses "
        "complete typed authority, write-scope, sensitivity, and mutable-contract "
        "profiles. All 19 M01 edge kinds have explicit impact direction, unresolved "
        "edges remain recorded but excluded, and all eight shared-resource kinds "
        "materialize deterministic pairwise bidirectional effective edges. Multi-source "
        "BFS, cycles, no-change input, canonical equal-distance witnesses, permutation "
        "identity, hash rebuilding, immutability, tampering, and hostile inputs are "
        "verified fail closed. Targeted M03 is 33/33 (personalization 12, blast radius "
        "21); M01+M02+M03 is 80/80; syntax is 6/6; full Node is 693/693 over "
        "69 files; full Python is 1064/1064; codegen is 126/126. "
        f"Verification sha256:{hashes['query-risk-change-impact-verification.json']}; "
        f"receipt sha256:{hashes['query-risk-change-impact-verification.artifact-receipt.json']}; "
        f"personalization sha256:{hashes['personalization-verification.json']}; risk/impact "
        f"sha256:{hashes['risk-change-impact-verification.json']}; regression sha256:"
        f"{hashes['full-regression-impact.json']}; dependency sha256:"
        f"{hashes['dependency-status.json']}; scope sha256:"
        f"{hashes['write-scope-verification.json']}; syntax sha256:"
        f"{hashes['syntax-verification.json']}; targeted JUnit sha256:"
        f"{hashes['targeted-m03-node.junit.xml']}; combined JUnit sha256:"
        f"{hashes['combined-m01-m02-m03-node.junit.xml']}; Node JUnit sha256:"
        f"{hashes['full-node-suite.junit.xml']}; Python JUnit sha256:"
        f"{hashes['full-python-suite.junit.xml']}; inventory-list sha256:"
        f"{hashes['node-test-inventory.json']}; review sha256:{hashes['review.md']}; "
        f"metadata sha256:{hashes['attempt-metadata.json']}; runner sha256:"
        f"{hashes['run_m03_0001_checks.py']}; builder sha256:"
        f"{hashes['build_m03_0001_evidence.py']}; sealer sha256:"
        f"{hashes['m03_0001_rah_seal.py']}. Review is primary-session separate "
        "with actor_independence=false under the product-owner no-subagent "
        "constraint. Global implementation_gate=fail and completion_ready=false."
    )


def final_summary(parent: str) -> tuple[str, dict[str, str]]:
    names = (
        "report.json",
        "commands.jsonl",
        "review.md",
        "query-risk-change-impact-verification.json",
        "query-risk-change-impact-verification.artifact-receipt.json",
        "personalization-verification.json",
        "risk-change-impact-verification.json",
        "full-regression-impact.json",
        "dependency-status.json",
        "write-scope-verification.json",
        "syntax-verification.json",
        "targeted-m03-node.junit.xml",
        "combined-m01-m02-m03-node.junit.xml",
        "full-node-suite.junit.xml",
        "full-python-suite.junit.xml",
        "rah-core-integrity.json",
        "build_m03_0001_evidence.py",
        "m03_0001_rah_seal.py",
    )
    hashes = artifact_hashes(names)
    summary = (
        f"M03-0001 PASS closeout is hash-sealed after core generation {parent}: "
        f"report sha256:{hashes['report.json']}; commands sha256:"
        f"{hashes['commands.jsonl']}; review sha256:{hashes['review.md']}; "
        f"verification sha256:{hashes['query-risk-change-impact-verification.json']}; "
        f"receipt sha256:{hashes['query-risk-change-impact-verification.artifact-receipt.json']}; "
        f"personalization sha256:{hashes['personalization-verification.json']}; risk/impact "
        f"sha256:{hashes['risk-change-impact-verification.json']}; regression sha256:"
        f"{hashes['full-regression-impact.json']}; dependency sha256:"
        f"{hashes['dependency-status.json']}; scope sha256:"
        f"{hashes['write-scope-verification.json']}; syntax sha256:"
        f"{hashes['syntax-verification.json']}; RAH integrity sha256:"
        f"{hashes['rah-core-integrity.json']}; builder sha256:"
        f"{hashes['build_m03_0001_evidence.py']}; sealer sha256:"
        f"{hashes['m03_0001_rah_seal.py']}. Every prior attempt, report, and "
        "generation is preserved. M03-0001 is immutable PASS and the live "
        "156-package DAG must now be recomputed. Global implementation_gate=fail "
        "and completion_ready=false."
    )
    return summary, hashes


_base_verify_generation_store = sealed_base.verify_generation_store
_base_run_preflight = sealed_base.run_preflight
_base_commit_generation = sealed_base.commit_generation


def verify_generation_store(expected_count: int | None = None) -> dict[str, Any]:
    result = _base_verify_generation_store(expected_count)
    result["attempt_id"] = ATTEMPT_ID
    result["work_package_id"] = "M03"
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
        raise SystemExit("M03 parent generation manifest hash changed")
    if result.get("next_evidence_id") != EXPECTED_CORE_EVIDENCE:
        raise SystemExit("M03 preflight does not allocate E0059")
    result["parent_generation_manifest_sha256"] = (
        "sha256:" + EXPECTED_INITIAL_PARENT_MANIFEST_SHA256
    )
    return result


def commit_generation(
    *, payloads: dict[str, Any], summary: str, expected_evidence_id: str
) -> str:
    generation = _base_commit_generation(
        payloads=payloads,
        summary=summary,
        expected_evidence_id=expected_evidence_id,
    )
    status_path = ROOT / ".rah/state/status.json"
    gates_path = ROOT / ".rah/state/gates.json"
    status = sealed_base.read_json(status_path)
    gates = sealed_base.read_json(gates_path)
    note = (
        "M03-0001 query personalization, risk, and change-impact semantics are "
        "evidence-sealed PASS. The live DAG and downstream packages remain; "
        "implementation_gate=fail and completion_ready=false."
    )
    status["implementation_gate"] = "fail"
    status["implementation_gate_note"] = note
    status["next_recommended_action"] = NEXT_ACTIONS[0]
    gate = gates.get("implementation_gate")
    if not isinstance(gate, dict):
        raise SystemExit("M03 RAH implementation gate is malformed")
    gate["note"] = note
    gate["status"] = "fail"
    sealed_base.rh.write_json(status_path, status)
    sealed_base.rh.write_json(gates_path, gates)
    return generation


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
sealed_base.commit_generation = commit_generation


def run_core() -> dict[str, Any]:
    result = sealed_base.run_core()
    if not (
        result.get("evidence_id") == EXPECTED_CORE_EVIDENCE
        and result.get("final_closeout_evidence_id") == EXPECTED_FINAL_EVIDENCE
    ):
        raise SystemExit("M03 core evidence allocation changed")
    return result


def run_final() -> dict[str, Any]:
    result = sealed_base.run_final()
    if result.get("evidence_id") != EXPECTED_FINAL_EVIDENCE:
        raise SystemExit("M03 final evidence allocation changed")
    return result


def run_verify() -> dict[str, Any]:
    result = sealed_base.run_verify()
    if result.get("latest_evidence_id") != EXPECTED_FINAL_EVIDENCE:
        raise SystemExit("M03 verification did not end at E0060")
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
