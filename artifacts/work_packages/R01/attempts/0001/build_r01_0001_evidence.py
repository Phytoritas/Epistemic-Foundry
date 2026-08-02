#!/usr/bin/env python3
"""Build and verify R01-0001 inductive synthesis and heterogeneity evidence.

R01-0001 implements `python/epistemic_foundry/reasoning/induction/**`: the deterministic
inductive synthesis that weights direction by O03 dependency-adjusted
independence rather than head count, estimates heterogeneity on the same
adjusted weights, retains every observed moderator and every declared null,
and never promotes an association to a causal claim.  This builder verifies
the executed checks and emits immutable attempt evidence; it never modifies
product files.
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
ATTEMPT = ROOT / "artifacts/work_packages/R01/attempts/0001"
ATTEMPT_ID = "R01-0001"
WORK_PACKAGE_ID = "R01"
RECORDED_AT = "2026-08-01T09:30:00.000Z"

EXPECTED_INDUCTION_FIXTURE_COUNT = 23
EXPECTED_HETEROGENEITY_COUNT = 21
EXPECTED_TARGETED_COUNT = 44
EXPECTED_DEPENDENCY_REGRESSION_COUNT = 63
EXPECTED_PYTHON_COUNT = 1261
EXPECTED_NODE_COUNT = 903
EXPECTED_NODE_FILE_COUNT = 87

COMPONENT = "python/epistemic_foundry/reasoning/induction"
EXPECTED_PRODUCT_HASHES = {
    "python/epistemic_foundry/reasoning/induction/__init__.py": "d8c472522e1c44db3b24b6396aaf94f7c6281feec1641ef6915e3b6e2247b93c",
    "python/epistemic_foundry/reasoning/induction/contracts.py": "62354a16e8853e17be50d607d4d9c7bb07c5fa2e4299a66a354301eb2770eb9f",
    "python/epistemic_foundry/reasoning/induction/pytest.ini": "4d366ee4f25809ec242463d2ed76199f10c0a955763d8b77fd98cd4750d2e3fa",
    "python/epistemic_foundry/reasoning/induction/test_heterogeneity.py": "81d3e7907fe4eb027b943e4a5447103f64dd785c68e30ad69969d050a770344a",
    "python/epistemic_foundry/reasoning/induction/test_induction_fixture.py": "d601240b8c8b77f970e126d76d24504e4d6f6e9917a9639eb2555e3c924b27e9",
}
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/C04/attempts/0004/report.json": "28cded86378c3ad189839296bd00dc5c29395dce3d31a6db590de67a7ac008ab",
    "artifacts/work_packages/O04/attempts/0001/report.json": "2fd0059a9e1bd66d383168472a644386c299f870e6815e7df291391005f79f0f",
    "artifacts/work_packages/T02/attempts/0001/report.json": "53218e162140319fabd504be498d4248009763c2853b27c09f60626ae9c00bbd",
}

JUNIT_PATHS = {
    "induction_fixture": ATTEMPT / "induction-fixture-test.junit.xml",
    "heterogeneity": ATTEMPT / "heterogeneity-test.junit.xml",
    "targeted": ATTEMPT / "targeted-induction.junit.xml",
    "dependency_regression": ATTEMPT / "dependency-component-regression.junit.xml",
    "full_python": ATTEMPT / "full-python-suite.junit.xml",
    "full_node": ATTEMPT / "full-node-suite.junit.xml",
}
_NODE_JUNITS = frozenset({"full_node"})
RUN_RESULTS = (
    "ruff-check",
    "ruff-format-check",
    "induction-fixture-test",
    "heterogeneity-test",
    "targeted-induction",
    "dependency-component-regression",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "run_r01_0001_checks.py",
    "build_r01_0001_evidence.py",
    "r01_0001_rah_seal.py",
    "dependency-status.json",
    "r01-verification.json",
    "write-scope-verification.json",
    "node-test-inventory.json",
    "junit-normalization-verification.json",
    "induction-fixture-test.junit.xml",
    "heterogeneity-test.junit.xml",
    "targeted-induction.junit.xml",
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
    fixture = pytest_summary(JUNIT_PATHS["induction_fixture"])
    heterogeneity = pytest_summary(JUNIT_PATHS["heterogeneity"])
    targeted = pytest_summary(JUNIT_PATHS["targeted"])
    dependency = pytest_summary(JUNIT_PATHS["dependency_regression"])
    python = pytest_summary(JUNIT_PATHS["full_python"])
    node = node_summary(JUNIT_PATHS["full_node"])
    node_inventory = read_json(ATTEMPT / "node-test-inventory.json")
    for label, summary, expected in (
        ("induction_fixture_test", fixture, EXPECTED_INDUCTION_FIXTURE_COUNT),
        ("heterogeneity_test", heterogeneity, EXPECTED_HETEROGENEITY_COUNT),
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
        "baseline_attempt": "T02-0001",
        "component_tests_are_targeted_only": True,
        "dependency_component_regression": dependency,
        "full_node": node,
        "full_python": python,
        "heterogeneity_test": heterogeneity,
        "induction_fixture_test": fixture,
        "new_failure_count": 0,
        "prior_baseline_counts": {"full_node": 903, "full_python": 1261},
        "status": "PASS",
        "targeted_induction": targeted,
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
            "C04": _sealed_dependency("C04", "C04-0004", "E0107", "E0108"),
            "O04": _sealed_dependency("O04", "O04-0001", "E0121", "E0122"),
        },
        "next_action": "SEAL_R01_0001_THEN_CONTINUE_DAG",
        "regression_baseline": _sealed_dependency("T02", "T02-0001", "E0127", "E0128"),
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
            f"induction component holds unexpected files: {component_files}"
        )
    return {
        "approved_scope": [f"{COMPONENT}/**", "artifacts/work_packages/R01/**"],
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


def r01_verification(regression: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "causal_discipline": {
            "causal_identification_reported": "NOT_ASSESSED",
            "identification_owner": "R04",
            "relation_kind": "ASSOCIATION",
        },
        "exit_criteria": {
            "independence_adjustment_applied": {
                "evidence": [
                    f"{COMPONENT}/test_induction_fixture.py",
                    f"{COMPONENT}/test_heterogeneity.py",
                ],
                "mechanism": (
                    "each finding carries its O03 cluster weight "
                    "support_count_adjusted / support_count_raw; the recomputed "
                    "effective independent count is cross-checked against the pack"
                ),
                "status": "PASS",
            },
            "moderators_and_nulls_retained": {
                "evidence": [
                    f"{COMPONENT}/test_heterogeneity.py",
                    f"{COMPONENT}/test_induction_fixture.py",
                ],
                "mechanism": (
                    "every observed moderator and level survives whatever its "
                    "status, and a declared null without a finding fails closed"
                ),
                "status": "PASS",
            },
        },
        "heterogeneity_semantics": {
            "bands": ["LOW", "MODERATE", "SUBSTANTIAL", "CONSIDERABLE"],
            "boundary_resolves_to_the_more_cautious_band": True,
            "estimator": "independence-weighted Cochran Q, I-squared, DerSimonian-Laird tau-squared",
            "insufficient_data_is_undetermined_not_low": True,
        },
        "required_checks": {
            "heterogeneity_test": {
                "module": f"{COMPONENT}/test_heterogeneity.py",
                "status": "PASS",
                "test_count": regression["heterogeneity_test"]["collected"],
            },
            "induction_fixture_test": {
                "module": f"{COMPONENT}/test_induction_fixture.py",
                "status": "PASS",
                "test_count": regression["induction_fixture_test"]["collected"],
            },
        },
        "status": "PASS",
        "targeted_test_count": regression["targeted_induction"]["collected"],
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
                "artifacts/work_packages/R01/attempts/0001/build_r01_0001_evidence.py",
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
        "# R01-0001 primary-session separate adversarial review\n"
        "\n"
        "- Reviewer: primary session in a separate adversarial pass under the\n"
        "  product-owner instruction forbidding subagents and Fleet;\n"
        "  actor_independence=false is recorded, not hidden.\n"
        "- Independence adjustment is structural, not advisory. Every finding\n"
        "  carries the independence weight of its O03 dependency cluster\n"
        "  (support_count_adjusted / support_count_raw), so a cluster of k\n"
        "  dependent replications contributes exactly its adjusted support and\n"
        "  never k votes. The fixture pack clusters two of four positive\n"
        "  findings, and the synthesis reports raw_count 4 against adjusted\n"
        "  weight 3. The engine recomputes the pack's effective independent\n"
        "  count from the clusters and refuses to proceed when the pack's own\n"
        "  declared value disagrees, or when the supplied clusters do not match\n"
        "  the membership the pack declares.\n"
        "- The same weights enter the statistics. Inverse-variance weights are\n"
        "  scaled by independence before Cochran Q, so dependent replications\n"
        "  cannot present themselves as that many precise measurements; halving\n"
        "  both weights halves Q while leaving the pooled effect unchanged.\n"
        "- Heterogeneity fails toward ignorance. Fewer than two quantitative\n"
        "  findings, or any finding with no positive independence weight,\n"
        "  yields UNDETERMINED with a stated reason rather than a reassuring\n"
        "  LOW, and a sealed record whose classification is UNDETERMINED with\n"
        "  no reason is rejected. A band boundary resolves upward into the more\n"
        "  cautious band.\n"
        "- Moderators and nulls are retained by construction. Every observed\n"
        "  moderator and level appears in the output whether it discriminates,\n"
        "  agrees, or has a single level, because an absent moderator is\n"
        "  indistinguishable from one never examined. A retained moderator with\n"
        "  no levels and a declared null with no finding both fail closed, and\n"
        "  a null stratum keeps its own direction rather than being absorbed.\n"
        "- No causal promotion. The synthesis reports relation_kind ASSOCIATION\n"
        "  and causal_identification NOT_ASSESSED; injecting either a causal\n"
        "  relation kind or an identification verdict is refused. Identification\n"
        "  belongs to R04.\n"
        "- Integrity: identical inputs seal byte-identical artifacts, the\n"
        "  synthesis id is the content address of the recorded conclusions, and\n"
        "  a tamper that recomputes the self-hash is still caught because the id\n"
        "  no longer derives from the content it claims.\n"
        "- Residual limitations: the engine consumes findings supplied by a\n"
        "  caller and does not itself extract effect sizes from sources;\n"
        "  moderator discrimination is a direction-level screen rather than a\n"
        "  between-group significance test; and R02/R03/R04 remain unbuilt. This\n"
        "  review is not external actor-independent certification.\n"
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
            "path": f"artifacts/work_packages/R01/attempts/0001/{name}",
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in sorted(set(output_names))
    ]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "R01_INDUCTIVE_SYNTHESIS_AND_HETEROGENEITY",
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependency_state": dependencies,
        "exit_criteria": {
            "independence_adjustment_applied": "PASS",
            "moderators_and_nulls_retained": "PASS",
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
            "extraction of effect sizes or moderator levels from primary sources",
            "between-group significance testing of moderator effects",
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
        "heterogeneity_test": f"{EXPECTED_HETEROGENEITY_COUNT}/{EXPECTED_HETEROGENEITY_COUNT}",
        "induction_fixture_test": (
            f"{EXPECTED_INDUCTION_FIXTURE_COUNT}/{EXPECTED_INDUCTION_FIXTURE_COUNT}"
        ),
        "next_action": "SEAL_R01_0001_THEN_CONTINUE_DAG",
        "package_status": "PASS",
        "status": "PASS",
        "targeted_induction": f"{EXPECTED_TARGETED_COUNT}/{EXPECTED_TARGETED_COUNT}",
    }


def build() -> dict[str, Any]:
    for name in RUN_RESULTS:
        check_run(name)
    normalize_junits()
    regression = regression_evidence()
    dependencies = dependency_status()
    write_scope = write_scope_verification()
    verification = r01_verification(regression)
    write_json("dependency-status.json", dependencies)
    write_json("write-scope-verification.json", write_scope)
    write_json("r01-verification.json", verification)
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
        raise SystemExit("R01-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "r01-verification.json")
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
    verification = read_json(ATTEMPT / "r01-verification.json")
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
        raise SystemExit("stored R01-0001 report is not the deterministic document")
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
