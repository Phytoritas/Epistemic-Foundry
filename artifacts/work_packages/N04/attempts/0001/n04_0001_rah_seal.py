#!/usr/bin/env python3
"""Append N04-0001 core and closeout evidence to the active RAH state."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/N04/attempts/0001"
N03_ATTEMPT = ROOT / "artifacts/work_packages/N03/attempts/0001"
ATTEMPT_ID = "N04-0001"
sys.path.insert(0, str(ATTEMPT))
sys.path.insert(0, str(N03_ATTEMPT))

import build_n04_0001_evidence as evidence  # noqa: E402
import n03_0001_rah_seal as n03_seal  # noqa: E402


sealed_base = n03_seal.sealed_base
EXPECTED_INITIAL_PARENT = "000075-9252a1f0"
EXPECTED_INITIAL_PARENT_MANIFEST_SHA256 = (
    "970f54fe22e146978d2c716bc2dc7e1c11e3f0223a88b802b1ad835150cae4a1"
)
EXPECTED_INITIAL_EVIDENCE = "E0075"
EXPECTED_INITIAL_GENERATION_COUNT = 75
EXPECTED_CORE_EVIDENCE = "E0076"
EXPECTED_FINAL_EVIDENCE = "E0077"
NEXT_ACTIONS = [
    "Recompute and seal the live 156-package DAG after N04-0001 PASS.",
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
            raise SystemExit(f"required N04 artifact is missing: {name}")
        result[name] = sha256(path)
    return result


def core_summary() -> str:
    names = (
        "fan-in-verification.json",
        "fan-in-verification.artifact-receipt.json",
        "full-regression-impact.json",
        "dependency-status.json",
        "write-scope-verification.json",
        "syntax-verification.json",
        "targeted-n04-node.junit.xml",
        "n02-adapter-regression.junit.xml",
        "n03-scheduler-regression.junit.xml",
        "full-node-suite.junit.xml",
        "full-python-suite.junit.xml",
        "node-test-inventory.json",
        "review.md",
        "attempt-metadata.json",
        "run_n04_0001_checks.py",
        "build_n04_0001_evidence.py",
        "n04_0001_rah_seal.py",
    )
    hashes = artifact_hashes(names)
    return (
        "N04-0001 PASS: exact N02 dispatch descriptors and N03 replayed scheduler "
        "state are bound into a deterministic immutable fan-in decision. Dispatch, "
        "role, spawn, scheduler, result, completeness, business-artifact, terminal-"
        "receipt, and expected/actual counts reconcile exactly; missing, duplicate, "
        "unexpected, fabricated, truncated, non-terminal, prose-only, and partial "
        "fan-in paths fail closed. Independent review is sealed and hash-bound to "
        "the exact dispatch, scheduler state, command log, maker receipts and output "
        "hashes; the reviewer must be a distinct actor and independence group, run "
        "after every maker, return PASS, and emit the review artifact. Author self-"
        "approval is forbidden. Targeted N04 is 26/26 (missing-node 14, independent-"
        "review 12); N02 regression is 29/29; N03 regression is 24/24; syntax is "
        "4/4; full Node is 819/819 over 79 files; full Python is 1064/1064; codegen "
        "is 126/126. Verification sha256:"
        f"{hashes['fan-in-verification.json']}; receipt sha256:"
        f"{hashes['fan-in-verification.artifact-receipt.json']}; regression sha256:"
        f"{hashes['full-regression-impact.json']}; dependency sha256:"
        f"{hashes['dependency-status.json']}; scope sha256:"
        f"{hashes['write-scope-verification.json']}; syntax sha256:"
        f"{hashes['syntax-verification.json']}; targeted JUnit sha256:"
        f"{hashes['targeted-n04-node.junit.xml']}; N02 JUnit sha256:"
        f"{hashes['n02-adapter-regression.junit.xml']}; N03 JUnit sha256:"
        f"{hashes['n03-scheduler-regression.junit.xml']}; Node JUnit sha256:"
        f"{hashes['full-node-suite.junit.xml']}; Python JUnit sha256:"
        f"{hashes['full-python-suite.junit.xml']}; inventory sha256:"
        f"{hashes['node-test-inventory.json']}; review sha256:{hashes['review.md']}; "
        f"metadata sha256:{hashes['attempt-metadata.json']}; runner sha256:"
        f"{hashes['run_n04_0001_checks.py']}; builder sha256:"
        f"{hashes['build_n04_0001_evidence.py']}; sealer sha256:"
        f"{hashes['n04_0001_rah_seal.py']}. Review is primary-session separate with "
        "actor_independence=false under the product-owner no-subagent constraint. "
        "Global implementation_gate=fail and completion_ready=false."
    )


def final_summary(parent: str) -> tuple[str, dict[str, str]]:
    names = (
        "report.json",
        "commands.jsonl",
        "review.md",
        "fan-in-verification.json",
        "fan-in-verification.artifact-receipt.json",
        "full-regression-impact.json",
        "dependency-status.json",
        "write-scope-verification.json",
        "syntax-verification.json",
        "targeted-n04-node.junit.xml",
        "n02-adapter-regression.junit.xml",
        "n03-scheduler-regression.junit.xml",
        "full-node-suite.junit.xml",
        "full-python-suite.junit.xml",
        "rah-core-integrity.json",
        "build_n04_0001_evidence.py",
        "n04_0001_rah_seal.py",
    )
    hashes = artifact_hashes(names)
    summary = (
        f"N04-0001 PASS closeout is hash-sealed after core generation {parent}: "
        f"report sha256:{hashes['report.json']}; commands sha256:"
        f"{hashes['commands.jsonl']}; review sha256:{hashes['review.md']}; "
        f"verification sha256:{hashes['fan-in-verification.json']}; receipt "
        f"sha256:{hashes['fan-in-verification.artifact-receipt.json']}; regression "
        f"sha256:{hashes['full-regression-impact.json']}; dependency sha256:"
        f"{hashes['dependency-status.json']}; scope sha256:"
        f"{hashes['write-scope-verification.json']}; syntax sha256:"
        f"{hashes['syntax-verification.json']}; RAH integrity sha256:"
        f"{hashes['rah-core-integrity.json']}; builder sha256:"
        f"{hashes['build_n04_0001_evidence.py']}; sealer sha256:"
        f"{hashes['n04_0001_rah_seal.py']}. Every prior attempt, report, and "
        "generation is preserved. N04-0001 is immutable PASS and the live "
        "156-package DAG must now be recomputed. Global implementation_gate=fail "
        "and completion_ready=false."
    )
    return summary, hashes


_base_verify_generation_store = n03_seal._base_verify_generation_store
_base_run_preflight = n03_seal._base_run_preflight
_base_commit_generation = n03_seal._base_commit_generation


def verify_generation_store(expected_count: int | None = None) -> dict[str, Any]:
    result = _base_verify_generation_store(expected_count)
    result["attempt_id"] = ATTEMPT_ID
    result["work_package_id"] = "N04"
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
        raise SystemExit("N04 parent generation manifest hash changed")
    if result.get("next_evidence_id") != EXPECTED_CORE_EVIDENCE:
        raise SystemExit("N04 preflight does not allocate E0076")
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
        "N04-0001 fan-in completeness, missing-node, and independent-review "
        "contracts are evidence-sealed PASS. The live DAG and downstream packages "
        "remain; implementation_gate=fail and completion_ready=false."
    )
    status["implementation_gate"] = "fail"
    status["implementation_gate_note"] = note
    status["next_recommended_action"] = NEXT_ACTIONS[0]
    gate = gates.get("implementation_gate")
    if not isinstance(gate, dict):
        raise SystemExit("N04 RAH implementation gate is malformed")
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
        raise SystemExit("N04 core evidence allocation changed")
    return result


def run_final() -> dict[str, Any]:
    result = sealed_base.run_final()
    if result.get("evidence_id") != EXPECTED_FINAL_EVIDENCE:
        raise SystemExit("N04 final evidence allocation changed")
    return result


def run_verify() -> dict[str, Any]:
    result = sealed_base.run_verify()
    if result.get("latest_evidence_id") != EXPECTED_FINAL_EVIDENCE:
        raise SystemExit("N04 verification did not end at E0077")
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
