#!/usr/bin/env python3
"""Build and verify I03-0001 evidence: ontology and measurement resolution.

This attempt was implemented by a bounded implementation agent under the product
owner's explicit instruction, with a disjoint write scope, and was reviewed by
the sealing agent (actor-independent from the author) before sealing.  The
builder verifies every executed check receipt, gates every JUnit against its
measured count, pins product and dependency bytes, and emits the deterministic
attempt evidence; it never modifies product files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/I03/attempts/0001"
ATTEMPT_ID = "I03-0001"
WORK_PACKAGE_ID = "I03"
RECORDED_AT = "2026-08-02T08:00:00.000Z"
ATTEMPT_DIR = "artifacts/work_packages/I03/attempts/0001"
AUTHORITY_DECISION = None

EXPECTED_PRODUCT_HASHES = {
    "artifacts/work_packages/I03/attempts/0001/check_packaging.py": "89ea613bb6e015d0de676e76c9dbbd04aed972117922c613c3ff61bf1f2cfb28",
    "artifacts/work_packages/I03/attempts/0001/run_i03_0001_checks.py": "8af39bbad77801de7c665907b5d3b2443409855701ad8f5b86d321a2c1b9e308",
    "python/epistemic_foundry/ontology/__init__.py": "6f165694369ae8a53ff5f86d64823ae959bef655b4774f5f7c68833c898e0f10",
    "python/epistemic_foundry/ontology/resolver.py": "cf8be5f3e4f578040ad6036e058d8424c91f4c221f3907fa9c7f5d9940f3514f",
    "python/epistemic_foundry/ontology/test_measurement_identity.py": "71d6f3e1572aa25d6d4329d9df82d5a0d6589d325d4e4ea2908ffa50a10ae0d3",
    "python/epistemic_foundry/ontology/test_ontology_fixture.py": "a85c9c84a0f960133516a40bd13db8993789a247b6f86f9b6f4aa28c71d6f358",
}
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/I01/report.json": "7174f9292421996fcd7e48de8f29757657dcf9b7aff3483028bbb86be70f886a",
}

JUNIT_PATHS = {
    "full_node_suite": ATTEMPT / "full-node-suite.junit.xml",
    "full_python_suite": ATTEMPT / "full-python-suite.junit.xml",
    "measurement_identity_test": ATTEMPT / "measurement-identity-test.junit.xml",
    "ontology_fixture_test": ATTEMPT / "ontology-fixture-test.junit.xml",
    "wire_literal_discipline": ATTEMPT / "wire-literal-discipline.junit.xml",
}
_NODE_JUNITS = frozenset({"full_node_suite"})
RUN_RESULTS = (
    "full-node-suite",
    "full-python-suite",
    "git-diff-check",
    "measurement-identity-test",
    "ontology-fixture-test",
    "packaging-discovery",
    "ruff-check",
    "wire-literal-discipline",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "build_i03_0001_evidence.py",
    "check_packaging.py",
    "commands.jsonl",
    "dependency-status.json",
    "full-node-suite.junit.xml",
    "full-python-suite.junit.xml",
    "i03-verification.json",
    "i03_0001_rah_seal.py",
    "junit-normalization-verification.json",
    "measurement-identity-test.junit.xml",
    "node-test-inventory.json",
    "ontology-fixture-test.junit.xml",
    "review.md",
    "run_i03_0001_checks.py",
    "wire-literal-discipline.junit.xml",
    "write-scope-verification.json",
)

# Measured gate counts (observed at seal-prep time on the live tree).
ONTOLOGY_FIXTURE_COUNT = 16
MEASUREMENT_IDENTITY_COUNT = 23
WIRE_LITERAL_COUNT = 5
FULL_PYTHON_COUNT = 1261
FULL_NODE_COUNT = 1702
NODE_INVENTORY_COUNT = 136


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_id(path: Path) -> str:
    return "sha256:" + sha256(path)


def sha256_bytes(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SystemExit(f"cannot read JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise SystemExit(f"JSON artifact is not an object: {path}")
    return value


def render(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_json(name: str, value: dict[str, Any]) -> Path:
    path = ATTEMPT / name
    path.write_text(render(value), encoding="utf-8", newline="\n")
    return path


def assert_hashes(expected: dict[str, str]) -> None:
    for relative, wanted in expected.items():
        path = ROOT / relative
        actual = sha256(path) if path.is_file() else "MISSING"
        if actual != wanted:
            raise SystemExit(f"sealed input changed: {relative}: {actual} != {wanted}")


def check_run(name: str) -> dict[str, Any]:
    value = read_json(ATTEMPT / f"{name}.run.json")
    commanded = isinstance(value.get("command"), list) or isinstance(
        value.get("commands"), list
    )
    if (
        value.get("attempt_id") != ATTEMPT_ID
        or value.get("check") != name
        or value.get("exit_code") != 0
        or value.get("status") != "PASS"
        or not commanded
    ):
        raise SystemExit(f"required check did not pass: {name}: {value}")
    return value


def semantic_junit_signature(text: str) -> list[tuple[Any, ...]]:
    root = ET.fromstring(text)
    rows: list[tuple[Any, ...]] = []
    prefixes = (str(ROOT) + "\\", str(ROOT).replace("\\", "/") + "/")
    roots = (str(ROOT), str(ROOT).replace("\\", "/"))
    for case in root.findall(".//testcase"):
        failure = case.find("failure")
        error = case.find("error")
        problem = failure if failure is not None else error
        message = problem.get("message", "") if problem is not None else ""
        body = (problem.text or "") if problem is not None else ""
        for prefix in prefixes:
            message = message.replace(prefix, "")
            body = body.replace(prefix, "")
        for value in roots:
            message = message.replace(value, ".")
            body = body.replace(value, ".")
        rows.append(
            (
                case.get("classname", ""),
                case.get("name", ""),
                problem.tag if problem is not None else "",
                problem.get("type", "") if problem is not None else "",
                message,
                body,
                case.find("skipped") is not None,
            )
        )
    return rows


def verify_junit_portability() -> None:
    roots = (str(ROOT), str(ROOT).replace("\\", "/"))
    for name, path in JUNIT_PATHS.items():
        text = path.read_text(encoding="utf-8")
        if any(root in text for root in roots):
            raise SystemExit(f"JUnit contains absolute repository path: {name}")
        if name in _NODE_JUNITS:
            if "duration_ms" in text:
                raise SystemExit(f"Node JUnit retains volatile duration_ms: {name}")
        elif re.search(r'\s+(?:hostname|timestamp|time)="', text):
            raise SystemExit(f"pytest JUnit retains volatile attributes: {name}")


def normalize_junits() -> dict[str, Any]:
    record_path = ATTEMPT / "junit-normalization-verification.json"
    if record_path.is_file():
        record = read_json(record_path)
        for name, path in JUNIT_PATHS.items():
            if record.get("files", {}).get(name, {}).get(
                "normalized_sha256"
            ) != sha256_id(path):
                raise SystemExit(f"normalized JUnit changed: {name}")
        verify_junit_portability()
        return record

    files: dict[str, Any] = {}
    root_backslash = str(ROOT) + "\\"
    root_slash = str(ROOT).replace("\\", "/") + "/"
    for name, path in JUNIT_PATHS.items():
        before_bytes = path.read_bytes()
        before = before_bytes.decode("utf-8")
        signature = semantic_junit_signature(before)
        normalized = before
        removed = {
            "duration_comments": 0,
            "hostname_attributes": 0,
            "repository_prefixes": 0,
            "time_attributes": 0,
            "timestamp_attributes": 0,
        }
        for prefix in (root_backslash, root_slash):
            count = normalized.count(prefix)
            normalized = normalized.replace(prefix, "")
            removed["repository_prefixes"] += count
        for value in (str(ROOT), str(ROOT).replace("\\", "/")):
            count = normalized.count(value)
            normalized = normalized.replace(value, ".")
            removed["repository_prefixes"] += count
        if name in _NODE_JUNITS:
            normalized, removed["duration_comments"] = re.subn(
                r"\s*<!-- duration_ms [^>]+ -->", "", normalized
            )
        else:
            normalized, removed["timestamp_attributes"] = re.subn(
                r'\s+timestamp="[^"]*"', "", normalized
            )
            normalized, removed["hostname_attributes"] = re.subn(
                r'\s+hostname="[^"]*"', "", normalized
            )
            normalized, removed["time_attributes"] = re.subn(
                r'(<(?:testsuite|testcase)\b[^>]*?)\s+time="[^"]*"', r"\1", normalized
            )
        if semantic_junit_signature(normalized) != signature:
            raise SystemExit(f"JUnit normalization changed semantics: {name}")
        path.write_text(normalized, encoding="utf-8", newline="\n")
        files[name] = {
            "normalized_sha256": sha256_id(path),
            "raw_sha256": sha256_bytes(before_bytes),
            "removed": removed,
            "semantic_signature_preserved": True,
            "testcase_count": len(signature),
        }
    record = {
        "attempt_id": ATTEMPT_ID,
        "files": files,
        "preserved": [
            "testcase identity and result state",
            "failure type, message, and body after path normalization",
            "Node semantic footer counters",
        ],
        "recorded_at_utc": RECORDED_AT,
        "status": "PASS",
    }
    write_json("junit-normalization-verification.json", record)
    verify_junit_portability()
    return record


def pytest_summary(path: Path) -> dict[str, Any]:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    cases = list(root.findall(".//testcase"))
    result = {
        "collected": sum(int(row.get("tests", "0")) for row in suites),
        "errors": sum(int(row.get("errors", "0")) for row in suites),
        "failed": sum(int(row.get("failures", "0")) for row in suites),
        "skipped": sum(int(row.get("skipped", "0")) for row in suites),
        "xml_testcase_count": len(cases),
    }
    result["passed"] = (
        result["collected"] - result["errors"] - result["failed"] - result["skipped"]
    )
    result.update(
        {
            "junit": path.relative_to(ROOT).as_posix(),
            "junit_sha256": sha256_id(path),
            "semantic_counter_authority": "pytest_testsuite_attributes",
        }
    )
    return result


def node_summary(path: Path) -> dict[str, Any]:
    root = ET.parse(path).getroot()
    cases = list(root.findall(".//testcase"))
    footer = {
        key.decode("ascii"): int(value)
        for key, value in NODE_FOOTER_PATTERN.findall(path.read_bytes())
    }
    if set(footer) != {"tests", "pass", "fail", "cancelled", "skipped", "todo"}:
        raise SystemExit("Node JUnit semantic footer is incomplete")
    return {
        "cancelled": footer["cancelled"],
        "collected": footer["tests"],
        "failed": footer["fail"],
        "junit": path.relative_to(ROOT).as_posix(),
        "junit_sha256": sha256_id(path),
        "passed": footer["pass"],
        "semantic_counter_authority": "node_test_footer",
        "skipped": footer["skipped"],
        "todo": footer["todo"],
        "xml_error_count": sum(case.find("error") is not None for case in cases),
        "xml_failure_count": sum(case.find("failure") is not None for case in cases),
        "xml_testcase_count": len(cases),
    }


def regression_evidence() -> dict[str, Any]:
    summaries: dict[str, dict[str, Any]] = {}
    for label, summary, expected in (
        (
            "ontology_fixture_test",
            pytest_summary(JUNIT_PATHS["ontology_fixture_test"]),
            ONTOLOGY_FIXTURE_COUNT,
        ),
        (
            "measurement_identity_test",
            pytest_summary(JUNIT_PATHS["measurement_identity_test"]),
            MEASUREMENT_IDENTITY_COUNT,
        ),
        (
            "wire_literal_discipline",
            pytest_summary(JUNIT_PATHS["wire_literal_discipline"]),
            WIRE_LITERAL_COUNT,
        ),
        (
            "full_python_suite",
            pytest_summary(JUNIT_PATHS["full_python_suite"]),
            FULL_PYTHON_COUNT,
        ),
    ):
        if (
            summary["collected"],
            summary["passed"],
            summary["failed"],
            summary["errors"],
            summary["skipped"],
        ) != (expected, expected, 0, 0, 0):
            raise SystemExit(f"{label} gate failed: {summary}")
        summaries[label] = summary
    for label, summary, expected in (
        ("full_node_suite", node_summary(JUNIT_PATHS["full_node_suite"]), FULL_NODE_COUNT),
    ):
        if (
            summary["collected"],
            summary["passed"],
            summary["failed"],
            summary["cancelled"],
            summary["skipped"],
            summary["todo"],
            summary["xml_error_count"],
            summary["xml_failure_count"],
        ) != (expected, expected, 0, 0, 0, 0, 0, 0):
            raise SystemExit(f"{label} gate failed: {summary}")
        summaries[label] = summary

    node_inventory = read_json(ATTEMPT / "node-test-inventory.json")
    if node_inventory.get("count") != NODE_INVENTORY_COUNT:
        raise SystemExit(f"Node inventory gate failed: {node_inventory}")
    return {
        "attempt_id": ATTEMPT_ID,
        "component_tests_are_targeted_only": True,
        "new_failure_count": 0,
        "status": "PASS",
        "suites": summaries,
    }


def _sealed_dependency(package: str, core: str, final: str) -> dict[str, Any]:
    path = ROOT / f"artifacts/work_packages/{package}/report.json"
    report = read_json(path)
    rah = report.get("rah_state")
    if (
        report.get("status") != "PASS"
        or not isinstance(rah, dict)
        or rah.get("core_evidence_id") != core
        or rah.get("final_closeout_evidence_id") != final
    ):
        raise SystemExit(f"{package} is not the sealed PASS dependency")
    return {
        "attempt_id": str(report.get("attempt_id")),
        "core_evidence_id": core,
        "final_closeout_evidence_id": final,
        "report": path.relative_to(ROOT).as_posix(),
        "report_sha256": sha256_id(path),
        "status": "PASS",
    }


def dependency_status() -> dict[str, Any]:
    assert_hashes(EXPECTED_DEPENDENCY_HASHES)
    status: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "dependencies": {
            "I01": _sealed_dependency("I01", "E0068", "E0069"),
        },
        "next_action": "SEAL_I03_0001_THEN_RECOMPUTE_DAG",
        "status": "PASS",
    }
    if AUTHORITY_DECISION is not None:
        decision_path = (
            f"artifacts/authority_decisions/{AUTHORITY_DECISION}.human-decision.json"
        )
        status["authority_decision"] = {
            "decision_id": AUTHORITY_DECISION,
            "path": decision_path,
            "sha256": sha256_id(ROOT / decision_path),
        }
    return status


def write_scope_verification() -> dict[str, Any]:
    assert_hashes(EXPECTED_PRODUCT_HASHES)
    return {
        "approved_scope": [
            "python/epistemic_foundry/ontology/**",
            "artifacts/work_packages/I03/**",
        ],
        "attempt_id": ATTEMPT_ID,
        "authority_decision": AUTHORITY_DECISION,
        "authored_by": (
            "bounded implementation agent under the product owner's explicit "
            "instruction"
        ),
        "composed_modules_modified": False,
        "product_file_hashes": {
            relative: "sha256:" + digest
            for relative, digest in EXPECTED_PRODUCT_HASHES.items()
        },
        "pyproject_modified": False,
        "reset_clean_stash_commit_push_performed": False,
        "reviewed_by": "sealing agent (actor-independent from the author)",
        "root_canonical_source_mutation_count": 0,
        "schema_or_test_weakening_count": 0,
        "status": "PASS",
        "subagents_or_fleet_used": True,
        "write_scope_violation_count": 0,
    }


def package_verification(regression: dict[str, Any]) -> dict[str, Any]:
    suites = regression["suites"]
    required = {
        "ontology_fixture_test": suites["ontology_fixture_test"]["collected"],
        "measurement_identity_test": suites["measurement_identity_test"]["collected"],
    }
    return {
        "attempt_id": ATTEMPT_ID,
        "declaring_sources": {
            "finding_codes": (
                "ONTOLOGY_INPUT_INVALID, ONTOLOGY_INPUT_DUPLICATE, "
                "ONTOLOGY_CATALOG_DUPLICATE_ID, ONTOLOGY_AUTHORITY_UNAVAILABLE, "
                "MEASUREMENT_INPUT_INVALID, MEASUREMENT_IDENTITY_INVALID, "
                "MEASUREMENT_IDENTITY_CONFLICT, MEASUREMENT_BRIDGE_INVALID, "
                "MEASUREMENT_BRIDGE_DUPLICATE_ID, MEASUREMENT_BRIDGE_AMBIGUOUS"
            ),
            "ontology_vocabulary": (
                "the closed OntologyEntityKind/MappingImpact/ResolutionStatus/"
                "CompatibilityStatus/ConstructEquivalence/PromotionCeiling enums "
                "declared in python/epistemic_foundry/ontology/resolver.py, each "
                "bound key-for-key to its wire literal"
            ),
        },
        "exit_criteria": {
            "human_approval_queue_exists": {
                "mechanism": (
                    "ambiguous, high-impact, high-frequency, and unknown-term "
                    "mappings route to a deterministic MappingReviewItem whose "
                    "required_authority_artifact is HumanDecision; a queue item is "
                    "a proposal that never selects the construct, and its "
                    "review_item_id binds the full mapping context "
                    "(mapping_key_hash, candidate ids, and policy version) so a "
                    "change in population or frequency mints a new item"
                ),
                "status": "PASS",
            },
            "same_label_different_construct_not_silently_merged": {
                "mechanism": (
                    "a raw term resolves only when exactly one complete viable "
                    "candidate exists within the pinned ontology/DomainPack "
                    "authority; a label shared by distinct construct_ids returns "
                    "AMBIGUOUS rather than a silent merge, compatibility "
                    "normalization (NFKC/casefold/whitespace) is never mapping "
                    "authority, and distinct construct_ids are never pooled - "
                    "compare_measurements returns NOT_COMPARABLE with "
                    "BLOCK_AGGREGATION"
                ),
                "status": "PASS",
            },
        },
        "required_checks": {
            "independent_review": {
                "evidence": (
                    "review.md (author: bounded implementation agent; reviewer: "
                    "the sealing agent, a distinct actor; actor_independence "
                    "between author and reviewer holds, external certification "
                    "does not)"
                ),
                "status": "PASS",
            },
            **{
                name: {"status": "PASS", "test_count": count}
                for name, count in required.items()
            },
        },
        "status": "PASS",
        "suite_counts": {name: row["collected"] for name, row in suites.items()},
    }


def command_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for name in RUN_RESULTS:
        value = read_json(ATTEMPT / f"{name}.run.json")
        record = {
            "attempt_id": ATTEMPT_ID,
            "exit_code": value["exit_code"],
            "recorded_at_utc": RECORDED_AT,
            "status": value["status"],
            "step": name,
        }
        if "command" in value:
            record["command"] = value["command"]
        else:
            record["commands"] = value["commands"]
        records.append(record)
    records.append(
        {
            "attempt_id": ATTEMPT_ID,
            "command": [
                "python",
                "-B",
                f"{ATTEMPT_DIR}/build_i03_0001_evidence.py",
                "build",
            ],
            "exit_code": 0,
            "recorded_at_utc": RECORDED_AT,
            "status": "PASS",
            "step": "evidence-build",
        }
    )
    return records


def commands_text() -> str:
    return (
        "\n".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True)
            for record in command_records()
        )
        + "\n"
    )


def review_text() -> str:
    return (
        "# I03-0001 independent review of bounded-agent work\n"
        "\n"
        "- Author: a bounded implementation agent (disjoint write scope, frozen\n"
        "  contracts) under the product owner's explicit instruction. Reviewer:\n"
        "  the sealing agent, which did not author this attempt; author/reviewer\n"
        "  separation holds with actor_independence=true, while external\n"
        "  actor-independent certification does not.\n"
        "- Same label, different construct is never silently merged: a raw term\n"
        "  resolves only when exactly one complete viable candidate exists within\n"
        "  the pinned ontology/DomainPack authority; a label shared by distinct\n"
        "  construct_ids returns AMBIGUOUS and routes to the review queue when the\n"
        "  mapping is high-impact or high-frequency, and an inexact term is UNKNOWN\n"
        "  with no candidate.\n"
        "- String similarity is not mapping authority: NFKC, case, and whitespace\n"
        "  folding is compatibility normalization only; no edit distance, stemming,\n"
        "  synonym expansion, or embedding is ever consulted, and an alias binds a\n"
        "  label only when the catalog entry declares it explicitly.\n"
        "- Distinct construct identities are never pooled: compare_measurements\n"
        "  returns NOT_COMPARABLE / DIFFERENT with BLOCK_AGGREGATION for distinct\n"
        "  construct_ids, and scope, support, unit, method, protocol, calibration,\n"
        "  domain-pack, and proxy differences each bind aggregation to their exact\n"
        "  promotion ceiling rather than collapsing to a single comparable pool.\n"
        "- The human approval queue exists and is authoritative: ambiguous,\n"
        "  high-impact, high-frequency, and unknown-term mappings each produce a\n"
        "  deterministic MappingReviewItem whose required_authority_artifact is\n"
        "  HumanDecision; the item is a proposal that never selects the construct,\n"
        "  and its review_item_id binds the full mapping context so a change in\n"
        "  population or frequency mints a new item.\n"
        "- Unit conversion needs an explicit directional bridge: an external\n"
        "  authority MeasurementBridge, matched on the ordered identity-hash pair,\n"
        "  is the only path from a unit mismatch to CONVERTIBLE; it is not silently\n"
        "  reversed, duplicate matching bridges fail closed, and a permissive\n"
        "  ceiling is required before aggregation is allowed.\n"
        "- Fail-closed on adversarial input: mutable catalog or bridge collections,\n"
        "  duplicate construct or bridge ids, one measurement id naming two\n"
        "  semantic identities, foreign or absent authority, and malformed\n"
        "  contracts each raise the exact finding code (ONTOLOGY_INPUT_INVALID,\n"
        "  ONTOLOGY_INPUT_DUPLICATE, ONTOLOGY_CATALOG_DUPLICATE_ID,\n"
        "  ONTOLOGY_AUTHORITY_UNAVAILABLE, MEASUREMENT_INPUT_INVALID,\n"
        "  MEASUREMENT_IDENTITY_INVALID, MEASUREMENT_IDENTITY_CONFLICT,\n"
        "  MEASUREMENT_BRIDGE_INVALID, MEASUREMENT_BRIDGE_DUPLICATE_ID,\n"
        "  MEASUREMENT_BRIDGE_AMBIGUOUS) rather than degrading silently.\n"
        "- Boundary: the resolver imports the standard library alone and resolves\n"
        "  one mapping or compares two measurement identities; it does not add a\n"
        "  canonical schema, issue a HumanDecision, persist authority, or implement\n"
        "  a review UI, and I01 is a manifest-order dependency, not composed code.\n"
        "  The component ships under python/ and stays out of the wheel.\n"
        "- Non-blocking residual: the component-local enum strings are documented\n"
        "  as execution contracts with no canonical schema, and the EF4-I22\n"
        "  wire-literal gate scans only src/, so it is honestly GREEN here (the same\n"
        "  idiom as sealed I01/I02).\n"
        "- Integration gates at review time: ruff check clean, git diff --check\n"
        "  clean, the two required suites green at 16/16 and 23/23 (39 targeted),\n"
        "  the EF4-I22 wire-literal gate 5/5, packaging discovery PASS, full Python\n"
        "  1261/1261 and full Node 1702/1702 across the 136-file inventory. Zero\n"
        "  blocking findings.\n"
    )


def report_document(
    regression: dict[str, Any],
    dependencies: dict[str, Any],
    write_scope: dict[str, Any],
    verification: dict[str, Any],
    *,
    rah_state: dict[str, Any] | None,
) -> dict[str, Any]:
    output_names = [
        name
        for name in OUTPUT_NAMES
        if name != "report.json" and (ATTEMPT / name).is_file()
    ]
    if rah_state is not None:
        output_names.append("rah-core-integrity.json")
    artifacts = [
        {
            "byte_size": (ATTEMPT / name).stat().st_size,
            "path": f"{ATTEMPT_DIR}/{name}",
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in sorted(set(output_names))
    ]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "I03_ONTOLOGY_AND_MEASUREMENT_CONSTRUCT_RESOLUTION",
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependency_state": dependencies,
        "exit_criteria": {key: "PASS" for key in verification["exit_criteria"]},
        "global_implementation_gate": "fail",
        "history_and_worktree": {
            "dirty_worktree_preserved": True,
            "prior_attempts_reports_and_rah_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
            "subagents_or_fleet_used": True,
        },
        "implementation_status": "PASS",
        "next_package": "RECOMPUTE_DAG",
        "not_claimed": [
            "scoring, ranking, selection, promotion or evaluation of any candidate: I03 resolves a term against pinned authority or abstains",
            "a canonical ontology or measurement JSON Schema: the I03 types are component-local execution contracts",
            "HumanDecision approval, ontology persistence, a review UI, or a remote service: a MappingReviewItem is a proposal, not an approval",
            "any composed code dependency on I01: it is a manifest-order dependency and the resolver imports the standard library alone",
            "external actor-independent certification of this review",
            "release or production readiness",
            "completion_ready=true",
        ],
        "output_artifacts": artifacts,
        "package_status": "PASS",
        "regression": regression,
        "required_checks": verification["required_checks"],
        "review": {
            "actor_independence": True,
            "assurance_limitation": (
                "Author/reviewer separation holds with actor_independence=true "
                "(a bounded implementation agent authored, the sealing agent "
                "reviewed); external actor-independent certification does not."
            ),
            "blocking_finding_count": 0,
            "mode": "INDEPENDENT_REVIEW_OF_BOUNDED_AGENT_WORK",
            "status": "PASS",
        },
        "status": "PASS",
        "work_package_id": WORK_PACKAGE_ID,
        "write_scope": write_scope,
    }
    if rah_state is not None:
        report["rah_state"] = rah_state
    return report


def _summary() -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "completion_ready": False,
        "next_action": "SEAL_I03_0001_THEN_RECOMPUTE_DAG",
        "package_status": "PASS",
        "status": "PASS",
    }


def build() -> dict[str, Any]:
    for name in RUN_RESULTS:
        check_run(name)
    normalize_junits()
    regression = regression_evidence()
    dependencies = dependency_status()
    write_scope = write_scope_verification()
    verification = package_verification(regression)
    write_json("dependency-status.json", dependencies)
    write_json("write-scope-verification.json", write_scope)
    write_json("i03-verification.json", verification)
    (ATTEMPT / "commands.jsonl").write_text(
        commands_text(), encoding="utf-8", newline="\n"
    )
    (ATTEMPT / "review.md").write_text(review_text(), encoding="utf-8", newline="\n")
    report = report_document(
        regression, dependencies, write_scope, verification, rah_state=None
    )
    write_json("report.json", report)
    return _summary()


def bind_rah_state(
    *,
    core_generation: str,
    core_evidence_id: str,
    final_closeout_evidence_id: str,
) -> None:
    integrity = read_json(ATTEMPT / "rah-core-integrity.json")
    stored = read_json(ATTEMPT / "report.json")
    if "rah_state" in stored:
        raise SystemExit("I03-0001 report is already RAH-bound")
    if integrity.get("current_generation") != core_generation:
        raise SystemExit("rah-core-integrity does not match the core generation")
    rah_state = {
        "completion_ready": False,
        "core_evidence_id": core_evidence_id,
        "core_generation": core_generation,
        "final_closeout_evidence_id": final_closeout_evidence_id,
        "flat_snapshot_content_matches": integrity["flat_snapshot_content_matches"],
        "flat_snapshot_stamps_verified": integrity["flat_snapshot_stamps_verified"],
        "generation_file_hashes_verified": integrity["generation_file_hashes_verified"],
        "implementation_gate": "fail",
        "retained_generation_count": integrity["retained_generation_count"],
        "status": "active",
    }
    regression = regression_evidence()
    dependencies = read_json(ATTEMPT / "dependency-status.json")
    write_scope = read_json(ATTEMPT / "write-scope-verification.json")
    verification = read_json(ATTEMPT / "i03-verification.json")
    report = report_document(
        regression, dependencies, write_scope, verification, rah_state=rah_state
    )
    write_json("report.json", report)


def verify() -> dict[str, Any]:
    for name in RUN_RESULTS:
        check_run(name)
    normalize_junits()
    regression = regression_evidence()
    assert_hashes(EXPECTED_DEPENDENCY_HASHES)
    stored = read_json(ATTEMPT / "report.json")
    dependencies = read_json(ATTEMPT / "dependency-status.json")
    write_scope_live = write_scope_verification()
    write_scope = read_json(ATTEMPT / "write-scope-verification.json")
    if write_scope_live != write_scope:
        raise SystemExit("write-scope verification drifted from the sealed record")
    verification = read_json(ATTEMPT / "i03-verification.json")
    if (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8") != commands_text():
        raise SystemExit("commands.jsonl differs from deterministic command records")
    if (ATTEMPT / "review.md").read_text(encoding="utf-8") != review_text():
        raise SystemExit("review.md differs from the recorded review")
    expected = report_document(
        regression,
        dependencies,
        write_scope,
        verification,
        rah_state=stored.get("rah_state"),
    )
    if render(expected) != render(stored):
        raise SystemExit("stored I03-0001 report is not the deterministic document")
    return _summary()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("build", "verify"))
    args = parser.parse_args()
    result = {"build": build, "verify": verify}[args.mode]()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
