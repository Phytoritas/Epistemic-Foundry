#!/usr/bin/env python3
"""Append N03-0001 core and closeout evidence to the active RAH state."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/N03/attempts/0001"
N02_ATTEMPT = ROOT / "artifacts/work_packages/N02/attempts/0001"
ATTEMPT_ID = "N03-0001"
sys.path.insert(0, str(ATTEMPT))
sys.path.insert(0, str(N02_ATTEMPT))

import build_n03_0001_evidence as evidence  # noqa: E402
import n02_0001_rah_seal as n02_seal  # noqa: E402


sealed_base = n02_seal.sealed_base
EXPECTED_INITIAL_PARENT = "000071-d52c1b66"
EXPECTED_INITIAL_PARENT_MANIFEST_SHA256 = (
    "f8a351e116a8f3acbab8c2a4bf1c957f8db1d056da47bf2c81dcc0ea1f8fd00e"
)
EXPECTED_INITIAL_EVIDENCE = "E0071"
EXPECTED_INITIAL_GENERATION_COUNT = 71
EXPECTED_CORE_EVIDENCE = "E0072"
EXPECTED_FINAL_EVIDENCE = "E0073"
NEXT_ACTIONS = [
    "Recompute and seal the live 156-package DAG after N03-0001 PASS.",
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
            raise SystemExit(f"required N03 artifact is missing: {name}")
        result[name] = sha256(path)
    return result


def core_summary() -> str:
    names = (
        "scheduler-verification.json",
        "scheduler-verification.artifact-receipt.json",
        "full-regression-impact.json",
        "dependency-status.json",
        "write-scope-verification.json",
        "syntax-verification.json",
        "targeted-n03-node.junit.xml",
        "n01-role-contract-regression.junit.xml",
        "e02-effect-regression.junit.xml",
        "e03-capability-regression.junit.xml",
        "full-node-suite.junit.xml",
        "full-python-suite.junit.xml",
        "node-test-inventory.json",
        "review.md",
        "attempt-metadata.json",
        "run_n03_0001_checks.py",
        "build_n03_0001_evidence.py",
        "n03_0001_rah_seal.py",
    )
    hashes = artifact_hashes(names)
    return (
        "N03-0001 PASS: deterministic DAG compilation rejects unknown, duplicate, "
        "self, hostile, and uncontracted cyclic dependencies. Every real cycle is "
        "bound to one matching hash-valid bounded LoopContract. Readiness requires "
        "successful predecessor terminal receipts. Admission binds resolved inputs, "
        "policy/approval evidence, external capability leases, hard budgets, and "
        "atomic resources without minting authority. Exclusive/quota capacity, node "
        "and resource fencing, exact idempotent lease retry, changed-binding conflict, "
        "immutable attempts, typed retries, monotonic clocks, effect reconciliation, "
        "receipt-bound success, failure propagation, bounded loop dedupe/dry rounds, "
        "command replay, tamper rejection, and immutable snapshots pass. Targeted N03 "
        "is 24/24 (scheduler property 15, resource conflict 9); N01 regression is "
        "21/21; E02 is 19/19; E03 is 30/30; syntax is 5/5; official serial full Node "
        "is 793/793 over 77 files; full Python is 1064/1064; codegen is 126/126. An "
        "earlier diagnostic 792/793 artifact-store concurrency observation reconciled "
        "with isolated 1/1 and complete 793/793 reruns; its original test identifier "
        "was not retained and is not invented. Verification sha256:"
        f"{hashes['scheduler-verification.json']}; receipt sha256:"
        f"{hashes['scheduler-verification.artifact-receipt.json']}; regression sha256:"
        f"{hashes['full-regression-impact.json']}; dependency sha256:"
        f"{hashes['dependency-status.json']}; scope sha256:"
        f"{hashes['write-scope-verification.json']}; syntax sha256:"
        f"{hashes['syntax-verification.json']}; targeted JUnit sha256:"
        f"{hashes['targeted-n03-node.junit.xml']}; N01 JUnit sha256:"
        f"{hashes['n01-role-contract-regression.junit.xml']}; E02 JUnit sha256:"
        f"{hashes['e02-effect-regression.junit.xml']}; E03 JUnit sha256:"
        f"{hashes['e03-capability-regression.junit.xml']}; Node JUnit sha256:"
        f"{hashes['full-node-suite.junit.xml']}; Python JUnit sha256:"
        f"{hashes['full-python-suite.junit.xml']}; inventory sha256:"
        f"{hashes['node-test-inventory.json']}; review sha256:{hashes['review.md']}; "
        f"metadata sha256:{hashes['attempt-metadata.json']}; runner sha256:"
        f"{hashes['run_n03_0001_checks.py']}; builder sha256:"
        f"{hashes['build_n03_0001_evidence.py']}; sealer sha256:"
        f"{hashes['n03_0001_rah_seal.py']}. Review is primary-session separate with "
        "actor_independence=false under the product-owner no-subagent constraint. "
        "Global implementation_gate=fail and completion_ready=false."
    )


def final_summary(parent: str) -> tuple[str, dict[str, str]]:
    names = (
        "report.json",
        "commands.jsonl",
        "review.md",
        "scheduler-verification.json",
        "scheduler-verification.artifact-receipt.json",
        "full-regression-impact.json",
        "dependency-status.json",
        "write-scope-verification.json",
        "syntax-verification.json",
        "targeted-n03-node.junit.xml",
        "n01-role-contract-regression.junit.xml",
        "e02-effect-regression.junit.xml",
        "e03-capability-regression.junit.xml",
        "full-node-suite.junit.xml",
        "full-python-suite.junit.xml",
        "rah-core-integrity.json",
        "build_n03_0001_evidence.py",
        "n03_0001_rah_seal.py",
    )
    hashes = artifact_hashes(names)
    summary = (
        f"N03-0001 PASS closeout is hash-sealed after core generation {parent}: "
        f"report sha256:{hashes['report.json']}; commands sha256:"
        f"{hashes['commands.jsonl']}; review sha256:{hashes['review.md']}; "
        f"verification sha256:{hashes['scheduler-verification.json']}; receipt "
        f"sha256:{hashes['scheduler-verification.artifact-receipt.json']}; regression "
        f"sha256:{hashes['full-regression-impact.json']}; dependency sha256:"
        f"{hashes['dependency-status.json']}; scope sha256:"
        f"{hashes['write-scope-verification.json']}; syntax sha256:"
        f"{hashes['syntax-verification.json']}; RAH integrity sha256:"
        f"{hashes['rah-core-integrity.json']}; builder sha256:"
        f"{hashes['build_n03_0001_evidence.py']}; sealer sha256:"
        f"{hashes['n03_0001_rah_seal.py']}. Every prior attempt, report, and "
        "generation is preserved. N03-0001 is immutable PASS and the live "
        "156-package DAG must now be recomputed. Global implementation_gate=fail "
        "and completion_ready=false."
    )
    return summary, hashes


_base_verify_generation_store = n02_seal._base_verify_generation_store
_base_run_preflight = n02_seal._base_run_preflight
_base_commit_generation = n02_seal._base_commit_generation


def verify_generation_store(expected_count: int | None = None) -> dict[str, Any]:
    result = _base_verify_generation_store(expected_count)
    result["attempt_id"] = ATTEMPT_ID
    result["work_package_id"] = "N03"
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
        raise SystemExit("N03 parent generation manifest hash changed")
    if result.get("next_evidence_id") != EXPECTED_CORE_EVIDENCE:
        raise SystemExit("N03 preflight does not allocate E0072")
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
        "N03-0001 DAG scheduler, lease, retry, resource, fencing, and replay "
        "contracts are evidence-sealed PASS. The live DAG and downstream packages "
        "remain; implementation_gate=fail and completion_ready=false."
    )
    status["implementation_gate"] = "fail"
    status["implementation_gate_note"] = note
    status["next_recommended_action"] = NEXT_ACTIONS[0]
    gate = gates.get("implementation_gate")
    if not isinstance(gate, dict):
        raise SystemExit("N03 RAH implementation gate is malformed")
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
        raise SystemExit("N03 core evidence allocation changed")
    return result


def run_final() -> dict[str, Any]:
    result = sealed_base.run_final()
    if result.get("evidence_id") != EXPECTED_FINAL_EVIDENCE:
        raise SystemExit("N03 final evidence allocation changed")
    return result


def run_verify() -> dict[str, Any]:
    result = sealed_base.run_verify()
    if result.get("latest_evidence_id") != EXPECTED_FINAL_EVIDENCE:
        raise SystemExit("N03 verification did not end at E0073")
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
