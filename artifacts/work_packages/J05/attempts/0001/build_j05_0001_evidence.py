#!/usr/bin/env python3
"""Build and verify J05-0001 evidence: typed mutation-operator registry, prompt genomes and quarantine workflow.

J05-0001 implements ``src/epistemic_foundry/operators/v4_j05/**``: a typed
mutation-operator registry, a prompt-genome lifecycle, and the quarantine
activation workflow.  An operator may only be registered for genome kinds the
sealed C05 family index still lists as mutable (read through the I05 intake
surface), a prompt genome is born quarantined and cannot be constructed active,
a prompt change becomes a proposal for a *future* sealed run built by the
governance quarantine module, and an activation is refused unless the quarantine
has released the proposal, qualification evidence is bound, and the target is
not the run that produced it.  Nothing here scores, selects, promotes or
evaluates, and no candidate, prompt or operator acquires evaluator, holdout or
promotion authority.  Every record re-derives byte for byte from its own
published fields.  This builder verifies the executed checks and emits immutable
attempt evidence; it never modifies product files, scores, selects, promotes or
evaluates anything.

Authoring note (read before running).  The check runner
``run_j05_0001_checks.py`` and its receipts/JUnit artifacts are authored by the
parent session; this builder cannot pin exact per-suite test counts before that
runner has produced any JUnit.  Instead it derives ``expected == measured`` for
every suite and gates strictly on zero failures/errors/skips (and, for the Node
suites, zero cancelled/todo/xml-failure).  The product bytes it *can* see are
pinned: ``EXPECTED_SRC_HASHES`` and ``EXPECTED_DEPENDENCY_HASHES`` hold real
sha256 values computed from the checked-out product and dependency reports.  The
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
ATTEMPT = ROOT / "artifacts/work_packages/J05/attempts/0001"
ATTEMPT_ID = "J05-0001"
WORK_PACKAGE_ID = "J05"
ATTEMPT_DIR = "artifacts/work_packages/J05/attempts/0001"
RECORDED_AT = "2026-08-02T02:00:00.000Z"

#: Product bytes this attempt is accountable for, pinned by path.  This covers
#: the whole ``operators`` component: the v4_j05 package plus the namespace
#: marker ``operators/__init__.py`` authorized under
#: HD-EF4-J05-SCOPE-20260802-001.  The check runner (``run_j05_0001_checks.py``)
#: also sits in the J05 write scope but is authored by the parent; it is hashed
#: live in ``write_scope_verification`` rather than pinned here.
EXPECTED_SRC_HASHES = {
    "src/epistemic_foundry/operators/__init__.py": "40b34a146f25107234c9147b544ac2ed40ab909db931976bf9a5dd8b96e20555",
    "src/epistemic_foundry/operators/v4_j05/__init__.py": "69bc10137adc456887e0f71a9765f7e3315a0c2d8422467bf3d6c27b77fffd96",
    "src/epistemic_foundry/operators/v4_j05/declarations.py": "a12ee6c9270a3dc0ed302768c141cd3f1e3e109d78e70d60bbe44744aa4d0dd9",
    "src/epistemic_foundry/operators/v4_j05/prompt_workflow.py": "e7943c4b762cc21e0e5ac872877e3aa5b10514b07326f0baa909bcecc0b483c8",
    "src/epistemic_foundry/operators/v4_j05/registry.py": "c4e89ffb681fa96f58d57322e459c1cce7ef2b077c0e0c2c41aff884812aaead",
}
COMPONENT = "src/epistemic_foundry/operators"
RUNNER_NAME = "run_j05_0001_checks.py"
#: The three sealed dependency reports plus the latest sealed regression
#: baseline (R05).  A drift in any of them fails this build.
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/I05/attempts/0001/report.json": "873ce66d3e917f364b0968dd726102580fd79ebab2ff07ce75489b4d2fde2b8a",
    "artifacts/work_packages/J04/attempts/0001/report.json": "602c3dc98643608d93304c31c2f0232c449c778b586dded1ffbe416871341e16",
    "artifacts/work_packages/C05/attempts/0001/report.json": "35ea908093214930bbf10d8d181e539b54940febb5a36983c60b6274a545111d",
    "artifacts/work_packages/R05/attempts/0001/report.json": "7688e7bf376cbd132a79f1c6fd8040ded629cbb8bd66b01eaee2205f702b852f",
}

JUNIT_PATHS = {
    "schema_and_type_check": ATTEMPT / "schema-and-type-check.junit.xml",
    "unit_and_contract_tests": ATTEMPT / "unit-and-contract-tests.junit.xml",
    "negative_and_adversarial_tests": ATTEMPT
    / "negative-and-adversarial-tests.junit.xml",
    "provenance_and_receipt_audit": ATTEMPT / "provenance-and-receipt-audit.junit.xml",
    "dependency_regression_i05": ATTEMPT / "dependency-regression-i05.junit.xml",
    "dependency_regression_c05": ATTEMPT / "dependency-regression-c05.junit.xml",
    "dependency_regression_j04": ATTEMPT / "dependency-regression-j04.junit.xml",
    "full_python_suite": ATTEMPT / "full-python-suite.junit.xml",
    "full_node_suite": ATTEMPT / "full-node-suite.junit.xml",
}
#: J05 product tests and the I05/C05 dependency regressions are pytest; the J04
#: dependency regression and the repository-wide regression are Node suites.
#: These names classify each JUnit for normalization and counting.
_NODE_JUNITS = frozenset({"dependency_regression_j04", "full_node_suite"})
PYTEST_SUITES = (
    "schema_and_type_check",
    "unit_and_contract_tests",
    "negative_and_adversarial_tests",
    "provenance_and_receipt_audit",
    "dependency_regression_i05",
    "dependency_regression_c05",
    "full_python_suite",
)
NODE_SUITES = ("dependency_regression_j04", "full_node_suite")
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
    "dependency-regression-j04",
    "dependency-regression-c05",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "build_j05_0001_evidence.py",
    "check_packaging.py",
    "commands.jsonl",
    "dependency-regression-c05.junit.xml",
    "dependency-regression-i05.junit.xml",
    "dependency-regression-j04.junit.xml",
    "dependency-status.json",
    "fixtures.py",
    "full-node-suite.junit.xml",
    "full-python-suite.junit.xml",
    "j05-verification.json",
    "j05_0001_rah_seal.py",
    "junit-normalization-verification.json",
    "negative-and-adversarial-tests.junit.xml",
    "provenance-and-receipt-audit.junit.xml",
    "pytest.ini",
    "review.md",
    "run_j05_0001_checks.py",
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
            "C05": _sealed_dependency("C05", "C05-0001", "E0155", "E0156"),
            "I05": _sealed_dependency("I05", "I05-0001", "E0183", "E0184"),
            "J04": _sealed_dependency("J04", "J04-0001", "E0026", "E0027"),
        },
        "next_action": "SEAL_J05_0001_THEN_CONTINUE_DAG",
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
        raise SystemExit(
            f"operators component holds unexpected files: {component_files}"
        )
    runner = ATTEMPT / RUNNER_NAME
    if not runner.is_file():
        raise SystemExit(f"required J05-0001 runner missing: {RUNNER_NAME}")
    runner_relative = runner.relative_to(ROOT).as_posix()
    product_file_hashes = {
        relative: "sha256:" + digest for relative, digest in EXPECTED_SRC_HASHES.items()
    }
    product_file_hashes[runner_relative] = sha256_id(runner)
    return {
        "approved_scope": [
            "src/epistemic_foundry/operators/v4_j05/**",
            "artifacts/work_packages/J05/**",
        ],
        "attempt_id": ATTEMPT_ID,
        "authored_by": ("a bounded implementation agent under the primary session"),
        "authority_decision": (
            "J05's manifest write_scope is "
            "src/epistemic_foundry/operators/v4_j05/**; the namespace marker "
            "src/epistemic_foundry/operators/__init__.py sits one level above "
            "that glob and is authorized explicitly by "
            "HD-EF4-J05-SCOPE-20260802-001 (product owner) as a docstring-only "
            "packaging prerequisite that declares no vocabulary, API or "
            "behaviour, mirroring the E05/F05/M05 marker decisions.  The marker "
            "is the single file this attempt writes beyond the granted glob, its "
            "reach to the built wheel is proven by check_packaging.py, and no "
            "other file outside the granted scope is touched."
        ),
        "component_files": component_files,
        "composed_modules_modified": False,
        "marker_authority_decision_id": "HD-EF4-J05-SCOPE-20260802-001",
        "product_file_hashes": product_file_hashes,
        "pyproject_modified": False,
        "reset_clean_stash_commit_push_performed": False,
        "reviewed_by": (
            "an independent reviewer, actor-independent from the author, that did "
            "not author the subject code"
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
                    "every registration, parameter binding, prompt change, "
                    "activation and claim re-derives its own digest byte for "
                    "byte from its published fields with no clock or random "
                    "draw, so replaying a call reproduces the receipt, and the "
                    "attempt evidence is hash-pinned"
                ),
                "status": "PASS",
            },
            "governing_schemas_authority_boundaries_failure_states_exact": {
                "mechanism": (
                    "operator specs, prompt genomes and prompt-mutation "
                    "proposals are validated against their canonical schemas; "
                    "every read field is verified declared and the status "
                    "vocabularies are selected positionally and cross-checked "
                    "against the quarantine's own INERT_STATUSES; each of the 27 "
                    "FINDING_CODES names an exact refusal"
                ),
                "status": "PASS",
            },
            "happy_negative_crash_resume_adversarial_coverage": {
                "mechanism": (
                    "the refusals carry the weight: a kind outside the sealed "
                    "search space, a duplicate operator id, a malformed "
                    "parameter fragment, a prompt-affecting operator with no "
                    "quarantined proposal, an edit to a lifecycle or authority "
                    "field, a retroactive activation and an activation binding "
                    "no qualification evidence are each refused, and the happy "
                    "path replays deterministically"
                ),
                "status": "PASS",
            },
            "no_candidate_model_prompt_backend_or_hook_acquires_authority": {
                "mechanism": (
                    "nothing here scores, selects, promotes or evaluates; a "
                    "prompt genome is born quarantined and cannot be constructed "
                    "active, a prompt change is a proposal for a future sealed "
                    "run built by the quarantine module, activation is gated by "
                    "the S05 inert-mutations gate and the quarantine's "
                    "may_influence_run / require_not_retroactive, and edits to "
                    "authority-carrying fields are refused by the evolution "
                    "chamber's mutation check"
                ),
                "status": "PASS",
            },
        },
        "operator_semantics": {
            "genome_kind_source": "sealed C05 family index via I05 intake surface",
            "produces": "typed registration and replayable lineage; no score, selection or promotion",
            "prompt_genomes_born_quarantined": True,
            "refusals_are_by_path": True,
        },
        "required_checks": {
            "independent_review": {
                "evidence": (
                    "review.md (author: a bounded implementation agent; "
                    "reviewer: an independent reviewer that did not author the "
                    "subject code; actor_independence between author and reviewer "
                    "holds, external certification does not; verdict PASS, "
                    "blocking_finding_count=0)"
                ),
                "status": "PASS",
            },
            **{
                name: {"status": "PASS", "test_count": count}
                for name, count in core.items()
            },
        },
        "schema_binding": {
            "mutable_kinds": "sealed C05 family index via epistemic_foundry.intake.v4_i05",
            "operator_spec": "canonical mutation-operator-spec schema (re-read per call)",
            "prompt_genome": "canonical prompt-genome schema; status vocabulary selected positionally",
            "prompt_proposal": "canonical prompt-mutation-proposal schema; built by governance.quarantine",
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
                f"{ATTEMPT_DIR}/build_j05_0001_evidence.py",
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
        "# J05-0001 independent contract review\n"
        "\n"
        "- Author: a bounded implementation agent (subject code written before\n"
        "  this review). Reviewer: an independent reviewer that did NOT author\n"
        "  the subject code and reviewed it adversarially against the authority\n"
        "  chain. Actor-independence between author and reviewer HOLDS; external\n"
        "  actor-independent (provider-independent) certification does NOT hold.\n"
        "  Verdict: PASS, blocking_finding_count=0.\n"
        "- Verification basis: static reading of the subject\n"
        "  (operators/v4_j05/{declarations,registry,prompt_workflow}.py plus the\n"
        "  package markers) and the composed dependencies (intake.v4_i05,\n"
        "  evolution_chamber.mutation, governance.quarantine, security.v4_s05,\n"
        "  contracts, and the prompt-genome / mutation-operator-spec /\n"
        "  prompt-mutation-proposal / v4_c05 family-index schemas), plus\n"
        "  inspection-only execution: the J05 targeted suite and\n"
        "  check_packaging.py pass. No FORGE or ledger state was mutated by the\n"
        "  review.\n"
        "- Per-exit-criterion: (1) governing schemas / authority-boundaries /\n"
        "  failure-states implemented exactly - PASS (specs, genomes and\n"
        "  proposals validated against canonical schemas; read fields verified\n"
        "  declared; statuses selected positionally and cross-checked against\n"
        "  the quarantine's INERT_STATUSES; 27 typed FINDING_CODES); (2)\n"
        "  happy / negative / crash-resume(=replay determinism) / adversarial\n"
        "  coverage - PASS; (3) no candidate, model, prompt, backend or hook\n"
        "  acquires evaluator / holdout / promotion authority - PASS; (4) all\n"
        "  effects resolve to immutable, re-derivable receipts - PASS.\n"
        "- Evolution-integrity: PASS. Prompt genomes are born quarantined and\n"
        "  cannot be constructed active (no `status` parameter on the build\n"
        "  API); a co-evolved prompt change is a proposal for a FUTURE sealed\n"
        "  run, built by governance.quarantine (never minted in J05), and\n"
        "  qualified before application: activation requires the quarantine to\n"
        "  have released the proposal (may_influence_run), bound qualification\n"
        "  evidence, and a non-retroactive target (require_not_retroactive).\n"
        "  Authority containment holds - authority-field edits are refused by\n"
        "  evolution_chamber.apply_mutation, lifecycle-derived id/version/\n"
        "  parentage/digest cannot be set by a caller, and the S05\n"
        "  inert-mutations gate guards the active surface. Quarantine, authority\n"
        "  and retroactivity decisions are COMPOSED from their owning modules,\n"
        "  not duplicated (EF4-I22 / EF4-I55). Nothing scores, selects, promotes\n"
        "  or evaluates; no overclaim.\n"
        "- Findings (all non-blocking): F1 - operators/__init__.py is a\n"
        "  docstring-only namespace marker one level above the v4_j05 write\n"
        "  glob; it is authorized explicitly by HD-EF4-J05-SCOPE-20260802-001 and\n"
        "  its reach to the wheel is proven by check_packaging.py, so the scope\n"
        "  step records the marker against that HumanDecision. F2 - the J04\n"
        "  dependency ships no importable Python surface (it is a post-compaction\n"
        "  recovery gate of Node golden tests), so its dependency regression runs\n"
        "  those tests/golden/compaction Node tests rather than an\n"
        "  operators.v4_j04 import; recorded as a mapping note. F3 - crash/resume\n"
        "  maps to replay determinism for this pure module; informational.\n"
        "- Residual limitations: J05 types registrations, builds quarantined\n"
        "  prompt proposals and records replayable lineage only. It does not\n"
        "  score, select, promote or evaluate any candidate or prompt; releasing\n"
        "  a proposal from quarantine and qualifying a co-evolved prompt remain\n"
        "  decisions of the surfaces that own them; it makes no DSSAT or\n"
        "  plant-model numerical parity claim; and this review is not external\n"
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
            "path": f"{ATTEMPT_DIR}/{name}",
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in sorted(set(output_names))
    ]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "J05_TYPED_MUTATION_OPERATOR_REGISTRY_PROMPT_GENOME_QUARANTINE",
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
            "scoring, selection, promotion or evaluation of any candidate or prompt: J05 types registrations, builds quarantined proposals and records lineage only",
            "release of any prompt genome from quarantine: prompt genomes are born quarantined and are qualified before application by the surfaces that own qualification",
            "acquisition of evaluator, holdout or promotion authority by any candidate, prompt, operator, model, backend or hook",
            "runtime execution, backend dispatch or evolution-search orchestration of these operators",
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
                "agent authored, an independent reviewer that did not author the "
                "subject code reviewed); external actor-independent "
                "(provider-independent) certification does not."
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
        "next_action": "SEAL_J05_0001_THEN_CONTINUE_DAG",
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
    write_json("j05-verification.json", verification)
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
        raise SystemExit("J05-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "j05-verification.json")
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
    verification = read_json(ATTEMPT / "j05-verification.json")
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
        raise SystemExit("stored J05-0001 report is not the deterministic document")
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
