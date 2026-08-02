#!/usr/bin/env python3
"""Seal F01-0002 evidence and F01-SG002 without rewriting history."""

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
ATTEMPT = ROOT / "artifacts" / "work_packages" / "F01" / "attempts" / "0002"
AUTOMATION = (
    ROOT
    / ".rah"
    / "helpers"
    / "recursive-architecture-refactoring-auto"
    / "automation"
)
sys.path.insert(0, str(AUTOMATION))

import ralph_harness as rh  # noqa: E402
import state_store  # noqa: E402


CORE_PARENT = "000033-e5f23709"
IMPLEMENTATION_EVIDENCE_ID = "E0035"
GAP_EVIDENCE_ID = "E0036"
FINAL_EVIDENCE_ID = "E0037"
BLOCK_REASON = (
    "F01-SG002 requires a product-owner HumanDecision assigning ownership and "
    "execution timing for packaged canonical snapshot reprojection after later "
    "canonical schema/OpenAPI changes, choosing a new B04 attempt or a distinct "
    "integration package, and deciding whether F01 PASS waits for reprojection "
    "or may transfer the exact drift as bounded downstream debt. F01 cannot "
    "modify B04-owned src/epistemic_foundry/_canonical/** or waive the new "
    "repository regression. F02 and F03 remain waiting; completion_ready=false."
)

FIXED_HASHES = {
    "artifacts/authority_decisions/HD-EF4-F01-SG001-20260729-001.human-decision.json": "1a4f8729628ffc6409e0cc7bd36e3aba7913836dabf5e97ecfc9eb061617c196",
    "artifacts/work_packages/F01/report.json": "f71fa20f5646a9c47672ee2abc152f03af67b5e5d88df04657455bd468fe3134",
    "artifacts/work_packages/F01/commands.jsonl": "5fad33dc0fee109c98ce0ea737cbc1605b83376f1de80d0afa0319a30835a5f2",
    "artifacts/work_packages/F01/review.md": "342507ec2a0b34c23cf3d3a35bd086a0fc3282a5e9548bcb40dcb1561417ddf7",
    "artifacts/work_packages/B04/attempts/0002/report.json": "a75e724b453bf58ce2745af174e96d7f08616bd09467e3b047b78f31b8add643",
    "packages/foundry-kernel/src/forge/classifier/epistemic-work-classifier.mjs": "16ce5f1c1622ca908d1f781bf7be094834636d73db0619cf2759e788d1e18c64",
    "packages/foundry-kernel/src/forge/classifier/classification-committer.mjs": "a603aa354cab8e9bcdc318e7a5075b88dd754f0e84c28d11eb17553a19975a5e",
    "schemas/epistemic-work-classification.schema.json": "dbe8437eae1ec8c956b1290556efa7f2bb89c862134870d80f15e6e49679efa9",
    "examples/sample_epistemic-work-classification.json": "ab805fed88f6c25eb6cb708ea9cb854193d90ccd21ce87baa06457f2fb018b7c",
    "workflows/forge_research_cycle.workflow.yaml": "cf95ed843b87f473653976735c5d06ce4462ace337efaa4d60fac4373b20e454",
    "manifests/development_manifest.yaml": "526f744b3ce67ebc3bf4a6e9f82defa83455568c4ae594cbf70d51d0cb436e63",
    "manifests/acceptance_matrix.yaml": "004ecdffd791c7dd318704e0595fb675baf596b9c6fb8f88deca96940bf032d3",
    "tests/golden/forge/f01_classifier_gold_cases.json": "3adf6be1dc5ce43455ece62a26ba2ce02d064cb46bb249bf5c408387070843c7",
    "tests/golden/forge/f01_classifier_adversarial_cases.json": "93a7617d29a52fe3af9bcc15a395056f5a38afc5d36b80034a1f3c547f0d6f66",
    "tests/golden/forge/f01_classifier_hash_vectors.json": "9715c2e6e374fdfedc4d6011fec498f71e4396ad788773c93b3b49bae25b0915",
    "tests/golden/forge/f01_classifier_override_cases.json": "afe77ea97803b280fb6333bc629dd3c7d7bcc96090d7e1f4155567251cf9264c",
    "tests/test_f01_epistemic_work_classifier.py": "98516fbc6c99c3ee06f61b6e3c251b5fbfbab7bd1b0df2a6afa7f996c3d2e5d1",
    "tests/test_f01_underprocessing_guard.py": "a7595337682857c0b6a37924f80056bd6f4bb77b1954875eb966a35098199d7c",
    "tests/test_f01_workflow_contract.py": "61b5effd4694a82a5a3124e31a41dfd3141973d82537001e0c6a3ad8002c314a",
}

