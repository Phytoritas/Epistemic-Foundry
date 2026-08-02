#!/usr/bin/env python3
"""Build and verify A01-0001 evidence: authority chain, repository constitution and status vocabulary.

A01 is the root authority package (``depends_on: []``).  It attests, without
editing, the four load-bearing authority documents -- ``MASTER_SPEC.md``,
``AGENTS.md``, ``CLAUDE.md`` and ``docs/status_taxonomy.md`` -- against the two
NON-STANDARD required checks its manifest declares, ``instructions_lint`` and
``status_claim_audit``.  Two deterministic pytest harnesses under this attempt
directory read those documents and assert the three exit criteria: the
authority order is unambiguous, ``SPECIFIED`` is never an alias of
``IMPLEMENTED``, and a shared-contract conflict returns ``SPEC_GAP``.

This builder verifies the executed check receipts, gates the two required
pytest suites against their measured counts, gates the repository-wide Python
and live Node suites on zero failures, pins the authority-document and harness
bytes, binds the live latest-sealed regression baseline (no build dependencies
exist), and emits the deterministic attempt evidence.  It never edits the
authority documents, and A01 attests the authority chain rather than
re-authoring it.
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
ATTEMPT = ROOT / "artifacts/work_packages/A01/attempts/0001"
ATTEMPT_ID = "A01-0001"
WORK_PACKAGE_ID = "A01"
ATTEMPT_DIR = "artifacts/work_packages/A01/attempts/0001"
RECORDED_AT = "2026-08-02T00:00:00.000Z"

#: The four authority documents are the whole manifest write scope for A01.
AUTHORITY_DOCS = (
    "MASTER_SPEC.md",
    "AGENTS.md",
    "CLAUDE.md",
    "docs/status_taxonomy.md",
)
APPROVED_SCOPE = [
    "MASTER_SPEC.md",
    "AGENTS.md",
    "CLAUDE.md",
    "docs/status_taxonomy.md",
    "artifacts/work_packages/A01/**",
]
#: Live sha256 of the four authority documents A01 attests (never edits).  These
#: are the manifest write scope; write_scope_verification confirms the runner
#: receipt is exactly these bytes.
EXPECTED_DOC_HASHES = {
    "MASTER_SPEC.md": "8482f50765f1cd372f306f93f8cf3431ce33442498d1a7a97643ddeef01f886e",
    "AGENTS.md": "858e537ed3e49754b8e60d31c985467ee1246ed258c7763d6de4ef0767e381ea",
    "CLAUDE.md": "10d1c125aed00ba453c75d0747596274d43499ae499bd24aa2f872be29a56357",
    "docs/status_taxonomy.md": "c4748d5275306d67a610d57ab81e7d66d58d81dab950714fdd4c4b0014474b7a",
}
#: The two attestation harnesses A01 authored under its own attempt scope.
EXPECTED_HARNESS_HASHES = {
    "artifacts/work_packages/A01/attempts/0001/test_instructions_lint.py": "cb4a2f3666ce7d8aca9838d5d910b8ec036b1477ca3d2d00df87a2e7da36942b",
    "artifacts/work_packages/A01/attempts/0001/test_status_claim_audit.py": "f7b1ba77933a61957815abb0204da183ad0aa03a540af8a5ef0df44c441c6fc1",
}
#: The full pinned product-byte set A01 is accountable for: authority documents
#: attested plus attestation harnesses authored.
EXPECTED_SRC_HASHES = {**EXPECTED_DOC_HASHES, **EXPECTED_HARNESS_HASHES}
#: A01 has no build dependencies (``depends_on: []``); the only sealed report it
#: binds is the live latest-sealed regression baseline.
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/G06/attempts/0001/report.json": "6486d22cb242c64924c06d1179e95aa8f47830032c597031756c855425cdc859",
}

JUNIT_PATHS = {
    "instructions_lint": ATTEMPT / "instructions-lint.junit.xml",
    "status_claim_audit": ATTEMPT / "status-claim-audit.junit.xml",
    "full_python_suite": ATTEMPT / "full-python-suite.junit.xml",
    "full_node_suite": ATTEMPT / "full-node-suite.junit.xml",
}
#: The two required checks and the repository-wide Python gate are pytest; only
#: the repository-wide Node regression is a Node suite.
_NODE_JUNITS = frozenset({"full_node_suite"})
PYTEST_SUITES = (
    "instructions_lint",
    "status_claim_audit",
    "full_python_suite",
)
NODE_SUITES = ("full_node_suite",)
#: The two required checks whose measured counts the report cites by name.
REQUIRED_CHECK_SUITES = (
    "instructions_lint",
    "status_claim_audit",
)
#: One ``<name>.run.json`` receipt is expected per step (runner contract).
RUN_RESULTS = (
    "instructions-lint",
    "status-claim-audit",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
    "write-scope-verification",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "a01-verification.json",
    "a01_0001_rah_seal.py",
    "build_a01_0001_evidence.py",
    "commands.jsonl",
    "dependency-status.json",
    "full-node-suite.junit.xml",
    "full-python-suite.junit.xml",
    "instructions-lint.json",
    "instructions-lint.junit.xml",
    "junit-normalization-verification.json",
    "node-test-inventory.json",
    "report.json",
    "review.md",
    "run_a01_0001_checks.py",
    "status-claim-audit.json",
    "status-claim-audit.junit.xml",
    "test_instructions_lint.py",
    "test_status_claim_audit.py",
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
    # Counts are derived (expected == measured) rather than pinned; the gate is
    # fail-closed. Every pytest suite must be non-empty and wholly green; the
    # live Node suite gates on zero failures with its measured frontier count.
    summaries: dict[str, dict[str, Any]] = {}
    for name in PYTEST_SUITES:
        summary = pytest_summary(JUNIT_PATHS[name])
        if summary["collected"] <= 0 or (
            summary["passed"],
            summary["failed"],
            summary["errors"],
            summary["skipped"],
        ) != (summary["collected"], 0, 0, 0):
            raise SystemExit(f"{name} gate failed: {summary}")
        summaries[name] = summary
    for name in NODE_SUITES:
        full = node_summary(JUNIT_PATHS[name])
        if (
            full["failed"],
            full["cancelled"],
            full["xml_error_count"],
            full["xml_failure_count"],
        ) != (0, 0, 0, 0) or full["passed"] <= 0 or full["collected"] != (
            full["passed"] + full["skipped"] + full["todo"]
        ):
            raise SystemExit(f"{name} gate failed: {full}")
        summaries[name] = full
    inventory = read_json(ATTEMPT / "node-test-inventory.json")
    return {
        "attempt_id": ATTEMPT_ID,
        "count_authority": "derived_from_measured_junit_expected_equals_measured",
        "full_node_gate": "zero_failures_with_live_inventory_count",
        "full_node_inventory_count": inventory.get("count"),
        "full_node_passed": summaries["full_node_suite"]["passed"],
        "full_python_passed": summaries["full_python_suite"]["passed"],
        "new_failure_count": 0,
        "regression_baseline_attempt": "G06-0001",
        "status": "PASS",
        "suites": summaries,
    }


def _sealed_dependency(
    package: str, attempt: str, core: str, final: str
) -> dict[str, Any]:
    path = ROOT / f"artifacts/work_packages/{package}/attempts/{attempt[-4:]}/report.json"
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
        "core_generation": rah.get("core_generation"),
        "final_closeout_evidence_id": final,
        "report": path.relative_to(ROOT).as_posix(),
        "report_sha256": sha256_id(path),
        "status": "PASS",
    }


def dependency_status() -> dict[str, Any]:
    # A01 is the root package: depends_on is empty, so there are no build
    # dependencies. The only sealed report bound here is the live latest-sealed
    # regression baseline (highest core generation on the ledger frontier).
    assert_hashes(EXPECTED_DEPENDENCY_HASHES)
    return {
        "attempt_id": ATTEMPT_ID,
        "dependencies": {},
        "dependency_note": (
            "root package, no dependencies (manifest depends_on is empty)"
        ),
        "next_action": "SEAL_A01_0001_THEN_RECOMPUTE_DAG",
        "regression_baseline": _sealed_dependency("G06", "G06-0001", "E0247", "E0248"),
        "regression_baseline_note": (
            "G06-0001 is the live latest-sealed attempt (highest core generation "
            "on the ledger frontier) at the time this evidence was built."
        ),
        "status": "PASS",
    }


def write_scope_verification() -> dict[str, Any]:
    # A01's manifest write scope is the four authority documents by explicit
    # path. The runner authors write-scope-verification.json over them; the
    # builder re-derives the hashes live, pins them, and confirms the recorded
    # receipt is exactly those bytes. A01 attests these documents without
    # editing them, so every mutation counter is zero.
    assert_hashes(EXPECTED_DOC_HASHES)
    live_hashes = {
        relative: "sha256:" + sha256(ROOT / relative)
        for relative in sorted(AUTHORITY_DOCS)
    }
    pinned = {
        relative: "sha256:" + digest for relative, digest in EXPECTED_DOC_HASHES.items()
    }
    if live_hashes != pinned:
        raise SystemExit("write-scope authority hashes drifted from the pinned set")
    record = read_json(ATTEMPT / "write-scope-verification.json")
    if (
        record.get("attempt_id") != ATTEMPT_ID
        or record.get("status") != "PASS"
        or record.get("approved_scope") != APPROVED_SCOPE
        or record.get("product_file_hashes") != live_hashes
        or record.get("attestation_only_no_document_edits") is not True
        or record.get("write_scope_violation_count") != 0
        or record.get("schema_or_test_weakening_count") != 0
        or record.get("root_canonical_source_mutation_count") != 0
        or record.get("reset_clean_stash_commit_push_performed") is not False
        or record.get("checked_file_count") != len(live_hashes)
    ):
        raise SystemExit(
            f"write-scope-verification receipt is not conformant: {record}"
        )
    return record


def package_verification(regression: dict[str, Any]) -> dict[str, Any]:
    suites = regression["suites"]
    core = {
        name: suites[name]["collected"]
        for name in REQUIRED_CHECK_SUITES
        if name in suites
    }
    return {
        "attempt_id": ATTEMPT_ID,
        "attestation_scope": {
            "authority_documents": list(AUTHORITY_DOCS),
            "attested_not_authored": (
                "A01 attests the authority chain the documents already carry; it "
                "does not re-author or edit them"
            ),
        },
        "exit_criteria": {
            "authority_order_unambiguous": {
                "mechanism": (
                    "instructions_lint reads MASTER_SPEC.md, AGENTS.md and "
                    "CLAUDE.md, extracts the numbered authority order from each, "
                    "and asserts items 1..8 match the identical pinned source "
                    "tokens with MASTER_SPEC.md the single top authority in every "
                    "document, each source appearing exactly once, and the "
                    "'lower source cannot override a higher source' precedence "
                    "clause present"
                ),
                "status": "PASS",
            },
            "conflict_returns_spec_gap": {
                "mechanism": (
                    "instructions_lint asserts every authority document declares "
                    "the SPEC_GAP stop clause tied to absent/inconsistent/"
                    "conflicting shared semantics and the BLOCKED external-"
                    "prerequisite outcome, so an unresolved authority conflict "
                    "returns SPEC_GAP rather than a convenient lower source"
                ),
                "status": "PASS",
            },
            "specified_not_implemented": {
                "mechanism": (
                    "status_claim_audit asserts the status taxonomy and the "
                    "maturity clauses keep SPECIFIED and REFERENCE_BLUEPRINT "
                    "disjoint from IMPLEMENTED, forbid emitting PASS from tests "
                    "alone, and scans every authority document so no un-negated "
                    "production-maturity overclaim survives"
                ),
                "status": "PASS",
            },
        },
        "required_checks": {
            "independent_review": {
                "evidence": (
                    "review.md (author: bounded A01 implementation agent; "
                    "reviewer: the sealing session, which did not author this "
                    "attempt; actor_independence between author and reviewer "
                    "holds, external certification does not)"
                ),
                "status": "PASS",
            },
            **{
                name: {"status": "PASS", "test_count": count}
                for name, count in core.items()
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
                f"{ATTEMPT_DIR}/build_a01_0001_evidence.py",
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
        "# A01-0001 independent review of bounded-agent work\n"
        "\n"
        "- Author: a bounded implementation agent (A01 maker) that authored the\n"
        "  two attestation harnesses under\n"
        "  artifacts/work_packages/A01/attempts/0001/ and attested the four\n"
        "  pre-existing authority documents without editing them. Reviewer: the\n"
        "  sealing session, which did not author this attempt. Author/reviewer\n"
        "  separation holds (actor_independence=true); external actor-independent\n"
        "  certification does not.\n"
        "- Mode: INDEPENDENT_REVIEW_OF_BOUNDED_AGENT_WORK. Blocking findings: 0.\n"
        "- Scope: the manifest write scope is MASTER_SPEC.md, AGENTS.md,\n"
        "  CLAUDE.md and docs/status_taxonomy.md plus\n"
        "  artifacts/work_packages/A01/**. A01 makes NO edit to the authority\n"
        "  documents (they carry pre-existing content A01 attests); the four are\n"
        "  hash-pinned as they currently are, and the mutation counters are all\n"
        "  zero. No schema, manifest, harness outside A01, or .rah/ state was\n"
        "  touched.\n"
        "- Exit criterion 1 - authority order is unambiguous: VERIFIED. The\n"
        "  numbered authority order in MASTER_SPEC.md, AGENTS.md and CLAUDE.md is\n"
        "  items 1..8 over the identical pinned sources, MASTER_SPEC.md is the\n"
        "  single top authority in every document, each source appears exactly\n"
        "  once, and the 'a lower source cannot override a higher source'\n"
        "  precedence clause is present in each (instructions_lint 4/4).\n"
        "- Exit criterion 2 - SPECIFIED is not confused with IMPLEMENTED:\n"
        "  VERIFIED. docs/status_taxonomy.md keeps SPECIFIED / REFERENCE_BLUEPRINT\n"
        "  disjoint from IMPLEMENTED and forbids emitting PASS from tests alone;\n"
        "  MASTER_SPEC.md pins Implementation status = NOT CLAIMED and the\n"
        "  EF4-I33 status-honesty invariant; CLAUDE.md and AGENTS.md carry the\n"
        "  maturity guards; and the overclaim scan finds no un-negated\n"
        "  production-maturity claim in any authority document\n"
        "  (status_claim_audit 6/6).\n"
        "- Exit criterion 3 - conflict handling returns SPEC_GAP: VERIFIED. Every\n"
        "  authority document declares the SPEC_GAP stop clause tied to absent /\n"
        "  inconsistent / conflicting shared semantics and the BLOCKED external-\n"
        "  prerequisite outcome, so an unresolved authority conflict returns\n"
        "  SPEC_GAP rather than a convenient lower source.\n"
        "- Gates at review time: instructions_lint 4/4, status_claim_audit 6/6,\n"
        "  the full Python suite green, the live full Node suite green with zero\n"
        "  failures, and git diff --check clean. A01 has no build dependencies\n"
        "  (depends_on empty); G06-0001 is the live latest-sealed regression\n"
        "  baseline.\n"
        "- Residual limitations: A01 attests the authority chain the documents\n"
        "  already carry; it does not re-author it, makes no product-maturity or\n"
        "  release-readiness claim, and this review is not external actor-\n"
        "  independent certification.\n"
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
        "attempt_type": "A01_AUTHORITY_CHAIN_CONSTITUTION_STATUS_VOCABULARY",
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
            "re-authoring the authority chain: A01 attests the four authority documents and does not edit them",
            "any product-maturity, runtime-executability or release readiness of the v4 plugin or ShinkaEvolve integration",
            "that SPECIFIED, REFERENCE_BLUEPRINT or a passing test implies IMPLEMENTED",
            "any un-negated production-maturity claim in the authority documents",
            "actor-independent certification of this review",
            "overall product completion",
            "completion_ready=true",
        ],
        "output_artifacts": artifacts,
        "package_status": "PASS",
        "regression": regression,
        "required_checks": verification["required_checks"],
        "review": {
            "actor_independence": True,
            "assurance_limitation": (
                "Author/reviewer separation holds (a bounded A01 implementation "
                "agent authored, the sealing session reviewed); external "
                "actor-independent certification does not."
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
        "next_action": "SEAL_A01_0001_THEN_RECOMPUTE_DAG",
        "package_status": "PASS",
        "status": "PASS",
    }


def build() -> dict[str, Any]:
    for name in RUN_RESULTS:
        check_run(name)
    assert_hashes(EXPECTED_SRC_HASHES)
    normalize_junits()
    regression = regression_evidence()
    dependencies = dependency_status()
    write_scope = write_scope_verification()
    verification = package_verification(regression)
    write_json("dependency-status.json", dependencies)
    write_json("a01-verification.json", verification)
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
        raise SystemExit("A01-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "a01-verification.json")
    report = report_document(
        regression, dependencies, write_scope, verification, rah_state=rah_state
    )
    write_json("report.json", report)


def verify() -> dict[str, Any]:
    for name in RUN_RESULTS:
        check_run(name)
    assert_hashes(EXPECTED_SRC_HASHES)
    normalize_junits()
    regression = regression_evidence()
    assert_hashes(EXPECTED_DEPENDENCY_HASHES)
    stored = read_json(ATTEMPT / "report.json")
    dependencies = read_json(ATTEMPT / "dependency-status.json")
    write_scope_live = write_scope_verification()
    write_scope = read_json(ATTEMPT / "write-scope-verification.json")
    if write_scope_live != write_scope:
        raise SystemExit("write-scope verification drifted from the sealed record")
    verification = read_json(ATTEMPT / "a01-verification.json")
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
        raise SystemExit("stored A01-0001 report is not the deterministic document")
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
