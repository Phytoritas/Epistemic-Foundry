#!/usr/bin/env python3
"""Append M04-0001 core and closeout evidence to the active RAH state."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/M04/attempts/0001"
M03_ATTEMPT = ROOT / "artifacts/work_packages/M03/attempts/0001"
ATTEMPT_ID = "M04-0001"
sys.path.insert(0, str(ATTEMPT))
sys.path.insert(0, str(M03_ATTEMPT))

import build_m04_0001_evidence as evidence  # noqa: E402
import m03_0001_rah_seal as m03_seal  # noqa: E402


sealed_base = m03_seal.sealed_base
EXPECTED_INITIAL_PARENT = "000061-c855ff9a"
EXPECTED_INITIAL_PARENT_MANIFEST_SHA256 = (
    "20ba97d775767da553dbd3a3ea22f95f1fdc43bf8bc1e5947398eff5c0bf5da9"
)
EXPECTED_INITIAL_EVIDENCE = "E0061"
EXPECTED_INITIAL_GENERATION_COUNT = 61
EXPECTED_CORE_EVIDENCE = "E0062"
EXPECTED_FINAL_EVIDENCE = "E0063"
NEXT_ACTIONS = [
    "Recompute and seal the live 156-package DAG after M04-0001 PASS.",
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
            raise SystemExit(f"required M04 artifact is missing: {name}")
        result[name] = sha256(path)
    return result


def core_summary() -> str:
    names = (
        "map-ui-ranking-claim-verification.json",
        "map-ui-ranking-claim-verification.artifact-receipt.json",
        "full-regression-impact.json",
        "dependency-status.json",
        "write-scope-verification.json",
        "syntax-verification.json",
        "targeted-m04-node.junit.xml",
        "combined-m01-m02-m03-m04-node.junit.xml",
        "full-node-suite.junit.xml",
        "full-python-suite.junit.xml",
        "node-test-inventory.json",
        "review.md",
        "attempt-metadata.json",
        "run_m04_0001_checks.py",
        "build_m04_0001_evidence.py",
        "m04_0001_rah_seal.py",
    )
    hashes = artifact_hashes(names)
    return (
        "M04-0001 PASS: the workspace-map UI accepts exactly M01 inventory and "
        "edge extraction, M02 baseline centrality, and M03 query and risk/change-"
        "impact artifacts, invoking every owning validator. A closed four-claim "
        "vocabulary keeps baseline structural centrality, query lexical relevance, "
        "intrinsic risk, and change impact separate. Labels are bound to sealed "
        "algorithm names, versions, hashes, orders, score fields, and exclusions; "
        "generic importance, combined scores, confidence, verdict, and semantic rank "
        "are forbidden. Coverage, unreadable paths, unresolved edges, reasons, and "
        "per-dimension exclusions are first and visible. Null query remains "
        "NOT_PERSONALIZED and semantic scoring remains null/NOT_COMPUTED. HTML "
        "escaping, deterministic projection, deep immutability, upstream tamper, "
        "claim laundering, proxies, accessors, sparse arrays, and unknown fields are "
        "verified fail closed. Targeted M04 is 26/26 (map UI 12, ranking-claim audit "
        "14); M01+M02+M03+M04 is 106/106; syntax is 6/6; full Node is 719/719 "
        "over 71 files; full Python is 1064/1064; codegen is 126/126. "
        f"Verification sha256:{hashes['map-ui-ranking-claim-verification.json']}; "
        f"receipt sha256:{hashes['map-ui-ranking-claim-verification.artifact-receipt.json']}; "
        f"regression sha256:{hashes['full-regression-impact.json']}; dependency "
        f"sha256:{hashes['dependency-status.json']}; scope sha256:"
        f"{hashes['write-scope-verification.json']}; syntax sha256:"
        f"{hashes['syntax-verification.json']}; targeted JUnit sha256:"
        f"{hashes['targeted-m04-node.junit.xml']}; combined JUnit sha256:"
        f"{hashes['combined-m01-m02-m03-m04-node.junit.xml']}; Node JUnit sha256:"
        f"{hashes['full-node-suite.junit.xml']}; Python JUnit sha256:"
        f"{hashes['full-python-suite.junit.xml']}; inventory sha256:"
        f"{hashes['node-test-inventory.json']}; review sha256:{hashes['review.md']}; "
        f"metadata sha256:{hashes['attempt-metadata.json']}; runner sha256:"
        f"{hashes['run_m04_0001_checks.py']}; builder sha256:"
        f"{hashes['build_m04_0001_evidence.py']}; sealer sha256:"
        f"{hashes['m04_0001_rah_seal.py']}. Review is primary-session separate "
        "with actor_independence=false under the product-owner no-subagent "
        "constraint. Global implementation_gate=fail and completion_ready=false."
    )


def final_summary(parent: str) -> tuple[str, dict[str, str]]:
    names = (
        "report.json",
        "commands.jsonl",
        "review.md",
        "map-ui-ranking-claim-verification.json",
        "map-ui-ranking-claim-verification.artifact-receipt.json",
        "full-regression-impact.json",
        "dependency-status.json",
        "write-scope-verification.json",
        "syntax-verification.json",
        "targeted-m04-node.junit.xml",
        "combined-m01-m02-m03-m04-node.junit.xml",
        "full-node-suite.junit.xml",
        "full-python-suite.junit.xml",
        "rah-core-integrity.json",
        "build_m04_0001_evidence.py",
        "m04_0001_rah_seal.py",
    )
    hashes = artifact_hashes(names)
    summary = (
        f"M04-0001 PASS closeout is hash-sealed after core generation {parent}: "
        f"report sha256:{hashes['report.json']}; commands sha256:"
        f"{hashes['commands.jsonl']}; review sha256:{hashes['review.md']}; "
        f"verification sha256:{hashes['map-ui-ranking-claim-verification.json']}; "
        f"receipt sha256:{hashes['map-ui-ranking-claim-verification.artifact-receipt.json']}; "
        f"regression sha256:{hashes['full-regression-impact.json']}; dependency "
        f"sha256:{hashes['dependency-status.json']}; scope sha256:"
        f"{hashes['write-scope-verification.json']}; syntax sha256:"
        f"{hashes['syntax-verification.json']}; RAH integrity sha256:"
        f"{hashes['rah-core-integrity.json']}; builder sha256:"
        f"{hashes['build_m04_0001_evidence.py']}; sealer sha256:"
        f"{hashes['m04_0001_rah_seal.py']}. Every prior attempt, report, and "
        "generation is preserved. M04-0001 is immutable PASS and the live "
        "156-package DAG must now be recomputed. Global implementation_gate=fail "
        "and completion_ready=false."
    )
    return summary, hashes


_base_verify_generation_store = m03_seal._base_verify_generation_store
_base_run_preflight = m03_seal._base_run_preflight
_base_commit_generation = m03_seal._base_commit_generation


def verify_generation_store(expected_count: int | None = None) -> dict[str, Any]:
    result = _base_verify_generation_store(expected_count)
    result["attempt_id"] = ATTEMPT_ID
    result["work_package_id"] = "M04"
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
        raise SystemExit("M04 parent generation manifest hash changed")
    if result.get("next_evidence_id") != EXPECTED_CORE_EVIDENCE:
        raise SystemExit("M04 preflight does not allocate E0062")
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
        "M04-0001 map UI and ranking-claim semantics are evidence-sealed PASS. "
        "The live DAG and downstream packages remain; implementation_gate=fail "
        "and completion_ready=false."
    )
    status["implementation_gate"] = "fail"
    status["implementation_gate_note"] = note
    status["next_recommended_action"] = NEXT_ACTIONS[0]
    gate = gates.get("implementation_gate")
    if not isinstance(gate, dict):
        raise SystemExit("M04 RAH implementation gate is malformed")
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
        raise SystemExit("M04 core evidence allocation changed")
    return result


def run_final() -> dict[str, Any]:
    result = sealed_base.run_final()
    if result.get("evidence_id") != EXPECTED_FINAL_EVIDENCE:
        raise SystemExit("M04 final evidence allocation changed")
    return result


def run_verify() -> dict[str, Any]:
    result = sealed_base.run_verify()
    if result.get("latest_evidence_id") != EXPECTED_FINAL_EVIDENCE:
        raise SystemExit("M04 verification did not end at E0063")
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
