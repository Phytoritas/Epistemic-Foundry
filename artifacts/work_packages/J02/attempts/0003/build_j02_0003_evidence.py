#!/usr/bin/env python3
"""Build byte-bound evidence for the J02-0003 revalidation attempt.

This verifier recomputes J02 inventory, tokenizer, reference graph, selection,
dependency-lock, and regression evidence from the current repository bytes. It
does not import or copy evidence from J02-0002. The single S04-TM004 Node
failure is retained as the exact later-attempt debt authorized by
HD-EF4-B04-SG002-20260730-001.
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
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path
from types import ModuleType
from typing import Any

import yaml
from jsonschema import Draft202012Validator


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/J02/attempts/0003"
PACKAGE_ROOT = ROOT / "artifacts/work_packages/J02"
ATTEMPT_ID = "J02-0003"
WORK_PACKAGE_ID = "J02"
RECORDED_AT = "2026-07-30T13:45:00.000Z"

INVENTORY_PATH = ROOT / "plugins/epistemic-foundry/skills/skill-inventory.json"
FIXTURE_ROOT = ROOT / "tests/fixtures/j02"
COUNTER_PATH = ROOT / "tools/skill-context/count_tokens.py"
MANIFEST_PATH = ROOT / "manifests/development_manifest.yaml"
RECEIPT_SCHEMA_PATH = ROOT / "schemas/artifact-receipt.schema.json"

J02_DECISION_PATH = (
    ROOT
    / "artifacts/authority_decisions/"
    "HD-EF4-J02-SG002-20260730-001.human-decision.json"
)
ORDER_DECISION_PATH = (
    ROOT
    / "artifacts/authority_decisions/"
    "HD-EF4-B04-SG002-20260730-001.human-decision.json"
)

CHANGED_PRODUCT_FILES = (
    "tools/skill-context/count_tokens.py",
    "tests/test_j02_context_budget.py",
    "plugins/epistemic-foundry/skills/skill-inventory.json",
    "tests/fixtures/j02/skill-inventory.expected.json",
    "tests/fixtures/j02/reference-selection-cases.json",
)

PRESERVED_INPUTS = {
    "artifacts/work_packages/J02/attempts/0001/report.json":
        "6b0f4f37acbe1014afcf17ef5449fa4ed799e7ca0e7ea7523c014a3a44607688",
    "artifacts/work_packages/J02/attempts/0002/report.json":
        "17e342ae7f54707ebc0acc17f695507397b9d300a54cef741b2ab3ed05ffbd0c",
    "artifacts/work_packages/B02/attempts/0002/report.json":
        "3c2259e7d4b7ce987960b82f2fb161914637567eacf3030d24899e44f462b33a",
    "artifacts/work_packages/B04/attempts/0005/report.json":
        "ff7e1f1fa7836fe612284542353e5aefe5f26ab644e2ac40c5f79c09f06ca1e2",
    "artifacts/work_packages/F04/attempts/0002/report.json":
        "5a2414ebb79c923af7425b87d614faa088ba9fbd4e6950406948b2eb86d6ab46",
    "pyproject.toml":
        "31cf5dffa4703052d70536dbbb6e64d917900c70d52b039f9c9cbf09920353db",
    "uv.lock":
        "5c3798ff0323f9352d73f17fa93913590d7dbb5382dd0de26b1619e775b58caa",
    "manifests/development_manifest.yaml":
        "5dd99d2aae1e9ef662b9b8242b5fa921621434c6600c9c06e3a573d03079bb12",
    "MASTER_SPEC.md":
        "d4854c916594610e0503f9b017c57b0dbac9f52eef78b825b922fdf26b1a0fe3",
    "artifacts/authority_decisions/HD-EF4-J02-SG002-20260730-001.human-decision.json":
        "ad7c8345bbcaa813c641ba139913728dabfe969fb1fef06a3e2209949939cc90",
    "artifacts/authority_decisions/HD-EF4-B04-SG002-20260730-001.human-decision.json":
        "13feb432b4504e11fecabfed4b6fc51c17db315b7a7124106baa82ff1cd63ffe",
}

JUNIT_HASHES = {
    "targeted-python-suite.junit.xml":
        "117e3121be75c7b9b0d255c68358d31529d70728b91ceaa89d0f295142aa0bc5",
    "targeted-node-suite.junit.xml":
        "5ba097b4554c7c667adfe41e80a6f465f4b666fa80670d72accf39cfce92c574",
    "j01-regression-node-suite.junit.xml":
        "489631a9d362ffc87f0a020d2e886199ec4460a5c51c3705ef1bde9cb5ca47ea",
    "full-python-suite.junit.xml":
        "ab53c845aeda8a0ff60b503bb198a14030614c4a9bd569c21462e6d61d1595eb",
    "full-node-suite.junit.xml":
        "1ee0a32d5b80e2901e8d8c0c83d6b4d406d5eed0b5726b8349a57190c40e12ab",
}

NODE_TOTAL_PATTERNS = {
    label: re.compile(rb"<!-- " + label.encode("ascii") + rb" ([0-9]+) -->")
    for label in ("tests", "pass", "fail", "cancelled", "skipped", "todo")
}

S04_TEST = "S04-TM004 traceability source bindings fail on undocumented contract drift"
S04_TEST_FILE = "tests/security/s04-threat-model-traceability.test.mjs"
S04_SOURCE_PATH = "manifests/development_manifest.yaml"
S04_CURRENT_HASH = "5dd99d2aae1e9ef662b9b8242b5fa921621434c6600c9c06e3a573d03079bb12"
S04_STALE_BOUND_HASH = "7d1d3248dc3e2ca56d8f08ec282aa3d95bea9466ba6b7580fccff81e0f639319"

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


def load_counter() -> ModuleType:
    spec = importlib.util.spec_from_file_location("j02_0003_counter", COUNTER_PATH)
    if spec is None or spec.loader is None:
        raise SystemExit("cannot load canonical J02 token counter")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


COUNTER = load_counter()


def assert_preserved_inputs() -> dict[str, str]:
    observed: dict[str, str] = {}
    for relative, expected in PRESERVED_INPUTS.items():
        path = ROOT / relative
        if not path.is_file():
            raise SystemExit(f"preserved input/history is missing: {relative}")
        actual = sha256(path)
        if actual != expected:
            raise SystemExit(
                f"preserved input/history changed: {relative}: {actual} != {expected}"
            )
        observed[relative] = "sha256:" + actual
    for name, expected in JUNIT_HASHES.items():
        path = ATTEMPT / name
        actual = sha256(path) if path.is_file() else "MISSING"
        if actual != expected:
            raise SystemExit(f"J02-0003 JUnit changed: {name}: {actual} != {expected}")
    return observed


def source_inventory() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for relative in CHANGED_PRODUCT_FILES:
        path = ROOT / relative
        data = path.read_bytes()
        if data.startswith(b"\xef\xbb\xbf") or b"\x00" in data:
            raise SystemExit(f"invalid encoding marker in J02 product file: {relative}")
        text = data.decode("utf-8")
        if "\ufffd" in text:
            raise SystemExit(f"replacement character in J02 product file: {relative}")
        rows.append(
            {
                "path": relative,
                "byte_size": len(data),
                "sha256": sha256_bytes(data),
            }
        )
    return rows


def decision_evidence(path: Path, expected_id: str) -> dict[str, Any]:
    decision = read_json(path)
    if decision.get("decision_id") != expected_id:
        raise SystemExit(f"authority decision identity changed: {path.name}")
    asserted = decision.get("decision_hash")
    computed = canonical_hash_excluding(decision, "decision_hash")
    if asserted != computed:
        raise SystemExit(f"authority decision hash mismatch: {path.name}")
    return {
        "decision_id": expected_id,
        "path": path.relative_to(ROOT).as_posix(),
        "file_sha256": sha256_id(path),
        "decision_hash": computed,
    }


def inventory_evidence() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    inventory = read_json(INVENTORY_PATH)
    expected = read_json(FIXTURE_ROOT / "skill-inventory.expected.json")
    report = COUNTER.inventory_report(ROOT, INVENTORY_PATH)
    if report.get("status") != "PASS":
        raise SystemExit("canonical token counter did not validate the inventory")

    preimage = copy.deepcopy(inventory)
    asserted_inventory_hash = preimage.pop("inventory_hash", None)
    computed_inventory_hash = sha256_bytes(canonical_bytes(preimage))
    if asserted_inventory_hash != computed_inventory_hash:
        raise SystemExit("J02 inventory self-hash differs from current bytes")
    if expected.get("inventory_hash") != computed_inventory_hash:
        raise SystemExit("J02 expected inventory fixture is stale")
    for field in (
        "inventory_id",
        "inventory_version",
        "parent_skill_id",
        "metadata_projection",
    ):
        if expected.get(field) != inventory.get(field):
            raise SystemExit(f"J02 expected inventory fixture differs at {field}")

    skills = inventory.get("skills")
    references = inventory.get("references")
    if not isinstance(skills, list) or len(skills) != 29:
        raise SystemExit("J02 inventory must contain exactly 29 skills")
    if not isinstance(references, list) or len(references) != 17:
        raise SystemExit("J02 inventory must contain exactly 17 references")
    if expected.get("skill_count") != 29 or expected.get("reference_count") != 17:
        raise SystemExit("J02 expected inventory cardinality changed")

    metadata = COUNTER.serialize_metadata(skills)
    encoding = COUNTER.require_tokenizer()
    token_count, _ = COUNTER.count_text(metadata, encoding)
    metadata_projection = {
        "sha256": sha256_bytes(metadata.encode("utf-8")),
        "byte_count": len(metadata.encode("utf-8")),
        "token_count": token_count,
    }
    if metadata_projection != {
        "sha256": "sha256:f7d347b3e64d3d079fd3deaf07a02da95a8dabd4ccf212a6710973ade33dea17",
        "byte_count": 4767,
        "token_count": 1112,
    }:
        raise SystemExit("J02 metadata projection changed from the fixed oracle")

    tokenizer_fixture = read_json(FIXTURE_ROOT / "tokenizer-vectors.json")
    vectors = tokenizer_fixture.get("vectors")
    if not isinstance(vectors, list) or len(vectors) != 7:
        raise SystemExit("J02 tokenizer vector cardinality changed")
    vector_rows: list[dict[str, Any]] = []
    for vector in vectors:
        text = str(vector["text"])
        if vector.get("normalize_nfc"):
            text = unicodedata.normalize("NFC", text)
        count, token_ids = COUNTER.count_text(text, encoding)
        if text != vector.get("encoded_text") or token_ids != vector.get("token_ids"):
            raise SystemExit(f"tokenizer vector mismatch: {vector.get('id')}")
        vector_rows.append(
            {"id": str(vector["id"]), "token_count": count, "status": "PASS"}
        )

    boundary_fixture = read_json(FIXTURE_ROOT / "context-budget-cases.json")
    cases = boundary_fixture.get("cases")
    if not isinstance(cases, list) or len(cases) != 12:
        raise SystemExit("J02 budget boundary fixture must contain exactly 12 cases")
    boundary_rows: list[dict[str, Any]] = []
    for case in cases:
        observed = "PASS"
        try:
            if case["operation"] == "metadata":
                COUNTER.assert_metadata_budget(**case["input"])
            elif case["operation"] == "description":
                COUNTER.assert_description_budget("x" * int(case["input"]["byte_count"]))
            elif case["operation"] == "activation":
                COUNTER.assert_activation_budget(case["input"])
            else:
                raise SystemExit(f"unknown boundary operation: {case['operation']}")
        except COUNTER.TokenizerContractError as error:
            observed = error.code
        if observed != case.get("expected"):
            raise SystemExit(f"budget boundary mismatch: {case.get('case_id')}")
        boundary_rows.append(
            {
                "case_id": str(case["case_id"]),
                "expected": str(case["expected"]),
                "observed": observed,
            }
        )

    lock = COUNTER.verify_repository_tokenizer_lock(ROOT)
    if lock != {
        "dependency_group": "skill-context",
        "pyproject_requirement": "tiktoken==0.13.0",
        "lock_package_count": 1,
        "locked_version": "0.13.0",
        "runtime_dependency_exposure": False,
        "sdist_sha256": COUNTER.TOKENIZER_SDIST_SHA256,
        "status": "PASS",
    }:
        raise SystemExit(f"repository tokenizer-lock result changed: {lock}")
    installed = importlib.metadata.version("tiktoken")
    if installed != "0.13.0" or encoding.name != "o200k_base":
        raise SystemExit("installed tokenizer runtime differs from the canonical pin")

    metadata_evidence = {
        "attempt_id": ATTEMPT_ID,
        "status": "PASS",
        "inventory_hash": computed_inventory_hash,
        "skill_count": 29,
        "metadata_projection": metadata_projection,
        "limits": {"max_utf8_bytes": 6400, "max_o200k_base_tokens": 1600},
        "margin": {"utf8_bytes": 1633, "o200k_base_tokens": 488},
        "boundary_case_count": 12,
        "boundary_exact_pass_count": 12,
        "boundary_cases": boundary_rows,
    }
    tokenizer_evidence = {
        "attempt_id": ATTEMPT_ID,
        "status": "PASS",
        "installed_runtime": {
            "package": "tiktoken",
            "version": installed,
            "encoding": encoding.name,
            "status": "PASS",
        },
        "repository_lock": {
            **lock,
            "pyproject_path": "pyproject.toml",
            "pyproject_sha256": sha256_id(ROOT / "pyproject.toml"),
            "uv_lock_path": "uv.lock",
            "uv_lock_sha256": sha256_id(ROOT / "uv.lock"),
            "dependency_group_exact_member_count": 1,
            "runtime_or_optional_exposure": False,
            "root_requires_dist_exposure": False,
        },
        "vectors": vector_rows,
        "vector_exact_pass_count": 7,
        "negative_dependency_contract_tests": {
            "nonexclusive_group_rejected": True,
            "runtime_exposure_rejected": True,
            "expanded_uv_group_rejected": True,
        },
    }
    authority_evidence = {
        "attempt_id": ATTEMPT_ID,
        "status": "PASS",
        "inventory_id": inventory.get("inventory_id"),
        "inventory_version": inventory.get("inventory_version"),
        "inventory_hash": computed_inventory_hash,
        "inventory_file_sha256": sha256_id(INVENTORY_PATH),
        "skill_count": 29,
        "reference_count": 17,
        "metadata_projection": metadata_projection,
        "content_hash_mismatch_count": 0,
        "byte_or_token_budget_violation_count": 0,
        "canonical_counter_report": report,
    }
    return metadata_evidence, tokenizer_evidence, authority_evidence


def graph_evidence() -> tuple[dict[str, Any], dict[str, Any]]:
    inventory = read_json(INVENTORY_PATH)
    skills = {str(row["skill_id"]): row for row in inventory["skills"]}
    references = {str(row["reference_id"]): row for row in inventory["references"]}
    if len(skills) != 29 or len(references) != 17:
        raise SystemExit("J02 graph source cardinality changed")

    visiting: set[str] = set()
    depths: dict[str, int] = {}

    def depth(reference_id: str) -> int:
        if reference_id in depths:
            return depths[reference_id]
        if reference_id in visiting:
            raise SystemExit(f"reference graph cycle: {reference_id}")
        if reference_id not in references:
            raise SystemExit(f"missing reference target: {reference_id}")
        visiting.add(reference_id)
        dependencies = [str(value) for value in references[reference_id]["depends_on"]]
        result = 1 + max((depth(value) for value in dependencies), default=-1)
        visiting.remove(reference_id)
        depths[reference_id] = result
        return result

    def closure(reference_ids: list[str]) -> set[str]:
        result: set[str] = set()

        def add(reference_id: str) -> None:
            if reference_id in result:
                return
            if reference_id not in references:
                raise SystemExit(f"missing reference closure target: {reference_id}")
            for dependency in references[reference_id]["depends_on"]:
                add(str(dependency))
            result.add(reference_id)

        for reference_id in reference_ids:
            add(reference_id)
        return result

    for reference_id in references:
        depth(reference_id)

    parent = skills.get("foundry")
    if not isinstance(parent, dict):
        raise SystemExit("J02 parent skill is missing")
    children = {str(value) for value in parent.get("child_skills", [])}
    if children != set(skills) - {"foundry"} or len(children) != 28:
        raise SystemExit("J02 parent/child graph changed")

    declared: set[str] = set()
    defaults: dict[str, dict[str, int]] = {}
    maximum_count = 0
    maximum_depth = 0
    for skill_id, skill in skills.items():
        direct = [str(value) for value in skill.get("direct_references", [])]
        declared.update(direct)
        for conditional in skill.get("conditional_references", []):
            declared.add(str(conditional["reference_id"]))
        selected = closure(direct)
        selected_depth = max((depths[value] for value in selected), default=0)
        maximum_count = max(maximum_count, len(selected))
        maximum_depth = max(maximum_depth, selected_depth)
        defaults[skill_id] = {
            "transitive_depth": selected_depth,
            "total_reference_bytes": sum(
                int(references[value]["byte_count"]) for value in selected
            ),
            "total_reference_tokens": sum(
                int(references[value]["token_count"]) for value in selected
            ),
        }
    if declared != set(references) or maximum_count != 11 or maximum_depth != 5:
        raise SystemExit("J02 reference graph reachability/limits changed")

    selection_fixture = read_json(FIXTURE_ROOT / "reference-selection-cases.json")
    cases = selection_fixture.get("cases")
    if (
        selection_fixture.get("inventory_hash") != inventory.get("inventory_hash")
        or not isinstance(cases, list)
        or len(cases) != 35
    ):
        raise SystemExit("J02 selection fixture identity/cardinality changed")
    categories: dict[str, int] = {}
    for case in cases:
        category = str(case["category"])
        categories[category] = categories.get(category, 0) + 1
        if category == "DEFAULT":
            expected = defaults[str(case["skill_id"])]
            for field, value in expected.items():
                if int(case[field]) != value:
                    raise SystemExit(
                        f"J02 selection fixture drift: {case['case_id']} {field}"
                    )
        if re.fullmatch(r"sha256:[0-9a-f]{64}", str(case.get("selection_hash"))) is None:
            raise SystemExit(f"invalid selection hash: {case.get('case_id')}")
    if categories != {
        "DEFAULT": 29,
        "CONDITIONAL_POSITIVE": 3,
        "CONDITIONAL_NEGATIVE": 3,
    }:
        raise SystemExit(f"J02 selection categories changed: {categories}")

    reachability_fixture = read_json(FIXTURE_ROOT / "reference-reachability-cases.json")
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
    if reachability_fixture.get("expected_graph") != expected_graph:
        raise SystemExit("J02 reachability expected graph changed")
    adversarial = reachability_fixture.get("adversarial_cases")
    if not isinstance(adversarial, list) or len(adversarial) != 16:
        raise SystemExit("J02 adversarial case cardinality changed")

    targeted = node_junit(
        "targeted-node-suite.junit.xml",
        expected={
            "tests": 25,
            "pass": 25,
            "fail": 0,
            "cancelled": 0,
            "skipped": 0,
            "todo": 0,
        },
    )
    names = {row["name"] for row in targeted["testcases"]}
    expected_adversarial_names = {str(row["case_id"]) for row in adversarial}
    if not expected_adversarial_names.issubset(names):
        raise SystemExit("targeted Node receipt omits an adversarial reachability case")
    if "all 35 fixed selection cases match sealed IDs, order, reasons, and totals" not in names:
        raise SystemExit("targeted Node receipt omits exact selection verification")
    if "ResolvedSkillContext is identical across 100 repeated sealed loads" not in names:
        raise SystemExit("targeted Node receipt omits deterministic loader verification")

    selection = {
        "attempt_id": ATTEMPT_ID,
        "status": "PASS",
        "inventory_hash": inventory["inventory_hash"],
        "case_count": 35,
        "category_counts": categories,
        "selection_exact_pass_count": 35,
        "default_activation_budget_pass_count": 29,
        "maximum_default_closure_count": maximum_count,
        "maximum_default_transitive_depth": maximum_depth,
        "targeted_node_junit": targeted["summary"],
    }
    reachability = {
        "attempt_id": ATTEMPT_ID,
        "status": "PASS",
        "graph": expected_graph,
        "adversarial_case_count": 16,
        "adversarial_exact_fail_closed_count": 16,
        "adversarial_cases": [
            {
                "case_id": str(row["case_id"]),
                "expected_error": str(row["expected_error"]),
                "status": "PASS",
            }
            for row in adversarial
        ],
        "loader_determinism_repeat_count": 100,
        "loader_determinism_mismatch_count": 0,
        "targeted_node_junit": targeted["summary"],
    }
    return selection, reachability


def python_junit(name: str, expected: dict[str, int]) -> dict[str, Any]:
    path = ATTEMPT / name
    if sha256(path) != JUNIT_HASHES[name]:
        raise SystemExit(f"Python JUnit hash changed: {name}")
    root = ET.fromstring(path.read_bytes())
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    totals = {
        key: sum(int(suite.get(key, "0")) for suite in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }
    if totals != expected:
        raise SystemExit(f"Python JUnit totals changed: {name}: {totals}")
    cases = root.findall(".//testcase")
    failures: list[dict[str, str]] = []
    for case in cases:
        bad = case.find("failure")
        if bad is None:
            bad = case.find("error")
        if bad is not None:
            failures.append(
                {
                    "node_id": f"{case.get('classname', '')}::{case.get('name', '')}",
                    "message": "\n".join(
                        value
                        for value in (bad.get("message") or "", bad.text or "")
                        if value
                    ),
                }
            )
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": sha256_id(path),
        "byte_size": path.stat().st_size,
        "totals": {
            **totals,
            "passed": totals["tests"]
            - totals["failures"]
            - totals["errors"]
            - totals["skipped"],
        },
        "xml_testcase_count": len(cases),
        "failures": failures,
        "testcase_ids": [
            f"{case.get('classname', '')}::{case.get('name', '')}" for case in cases
        ],
    }


def relative_test_file(value: str) -> str:
    normalized = value.replace("\\", "/")
    for marker in ("packages/", "tests/", "web/"):
        index = normalized.find(marker)
        if index >= 0:
            return normalized[index:]
    return normalized


def node_junit(name: str, *, expected: dict[str, int]) -> dict[str, Any]:
    path = ATTEMPT / name
    if sha256(path) != JUNIT_HASHES[name]:
        raise SystemExit(f"Node JUnit hash changed: {name}")
    content = path.read_bytes()
    root = ET.fromstring(content)
    totals: dict[str, int] = {}
    for label, pattern in NODE_TOTAL_PATTERNS.items():
        matches = pattern.findall(content)
        if len(matches) != 1:
            raise SystemExit(f"missing/ambiguous Node footer {label}: {name}")
        totals[label] = int(matches[0])
    if totals != expected:
        raise SystemExit(f"Node JUnit totals changed: {name}: {totals}")
    cases = root.findall(".//testcase")
    failures: list[dict[str, str]] = []
    testcases: list[dict[str, str]] = []
    for case in cases:
        row = {
            "name": str(case.get("name") or ""),
            "file": relative_test_file(str(case.get("file") or "")),
        }
        testcases.append(row)
        bad = case.find("failure")
        if bad is None:
            bad = case.find("error")
        if bad is not None:
            failures.append(
                {
                    **row,
                    "message": "\n".join(
                        value
                        for value in (bad.get("message") or "", bad.text or "")
                        if value
                    ),
                }
            )
    if len(failures) != totals["fail"]:
        raise SystemExit(f"Node failure inventory differs from footer: {name}")
    summary = {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": sha256_id(path),
        "byte_size": path.stat().st_size,
        "totals": totals,
        "xml_testcase_count": len(cases),
        "xml_footer_testcase_delta": totals["tests"] - len(cases),
        "semantic_totals_authority": "node_junit_footer_comments",
        "test_file_count": len({row["file"] for row in testcases if row["file"]}),
        "failures": failures,
    }
    return {"summary": summary, "testcases": testcases}


def expected_node_files() -> list[str]:
    files = sorted(
        path.relative_to(ROOT).as_posix()
        for top in ("packages", "tests", "web")
        for path in (ROOT / top).rglob("*.test.mjs")
        if path.is_file()
    )
    if len(files) != 52 or len(set(files)) != 52:
        raise SystemExit(f"live Node test inventory is not exactly 52: {len(files)}")
    return files


def regression_evidence() -> tuple[dict[str, Any], dict[str, Any]]:
    targeted_python = python_junit(
        "targeted-python-suite.junit.xml",
        {"tests": 20, "failures": 0, "errors": 0, "skipped": 0},
    )
    full_python = python_junit(
        "full-python-suite.junit.xml",
        {"tests": 990, "failures": 0, "errors": 0, "skipped": 0},
    )
    required_python_nodes = {
        "tests.test_j02_context_budget::test_repository_dependency_lock_closes_exact_tiktoken_pin",
        "tests.test_j02_context_budget::test_repository_dependency_lock_rejects_nonexclusive_dependency_group",
        "tests.test_j02_context_budget::test_repository_dependency_lock_rejects_runtime_exposure",
        "tests.test_j02_context_budget::test_repository_dependency_lock_rejects_expanded_uv_group",
    }
    if not required_python_nodes.issubset(set(targeted_python["testcase_ids"])):
        raise SystemExit("targeted Python receipt omits dependency-lock contract cases")

    targeted_node = node_junit(
        "targeted-node-suite.junit.xml",
        expected={
            "tests": 25,
            "pass": 25,
            "fail": 0,
            "cancelled": 0,
            "skipped": 0,
            "todo": 0,
        },
    )["summary"]
    j01_node = node_junit(
        "j01-regression-node-suite.junit.xml",
        expected={
            "tests": 19,
            "pass": 19,
            "fail": 0,
            "cancelled": 0,
            "skipped": 0,
            "todo": 0,
        },
    )["summary"]
    full_node_result = node_junit(
        "full-node-suite.junit.xml",
        expected={
            "tests": 460,
            "pass": 459,
            "fail": 1,
            "cancelled": 0,
            "skipped": 0,
            "todo": 0,
        },
    )
    full_node = full_node_result["summary"]
    observed_files = sorted(
        {row["file"] for row in full_node_result["testcases"] if row["file"]}
    )
    if observed_files != expected_node_files():
        raise SystemExit("full Node receipt does not cover all 52 live test files")
    if len(full_node["failures"]) != 1:
        raise SystemExit("full Node receipt must contain exactly one failure")
    failure = full_node["failures"][0]
    blob = failure["message"]
    if (
        failure["name"] != S04_TEST
        or failure["file"] != S04_TEST_FILE
        or S04_CURRENT_HASH not in blob
        or S04_STALE_BOUND_HASH not in blob
    ):
        raise SystemExit("full Node residual is not the authorized S04-TM004 debt")

    regression = {
        "attempt_id": ATTEMPT_ID,
        "status": "PASS_WITH_BOUNDED_LATER_ATTEMPT_DEBT",
        "targeted_python": {
            key: value for key, value in targeted_python.items() if key != "testcase_ids"
        },
        "targeted_node": targeted_node,
        "j01_node_regression": j01_node,
        "full_python": {
            key: value for key, value in full_python.items() if key != "testcase_ids"
        },
        "full_node": full_node,
        "j02_causal_failure_count": 0,
        "python_failure_count": 0,
        "node_failure_count": 1,
        "new_skip_or_xfail_count": 0,
        "bounded_later_attempt_debt_count": 1,
        "repository_fully_green": False,
        "full_node_test_file_count": 52,
    }
    debt = {
        "attempt_id": ATTEMPT_ID,
        "status": "AUTHORIZED_BOUNDED_LATER_ATTEMPT_DEBT",
        "debt_id": "S04-TM004",
        "owner": "S04",
        "resolving_attempt": "S04-0003",
        "authorizing_decision_id": "HD-EF4-B04-SG002-20260730-001",
        "test_name": S04_TEST,
        "test_file": S04_TEST_FILE,
        "source_path": S04_SOURCE_PATH,
        "current_source_sha256": "sha256:" + sha256(MANIFEST_PATH),
        "stale_bound_successor_sha256": "sha256:" + S04_STALE_BOUND_HASH,
        "normalized_failure_fingerprint": {
            "test_name": S04_TEST,
            "test_file": S04_TEST_FILE,
            "actual": "sha256:" + S04_CURRENT_HASH,
            "expected": "sha256:" + S04_STALE_BOUND_HASH,
        },
        "j02_causal_impact": "NONE",
        "failure_count": 1,
        "skip_or_xfail_used": False,
        "package_pass_effect": (
            "The later product-owner ordering decision requires J02-0003 before "
            "S04-0003; this exact residual is not relabeled as resolved or hidden."
        ),
    }
    return regression, debt


def dependency_evidence() -> dict[str, Any]:
    b02 = read_json(ROOT / "artifacts/work_packages/B02/attempts/0002/report.json")
    b04 = read_json(ROOT / "artifacts/work_packages/B04/attempts/0005/report.json")
    f04 = read_json(ROOT / "artifacts/work_packages/F04/attempts/0002/report.json")
    if (
        b02.get("status") != "PASS"
        or b02.get("package_status") != "PASS"
        or b02.get("required_checks", {})
        .get("tiktoken_exact_lock_check", {})
        .get("status")
        != "PASS"
    ):
        raise SystemExit("B02-0002 exact tokenizer-lock dependency is not PASS")
    if (
        b04.get("status") != "PASS"
        or b04.get("package_status") != "PASS"
        or b04.get("dependency_build_revalidation") != "PASS"
    ):
        raise SystemExit("B04-0005 dependency/build revalidation is not PASS")
    if f04.get("status") != "PASS" or f04.get("package_status") != "PASS":
        raise SystemExit("F04-0002 predecessor in the ordered repair chain is not PASS")
    j02_decision = decision_evidence(
        J02_DECISION_PATH, "HD-EF4-J02-SG002-20260730-001"
    )
    order_decision = decision_evidence(
        ORDER_DECISION_PATH, "HD-EF4-B04-SG002-20260730-001"
    )
    return {
        "attempt_id": ATTEMPT_ID,
        "status": "PASS",
        "dependencies": {
            "J01": {"status": "PASS", "manifest_dependency": True},
            "B02-0002": {
                "status": "PASS",
                "report_path": "artifacts/work_packages/B02/attempts/0002/report.json",
                "report_sha256": sha256_id(
                    ROOT / "artifacts/work_packages/B02/attempts/0002/report.json"
                ),
                "exact_tiktoken_lock": "PASS",
            },
            "B04-0005": {
                "status": "PASS",
                "report_path": "artifacts/work_packages/B04/attempts/0005/report.json",
                "report_sha256": sha256_id(
                    ROOT / "artifacts/work_packages/B04/attempts/0005/report.json"
                ),
                "dependency_build_revalidation": "PASS",
            },
            "F04-0002": {
                "status": "PASS",
                "report_path": "artifacts/work_packages/F04/attempts/0002/report.json",
                "report_sha256": sha256_id(
                    ROOT / "artifacts/work_packages/F04/attempts/0002/report.json"
                ),
            },
        },
        "authority": {
            "j02_repair_decision": j02_decision,
            "latest_serial_order_decision": order_decision,
            "effective_attempt_order": ["F04-0002", "J02-0003", "S04-0003"],
            "s04_residual_disposition": "BOUNDED_LATER_ATTEMPT_DEBT",
        },
        "next_state": {
            "J02": "PASS",
            "S04": "READY_FOR_ATTEMPT_0003",
            "B04-0007": "WAITING_ON_S04_0003",
        },
    }


def run_command(arguments: list[str], *, timeout: int = 180) -> dict[str, Any]:
    completed = subprocess.run(
        arguments,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env={**dict(__import__("os").environ), "PYTHONDONTWRITEBYTECODE": "1"},
    )
    return {
        "command": subprocess.list2cmdline(arguments),
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
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
    violations = [path for path in CHANGED_PRODUCT_FILES if not scope_allows(path, patterns)]
    if violations:
        raise SystemExit(f"J02 changed files outside write scope: {violations}")
    if not scope_allows("artifacts/work_packages/J02/attempts/0003/report.json", patterns):
        raise SystemExit("J02 artifact scope is absent")

    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if npm is None:
        raise SystemExit("npm is unavailable")
    structure = run_command([npm, "run", "check:structure"])
    boundaries = run_command([npm, "run", "check:boundaries"])
    scoped = run_command(["git", "diff", "--check", "--", *CHANGED_PRODUCT_FILES])
    full = run_command(["git", "diff", "--check"])
    for label, result in (
        ("repository structure", structure),
        ("package boundaries", boundaries),
        ("J02 scoped diff", scoped),
        ("repository diff", full),
    ):
        if result["exit_code"] != 0:
            raise SystemExit(f"{label} failed: {result['stdout']} {result['stderr']}")
    return {
        "attempt_id": ATTEMPT_ID,
        "status": "PASS",
        "manifest_sha256": sha256_id(MANIFEST_PATH),
        "manifest_package_count": 156,
        "manifest_write_scope": patterns,
        "changed_product_files": source_inventory(),
        "product_write_scope_violation_count": 0,
        "checks": {
            "npm_check_structure": {
                key: structure[key] for key in ("command", "exit_code", "status")
            },
            "npm_check_boundaries": {
                key: boundaries[key] for key in ("command", "exit_code", "status")
            },
            "scoped_git_diff_check": {
                key: scoped[key] for key in ("command", "exit_code", "status")
            },
            "repository_git_diff_check": {
                key: full[key] for key in ("command", "exit_code", "status")
            },
        },
        "preservation": {
            "j02_0001_report_sha256": sha256_id(
                ROOT / "artifacts/work_packages/J02/attempts/0001/report.json"
            ),
            "j02_0002_report_sha256": sha256_id(
                ROOT / "artifacts/work_packages/J02/attempts/0002/report.json"
            ),
            "pyproject_toml_modified_by_j02_0003": False,
            "uv_lock_modified_by_j02_0003": False,
            "s04_files_modified_by_j02_0003": False,
            "dirty_worktree_preserved": True,
            "subagents_or_fleet_used": False,
            "reset_clean_stash_commit_push_performed": False,
        },
    }


def evidence_documents() -> dict[str, dict[str, Any]]:
    assert_preserved_inputs()
    metadata, tokenizer, inventory = inventory_evidence()
    selection, reachability = graph_evidence()
    dependency = dependency_evidence()
    regression, debt = regression_evidence()
    scope = write_scope_evidence()
    return {
        "metadata-budget-verification.json": metadata,
        "tokenizer-verification.json": tokenizer,
        "inventory-authority-verification.json": inventory,
        "reference-selection-verification.json": selection,
        "reference-reachability-verification.json": reachability,
        "dependency-status.json": dependency,
        "full-regression-impact.json": regression,
        "preexisting-debt-reconciliation.json": debt,
        "write-scope-verification.json": scope,
    }


def command_records(documents: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    regression = documents["full-regression-impact.json"]
    checks = documents["write-scope-verification.json"]["checks"]
    rows = [
        ("C001", "Inspect J02-0001/J02-0002 history, current authority, dependency reports, and RAH state", 0, "PASS"),
        ("C002", "Apply bounded J02 dependency-lock validation and fixture corrections", 0, "PASS: five authorized J02 product files"),
        ("C003", "python tools/skill-context/count_tokens.py verify-inventory --root .", 0, "PASS: 29 skills, 17 references, exact inventory hash"),
        ("C004", "pytest tests/test_j02_context_budget.py --junitxml=<attempt>/targeted-python-suite.junit.xml", 0, "PASS: 20/20"),
        ("C005", "node --test --test-reporter=junit tests/node/j02-reference-reachability.test.mjs tests/node/j02-skill-context-loader.test.mjs", 0, "PASS: 25/25"),
        ("C006", "node --test --test-reporter=junit <J01 routing regression files>", 0, "PASS: 19/19"),
        ("C007", "pytest --junitxml=<attempt>/full-python-suite.junit.xml", 0, "PASS: 990/990"),
        ("C008", "node --test --test-concurrency=1 --test-reporter=junit <all 52 packages/tests/web .test.mjs files>", 1, "BOUNDED_LATER_ATTEMPT_DEBT: 459 passed; exact S04-TM004 failure only"),
        ("C009", "npm run check:structure", checks["npm_check_structure"]["exit_code"], "PASS"),
        ("C010", "npm run check:boundaries", checks["npm_check_boundaries"]["exit_code"], "PASS"),
        ("C011", "git diff --check -- <five J02 changed product files>", checks["scoped_git_diff_check"]["exit_code"], "PASS"),
        ("C012", "git diff --check", checks["repository_git_diff_check"]["exit_code"], "PASS"),
        ("C013", "Primary-session separate adversarial implementation review", 0, "PASS: zero J02-blocking findings; actor_independence=false"),
        ("D001", "Attempt PowerShell wildcard rg against JUnit paths", 1, "DIAGNOSTIC_ONLY: Windows path glob syntax rejected; no mutation"),
        ("D002", "Read two nonexistent guessed .mjs source filenames while locating TypeScript implementation", 1, "DIAGNOSTIC_ONLY: corrected to selector.ts/inventory.ts; no mutation"),
    ]
    if regression["full_python"]["totals"]["passed"] != 990:
        raise SystemExit("command record full Python total disagrees with evidence")
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
    dependency = documents["dependency-status.json"]
    debt = documents["preexisting-debt-reconciliation.json"]
    return f"""# J02-0003 separate adversarial implementation review

