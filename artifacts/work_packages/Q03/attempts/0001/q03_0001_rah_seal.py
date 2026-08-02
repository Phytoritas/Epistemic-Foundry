#!/usr/bin/env python3
"""Append Q03-0001 PASS evidence while global completion remains false."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/Q03/attempts/0001"
AUTOMATION = ROOT / ".rah/helpers/recursive-architecture-refactoring-auto/automation"
ATTEMPT_ID = "Q03-0001"
WORK_PACKAGE_ID = "Q03"
EXPECTED_PARENT = "000156-aeb809a2"
EXPECTED_PARENT_COUNT = 156
EXPECTED_PARENT_EVIDENCE = "E0158"
EXPECTED_PARENT_MANIFEST_SHA256 = (
    "0a511110ca446981fdf7690e77f225790e2769ec2d66110d49c84921f0305e63"
)
CORE_EVIDENCE_ID = "E0159"
FINAL_EVIDENCE_ID = "E0160"
sys.path.insert(0, str(ATTEMPT))
sys.path.insert(0, str(AUTOMATION))

import build_q03_0001_evidence as evidence  # noqa: E402
import ralph_harness as rh  # noqa: E402
import state_store  # noqa: E402


NEXT_ACTIONS = [
    "Run the C06 generated types, fixtures and compatibility integration gate "
    "on the sealed C05 state.",
    "Continue toward C06, the remaining x05 wave and the U01/V01/X01 "
    "integration layer.",
    "Keep completion_ready=false until every objective, source-coverage, PRD, "
    "review, and closeout gate passes.",
]


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
    if state_store.verify_current(ralph_root).get("generation") != generation:
        raise SystemExit("RAH current pointer and verified generation disagree")
    return ralph_root, generation, payloads


def evidence_ids(payloads: dict[str, Any]) -> list[str]:
    ledger = payloads.get("evidence_ledger.json")
    if not isinstance(ledger, dict) or not isinstance(ledger.get("entries"), list):
        raise SystemExit("invalid RAH evidence ledger")
    identifiers = [
        str(row.get("id")) for row in ledger["entries"] if isinstance(row, dict)
    ]
    expected = [f"E{index:04d}" for index in range(1, len(identifiers) + 1)]
    if identifiers != expected or int(ledger.get("issued_id_high_water", 0)) != len(
        identifiers
    ):
        raise SystemExit("RAH evidence ledger is not contiguous")
    return identifiers


def generation_number(generation: str) -> int:
    if re.fullmatch(r"\d{6}-[0-9a-f]{8}", generation) is None:
        raise SystemExit(f"malformed RAH generation: {generation}")
    return int(generation.split("-", 1)[0])


def artifact_hashes(names: tuple[str, ...]) -> dict[str, str]:
    result: dict[str, str] = {}
    for name in names:
        path = ATTEMPT / name
        if not path.is_file():
            raise SystemExit(f"required Q03-0001 artifact missing: {name}")
        result[name] = sha256(path)
    return result


def core_summary() -> str:
    names = (
        "dependency-status.json",
        "q03-verification.json",
        "write-scope-verification.json",
        "node-test-inventory.json",
        "junit-normalization-verification.json",
        "retrieval-eval.junit.xml",
        "calibration-eval.junit.xml",
        "targeted-retrieval-verdict.junit.xml",
        "dependency-regression-gold.junit.xml",
        "dependency-regression-claims.junit.xml",
        "full-python-suite.junit.xml",
        "full-node-suite.junit.xml",
        "review.md",
        "run_q03_0001_checks.py",
        "build_q03_0001_evidence.py",
        "q03_0001_rah_seal.py",
    )
    hashes = artifact_hashes(names)
    return (
        "Q03-0001 PASS core verification: the retrieval, verdict and "
        "calibration evaluation is implemented in evals/retrieval_verdict "
        "under an exact Q01-0001 dependency binding and a Q02-0001 regression "
        "baseline. Counter and null recall are measured on their own, because "
        "an agreement-seeking retriever loses exactly those: v1 measures "
        "supporting recall 1.00 and null recall 1.00 while counter recall is "
        "0.50, with both missed documents named rather than averaged away, and "
        "a corpus carrying no counter or null evidence is refused as "
        "POLARITY_UNMEASURED rather than scored a perfect one. Calibration is "
        "computed with its inputs exposed: the Brier score and the expected "
        "calibration error derive from the same confidence/outcome pairs and "
        "are reported with the reliability bins they came from, so re-adding "
        "the bins recovers the ECE, measuring Brier 0.166 and ECE 0.305 for a "
        "WARN status over twelve graded predictions, with a PASS proved "
        "separately on a well-calibrated variant. The emitted document is "
        "validated against schemas/calibration-report.schema.json with its "
        "target and status read from that schema, a sample below the floor is "
        "INSUFFICIENT_DATA with both statistics null, and an empty reliability "
        "bin reports null rather than zero. UNDETERMINED is a first-class "
        "verdict, so the benchmark never forces a decision the evidence does "
        "not support. Ruff lint/format, retrieval_eval 24/24, calibration_eval "
        "23/23, targeted 47/47, Q01 gold regression 41/41, Q02 claims "
        "regression 46/46, full Python 1261/1261, full Node 982/982 across 91 "
        "files, and git diff --check pass. "
        + "; ".join(f"{name}=sha256:{digest}" for name, digest in hashes.items())
        + ". Review is primary-session separate with actor_independence=false. "
        "C06-0001 is next; implementation_gate=fail and completion_ready=false."
    )


def final_summary(parent: str) -> tuple[str, dict[str, str]]:
    names = (
        "report.json",
        "commands.jsonl",
        "review.md",
        "dependency-status.json",
        "q03-verification.json",
        "write-scope-verification.json",
        "node-test-inventory.json",
        "junit-normalization-verification.json",
        "retrieval-eval.junit.xml",
        "calibration-eval.junit.xml",
        "targeted-retrieval-verdict.junit.xml",
        "dependency-regression-gold.junit.xml",
        "dependency-regression-claims.junit.xml",
        "full-python-suite.junit.xml",
        "full-node-suite.junit.xml",
        "rah-core-integrity.json",
        "run_q03_0001_checks.py",
        "build_q03_0001_evidence.py",
        "q03_0001_rah_seal.py",
    )
    hashes = artifact_hashes(names)
    summary = (
        f"Q03-0001 PASS closeout is hash-sealed after core generation {parent}: "
        + "; ".join(f"{name}=sha256:{digest}" for name, digest in hashes.items())
        + ". Q02-0001 and every prior RAH generation remain immutable. The "
        "queries, relevance grades and retrieval results are synthetic "
        "fixtures written for this benchmark, and the retriever is declared "
        "synthetic with a corpus claiming otherwise refused, so the measured "
        "values characterise the harness rather than any deployed retriever; "
        "twelve graded predictions clear the calibration floor but are far too "
        "few to set production thresholds; ranking quality beyond binary "
        "recall is not measured. C06, the remaining x05 wave, U01, V01, X01, "
        "source coverage, PRD, review, and global closeout remain; "
        "implementation_gate=fail and completion_ready=false."
    )
    return summary, hashes


def assert_active(payloads: dict[str, Any]) -> None:
    loop = payloads["loop_state.json"]
    goal = payloads["goal.json"]
    if (
        loop.get("status") != "active"
        or goal.get("status") != "active"
        or loop.get("blocked_reason") is not None
        or loop.get("implementation_gate") != "fail"
        or loop.get("completion_readiness", {}).get("ready") is not False
    ):
        raise SystemExit("Q03-0001 seal requires active/fail/completion_ready=false")


def commit_active_failed_generation(
    *, payloads: dict[str, Any], summary: str, expected_evidence_id: str
) -> str:
    now = rh.utc_now()
    goal = copy.deepcopy(payloads["goal.json"])
    loop = copy.deepcopy(payloads["loop_state.json"])
    ledger = copy.deepcopy(payloads["evidence_ledger.json"])
    identifier = rh.add_evidence_entry(
        ledger,
        now=now,
        goal_id=goal["goal_id"],
        iteration=int(loop.get("current_iteration") or loop.get("iteration") or 1),
        kind="evidence",
        summary=summary,
    )
    if identifier != expected_evidence_id:
        raise SystemExit(
            f"unexpected evidence ID {identifier}; expected {expected_evidence_id}"
        )
    goal.update({"status": "active", "updated_at_utc": now})
    loop.update(
        {
            "blocked_reason": None,
            "checkpoint_required": False,
            "current_stage": "ralph-active",
            "done": False,
            "generated_at_utc": now,
            "harness_phase": "execution",
            "implementation_gate": "fail",
            "loop_phase": "bounded-implementation",
            "mark_done_rejected": False,
            "next_actions": NEXT_ACTIONS,
            "status": "active",
            "updated_at_utc": now,
        }
    )
    readiness = loop.get("completion_readiness")
    if not isinstance(readiness, dict) or readiness.get("ready") is not False:
        raise SystemExit("completion readiness must remain explicitly false")
    readiness["evidence_count"] = len(ledger["entries"])
    loop["state_machine"] = {
        "allowed_next_states": ["verify", "plan", "blocked", "failed"],
        "current_state": "act",
        "states": [
            "intake",
            "plan",
            "act",
            "verify",
            "review",
            "decide",
            "done",
            "blocked",
            "cancelled",
            "failed",
        ],
    }
    previous_used = loop.get("progress_update", {}).get("used_evidence", [])
    loop["progress_update"] = {
        "created_evidence": [identifier],
        "missing_acceptance_ids": [],
        "missing_closeout_ids": [],
        "missing_evidence_ids": [],
        "missing_validation_ids": [],
        "used_evidence": list(
            dict.fromkeys([*previous_used, *evidence_ids(payloads), identifier])
        ),
    }
    plan = rh.build_plan_graph(goal, loop, payloads["plan_graph.json"], now)
    bridge = rh.build_goal_bridge(
        ROOT,
        goal,
        loop,
        payloads["goal_bridge.json"],
        SimpleNamespace(goal_status="active", goal_objective=str(goal["goal"])),
        now,
    )
    review = copy.deepcopy(payloads["review_gate.json"])
    review["updated_at_utc"] = now
    state_store.KEEP_GENERATIONS = 10_000
    generation = state_store.commit_generation(
        ROOT / ".rah/ralph",
        {
            "evidence_ledger.json": ledger,
            "goal.json": goal,
            "goal_bridge.json": bridge,
            "loop_state.json": loop,
            "plan_graph.json": plan,
            "review_gate.json": review,
        },
    )

    status_path = ROOT / ".rah/state/status.json"
    gates_path = ROOT / ".rah/state/gates.json"
    status = read_json(status_path)
    gates = read_json(gates_path)
    note = (
        "Q03-0001 retrieval, verdict and calibration evaluation is "
        "evidence-sealed PASS. C06-0001 is next; implementation_gate=fail and "
        "completion_ready=false."
    )
    status["implementation_gate"] = "fail"
    status["implementation_gate_note"] = note
    status["next_recommended_action"] = NEXT_ACTIONS[0]
    prior_ids = gates.get("implementation_gate", {}).get("evidence_ids", [])
    gates["implementation_gate"] = {
        "evidence_ids": list(dict.fromkeys([*prior_ids, identifier])),
        "note": note,
        "status": "fail",
    }
    rh.write_json(status_path, status)
    rh.write_json(gates_path, gates)
    rh.refresh_status_for_ralph(ROOT, ROOT / ".rah", goal, loop, now)
    rh.upsert_current_loop(
        ROOT / ".rah/plans/current_loop.md", rh.render_managed_current_loop(goal, loop)
    )
    rh.write_text(ROOT / ".rah/ralph/blockers.md", rh.render_blockers(goal, loop, now))
    return generation


def verify_generation_store(expected_count: int) -> dict[str, Any]:
    ralph_root, current, payloads = current_state()
    generations = numbered_generations(ralph_root)
    if (
        len(generations) != expected_count
        or not generations
        or generations[-1] != current
    ):
        raise SystemExit(
            f"expected {expected_count} generations ending at {current}, found {len(generations)}"
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
                raise SystemExit(
                    f"generation payload hash mismatch: {generation}/{name}"
                )
            checked += 1
    flat_stamps = 0
    flat_matches = 0
    for name in state_store.GENERATION_FILES:
        flat = read_json(ralph_root / name)
        if flat.get("state_generation") == current:
            flat_stamps += 1
        stripped = {
            key: value for key, value in flat.items() if key != "state_generation"
        }
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
    if (
        flat_stamps != 6
        or flat_matches != 6
        or loop.get("status") != "active"
        or goal.get("status") != "active"
        or loop.get("implementation_gate") != "fail"
        or loop.get("completion_readiness", {}).get("ready") is not False
    ):
        raise SystemExit("RAH state is not active/fail with six matching projections")
    identifiers = evidence_ids(payloads)
    return {
        "attempt_id": ATTEMPT_ID,
        "completion_ready": False,
        "current_generation": current,
        "evidence_count": len(identifiers),
        "flat_snapshot_content_matches": flat_matches,
        "flat_snapshot_stamps_verified": flat_stamps,
        "generation_file_hashes_verified": checked,
        "generation_manifest_sha256": "sha256:"
        + sha256(ralph_root / "generations" / current / "generation-manifest.json"),
        "implementation_gate": "fail",
        "latest_evidence_id": identifiers[-1],
        "parse_errors": {},
        "ralph_status": "active",
        "retained_generation_count": len(generations),
        "status": "PASS",
        "work_package_id": WORK_PACKAGE_ID,
    }


def run_preflight() -> dict[str, Any]:
    checked = evidence.verify()
    ralph_root, generation, payloads = current_state()
    assert_active(payloads)
    if (
        generation != EXPECTED_PARENT
        or evidence_ids(payloads)[-1] != EXPECTED_PARENT_EVIDENCE
    ):
        raise SystemExit("Q03-0001 parent is not the sealed Q02-0001 tail")
    generations = numbered_generations(ralph_root)
    if len(generations) != EXPECTED_PARENT_COUNT or generations[-1] != generation:
        raise SystemExit("Q03 preflight requires exactly 156 preserved generations")
    manifest_path = ralph_root / "generations" / generation / "generation-manifest.json"
    if sha256(manifest_path) != EXPECTED_PARENT_MANIFEST_SHA256:
        raise SystemExit("Q03 parent generation manifest hash mismatch")
    if "rah_state" in read_json(ATTEMPT / "report.json"):
        raise SystemExit("Q03-0001 report is already RAH-bound; use verify")
    return {
        **checked,
        "completion_ready": False,
        "generation": generation,
        "latest_evidence_id": EXPECTED_PARENT_EVIDENCE,
        "mode": "preflight",
        "next_evidence_id": CORE_EVIDENCE_ID,
        "retained_generation_count": len(generations),
    }


def run_core() -> dict[str, Any]:
    run_preflight()
    ralph_root, parent, payloads = current_state()
    before = numbered_generations(ralph_root)
    prior_ids = evidence_ids(payloads)
    summary = core_summary()
    generation = commit_active_failed_generation(
        payloads=payloads, summary=summary, expected_evidence_id=CORE_EVIDENCE_ID
    )
    _, current, sealed = current_state()
    if (
        current != generation
        or generation_number(current) != generation_number(parent) + 1
    ):
        raise SystemExit("Q03 core generation pointer mismatch")
    if evidence_ids(sealed) != [*prior_ids, CORE_EVIDENCE_ID]:
        raise SystemExit("Q03 core did not append exactly E0159")
    if sealed["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
        raise SystemExit("Q03 core evidence summary mismatch")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or len(after) != EXPECTED_PARENT_COUNT + 1:
        raise SystemExit("Q03 core did not preserve all prior generations")
    integrity = verify_generation_store(EXPECTED_PARENT_COUNT + 1)
    write_json(ATTEMPT / "rah-core-integrity.json", integrity)
    evidence.bind_rah_state(
        core_generation=generation,
        core_evidence_id=CORE_EVIDENCE_ID,
        final_closeout_evidence_id=FINAL_EVIDENCE_ID,
    )
    evidence.verify()
    return {
        "completion_ready": False,
        "evidence_id": CORE_EVIDENCE_ID,
        "final_closeout_evidence_id": FINAL_EVIDENCE_ID,
        "generation": generation,
        "mode": "core",
        "parent_generation": parent,
        "state_verification": integrity,
        "status": "active",
    }


def run_final() -> dict[str, Any]:
    evidence.verify()
    ralph_root, parent, payloads = current_state()
    assert_active(payloads)
    report = read_json(ATTEMPT / "report.json")
    rah_state = report.get("rah_state")
    if not isinstance(rah_state, dict) or rah_state.get("core_generation") != parent:
        raise SystemExit("Q03 report does not bind current core generation")
    if (
        rah_state.get("core_evidence_id") != CORE_EVIDENCE_ID
        or rah_state.get("final_closeout_evidence_id") != FINAL_EVIDENCE_ID
        or evidence_ids(payloads)[-1] != CORE_EVIDENCE_ID
    ):
        raise SystemExit("Q03 report and live ledger evidence IDs disagree")
    if payloads["evidence_ledger.json"]["entries"][-1].get("summary") != core_summary():
        raise SystemExit("stored Q03 core summary changed before final seal")
    before = numbered_generations(ralph_root)
    prior_ids = evidence_ids(payloads)
    summary, hashes = final_summary(parent)
    generation = commit_active_failed_generation(
        payloads=payloads, summary=summary, expected_evidence_id=FINAL_EVIDENCE_ID
    )
    _, current, sealed = current_state()
    if (
        current != generation
        or generation_number(current) != generation_number(parent) + 1
    ):
        raise SystemExit("Q03 final generation pointer mismatch")
    if evidence_ids(sealed) != [*prior_ids, FINAL_EVIDENCE_ID]:
        raise SystemExit("Q03 final did not append exactly E0160")
    if sealed["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
        raise SystemExit("Q03 final closeout summary mismatch")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or len(after) != EXPECTED_PARENT_COUNT + 2:
        raise SystemExit("Q03 final did not preserve all prior generations")
    return {
        "artifact_hashes": hashes,
        "completion_ready": False,
        "evidence_id": FINAL_EVIDENCE_ID,
        "generation": generation,
        "mode": "final",
        "parent_generation": parent,
        "state_verification": verify_generation_store(EXPECTED_PARENT_COUNT + 2),
        "status": "active",
    }


def run_verify() -> dict[str, Any]:
    evidence.verify()
    ralph_root, generation, payloads = current_state()
    assert_active(payloads)
    count = len(numbered_generations(ralph_root))
    if count == EXPECTED_PARENT_COUNT:
        return run_preflight()
    if count == EXPECTED_PARENT_COUNT + 1:
        integrity = verify_generation_store(count)
        if evidence_ids(payloads)[-1] != CORE_EVIDENCE_ID:
            raise SystemExit("Q03 core tail is not E0159")
        return {
            "mode": "core-verify",
            "state_verification": integrity,
            "status": "PASS",
        }
    if count != EXPECTED_PARENT_COUNT + 2 or generation_number(generation) != 158:
        raise SystemExit(f"unexpected Q03 generation count: {count}")
    identifiers = evidence_ids(payloads)
    if identifiers[-2:] != [CORE_EVIDENCE_ID, FINAL_EVIDENCE_ID]:
        raise SystemExit("sealed ledger does not end with Q03 core/final evidence")
    report = read_json(ATTEMPT / "report.json")
    parent = str(report["rah_state"]["core_generation"])
    summary, hashes = final_summary(parent)
    if payloads["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
        raise SystemExit(
            "stored Q03 final evidence differs from current closeout bytes"
        )
    return {
        "artifact_hashes": hashes,
        "completion_ready": False,
        "generation": generation,
        "latest_evidence_id": FINAL_EVIDENCE_ID,
        "mode": "verify",
        "state_verification": verify_generation_store(count),
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
