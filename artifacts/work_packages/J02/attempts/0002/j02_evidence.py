#!/usr/bin/env python3
"""Build and verify byte-bound evidence for the J02-0002 FAIL result.

This verifier deliberately recomputes the J02 inventory, metadata projection,
token counts, reference graph, fixture cardinalities, repository dependency
lock, JUnit results, write-scope boundary, and RAH generation integrity.  It
does not repair either non-waivable failure and never starts J03 or J04.
"""

from __future__ import annotations

import argparse
import copy
import fnmatch
import hashlib
import importlib.metadata
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tomllib
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path
from types import ModuleType
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/J02/attempts/0002"
PACKAGE_ROOT = ROOT / "artifacts/work_packages/J02"
INVENTORY_PATH = ROOT / "plugins/epistemic-foundry/skills/skill-inventory.json"
FIXTURE_ROOT = ROOT / "tests/fixtures/j02"
COUNTER_PATH = ROOT / "tools/skill-context/count_tokens.py"
MANIFEST_PATH = ROOT / "manifests/development_manifest.yaml"

ATTEMPT_ID = "J02-0002"
WORK_PACKAGE_ID = "J02"
RECORDED_AT = "2026-07-30T03:06:41+09:00"
INVENTORY_HASH = "sha256:fe2c8b1814406af0f7cc380ddf95f2edd48f4df4745fc9fadaa9b743ab9961ac"
METADATA_HASH = "sha256:f7d347b3e64d3d079fd3deaf07a02da95a8dabd4ccf212a6710973ade33dea17"
MANIFEST_SHA256 = "de457bc4b141aef332d76f16357d4ba44daa663dd15c195d2e9575bc59a79940"
PYPROJECT_SHA256 = "29d7a25d530884a4a2dff3d8ca2d9878717a43a4dc3c2710fc5317f533a7be44"
UV_LOCK_SHA256 = "728e9d36f966b38a0f86ea5300210760b889110ba5adce5e646efa439ea2efac"
S04_TEST = "S04-TM004 traceability source bindings fail on undocumented contract drift"
S04_PATH = "manifests/development_manifest.yaml"
S04_FIXTURE_EXPECTED = "456330ae4aa950d1410d5180ad704927c5ec78a741d3c616d7a1cfd5bb0054a7"
S04_PRIOR_ACTUAL = "fb9656cce2fd4d0147571bc85726ebbbbb3f26a59ac644c5a12040007475d938"
S04_CURRENT_ACTUAL = MANIFEST_SHA256

JUNIT_HASHES = {
    "targeted-python-suite.junit.xml": "f72b8985f8a1284c20ed78f75aa24f7315e3023fd4b3043bd3eb5978b098ebf4",
    "targeted-node-suite.junit.xml": "f4eac13de7a1a4a1898994804aef7a705918db69d7c54b3001db5b0754f88f96",
    "j01-regression-node-suite.junit.xml": "36df2692ebc2e3eb92c79b0d6e99a9945d3dffe88c94f79b68c983bcc0c59e6b",
    "full-python-suite.junit.xml": "c5362aa2a2d7927889487e56faef1d8befec34445679030008aae9c853435ab2",
    "full-node-suite.junit.xml": "6b6704504f244e598298944e9357b54361a4e796d5b37f37a53095d5c14602c6",
}

J02_0001_HASHES = {
    "report.json": "6b0f4f37acbe1014afcf17ef5449fa4ed799e7ca0e7ea7523c014a3a44607688",
    "dependency-status.json": "20f5799699aa64091f8e3c971bb47e38a82d5035b949e109ad4939e0810c0783",
    "shared-contract-gap-verification.json": "e3fe3559a1f4ea61ba264b3534c6aa5b2778cb3e49fb27aaecf34974d95ec88a",
    "commands.jsonl": "2cf0c4e502f459eae2d901e3a361fa22885b2be35c51cd7edfa9051d2e4c5a3d",
    "review.md": "e799901e691903e00758794d6b45d0397f3c576df943f77ed4ca5dfab3743be0",
}

NODE_TOTAL_PATTERNS = {
    name: re.compile(rb"<!-- " + name.encode("ascii") + rb" ([0-9]+) -->")
    for name in ("tests", "pass", "fail", "cancelled", "skipped", "todo")
}

PRE_CORE_JSON_ARTIFACTS = (
    "metadata-budget-verification.json",
    "tokenizer-verification.json",
    "reference-inventory-verification.json",
    "reference-selection-verification.json",
    "reference-reachability-verification.json",
    "full-regression-impact.json",
    "write-scope-verification.json",
    "concurrency-diagnostic.json",
    "preexisting-debt-reconciliation.json",
)

OUTPUT_ARTIFACTS = (
    "report.json",
    "commands.jsonl",
    "review.md",
    *PRE_CORE_JSON_ARTIFACTS,
    "rah-core-integrity.json",
)

BLOCKERS = (
    {
        "id": "J02-TOKENIZER-LOCK",
        "classification": "FAIL",
        "summary": "The executable repository dependency graph does not lock exact tiktoken==0.13.0.",
        "required_decision": (
            "Assign the dependency-lock owner and authorize the exact pyproject.toml "
            "and uv.lock write paths for a new attempt."
        ),
    },
    {
        "id": "J02-S04-FINGERPRINT-CHANGE",
        "classification": "FAIL",
        "summary": (
            "The sole S04-TM004 residual no longer has the previously bounded "
            "actual-hash fingerprint after the authorized J02 manifest correction."
        ),
        "required_decision": (
            "Assign S04 traceability reconciliation/update authority for the current "
            "development manifest hash without weakening the drift gate."
        ),
    },
)

sys.dont_write_bytecode = True


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_id(path: Path) -> str:
    return "sha256:" + sha256(path)


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"JSON artifact is not an object: {path}")
    return value


def write_json(name: str, value: dict[str, Any]) -> Path:
    path = ATTEMPT / name
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def load_counter() -> ModuleType:
    spec = importlib.util.spec_from_file_location("j02_evidence_count_tokens", COUNTER_PATH)
    if spec is None or spec.loader is None:
        raise SystemExit("cannot load canonical J02 token counter")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


COUNTER = load_counter()


def normalized_output(value: str) -> str:
    value = value.replace(str(ROOT), "<ROOT>")
    value = value.replace(str(ROOT).replace("\\", "/"), "<ROOT>")
    value = re.sub(r"\x1b\[[0-9;]*m", "", value)
    return value.strip()


