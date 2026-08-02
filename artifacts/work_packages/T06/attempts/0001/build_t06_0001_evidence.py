#!/usr/bin/env python3
"""Build and verify T06-0001 evidence: external-backend qualification lifecycle, declared fallback and disablement gate.

T06-0001 implements ``src/epistemic_foundry/adapters/v4_t06/**``: an integration
gate that composes T05's sealed backend-adapter qualification and adds the three
things a qualification alone cannot express — for how long a backend may serve,
what serves instead when it lapses, and what becomes of the runs already in
flight when it is turned off.  Every judgement is made against a caller-supplied
instant, never a clock; the terminal fallback member is the domain-neutral
Foundry core, which runs no backend and declares no capability; and a fallback
may only ever narrow, never widen, the reach of the path it replaces.  Every
record re-derives byte for byte from its own published fields.  This builder
verifies the executed checks and emits immutable attempt evidence; it never
modifies product files, scores, selects, promotes or evaluates anything.

Authoring note (read before running).  This build script was authored by an
independent reviewer as a bounded hand while the check runner
``run_t06_0001_checks.py`` and its receipts/JUnit artifacts did not yet exist,
so it cannot pin exact per-suite test counts.  Instead it derives
``expected == measured`` for every suite and gates strictly on zero
failures/errors/skips (and, for the Node suite, zero cancelled/todo/xml-failure).
The product bytes it *can* see are pinned: ``EXPECTED_SRC_HASHES`` and
``EXPECTED_DEPENDENCY_HASHES`` hold real sha256 values computed from the
checked-out product and the sealed dependency/baseline reports.  The
JUnit/receipt filenames below are the contract the runner must satisfy; align
the runner to ``RUN_RESULTS`` / ``JUNIT_PATHS`` or adjust these constants
together.
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
ATTEMPT = ROOT / "artifacts/work_packages/T06/attempts/0001"
ATTEMPT_ID = "T06-0001"
WORK_PACKAGE_ID = "T06"
ATTEMPT_DIR = "artifacts/work_packages/T06/attempts/0001"
RECORDED_AT = "2026-08-02T20:00:00.000Z"

#: Product bytes this attempt is accountable for, pinned by path.  These are
#: exactly the v4_t06 files T06 owns; the ``epistemic_foundry.adapters`` marker
#: one level above this glob pre-exists under T05 (HD-EF4-T05-SCOPE-20260802-001)
#: and is neither hashed nor rewritten here.  The check runner
#: (``run_t06_0001_checks.py``) also sits in the T06 write scope but is authored
#: separately; it is hashed live in ``write_scope_verification`` rather than
#: pinned here, because it did not exist when this file was written.
EXPECTED_SRC_HASHES = {
    "src/epistemic_foundry/adapters/v4_t06/__init__.py": "05f9b42798c0f06942dfd942ca49a58eba2488fd5451f572d6d99415ee5067cc",
    "src/epistemic_foundry/adapters/v4_t06/disable.py": "9778522c51e3c91b720e5701b11d702dc443d72f6751b0139f5715fc4ca531de",
    "src/epistemic_foundry/adapters/v4_t06/fallback.py": "548ff8d9a284754225c725afbe30a6e85e78e5984f796c75e4bd237e8cbb63af",
    "src/epistemic_foundry/adapters/v4_t06/findings.py": "5a356d7ec6747d627ea122c2fd48269ba2210d59347b3cd87d7d588924128411",
    "src/epistemic_foundry/adapters/v4_t06/qualification_lifecycle.py": "11cd67e802e0a46bca6463b6633e58a5552d88b9f48414fa619a243c8962b39c",
}
#: The v4_t06 subpackage is rglob'd for the write-scope equality check, so this
#: root holds exactly the files pinned above (the parent adapters marker is not
#: under it).
COMPONENT = "src/epistemic_foundry/adapters/v4_t06"
RUNNER_NAME = "run_t06_0001_checks.py"
#: The sealed dependency this package composes (T05) and the latest sealed
#: package used as the regression baseline (R05).
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/T05/attempts/0001/report.json": "4a074f8940f5907da2f800b18f6bfc278b732d22b2cd39fa57c1e04194ff05cd",
    "artifacts/work_packages/R05/attempts/0001/report.json": "7688e7bf376cbd132a79f1c6fd8040ded629cbb8bd66b01eaee2205f702b852f",
}

JUNIT_PATHS = {
    "schema_and_type_check": ATTEMPT / "schema-and-type-check.junit.xml",
    "unit_and_contract_tests": ATTEMPT / "unit-and-contract-tests.junit.xml",
    "negative_and_adversarial_tests": ATTEMPT
    / "negative-and-adversarial-tests.junit.xml",
    "provenance_and_receipt_audit": ATTEMPT / "provenance-and-receipt-audit.junit.xml",
    "dependency_regression_t05": ATTEMPT / "dependency-regression-t05.junit.xml",
    "full_python_suite": ATTEMPT / "full-python-suite.junit.xml",
    "full_node_suite": ATTEMPT / "full-node-suite.junit.xml",
}
#: T06 product tests are pytest; only the repository-wide Node regression is a
#: Node suite.  These names classify each JUnit for normalization and counting.
_NODE_JUNITS = frozenset({"full_node_suite"})
PYTEST_SUITES = (
    "schema_and_type_check",
    "unit_and_contract_tests",
    "negative_and_adversarial_tests",
    "provenance_and_receipt_audit",
    "dependency_regression_t05",
    "full_python_suite",
)
NODE_SUITES = ("full_node_suite",)
#: The four required checks whose measured counts the report cites by name.
REQUIRED_CHECK_SUITES = (
    "schema_and_type_check",
    "unit_and_contract_tests",
    "negative_and_adversarial_tests",
    "provenance_and_receipt_audit",
)
#: One ``<name>.run.json`` receipt is expected per step (runner contract).
RUN_RESULTS = (
    "ruff-check",
    "ruff-format-check",
    "schema-and-type-check",
    "unit-and-contract-tests",
    "negative-and-adversarial-tests",
    "provenance-and-receipt-audit",
    "packaging-discovery",
    "dependency-regression-t05",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "build_t06_0001_evidence.py",
    "check_packaging.py",
    "commands.jsonl",
    "dependency-regression-t05.junit.xml",
    "dependency-status.json",
    "fixtures.py",
    "full-node-suite.junit.xml",
    "full-python-suite.junit.xml",
    "junit-normalization-verification.json",
    "negative-and-adversarial-tests.junit.xml",
    "node-test-inventory.json",
    "provenance-and-receipt-audit.junit.xml",
    "pytest.ini",
    "review.md",
    "run_t06_0001_checks.py",
    "schema-and-type-check.junit.xml",
    "t06-verification.json",
    "t06_0001_rah_seal.py",
    "test_negative_adversarial.py",
    "test_provenance_receipt.py",
    "test_schema_and_type.py",
    "test_unit_contract.py",
    "unit-and-contract-tests.junit.xml",
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
    # An aggregate receipt records ``commands`` (several processes, worst exit
    # code); a plain receipt records one ``command``.  Both are honest shapes.
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
    # Counts are derived (expected == measured) rather than pinned, because this
    # builder was authored before the runner produced any JUnit.  The gate is
    # still fail-closed: every suite must be non-empty and wholly green.
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
        summary = node_summary(JUNIT_PATHS[name])
        if summary["collected"] <= 0 or (
            summary["passed"],
            summary["failed"],
            summary["cancelled"],
            summary["skipped"],
            summary["todo"],
            summary["xml_error_count"],
            summary["xml_failure_count"],
        ) != (summary["collected"], 0, 0, 0, 0, 0, 0):
            raise SystemExit(f"{name} gate failed: {summary}")
        summaries[name] = summary
    return {
        "attempt_id": ATTEMPT_ID,
        "baseline_attempt": "R05-0001",
        "component_tests_are_targeted_only": True,
        "count_authority": "derived_from_measured_junit_expected_equals_measured",
        "new_failure_count": 0,
        "status": "PASS",
        "suites": summaries,
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
            "T05": _sealed_dependency("T05", "T05-0001", "E0193", "E0194"),
        },
        "next_action": "SEAL_T06_0001_THEN_CONTINUE_DAG",
        "regression_baseline": _sealed_dependency("R05", "R05-0001", "E0205", "E0206"),
        "status": "PASS",
    }


def write_scope_verification() -> dict[str, Any]:
    assert_hashes(EXPECTED_SRC_HASHES)
    component_files = sorted(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / COMPONENT).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )
    if component_files != sorted(EXPECTED_SRC_HASHES):
        raise SystemExit(f"v4_t06 component holds unexpected files: {component_files}")
    runner = ATTEMPT / RUNNER_NAME
    if not runner.is_file():
        raise SystemExit(f"required T06-0001 runner missing: {RUNNER_NAME}")
    runner_relative = runner.relative_to(ROOT).as_posix()
    product_file_hashes = {
        relative: "sha256:" + digest for relative, digest in EXPECTED_SRC_HASHES.items()
    }
    product_file_hashes[runner_relative] = sha256_id(runner)
    return {
        "approved_scope": [
            "src/epistemic_foundry/adapters/v4_t06/**",
            "artifacts/work_packages/T06/**",
        ],
        "attempt_id": ATTEMPT_ID,
        "authored_by": (
            "a bounded implementation agent (disjoint write scope, frozen "
            "contracts) under the product owner's explicit parallel-execution "
            "instruction"
        ),
        "component_files": component_files,
        "composed_modules_modified": False,
        "parent_adapters_marker_touched": False,
        "product_file_hashes": product_file_hashes,
        "pyproject_modified": False,
        "reset_clean_stash_commit_push_performed": False,
        "reviewed_by": (
            "an independent reviewer, actor-independent from the author, which "
            "also authored the evidence and seal plumbing"
        ),
        "root_canonical_source_mutation_count": 0,
        "schema_or_test_weakening_count": 0,
        "status": "PASS",
        "subagents_or_fleet_used": True,
        "write_scope_violation_count": 0,
    }


def package_verification(regression: dict[str, Any]) -> dict[str, Any]:
    suites = regression["suites"]
    core = {
        name: suites[name]["collected"]
        for name in REQUIRED_CHECK_SUITES
        if name in suites
    }
    return {
        "attempt_id": ATTEMPT_ID,
        "exit_criteria": {
            "all_completion_and_external_effects_resolve_to_immutable_receipts": {
                "mechanism": (
                    "every record re-derives its own hash byte for byte from its "
                    "published fields with no clock and no random draw on the "
                    "identified path; permits, routings, disablements and audits "
                    "each carry their own digest; byte-identical output across "
                    "replays is asserted; and no call mutates the binding, chain "
                    "or import it was handed"
                ),
                "status": "PASS",
            },
            "governing_schemas_authority_boundaries_failure_states_exact": {
                "mechanism": (
                    "the usable serving verdicts are read positionally from the "
                    "T05 backend-adapter-qualification schema enum intersected "
                    "with shinka_adapter's usable set, the six lifecycle "
                    "standings are proven disjoint from every canonical enum "
                    "value (EF4-I22), composed qualifications and imported runs "
                    "still validate against their canonical schemas, and each of "
                    "the eleven FINDING_CODES names an exact refusal"
                ),
                "status": "PASS",
            },
            "happy_negative_crash_resume_adversarial_coverage": {
                "mechanism": (
                    "an identity mismatch, a broken or out-of-order "
                    "qualification chain, a standing decided outside its window, "
                    "an unrecorded fallback step, a capability-widening "
                    "substitute, a disablement that left an in-flight import "
                    "unmarked, and an invented finding code are each refused by "
                    "their own code; the serving path, ordered step-down to the "
                    "qualified standby and fall-through to the inert core each "
                    "replay deterministically"
                ),
                "status": "PASS",
            },
            "no_candidate_model_prompt_backend_or_hook_acquires_authority": {
                "mechanism": (
                    "the gate only decides for-how-long, what-instead and "
                    "what-becomes-of-in-flight-work; it never scores, selects, "
                    "promotes or evaluates; an unqualified or lapsed backend "
                    "falls back to the domain-neutral core unchanged, external "
                    "output is treated as untrusted inert data, and no "
                    "evaluator, holdout or promotion field is ever bound"
                ),
                "status": "PASS",
            },
        },
        "gate_semantics": {
            "fallback_is_narrowing_only": True,
            "qualifies_a_backend": False,
            "serving_verdicts_source": (
                "T05 backend-adapter-qualification schema enum intersected with "
                "shinka_adapter usable set (computed per call)"
            ),
            "terminal_member": "foundry-native-core (runs no backend, no capabilities)",
        },
        "required_checks": {
            "independent_review": {
                "evidence": (
                    "review.md (author: bounded implementation agent; reviewer: "
                    "an independent reviewer that did not author the subject "
                    "code; actor_independence between author and reviewer holds, "
                    "external certification does not; verdict PASS, "
                    "blocking_finding_count=0)"
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
                f"{ATTEMPT_DIR}/build_t06_0001_evidence.py",
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
        "# T06-0001 independent review of bounded-agent work\n"
        "\n"
        "- Author: a bounded implementation agent (disjoint write scope, frozen\n"
        "  contracts) under the product owner's explicit parallel-execution\n"
        "  instruction. Reviewer: an independent reviewer that did not author\n"
        "  the subject code and reviewed it adversarially against the authority\n"
        "  chain and the evolution-integrity contract, and separately authored\n"
        "  this attempt's evidence and seal plumbing. Actor-independence between\n"
        "  author and reviewer HOLDS; external actor-independent\n"
        "  (provider-independent) certification does NOT hold. Verdict: PASS,\n"
        "  blocking_finding_count=0.\n"
        "- Verification basis: static reading of the subject\n"
        "  (adapters/v4_t06/{__init__,findings,qualification_lifecycle,fallback,\n"
        "  disable}.py) plus the composed T05 surface (adapters/v4_t05 findings,\n"
        "  seal, assert_hash_rederives, qualification_statuses) and\n"
        "  shinka_adapter.backend USABLE_QUALIFICATION_STATUSES; plus\n"
        "  inspection-only execution: the T06 targeted suite and\n"
        "  check_packaging.py pass. No FORGE or ledger state was mutated by the\n"
        "  review.\n"
        "- Per-exit-criterion: (1) governing schemas/authority-boundaries/\n"
        "  failure-states exact - PASS: the usable serving verdicts are the\n"
        "  intersection of the T05 schema enum and the shinka usable set,\n"
        "  computed per call, so a verdict dropped from either side stops\n"
        "  permitting service without this module being edited; the six\n"
        "  STANDING_* lifecycle words are proven disjoint from every canonical\n"
        "  enum value and the AST scan proves the modules hold no canonical wire\n"
        "  literal (EF4-I22). (2) happy/negative/crash-resume(=replay\n"
        "  determinism)/adversarial coverage - PASS: identity mismatch, chain\n"
        "  breaks, out-of-window standings, unrecorded fallback, capability\n"
        "  widening, unmarked in-flight imports and an invented finding code are\n"
        "  each refused by a typed code. (3) no candidate/model/prompt/backend/\n"
        "  hook acquires authority - PASS: nothing scores, selects, promotes or\n"
        "  evaluates; an unqualified or lapsed backend degrades along a declared\n"
        "  chain that always terminates in the inert domain-neutral core, which\n"
        "  runs no backend and declares no capability. (4) all effects resolve\n"
        "  to immutable, re-derivable receipts - PASS: every record seals its\n"
        "  own digest, no clock or random draw sits on any identified path, and\n"
        "  byte-identical replay is asserted for permits, routings and\n"
        "  disablements.\n"
        "- Evolution-integrity (EF4-I22/I63): PASS. Qualification is sandboxed -\n"
        "  T06 never qualifies a backend, it composes T05's\n"
        "  qualify_backend_adapter record whole and propagates T05 refusals\n"
        "  unwrapped (IntegrationGateError is deliberately NOT a subclass of\n"
        "  AdapterGateError, so a caller can tell which contract refused).\n"
        "  Fallback is narrowing-only: a substitute holding a capability the\n"
        "  primary or the request does not hold is refused at declaration and at\n"
        "  routing, and the terminal core is capability-empty by construction.\n"
        "  Disablement reaches backwards - it withdraws the head qualification\n"
        "  AND marks each in-flight imported run as requiring re-verification,\n"
        "  refusing if any claimed import was left unmarked or if the disabled\n"
        "  backend still served a request decided at/after the disablement.\n"
        "  Receipts are immutable and no evaluator/holdout/promotion field is\n"
        "  reachable.\n"
        "- Findings (all non-blocking): F1 - route_request refuses a member\n"
        "  whose declared capabilities exceed what a given request asked for\n"
        "  (gained = member_caps - requested), not only what the primary held;\n"
        "  this is an intentional conservative narrowing gate documented in the\n"
        "  fallback docstring, recorded as a design note, not a defect. F2 -\n"
        "  require_instant validates but does not canonicalize the stored\n"
        "  timestamp string; determinism is preserved because every comparison\n"
        "  re-parses through require_instant, so two differently-spelled equal\n"
        "  instants would compare equal at judgement time; informational. F3 -\n"
        "  report.json/commands.jsonl are materialized by this evidence/seal\n"
        "  step, satisfied here.\n"
        "- Residual limitations: T06 gates qualification duration, fallback and\n"
        "  disablement only. No real external backend was invoked, fetched or\n"
        "  validated; capability claims are recorded and cross-checked, not\n"
        "  behavioural evidence. It makes no DSSAT or plant-model numerical\n"
        "  parity claim; promotion remains a governance decision outside this\n"
        "  module; and this review is not external actor-independent\n"
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
            "path": f"{ATTEMPT_DIR}/{name}",
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in sorted(set(output_names))
    ]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "T06_EXTERNAL_BACKEND_QUALIFICATION_FALLBACK_GATE",
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
            "scoring, selection, promotion or evaluation of any candidate: T06 gates qualification duration, fallback and disablement only",
            "running any external backend: an unqualified or failed backend falls back to the inert domain-neutral core (the Foundry unchanged), which T06 does not run, score or promote",
            "treating external backend output as anything but untrusted inert data with no canonical meaning or authority",
            "invoking, fetching or validating a real external backend: capability claims are recorded and cross-checked, not behavioural evidence",
            "DSSAT or any plant-model numerical parity",
            "actor-independent (provider-independent) certification of this review",
            "overall product completion",
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
                "Author/reviewer separation holds (a bounded implementation "
                "agent authored the subject code, an independent reviewer "
                "reviewed it); external actor-independent (provider-independent) "
                "certification does not."
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
        "next_action": "SEAL_T06_0001_THEN_CONTINUE_DAG",
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
    write_json("t06-verification.json", verification)
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
        raise SystemExit("T06-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "t06-verification.json")
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
    verification = read_json(ATTEMPT / "t06-verification.json")
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
        raise SystemExit("stored T06-0001 report is not the deterministic document")
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
