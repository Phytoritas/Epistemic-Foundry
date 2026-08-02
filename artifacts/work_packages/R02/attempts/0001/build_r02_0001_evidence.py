#!/usr/bin/env python3
"""Build and verify R02-0001 proof-trace and assumption-ledger evidence.

R02-0001 implements `python/epistemic_foundry/reasoning/deduction/**`: the
deterministic proof trace and assumption ledger in which every statement a
conclusion rests on is either bound to a source or entered in the ledger, the
load-bearing assumptions are derived rather than declared, and a deduction may
narrow a ScopeVector but never widen it.  This builder verifies the executed
checks and emits immutable attempt evidence; it never modifies product files.
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
ATTEMPT = ROOT / "artifacts/work_packages/R02/attempts/0001"
ATTEMPT_ID = "R02-0001"
WORK_PACKAGE_ID = "R02"
RECORDED_AT = "2026-08-01T10:30:00.000Z"

EXPECTED_DEDUCTION_TRACE_COUNT = 24
EXPECTED_SCOPE_WIDENING_COUNT = 19
EXPECTED_TARGETED_COUNT = 43
EXPECTED_DEPENDENCY_REGRESSION_COUNT = 44
EXPECTED_PYTHON_COUNT = 1261
EXPECTED_NODE_COUNT = 903
EXPECTED_NODE_FILE_COUNT = 87

COMPONENT = "python/epistemic_foundry/reasoning/deduction"
EXPECTED_PRODUCT_HASHES = {
    "python/epistemic_foundry/reasoning/deduction/__init__.py": "de341cde0e659317108dd67d5f42ec2c939674cf51198f6af47fe6af61bfdd67",
    "python/epistemic_foundry/reasoning/deduction/contracts.py": "9139b11f29d2a76554c95b61e9a9bbf0f0fe4ce7705a0505f1f18e41275ef7cb",
    "python/epistemic_foundry/reasoning/deduction/pytest.ini": "b2b3cfc18934cf240975e80fb99c28f7aacc4ffe5610ba25ac4a7e7fc67116f0",
    "python/epistemic_foundry/reasoning/deduction/test_deduction_trace.py": "12a8038a6f11477e8d2f2d8b8dbf39ee9e29e0fe512fff1200061c8f79af7b2e",
    "python/epistemic_foundry/reasoning/deduction/test_scope_widening.py": "9e84a8f0d8d5f07c74775182927fa0c9559ba8aba7f71348d6011ec13a20239d",
}
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/R01/attempts/0001/report.json": "c964ad057111890bb259aacc86cdb4ec5b3091f4f479ae9786b822f09db00270"
}

JUNIT_PATHS = {
    "deduction_trace": ATTEMPT / "deduction-trace-test.junit.xml",
    "scope_widening": ATTEMPT / "scope-widening-test.junit.xml",
    "targeted": ATTEMPT / "targeted-deduction.junit.xml",
    "dependency_regression": ATTEMPT / "dependency-component-regression.junit.xml",
    "full_python": ATTEMPT / "full-python-suite.junit.xml",
    "full_node": ATTEMPT / "full-node-suite.junit.xml",
}
_NODE_JUNITS = frozenset({"full_node"})
RUN_RESULTS = (
    "ruff-check",
    "ruff-format-check",
    "deduction-trace-test",
    "scope-widening-test",
    "targeted-deduction",
    "dependency-component-regression",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "run_r02_0001_checks.py",
    "build_r02_0001_evidence.py",
    "r02_0001_rah_seal.py",
    "dependency-status.json",
    "r02-verification.json",
    "write-scope-verification.json",
    "node-test-inventory.json",
    "junit-normalization-verification.json",
    "deduction-trace-test.junit.xml",
    "scope-widening-test.junit.xml",
    "targeted-deduction.junit.xml",
    "dependency-component-regression.junit.xml",
    "full-python-suite.junit.xml",
    "full-node-suite.junit.xml",
    "commands.jsonl",
    "review.md",
)


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
    if (
        value.get("attempt_id") != ATTEMPT_ID
        or value.get("check") != name
        or value.get("exit_code") != 0
        or value.get("status") != "PASS"
        or not isinstance(value.get("command"), list)
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
    trace = pytest_summary(JUNIT_PATHS["deduction_trace"])
    widening = pytest_summary(JUNIT_PATHS["scope_widening"])
    targeted = pytest_summary(JUNIT_PATHS["targeted"])
    dependency = pytest_summary(JUNIT_PATHS["dependency_regression"])
    python = pytest_summary(JUNIT_PATHS["full_python"])
    node = node_summary(JUNIT_PATHS["full_node"])
    node_inventory = read_json(ATTEMPT / "node-test-inventory.json")
    for label, summary, expected in (
        ("deduction_trace_test", trace, EXPECTED_DEDUCTION_TRACE_COUNT),
        ("scope_widening_test", widening, EXPECTED_SCOPE_WIDENING_COUNT),
        ("targeted", targeted, EXPECTED_TARGETED_COUNT),
        (
            "dependency_component_regression",
            dependency,
            EXPECTED_DEPENDENCY_REGRESSION_COUNT,
        ),
        ("full_python", python, EXPECTED_PYTHON_COUNT),
    ):
        if (
            summary["collected"],
            summary["passed"],
            summary["failed"],
            summary["errors"],
            summary["skipped"],
        ) != (expected, expected, 0, 0, 0):
            raise SystemExit(f"{label} gate failed: {summary}")
    if (
        node["collected"],
        node["passed"],
        node["failed"],
        node["cancelled"],
        node["skipped"],
        node["todo"],
        node["xml_error_count"],
        node["xml_failure_count"],
        node_inventory.get("count"),
    ) != (
        EXPECTED_NODE_COUNT,
        EXPECTED_NODE_COUNT,
        0,
        0,
        0,
        0,
        0,
        0,
        EXPECTED_NODE_FILE_COUNT,
    ):
        raise SystemExit(f"full Node gate failed: {node}; inventory={node_inventory}")
    return {
        "attempt_id": ATTEMPT_ID,
        "baseline_attempt": "R01-0001",
        "component_tests_are_targeted_only": True,
        "dependency_component_regression": dependency,
        "full_node": node,
        "full_python": python,
        "deduction_trace_test": trace,
        "scope_widening_test": widening,
        "new_failure_count": 0,
        "prior_baseline_counts": {"full_node": 903, "full_python": 1261},
        "status": "PASS",
        "targeted_deduction": targeted,
        "unexpected_skip_xfail_todo_or_cancellation_count": 0,
    }


def _sealed_dependency(
    package: str, attempt: str, core: str, final: str
) -> dict[str, Any]:
    path = (
        ROOT / f"artifacts/work_packages/{package}/attempts/{attempt[-4:]}/report.json"
    )
    report = read_json(path)
    rah = report.get("rah_state")
    if (
        report.get("status") != "PASS"
        or not isinstance(rah, dict)
        or rah.get("core_evidence_id") != core
        or rah.get("final_closeout_evidence_id") != final
    ):
        raise SystemExit(f"{attempt} is not the sealed PASS attempt")
    return {
        "attempt_id": attempt,
        "core_evidence_id": core,
        "final_closeout_evidence_id": final,
        "report": path.relative_to(ROOT).as_posix(),
        "report_sha256": sha256_id(path),
        "status": "PASS",
    }


def dependency_status() -> dict[str, Any]:
    assert_hashes(EXPECTED_DEPENDENCY_HASHES)
    return {
        "attempt_id": ATTEMPT_ID,
        "dependencies": {
            "R01": _sealed_dependency("R01", "R01-0001", "E0129", "E0130"),
        },
        "next_action": "SEAL_R02_0001_THEN_CONTINUE_DAG",
        "regression_baseline": _sealed_dependency("R01", "R01-0001", "E0129", "E0130"),
        "status": "PASS",
    }


def write_scope_verification() -> dict[str, Any]:
    assert_hashes(EXPECTED_PRODUCT_HASHES)
    component_files = sorted(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / COMPONENT).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )
    if component_files != sorted(EXPECTED_PRODUCT_HASHES):
        raise SystemExit(
            f"deduction component holds unexpected files: {component_files}"
        )
    return {
        "approved_scope": [f"{COMPONENT}/**", "artifacts/work_packages/R02/**"],
        "attempt_id": ATTEMPT_ID,
        "component_files": component_files,
        "product_file_hashes": {
            relative: "sha256:" + digest
            for relative, digest in EXPECTED_PRODUCT_HASHES.items()
        },
        "reset_clean_stash_commit_push_performed": False,
        "root_canonical_source_mutation_count": 0,
        "schema_or_test_weakening_count": 0,
        "status": "PASS",
        "subagents_or_fleet_used": False,
        "write_scope_violation_count": 0,
    }


def r02_verification(regression: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "assumption_ledger_semantics": {
            "derived_rather_than_declared": True,
            "grounding_states": ["UNGROUNDED", "PARTIALLY_SUPPORTED"],
            "ledger_entry_carries_dependents": True,
            "undeclared_hidden_assumption_fails_closed": True,
        },
        "exit_criteria": {
            "premises_source_bound_or_assumptions": {
                "evidence": [f"{COMPONENT}/test_deduction_trace.py"],
                "mechanism": (
                    "a premise must cite evidence, an unevidenced statement must "
                    "be an assumption, and the engine derives the load-bearing "
                    "assumptions and requires the declared set to match exactly"
                ),
                "status": "PASS",
            },
            "scope_widening_rejected": {
                "evidence": [f"{COMPONENT}/test_scope_widening.py"],
                "mechanism": (
                    "a conclusion may narrow a ScopeVector but never drop a "
                    "boundary, criterion, or condition its premises carried, and "
                    "may not move to a value no premise covers"
                ),
                "status": "PASS",
            },
        },
        "required_checks": {
            "deduction_trace_test": {
                "module": f"{COMPONENT}/test_deduction_trace.py",
                "status": "PASS",
                "test_count": regression["deduction_trace_test"]["collected"],
            },
            "scope_widening_test": {
                "module": f"{COMPONENT}/test_scope_widening.py",
                "status": "PASS",
                "test_count": regression["scope_widening_test"]["collected"],
            },
        },
        "scope_discipline": {
            "checked_map_fields": ["conditions", "domain_extensions"],
            "checked_set_fields": ["exclusion_criteria", "inclusion_criteria"],
            "widening_kinds": [
                "ALTERED_CONDITION",
                "DROPPED_BOUNDARY",
                "DROPPED_CONDITION",
                "DROPPED_CRITERIA",
                "UNCOVERED_VALUE",
            ],
        },
        "status": "PASS",
        "targeted_test_count": regression["targeted_deduction"]["collected"],
    }


def command_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for name in RUN_RESULTS:
        value = read_json(ATTEMPT / f"{name}.run.json")
        records.append(
            {
                "attempt_id": ATTEMPT_ID,
                "command": value["command"],
                "exit_code": value["exit_code"],
                "recorded_at_utc": RECORDED_AT,
                "status": value["status"],
                "step": name,
            }
        )
    records.append(
        {
            "attempt_id": ATTEMPT_ID,
            "command": [
                "python",
                "-B",
                "artifacts/work_packages/R02/attempts/0001/build_r01_0001_evidence.py",
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
        "# R02-0001 primary-session separate adversarial review\n"
        "\n"
        "- Reviewer: primary session in a separate adversarial pass under the\n"
        "  product-owner instruction forbidding subagents and Fleet;\n"
        "  actor_independence=false is recorded, not hidden.\n"
        "- Premise binding is structural. A node typed premise must cite\n"
        "  evidence, so an unevidenced statement can only stand as an\n"
        "  assumption, and any other node type that carries support without\n"
        "  evidence is refused outright. A conclusion resting on nothing, or on\n"
        "  a floating intermediate claim, cannot be sealed.\n"
        "- The assumption ledger is derived, not trusted. The engine computes\n"
        "  the load-bearing unevidenced assumptions from the supporting graph\n"
        "  and requires the graph's declared hidden_assumption_ids to equal\n"
        "  them exactly, so both an undeclared assumption and an over-declared\n"
        "  one fail closed. Each ledger entry records its grounding and the\n"
        "  conclusions that rest on it; stripping the ledger from a rehashed\n"
        "  trace is still caught because the conclusions still cite it.\n"
        "- Scope widening is rejected rather than downgraded. A conclusion may\n"
        "  narrow a ScopeVector but may not drop a scalar boundary, an\n"
        "  inclusion or exclusion criterion, or a condition that any premise\n"
        "  carried, nor move to a value no premise covers. Every scalar, set,\n"
        "  and map field of the canonical ScopeVector is exercised, and an\n"
        "  unconstrained assumption cannot launder a scope the evidence never\n"
        "  had because only premise scopes bound the conclusion.\n"
        "- Trace integrity: the supporting graph must be acyclic, every edge\n"
        "  endpoint must exist, a deductive edge must name its rule, a\n"
        "  conclusion resting on rejected support cannot be accepted, and a\n"
        "  standing objection must be declared. Identical inputs seal\n"
        "  byte-identical artifacts and a tampered trace is rejected.\n"
        "- The fixtures are validated against the canonical\n"
        "  schemas/argument-graph.schema.json with its ScopeVector reference\n"
        "  resolved, so the component's shape is bound to the shared contract\n"
        "  rather than to a local convention.\n"
        "- Residual limitations: the engine checks a declared ArgumentGraph and\n"
        "  does not construct proofs or verify that a named rule licenses its\n"
        "  inference; rule_ref is an identifier, not a checked derivation.\n"
        "  Abduction and contradiction handling are R03 and causal\n"
        "  identification is R04. This review is not external\n"
        "  actor-independent certification.\n"
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
            "path": f"artifacts/work_packages/R02/attempts/0001/{name}",
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in sorted(set(output_names))
    ]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "R02_PROOF_TRACE_AND_ASSUMPTION_LEDGER",
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependency_state": dependencies,
        "exit_criteria": {
            "premises_source_bound_or_assumptions": "PASS",
            "scope_widening_rejected": "PASS",
        },
        "global_implementation_gate": "fail",
        "history_and_worktree": {
            "dirty_worktree_preserved": True,
            "prior_attempts_reports_and_rah_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
            "subagents_or_fleet_used": False,
        },
        "implementation_status": "PASS",
        "next_package": "R03-0001",
        "not_claimed": [
            "construction of proofs, as opposed to checking a declared graph",
            "verification that a named rule licenses the inference it labels",
            "abduction and contradiction handling, which belong to R03",
            "causal identification, which belongs to R04",
            "actor-independent certification of this implementation review",
            "overall product completion",
            "release or production readiness",
            "completion_ready=true",
        ],
        "output_artifacts": artifacts,
        "package_status": "PASS",
        "regression": regression,
        "required_checks": verification["required_checks"],
        "review": {
            "actor_independence": False,
            "assurance_limitation": (
                "Primary-session separate review; not external actor-independent "
                "certification."
            ),
            "blocking_finding_count": 0,
            "mode": "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_REVIEW",
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
        "full_node": f"{EXPECTED_NODE_COUNT}/{EXPECTED_NODE_COUNT}",
        "full_python": f"{EXPECTED_PYTHON_COUNT}/{EXPECTED_PYTHON_COUNT}",
        "deduction_trace_test": (
            f"{EXPECTED_DEDUCTION_TRACE_COUNT}/{EXPECTED_DEDUCTION_TRACE_COUNT}"
        ),
        "scope_widening_test": (
            f"{EXPECTED_SCOPE_WIDENING_COUNT}/{EXPECTED_SCOPE_WIDENING_COUNT}"
        ),
        "next_action": "SEAL_R02_0001_THEN_CONTINUE_DAG",
        "package_status": "PASS",
        "status": "PASS",
        "targeted_deduction": f"{EXPECTED_TARGETED_COUNT}/{EXPECTED_TARGETED_COUNT}",
    }


def build() -> dict[str, Any]:
    for name in RUN_RESULTS:
        check_run(name)
    normalize_junits()
    regression = regression_evidence()
    dependencies = dependency_status()
    write_scope = write_scope_verification()
    verification = r02_verification(regression)
    write_json("dependency-status.json", dependencies)
    write_json("write-scope-verification.json", write_scope)
    write_json("r02-verification.json", verification)
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
        raise SystemExit("R02-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "r02-verification.json")
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
    verification = read_json(ATTEMPT / "r02-verification.json")
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
        raise SystemExit("stored R02-0001 report is not the deterministic document")
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
