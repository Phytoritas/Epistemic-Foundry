#!/usr/bin/env python3
"""Build byte-bound evidence for the J02-0004 authority rebind.

The prior attempt's parser helpers are loaded read-only, but no prior evidence
document is copied or treated as current proof.  Every J02 result is recomputed
from the current inventory, fixtures, source bytes, and JUnit receipts.  Prior
attempt files are used only as immutable-history and semantic-delta anchors.
"""

from __future__ import annotations

import argparse
import copy
import fnmatch
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import yaml


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/J02/attempts/0004"
PACKAGE_ROOT = ROOT / "artifacts/work_packages/J02"
ATTEMPT_ID = "J02-0004"
WORK_PACKAGE_ID = "J02"
RECORDED_AT = "2026-07-31T08:30:00.000Z"

INVENTORY_PATH = ROOT / "plugins/epistemic-foundry/skills/skill-inventory.json"
EXPECTED_FIXTURE_PATH = ROOT / "tests/fixtures/j02/skill-inventory.expected.json"
SELECTION_FIXTURE_PATH = ROOT / "tests/fixtures/j02/reference-selection-cases.json"
MANIFEST_PATH = ROOT / "manifests/development_manifest.yaml"
MASTER_SPEC_PATH = ROOT / "MASTER_SPEC.md"
RECEIPT_SCHEMA_PATH = ROOT / "schemas/artifact-receipt.schema.json"
DECISION_PATH = (
    ROOT
    / "artifacts/authority_decisions/"
    "HD-EF4-C01-SG005-20260731-001.human-decision.json"
)
C01_REGRESSION_PATH = (
    ROOT / "artifacts/work_packages/C01/attempts/0008/full-regression-impact.json"
)

DECISION_ID = "HD-EF4-C01-SG005-20260731-001"
DECISION_HASH = "sha256:b833da71edfd31f8a41da371baad9aa75775d527ded2617b9a0b41d2353e028b"
CURRENT_MASTER_HASH = "sha256:a204288fb2b1e550cebf023424785774da30941cb7615fecb34f7b44822aff75"
PRIOR_MASTER_HASH = "sha256:d4854c916594610e0503f9b017c57b0dbac9f52eef78b825b922fdf26b1a0fe3"
CURRENT_INVENTORY_HASH = "sha256:6de50ce7f267c272c58788f032759dddf720216ebb7b7e4716b0488d4052ef54"
PRIOR_INVENTORY_HASH = "sha256:028264183f20ff6585c85052def9c9e8c75f68099c767e91169267bff21709c6"
CURRENT_MANIFEST_HASH = "sha256:6ccf07571c34c9010a10605ba201ba698a09f6343a281565520d392e4c77e063"
STALE_BOUND_MANIFEST_HASH = "sha256:5dd99d2aae1e9ef662b9b8242b5fa921621434c6600c9c06e3a573d03079bb12"

PRIMARY_PRODUCT_FILES = (
    "plugins/epistemic-foundry/skills/skill-inventory.json",
)
DERIVED_FIXTURE_PROJECTIONS = (
    "tests/fixtures/j02/skill-inventory.expected.json",
    "tests/fixtures/j02/reference-selection-cases.json",
)
CHANGED_J02_FILES = (*PRIMARY_PRODUCT_FILES, *DERIVED_FIXTURE_PROJECTIONS)

JUNIT_HASHES = {
    "targeted-python-suite.junit.xml":
        "9315848abeb1bc985cb4628b6933d62d148b6aa0428d082f908787a7fdb18fda",
    "targeted-node-suite.junit.xml":
        "58e3ab719cc5eb1700f67304c7057bb803a329bea98761967614444381234746",
    "j01-regression-node-suite.junit.xml":
        "751350673e5b16e4986c16d22500a07f844be2579f282c1002a0199647f407fe",
    "full-python-suite.junit.xml":
        "e2aba81719b896e2c479c50cb4aa65fd068b300451c8edcdc1b1907e9eb47679",
    "full-node-suite.junit.xml":
        "b0cae01818bf76df6acf469a934ca7755739c5ede438875357e69c580ffdd7bb",
}

PRESERVED_HISTORY = {
    "artifacts/work_packages/J02/attempts/0001/report.json":
        "6b0f4f37acbe1014afcf17ef5449fa4ed799e7ca0e7ea7523c014a3a44607688",
    "artifacts/work_packages/J02/attempts/0002/report.json":
        "17e342ae7f54707ebc0acc17f695507397b9d300a54cef741b2ab3ed05ffbd0c",
    "artifacts/work_packages/J02/attempts/0003/report.json":
        "d348ddc7c8b2d476d3424a6459079f0011d9fc69e29056131832b3ae2fc2d184",
    "artifacts/work_packages/J02/attempts/0003/review.md":
        "00b02015ddf13325c1695a4d6c7962db9a68388e60e0d7fc4c18b5b5df0a970a",
    "artifacts/work_packages/J02/attempts/0003/commands.jsonl":
        "bed80107ab62304c748210bba272d2bc3dfe6b5cbed07e783ea1c8fdd14d239c",
    "artifacts/work_packages/C01/attempts/0008/report.json":
        "bdbb3760c5799f8835bbe7becb87c8a3ab7c3252ebfb8734266d3106613d7a36",
    "artifacts/work_packages/C01/attempts/0008/full-regression-impact.json":
        "5ef986b23928fd8abd70d701fc4546e333e0e152df45fbc866957af7f2c144f3",
    "artifacts/work_packages/C01/attempts/0008/review.md":
        "3fe501fcf9da1094b3eee7fe5eb2a56f3a455255765ac19617ca5f70a31d5c61",
    "artifacts/authority_decisions/HD-EF4-C01-SG005-20260731-001.human-decision.json":
        "c7faa17fab992b701749c7fc492b2aa7d03442cfa6e065d58f154c79c50113ab",
    "C01-SG005_무엇을_승인해야_하는가.md":
        "c90851ced019e2f0e65dd652ff222ce91562641caa153fbcac7cb38212b3221f",
    "pyproject.toml":
        "31cf5dffa4703052d70536dbbb6e64d917900c70d52b039f9c9cbf09920353db",
    "uv.lock":
        "5c3798ff0323f9352d73f17fa93913590d7dbb5382dd0de26b1619e775b58caa",
}