def run_command(arguments: list[str], *, timeout: int = 120) -> dict[str, Any]:
    completed = subprocess.run(
        arguments,
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    stdout = normalized_output(completed.stdout)
    stderr = normalized_output(completed.stderr)
    recorded_arguments = list(arguments)
    if recorded_arguments and Path(recorded_arguments[0]).is_absolute():
        recorded_arguments[0] = Path(recorded_arguments[0]).name
    return {
        "command": " ".join(recorded_arguments),
        "exit_code": completed.returncode,
        "status": "PASS" if completed.returncode == 0 else "FAIL",
        "stdout": stdout,
        "stderr": stderr,
    }


def require_command_pass(result: dict[str, Any], label: str) -> None:
    if result["exit_code"] != 0:
        raise SystemExit(
            f"{label} failed ({result['exit_code']}): {result['stdout']} {result['stderr']}"
        )


def inventory_and_counter_evidence() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    inventory = read_json(INVENTORY_PATH)
    expected = read_json(FIXTURE_ROOT / "skill-inventory.expected.json")
    if inventory.get("inventory_hash") != INVENTORY_HASH:
        raise SystemExit("J02 inventory asserted hash changed")
    preimage = copy.deepcopy(inventory)
    preimage.pop("inventory_hash", None)
    computed_hash = sha256_bytes(canonical_bytes(preimage))
    if computed_hash != INVENTORY_HASH:
        raise SystemExit("J02 canonical inventory hash mismatch")
    if expected.get("inventory_hash") != computed_hash:
        raise SystemExit("J02 expected inventory fixture is stale")

    installed_version = importlib.metadata.version("tiktoken")
    if installed_version != "0.13.0":
        raise SystemExit(f"installed tokenizer changed: {installed_version}")
    encoding = COUNTER.require_tokenizer()
    if encoding.name != "o200k_base":
        raise SystemExit("tokenizer encoding changed")

    skills = inventory.get("skills")
    references = inventory.get("references")
    if not isinstance(skills, list) or len(skills) != 29:
        raise SystemExit("J02 skill inventory is not exactly 29")
    if not isinstance(references, list) or len(references) != 17:
        raise SystemExit("J02 reference inventory is not exactly 17")

    metadata = COUNTER.serialize_metadata(skills)
    metadata_bytes = metadata.encode("utf-8")
    metadata_tokens, _ = COUNTER.count_text(metadata, encoding)
    metadata_projection = {
        "sha256": sha256_bytes(metadata_bytes),
        "byte_count": len(metadata_bytes),
        "token_count": metadata_tokens,
    }
    if metadata_projection != inventory.get("metadata_projection"):
        raise SystemExit("J02 metadata projection differs from inventory seal")
    if metadata_projection != expected.get("metadata_projection"):
        raise SystemExit("J02 metadata projection differs from expected fixture")
    if metadata_projection != {
        "sha256": METADATA_HASH,
        "byte_count": 4767,
        "token_count": 1112,
    }:
        raise SystemExit("J02 metadata projection changed")
    COUNTER.assert_metadata_budget(4767, 1112, 29)

    skill_rows: list[dict[str, Any]] = []
    for entry in skills:
        path = ROOT / "plugins/epistemic-foundry" / str(entry["path"])
        data, text = COUNTER.read_canonical_text(path)
        token_count, _ = COUNTER.count_text(text, encoding)
        actual = {
            "skill_id": entry["skill_id"],
            "path": path.relative_to(ROOT).as_posix(),
            "sha256": sha256_bytes(data),
            "byte_count": len(data),
            "token_count": token_count,
        }
        sealed = {
            "sha256": entry.get("sha256"),
            "byte_count": entry.get("byte_count"),
            "token_count": entry.get("token_count"),
        }
        if {key: actual[key] for key in sealed} != sealed:
            raise SystemExit(f"skill content seal changed: {entry.get('skill_id')}")
        if len(data) > 4096 or token_count > 1024:
            raise SystemExit(f"skill budget exceeded: {entry.get('skill_id')}")
        skill_rows.append(actual)

    reference_rows: list[dict[str, Any]] = []
    for entry in references:
        path = ROOT / "plugins/epistemic-foundry" / str(entry["path"])
        data, text = COUNTER.read_canonical_text(path)
        token_count, _ = COUNTER.count_text(text, encoding)
        actual = {
            "reference_id": entry["reference_id"],
            "path": path.relative_to(ROOT).as_posix(),
            "sha256": sha256_bytes(data),
            "byte_count": len(data),
            "token_count": token_count,
        }
        sealed = {
            "sha256": entry.get("sha256"),
            "byte_count": entry.get("byte_count"),
            "token_count": entry.get("token_count"),
        }
        if {key: actual[key] for key in sealed} != sealed:
            raise SystemExit(f"reference content seal changed: {entry.get('reference_id')}")
        if len(data) > 4096 or token_count > 1024:
            raise SystemExit(f"reference budget exceeded: {entry.get('reference_id')}")
        reference_rows.append(actual)

    tokenizer_vectors = read_json(FIXTURE_ROOT / "tokenizer-vectors.json")
    vectors = tokenizer_vectors.get("vectors")
    if not isinstance(vectors, list) or len(vectors) != 7:
        raise SystemExit("J02 tokenizer vector inventory changed")
    vector_rows: list[dict[str, Any]] = []
    for vector in vectors:
        text = str(vector["text"])
        if vector.get("normalize_nfc"):
            text = unicodedata.normalize("NFC", text)
        count, token_ids = COUNTER.count_text(text, encoding)
        if text != vector.get("encoded_text") or token_ids != vector.get("token_ids"):
            raise SystemExit(f"tokenizer vector mismatch: {vector.get('id')}")
        vector_rows.append({"id": vector["id"], "token_count": count, "status": "PASS"})

    boundary_fixture = read_json(FIXTURE_ROOT / "context-budget-cases.json")
    cases = boundary_fixture.get("cases")
    if not isinstance(cases, list) or len(cases) != 12:
        raise SystemExit("J02 boundary fixture is not exactly 12 cases")
    boundary_rows: list[dict[str, Any]] = []
    for case in cases:
        observed = "PASS"
        try:
            operation = case["operation"]
            if operation == "metadata":
                COUNTER.assert_metadata_budget(**case["input"])
            elif operation == "description":
                COUNTER.assert_description_budget("x" * int(case["input"]["byte_count"]))
            elif operation == "activation":
                COUNTER.assert_activation_budget(case["input"])
            else:
                raise SystemExit(f"unknown J02 boundary operation: {operation}")
        except COUNTER.TokenizerContractError as error:
            observed = error.code
        if observed != case.get("expected"):
            raise SystemExit(f"J02 boundary result mismatch: {case.get('case_id')}")
        boundary_rows.append(
            {"case_id": case["case_id"], "expected": case["expected"], "observed": observed}
        )

    pyproject_hash = sha256(ROOT / "pyproject.toml")
    uv_hash = sha256(ROOT / "uv.lock")
    if pyproject_hash != PYPROJECT_SHA256 or uv_hash != UV_LOCK_SHA256:
        raise SystemExit("repository dependency files changed after J02 regression capture")
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    uv_lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    declared: list[str] = []
    project = pyproject.get("project", {})
    if isinstance(project, dict):
        declared.extend(v for v in project.get("dependencies", []) if isinstance(v, str))
        optional = project.get("optional-dependencies", {})
        if isinstance(optional, dict):
            for values in optional.values():
                if isinstance(values, list):
                    declared.extend(v for v in values if isinstance(v, str))
    exact_pyproject_pin = "tiktoken==0.13.0" in {value.replace(" ", "") for value in declared}
    packages = uv_lock.get("package", [])
    tokenizer_packages = [
        item for item in packages if isinstance(item, dict) and item.get("name") == "tiktoken"
    ] if isinstance(packages, list) else []
    roots = [
        item for item in packages
        if isinstance(item, dict) and item.get("name") == "epistemic-foundry"
    ] if isinstance(packages, list) else []
    root_has_tokenizer = False
    if len(roots) == 1:
        root_dependencies = roots[0].get("dependencies", [])
        root_has_tokenizer = any(
            isinstance(item, dict) and item.get("name") == "tiktoken"
            for item in root_dependencies
        )
    lock_error: dict[str, str] | None = None
    try:
        COUNTER.verify_repository_tokenizer_lock(ROOT)
    except COUNTER.TokenizerContractError as error:
        lock_error = {"code": error.code, "message": str(error)}
    if lock_error != {
        "code": "TOKENIZER_CONTRACT_UNAVAILABLE",
        "message": "pyproject.toml does not declare exact tiktoken==0.13.0",
    }:
        raise SystemExit(f"repository tokenizer-lock failure changed: {lock_error}")
    if exact_pyproject_pin or tokenizer_packages or root_has_tokenizer:
        raise SystemExit("repository tokenizer lock is no longer the sealed J02 failure")

    metadata_evidence = {
        "attempt_id": ATTEMPT_ID,
        "status": "PASS",
        "inventory_hash": computed_hash,
        "skill_count": len(skills),
        "parent_skill_count": 1,
        "child_skill_count": 28,
        "metadata_projection": metadata_projection,
        "limits": {
            "max_utf8_bytes": 6400,
            "max_o200k_base_tokens": 1600,
        },
        "margin": {
            "utf8_bytes": 6400 - len(metadata_bytes),
            "o200k_base_tokens": 1600 - metadata_tokens,
        },
        "boundary_cases": boundary_rows,
        "boundary_exact_pass_count": len(boundary_rows),
    }
    tokenizer_evidence = {
        "attempt_id": ATTEMPT_ID,
        "status": "FAIL",
        "installed_runtime": {
            "package": "tiktoken",
            "version": installed_version,
            "encoding": encoding.name,
            "status": "PASS",
        },
        "repository_lock": {
            "status": "FAIL",
            "error": lock_error,
            "pyproject_path": "pyproject.toml",
            "pyproject_sha256": "sha256:" + pyproject_hash,
            "exact_pyproject_requirement_present": exact_pyproject_pin,
            "uv_lock_path": "uv.lock",
            "uv_lock_sha256": "sha256:" + uv_hash,
            "tiktoken_package_count": len(tokenizer_packages),
            "root_dependency_closure_contains_tiktoken": root_has_tokenizer,
        },
        "vectors": vector_rows,
        "vector_exact_pass_count": len(vector_rows),
        "non_waivable": True,
        "owner_and_write_paths_defined_for_repair": False,
    }
    inventory_evidence = {
        "attempt_id": ATTEMPT_ID,
        "status": "PASS",
        "inventory_id": inventory.get("inventory_id"),
        "inventory_version": inventory.get("inventory_version"),
        "inventory_hash": computed_hash,
        "skill_count": len(skill_rows),
        "reference_count": len(reference_rows),
        "skill_files": skill_rows,
        "reference_files": reference_rows,
        "content_hash_mismatch_count": 0,
        "byte_or_token_budget_violation_count": 0,
    }
    return metadata_evidence, tokenizer_evidence, inventory_evidence


def reference_evidence() -> tuple[dict[str, Any], dict[str, Any]]:
    inventory = read_json(INVENTORY_PATH)
    skills = {str(row["skill_id"]): row for row in inventory["skills"]}
    references = {str(row["reference_id"]): row for row in inventory["references"]}
    if len(skills) != 29 or len(references) != 17:
        raise SystemExit("J02 graph source inventory changed")

    visiting: set[str] = set()
    visited: set[str] = set()
    depths: dict[str, int] = {}

    def visit(reference_id: str) -> int:
        if reference_id not in references:
            raise SystemExit(f"missing J02 reference target: {reference_id}")
        if reference_id in visiting:
            raise SystemExit(f"J02 reference cycle: {reference_id}")
        if reference_id in visited:
            return depths[reference_id]
        visiting.add(reference_id)
        dependencies = references[reference_id].get("depends_on", [])
        if not isinstance(dependencies, list):
            raise SystemExit(f"invalid dependency list: {reference_id}")
        # Canonical transitive depth counts dependency edges; a leaf is depth 0.
        depth = 1 + max((visit(str(item)) for item in dependencies), default=-1)
        visiting.remove(reference_id)
        visited.add(reference_id)
        depths[reference_id] = depth
        return depth

    for reference_id in sorted(references):
        visit(reference_id)

    def closure(reference_ids: list[str]) -> set[str]:
        result: set[str] = set()

        def add(reference_id: str) -> None:
            if reference_id in result:
                return
            if reference_id not in references:
                raise SystemExit(f"missing closure target: {reference_id}")
            for dependency in references[reference_id].get("depends_on", []):
                add(str(dependency))
            result.add(reference_id)

        for reference_id in reference_ids:
            add(reference_id)
        return result

    parent = skills.get("foundry")
    if not isinstance(parent, dict):
        raise SystemExit("J02 parent skill is missing")
    child_ids = set(str(value) for value in parent.get("child_skills", []))
    expected_children = set(skills) - {"foundry"}
    if child_ids != expected_children or len(child_ids) != 28:
        raise SystemExit("J02 parent-to-child reachability changed")

    directly_declared: set[str] = set()
    maximum_closure_count = 0
    maximum_transitive_depth = 0
    default_rows: dict[str, dict[str, int]] = {}
    for skill_id, skill in skills.items():
        direct = [str(value) for value in skill.get("direct_references", [])]
        directly_declared.update(direct)
        for conditional in skill.get("conditional_references", []):
            if isinstance(conditional, dict) and isinstance(conditional.get("reference_id"), str):
                directly_declared.add(conditional["reference_id"])
        selected = closure(direct)
        maximum_closure_count = max(maximum_closure_count, len(selected))
        selected_depth = max((depths[item] for item in selected), default=0)
        maximum_transitive_depth = max(maximum_transitive_depth, selected_depth)
        default_rows[skill_id] = {
            "reference_count": len(selected),
            "transitive_depth": selected_depth,
            "total_reference_bytes": sum(int(references[item]["byte_count"]) for item in selected),
            "total_reference_tokens": sum(int(references[item]["token_count"]) for item in selected),
        }
        COUNTER.assert_activation_budget(
            {
                "skill_bytes": int(skill["byte_count"]),
                "skill_tokens": int(skill["token_count"]),
                "reference_count": len(selected),
                "reference_depth": selected_depth,
                "reference_bytes": default_rows[skill_id]["total_reference_bytes"],
                "reference_tokens": default_rows[skill_id]["total_reference_tokens"],
            }
        )
    if directly_declared != set(references):
        raise SystemExit("J02 graph has an orphan reference")
    if maximum_closure_count != 11 or maximum_transitive_depth != 5:
        raise SystemExit("J02 maximum closure/depth changed")

    selection = read_json(FIXTURE_ROOT / "reference-selection-cases.json")
    cases = selection.get("cases")
    if (
        selection.get("inventory_hash") != INVENTORY_HASH
        or not isinstance(cases, list)
        or len(cases) != 35
    ):
        raise SystemExit("J02 selection fixture identity/cardinality changed")
    categories: dict[str, int] = {}
    for case in cases:
        category = str(case.get("category"))
        categories[category] = categories.get(category, 0) + 1
        if case.get("skill_id") not in skills:
            raise SystemExit(f"selection fixture names unknown skill: {case.get('case_id')}")
        if category == "DEFAULT":
            expected = default_rows[str(case["skill_id"])]
            for field in ("transitive_depth", "total_reference_bytes", "total_reference_tokens"):
                if int(case[field]) != expected[field]:
                    raise SystemExit(f"selection fixture drift: {case.get('case_id')} {field}")
    if categories != {
        "DEFAULT": 29,
        "CONDITIONAL_POSITIVE": 3,
        "CONDITIONAL_NEGATIVE": 3,
    }:
        raise SystemExit(f"J02 selection category counts changed: {categories}")

    reachability = read_json(FIXTURE_ROOT / "reference-reachability-cases.json")
    graph = reachability.get("expected_graph")
    adversarial = reachability.get("adversarial_cases")
    expected_graph = {
        "parent_count": 1,
        "child_count": 28,
        "reachable_child_count": 28,
        "unreachable_child_ids": [],
        "orphan_skill_ids": [],
        "reference_count": 17,
        "reachable_reference_count": 17,
        "orphan_reference_ids": [],
        "maximum_closure_count": 11,
        "maximum_transitive_depth": 5,
        "graph_integrity_errors": [],
    }
    if graph != expected_graph:
        raise SystemExit(f"J02 expected graph fixture changed: {graph}")
    if not isinstance(adversarial, list) or len(adversarial) != 16:
        raise SystemExit("J02 adversarial reachability fixture is not exactly 16 cases")
    if len({str(case.get("case_id")) for case in adversarial}) != 16:
        raise SystemExit("J02 adversarial case IDs are not unique")

    targeted_node = node_junit(
        "targeted-node-suite.junit.xml",
        expected_totals={
            "tests": 25,
            "pass": 25,
            "fail": 0,
            "cancelled": 0,
            "skipped": 0,
            "todo": 0,
        },
        expected_xml_cases=24,
    )
    selection_evidence = {
        "attempt_id": ATTEMPT_ID,
        "status": "PASS",
        "inventory_hash": INVENTORY_HASH,
        "case_count": len(cases),
        "category_counts": categories,
        "default_activation_budget_pass_count": 29,
        "selection_exact_pass_count": 35,
        "maximum_default_closure_count": maximum_closure_count,
        "maximum_default_transitive_depth": maximum_transitive_depth,
        "targeted_node_junit": targeted_node,
    }
    reachability_evidence = {
        "attempt_id": ATTEMPT_ID,
        "status": "PASS",
        "graph": expected_graph,
        "adversarial_case_count": len(adversarial),
        "adversarial_exact_fail_closed_count": 16,
        "adversarial_cases": [
            {
                "case_id": case["case_id"],
                "expected_error": case["expected_error"],
                "status": "PASS",
            }
            for case in adversarial
        ],
        "loader_determinism_repeat_count": 100,
        "loader_determinism_mismatch_count": 0,
        "targeted_node_junit": targeted_node,
    }
    return selection_evidence, reachability_evidence


def python_junit(name: str, expected: dict[str, int]) -> dict[str, Any]:
    path = ATTEMPT / name
    if sha256(path) != JUNIT_HASHES[name]:
        raise SystemExit(f"J02 JUnit hash changed: {name}")
    root = ET.fromstring(path.read_bytes())
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    totals = {
        key: sum(int(suite.get(key, "0")) for suite in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }
    if totals != expected:
        raise SystemExit(f"J02 Python JUnit totals changed: {name}: {totals}")
    cases = root.findall(".//testcase")
    failures = []
    for case in cases:
        failure = case.find("failure")
        if failure is None:
            continue
        text = "\n".join(
            value
            for value in (
                str(failure.get("message") or ""),
                str(failure.text or ""),
            )
            if value
        )
        failures.append(
            {
                "node_id": f"{case.get('classname')}::{case.get('name')}",
                "type": str(failure.get("type") or "pytest_failure"),
                "message": text,
            }
        )
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": sha256_id(path),
        "totals": {
            **totals,
            "passed": totals["tests"] - totals["failures"] - totals["errors"] - totals["skipped"],
        },
        "xml_testcase_count": len(cases),
        "failures": failures,
    }


def node_footer(content: bytes) -> dict[str, int]:
    totals: dict[str, int] = {}
    for label, pattern in NODE_TOTAL_PATTERNS.items():
        matches = pattern.findall(content)
        if len(matches) != 1:
            raise SystemExit(f"missing or ambiguous Node footer {label}")
        totals[label] = int(matches[0])
    return totals


def relative_test_file(value: str) -> str:
    normalized = value.replace("\\", "/")
    for marker in ("tests/", "packages/", "web/"):
        index = normalized.find(marker)
        if index >= 0:
            return normalized[index:]
    return normalized


def node_junit(
    name: str,
    *,
    expected_totals: dict[str, int],
    expected_xml_cases: int,
) -> dict[str, Any]:
    path = ATTEMPT / name
    if sha256(path) != JUNIT_HASHES[name]:
        raise SystemExit(f"J02 JUnit hash changed: {name}")
    content = path.read_bytes()
    root = ET.fromstring(content)
    totals = node_footer(content)
    if totals != expected_totals:
        raise SystemExit(f"J02 Node JUnit footer changed: {name}: {totals}")
    cases = root.findall(".//testcase")
    if len(cases) != expected_xml_cases:
        raise SystemExit(f"J02 Node XML testcase inventory changed: {name}: {len(cases)}")
    failures: list[dict[str, str]] = []
    for case in cases:
        failure = case.find("failure")
        if failure is None:
            continue
        message = "\n".join(
            value
            for value in (
                str(case.get("failure") or ""),
                str(failure.get("message") or ""),
                str(failure.text or ""),
            )
            if value
        )
        failures.append(
            {
                "node_id": f"test::{case.get('name')}",
                "test_file": relative_test_file(str(case.get("file") or "")),
                "type": str(failure.get("type") or "testCodeFailure"),
                "message": message,
            }
        )
    if len(failures) != totals["fail"]:
        raise SystemExit(f"J02 Node failure inventory differs from footer: {name}")
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": sha256_id(path),
        "totals": totals,
        "xml_testcase_count": len(cases),
        "xml_footer_testcase_delta": totals["tests"] - len(cases),
        "semantic_totals_authority": "node_junit_footer_comments",
        "failures": failures,
    }


