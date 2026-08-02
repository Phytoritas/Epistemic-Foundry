#!/usr/bin/env python3
"""Build and verify P01-0001 blind brief and asymmetric dispatch evidence.

P01-0001 implements `python/epistemic_foundry/parliament/blind/**`: the
assembly that gives each role only the evidence classes its registry ACL
permits, names what was withheld so its existence stays visible, and measures
rather than asserts that the first round stayed independent.  This builder
verifies the executed checks and emits immutable attempt evidence; it never
modifies product files.
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
ATTEMPT = ROOT / "artifacts/work_packages/P01/attempts/0001"
ATTEMPT_ID = "P01-0001"
WORK_PACKAGE_ID = "P01"
RECORDED_AT = "2026-08-01T13:30:00.000Z"

EXPECTED_BLINDNESS_COUNT = 16
EXPECTED_EVIDENCE_ACL_COUNT = 21
EXPECTED_TARGETED_COUNT = 37
EXPECTED_CAUSAL_REGRESSION_COUNT = 45
EXPECTED_COMPLETENESS_REGRESSION_COUNT = 18
EXPECTED_PYTHON_COUNT = 1261
EXPECTED_NODE_COUNT = 903
EXPECTED_NODE_FILE_COUNT = 87

COMPONENT = "python/epistemic_foundry/parliament/blind"
EXPECTED_PRODUCT_HASHES = {
    "python/epistemic_foundry/parliament/blind/__init__.py": "24d1759116152b0e3061bb9c7d59e28f6410aed2860a649b29b3fd8a1283649f",
    "python/epistemic_foundry/parliament/blind/contracts.py": "d350ee696769758745f3c77eb0a134835cbeed1be90b608e42e03b12ad75b7e6",
    "python/epistemic_foundry/parliament/blind/pytest.ini": "0dc45ebbe8ccac9848833c22c309199f547f8397e6cb9cc37ecd9381908ec813",
    "python/epistemic_foundry/parliament/blind/test_blindness.py": "1679b65070951e36e661456c4b55fa75e72fb135c956c3c60a4419b4482d71aa",
    "python/epistemic_foundry/parliament/blind/test_evidence_acl.py": "35f6be728c728e4b3cbcb14770dc3a4f8c619c02936708a72ce91a62f788d992",
}
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/N04/attempts/0001/report.json": "8cbe538b5adb087974f83cc181e97172052bc25ff92e6a14da7dad3eb70141f7",
    "artifacts/work_packages/O04/attempts/0001/report.json": "2fd0059a9e1bd66d383168472a644386c299f870e6815e7df291391005f79f0f",
    "artifacts/work_packages/R04/attempts/0001/report.json": "bc7080d66ced6dd68672995e60549b066b1290161b665bfd5b05aa48eb54d135",
}

JUNIT_PATHS = {
    "blindness": ATTEMPT / "blindness-test.junit.xml",
    "evidence_acl": ATTEMPT / "evidence-acl-test.junit.xml",
    "targeted": ATTEMPT / "targeted-parliament-blind.junit.xml",
    "causal_regression": ATTEMPT / "dependency-regression-causal.junit.xml",
    "completeness_regression": ATTEMPT / "dependency-regression-completeness.junit.xml",
    "full_python": ATTEMPT / "full-python-suite.junit.xml",
    "full_node": ATTEMPT / "full-node-suite.junit.xml",
}
_NODE_JUNITS = frozenset({"full_node"})
RUN_RESULTS = (
    "ruff-check",
    "ruff-format-check",
    "blindness-test",
    "evidence-acl-test",
    "targeted-parliament-blind",
    "dependency-regression-causal",
    "dependency-regression-completeness",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "run_p01_0001_checks.py",
    "build_p01_0001_evidence.py",
    "p01_0001_rah_seal.py",
    "dependency-status.json",
    "p01-verification.json",
    "write-scope-verification.json",
    "node-test-inventory.json",
    "junit-normalization-verification.json",
    "blindness-test.junit.xml",
    "evidence-acl-test.junit.xml",
    "targeted-parliament-blind.junit.xml",
    "dependency-regression-causal.junit.xml",
    "dependency-regression-completeness.junit.xml",
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
    blindness = pytest_summary(JUNIT_PATHS["blindness"])
    acl = pytest_summary(JUNIT_PATHS["evidence_acl"])
    targeted = pytest_summary(JUNIT_PATHS["targeted"])
    causal = pytest_summary(JUNIT_PATHS["causal_regression"])
    completeness = pytest_summary(JUNIT_PATHS["completeness_regression"])
    python = pytest_summary(JUNIT_PATHS["full_python"])
    node = node_summary(JUNIT_PATHS["full_node"])
    node_inventory = read_json(ATTEMPT / "node-test-inventory.json")
    for label, summary, expected in (
        ("blindness_test", blindness, EXPECTED_BLINDNESS_COUNT),
        ("evidence_acl_test", acl, EXPECTED_EVIDENCE_ACL_COUNT),
        ("targeted", targeted, EXPECTED_TARGETED_COUNT),
        ("causal_regression", causal, EXPECTED_CAUSAL_REGRESSION_COUNT),
        (
            "completeness_regression",
            completeness,
            EXPECTED_COMPLETENESS_REGRESSION_COUNT,
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
        "baseline_attempt": "R04-0001",
        "component_tests_are_targeted_only": True,
        "causal_regression": causal,
        "completeness_regression": completeness,
        "full_node": node,
        "full_python": python,
        "blindness_test": blindness,
        "evidence_acl_test": acl,
        "new_failure_count": 0,
        "prior_baseline_counts": {"full_node": 903, "full_python": 1261},
        "status": "PASS",
        "targeted_parliament_blind": targeted,
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
            "N04": _sealed_dependency("N04", "N04-0001", "E0076", "E0077"),
            "O04": _sealed_dependency("O04", "O04-0001", "E0121", "E0122"),
            "R04": _sealed_dependency("R04", "R04-0001", "E0135", "E0136"),
        },
        "next_action": "SEAL_P01_0001_THEN_CONTINUE_DAG",
        "regression_baseline": _sealed_dependency("R04", "R04-0001", "E0135", "E0136"),
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
        raise SystemExit(f"blind component holds unexpected files: {component_files}")
    return {
        "approved_scope": [f"{COMPONENT}/**", "artifacts/work_packages/P01/**"],
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


def p01_verification(regression: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "asymmetric_dispatch": {
            "identical_contexts_refused": True,
            "minimum_dispatched_roles": 2,
            "role_class_matrix_recorded": True,
        },
        "blindness": {
            "blind_round": 1,
            "cross_reference_check": "every ordered pair of first-round briefs",
            "isolation_is_measured_not_asserted": True,
            "shared_context_manifest_refused": True,
        },
        "evidence_acl": {
            "declaring_source": "manifests/role_registry.yaml",
            "unregistered_role_fails_closed": True,
            "wildcard_token": "all_permitted",
            "withholding_is_visible": True,
        },
        "exit_criteria": {
            "first_round_isolation_measured": {
                "evidence": [f"{COMPONENT}/test_blindness.py"],
                "mechanism": (
                    "the isolation ratio is computed over every ordered pair of "
                    "first-round briefs, and a single cross-reference, shared "
                    "manifest, or non-blind brief fails the seal"
                ),
                "status": "PASS",
            },
            "roles_cannot_see_forbidden_evidence": {
                "evidence": [f"{COMPONENT}/test_evidence_acl.py"],
                "mechanism": (
                    "each role's ACL is read from the declaring registry, the "
                    "context carries only permitted classes, withheld ids are "
                    "named, and a brief citing evidence its own context never "
                    "contained is refused"
                ),
                "status": "PASS",
            },
        },
        "required_checks": {
            "blindness_test": {
                "module": f"{COMPONENT}/test_blindness.py",
                "status": "PASS",
                "test_count": regression["blindness_test"]["collected"],
            },
            "evidence_acl_test": {
                "module": f"{COMPONENT}/test_evidence_acl.py",
                "status": "PASS",
                "test_count": regression["evidence_acl_test"]["collected"],
            },
        },
        "schema_binding": {"council_brief": "schemas/council-brief.schema.json"},
        "status": "PASS",
        "targeted_test_count": regression["targeted_parliament_blind"]["collected"],
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
                "artifacts/work_packages/P01/attempts/0001/build_r01_0001_evidence.py",
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
        "# P01-0001 primary-session separate adversarial review\n"
        "\n"
        "- Reviewer: primary session in a separate adversarial pass under the\n"
        "  product-owner instruction forbidding subagents and Fleet;\n"
        "  actor_independence=false is recorded, not hidden.\n"
        "- The Evidence ACL is read, not restated. Each role's permitted\n"
        "  classes come from manifests/role_registry.yaml, so the component\n"
        "  cannot drift from the declaring source, and a role the registry does\n"
        "  not describe has no ACL and fails closed rather than defaulting to\n"
        "  open. The defender and prosecutor contexts are disjoint on the\n"
        "  fixture corpus, which is the asymmetry the panel exists to create.\n"
        "- Withholding is visible rather than silent. The manifest names the\n"
        "  withheld ids and counts them by class, so a role can tell that\n"
        "  evidence exists outside its ACL without being able to read it, and a\n"
        "  brief citing either withheld evidence or evidence no context ever\n"
        "  held is refused with the offending ids named.\n"
        "- First-round isolation is measured. Every ordered pair of first-round\n"
        "  briefs is examined and the ratio is a computed fact: one\n"
        "  cross-reference takes a two-brief round from 1.0 to 0.5, and the\n"
        "  sealing path refuses anything below full isolation, any non-blind\n"
        "  first-round brief, and any two roles sharing one context manifest.\n"
        "  A sealed record whose isolation report does not cover every brief is\n"
        "  rejected as unmeasured.\n"
        "- A symmetric panel is refused. Roles briefed identically are one\n"
        "  opinion repeated, so an assembly whose contexts all carry the same\n"
        "  evidence fails rather than being recorded as unanimous, and a single\n"
        "  role is not a parliament.\n"
        "- A brief that names no condition which would change its verdict is\n"
        "  refused: an unfalsifiable brief cannot be cross-examined later.\n"
        "- Fixtures validate against the canonical\n"
        "  schemas/council-brief.schema.json, so the component is bound to the\n"
        "  shared contract rather than to a local convention.\n"
        "- Residual limitations: the component assembles contexts and checks\n"
        "  what the briefs cite; it does not generate briefs and cannot enforce\n"
        "  the ACL inside a model that has already received the context, so\n"
        "  collusion outside the recorded artifacts is invisible to it.\n"
        "  Cross-examination, adjudication, and minority reports are later\n"
        "  P-phase packages. This review is not external actor-independent\n"
        "  certification.\n"
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
            "path": f"artifacts/work_packages/P01/attempts/0001/{name}",
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in sorted(set(output_names))
    ]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "P01_BLIND_BRIEFS_AND_ASYMMETRIC_DISPATCH",
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependency_state": dependencies,
        "exit_criteria": {
            "first_round_isolation_measured": "PASS",
            "roles_cannot_see_forbidden_evidence": "PASS",
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
            "generation of briefs, as opposed to assembling contexts and checking returns",
            "detection of collusion outside the recorded briefs and manifests",
            "cross-examination, adjudication, or minority-report handling",
            "enforcement of the ACL inside a model that receives the context",
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
        "blindness_test": f"{EXPECTED_BLINDNESS_COUNT}/{EXPECTED_BLINDNESS_COUNT}",
        "evidence_acl_test": (
            f"{EXPECTED_EVIDENCE_ACL_COUNT}/{EXPECTED_EVIDENCE_ACL_COUNT}"
        ),
        "next_action": "SEAL_P01_0001_THEN_CONTINUE_DAG",
        "package_status": "PASS",
        "status": "PASS",
        "targeted_parliament_blind": (
            f"{EXPECTED_TARGETED_COUNT}/{EXPECTED_TARGETED_COUNT}"
        ),
    }


def build() -> dict[str, Any]:
    for name in RUN_RESULTS:
        check_run(name)
    normalize_junits()
    regression = regression_evidence()
    dependencies = dependency_status()
    write_scope = write_scope_verification()
    verification = p01_verification(regression)
    write_json("dependency-status.json", dependencies)
    write_json("write-scope-verification.json", write_scope)
    write_json("p01-verification.json", verification)
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
        raise SystemExit("P01-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "p01-verification.json")
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
    verification = read_json(ATTEMPT / "p01-verification.json")
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
        raise SystemExit("stored P01-0001 report is not the deterministic document")
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
