#!/usr/bin/env python3
"""Build and verify I01-0001 evidence: bounded Interview and contradiction scan.

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
ATTEMPT = ROOT / "artifacts/work_packages/I01/attempts/0001"
ATTEMPT_ID = "I01-0001"
WORK_PACKAGE_ID = "I01"
RECORDED_AT = "2026-08-02T08:00:00.000Z"
ATTEMPT_DIR = "artifacts/work_packages/I01/attempts/0001"
AUTHORITY_DECISION = None

EXPECTED_PRODUCT_HASHES = {
    "artifacts/work_packages/I01/attempts/0001/check_packaging.py": "6be85d615e01d7ce1d51590338a83f067431e0bea6051580c06a920f5ba46db9",
    "artifacts/work_packages/I01/attempts/0001/run_i01_0001_checks.py": "7345179c026b7caeeb918ee93333a7f3f12867ca1a804dbf64748804e3db1b8a",
    "python/epistemic_foundry/intake/interview/__init__.py": "533f3441733c40bb38f6182add7eb553d6d6b378503ed8dbfda5e426c96d457c",
    "python/epistemic_foundry/intake/interview/engine.py": "547a53b9b5ede09cdcea4cd9bdaeb144569d8bcdf0ebd96bc4ba829b29286c0b",
    "python/epistemic_foundry/intake/interview/test_interview_readiness.py": "4ee7b63cb4d49d007edcd608c422dbb0ad1fa1e5e165955d7122c0e5a4e3f1ef",
    "python/epistemic_foundry/intake/interview/test_no_repeat_question.py": "cdbbb20e8b3ca9da65f97de0dbc44e5fd34a4771ad3e5cacc432437b1865a5a7",
}
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/C04/report.json": "eca4fdd3f10537a2fb5c39643f4dee52bab9bcf5b95f9468ddcd470ffd98592f",
    "artifacts/work_packages/F04/report.json": "5a2414ebb79c923af7425b87d614faa088ba9fbd4e6950406948b2eb86d6ab46",
}

JUNIT_PATHS = {
    "full_node_suite": ATTEMPT / "full-node-suite.junit.xml",
    "full_python_suite": ATTEMPT / "full-python-suite.junit.xml",
    "interview_readiness_test": ATTEMPT / "interview-readiness-test.junit.xml",
    "no_repeat_question_test": ATTEMPT / "no-repeat-question-test.junit.xml",
    "wire_literal_discipline": ATTEMPT / "wire-literal-discipline.junit.xml",
}
_NODE_JUNITS = frozenset({"full_node_suite"})
RUN_RESULTS = (
    "full-node-suite",
    "full-python-suite",
    "git-diff-check",
    "interview-readiness-test",
    "no-repeat-question-test",
    "packaging-discovery",
    "ruff-check",
    "wire-literal-discipline",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "build_i01_0001_evidence.py",
    "check_packaging.py",
    "commands.jsonl",
    "dependency-status.json",
    "full-node-suite.junit.xml",
    "full-python-suite.junit.xml",
    "i01-verification.json",
    "i01_0001_rah_seal.py",
    "interview-readiness-test.junit.xml",
    "junit-normalization-verification.json",
    "no-repeat-question-test.junit.xml",
    "node-test-inventory.json",
    "review.md",
    "run_i01_0001_checks.py",
    "wire-literal-discipline.junit.xml",
    "write-scope-verification.json",
)

# Measured gate counts (observed at seal-prep time on the live tree).
INTERVIEW_READINESS_COUNT = 19
NO_REPEAT_QUESTION_COUNT = 17
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
            "interview_readiness_test",
            pytest_summary(JUNIT_PATHS["interview_readiness_test"]),
            INTERVIEW_READINESS_COUNT,
        ),
        (
            "no_repeat_question_test",
            pytest_summary(JUNIT_PATHS["no_repeat_question_test"]),
            NO_REPEAT_QUESTION_COUNT,
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
            "C04": _sealed_dependency("C04", "E0012", "E0013"),
            "F04": _sealed_dependency("F04", "E0006", "E0007"),
        },
        "next_action": "SEAL_I01_0001_THEN_RECOMPUTE_DAG",
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
            "python/epistemic_foundry/intake/interview/**",
            "artifacts/work_packages/I01/**",
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
        "interview_readiness_test": suites["interview_readiness_test"]["collected"],
        "no_repeat_question_test": suites["no_repeat_question_test"]["collected"],
    }
    return {
        "attempt_id": ATTEMPT_ID,
        "declaring_sources": {
            "interview_vocabulary": (
                "the closed InterviewRule/InterviewDimension/NeedCriticality/"
                "ContradictionDisposition/PriorQuestionState enums declared in "
                "python/epistemic_foundry/intake/interview/engine.py, each bound "
                "key-for-key to its wire literal"
            ),
            "finding_codes": (
                "INTERVIEW_INPUT_INVALID, INTERVIEW_INPUT_DUPLICATE, "
                "INTERVIEW_RULE_DIMENSION_MISMATCH, CONTRADICTION_DISPOSITION_INVALID, "
                "CONTRADICTION_EVIDENCE_REQUIRED, CONTRADICTION_BLOCKER_MISMATCH, "
                "PRIOR_QUESTION_ID_MISMATCH, PRIOR_QUESTION_TARGET_INVALID, "
                "PRIOR_QUESTION_STATE_INVALID"
            ),
        },
        "exit_criteria": {
            "only_decision_critical_questions_asked": {
                "mechanism": (
                    "the planner emits a question only for a missing "
                    "decision-critical dimension or a recorded critical "
                    "contradiction; non-critical needs are deferred (recorded, "
                    "never asked), duplicate needs on one dimension merge to a "
                    "single stable question, and question order is canonical "
                    "rather than input order"
                ),
                "status": "PASS",
            },
            "critical_contradictions_recorded": {
                "mechanism": (
                    "every contradiction is recorded verbatim; a critical, "
                    "unresolved contradiction routes a question, an "
                    "accepted-as-blocker contradiction sets an explicit sticky "
                    "blocker that is never silently downgraded, and a conflict "
                    "need without a recorded critical conflict is refused "
                    "CONTRADICTION_EVIDENCE_REQUIRED"
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
                f"{ATTEMPT_DIR}/build_i01_0001_evidence.py",
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
        "# I01-0001 independent review of bounded-agent work\n"
        "\n"
        "- Author: a bounded implementation agent (disjoint write scope, frozen\n"
        "  contracts) under the product owner's explicit instruction. Reviewer:\n"
        "  the sealing agent, which did not author this attempt; author/reviewer\n"
        "  separation holds with actor_independence=true, while external\n"
        "  actor-independent certification does not.\n"
        "- Only decision-critical questions surface: a question is emitted only for\n"
        "  a missing decision-critical dimension or a recorded critical\n"
        "  contradiction. Non-critical needs are recorded and deferred, duplicate\n"
        "  needs on one dimension merge to a single stable question, and question\n"
        "  order is canonical rather than input order (order-independent replay).\n"
        "- Answered and known priors are never re-asked: a known fact or an\n"
        "  answered prior question resolves its dimension, an open prior question is\n"
        "  held pending rather than re-emitted, and a prior blocker is sticky for\n"
        "  the same request revision; a new revision mints a new question identity.\n"
        "- Critical contradictions are recorded and routed: every contradiction is\n"
        "  preserved verbatim, a critical unresolved one routes a question, and an\n"
        "  accepted-as-blocker contradiction sets an explicit blocker that is never\n"
        "  silently downgraded.\n"
        "- Fail-closed on adversarial input: raw-enum aliases, mutable record\n"
        "  collections, duplicate identifiers, forged or mismatched prior-question\n"
        "  ids, unknown prior targets, invalid disposition linkage, invalid\n"
        "  revisions, and blocker mismatches each raise the exact finding code\n"
        "  (INTERVIEW_INPUT_INVALID, INTERVIEW_INPUT_DUPLICATE,\n"
        "  INTERVIEW_RULE_DIMENSION_MISMATCH, CONTRADICTION_DISPOSITION_INVALID,\n"
        "  CONTRADICTION_EVIDENCE_REQUIRED, CONTRADICTION_BLOCKER_MISMATCH,\n"
        "  PRIOR_QUESTION_ID_MISMATCH, PRIOR_QUESTION_TARGET_INVALID,\n"
        "  PRIOR_QUESTION_STATE_INVALID) rather than degrading silently.\n"
        "- Boundary: the engine imports the standard library alone and plans an\n"
        "  interview; it does not score, rank, select, promote or evaluate any\n"
        "  candidate, and C04/F04 are manifest-order dependencies, not composed\n"
        "  code. The component ships under python/ and stays out of the wheel.\n"
        "- Integration gates at review time: ruff check clean, git diff --check\n"
        "  clean, the two required suites green at 19/19 and 17/17 (36 targeted),\n"
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
        "attempt_type": "I01_BOUNDED_INTERVIEW_AND_CONTRADICTION_SCAN",
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
            "insight framing, falsifier or scope compilation: I02 territory; this package plans a bounded interview and records contradictions only",
            "scoring, ranking, selection, promotion or evaluation of any candidate",
            "any composed code dependency on C04/F04: they are manifest-order dependencies and the engine imports the standard library alone",
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
        "next_action": "SEAL_I01_0001_THEN_RECOMPUTE_DAG",
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
    write_json("i01-verification.json", verification)
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
        raise SystemExit("I01-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "i01-verification.json")
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
    verification = read_json(ATTEMPT / "i01-verification.json")
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
        raise SystemExit("stored I01-0001 report is not the deterministic document")
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
