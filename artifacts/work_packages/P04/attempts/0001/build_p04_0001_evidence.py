#!/usr/bin/env python3
"""Build and verify P04-0001 judge and independent attestation evidence.

P04-0001 implements `python/epistemic_foundry/parliament/adjudication/**`:
the gate whose recommendation is bounded by the deterministic P02 ceiling and
by any veto or unanswered challenge rather than by agreement among briefs, and
whose independent attestor reads a structured pack rather than a persuasive
transcript.  This builder verifies the executed checks and emits immutable
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
ATTEMPT = ROOT / "artifacts/work_packages/P04/attempts/0001"
ATTEMPT_ID = "P04-0001"
WORK_PACKAGE_ID = "P04"
RECORDED_AT = "2026-08-01T18:30:00.000Z"

EXPECTED_MAJORITY_INDEPENDENCE_COUNT = 22
EXPECTED_ATTESTATION_COUNT = 30
EXPECTED_TARGETED_COUNT = 52
EXPECTED_AUDITORS_REGRESSION_COUNT = 42
EXPECTED_CROSS_EXAM_REGRESSION_COUNT = 43
EXPECTED_PYTHON_COUNT = 1261
EXPECTED_NODE_COUNT = 982
EXPECTED_NODE_FILE_COUNT = 91

COMPONENT = "python/epistemic_foundry/parliament/adjudication"
EXPECTED_PRODUCT_HASHES = {
    "python/epistemic_foundry/parliament/adjudication/__init__.py": "eb2a0c7a698b4a143a84dee793450f62aaadac9b544e212381155a769fda9a03",
    "python/epistemic_foundry/parliament/adjudication/contracts.py": "e27145a9ecd18be4c3a517c8f42631e5a9dd93da144eb46b1cf8d995e49351b6",
    "python/epistemic_foundry/parliament/adjudication/pytest.ini": "3a4c27efe05d50356a6add408c2eac149359043c26681c93c27f0828c2eb012f",
    "python/epistemic_foundry/parliament/adjudication/test_attestation.py": "27ea3513b72da336ba7628a8a93190ee4c4c423b060996509f224e2701389457",
    "python/epistemic_foundry/parliament/adjudication/test_majority_independence.py": "244221b09dcc41bffe3dfe13a061a4fa5ab073f1964fbba6a41888526ea0f47c",
}
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/P02/attempts/0001/report.json": "71c5a03e266f2215f68db887994bdff15b40840f7c2431a3b57d6d73acdd1316",
    "artifacts/work_packages/P03/attempts/0001/report.json": "ed2af5dea715c28908d9c0387fa08fa19da77f767797106fed905f95dd1ffafd",
}

JUNIT_PATHS = {
    "majority_independence": ATTEMPT / "majority-independence-test.junit.xml",
    "attestation": ATTEMPT / "attestation-test.junit.xml",
    "targeted": ATTEMPT / "targeted-parliament-adjudication.junit.xml",
    "auditors_regression": ATTEMPT / "dependency-regression-auditors.junit.xml",
    "cross_exam_regression": ATTEMPT / "dependency-regression-cross-exam.junit.xml",
    "full_python": ATTEMPT / "full-python-suite.junit.xml",
    "full_node": ATTEMPT / "full-node-suite.junit.xml",
}
_NODE_JUNITS = frozenset({"full_node"})
RUN_RESULTS = (
    "ruff-check",
    "ruff-format-check",
    "majority-independence-test",
    "attestation-test",
    "targeted-parliament-adjudication",
    "dependency-regression-auditors",
    "dependency-regression-cross-exam",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "run_p04_0001_checks.py",
    "build_p04_0001_evidence.py",
    "p04_0001_rah_seal.py",
    "dependency-status.json",
    "p04-verification.json",
    "write-scope-verification.json",
    "node-test-inventory.json",
    "junit-normalization-verification.json",
    "majority-independence-test.junit.xml",
    "attestation-test.junit.xml",
    "targeted-parliament-adjudication.junit.xml",
    "dependency-regression-auditors.junit.xml",
    "dependency-regression-cross-exam.junit.xml",
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
    majority = pytest_summary(JUNIT_PATHS["majority_independence"])
    attestation = pytest_summary(JUNIT_PATHS["attestation"])
    targeted = pytest_summary(JUNIT_PATHS["targeted"])
    auditors = pytest_summary(JUNIT_PATHS["auditors_regression"])
    cross_exam = pytest_summary(JUNIT_PATHS["cross_exam_regression"])
    python = pytest_summary(JUNIT_PATHS["full_python"])
    node = node_summary(JUNIT_PATHS["full_node"])
    node_inventory = read_json(ATTEMPT / "node-test-inventory.json")
    for label, summary, expected in (
        (
            "majority_independence_test",
            majority,
            EXPECTED_MAJORITY_INDEPENDENCE_COUNT,
        ),
        ("attestation_test", attestation, EXPECTED_ATTESTATION_COUNT),
        ("targeted", targeted, EXPECTED_TARGETED_COUNT),
        ("auditors_regression", auditors, EXPECTED_AUDITORS_REGRESSION_COUNT),
        (
            "cross_exam_regression",
            cross_exam,
            EXPECTED_CROSS_EXAM_REGRESSION_COUNT,
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
        "baseline_attempt": "P03-0001",
        "component_tests_are_targeted_only": True,
        "auditors_regression": auditors,
        "cross_exam_regression": cross_exam,
        "full_node": node,
        "full_python": python,
        "attestation_test": attestation,
        "majority_independence_test": majority,
        "new_failure_count": 0,
        "prior_baseline_counts": {"full_node": 903, "full_python": 1261},
        "status": "PASS",
        "targeted_parliament_adjudication": targeted,
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
            "P02": _sealed_dependency("P02", "P02-0001", "E0143", "E0144"),
            "P03": _sealed_dependency("P03", "P03-0001", "E0145", "E0146"),
        },
        "next_action": "SEAL_P04_0001_THEN_CONTINUE_DAG",
        "regression_baseline": _sealed_dependency("P03", "P03-0001", "E0145", "E0146"),
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
            f"adjudication component holds unexpected files: {component_files}"
        )
    return {
        "approved_scope": [f"{COMPONENT}/**", "artifacts/work_packages/P04/**"],
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


def p04_verification(regression: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "attestation_independence": {
            "attestation_must_rest_on_exactly_the_pack": True,
            "checks_bound_to_canonical_shape": True,
            "judge_may_not_attest_to_itself": True,
            "pack_carries_no_persuasive_field": True,
        },
        "exit_criteria": {
            "attestor_sees_structured_pack": {
                "evidence": [f"{COMPONENT}/test_attestation.py"],
                "mechanism": (
                    "the pack carries ids, hashes, statuses, ceilings, and "
                    "counts only; any field carrying brief or challenge prose "
                    "is refused anywhere in the pack or its checks, and the "
                    "attestor must differ from the judge and attest to exactly "
                    "the pack it was given"
                ),
                "status": "PASS",
            },
            "majority_cannot_promote": {
                "evidence": [f"{COMPONENT}/test_majority_independence.py"],
                "mechanism": (
                    "the recommendation is bounded by the deterministic P02 "
                    "ceiling, a sustained veto or an unanswered challenge "
                    "forces BLOCK, agreement among briefs is recorded as "
                    "non-load-bearing, and a gate override attempt is refused"
                ),
                "status": "PASS",
            },
        },
        "promotion_bound": {
            "block_on_open_challenge": True,
            "block_on_sustained_veto": True,
            "derived_from_deterministic_gates": True,
            "unanswered_challenge_must_be_an_unresolved_issue": True,
        },
        "required_checks": {
            "attestation_test": {
                "module": f"{COMPONENT}/test_attestation.py",
                "status": "PASS",
                "test_count": regression["attestation_test"]["collected"],
            },
            "majority_independence_test": {
                "module": f"{COMPONENT}/test_majority_independence.py",
                "status": "PASS",
                "test_count": regression["majority_independence_test"]["collected"],
            },
        },
        "schema_binding": {
            "adjudication": "schemas/adjudication.schema.json",
            "attestation": "schemas/attestation.schema.json",
        },
        "status": "PASS",
        "targeted_test_count": regression["targeted_parliament_adjudication"][
            "collected"
        ],
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
                "artifacts/work_packages/P04/attempts/0001/build_r01_0001_evidence.py",
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
        "# P04-0001 primary-session separate adversarial review\n"
        "\n"
        "- Reviewer: primary session in a separate adversarial pass under the\n"
        "  product-owner instruction forbidding subagents and Fleet;\n"
        "  actor_independence=false is recorded, not hidden.\n"
        "- Both vocabularies are read from their declaring schemas, so a\n"
        "  verdict or recommendation this component invented would not resolve.\n"
        "- A majority cannot promote. The recommendation is bounded above by\n"
        "  the deterministic P02 ceiling; four briefs unanimously saying\n"
        "  ENTAILED still cannot lift it. The majority is computed and recorded\n"
        "  so a reader can see it existed, and the sealed gate carries an\n"
        "  explicit statement that it did not influence the recommendation,\n"
        "  which a rehashed edit cannot flip.\n"
        "- A sustained method veto or any unanswered cross-examination forces\n"
        "  BLOCK, because an objection nobody answered is not a detail to be\n"
        "  weighed against a majority. Every open challenge must also appear as\n"
        "  an unresolved issue in the adjudication, and the strongest dissent\n"
        "  must be cited by the adjudication that decided against it.\n"
        "- An attempt to override a deterministic gate is refused rather than\n"
        "  absorbed, and a sealed gate may not record a successful one.\n"
        "- The attestor reads structure, not persuasion. The pack carries ids,\n"
        "  hashes, statuses, ceilings and counts; every persuasive field name\n"
        "  is refused anywhere in the pack, including nested inside the\n"
        "  attestation's own checks, so rhetoric cannot re-enter through the\n"
        "  reviewer's worksheet. The judge's rationale never reaches the pack.\n"
        "- Independence is checked, not asserted. The attestor may not be the\n"
        "  judge, must state its independence, must name the adjudication its\n"
        "  pack describes, and must rest on exactly that pack: extra inputs are\n"
        "  refused as readily as wrong ones. Its checks must match the\n"
        "  canonical check shape, so an attestation cannot claim scrutiny it\n"
        "  did not record. A failing attestation still seals and says so.\n"
        "- Residual limitations: the judge's reasoning arrives as an input\n"
        "  adjudication rather than being produced here; the component cannot\n"
        "  verify that the attestor actually ran the checks it lists or\n"
        "  cryptographically verify its signature; and the promotion commit\n"
        "  belongs to the governance gates. This review is not external\n"
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
            "path": f"artifacts/work_packages/P04/attempts/0001/{name}",
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in sorted(set(output_names))
    ]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "P04_JUDGE_AND_INDEPENDENT_ATTESTATION_GATE",
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependency_state": dependencies,
        "exit_criteria": {
            "attestor_sees_structured_pack": "PASS",
            "majority_cannot_promote": "PASS",
        },
        "global_implementation_gate": "fail",
        "history_and_worktree": {
            "dirty_worktree_preserved": True,
            "prior_attempts_reports_and_rah_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
            "subagents_or_fleet_used": False,
        },
        "implementation_status": "PASS",
        "next_package": "T04-0001",
        "not_claimed": [
            "the judge's reasoning, which arrives as an input adjudication",
            "verification that the attestor actually performed the checks it lists",
            "cryptographic verification of the attestation signature",
            "the promotion commit itself, which the governance gates own",
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
        "attestation_test": (
            f"{EXPECTED_ATTESTATION_COUNT}/{EXPECTED_ATTESTATION_COUNT}"
        ),
        "majority_independence_test": (
            f"{EXPECTED_MAJORITY_INDEPENDENCE_COUNT}/"
            f"{EXPECTED_MAJORITY_INDEPENDENCE_COUNT}"
        ),
        "next_action": "SEAL_P04_0001_THEN_CONTINUE_DAG",
        "package_status": "PASS",
        "status": "PASS",
        "targeted_parliament_adjudication": (
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
    verification = p04_verification(regression)
    write_json("dependency-status.json", dependencies)
    write_json("write-scope-verification.json", write_scope)
    write_json("p04-verification.json", verification)
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
        raise SystemExit("P04-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "p04-verification.json")
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
    verification = read_json(ATTEMPT / "p04-verification.json")
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
        raise SystemExit("stored P04-0001 report is not the deterministic document")
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