PRIOR_PROJECTION_HASHES = {
    "plugins/epistemic-foundry/skills/skill-inventory.json":
        "093a0892377db04f66dfb49c2f1848067de5334e50c96f85990a7968405d211c",
    "tests/fixtures/j02/skill-inventory.expected.json":
        "b8f692384e27f038f0a89a2b2468a339fede8fd0d9b42a1650561b832d7fb321",
    "tests/fixtures/j02/reference-selection-cases.json":
        "4505491f1844bef6e420068c9600d4c18ec9982ea0cba67a007851e1aaaa30fe",
}

OUTPUT_NAMES = (
    "metadata-budget-verification.json",
    "tokenizer-verification.json",
    "inventory-authority-verification.json",
    "reference-selection-verification.json",
    "reference-reachability-verification.json",
    "dependency-status.json",
    "full-regression-impact.json",
    "preexisting-debt-reconciliation.json",
    "write-scope-verification.json",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_id(path: Path) -> str:
    return "sha256:" + sha256(path)


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def render(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"JSON artifact is not an object: {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(render(value), encoding="utf-8", newline="\n")


def canonical_hash_excluding(document: dict[str, Any], field: str) -> str:
    preimage = copy.deepcopy(document)
    preimage.pop(field, None)
    return sha256_bytes(canonical_bytes(preimage))


def load_prior_parser() -> ModuleType:
    path = ROOT / "artifacts/work_packages/J02/attempts/0003/build_j02_0003_evidence.py"
    spec = importlib.util.spec_from_file_location("j02_0004_prior_parser", path)
    if spec is None or spec.loader is None:
        raise SystemExit("cannot load the immutable J02 parser helper")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.ATTEMPT = ATTEMPT
    module.ATTEMPT_ID = ATTEMPT_ID
    module.JUNIT_HASHES = JUNIT_HASHES
    module.S04_CURRENT_HASH = CURRENT_MANIFEST_HASH.removeprefix("sha256:")
    module.S04_STALE_BOUND_HASH = STALE_BOUND_MANIFEST_HASH.removeprefix("sha256:")
    return module


BASE = load_prior_parser()


def assert_preserved_history() -> dict[str, str]:
    observed: dict[str, str] = {}
    for relative, expected in PRESERVED_HISTORY.items():
        path = ROOT / relative
        if not path.is_file() or sha256(path) != expected:
            raise SystemExit(f"immutable history changed or is missing: {relative}")
        observed[relative] = "sha256:" + expected
    for name, expected in JUNIT_HASHES.items():
        path = ATTEMPT / name
        if not path.is_file() or sha256(path) != expected:
            raise SystemExit(f"J02-0004 JUnit receipt changed: {name}")
    return observed


def authority_decision() -> dict[str, Any]:
    decision = read_json(DECISION_PATH)
    if (
        decision.get("decision_id") != DECISION_ID
        or decision.get("subject_id") != "C01-SG005"
        or decision.get("authority_role") != "product_owner"
        or decision.get("non_mutation_acknowledgement") is not True
    ):
        raise SystemExit("C01-SG005 HumanDecision identity or authority changed")
    computed = canonical_hash_excluding(decision, "decision_hash")
    if computed != DECISION_HASH or decision.get("decision_hash") != computed:
        raise SystemExit("C01-SG005 HumanDecision self-hash mismatch")
    return {
        "decision_id": DECISION_ID,
        "decision_hash": computed,
        "path": DECISION_PATH.relative_to(ROOT).as_posix(),
        "file_sha256": sha256_id(DECISION_PATH),
        "status": "PASS",
    }


def source_inventory() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for relative in CHANGED_J02_FILES:
        path = ROOT / relative
        data = path.read_bytes()
        if data.startswith(b"\xef\xbb\xbf") or b"\x00" in data:
            raise SystemExit(f"invalid encoding marker in J02 file: {relative}")
        if "\ufffd" in data.decode("utf-8"):
            raise SystemExit(f"replacement character in J02 file: {relative}")
        rows.append(
            {
                "path": relative,
                "byte_size": len(data),
                "sha256": sha256_bytes(data),
                "role": (
                    "AUTHORIZED_PRIMARY_PRODUCT_FILE"
                    if relative in PRIMARY_PRODUCT_FILES
                    else "DERIVED_TEST_FIXTURE_IDENTITY_PROJECTION"
                ),
            }
        )
    return rows


def prove_projection_only_delta() -> dict[str, Any]:
    current_master = sha256_id(MASTER_SPEC_PATH)
    if current_master != CURRENT_MASTER_HASH:
        raise SystemExit("MASTER_SPEC bytes changed after J02 authority rebinding")

    reconstructed: dict[str, str] = {}
    for relative, prior_hash in PRIOR_PROJECTION_HASHES.items():
        data = (ROOT / relative).read_bytes()
        data = data.replace(
            CURRENT_MASTER_HASH.encode("ascii"), PRIOR_MASTER_HASH.encode("ascii")
        )
        data = data.replace(
            CURRENT_INVENTORY_HASH.encode("ascii"), PRIOR_INVENTORY_HASH.encode("ascii")
        )
        observed = hashlib.sha256(data).hexdigest()
        if observed != prior_hash:
            raise SystemExit(
                f"J02-0004 changed more than authority identity in {relative}"
            )
        reconstructed[relative] = "sha256:" + observed
    return {
        "status": "PASS",
        "prior_master_spec_hash": PRIOR_MASTER_HASH,
        "current_master_spec_hash": CURRENT_MASTER_HASH,
        "prior_inventory_hash": PRIOR_INVENTORY_HASH,
        "current_inventory_hash": CURRENT_INVENTORY_HASH,
        "reconstructed_prior_file_hashes": reconstructed,
        "semantic_field_change_count": 0,
        "selection_hash_change_count": 0,
        "fixture_identity_projection_count": len(DERIVED_FIXTURE_PROJECTIONS),
    }


def inventory_documents() -> tuple[dict[str, Any], ...]:
    metadata, tokenizer, authority = BASE.inventory_evidence()
    selection, reachability = BASE.graph_evidence()
    inventory = read_json(INVENTORY_PATH)
    references = inventory.get("references")
    if not isinstance(references, list) or len(references) != 17:
        raise SystemExit("J02 inventory reference cardinality changed")
    master_bindings = [
        source
        for reference in references
        for source in reference.get("authority_sources", [])
        if source.get("path") == "MASTER_SPEC.md"
    ]
    if len(master_bindings) != 17:
        raise SystemExit("not every J02 reference has one MASTER_SPEC authority binding")
    if any(source.get("sha256") != CURRENT_MASTER_HASH for source in master_bindings):
        raise SystemExit("a J02 reference retains a stale MASTER_SPEC authority hash")
    serialized = INVENTORY_PATH.read_text(encoding="utf-8")
    if PRIOR_MASTER_HASH in serialized:
        raise SystemExit("stale MASTER_SPEC authority hash remains active")
    if inventory.get("inventory_hash") != CURRENT_INVENTORY_HASH:
        raise SystemExit("current J02 inventory hash differs from the approved rebind")
    delta = prove_projection_only_delta()
    authority["authority_rebinding"] = {
        **delta,
        "master_spec_binding_count": len(master_bindings),
        "stale_master_spec_binding_count": 0,
        "inventory_self_hash_recomputed": True,
        "inventory_file_sha256": sha256_id(INVENTORY_PATH),
    }
    selection["prior_attempt_semantic_delta"] = {
        "status": "PASS",
        "semantic_field_change_count": 0,
        "selection_hash_change_count": 0,
        "only_top_level_inventory_identity_changed": True,
    }
    return metadata, tokenizer, authority, selection, reachability


def expected_node_files() -> list[str]:
    files = sorted(
        path.relative_to(ROOT).as_posix()
        for top in ("packages", "tests", "web")
        for path in (ROOT / top).rglob("*.test.mjs")
        if path.is_file()
    )
    if len(files) != 79 or len(set(files)) != 79:
        raise SystemExit(f"live Node test inventory is not exactly 79: {len(files)}")
    return files


def regression_evidence() -> tuple[dict[str, Any], dict[str, Any]]:
    targeted_python = BASE.python_junit(
        "targeted-python-suite.junit.xml",
        {"tests": 20, "failures": 0, "errors": 0, "skipped": 0},
    )
    targeted_node_result = BASE.node_junit(
        "targeted-node-suite.junit.xml",
        expected={
            "tests": 25, "pass": 25, "fail": 0, "cancelled": 0,
            "skipped": 0, "todo": 0,
        },
    )
    j01_result = BASE.node_junit(
        "j01-regression-node-suite.junit.xml",
        expected={
            "tests": 19, "pass": 19, "fail": 0, "cancelled": 0,
            "skipped": 0, "todo": 0,
        },
    )
    full_python = BASE.python_junit(
        "full-python-suite.junit.xml",
        {"tests": 1073, "failures": 17, "errors": 0, "skipped": 0},
    )
    full_node_result = BASE.node_junit(
        "full-node-suite.junit.xml",
        expected={
            "tests": 819, "pass": 818, "fail": 1, "cancelled": 0,
            "skipped": 0, "todo": 0,
        },
    )

    baseline = read_json(C01_REGRESSION_PATH)
    expected_python = {
        str(row["node_id"]): row for row in baseline.get("python_failures", [])
    }
    current_python = {
        str(row["node_id"]): row for row in full_python["failures"]
    }
    if len(expected_python) != 17 or set(current_python) != set(expected_python):
        raise SystemExit("full Python residual is not the exact B04-0009 debt set")
    python_failures: list[dict[str, Any]] = []
    for node_id in sorted(expected_python):
        observed = current_python[node_id]
        expected = expected_python[node_id]
        if "expected 126 canonical schemas, found 127" not in observed["message"]:
            raise SystemExit(f"unexpected Python failure signature: {node_id}")
        if expected.get("classification") != "EXPECTED_B04_0009_PROJECTION_DEBT":
            raise SystemExit(f"C01 baseline classification changed: {node_id}")
        python_failures.append(
            {
                "node_id": node_id,
                "classification": expected["classification"],
                "owner": "B04",
                "resolving_attempt": "B04-0009",
                "normalized_failure_fingerprint": expected[
                    "normalized_failure_fingerprint"
                ],
                "message": "expected 126 canonical schemas, found 127",
            }
        )

    node_summary = full_node_result["summary"]
    observed_files = sorted(
        {row["file"] for row in full_node_result["testcases"] if row["file"]}
    )
    if observed_files != expected_node_files():
        raise SystemExit("full Node receipt does not cover all 79 live test files")
    if len(node_summary["failures"]) != 1:
        raise SystemExit("full Node receipt must contain exactly one residual")
    failure = node_summary["failures"][0]
    if (
        failure["name"] != BASE.S04_TEST
        or failure["file"] != BASE.S04_TEST_FILE
        or CURRENT_MANIFEST_HASH.removeprefix("sha256:") not in failure["message"]
        or STALE_BOUND_MANIFEST_HASH.removeprefix("sha256:") not in failure["message"]
    ):
        raise SystemExit("full Node residual is not exact S04-TM004")

    regression = {
        "attempt_id": ATTEMPT_ID,
        "status": "PASS_WITH_AUTHORIZED_DOWNSTREAM_DEBT",
        "targeted_python": {
            key: value
            for key, value in targeted_python.items()
            if key != "testcase_ids"
        },
        "targeted_node": targeted_node_result["summary"],
        "j01_node_regression": j01_result["summary"],
        "full_python": {
            key: value for key, value in full_python.items() if key != "testcase_ids"
        },
        "full_node": node_summary,
        "python_failures": python_failures,
        "python_projection_debt_failure_count": 17,
        "node_authorized_next_attempt_failure_count": 1,
        "j02_causal_failure_count": 0,
        "new_failure_count": 0,
        "new_skip_xfail_todo_or_cancellation_count": 0,
        "full_node_test_file_count": 79,
        "repository_fully_green": False,
    }
    debt = {
        "attempt_id": ATTEMPT_ID,
        "status": "AUTHORIZED_DOWNSTREAM_DEBT_RECONCILED",
        "debts": [
            {
                "debt_id": "B04-0009-CANONICAL-PROJECTION-COUNT",
                "owner": "B04",
                "resolving_attempt": "B04-0009",
                "failure_count": 17,
                "classification": "EXPECTED_B04_0009_PROJECTION_DEBT",
                "j02_causal_impact": "NONE",
            },
            {
                "debt_id": "S04-TM004",
                "owner": "S04",
                "resolving_attempt": "S04-0004",
                "failure_count": 1,
                "classification": "AUTHORIZED_NEXT_ATTEMPT_S04_0004",
                "current_source_sha256": CURRENT_MANIFEST_HASH,
                "stale_bound_successor_sha256": STALE_BOUND_MANIFEST_HASH,
                "test_name": BASE.S04_TEST,
                "test_file": BASE.S04_TEST_FILE,
                "j02_causal_impact": "NONE",
            },
        ],
        "j02_causal_failure_count": 0,
        "skip_or_xfail_used": False,
        "package_pass_effect": (
            "HD-EF4-C01-SG005-20260731-001 orders S04-0004 next and B04-0009 "
            "later. Both exact residual sets remain visible and cannot be "
            "reclassified as resolved."
        ),
    }
    return regression, debt


def dependency_evidence() -> dict[str, Any]:
    prior = read_json(ROOT / "artifacts/work_packages/J02/attempts/0003/report.json")
    c01 = read_json(ROOT / "artifacts/work_packages/C01/attempts/0008/report.json")
    if prior.get("status") != "PASS" or prior.get("package_status") != "PASS":
        raise SystemExit("J02-0003 immutable predecessor is not PASS")
    if c01.get("status") != "SPEC_GAP" or c01.get("spec_gap_id") != "C01-SG005":
        raise SystemExit("C01-0008 immutable SPEC_GAP history changed")
    return {
        "attempt_id": ATTEMPT_ID,
        "status": "PASS",
        "dependencies": {
            "J01": {"status": "PASS", "manifest_dependency": True},
            "J02-0003": {
                "status": "PASS",
                "report_path": "artifacts/work_packages/J02/attempts/0003/report.json",
                "report_sha256": sha256_id(
                    ROOT / "artifacts/work_packages/J02/attempts/0003/report.json"
                ),
            },
            "C01-0008": {
                "status": "IMMUTABLE_SPEC_GAP_HISTORY",
                "spec_gap_id": "C01-SG005",
                "report_path": "artifacts/work_packages/C01/attempts/0008/report.json",
                "report_sha256": sha256_id(
                    ROOT / "artifacts/work_packages/C01/attempts/0008/report.json"
                ),
            },
        },
        "authority": {
            "human_decision": authority_decision(),
            "effective_attempt_order": [
                "J02-0004", "S04-0004", "C01-0009", "C02-0004",
                "B04-0009", "O02-0002", "C04-0004",
                "NEXT_UNUSED_B04_FINAL",
            ],
        },
        "next_state": {
            "J02": "PASS",
            "S04": "READY_FOR_ATTEMPT_0004",
            "C01": "WAITING_ON_S04_0004",
            "C02": "WAITING_ON_C01_0009",
            "B04-0009": "WAITING_ON_C01_0009_AND_C02_0004",
        },
    }


def run_command(arguments: list[str], *, timeout: int = 300) -> dict[str, Any]:
    completed = subprocess.run(
        arguments,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    return {
        "command": subprocess.list2cmdline(arguments),
        "exit_code": completed.returncode,
        "status": "PASS" if completed.returncode == 0 else "FAIL",
    }


def scope_allows(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def write_scope_evidence() -> dict[str, Any]:
    manifest = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
    packages = manifest if isinstance(manifest, list) else manifest.get("work_packages")
    if not isinstance(packages, list) or len(packages) != 156:
        raise SystemExit("development manifest is not the 156-package DAG")
    rows = [row for row in packages if isinstance(row, dict) and row.get("id") == "J02"]
    if len(rows) != 1 or not isinstance(rows[0].get("write_scope"), list):
        raise SystemExit("development manifest has no unique J02 write scope")
    patterns = [str(value) for value in rows[0]["write_scope"]]
    violations = [path for path in CHANGED_J02_FILES if not scope_allows(path, patterns)]
    if violations:
        raise SystemExit(f"J02 files outside manifest scope: {violations}")
    if not scope_allows("artifacts/work_packages/J02/attempts/0004/report.json", patterns):
        raise SystemExit("J02 artifact scope is absent")

    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if npm is None:
        raise SystemExit("npm is unavailable")
    checks = {
        "npm_check_structure": run_command([npm, "run", "check:structure"]),
        "npm_check_boundaries": run_command([npm, "run", "check:boundaries"]),
        "scoped_git_diff_check": run_command(
            ["git", "diff", "--check", "--", *CHANGED_J02_FILES]
        ),
        "repository_git_diff_check": run_command(["git", "diff", "--check"]),
    }
    failures = [name for name, result in checks.items() if result["exit_code"] != 0]
    if failures:
        raise SystemExit(f"J02 write-scope verification failed: {failures}")
    return {
        "attempt_id": ATTEMPT_ID,
        "status": "PASS",
        "manifest_sha256": sha256_id(MANIFEST_PATH),
        "manifest_package_count": 156,
        "manifest_write_scope": patterns,
        "primary_authorized_product_files": list(PRIMARY_PRODUCT_FILES),
        "derived_fixture_identity_projections": list(DERIVED_FIXTURE_PROJECTIONS),
        "changed_j02_files": source_inventory(),
        "product_write_scope_violation_count": 0,
        "decision_primary_product_path_violation_count": 0,
        "checks": checks,
        "projection_only_delta": prove_projection_only_delta(),
        "preservation": {
            "preserved_history_hashes": assert_preserved_history(),
            "dirty_worktree_preserved": True,
            "subagents_or_fleet_used": False,
            "reset_clean_stash_commit_push_performed": False,
            "s04_files_modified_by_j02_0004": False,
            "schema_or_openapi_files_modified_by_j02_0004": False,
        },
    }


def evidence_documents() -> dict[str, dict[str, Any]]:
    assert_preserved_history()
    metadata, tokenizer, inventory, selection, reachability = inventory_documents()
    regression, debt = regression_evidence()
    return {
        "metadata-budget-verification.json": metadata,
        "tokenizer-verification.json": tokenizer,
        "inventory-authority-verification.json": inventory,
        "reference-selection-verification.json": selection,
        "reference-reachability-verification.json": reachability,
        "dependency-status.json": dependency_evidence(),
        "full-regression-impact.json": regression,
        "preexisting-debt-reconciliation.json": debt,
        "write-scope-verification.json": write_scope_evidence(),
    }


def command_records(documents: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    checks = documents["write-scope-verification.json"]["checks"]
    rows = [
        ("C001", "Inspect C01-SG005 authority, J02-0001..0003 history, current inventory, fixtures, and RAH state", 0, "PASS"),
        ("C002", "Apply exact MASTER_SPEC authority rebind and deterministic inventory self-hash correction", 0, "PASS: one primary inventory file and two identity-only J02 fixture projections"),
        ("C003", "python tools/skill-context/count_tokens.py verify-inventory --root .", 0, "PASS: 29 skills, 17 references, 17/17 current authority bindings"),
        ("C004", "python -m pytest tests/test_j02_context_budget.py --junitxml=<attempt>/targeted-python-suite.junit.xml", 0, "PASS: 20/20"),
        ("C005", "node --test --test-reporter=junit tests/node/j02-reference-reachability.test.mjs tests/node/j02-skill-context-loader.test.mjs", 0, "PASS: 25/25"),
        ("C006", "node --test --test-reporter=junit <J01 routing regression files>", 0, "PASS: 19/19"),
        ("C007", "python -m pytest --junitxml=<attempt>/full-python-suite.junit.xml", 1, "EXPECTED_B04_0009_PROJECTION_DEBT: 1056 passed, exact 17 count failures"),
        ("C008", "node --test --test-concurrency=1 --test-reporter=junit <all 79 live .test.mjs files>", 1, "AUTHORIZED_NEXT_ATTEMPT_S04_0004: 818 passed, exact S04-TM004 only"),
        ("C009", "npm run check:structure", checks["npm_check_structure"]["exit_code"], "PASS"),
        ("C010", "npm run check:boundaries", checks["npm_check_boundaries"]["exit_code"], "PASS"),
        ("C011", "git diff --check -- <three J02 files>", checks["scoped_git_diff_check"]["exit_code"], "PASS"),
        ("C012", "git diff --check", checks["repository_git_diff_check"]["exit_code"], "PASS"),
        ("C013", "Primary-session separate adversarial implementation review", 0, "PASS: zero J02-blocking findings; actor_independence=false"),
        ("D001", "pytest <full suite> without python -m", 2, "DIAGNOSTIC_ONLY: five import collection errors; command shape changed; no product mutation"),
        ("D002", "node --test <guessed J01 filenames>", 1, "DIAGNOSTIC_ONLY: guessed files absent; actual two J01 package tests used"),
        ("D003", "PowerShell foreach pipeline inspection block", 1, "DIAGNOSTIC_ONLY: safety hook blocked command before execution; no mutation"),
        ("D004", "Read .rah/ralph/CURRENT and generation-stamp.json", 1, "DIAGNOSTIC_ONLY: files do not exist; state_store authority used"),
        ("D005", "rg ^# against Node JUnit footer", 1, "DIAGNOSTIC_ONLY: XML comments use a different prefix; parser switched to exact comment form"),
        ("D006", "Reconstruct compact selection fixture through pretty JSON serialization", 1, "DIAGNOSTIC_ONLY: serialization changed formatting; byte replacement proved exact prior hash"),
    ]
    return [
        {
            "command_id": f"{ATTEMPT_ID}-{identifier}",
            "command": command,
            "recorded_at_utc": RECORDED_AT,
            "exit_code": exit_code,
            "result": result,
            "scope": ATTEMPT_ID,
        }
        for identifier, command, exit_code, result in rows
    ]


def review_text(documents: dict[str, dict[str, Any]]) -> str:
    inventory = documents["inventory-authority-verification.json"]
    regression = documents["full-regression-impact.json"]
    return f"""# J02-0004 separate adversarial implementation review

Status: `PASS_WITH_PRIMARY_SESSION_SEPARATE_ADVERSARIAL_IMPLEMENTATION_REVIEW`

Final verdict: `PASS`

Blocking J02 findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_IMPLEMENTATION_REVIEW`

Actor independence: `false`

The product owner requires the correction chain to run in the primary session
without Fleet or subagents. This is a procedurally separate review of the final
J02 bytes, not actor-independent certification.

## Findings

1. All 17 `MASTER_SPEC.md` authority-source entries now bind the current hash
   `{CURRENT_MASTER_HASH}`; the stale authority hash is absent.
2. The deterministic inventory self-hash is
   `{inventory['inventory_hash']}`. It covers the unchanged 29 skills, 17
   references, 4,767 metadata bytes, and 1,112 pinned `o200k_base` tokens.
3. Replacing only the current authority and inventory identity values recreates
   the exact J02-0003 hashes for the inventory and both derived fixtures. No
   selection hash or semantic fixture field changed.
4. Targeted Python is 20/20, targeted Node is 25/25, and J01 routing regression
   is 19/19. The two J02 stale-authority Node failures from C01-0008 are gone.
5. Full Python is {regression['full_python']['totals']['passed']} passed and 17
   failed; every failure is the exact authorized B04-0009 `126` versus `127`
   canonical projection debt. J02 causal failures are zero.
6. Full Node is 818/819. Its only residual is S04-TM004: current manifest
   `{CURRENT_MANIFEST_HASH}` versus stale successor
   `{STALE_BOUND_MANIFEST_HASH}`. The authorizing decision requires S04-0004
   next, so this failure remains visible and is not claimed resolved.
7. J02 changed no S04, schema, OpenAPI, runtime, or prior-attempt file. The
   primary product correction is the inventory; the two fixture changes are
   identity-only projections within the existing exact J02 manifest scope.

## Assurance boundary

J02 PASS establishes current skill-inventory authority and unchanged routing,
selection, and budget semantics. It does not establish S04-0004, C01-0009,
B04-0009, repository-wide green status, release readiness, or product
completion. `implementation_gate=fail` and `completion_ready=false` remain.
"""


def make_receipt(authority_path: Path) -> dict[str, Any]:
    receipt = {
        "receipt_id": "AR-J02-0004-INVENTORY-AUTHORITY-VERIFICATION",
        "artifact_id": "J02-0004-INVENTORY-AUTHORITY-VERIFICATION",
        "action_intent_id": None,
        "media_type": "application/json",
        "content_hash": sha256_id(authority_path),
        "byte_size": authority_path.stat().st_size,
        "created_by": {
            "actor_id": "SVC-FOUNDRY-KERNEL-J02",
            "actor_type": "service",
        },
        "created_at": RECORDED_AT,
        "locator": authority_path.relative_to(ROOT).as_posix(),
        "schema_ref": None,
        "validation_results": [
            {"check": "authority_rebinding", "status": "PASS", "details": "17/17 current MASTER_SPEC bindings"},
            {"check": "context_budget_test", "status": "PASS", "details": "20/20"},
            {"check": "reference_reachability_test", "status": "PASS", "details": "25/25"},
            {"check": "j01_routing_regression", "status": "PASS", "details": "19/19"},
            {"check": "j02_regression_reconciliation", "status": "PASS", "details": "J02-caused failures 0; downstream B04 and S04 debts retained"},
        ],
    }
    receipt["receipt_hash"] = canonical_hash_excluding(receipt, "receipt_hash")
    schema = read_json(RECEIPT_SCHEMA_PATH)
    BASE.Draft202012Validator.check_schema(schema)
    errors = list(BASE.Draft202012Validator(schema).iter_errors(receipt))
    if errors:
        raise SystemExit(f"invalid J02 ArtifactReceipt: {errors[0].message}")
    return receipt


def report_document(
    documents: dict[str, dict[str, Any]],
    *,
    rah_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    regression = documents["full-regression-impact.json"]
    dependency = documents["dependency-status.json"]
    evidence_names = [
        *OUTPUT_NAMES,
        "j02-verification.artifact-receipt.json",
        "targeted-python-suite.junit.xml",
        "targeted-node-suite.junit.xml",
        "j01-regression-node-suite.junit.xml",
        "full-python-suite.junit.xml",
        "full-node-suite.junit.xml",
        "commands.jsonl",
        "review.md",
        "build_j02_0004_evidence.py",
        "j02_0004_rah_seal.py",
    ]
    if (ATTEMPT / "rah-core-integrity.json").is_file():
        evidence_names.append("rah-core-integrity.json")
    artifacts = [
        {
            "path": (ATTEMPT / name).relative_to(ROOT).as_posix(),
            "byte_size": (ATTEMPT / name).stat().st_size,
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in evidence_names
    ]
    report: dict[str, Any] = {
        "work_package_id": WORK_PACKAGE_ID,
        "attempt_id": ATTEMPT_ID,
        "title": "Progressive references and context budgets after current MASTER_SPEC authority rebinding",
        "status": "PASS",
        "implementation_status": "PASS",
        "package_status": "PASS",
        "contract_status": "CONFORMANT",
        "completion_ready": False,
        "changed_files": source_inventory(),
        "dependencies": dependency["dependencies"],
        "authority": dependency["authority"],
        "inventory": {
            "inventory_id": documents["inventory-authority-verification.json"]["inventory_id"],
            "inventory_version": documents["inventory-authority-verification.json"]["inventory_version"],
            "inventory_hash": documents["inventory-authority-verification.json"]["inventory_hash"],
            "master_spec_hash": CURRENT_MASTER_HASH,
            "master_spec_binding_count": 17,
            "skill_count": 29,
            "reference_count": 17,
            "metadata_utf8_bytes": 4767,
            "metadata_o200k_base_tokens": 1112,
            "maximum_closure_count": 11,
            "maximum_transitive_depth": 5,
        },
        "required_checks": {
            "authority_rebinding": {"status": "PASS", "bindings": "17/17"},
            "context_budget_test": {"status": "PASS", "passed": 20, "failed": 0},
            "reference_reachability_test": {"status": "PASS", "passed": 25, "failed": 0},
            "skill_routing_eval": {"status": "PASS", "passed": 19, "failed": 0},
            "inventory_hash_verification": {"status": "PASS"},
            "full_python_suite": {
                "status": "EXPECTED_B04_0009_PROJECTION_DEBT",
                "passed": 1056, "failed": 17, "skipped": 0,
                "j02_causal_failures": 0,
            },
            "full_node_suite": {
                "status": "AUTHORIZED_NEXT_ATTEMPT_S04_0004",
                "passed": 818, "failed": 1, "skipped": 0,
                "j02_causal_failures": 0, "debt_id": "S04-TM004",
            },
            "write_scope_audit": {"status": "PASS", "violations": 0},
            "independent_review": {
                "status": "PASS_WITH_PRIMARY_SESSION_SEPARATE_REVIEW",
                "actor_independence": False,
                "blocking_j02_finding_count": 0,
            },
        },
        "verification": {
            "budget_boundary_cases": "12/12",
            "selection_cases": "35/35",
            "adversarial_reachability_cases": "16/16",
            "loader_determinism": "100/100",
            "targeted_python": "20/20",
            "targeted_node": "25/25",
            "j01_node_regression": "19/19",
            "full_python": "1056 passed; exact 17 B04-0009 projection debts",
            "full_node": "818 passed; exact S04-TM004 next-attempt debt",
            "new_skip_or_xfail_count": 0,
        },
        "regression": {
            "python_regression_status": "EXPECTED_B04_0009_PROJECTION_DEBT",
            "node_regression_status": "AUTHORIZED_NEXT_ATTEMPT_S04_0004",
            "j02_causal_failure_count": regression["j02_causal_failure_count"],
            "repository_fully_green": False,
        },
        "review": {
            "status": "PASS_WITH_PRIMARY_SESSION_SEPARATE_ADVERSARIAL_IMPLEMENTATION_REVIEW",
            "mode": "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_IMPLEMENTATION_REVIEW",
            "actor_independence": False,
            "blocking_j02_finding_count": 0,
            "subagents_used": False,
            "artifact": "artifacts/work_packages/J02/attempts/0004/review.md",
            "artifact_sha256": sha256_id(ATTEMPT / "review.md"),
        },
        "history_and_worktree": documents["write-scope-verification.json"]["preservation"],
        "bounded_downstream_debt": documents["preexisting-debt-reconciliation.json"],
        "dependency_effect": dependency["next_state"],
        "evidence_artifacts": artifacts,
        "artifact_receipt": {
            "path": "artifacts/work_packages/J02/attempts/0004/j02-verification.artifact-receipt.json",
            "receipt_id": "AR-J02-0004-INVENTORY-AUTHORITY-VERIFICATION",
        },
        "not_claimed": [
            "S04-0004 PASS", "C01-0009 PASS", "B04-0009 PASS",
            "repository-wide green status", "release or production readiness",
            "actor-independent certification", "completion_ready=true",
        ],
        "global_status": {
            "implementation_gate": "fail",
            "completion_ready": False,
            "repository_fully_green": False,
            "next_attempt": "S04-0004",
        },
    }
    if rah_state is not None:
        report["rah_state"] = rah_state
    return report


def live_documents() -> dict[str, dict[str, Any]]:
    return evidence_documents()


def build() -> dict[str, Any]:
    ATTEMPT.mkdir(parents=True, exist_ok=True)
    documents = live_documents()
    for name, document in documents.items():
        write_json(ATTEMPT / name, document)
    (ATTEMPT / "commands.jsonl").write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in command_records(documents)
        ),
        encoding="utf-8",
        newline="\n",
    )
    (ATTEMPT / "review.md").write_text(
        review_text(documents), encoding="utf-8", newline="\n"
    )
    write_json(
        ATTEMPT / "j02-verification.artifact-receipt.json",
        make_receipt(ATTEMPT / "inventory-authority-verification.json"),
    )
    write_json(ATTEMPT / "report.json", report_document(documents))
    return verify()


def bind_rah_state(
    *, core_generation: str, core_evidence_id: str, final_closeout_evidence_id: str
) -> dict[str, Any]:
    documents = live_documents()
    integrity = read_json(ATTEMPT / "rah-core-integrity.json")
    rah_state = {
        "status": "active",
        "implementation_gate": "fail",
        "completion_ready": False,
        "core_generation": core_generation,
        "core_evidence_id": core_evidence_id,
        "final_closeout_evidence_id": final_closeout_evidence_id,
        "retained_generation_count": integrity["retained_generation_count"],
        "generation_file_hashes_verified": integrity[
            "generation_file_hashes_verified"
        ],
        "flat_snapshot_stamps_verified": integrity["flat_snapshot_stamps_verified"],
        "flat_snapshot_content_matches": integrity["flat_snapshot_content_matches"],
    }
    write_json(ATTEMPT / "report.json", report_document(documents, rah_state=rah_state))
    PACKAGE_ROOT.mkdir(parents=True, exist_ok=True)
    for name in ("report.json", "commands.jsonl", "review.md"):
        shutil.copyfile(ATTEMPT / name, PACKAGE_ROOT / name)
    return rah_state


def verify() -> dict[str, Any]:
    documents = live_documents()
    report = read_json(ATTEMPT / "report.json")
    rah_state = report.get("rah_state")
    if rah_state is not None:
        if not isinstance(rah_state, dict):
            raise SystemExit("J02-0004 RAH binding is not an object")
        if re.fullmatch(
            r"\d{6}-[0-9a-f]{8}", str(rah_state.get("core_generation"))
        ) is None:
            raise SystemExit("J02-0004 core generation binding is malformed")
        for key in ("core_evidence_id", "final_closeout_evidence_id"):
            if re.fullmatch(r"E\d{4,}", str(rah_state.get(key))) is None:
                raise SystemExit(f"J02-0004 {key} binding is malformed")
    for name, expected in documents.items():
        path = ATTEMPT / name
        if not path.is_file() or path.read_text(encoding="utf-8") != render(expected):
            raise SystemExit(f"stored J02-0004 evidence differs from live inputs: {name}")
    expected_review = review_text(documents)
    if (ATTEMPT / "review.md").read_text(encoding="utf-8") != expected_review:
        raise SystemExit("stored J02-0004 review differs from current evidence")
    expected_commands = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
        for row in command_records(documents)
    )
    if (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8") != expected_commands:
        raise SystemExit("stored J02-0004 commands differ from deterministic records")
    for line in expected_commands.splitlines():
        json.loads(line)
    expected_receipt = make_receipt(ATTEMPT / "inventory-authority-verification.json")
    if (ATTEMPT / "j02-verification.artifact-receipt.json").read_text(
        encoding="utf-8"
    ) != render(expected_receipt):
        raise SystemExit("stored J02-0004 ArtifactReceipt differs from live evidence")
    expected_report = report_document(documents, rah_state=rah_state)
    if (ATTEMPT / "report.json").read_text(encoding="utf-8") != render(expected_report):
        raise SystemExit("stored J02-0004 report differs from current evidence")
    if rah_state is not None:
        for name in ("report.json", "commands.jsonl", "review.md"):
            if (ATTEMPT / name).read_bytes() != (PACKAGE_ROOT / name).read_bytes():
                raise SystemExit(f"J02 package projection differs: {name}")
    return {
        "attempt_id": ATTEMPT_ID,
        "status": "PASS",
        "inventory_hash": documents["inventory-authority-verification.json"]["inventory_hash"],
        "master_spec_authority_bindings": "17/17",
        "targeted_python": "20/20",
        "targeted_node": "25/25",
        "j01_regression_node": "19/19",
        "full_python": "1056 passed, exact 17 B04-0009 debts",
        "full_node": "818 passed, exact S04-TM004 next-attempt debt",
        "j02_causal_failure_count": 0,
        "completion_ready": False,
        "rah_bound": rah_state is not None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("build", "verify"))
    args = parser.parse_args()
    result = build() if args.mode == "build" else verify()
    print(render(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
