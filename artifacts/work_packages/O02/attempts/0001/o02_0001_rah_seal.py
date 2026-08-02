#!/usr/bin/env python3
"""Append O02-0001 SPEC_GAP evidence without rewriting RAH history."""

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


ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/O02/attempts/0001"
AUTOMATION = ROOT / ".rah/helpers/recursive-architecture-refactoring-auto/automation"
sys.dont_write_bytecode = True
sys.path.insert(0, str(AUTOMATION))

import ralph_harness as rh  # noqa: E402
import state_store  # noqa: E402


EXPECTED_PARENT = "000083-73439bf3"
EXPECTED_PARENT_MANIFEST_SHA256 = (
    "cd1cb9e28481e41288494ba23444990cb451733e0888322a86e4aa4161d21bfd"
)
EXPECTED_PARENT_EVIDENCE = "E0083"
EXPECTED_PARENT_GENERATION_COUNT = 83
GAP_EVIDENCE_ID = "E0084"
SPEC_GAP_ID = "O02-SG001"
AUTHORITY_HASHES = {
    "AGENTS.md": "858e537ed3e49754b8e60d31c985467ee1246ed258c7763d6de4ef0767e381ea",
    "MASTER_SPEC.md": "d4854c916594610e0503f9b017c57b0dbac9f52eef78b825b922fdf26b1a0fe3",
    "config/retrieval_policy.example.yaml": "a5d20c342d16ad2ba0ad10fdf7d0b6398812f47eecc6c90a2c87cac94f0767f8",
    "docs/search_completeness.md": "ee710a914ad5252948166ae219691dc46e632604514432934351e339db24376d",
    "manifests/144_lens_audit_matrix.yaml": "bb79fda3deaee277b9e13c45cd11540d33abf2ac4af7418d1a3844f9f7003cec",
    "manifests/development_manifest.yaml": "5dd99d2aae1e9ef662b9b8242b5fa921621434c6600c9c06e3a573d03079bb12",
    "schemas/evidence-node.schema.json": "dbb39dae38266145f3c8d3bef94386ddfefe81ca2ed9ec93f43b26abc27ff768",
    "schemas/query-plan.schema.json": "6f9fe754cce171efbf9bfa738646046ae5232224b84d8a96e1f72dc14e5f0c4e",
    "schemas/result-envelope.schema.json": "5985f8b16314a61c14d54902a1004f0149a95e9db60f6e316511aa9424418e74",
    "schemas/search-lane-receipt.schema.json": "3c5bfbd600535e061b1d783a5f0df146f2896e980e438b58721c139c3b4305ac",
    "schemas/source-span.schema.json": "4d4c8ec8b9a778c0176c7d8b866d15a82bf53be898985389ac0cc42d6a60586a",
    "workflows/evidence_retrieval.workflow.yaml": "05e8e360187520c18d1fe8fba3e492896c9e4dbd7a324907fc271c0568ae3438",
    "artifacts/work_packages/O01/attempts/0002/report.json": "21cd6f07ce4caae4d7a7d673a85aec105117f35f2a560ef8310ee532cb188051",
}
BLOCK_REASON = (
    "O02-SG001 requires a product-owner HumanDecision defining the canonical "
    "RetrievalCandidate or equivalent output and provenance fields, backend input "
    "interfaces, lane-to-QueryPlan query-family mapping, relation direction and "
    "inverse semantics, score normalization, cutoff, deduplication and tie-break "
    "rules, snapshot and index integrity binding, unavailable/partial/invalid and "
    "fallback behavior, an executable non-vector-only fusion rule, exact "
    "retrieval_benchmark and relation_direction_test fixtures, metrics, answers "
    "and thresholds, the O01/O02 receipt ownership boundary, and exact resolving "
    "implementation/test/fixture/evidence write scopes. O02 cannot invent these "
    "shared contracts. Later dependency-ready packages remain unstarted under "
    "serial execution; completion_ready=false."
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


def verify_authorities() -> None:
    for relative, expected in AUTHORITY_HASHES.items():
        path = ROOT / relative
        if not path.is_file() or sha256(path) != expected:
            raise SystemExit(f"O02 authority changed: {relative}")
    dependency = read_json(ROOT / "artifacts/work_packages/O01/attempts/0002/report.json")
    if dependency.get("attempt_id") != "O01-0002":
        raise SystemExit("unexpected O01 dependency attempt")
    if dependency.get("status") != "PASS" or dependency.get("package_status") != "PASS":
        raise SystemExit("O01 dependency is not PASS")
    if (ROOT / "python/epistemic_foundry/retrieval/lanes").exists():
        raise SystemExit("O02 product implementation path unexpectedly exists")
    verification = read_json(ATTEMPT / "shared-contract-gap-verification.json")
    dependency_status = read_json(ATTEMPT / "dependency-status.json")
    if verification.get("status") != "SPEC_GAP":
        raise SystemExit("O02 verification does not preserve SPEC_GAP")
    if dependency_status.get("status") != "SPEC_GAP":
        raise SystemExit("O02 dependency status does not preserve SPEC_GAP")
    expected_checks = {
        "relation_direction_test": {
            "reason": "No authoritative direction vocabulary, inverse/reverse rule, fixture, or exact expected answer exists.",
            "status": "NOT_RUN_SPEC_GAP",
        },
        "retrieval_benchmark": {
            "reason": "No authoritative benchmark corpus, query set, relevance labels, metric, normalization rule, or PASS threshold exists.",
            "status": "NOT_RUN_SPEC_GAP",
        },
    }
    if verification.get("required_checks") != expected_checks:
        raise SystemExit("O02 required-check disposition changed")


def gap_summary() -> str:
    hashes = {
        "verification": sha256(ATTEMPT / "shared-contract-gap-verification.json"),
        "dependency": sha256(ATTEMPT / "dependency-status.json"),
        "review": sha256(ATTEMPT / "review.md"),
        "sealer": sha256(Path(__file__)),
    }
    return (
        "O02-0001 SPEC_GAP O02-SG001: O01-0002 is PASS, but "
        "retrieval_benchmark and relation_direction_test are NOT_RUN_SPEC_GAP. "
        "The authority chain lacks a canonical retrieval candidate and provenance "
        "artifact, provider-neutral backend interfaces, lane-to-query-family and "
        "relation-direction semantics, ranking/cutoff/deduplication/tie-break "
        "rules, snapshot integrity and stale-result binding, failure/fallback "
        "semantics, an executable non-vector-only rule, benchmark fixtures, labels, "
        "metrics and thresholds, exact relation expected answers, and a raw-result/"
        "SearchLaneReceipt ownership boundary with resolving write scopes. Product "
        "implementation changes=0; this is not FAIL because no implementation ran "
        "against an invented oracle and not BLOCKED because no external prerequisite "
        "is established unavailable. Verification sha256:"
        f"{hashes['verification']}; dependency sha256:{hashes['dependency']}; "
        f"review sha256:{hashes['review']}; sealer sha256:{hashes['sealer']}. "
        "Later packages remain unstarted under serial execution; "
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
            f"expected {expected_count} generations ending at {current}, found {len(generations)}"
        )
    verified_hashes = 0
    for generation in generations:
        root = ralph_root / "generations" / generation
        manifest = read_json(root / "generation-manifest.json")
        files = manifest.get("files")
        if manifest.get("generation") != generation or not isinstance(files, dict):
            raise SystemExit(f"invalid generation manifest: {generation}")
        if set(files) != set(state_store.GENERATION_FILES):
            raise SystemExit(f"generation file set mismatch: {generation}")
        for name in state_store.GENERATION_FILES:
            if sha256(root / name) != files[name]:
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
    if flat_stamps != 6 or flat_matches != 6:
        raise SystemExit(
            f"flat snapshot mismatch: stamps={flat_stamps}, matches={flat_matches}"
        )
    identifiers = evidence_ids(payloads)
    return {
        "attempt_id": "O02-0001",
        "completion_ready": payloads["loop_state.json"].get(
            "completion_readiness", {}
        ).get("ready"),
        "current_generation": current,
        "evidence_count": len(identifiers),
        "flat_snapshot_content_matches": flat_matches,
        "flat_snapshot_stamps_verified": flat_stamps,
        "generation_file_hashes_verified": verified_hashes,
        "generation_manifest_sha256": sha256(
            ralph_root / "generations" / current / "generation-manifest.json"
        ),
        "latest_evidence_id": identifiers[-1],
        "ralph_goal_status": payloads["goal.json"].get("status"),
        "ralph_status": payloads["loop_state.json"].get("status"),
        "retained_generation_count": len(generations),
        "schema_version": 1,
        "spec_gap_id": SPEC_GAP_ID,
        "status": "PASS",
        "work_package_id": "O02",
    }


def preflight() -> dict[str, Any]:
    verify_authorities()
    ralph_root, generation, payloads = current_state()
    if generation != EXPECTED_PARENT:
        raise SystemExit(f"unexpected O02 parent {generation}; expected {EXPECTED_PARENT}")
    parent_manifest = ralph_root / "generations" / generation / "generation-manifest.json"
    if sha256(parent_manifest) != EXPECTED_PARENT_MANIFEST_SHA256:
        raise SystemExit("O02 parent generation manifest hash changed")
    expected_ids = [f"E{index:04d}" for index in range(1, 84)]
    if evidence_ids(payloads) != expected_ids:
        raise SystemExit("O02 preflight requires preserved E0001-E0083")
    generations = numbered_generations(ralph_root)
    if len(generations) != EXPECTED_PARENT_GENERATION_COUNT or generations[-1] != generation:
        raise SystemExit("O02 preflight requires all 83 prior generations")
    loop = payloads["loop_state.json"]
    goal = payloads["goal.json"]
    if loop.get("status") != "active" or goal.get("status") != "active":
        raise SystemExit("O02 preflight requires active goal and loop")
    if loop.get("implementation_gate") != "fail":
        raise SystemExit("O02 preflight requires implementation_gate=fail")
    if loop.get("completion_readiness", {}).get("ready") is not False:
        raise SystemExit("O02 preflight requires completion_ready=false")
    return {
        "completion_ready": False,
        "generation": generation,
        "generation_manifest_sha256": EXPECTED_PARENT_MANIFEST_SHA256,
        "latest_evidence_id": EXPECTED_PARENT_EVIDENCE,
        "mode": "preflight",
        "retained_generation_count": len(generations),
        "status": "PASS",
    }


def seal() -> dict[str, Any]:
    preflight()
    ralph_root, parent, _ = current_state()
    before = numbered_generations(ralph_root)
    result, output = invoke_ralph(
        ["--record-gap", gap_summary(), "--block", BLOCK_REASON, "--no-increment"]
    )
    if result != 0:
        raise SystemExit(f"RAH O02 append failed ({result}): {output}")
    _, generation, payloads = current_state()
    expected_ids = [f"E{index:04d}" for index in range(1, 85)]
    if evidence_ids(payloads) != expected_ids:
        raise SystemExit("O02 seal did not append exactly E0084")
    last = payloads["evidence_ledger.json"]["entries"][-1]
    if last.get("kind") != "documented_gap" or last.get("summary") != gap_summary():
        raise SystemExit("E0084 is not the exact O02 documented gap")
    loop = payloads["loop_state.json"]
    goal = payloads["goal.json"]
    if loop.get("status") != "blocked" or goal.get("status") != "blocked":
        raise SystemExit("RAH did not persist blocked goal and loop states")
    if loop.get("blocked_reason") != BLOCK_REASON:
        raise SystemExit("RAH did not persist the exact O02-SG001 blocker")
    if loop.get("implementation_gate") != "fail":
        raise SystemExit("RAH changed implementation_gate during O02 seal")
    if loop.get("completion_readiness", {}).get("ready") is not False:
        raise SystemExit("RAH advanced completion_ready during O02 seal")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("O02 seal did not preserve every prior generation")
    integrity = verify_generation_store(84)
    if integrity["latest_evidence_id"] != GAP_EVIDENCE_ID:
        raise SystemExit("O02 documented gap is not the live evidence tail")
    return {
        "completion_ready": False,
        "documented_gap_evidence_id": GAP_EVIDENCE_ID,
        "generation": generation,
        "mode": "seal",
        "parent_generation": parent,
        "spec_gap_id": SPEC_GAP_ID,
        "state_verification": integrity,
        "status": "blocked",
    }


def verify() -> dict[str, Any]:
    verify_authorities()
    ralph_root, current, payloads = current_state()
    generations = numbered_generations(ralph_root)
    if len(generations) == EXPECTED_PARENT_GENERATION_COUNT:
        return preflight()
    if len(generations) != 84 or not re.fullmatch(r"000084-[0-9a-f]{8}", current):
        raise SystemExit(f"unexpected O02 generation state: {current}/{len(generations)}")
    expected_ids = [f"E{index:04d}" for index in range(1, 85)]
    if evidence_ids(payloads) != expected_ids:
        raise SystemExit("O02 verification requires preserved E0001-E0084")
    last = payloads["evidence_ledger.json"]["entries"][-1]
    if last.get("kind") != "documented_gap" or last.get("summary") != gap_summary():
        raise SystemExit("stored E0084 differs from current O02 artifacts")
    if payloads["goal.json"].get("status") != "blocked":
        raise SystemExit("O02 goal status is not blocked")
    loop = payloads["loop_state.json"]
    if loop.get("status") != "blocked" or loop.get("blocked_reason") != BLOCK_REASON:
        raise SystemExit("O02 loop blocker changed")
    integrity = verify_generation_store(84)
    return {**integrity, "mode": "verify"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("preflight", "seal", "verify"))
    args = parser.parse_args()
    result = {"preflight": preflight, "seal": seal, "verify": verify}[args.mode]()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