def regression_evidence() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    targeted_python = python_junit(
        "targeted-python-suite.junit.xml",
        {"tests": 17, "failures": 1, "errors": 0, "skipped": 0},
    )
    full_python = python_junit(
        "full-python-suite.junit.xml",
        {"tests": 964, "failures": 1, "errors": 0, "skipped": 0},
    )
    lock_node = (
        "tests.test_j02_context_budget::"
        "test_repository_dependency_lock_closes_exact_tiktoken_pin"
    )
    for result in (targeted_python, full_python):
        failures = result["failures"]
        if (
            len(failures) != 1
            or failures[0]["node_id"] != lock_node
            or "TOKENIZER_CONTRACT_UNAVAILABLE" not in failures[0]["message"]
            or "tiktoken==0.13.0" not in failures[0]["message"]
        ):
            raise SystemExit("J02 Python failure is not the exact tokenizer-lock gate")

    targeted_node = node_junit(
        "targeted-node-suite.junit.xml",
        expected_totals={
            "tests": 25,
            "pass": 25,
            "fail": 0,
            "cancelled": 0,
            "skipped": 0,
            "todo": 0,
        },
        expected_xml_cases=24,
    )
    j01_node = node_junit(
        "j01-regression-node-suite.junit.xml",
        expected_totals={
            "tests": 19,
            "pass": 19,
            "fail": 0,
            "cancelled": 0,
            "skipped": 0,
            "todo": 0,
        },
        expected_xml_cases=19,
    )
    full_node = node_junit(
        "full-node-suite.junit.xml",
        expected_totals={
            "tests": 437,
            "pass": 436,
            "fail": 1,
            "cancelled": 0,
            "skipped": 0,
            "todo": 0,
        },
        expected_xml_cases=434,
    )
    if len(full_node["failures"]) != 1:
        raise SystemExit("J02 full Node failure inventory changed")
    node_failure = full_node["failures"][0]
    if (
        node_failure["node_id"] != f"test::{S04_TEST}"
        or not node_failure["test_file"].endswith(
            "tests/security/s04-threat-model-traceability.test.mjs"
        )
        or S04_FIXTURE_EXPECTED not in node_failure["message"]
        or S04_CURRENT_ACTUAL not in node_failure["message"]
    ):
        raise SystemExit("J02 full Node failure is not the current S04-TM004 result")
    if S04_PRIOR_ACTUAL in node_failure["message"]:
        raise SystemExit("J02 full Node failure still claims the prior bounded fingerprint")

    full_regression = {
        "attempt_id": ATTEMPT_ID,
        "status": "FAIL",
        "targeted_python": targeted_python,
        "targeted_node": targeted_node,
        "j01_node_regression": j01_node,
        "full_python": full_python,
        "full_node": full_node,
        "acceptance_failure_count": 2,
        "new_skip_or_xfail_count": 0,
        "blocking_failures": [
            {
                "id": "J02-TOKENIZER-LOCK",
                "owner": "UNASSIGNED_PRODUCT_DECISION_REQUIRED",
                "non_waivable": True,
            },
            {
                "id": "J02-S04-FINGERPRINT-CHANGE",
                "owner": "S04_TRACEABILITY_AUTHORITY_REQUIRED",
                "non_waivable": True,
            },
        ],
        "implementation_checks": {
            "inventory_metadata_reference_runtime": "VERIFIED",
            "targeted_node": "25/25",
            "j01_node_regression": "19/19",
            "loader_determinism": "100/100",
        },
    }
    concurrency = {
        "attempt_id": ATTEMPT_ID,
        "status": "DIAGNOSTIC_RECONCILED_NOT_A_PRODUCT_FAILURE",
        "initial_parallel_full_node_observation": {
            "tests": 437,
            "passed": 435,
            "failed": 2,
            "failures": [
                "S04-TM004",
                "orphan_receipt_test: concurrent identical publishers converge",
            ],
            "transient_error_code": "ARTIFACT_MUTATION_LOCK_FAILED",
            "provenance": "PRIMARY_SESSION_COMMAND_OBSERVATION_NO_PRESERVED_JUNIT",
            "artifact_claimed": False,
        },
        "isolated_reconciliation": {
            "test": "orphan_receipt_test: concurrent identical publishers converge",
            "runs": 5,
            "passed": 5,
            "failed": 0,
            "provenance": "PRIMARY_SESSION_ISOLATED_COMMAND_OBSERVATION",
        },
        "final_serial_full_node": {
            "junit": full_node["path"],
            "junit_sha256": full_node["sha256"],
            "tests": 437,
            "passed": 436,
            "failed": 1,
            "concurrent_identical_publishers_status": "PASS",
            "sole_failure": "S04-TM004",
        },
        "disposition": (
            "The lock handoff observation was transient and is not counted as a J02 "
            "product failure; the serial full-suite artifact is authoritative."
        ),
    }
    debt = {
        "attempt_id": ATTEMPT_ID,
        "status": "FAIL",
        "debt_id": "S04-TM004",
        "owner": "S04",
        "test_name": S04_TEST,
        "test_file": "tests/security/s04-threat-model-traceability.test.mjs",
        "source_path": S04_PATH,
        "fixture_expected_sha256": S04_FIXTURE_EXPECTED,
        "prior_bounded_actual_sha256": S04_PRIOR_ACTUAL,
        "current_actual_sha256": S04_CURRENT_ACTUAL,
        "current_manifest_sha256_verified": sha256(MANIFEST_PATH),
        "fingerprint_changed": True,
        "same_fingerprint_allowance_satisfied": False,
        "skip_or_xfail_used": False,
        "cause": "AUTHORIZED_J02_DEVELOPMENT_MANIFEST_CORRECTION",
        "required_authority": (
            "S04 traceability fingerprint reconciliation/update authority for the "
            "current manifest revision"
        ),
    }
    if debt["current_manifest_sha256_verified"] != S04_CURRENT_ACTUAL:
        raise SystemExit("current manifest hash differs from S04 reconciliation evidence")
    return full_regression, concurrency, debt


