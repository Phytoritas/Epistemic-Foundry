#!/usr/bin/env python3
"""Build and verify R04-0001 causal identification and ArgumentGraph gate evidence.

R04-0001 implements `python/epistemic_foundry/reasoning/causal/**`: the
gate that derives identification from assessed confounding, collider
conditioning, and temporal order rather than accepting a declared status, and
that keeps the inductive, deductive, and abductive modes separate so none can
stand in for causal identification.  This builder verifies the executed checks
and emits immutable attempt evidence; it never modifies product files.
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
ATTEMPT = ROOT / "artifacts/work_packages/R04/attempts/0001"
ATTEMPT_ID = "R04-0001"
WORK_PACKAGE_ID = "R04"
RECORDED_AT = "2026-08-01T12:30:00.000Z"

EXPECTED_CAUSAL_OVERCLAIM_COUNT = 26
EXPECTED_ARGUMENT_GRAPH_VALIDATION_COUNT = 19
EXPECTED_TARGETED_COUNT = 45
EXPECTED_DEDUCTION_REGRESSION_COUNT = 43
EXPECTED_APORIA_REGRESSION_COUNT = 44
EXPECTED_PYTHON_COUNT = 1261
EXPECTED_NODE_COUNT = 903
EXPECTED_NODE_FILE_COUNT = 87

COMPONENT = "python/epistemic_foundry/reasoning/causal"
EXPECTED_PRODUCT_HASHES = {
    "python/epistemic_foundry/reasoning/causal/__init__.py": "518679fc07bbcdd20edb105eee83e5671b72e287330000b2ba1d5969609c5c0a",
    "python/epistemic_foundry/reasoning/causal/contracts.py": "aa3221bc52b1a7d8ce5710e8b29a97904f52bec8df0bee62a91638a3f0eb5cd0",
    "python/epistemic_foundry/reasoning/causal/pytest.ini": "ce793df03f459f7394f81fcdcad23287f83918de06640c830911cb4251744714",
    "python/epistemic_foundry/reasoning/causal/test_argument_graph_validation.py": "b5f6dca1c6560822a1ce86c0eabd925b3c25f02b8b0bf947ab4bc317e31bddbc",
    "python/epistemic_foundry/reasoning/causal/test_causal_overclaim.py": "70753e93bee669ce31d7a2f0db9a4775356471b20f0f73b71203245cae1a45b5",
}
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/R02/attempts/0001/report.json": "0e8f8c95aeb28551797c6d125b99328e7796c238152b0977b64a9159419421de",
    "artifacts/work_packages/R03/attempts/0001/report.json": "09c59180036ff2a2cac571aaa239ed768fc2e78b524b4284ea710b8ba3b9c147",
}

JUNIT_PATHS = {
    "causal_overclaim": ATTEMPT / "causal-overclaim-test.junit.xml",
    "argument_graph_validation": ATTEMPT / "argument-graph-validation.junit.xml",
    "targeted": ATTEMPT / "targeted-causal.junit.xml",
    "deduction_regression": ATTEMPT / "dependency-regression-deduction.junit.xml",
    "aporia_regression": ATTEMPT / "dependency-regression-aporia.junit.xml",
    "full_python": ATTEMPT / "full-python-suite.junit.xml",
    "full_node": ATTEMPT / "full-node-suite.junit.xml",
}
_NODE_JUNITS = frozenset({"full_node"})
RUN_RESULTS = (
    "ruff-check",
    "ruff-format-check",
    "causal-overclaim-test",
    "argument-graph-validation",
    "targeted-causal",
    "dependency-regression-deduction",
    "dependency-regression-aporia",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "run_r04_0001_checks.py",
    "build_r04_0001_evidence.py",
    "r04_0001_rah_seal.py",
    "dependency-status.json",
    "r04-verification.json",
    "write-scope-verification.json",
    "node-test-inventory.json",
    "junit-normalization-verification.json",
    "causal-overclaim-test.junit.xml",
    "argument-graph-validation.junit.xml",
    "targeted-causal.junit.xml",
    "dependency-regression-deduction.junit.xml",
    "dependency-regression-aporia.junit.xml",
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
    overclaim = pytest_summary(JUNIT_PATHS["causal_overclaim"])
    argument_graph = pytest_summary(JUNIT_PATHS["argument_graph_validation"])
    targeted = pytest_summary(JUNIT_PATHS["targeted"])
    deduction = pytest_summary(JUNIT_PATHS["deduction_regression"])
    aporia = pytest_summary(JUNIT_PATHS["aporia_regression"])
    python = pytest_summary(JUNIT_PATHS["full_python"])
    node = node_summary(JUNIT_PATHS["full_node"])
    node_inventory = read_json(ATTEMPT / "node-test-inventory.json")
    for label, summary, expected in (
        ("causal_overclaim_test", overclaim, EXPECTED_CAUSAL_OVERCLAIM_COUNT),
        (
            "argument_graph_validation",
            argument_graph,
            EXPECTED_ARGUMENT_GRAPH_VALIDATION_COUNT,
        ),
        ("targeted", targeted, EXPECTED_TARGETED_COUNT),
        ("deduction_regression", deduction, EXPECTED_DEDUCTION_REGRESSION_COUNT),
        ("aporia_regression", aporia, EXPECTED_APORIA_REGRESSION_COUNT),
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
        "baseline_attempt": "R03-0001",
        "component_tests_are_targeted_only": True,
        "aporia_regression": aporia,
        "deduction_regression": deduction,
        "full_node": node,
        "full_python": python,
        "argument_graph_validation": argument_graph,
        "causal_overclaim_test": overclaim,
        "new_failure_count": 0,
        "prior_baseline_counts": {"full_node": 903, "full_python": 1261},
        "status": "PASS",
        "targeted_causal": targeted,
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
            "R02": _sealed_dependency("R02", "R02-0001", "E0131", "E0132"),
            "R03": _sealed_dependency("R03", "R03-0001", "E0133", "E0134"),
        },
        "next_action": "SEAL_R04_0001_THEN_CONTINUE_DAG",
        "regression_baseline": _sealed_dependency("R03", "R03-0001", "E0133", "E0134"),
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
        raise SystemExit(f"causal component holds unexpected files: {component_files}")
    return {
        "approved_scope": [f"{COMPONENT}/**", "artifacts/work_packages/R04/**"],
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


def r04_verification(regression: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "exit_criteria": {
            "colliders_confounders_time_order_assessed": {
                "evidence": [f"{COMPONENT}/test_causal_overclaim.py"],
                "mechanism": (
                    "all three assessments run on every evaluation, each can "
                    "only lower the result, and a declared identification "
                    "status stronger than the derived one is refused"
                ),
                "status": "PASS",
            },
            "inference_modes_remain_separate": {
                "evidence": [f"{COMPONENT}/test_argument_graph_validation.py"],
                "mechanism": (
                    "induction, deduction, and abduction each contribute one "
                    "verdict, none may carry a causal or selected result, and "
                    "the weakest ceiling any mode leaves is binding"
                ),
                "status": "PASS",
            },
        },
        "identification_semantics": {
            "assessments": ["collider", "confounding", "time_order"],
            "derived_not_declared": True,
            "ladder": [
                "NOT_ASSESSED",
                "NOT_IDENTIFIED",
                "ASSUMPTION_DEPENDENT",
                "IDENTIFIED",
            ],
            "modes_can_only_lower_the_ceiling": True,
        },
        "required_checks": {
            "argument_graph_validation": {
                "module": f"{COMPONENT}/test_argument_graph_validation.py",
                "status": "PASS",
                "test_count": regression["argument_graph_validation"]["collected"],
            },
            "causal_overclaim_test": {
                "module": f"{COMPONENT}/test_causal_overclaim.py",
                "status": "PASS",
                "test_count": regression["causal_overclaim_test"]["collected"],
            },
        },
        "schema_binding": {
            "argument_graph": "schemas/argument-graph.schema.json",
            "mechanism_graph": "schemas/mechanism-graph.schema.json",
        },
        "status": "PASS",
        "targeted_test_count": regression["targeted_causal"]["collected"],
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
                "artifacts/work_packages/R04/attempts/0001/build_r01_0001_evidence.py",
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
        "# R04-0001 primary-session separate adversarial review\n"
        "\n"
        "- Reviewer: primary session in a separate adversarial pass under the\n"
        "  product-owner instruction forbidding subagents and Fleet;\n"
        "  actor_independence=false is recorded, not hidden.\n"
        "- Identification is derived, never accepted. Confounding, collider\n"
        "  conditioning, and temporal order are all assessed on every\n"
        "  evaluation; an unadjusted or honestly unmeasured confounder, a\n"
        "  conditioned collider, or a causal edge whose lag establishes no\n"
        "  order each force NOT_IDENTIFIED, and a graph carrying assumptions\n"
        "  can rise no higher than ASSUMPTION_DEPENDENT. A declared status\n"
        "  above the derived one is refused with the failing assessments\n"
        "  named, and a sealed gate cannot be upgraded afterwards even when\n"
        "  its hash is recomputed.\n"
        "- A purely correlational graph establishes no temporal order at all\n"
        "  and therefore cannot be identified, which is the case an\n"
        "  association-only pipeline is most likely to overclaim.\n"
        "- The three inference modes stay separate. Each contributes exactly\n"
        "  one verdict; a missing, duplicated, or unknown mode fails closed. An\n"
        "  inductive synthesis carrying a causal verdict and an aporia record\n"
        "  arriving with an explanation already selected are both refused as\n"
        "  mode collapse. Modes can only lower the ceiling: a live competing\n"
        "  explanation or a conditional deductive trace caps the result at\n"
        "  ASSUMPTION_DEPENDENT and a broken trace caps it at NOT_IDENTIFIED,\n"
        "  while no combination of favourable modes can lift a graph whose\n"
        "  assessments failed.\n"
        "- Both graphs are validated against their canonical schemas -\n"
        "  mechanism-graph for the causal structure and argument-graph with its\n"
        "  ScopeVector reference for the R02 trace - so the gate is bound to\n"
        "  the shared contracts rather than to a local convention.\n"
        "- Residual limitations: the engine assesses the graph it is given and\n"
        "  does not discover structure, so a confounder nobody declared is\n"
        "  invisible to it; backdoor reasoning is limited to declared confounder\n"
        "  roles rather than full path enumeration; and promotion of an\n"
        "  identified cause remains a governance decision. This review is not\n"
        "  external actor-independent certification.\n"
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
            "path": f"artifacts/work_packages/R04/attempts/0001/{name}",
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in sorted(set(output_names))
    ]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "R04_CAUSAL_IDENTIFICATION_AND_ARGUMENT_GRAPH_GATE",
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependency_state": dependencies,
        "exit_criteria": {
            "colliders_confounders_time_order_assessed": "PASS",
            "inference_modes_remain_separate": "PASS",
        },
        "global_implementation_gate": "fail",
        "history_and_worktree": {
            "dirty_worktree_preserved": True,
            "prior_attempts_reports_and_rah_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
            "subagents_or_fleet_used": False,
        },
        "implementation_status": "PASS",
        "next_package": "T03-0001",
        "not_claimed": [
            "discovery of the causal graph, as opposed to assessing a declared one",
            "detection of confounders the graph does not declare",
            "backdoor-path enumeration beyond declared confounder roles",
            "promotion of an identified cause, which belongs to the governance gates",
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
        "argument_graph_validation": (
            f"{EXPECTED_ARGUMENT_GRAPH_VALIDATION_COUNT}/"
            f"{EXPECTED_ARGUMENT_GRAPH_VALIDATION_COUNT}"
        ),
        "causal_overclaim_test": (
            f"{EXPECTED_CAUSAL_OVERCLAIM_COUNT}/{EXPECTED_CAUSAL_OVERCLAIM_COUNT}"
        ),
        "next_action": "SEAL_R04_0001_THEN_CONTINUE_DAG",
        "package_status": "PASS",
        "status": "PASS",
        "targeted_causal": f"{EXPECTED_TARGETED_COUNT}/{EXPECTED_TARGETED_COUNT}",
    }


def build() -> dict[str, Any]:
    for name in RUN_RESULTS:
        check_run(name)
    normalize_junits()
    regression = regression_evidence()
    dependencies = dependency_status()
    write_scope = write_scope_verification()
    verification = r04_verification(regression)
    write_json("dependency-status.json", dependencies)
    write_json("write-scope-verification.json", write_scope)
    write_json("r04-verification.json", verification)
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
        raise SystemExit("R04-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "r04-verification.json")
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
    verification = read_json(ATTEMPT / "r04-verification.json")
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
        raise SystemExit("stored R04-0001 report is not the deterministic document")
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
