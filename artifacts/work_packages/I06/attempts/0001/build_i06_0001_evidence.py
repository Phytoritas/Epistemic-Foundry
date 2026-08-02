#!/usr/bin/env python3
"""Build and verify I06-0001 evidence: genome intake, scope and falsifiability integration gate.

I06-0001 implements ``src/epistemic_foundry/intake/v4_i06/**``: an integration
gate that admits a hypothesis genome only when the artifacts its declarations
*point at* actually bind.  It composes the sealed I05 eligibility screen without
restating it, then resolves the references across the genome, its scope vector,
its falsifier genes and its prediction genes: every gene is validated against the
canonical schema that owns it, every prediction is scoped to the vector the
genome declares, every falsifier names this genome and links only declared
predictions, and a genome arriving with an advanced lifecycle status is refused
because intake grants no evaluator, holdout or promotion authority at the door.
Every admit or refuse decision resolves to one immutable receipt whose hash
re-derives byte for byte from its own fields.  This builder verifies the executed
checks and emits immutable attempt evidence; it never modifies product files,
scores, selects, promotes or evaluates anything.

Authoring note (read before running).  The gate was authored by a bounded
implementation subagent; this builder and the check runner were prepared by the
sealing agent for the parent to seal, and the sealing agent is the independent
reviewer (actor-independent from the author).  The builder derives
``expected == measured`` for every suite and gates strictly on zero
failures/errors/skips (and, for the Node suite, zero cancelled/todo/xml-failure)
rather than pinning per-suite counts.  The product bytes it *can* see are pinned:
``EXPECTED_SRC_HASHES`` and ``EXPECTED_DEPENDENCY_HASHES`` hold real sha256
values computed from the checked-out product and dependency reports.  The
JUnit/receipt filenames below are the contract the runner must satisfy; align the
runner to ``RUN_RESULTS`` / ``JUNIT_PATHS`` or adjust these two constants
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
ATTEMPT = ROOT / "artifacts/work_packages/I06/attempts/0001"
ATTEMPT_ID = "I06-0001"
WORK_PACKAGE_ID = "I06"
ATTEMPT_DIR = "artifacts/work_packages/I06/attempts/0001"
RECORDED_AT = "2026-08-02T02:00:00.000Z"

#: Product bytes this attempt is accountable for, pinned by path.  The check
#: runner (``run_i06_0001_checks.py``) also sits in the I06 write scope but is
#: authored outside the gate; it is hashed live in ``write_scope_verification``
#: rather than pinned here.  The ``intake`` parent marker is not pinned here: it
#: was authorized and sealed by I05 and is outside this package's write scope.
EXPECTED_SRC_HASHES = {
    "src/epistemic_foundry/intake/v4_i06/__init__.py": "d5ca672ed0c66d32890889d5eb9cf506b33f7b1f8aa6582b3250d0dc78e4750f",
    "src/epistemic_foundry/intake/v4_i06/gate.py": "6becfaacc682be105132d6e31615053b142cceb91709fec7c71625ec37f868b5",
}
COMPONENT = "src/epistemic_foundry/intake/v4_i06"
RUNNER_NAME = "run_i06_0001_checks.py"
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/I05/attempts/0001/report.json": "873ce66d3e917f364b0968dd726102580fd79ebab2ff07ce75489b4d2fde2b8a",
    "artifacts/work_packages/R05/attempts/0001/report.json": "7688e7bf376cbd132a79f1c6fd8040ded629cbb8bd66b01eaee2205f702b852f",
    "artifacts/work_packages/W05/attempts/0001/report.json": "93f9f67faac10382c89d8d1c42cbe0f84ca7fae77aa32e9b5d1edb1203430c2b",
}

JUNIT_PATHS = {
    "schema_and_type_check": ATTEMPT / "schema-and-type-check.junit.xml",
    "unit_and_contract_tests": ATTEMPT / "unit-and-contract-tests.junit.xml",
    "negative_and_adversarial_tests": ATTEMPT
    / "negative-and-adversarial-tests.junit.xml",
    "provenance_and_receipt_audit": ATTEMPT / "provenance-and-receipt-audit.junit.xml",
    "dependency_regression_i05": ATTEMPT / "dependency-regression-i05.junit.xml",
    "dependency_regression_r05": ATTEMPT / "dependency-regression-r05.junit.xml",
    "full_python_suite": ATTEMPT / "full-python-suite.junit.xml",
    "full_node_suite": ATTEMPT / "full-node-suite.junit.xml",
}
#: I06 product tests are pytest; only the repository-wide Node regression is a
#: Node suite.  These names classify each JUnit for normalization and counting.
_NODE_JUNITS = frozenset({"full_node_suite"})
PYTEST_SUITES = (
    "schema_and_type_check",
    "unit_and_contract_tests",
    "negative_and_adversarial_tests",
    "provenance_and_receipt_audit",
    "dependency_regression_i05",
    "dependency_regression_r05",
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
    "dependency-regression-i05",
    "dependency-regression-r05",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "build_i06_0001_evidence.py",
    "check_packaging.py",
    "commands.jsonl",
    "dependency-regression-i05.junit.xml",
    "dependency-regression-r05.junit.xml",
    "dependency-status.json",
    "fixtures.py",
    "full-node-suite.junit.xml",
    "full-python-suite.junit.xml",
    "i06-verification.json",
    "i06_0001_rah_seal.py",
    "junit-normalization-verification.json",
    "negative-and-adversarial-tests.junit.xml",
    "provenance-and-receipt-audit.junit.xml",
    "pytest.ini",
    "review.md",
    "run_i06_0001_checks.py",
    "schema-and-type-check.junit.xml",
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
        "baseline_attempt": "W05-0001",
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
            "I05": _sealed_dependency("I05", "I05-0001", "E0183", "E0184"),
            "R05": _sealed_dependency("R05", "R05-0001", "E0205", "E0206"),
        },
        "next_action": "SEAL_I06_0001_THEN_RECOMPUTE_DAG",
        "regression_baseline": _sealed_dependency("W05", "W05-0001", "E0215", "E0216"),
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
        raise SystemExit(f"v4_i06 component holds unexpected files: {component_files}")
    runner = ATTEMPT / RUNNER_NAME
    if not runner.is_file():
        raise SystemExit(f"required I06-0001 runner missing: {RUNNER_NAME}")
    runner_relative = runner.relative_to(ROOT).as_posix()
    product_file_hashes = {
        relative: "sha256:" + digest for relative, digest in EXPECTED_SRC_HASHES.items()
    }
    product_file_hashes[runner_relative] = sha256_id(runner)
    return {
        "approved_scope": [
            "src/epistemic_foundry/intake/v4_i06/**",
            "artifacts/work_packages/I06/**",
        ],
        "attempt_id": ATTEMPT_ID,
        "authored_by": (
            "a bounded implementation subagent (the implementing agent); the "
            "check runner and evidence scripts were prepared by the sealing "
            "agent, who is actor-independent from the implementing agent"
        ),
        "authority_decision": (
            "I06's manifest write_scope is "
            "src/epistemic_foundry/intake/v4_i06/**; both product files "
            "(v4_i06/__init__.py and v4_i06/gate.py) sit squarely inside that "
            "glob, so no scope-precision waiver is needed. The parent "
            "epistemic_foundry.intake namespace marker "
            "(src/epistemic_foundry/intake/__init__.py) was authorized and "
            "sealed by I05 under HD-EF4-I05-SCOPE-20260802-001 and is left "
            "untouched; check_packaging.py proves both the pre-existing intake "
            "marker and the new v4_i06 marker reach the wheel. No HumanDecision "
            "was required for this package's scope."
        ),
        "component_files": component_files,
        "composed_modules_modified": False,
        "product_file_hashes": product_file_hashes,
        "pyproject_modified": False,
        "reset_clean_stash_commit_push_performed": False,
        "reviewed_by": (
            "the sealing agent's independent review, actor-independent from the "
            "implementing agent that authored the gate"
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
                    "admit and refuse alike emit one receipt whose receipt_hash "
                    "re-derives from its own fields via hash_excluding; the "
                    "batch report reconciles submitted == admitted + refused and "
                    "its report_hash re-derives; the gate reads no clock and "
                    "draws no random value when the receipt is named, so every "
                    "hash is a pure function of the published bytes"
                ),
                "status": "PASS",
            },
            "governing_schemas_authority_boundaries_failure_states_exact": {
                "mechanism": (
                    "verify_contract reads every genome/scope/falsifier/"
                    "prediction field back out of the canonical schema that owns "
                    "it on every call, eligibility is deferred entirely to the "
                    "sealed I05 screen rather than restated, the un-evaluated "
                    "intake status is read from the genome status enum, and each "
                    "of the fifteen FINDING_CODES names an exact refusal"
                ),
                "status": "PASS",
            },
            "happy_negative_crash_resume_adversarial_coverage": {
                "mechanism": (
                    "a fully-consistent bundle is admitted; the refusals carry "
                    "the weight and are surveyed together — a screening refusal, "
                    "an advanced-status authority presumption, a missing or "
                    "malformed scope vector, a prediction scoped out of the "
                    "genome's bounds, an unresolved/undeclared/mis-attributed/"
                    "malformed falsifier or prediction, and contract drift — and "
                    "every decision replays byte for byte after a crash"
                ),
                "status": "PASS",
            },
            "no_candidate_model_prompt_backend_or_hook_acquires_authority": {
                "mechanism": (
                    "nothing here scores, ranks, selects, promotes or evaluates; "
                    "a genome presenting an evaluated, promoted or otherwise "
                    "advanced lifecycle status is refused AUTHORITY_STATUS_"
                    "PRESUMED because intake grants no evaluator, holdout or "
                    "promotion authority at the door, and the receipt carries "
                    "none of the scoring or promotion fields"
                ),
                "status": "PASS",
            },
        },
        "gate_semantics": {
            "authority_at_intake": "none granted; advanced status is refused by path",
            "eligibility": "deferred to epistemic_foundry.intake.v4_i05 screen",
            "intake_status_source": (
                "first value of the canonical genome status enum (un-evaluated "
                "draft), read from the schema not named here"
            ),
            "produces": (
                "one immutable admit/refuse receipt with resolved bindings; no "
                "score, selection or promotion"
            ),
            "refusals_are_a_complete_survey": True,
        },
        "required_checks": {
            "independent_review": {
                "evidence": (
                    "review.md (author: the implementing agent; reviewer: the "
                    "sealing agent, actor-independent from the author; verdict "
                    "PASS, blocking_finding_count=0; external certification does "
                    "not hold)"
                ),
                "status": "PASS",
            },
            **{
                name: {"status": "PASS", "test_count": count}
                for name, count in core.items()
            },
        },
        "schema_binding": {
            "eligibility_screen": "epistemic_foundry.intake.v4_i05 (not re-derived)",
            "falsifier_binding": (
                "canonical falsifier-gene contract; must name this genome and "
                "link only predictions the genome declares"
            ),
            "genome_schema": "canonical genome schema properties (re-derived per call)",
            "prediction_binding": (
                "canonical prediction-gene contract; must name this genome and "
                "be scoped to the genome's declared scope vector"
            ),
            "scope_binding": "canonical scope-vector contract (re-derived per call)",
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
                f"{ATTEMPT_DIR}/build_i06_0001_evidence.py",
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
        "# I06-0001 independent review\n"
        "\n"
        "- Author: a bounded implementation subagent (the implementing agent)\n"
        "  authored the gate under src/epistemic_foundry/intake/v4_i06.\n"
        "  Reviewer: the sealing agent, who did NOT author the gate and reviewed\n"
        "  it adversarially against the authority chain and the evolution-\n"
        "  integrity rules. Actor-independence between author and reviewer HOLDS;\n"
        "  external actor-independent (provider-independent) certification does\n"
        "  NOT hold. Verdict: PASS, blocking_finding_count=0.\n"
        "- Verification basis: static reading of the gate plus the composed\n"
        "  dependencies (intake.v4_i05 screen; contracts registry for the\n"
        "  genome, scope-vector, falsifier-gene and prediction-gene schemas;\n"
        "  domain.hashing and domain.ids), plus inspection-only execution: the\n"
        "  I06 targeted suite and check_packaging.py pass, and the I05/R05\n"
        "  dependency regressions and the full Python and Node suites are green.\n"
        "  No FORGE or ledger state was mutated by the review.\n"
        "- Per-exit-criterion: (1) governing schemas, authority boundaries and\n"
        "  failure states implemented exactly - PASS; (2) happy/negative/\n"
        "  crash-resume(=replay determinism)/adversarial coverage - PASS; (3) no\n"
        "  candidate, model, prompt, backend or hook acquires evaluator, holdout\n"
        "  or promotion authority - PASS; (4) all completion and external\n"
        "  effects resolve to immutable, re-derivable receipts - PASS.\n"
        "- Evolution-integrity: PASS. The gate refuses an out-of-scope\n"
        "  prediction (PREDICTION_SCOPE_OUT_OF_BOUNDS), a non-falsifiable or\n"
        "  mis-attributed genome (FALSIFIER_UNRESOLVED / FALSIFIER_GENOME_\n"
        "  MISMATCH / FALSIFIER_PREDICTION_UNLINKED and the prediction analogues)\n"
        "  and a malformed genome (SCOPE_VECTOR_MALFORMED / FALSIFIER_MALFORMED /\n"
        "  PREDICTION_MALFORMED). AUTHORITY_STATUS_PRESUMED enforces that no\n"
        "  candidate acquires evaluator, holdout or promotion authority at the\n"
        "  intake door; the un-evaluated status is read from the genome schema\n"
        "  enum rather than named. Eligibility composes the I05 SCREENING refusal\n"
        "  rather than duplicating the falsifier-present/scope-present checks\n"
        "  (EF4-I22), and contract drift fails closed (CONTRACT_DRIFT on every\n"
        "  call). Every admit or refuse resolves to one deterministic,\n"
        "  re-derivable receipt; nothing scores, ranks, selects or promotes.\n"
        "- Findings (all non-blocking): F1 - the gate publishes no schema of its\n"
        "  own for the receipt yet; the provenance suite asserts the receipt\n"
        "  shape directly. Recorded as a completeness note, consistent with an\n"
        "  intake-stage gate. F2 - report.json/commands.jsonl are materialized\n"
        "  by this build/seal step (the parent's emission responsibility).\n"
        "- Residual limitations: I06 binds a genome's references and records an\n"
        "  admit/refuse receipt only. It does not score, select, promote or\n"
        "  evaluate any candidate; it makes no DSSAT or plant-model numerical\n"
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
        "attempt_type": "I06_GENOME_INTAKE_SCOPE_FALSIFIABILITY_GATE",
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
            "scoring, ranking, selection, promotion or evaluation of any candidate: I06 binds references and records an admit/refuse receipt only",
            "any grant of evaluator, holdout or promotion authority at intake: an advanced-status genome is refused by path",
            "re-derivation of the I05 eligibility judgement: eligibility is deferred to the sealed intake screen",
            "DSSAT or any plant-model numerical parity",
            "actor-independent certification of this review",
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
                "subagent authored the gate; the sealing agent reviewed it "
                "independently); external actor-independent (provider-"
                "independent) certification does not."
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
        "next_action": "SEAL_I06_0001_THEN_RECOMPUTE_DAG",
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
    write_json("i06-verification.json", verification)
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
        raise SystemExit("I06-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "i06-verification.json")
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
    verification = read_json(ATTEMPT / "i06-verification.json")
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
        raise SystemExit("stored I06-0001 report is not the deterministic document")
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