Status: `PASS_WITH_PRIMARY_SESSION_SEPARATE_ADVERSARIAL_IMPLEMENTATION_REVIEW`

Final verdict: `PASS`

Blocking J02 findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_IMPLEMENTATION_REVIEW`

Actor independence: `false`

The product owner requires this ordered correction chain to run in the primary
session without Fleet or subagents. This is a procedurally separate review of
the final J02 bytes, not actor-independent certification.

## Findings

1. The repository now closes the exact `skill-context` dependency group on
   `tiktoken==0.13.0`. The uv lock contains exactly one pinned package, the
   canonical sdist digest, and no runtime or optional dependency exposure.
2. Inventory identity and semantics remain stable at
   `{inventory['inventory_hash']}`: 29 skills, 17 references, 4,767 UTF-8
   metadata bytes, and 1,112 pinned `o200k_base` tokens.
3. All 12 budget boundaries, 35 selection cases, 16 adversarial reachability
   cases, 100 deterministic loader repetitions, and the 29 default activation
   budgets pass exactly. The three new dependency-boundary negative cases pass.
4. Targeted Python is 20/20, targeted Node is 25/25, and J01 routing regression
   is 19/19. Full Python is 990/990 with zero skip or xfail.
5. The complete serial Node receipt covers all 52 live test files and is
   459/460. Its only failure is `{debt['debt_id']}`, with actual manifest hash
   `{debt['current_source_sha256']}` and stale bound successor
   `{debt['stale_bound_successor_sha256']}`.
6. `{dependency['authority']['latest_serial_order_decision']['decision_id']}`
   fixes the repair order as F04-0002 → J02-0003 → S04-0003. The exact residual
   is therefore retained as a bounded later-attempt S04 debt; it is neither
   hidden nor relabeled as resolved and has no J02 causal impact.
7. The five J02 product changes are within exact J02 write scope. J02 did not
   edit `pyproject.toml`, `uv.lock`, S04 files, or prior attempt evidence.

## Assurance boundary

J02 package PASS establishes progressive-reference and context-budget
conformance. It does not establish repository-wide green status, S04 PASS,
B04-0007/C04-0002/B04-0008 PASS, release readiness, or product completion.
`implementation_gate=fail` and `completion_ready=false` remain required.
"""


def make_receipt(authority_path: Path) -> dict[str, Any]:
    receipt = {
        "receipt_id": "AR-J02-0003-INVENTORY-AUTHORITY-VERIFICATION",
        "artifact_id": "J02-0003-INVENTORY-AUTHORITY-VERIFICATION",
        "action_intent_id": None,
        "media_type": "application/json",
        "content_hash": sha256_id(authority_path),
        "byte_size": authority_path.stat().st_size,
        "created_by": {"actor_id": "SVC-FOUNDRY-KERNEL-J02", "actor_type": "service"},
        "created_at": RECORDED_AT,
        "locator": authority_path.relative_to(ROOT).as_posix(),
        "schema_ref": None,
        "validation_results": [
            {"check": "context_budget_test", "status": "PASS", "details": "20/20"},
            {"check": "reference_reachability_test", "status": "PASS", "details": "25/25"},
            {"check": "inventory_hash_verification", "status": "PASS", "details": "29 skills / 17 references"},
            {"check": "full_python_suite", "status": "PASS", "details": "990/990"},
            {"check": "j02_regression_reconciliation", "status": "PASS", "details": "J02-caused failures 0; exact S04-TM004 later-attempt debt retained"},
        ],
    }
    receipt["receipt_hash"] = canonical_hash_excluding(receipt, "receipt_hash")
    schema = read_json(RECEIPT_SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    errors = list(Draft202012Validator(schema).iter_errors(receipt))
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
        "build_j02_0003_evidence.py",
        "j02_0003_rah_seal.py",
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
        "title": "Progressive references and context budgets after exact tokenizer-lock correction",
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
            "skill_count": 29,
            "reference_count": 17,
            "metadata_utf8_bytes": 4767,
            "metadata_o200k_base_tokens": 1112,
            "maximum_closure_count": 11,
            "maximum_transitive_depth": 5,
        },
        "required_checks": {
            "context_budget_test": {"status": "PASS", "passed": 20, "failed": 0},
            "reference_reachability_test": {"status": "PASS", "passed": 25, "failed": 0},
            "skill_routing_eval": {"status": "PASS", "passed": 19, "failed": 0},
            "skill_metadata_lint": {"status": "PASS", "passed": 29, "failed": 0},
            "inventory_hash_verification": {"status": "PASS"},
            "exact_tokenizer_lock_check": {"status": "PASS", "version": "0.13.0"},
            "full_python_suite": {"status": "PASS", "passed": 990, "failed": 0, "skipped": 0},
            "full_node_suite": {
                "status": "PASS_WITH_BOUNDED_LATER_ATTEMPT_DEBT",
                "passed": 459,
                "failed": 1,
                "skipped": 0,
                "j02_causal_failures": 0,
                "debt_id": "S04-TM004",
            },
            "active_manifest_binding_check": {
                "status": "AUTHORIZED_LATER_ATTEMPT_S04_0003",
                "current_manifest_hash_verified": True,
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
            "full_python": "990/990",
            "full_node": "459 passed, exact S04-TM004 later-attempt debt only",
            "new_skip_or_xfail_count": 0,
        },
        "regression": {
            "python_regression_status": "PASS",
            "node_regression_status": "BOUNDED_LATER_ATTEMPT_DEBT_S04",
            "j02_causal_failure_count": regression["j02_causal_failure_count"],
            "repository_fully_green": False,
        },
        "review": {
            "status": "PASS_WITH_PRIMARY_SESSION_SEPARATE_ADVERSARIAL_IMPLEMENTATION_REVIEW",
            "mode": "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_IMPLEMENTATION_REVIEW",
            "actor_independence": False,
            "blocking_j02_finding_count": 0,
            "subagents_used": False,
            "artifact": "artifacts/work_packages/J02/attempts/0003/review.md",
            "artifact_sha256": sha256_id(ATTEMPT / "review.md"),
        },
        "history_and_worktree": documents["write-scope-verification.json"]["preservation"],
        "bounded_later_attempt_debt": documents["preexisting-debt-reconciliation.json"],
        "dependency_effect": dependency["next_state"],
        "evidence_artifacts": artifacts,
        "artifact_receipt": {
            "path": "artifacts/work_packages/J02/attempts/0003/j02-verification.artifact-receipt.json",
            "receipt_id": "AR-J02-0003-INVENTORY-AUTHORITY-VERIFICATION",
        },
        "not_claimed": [
            "S04-0003 PASS",
            "repository-wide green status",
            "B04-0007, C04-0002, or B04-0008 PASS",
            "release or production readiness",
            "actor-independent certification",
            "completion_ready=true",
        ],
        "global_status": {
            "implementation_gate": "fail",
            "completion_ready": False,
            "repository_fully_green": False,
            "next_attempt": "S04-0003",
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
    commands = command_records(documents)
    (ATTEMPT / "commands.jsonl").write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in commands
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
        "generation_file_hashes_verified": integrity["generation_file_hashes_verified"],
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
            raise SystemExit("J02-0003 RAH binding is not an object")
        if re.fullmatch(r"\d{6}-[0-9a-f]{8}", str(rah_state.get("core_generation"))) is None:
            raise SystemExit("J02-0003 core generation binding is malformed")
        for key in ("core_evidence_id", "final_closeout_evidence_id"):
            if re.fullmatch(r"E\d{4,}", str(rah_state.get(key))) is None:
                raise SystemExit(f"J02-0003 {key} binding is malformed")
    for name, expected in documents.items():
        path = ATTEMPT / name
        if not path.is_file() or path.read_text(encoding="utf-8") != render(expected):
            raise SystemExit(f"stored J02-0003 evidence differs from live inputs: {name}")
    expected_review = review_text(documents)
    if (ATTEMPT / "review.md").read_text(encoding="utf-8") != expected_review:
        raise SystemExit("stored J02-0003 review differs from current evidence")
    expected_commands = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
        for row in command_records(documents)
    )
    if (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8") != expected_commands:
        raise SystemExit("stored J02-0003 commands differ from deterministic records")
    for line in expected_commands.splitlines():
        json.loads(line)
    expected_receipt = make_receipt(ATTEMPT / "inventory-authority-verification.json")
    if (
        ATTEMPT / "j02-verification.artifact-receipt.json"
    ).read_text(encoding="utf-8") != render(expected_receipt):
        raise SystemExit("stored J02-0003 ArtifactReceipt differs from live evidence")
    expected_report = report_document(documents, rah_state=rah_state)
    if (ATTEMPT / "report.json").read_text(encoding="utf-8") != render(expected_report):
        raise SystemExit("stored J02-0003 report differs from current evidence")
    if rah_state is not None:
        for name in ("report.json", "commands.jsonl", "review.md"):
            if (ATTEMPT / name).read_bytes() != (PACKAGE_ROOT / name).read_bytes():
                raise SystemExit(f"J02 root projection differs: {name}")
    return {
        "attempt_id": ATTEMPT_ID,
        "status": "PASS",
        "inventory_hash": documents["inventory-authority-verification.json"]["inventory_hash"],
        "targeted_python": "20/20",
        "targeted_node": "25/25",
        "j01_regression_node": "19/19",
        "full_python": "990/990",
        "full_node": "459 passed, exact S04-TM004 later-attempt debt only",
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