CORE_ARTIFACTS = (
    "classifier-verification.json",
    "monotonicity-report.json",
    "hash-vector-report.json",
    "full-regression-impact.json",
    "dependency-status.json",
    "review.md",
    "commands.jsonl",
    "report.json",
    "f01-rah-seal.py",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"cannot read JSON evidence {path}: {error}")
    if not isinstance(payload, dict):
        raise SystemExit(f"JSON evidence is not an object: {path}")
    return payload


def read_commands() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for number, raw in enumerate(
        (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as error:
            raise SystemExit(f"commands.jsonl line {number} is invalid: {error}")
        if not isinstance(row, dict):
            raise SystemExit(f"commands.jsonl line {number} is not an object")
        rows.append(row)
    ids = [row.get("command_id") for row in rows]
    if any(not isinstance(value, str) for value in ids) or len(ids) != len(set(ids)):
        raise SystemExit("commands.jsonl has missing or duplicate command IDs")
    return rows


def numbered_generations(ralph_root: Path) -> list[str]:
    return sorted(
        path.name
        for path in (ralph_root / "generations").iterdir()
        if path.is_dir() and re.fullmatch(r"\d{6}-[0-9a-f]{8}", path.name)
    )


def evidence_ids(payloads: dict[str, Any]) -> list[str]:
    ledger = payloads.get("evidence_ledger.json")
    if not isinstance(ledger, dict) or not isinstance(ledger.get("entries"), list):
        raise SystemExit("RAH evidence ledger is invalid")
    return [str(entry.get("id")) for entry in ledger["entries"] if isinstance(entry, dict)]


def current_state() -> tuple[Path, str, dict[str, Any]]:
    ralph_root = ROOT / ".rah" / "ralph"
    current = state_store.read_current(ralph_root)
    if current is None:
        raise SystemExit("No committed RAH generation")
    generation, payloads = current
    verified = state_store.verify_current(ralph_root)
    if verified.get("generation") != generation:
        raise SystemExit("RAH pointer and generation verification disagree")
    return ralph_root, generation, payloads


def assert_fixed_hashes() -> None:
    for relative, expected in FIXED_HASHES.items():
        actual = sha256(ROOT / relative)
        if actual != expected:
            raise SystemExit(
                f"fixed evidence hash mismatch for {relative}: {actual} != {expected}"
            )


def assert_core_artifacts() -> None:
    for name in CORE_ARTIFACTS:
        if not (ATTEMPT / name).is_file():
            raise SystemExit(f"missing F01-0002 artifact: {name}")
    verification = read_json(ATTEMPT / "classifier-verification.json")
    monotonicity = read_json(ATTEMPT / "monotonicity-report.json")
    hash_vectors = read_json(ATTEMPT / "hash-vector-report.json")
    regression = read_json(ATTEMPT / "full-regression-impact.json")
    dependency = read_json(ATTEMPT / "dependency-status.json")
    report = read_json(ATTEMPT / "report.json")
    if verification.get("status") != "PASS":
        raise SystemExit("classifier verification is not PASS")
    if monotonicity.get("status") != "PASS":
        raise SystemExit("monotonicity report is not PASS")
    exhaustive = monotonicity.get("exhaustive_signal_set_test")
    pairwise = monotonicity.get("pairwise_monotonicity")
    if not isinstance(exhaustive, dict) or exhaustive.get("evaluated_subset_count") != 1023:
        raise SystemExit("monotonicity report does not cover all 1023 subsets")
    if not isinstance(pairwise, dict) or pairwise.get("subset_to_superset_comparison_count") != 58025:
        raise SystemExit("monotonicity report does not cover all 58025 comparisons")
    if hash_vectors.get("status") != "PASS" or hash_vectors.get("passed") != 4:
        raise SystemExit("hash vector report is not 4/4 PASS")
    if regression.get("status") != "FAIL" or regression.get("new_repository_failure_count") != 1:
        raise SystemExit("full regression impact does not preserve the new failure")
    drift = regression.get("projection_drift")
    if not isinstance(drift, dict) or drift.get("mismatches") != [
        "canonical-registry.json",
        "schemas/epistemic-work-classification.schema.json",
    ]:
        raise SystemExit("full regression impact does not bind the exact projection drift")
    if dependency.get("status") != "SPEC_GAP" or dependency.get("spec_gap_id") != "F01-SG002":
        raise SystemExit("dependency status does not record F01-SG002")
    if report.get("status") != "SPEC_GAP" or report.get("spec_gap_id") != "F01-SG002":
        raise SystemExit("F01 report is not SPEC_GAP F01-SG002")
    if report.get("implementation_status") != "PASS" or report.get("completion_ready") is not False:
        raise SystemExit("F01 report implementation/completion state is inconsistent")
    review = (ATTEMPT / "review.md").read_text(encoding="utf-8")
    if "Classifier implementation assessment: `PASS`" not in review:
        raise SystemExit("review does not record the classifier implementation PASS")
    if "Overall package status: `SPEC_GAP (F01-SG002)`" not in review:
        raise SystemExit("review does not record F01-SG002")
    normalized_review = " ".join(review.split())
    if "not external actor-independent certification" not in normalized_review:
        raise SystemExit("review omits the actor-independence limitation")
    read_commands()


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
    if flat_stamps != 6 or flat_matches != 6:
        raise SystemExit(
            f"flat snapshot mismatch: stamps={flat_stamps}, matches={flat_matches}"
        )
    return {
        "current_generation": current,
        "retained_generation_count": len(generations),
        "generation_file_hashes_verified": verified_hashes,
        "flat_snapshot_stamps_verified": flat_stamps,
        "flat_snapshot_content_matches": flat_matches,
        "generation_manifest_sha256": sha256(
            ralph_root / "generations" / current / "generation-manifest.json"
        ),
        "latest_evidence_id": evidence_ids(payloads)[-1],
        "completion_ready": payloads["loop_state.json"]["completion_readiness"]["ready"],
    }


def core_summary() -> str:
    return (
        "F01-0002 implementation evidence: the deterministic Kernel classifier "
        "passes 30 Node and 24 Python targeted tests; fixed gold 14/14, adversarial "
        "16/16, hash vectors 4/4 and override fixtures 6/6; all 1023 signal subsets "
        "and 58025 subset/superset comparisons have zero underclassification, "
        "monotonicity or protection violations. Verification sha256:"
        f"{sha256(ATTEMPT / 'classifier-verification.json')}; monotonicity sha256:"
        f"{sha256(ATTEMPT / 'monotonicity-report.json')}; hash vectors sha256:"
        f"{sha256(ATTEMPT / 'hash-vector-report.json')}. Schema/example cardinality "
        "remains 124/124, workflow authority and canonical capabilities pass, and "
        "F01-0001 plus the dirty worktree remain preserved. completion_ready=false."
    )


def gap_summary() -> str:
    return (
        "F01-0002 SPEC_GAP F01-SG002: full Python regression is 936 passed and "
        "1 failed because the F01-authorized root EpistemicWorkClassification "
        "schema now differs from the B04-owned packaged snapshot, producing exact "
        "mismatches canonical-registry.json and schemas/epistemic-work-"
        "classification.schema.json. Regression impact sha256:"
        f"{sha256(ATTEMPT / 'full-regression-impact.json')}. F01 cannot modify "
        "src/epistemic_foundry/_canonical/**, and no authority defines post-B04 "
        "reprojection ownership/timing or whether F01 PASS waits for it. The sole "
        "Node failure S04-TM004 is pre-existing and separate. F02/F03 remain waiting; "
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


def run_preflight() -> dict[str, Any]:
    assert_fixed_hashes()
    assert_core_artifacts()
    ralph_root, generation, payloads = current_state()
    if generation != CORE_PARENT:
        raise SystemExit(f"unexpected F01 core parent {generation}; expected {CORE_PARENT}")
    if evidence_ids(payloads) != [f"E{index:04d}" for index in range(1, 35)]:
        raise SystemExit("F01 core preflight requires preserved E0001-E0034")
    if payloads["loop_state.json"].get("status") != "active":
        raise SystemExit("F01 core preflight requires active RAH state")
    generations = numbered_generations(ralph_root)
    if len(generations) != 33 or generations[-1] != generation:
        raise SystemExit("F01 core preflight requires all 33 retained generations")
    return {
        "mode": "preflight",
        "generation": generation,
        "latest_evidence_id": "E0034",
        "retained_generation_count": len(generations),
        "commands_parsed": len(read_commands()),
        "completion_ready": False,
    }


def run_core() -> dict[str, Any]:
    run_preflight()
    ralph_root, parent, _ = current_state()
    before = numbered_generations(ralph_root)
    result, output = invoke_ralph(
        [
            "--record-evidence",
            core_summary(),
            "--record-gap",
            gap_summary(),
            "--block",
            BLOCK_REASON,
            "--no-increment",
        ]
    )
    if result != 0:
        raise SystemExit(f"RAH core blocker append failed with exit {result}: {output}")
    _, generation, payloads = current_state()
    expected_ids = [f"E{index:04d}" for index in range(1, 37)]
    if evidence_ids(payloads) != expected_ids:
        raise SystemExit("F01 core seal did not append exactly E0035 and E0036")
    entries = payloads["evidence_ledger.json"]["entries"]
    if entries[-2].get("kind") != "evidence" or entries[-2].get("summary") != core_summary():
        raise SystemExit("E0035 is not the exact F01 implementation evidence")
    if entries[-1].get("kind") != "documented_gap" or entries[-1].get("summary") != gap_summary():
        raise SystemExit("E0036 is not the exact F01-SG002 documented gap")
    loop = payloads["loop_state.json"]
    if loop.get("status") != "blocked" or loop.get("blocked_reason") != BLOCK_REASON:
        raise SystemExit("RAH did not persist the exact F01-SG002 blocker")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("F01 core seal did not preserve every prior generation")
    verification = verify_generation_store(34)
    return {
        "mode": "core",
        "parent_generation": parent,
        "generation": generation,
        "implementation_evidence_id": IMPLEMENTATION_EVIDENCE_ID,
        "documented_gap_evidence_id": GAP_EVIDENCE_ID,
        "status": "blocked",
        "spec_gap_id": "F01-SG002",
        "state_verification": verification,
        "completion_ready": False,
    }


def run_final() -> dict[str, Any]:
    assert_fixed_hashes()
    assert_core_artifacts()
    ralph_root, parent, payloads = current_state()
    if not re.fullmatch(r"000034-[0-9a-f]{8}", parent):
        raise SystemExit(f"unexpected F01 final parent generation: {parent}")
    if evidence_ids(payloads) != [f"E{index:04d}" for index in range(1, 37)]:
        raise SystemExit("F01 final seal requires preserved E0001-E0036")
    entries = payloads["evidence_ledger.json"]["entries"]
    if entries[-2].get("summary") != core_summary() or entries[-1].get("summary") != gap_summary():
        raise SystemExit("F01 core evidence summaries changed before final seal")
    report = read_json(ATTEMPT / "report.json")
    rah_state = report.get("rah_state")
    if not isinstance(rah_state, dict):
        raise SystemExit("F01 report lacks rah_state")
    if rah_state.get("core_generation") != parent:
        raise SystemExit("F01 report core generation does not match RAH authority")
    if rah_state.get("implementation_evidence_id") != IMPLEMENTATION_EVIDENCE_ID:
        raise SystemExit("F01 report does not bind E0035")
    if rah_state.get("documented_gap_evidence_id") != GAP_EVIDENCE_ID:
        raise SystemExit("F01 report does not bind E0036")
    if rah_state.get("final_closeout_evidence_id") != FINAL_EVIDENCE_ID:
        raise SystemExit("F01 report does not reserve E0037")
    integrity = read_json(ATTEMPT / "rah-core-integrity.json")
    if integrity.get("status") != "PASS" or integrity.get("current_generation") != parent:
        raise SystemExit("F01 core RAH integrity evidence is not PASS")
    closeout_names = (
        "report.json",
        "review.md",
        "commands.jsonl",
        "classifier-verification.json",
        "monotonicity-report.json",
        "hash-vector-report.json",
        "full-regression-impact.json",
        "dependency-status.json",
        "rah-core-integrity.json",
        "f01-rah-seal.py",
    )
    hashes = {name: sha256(ATTEMPT / name) for name in closeout_names}
    summary = (
        "F01-0002 SPEC_GAP closeout is hash-sealed after core blocker generation "
        f"{parent}: report sha256:{hashes['report.json']}; review sha256:"
        f"{hashes['review.md']}; commands sha256:{hashes['commands.jsonl']}; "
        f"classifier verification sha256:{hashes['classifier-verification.json']}; "
        f"monotonicity sha256:{hashes['monotonicity-report.json']}; hash vectors "
        f"sha256:{hashes['hash-vector-report.json']}; regression impact sha256:"
        f"{hashes['full-regression-impact.json']}; dependency status sha256:"
        f"{hashes['dependency-status.json']}; core RAH integrity sha256:"
        f"{hashes['rah-core-integrity.json']}; preservation wrapper sha256:"
        f"{hashes['f01-rah-seal.py']}. Classifier implementation gates pass, but "
        "F01 remains SPEC_GAP F01-SG002; F02/F03 remain waiting; all prior "
        "generations, reports and dirty-worktree content remain preserved; "
        "completion_ready=false."
    )
    before = numbered_generations(ralph_root)
    result, output = invoke_ralph(
        ["--record-evidence", summary, "--no-increment", "--no-update-current-loop"]
    )
    if result != 0:
        raise SystemExit(f"RAH final closeout append failed with exit {result}: {output}")
    _, generation, sealed = current_state()
    if evidence_ids(sealed) != [f"E{index:04d}" for index in range(1, 38)]:
        raise SystemExit("F01 final seal did not append exactly E0037")
    if sealed["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
        raise SystemExit("E0037 does not match the closeout hash seal")
    if sealed["loop_state.json"].get("status") != "blocked":
        raise SystemExit("F01 final closeout did not retain blocked status")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("F01 final seal did not preserve every prior generation")
    verification = verify_generation_store(35)
    return {
        "mode": "final",
        "parent_generation": parent,
        "generation": generation,
        "evidence_id": FINAL_EVIDENCE_ID,
        "artifact_hashes": hashes,
        "state_verification": verification,
        "status": "blocked",
        "completion_ready": False,
    }


def run_verify() -> dict[str, Any]:
    assert_fixed_hashes()
    assert_core_artifacts()
    generations = numbered_generations(ROOT / ".rah" / "ralph")
    if len(generations) not in (33, 34, 35):
        raise SystemExit(f"unexpected retained generation count: {len(generations)}")
    return {
        "mode": "verify",
        "fixed_evidence": "PASS",
        "state_verification": verify_generation_store(len(generations)),
        "completion_ready": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("preflight", "core", "final", "verify"))
    args = parser.parse_args()
    if args.mode == "preflight":
        result = run_preflight()
    elif args.mode == "core":
        result = run_core()
    elif args.mode == "final":
        result = run_final()
    else:
        result = run_verify()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