def scope_allows(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def write_scope_evidence() -> dict[str, Any]:
    manifest = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
    packages = manifest.get("work_packages") if isinstance(manifest, dict) else None
    if not isinstance(packages, list):
        packages = manifest if isinstance(manifest, list) else None
    if not isinstance(packages, list):
        raise SystemExit("cannot locate development manifest work packages")
    rows = [row for row in packages if isinstance(row, dict) and row.get("id") == "J02"]
    if len(rows) != 1 or not isinstance(rows[0].get("write_scope"), list):
        raise SystemExit("development manifest has no unique J02 write scope")
    patterns = [str(value) for value in rows[0]["write_scope"]]

    product_paths: list[str] = [
        INVENTORY_PATH.relative_to(ROOT).as_posix(),
        COUNTER_PATH.relative_to(ROOT).as_posix(),
        "docs/skill_context_contract.md",
        "tests/test_j02_context_budget.py",
        "tests/node/j02-reference-reachability.test.mjs",
        "tests/node/j02-skill-context-loader.test.mjs",
    ]
    product_paths.extend(
        path.relative_to(ROOT).as_posix()
        for path in sorted((ROOT / "packages/plugin-host/src/skill-context").glob("*"))
        if path.is_file()
    )
    product_paths.extend(
        path.relative_to(ROOT).as_posix()
        for path in sorted((ROOT / "plugins/epistemic-foundry/skills").glob("*/SKILL.md"))
    )
    product_paths.extend(
        path.relative_to(ROOT).as_posix()
        for path in sorted((ROOT / "plugins/epistemic-foundry/skills").glob("*/agents/openai.yaml"))
    )
    product_paths.extend(
        path.relative_to(ROOT).as_posix()
        for path in sorted((ROOT / "plugins/epistemic-foundry/skills/foundry/references").rglob("*.md"))
    )
    product_paths.extend(
        path.relative_to(ROOT).as_posix()
        for path in sorted(FIXTURE_ROOT.glob("*.json"))
    )
    product_paths = sorted(set(product_paths))
    violations = [path for path in product_paths if not scope_allows(path, patterns)]
    if violations:
        raise SystemExit(f"J02 product files outside write scope: {violations}")
    if len(list((ROOT / "plugins/epistemic-foundry/skills").glob("*/SKILL.md"))) != 29:
        raise SystemExit("production SKILL.md count changed")
    if len(list((ROOT / "plugins/epistemic-foundry/skills").glob("*/agents/openai.yaml"))) != 29:
        raise SystemExit("production skill agent metadata count changed")
    if len(list((ROOT / "plugins/epistemic-foundry/skills/foundry/references").rglob("*.md"))) != 17:
        raise SystemExit("production reference file count changed")

    if sha256(MANIFEST_PATH) != MANIFEST_SHA256:
        raise SystemExit("development manifest changed after J02 regression capture")
    for name, expected in J02_0001_HASHES.items():
        actual = sha256(ROOT / "artifacts/work_packages/J02/attempts/0001" / name)
        if actual != expected:
            raise SystemExit(f"J02-0001 immutable history changed: {name}")
    if sha256(ROOT / "pyproject.toml") != PYPROJECT_SHA256:
        raise SystemExit("pyproject.toml changed during J02 evidence sealing")
    if sha256(ROOT / "uv.lock") != UV_LOCK_SHA256:
        raise SystemExit("uv.lock changed during J02 evidence sealing")

    forbidden_cache_paths = (
        ROOT / "tests/__pycache__/test_j02_context_budget.cpython-312-pytest-9.0.3.pyc",
        ROOT / "tools/skill-context/__pycache__/count_tokens.cpython-312.pyc",
    )
    if any(path.exists() for path in forbidden_cache_paths):
        raise SystemExit("J02 cache residue is present")
    if (ROOT / "tools/skill-context/__pycache__").exists():
        raise SystemExit("J02 token-counter cache directory is present")
    if (ROOT / "artifacts/work_packages/J03").exists():
        raise SystemExit("J03 was started before J02 PASS")
    if (ROOT / "artifacts/work_packages/J04").exists():
        raise SystemExit("J04 was started before J02 PASS")

    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if npm is None:
        raise SystemExit("npm command is unavailable")
    structure = run_command([npm, "run", "check:structure"])
    boundaries = run_command([npm, "run", "check:boundaries"])
    scoped_diff = run_command(
        [
            "git",
            "diff",
            "--check",
            "--",
            "plugins/epistemic-foundry/skills",
            "packages/plugin-host/src/skill-context",
            "tools/skill-context/count_tokens.py",
            "docs/skill_context_contract.md",
            "tests/fixtures/j02",
            "tests/test_j02_context_budget.py",
            "tests/node/j02-reference-reachability.test.mjs",
            "tests/node/j02-skill-context-loader.test.mjs",
            "manifests/development_manifest.yaml",
            "manifests/acceptance_matrix.yaml",
        ]
    )
    repository_diff = run_command(["git", "diff", "--check"])
    for label, result in (
        ("repository structure", structure),
        ("repository boundaries", boundaries),
        ("J02 scoped diff", scoped_diff),
        ("repository diff", repository_diff),
    ):
        require_command_pass(result, label)

    status = run_command(
        [
            "git",
            "status",
            "--short",
            "--untracked-files=all",
            "--",
            "plugins/epistemic-foundry/skills",
            "packages/plugin-host/src/skill-context",
            "tools/skill-context/count_tokens.py",
            "docs/skill_context_contract.md",
            "tests/fixtures/j02",
            "tests/test_j02_context_budget.py",
            "tests/node/j02-reference-reachability.test.mjs",
            "tests/node/j02-skill-context-loader.test.mjs",
        ]
    )
    require_command_pass(status, "J02 scoped status")
    status_lines = [line for line in status["stdout"].splitlines() if line.strip()]
    return {
        "attempt_id": ATTEMPT_ID,
        "status": "PASS",
        "manifest_sha256": "sha256:" + MANIFEST_SHA256,
        "manifest_write_scope": patterns,
        "authorized_product_file_count": len(product_paths),
        "authorized_product_files": product_paths,
        "product_write_scope_violation_count": len(violations),
        "authority_level_corrections_not_claimed_as_j02_self_expansion": [
            "manifests/development_manifest.yaml",
            "manifests/acceptance_matrix.yaml",
        ],
        "scoped_git_status": status_lines,
        "checks": {
            "npm_check_structure": {key: structure[key] for key in ("command", "exit_code", "status")},
            "npm_check_boundaries": {key: boundaries[key] for key in ("command", "exit_code", "status")},
            "scoped_git_diff_check": {key: scoped_diff[key] for key in ("command", "exit_code", "status")},
            "repository_git_diff_check": {key: repository_diff[key] for key in ("command", "exit_code", "status")},
        },
        "preservation": {
            "j02_0001_hashes": {
                name: "sha256:" + value for name, value in J02_0001_HASHES.items()
            },
            "dirty_worktree_preserved": bool(status_lines),
            "pyproject_toml_sha256": "sha256:" + PYPROJECT_SHA256,
            "uv_lock_sha256": "sha256:" + UV_LOCK_SHA256,
            "pyproject_or_uv_lock_modified_by_seal": False,
            "s04_fixture_or_test_modified_by_seal": False,
            "cache_residue_count": 0,
            "j03_started": False,
            "j04_started": False,
            "subagents_or_fleet_used": False,
            "reset_clean_stash_commit_push_performed": False,
        },
    }


def evidence_documents() -> dict[str, dict[str, Any]]:
    metadata, tokenizer, inventory = inventory_and_counter_evidence()
    selection, reachability = reference_evidence()
    regression, concurrency, debt = regression_evidence()
    write_scope = write_scope_evidence()
    return {
        "metadata-budget-verification.json": metadata,
        "tokenizer-verification.json": tokenizer,
        "reference-inventory-verification.json": inventory,
        "reference-selection-verification.json": selection,
        "reference-reachability-verification.json": reachability,
        "full-regression-impact.json": regression,
        "write-scope-verification.json": write_scope,
        "concurrency-diagnostic.json": concurrency,
        "preexisting-debt-reconciliation.json": debt,
    }


def command_rows(documents: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    regression = documents["full-regression-impact.json"]
    checks = documents["write-scope-verification.json"]["checks"]
    return [
        {
            "command_id": "C001",
            "command": "python artifacts/work_packages/J02/attempts/0002/activate_j02_0002.py",
            "exit_code": 0,
            "result": "PASS: E0081 and generation 000078-e5a8777f activated J02-0002",
        },
        {
            "command_id": "C002",
            "command": "python artifacts/work_packages/J02/attempts/0002/materialize_j02.py",
            "exit_code": 0,
            "result": "PASS: 29 production skills and 17 references materialized",
        },
        {
            "command_id": "C003",
            "command": "python artifacts/work_packages/J02/attempts/0002/generate_inventory.py",
            "exit_code": 0,
            "result": f"PASS: {INVENTORY_HASH}",
        },
        {
            "command_id": "C004",
            "command": "pytest tests/test_j02_context_budget.py --junitxml=<attempt>/targeted-python-suite.junit.xml",
            "exit_code": 1,
            "result": "FAIL: 16 passed, exact repository tokenizer-lock gate failed",
            "junit_sha256": regression["targeted_python"]["sha256"],
        },
        {
            "command_id": "C005",
            "command": "node --test --test-reporter=junit tests/node/j02-reference-reachability.test.mjs tests/node/j02-skill-context-loader.test.mjs",
            "exit_code": 0,
            "result": "PASS: Node footer 25/25; loader determinism 100/100",
            "junit_sha256": regression["targeted_node"]["sha256"],
        },
        {
            "command_id": "C006",
            "command": "node --test --test-reporter=junit <J01 routing regression files>",
            "exit_code": 0,
            "result": "PASS: Node footer 19/19",
            "junit_sha256": regression["j01_node_regression"]["sha256"],
        },
        {
            "command_id": "C007",
            "command": "pytest --junitxml=<attempt>/full-python-suite.junit.xml",
            "exit_code": 1,
            "result": "FAIL: 963 passed, exact repository tokenizer-lock gate failed",
            "junit_sha256": regression["full_python"]["sha256"],
        },
        {
            "command_id": "C008",
            "command": "node --test --test-reporter=junit <full repository Node discovery>",
            "exit_code": 1,
            "result": "FAIL: Node footer 436 passed/1 failed; S04-TM004 fingerprint changed",
            "junit_sha256": regression["full_node"]["sha256"],
        },
        {
            "command_id": "C009",
            "command": "npm run check:structure",
            "exit_code": checks["npm_check_structure"]["exit_code"],
            "result": "PASS",
        },
        {
            "command_id": "C010",
            "command": "npm run check:boundaries",
            "exit_code": checks["npm_check_boundaries"]["exit_code"],
            "result": "PASS",
        },
        {
            "command_id": "C011",
            "command": "git diff --check -- <J02 scoped paths>",
            "exit_code": checks["scoped_git_diff_check"]["exit_code"],
            "result": "PASS",
        },
        {
            "command_id": "C012",
            "command": "git diff --check",
            "exit_code": checks["repository_git_diff_check"]["exit_code"],
            "result": "PASS",
        },
        {
            "command_id": "C013",
            "command": "primary-session separate adversarial implementation review",
            "exit_code": 1,
            "result": "FAIL: two non-waivable blocking findings; actor_independence=false",
        },
    ]


def review_text() -> str:
    return """# J02-0002 separate adversarial implementation review

## Verdict

**FAIL.** The progressive-reference implementation is verified, but J02 cannot
pass because two non-waivable acceptance gates fail. This is a procedurally
separate primary-session review, not actor-independent certification:
`actor_independence=false`. Fleet and subagents were not used.

## Verified implementation

- Canonical inventory hash is
  `sha256:fe2c8b1814406af0f7cc380ddf95f2edd48f4df4745fc9fadaa9b743ab9961ac`.
- Initial metadata is exactly 4,767 UTF-8 bytes and 1,112 pinned
  `o200k_base` tokens for 29 skills.
- All 29 skill files and 17 reference files match their byte, SHA-256, and
  token seals. The reference graph is 1 parent, 28 children, 17 references,
  maximum closure 11, and maximum depth 5.
- All 12 budget boundaries, 35 selection cases, 16 adversarial reachability
  cases, and 100 deterministic loader repetitions match the fixed oracle.
- Targeted Node is 25/25 and the J01 routing regression is 19/19. Structure,
  boundary, scoped diff, repository diff, cache, history, and write-scope
  checks pass.

## Blocking findings

1. **Repository tokenizer dependency lock is absent.** The host has
   `tiktoken 0.13.0`, but `pyproject.toml` does not declare exact
   `tiktoken==0.13.0`, and `uv.lock` has neither the package nor the root
   dependency closure. Targeted Python is 16/17 and full Python is 963/964,
   with only this exact non-waivable gate failing. J02 is not authorized to
   modify either dependency file.
2. **The previously bounded S04-TM004 fingerprint changed.** The historical
   fixture expects `456330ae...`; the previously reconciled actual manifest
   hash was `fb9656cc...`; the current authorized J02 manifest revision is
   `de457bc4...`. Full Node is 436/437 with only S04-TM004 failing, but the
   contract permits that debt only while its fingerprint is identical. J02
   does not own the S04 traceability record or test.

The initial parallel Node observation also included a transient
`ARTIFACT_MUTATION_LOCK_FAILED` on `concurrent identical publishers`. That case
passed 5/5 in isolation and passes in the final serial full-suite JUnit; it is
diagnostic, not a third product failure.

## Required decision before another attempt

- Assign the exact tokenizer dependency-lock owner and authorize the
  `pyproject.toml` and `uv.lock` write paths.
- Assign S04 traceability fingerprint reconciliation/update authority for the
  current development manifest revision without weakening S04-TM004.

J03 and J04 remain unstarted. `completion_ready=false`.
"""


def write_commands(rows: list[dict[str, Any]]) -> None:
    with (ATTEMPT / "commands.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            record = {"attempt_id": ATTEMPT_ID, "recorded_at": RECORDED_AT, **row}
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def verify_commands(expected_rows: list[dict[str, Any]]) -> None:
    lines = (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8").splitlines()
    expected = [
        {"attempt_id": ATTEMPT_ID, "recorded_at": RECORDED_AT, **row}
        for row in expected_rows
    ]
    observed = [json.loads(line) for line in lines]
    if observed != expected:
        raise SystemExit("J02 commands.jsonl differs from recomputed command evidence")


def generation_names() -> list[str]:
    return sorted(
        path.name
        for path in (ROOT / ".rah/ralph/generations").iterdir()
        if path.is_dir() and re.fullmatch(r"\d{6}-[0-9a-f]{8}", path.name)
    )


def generation_integrity(expected_count: int, expected_latest_evidence: str) -> dict[str, Any]:
    automation = ROOT / ".rah/helpers/recursive-architecture-refactoring-auto/automation"
    sys.path.insert(0, str(automation))
    import state_store  # type: ignore  # noqa: PLC0415

    ralph_root = ROOT / ".rah/ralph"
    current = state_store.read_current(ralph_root)
    if current is None:
        raise SystemExit("no current RAH generation")
    generation, payloads = current
    generations = generation_names()
    if len(generations) != expected_count or generations[-1] != generation:
        raise SystemExit(f"expected {expected_count} RAH generations ending at {generation}")
    verified_hashes = 0
    for name in generations:
        directory = ralph_root / "generations" / name
        manifest = read_json(directory / "generation-manifest.json")
        files = manifest.get("files")
        if manifest.get("generation") != name or not isinstance(files, dict):
            raise SystemExit(f"invalid RAH generation manifest: {name}")
        if set(files) != set(state_store.GENERATION_FILES):
            raise SystemExit(f"RAH generation file set mismatch: {name}")
        for filename in state_store.GENERATION_FILES:
            if sha256(directory / filename) != files[filename]:
                raise SystemExit(f"RAH generation hash mismatch: {name}/{filename}")
            verified_hashes += 1
    ledger = payloads.get("evidence_ledger.json")
    entries = ledger.get("entries") if isinstance(ledger, dict) else None
    ids = [str(row.get("id")) for row in entries if isinstance(row, dict)] if isinstance(entries, list) else []
    expected_ids = [f"E{index:04d}" for index in range(1, int(expected_latest_evidence[1:]) + 1)]
    if ids != expected_ids:
        raise SystemExit("RAH evidence ledger is not contiguous through expected high-water")
    flat_stamps = 0
    flat_matches = 0
    for filename in state_store.GENERATION_FILES:
        flat = read_json(ralph_root / filename)
        if flat.get("state_generation") == generation:
            flat_stamps += 1
        stripped = {key: value for key, value in flat.items() if key != "state_generation"}
        authority = payloads[filename]
        if isinstance(authority, dict):
            authority = {key: value for key, value in authority.items() if key != "state_generation"}
        if state_store._dump(stripped) == state_store._dump(authority):
            flat_matches += 1
    if flat_stamps != 6 or flat_matches != 6:
        raise SystemExit("RAH flat snapshot verification failed")
    return {
        "schema_version": 1,
        "attempt_id": ATTEMPT_ID,
        "status": "PASS",
        "current_generation": generation,
        "generation_manifest_sha256": sha256_id(
            ralph_root / "generations" / generation / "generation-manifest.json"
        ),
        "retained_generation_count": len(generations),
        "generation_file_hashes_verified": verified_hashes,
        "flat_snapshot_stamps_verified": flat_stamps,
        "flat_snapshot_content_matches": flat_matches,
        "latest_evidence_id": ids[-1],
        "evidence_count": len(ids),
        "ralph_status": payloads["loop_state.json"].get("status"),
        "implementation_gate": payloads["loop_state.json"].get("implementation_gate"),
        "completion_ready": payloads["loop_state.json"].get("completion_readiness", {}).get("ready"),
    }


def verify_core_generation_artifact(integrity: dict[str, Any]) -> None:
    generation = str(integrity.get("current_generation"))
    if not re.fullmatch(r"000079-[0-9a-f]{8}", generation):
        raise SystemExit("stored J02 core generation is not generation 79")
    directory = ROOT / ".rah/ralph/generations" / generation
    manifest = read_json(directory / "generation-manifest.json")
    if sha256_id(directory / "generation-manifest.json") != integrity.get("generation_manifest_sha256"):
        raise SystemExit("stored J02 core generation manifest hash changed")
    if manifest.get("generation") != generation:
        raise SystemExit("stored J02 core generation identity changed")
    ledger = read_json(directory / "evidence_ledger.json")
    entries = ledger.get("entries")
    ids = [str(row.get("id")) for row in entries if isinstance(row, dict)] if isinstance(entries, list) else []
    if ids != [f"E{index:04d}" for index in range(1, 83)]:
        raise SystemExit("stored J02 core generation does not end at E0082")


def report_document(integrity: dict[str, Any]) -> dict[str, Any]:
    documents = {name: read_json(ATTEMPT / name) for name in PRE_CORE_JSON_ARTIFACTS}
    regression = documents["full-regression-impact.json"]
    return {
        "work_package_id": WORK_PACKAGE_ID,
        "attempt_id": ATTEMPT_ID,
        "title": "Progressive references and context budgets",
        "status": "FAIL",
        "implementation_status": "VERIFIED",
        "package_status": "FAIL",
        "completion_ready": False,
        "inventory": {
            "inventory_hash": INVENTORY_HASH,
            "metadata_utf8_bytes": 4767,
            "metadata_o200k_base_tokens": 1112,
            "skill_count": 29,
            "parent_skill_count": 1,
            "child_skill_count": 28,
            "reference_count": 17,
            "maximum_closure_count": 11,
            "maximum_transitive_depth": 5,
        },
        "verification": {
            "budget_boundary_cases": "12/12",
            "selection_cases": "35/35",
            "adversarial_reachability_cases": "16/16",
            "loader_determinism": "100/100",
            "targeted_node": "25/25",
            "j01_node_regression": "19/19",
            "targeted_python": "16 passed, 1 failed",
            "full_python": "963 passed, 1 failed",
            "full_node": "436 passed, 1 failed",
            "new_skip_or_xfail_count": 0,
        },
        "blocking_findings": list(BLOCKERS),
        "required_checks": {
            "context_budget_test": {
                "status": "FAIL",
                "reason": "repository exact tokenizer dependency lock is absent",
            },
            "reference_reachability_test": {"status": "PASS"},
            "skill_routing_eval": {"status": "PASS", "passed": 19},
            "skill_metadata_lint": {"status": "PASS", "passed": 29},
            "inventory_hash_verification": {"status": "PASS"},
            "full_python_suite": {
                "status": "FAIL",
                "passed": 963,
                "failed": 1,
            },
            "full_node_suite": {
                "status": "FAIL",
                "passed": 436,
                "failed": 1,
                "reason": "S04-TM004 fingerprint changed",
            },
            "write_scope_audit": {"status": "PASS", "violations": 0},
            "independent_review": {
                "status": "FAIL",
                "mode": "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_IMPLEMENTATION_REVIEW",
                "actor_independence": False,
                "blocking_finding_count": 2,
            },
        },
        "regression": regression,
        "review": {
            "artifact": "artifacts/work_packages/J02/attempts/0002/review.md",
            "verdict": "FAIL",
            "blocking_finding_count": 2,
            "mode": "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_IMPLEMENTATION_REVIEW",
            "actor_independence": False,
            "assurance_limitation": (
                "Procedurally separate primary-session review; not actor-independent "
                "certification because Fleet and subagents were prohibited."
            ),
        },
        "dependency_effect": {
            "J01": "PASS",
            "J02": "FAIL",
            "J03": "DEPENDENCY_READY_BUT_UNSTARTED",
            "J04": "WAITING_ON_J02_AND_J03_AND_NOT_STARTED",
        },
        "historical_and_worktree_preservation": {
            "j02_0001_immutable": True,
            "dirty_worktree_preserved": True,
            "pyproject_toml_modified": False,
            "uv_lock_modified": False,
            "s04_fixture_or_test_modified": False,
            "reset_clean_stash_commit_push_performed": False,
            "subagents_or_fleet_used": False,
        },
        "output_artifacts": [
            f"artifacts/work_packages/J02/attempts/0002/{name}" for name in OUTPUT_ARTIFACTS
        ],
        "rah_state": {
            "core_generation": integrity["current_generation"],
            "core_generation_manifest_sha256": integrity["generation_manifest_sha256"],
            "core_evidence_id": "E0082",
            "final_artifact_seal_evidence_id": "E0083",
            "retained_generation_count_after_core": integrity["retained_generation_count"],
            "generation_file_hashes_verified_after_core": integrity["generation_file_hashes_verified"],
            "flat_snapshot_stamps_verified_after_core": integrity["flat_snapshot_stamps_verified"],
            "flat_snapshot_content_matches_after_core": integrity["flat_snapshot_content_matches"],
            "status": "blocked",
            "implementation_gate": "fail",
            "completion_ready": False,
        },
        "resume_condition": (
            "A product-owner decision must assign the exact tokenizer dependency-lock "
            "owner and authorize pyproject.toml plus uv.lock, and assign S04 "
            "traceability fingerprint reconciliation/update authority. Then J02 must "
            "run as a new attempt; J03/J04 remain unstarted until their dependency gates."
        ),
        "not_claimed": [
            "J02 package PASS",
            "repository-wide green status",
            "J03 or J04 start",
            "release readiness or product completion",
            "actor-independent review",
        ],
    }


def build_pre_core() -> None:
    ATTEMPT.mkdir(parents=True, exist_ok=True)
    documents = evidence_documents()
    for name, document in documents.items():
        write_json(name, document)
    rows = command_rows(documents)
    write_commands(rows)
    (ATTEMPT / "review.md").write_text(review_text(), encoding="utf-8", newline="\n")
    verify_pre_core()


def verify_pre_core() -> dict[str, Any]:
    expected_documents = evidence_documents()
    for name, expected in expected_documents.items():
        if read_json(ATTEMPT / name) != expected:
            raise SystemExit(f"stored J02 evidence differs from live recomputation: {name}")
    verify_commands(command_rows(expected_documents))
    if (ATTEMPT / "review.md").read_text(encoding="utf-8") != review_text():
        raise SystemExit("stored J02 review differs from deterministic review")
    return {
        "attempt_id": ATTEMPT_ID,
        "status": "FAIL",
        "implementation_status": "VERIFIED",
        "pre_core_json_artifact_count": len(PRE_CORE_JSON_ARTIFACTS),
        "blocking_finding_count": 2,
        "completion_ready": False,
    }


def build_post_core() -> None:
    verify_pre_core()
    integrity = generation_integrity(79, "E0082")
    if (
        integrity["ralph_status"] != "blocked"
        or integrity["implementation_gate"] != "fail"
        or integrity["completion_ready"] is not False
    ):
        raise SystemExit("J02 core RAH state is not blocked/fail/completion_ready=false")
    write_json("rah-core-integrity.json", integrity)
    write_json("report.json", report_document(integrity))
    PACKAGE_ROOT.mkdir(parents=True, exist_ok=True)
    for name in ("report.json", "commands.jsonl", "review.md"):
        shutil.copyfile(ATTEMPT / name, PACKAGE_ROOT / name)
    verify_post_core()


def verify_post_core() -> dict[str, Any]:
    pre = verify_pre_core()
    stored_integrity = read_json(ATTEMPT / "rah-core-integrity.json")
    generations = generation_names()
    if len(generations) == 79:
        observed_integrity = generation_integrity(79, "E0082")
        if stored_integrity != observed_integrity:
            raise SystemExit("stored J02 RAH core integrity differs from live core state")
    elif len(generations) == 80:
        verify_core_generation_artifact(stored_integrity)
    else:
        raise SystemExit(f"unexpected J02 post-core generation count: {len(generations)}")
    expected_report = report_document(stored_integrity)
    if read_json(ATTEMPT / "report.json") != expected_report:
        raise SystemExit("stored J02 report differs from verified evidence")
    for name in ("report.json", "commands.jsonl", "review.md"):
        if (ATTEMPT / name).read_bytes() != (PACKAGE_ROOT / name).read_bytes():
            raise SystemExit(f"J02 root projection differs from attempt artifact: {name}")
    return {
        **pre,
        "core_generation": stored_integrity["current_generation"],
        "core_evidence_id": "E0082",
        "root_projection_count": 3,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode",
        choices=("build-pre-core", "verify-pre-core", "build-post-core", "verify-post-core"),
    )
    args = parser.parse_args()
    if args.mode == "build-pre-core":
        build_pre_core()
        result = verify_pre_core()
    elif args.mode == "verify-pre-core":
        result = verify_pre_core()
    elif args.mode == "build-post-core":
        build_post_core()
        result = verify_post_core()
    else:
        result = verify_post_core()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
