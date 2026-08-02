#!/usr/bin/env python3
"""Append M02-0001 core and closeout evidence to the active RAH state."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/M02/attempts/0001"
M01_ATTEMPT = ROOT / "artifacts/work_packages/M01/attempts/0001"
L03_ATTEMPT = ROOT / "artifacts/work_packages/L03/attempts/0001"
ATTEMPT_ID = "M02-0001"

sys.path.insert(0, str(ATTEMPT))
sys.path.insert(0, str(M01_ATTEMPT))
sys.path.insert(0, str(L03_ATTEMPT))

import build_m02_0001_evidence as evidence  # noqa: E402
import l03_0001_rah_seal as sealed_base  # noqa: E402


EXPECTED_INITIAL_PARENT = "000055-2c362890"
EXPECTED_INITIAL_PARENT_MANIFEST_SHA256 = (
    "355e62aef400bd8b43f53757383a5c4dfb98898a9c2299b4b8256d81d334393c"
)
EXPECTED_INITIAL_EVIDENCE = "E0055"
EXPECTED_INITIAL_GENERATION_COUNT = 55
EXPECTED_CORE_EVIDENCE = "E0056"
EXPECTED_FINAL_EVIDENCE = "E0057"
NEXT_ACTIONS = [
    "Recompute and seal the live 156-package DAG after M02-0001 PASS.",
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
            raise SystemExit(f"required M02 artifact is missing: {name}")
        result[name] = sha256(path)
    return result


def core_summary() -> str:
    names = (
        "baseline-centrality-verification.json",
        "baseline-centrality-verification.artifact-receipt.json",
        "centrality-verification.json",
        "uniform-rank-verification.json",
        "full-regression-impact.json",
        "dependency-status.json",
        "write-scope-verification.json",
        "syntax-verification.json",
        "targeted-m02-node.junit.xml",
        "combined-m01-m02-node.junit.xml",
        "full-node-suite.junit.xml",
        "full-python-suite.junit.xml",
        "node-test-inventory.json",
        "review.md",
        "attempt-metadata.json",
        "run_m02_0001_checks.py",
        "build_m02_0001_evidence.py",
        "m02_0001_rah_seal.py",
    )
    hashes = artifact_hashes(names)
    return (
        "M02-0001 PASS: deterministic weighted directed PageRank computes real "
        "baseline centrality over M01-validated resolved typed edges with "
        "alpha=0.85, bounded L1 convergence, uniform dangling redistribution, "
        "unit edge weights, stable UTF-8 ordering, isolates, weak components, "
        "and normalized scores. Algorithm version, parameters, node inventory, "
        "resolved edges, and excluded unresolved edge IDs are recorded and "
        "hash-bound. Analytical references and asymmetric star/path cases are "
        "non-uniform; structurally asymmetric uniform output fails closed while "
        "mathematically valid cycle/isolate ties remain allowed. Unresolved "
        "edges are recorded but do not influence scores. Tampering, hostile "
        "wrappers, invalid parameters, and nonconvergence fail closed. M02 emits "
        "no query relevance, risk, blast radius, or WorkspaceMapSnapshot. "
        "Targeted M02 is 25/25; M01+M02 is 47/47; syntax is 4/4; full Node "
        "is 660/660 over 67 files; full Python is 1064/1064; codegen is 126/126. "
        f"Verification sha256:{hashes['baseline-centrality-verification.json']}; "
        f"receipt sha256:{hashes['baseline-centrality-verification.artifact-receipt.json']}; "
        f"centrality sha256:{hashes['centrality-verification.json']}; uniformity "
        f"sha256:{hashes['uniform-rank-verification.json']}; regression sha256:"
        f"{hashes['full-regression-impact.json']}; dependency sha256:"
        f"{hashes['dependency-status.json']}; scope sha256:"
        f"{hashes['write-scope-verification.json']}; syntax sha256:"
        f"{hashes['syntax-verification.json']}; targeted JUnit sha256:"
        f"{hashes['targeted-m02-node.junit.xml']}; combined JUnit sha256:"
        f"{hashes['combined-m01-m02-node.junit.xml']}; Node JUnit sha256:"
        f"{hashes['full-node-suite.junit.xml']}; Python JUnit sha256:"
        f"{hashes['full-python-suite.junit.xml']}; inventory-list sha256:"
        f"{hashes['node-test-inventory.json']}; review sha256:{hashes['review.md']}; "
        f"metadata sha256:{hashes['attempt-metadata.json']}; runner sha256:"
        f"{hashes['run_m02_0001_checks.py']}; builder sha256:"
        f"{hashes['build_m02_0001_evidence.py']}; sealer sha256:"
        f"{hashes['m02_0001_rah_seal.py']}. Review is primary-session separate "
        "with actor_independence=false under the product-owner no-subagent "
        "constraint. Global implementation_gate=fail and completion_ready=false."
    )


def final_summary(parent: str) -> tuple[str, dict[str, str]]:
    names = (
        "report.json",
        "commands.jsonl",
        "review.md",
        "baseline-centrality-verification.json",
        "baseline-centrality-verification.artifact-receipt.json",
        "centrality-verification.json",
        "uniform-rank-verification.json",
        "full-regression-impact.json",
        "dependency-status.json",
        "write-scope-verification.json",
        "syntax-verification.json",
        "targeted-m02-node.junit.xml",
        "combined-m01-m02-node.junit.xml",
        "full-node-suite.junit.xml",
        "full-python-suite.junit.xml",
        "rah-core-integrity.json",
        "build_m02_0001_evidence.py",
        "m02_0001_rah_seal.py",
    )
    hashes = artifact_hashes(names)
    summary = (
        f"M02-0001 PASS closeout is hash-sealed after core generation {parent}: "
        f"report sha256:{hashes['report.json']}; commands sha256:"
        f"{hashes['commands.jsonl']}; review sha256:{hashes['review.md']}; "
        f"verification sha256:{hashes['baseline-centrality-verification.json']}; "
        f"receipt sha256:{hashes['baseline-centrality-verification.artifact-receipt.json']}; "
        f"centrality sha256:{hashes['centrality-verification.json']}; uniformity "
        f"sha256:{hashes['uniform-rank-verification.json']}; regression sha256:"
        f"{hashes['full-regression-impact.json']}; dependency sha256:"
        f"{hashes['dependency-status.json']}; scope sha256:"
        f"{hashes['write-scope-verification.json']}; syntax sha256:"
        f"{hashes['syntax-verification.json']}; RAH integrity sha256:"
        f"{hashes['rah-core-integrity.json']}; builder sha256:"
        f"{hashes['build_m02_0001_evidence.py']}; sealer sha256:"
        f"{hashes['m02_0001_rah_seal.py']}. Every prior attempt, report, and "
        "generation is preserved. M02-0001 is immutable PASS and the live "
        "156-package DAG must now be recomputed. Global implementation_gate=fail "
        "and completion_ready=false."
    )
    return summary, hashes


_base_verify_generation_store = sealed_base.verify_generation_store
_base_run_preflight = sealed_base.run_preflight


def verify_generation_store(expected_count: int | None = None) -> dict[str, Any]:
    result = _base_verify_generation_store(expected_count)
    result["attempt_id"] = ATTEMPT_ID
    result["work_package_id"] = "M02"
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
        raise SystemExit("M02 parent generation manifest hash changed")
    if result.get("next_evidence_id") != EXPECTED_CORE_EVIDENCE:
        raise SystemExit("M02 preflight does not allocate E0056")
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
        raise SystemExit("M02 core evidence allocation changed")
    return result


def run_final() -> dict[str, Any]:
    result = sealed_base.run_final()
    if result.get("evidence_id") != EXPECTED_FINAL_EVIDENCE:
        raise SystemExit("M02 final evidence allocation changed")
    return result


def run_verify() -> dict[str, Any]:
    result = sealed_base.run_verify()
    if result.get("latest_evidence_id") != EXPECTED_FINAL_EVIDENCE:
        raise SystemExit("M02 verification did not end at E0057")
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
