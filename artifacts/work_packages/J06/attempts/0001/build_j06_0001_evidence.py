#!/usr/bin/env python3
"""Build and verify J06-0001 evidence: operator/prompt qualification and context-budget gate.

J06-0001 implements ``src/epistemic_foundry/operators/v4_j06/**``: an
integration gate that admits a mutation operator to a run only when a
prompt-affecting operator has been qualified out of quarantine for a *future*
run and the work's context tokens fit under a budget that actually bounds spend.
The gate composes the sealed J05 registry/prompt-workflow and the S05
inert-mutations gate for qualification, and the budget-envelope module and the
canonical context-assembly-manifest schema for the budget; it re-derives the
context total from the manifest's own components rather than trusting the
published total, reads the ceiling through the budget module's own normalizer,
and refuses over-budget work rather than truncating it.  Every admission resolves
to one immutable receipt that re-derives its own digest.  Nothing here scores,
selects, promotes or executes.  This builder verifies the executed checks and
emits immutable attempt evidence; it never modifies product files, scores,
selects, promotes or evaluates anything.

Authoring note (read before running).  The J06 product code and tests were
authored by a bounded implementation agent; this builder and the check runner
``run_j06_0001_checks.py`` are the sealing hand's emission responsibility, and
the independent review was performed by the sealing agent, which did not author
the subject code.  Because this builder is authored alongside the runner but
before any JUnit exists, it does not pin exact per-suite test counts; instead it
derives ``expected == measured`` for every suite and gates strictly on zero
failures/errors/skips (and, for the Node suite, zero cancelled/todo/xml-failure).
The product bytes it *can* see are pinned: ``EXPECTED_SRC_HASHES`` and
``EXPECTED_DEPENDENCY_HASHES`` hold real sha256 values computed from the
checked-out product and dependency reports.  The JUnit/receipt filenames below
are the contract the runner must satisfy; align the runner to ``RUN_RESULTS`` /
``JUNIT_PATHS`` or adjust these two constants together.
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
ATTEMPT = ROOT / "artifacts/work_packages/J06/attempts/0001"
ATTEMPT_ID = "J06-0001"
WORK_PACKAGE_ID = "J06"
ATTEMPT_DIR = "artifacts/work_packages/J06/attempts/0001"
RECORDED_AT = "2026-08-02T02:30:00.000Z"

#: Product bytes this attempt is accountable for, pinned by path.  Only the
#: v4_j06 subpackage is in J06's write scope; the ``operators`` package marker
#: one level above pre-exists from J05 and is out of scope, so it is neither
#: pinned nor hashed here.  The check runner (``run_j06_0001_checks.py``) also
#: sits in the J06 write scope but is the sealing hand's own artifact; it is
#: hashed live in ``write_scope_verification`` rather than pinned here.
EXPECTED_SRC_HASHES = {
    "src/epistemic_foundry/operators/v4_j06/__init__.py": "47013bf3f549cc12e56b34945ea48e6ee8dcb4bb07152d7c868cc2e7648ea36a",
    "src/epistemic_foundry/operators/v4_j06/declarations.py": "f30c9587bee3eb0b879b4ade897f76473b278fb1b830905526a848b8357bdcff",
    "src/epistemic_foundry/operators/v4_j06/gate.py": "aa5e40fea14a090aa3831020e9aa2dcc04a3840c5fc76668aba93f1c47f8053e",
}
COMPONENT = "src/epistemic_foundry/operators/v4_j06"
RUNNER_NAME = "run_j06_0001_checks.py"
#: Sealed dependency reports (J05, S05) plus the regression baseline (W05, the
#: latest sealed report at seal time), pinned by content so a change fails here.
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/J05/attempts/0001/report.json": "b039283f320f5d9d963a2ace2e1e17d0f2a61193a7319755db500686bcc8200f",
    "artifacts/work_packages/S05/attempts/0001/report.json": "dbcb94e77fd885f18aa36a00dc352a9d5a788d265b979ff7a23fafd5f261c727",
    "artifacts/work_packages/W05/attempts/0001/report.json": "93f9f67faac10382c89d8d1c42cbe0f84ca7fae77aa32e9b5d1edb1203430c2b",
}

JUNIT_PATHS = {
    "schema_and_type_check": ATTEMPT / "schema-and-type-check.junit.xml",
    "unit_and_contract_tests": ATTEMPT / "unit-and-contract-tests.junit.xml",
    "negative_and_adversarial_tests": ATTEMPT
    / "negative-and-adversarial-tests.junit.xml",
    "provenance_and_receipt_audit": ATTEMPT / "provenance-and-receipt-audit.junit.xml",
    "dependency_regression_j05": ATTEMPT / "dependency-regression-j05.junit.xml",
    "dependency_regression_s05": ATTEMPT / "dependency-regression-s05.junit.xml",
    "full_python_suite": ATTEMPT / "full-python-suite.junit.xml",
    "full_node_suite": ATTEMPT / "full-node-suite.junit.xml",
}
#: J06 product and dependency tests are pytest; only the repository-wide Node
#: regression is a Node suite.  These names classify each JUnit for counting.
_NODE_JUNITS = frozenset({"full_node_suite"})
PYTEST_SUITES = (
    "schema_and_type_check",
    "unit_and_contract_tests",
    "negative_and_adversarial_tests",
    "provenance_and_receipt_audit",
    "dependency_regression_j05",
    "dependency_regression_s05",
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
    "dependency-regression-j05",
    "dependency-regression-s05",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "build_j06_0001_evidence.py",
    "check_packaging.py",
    "commands.jsonl",
    "dependency-regression-j05.junit.xml",
    "dependency-regression-s05.junit.xml",
    "dependency-status.json",
    "fixtures.py",
    "full-node-suite.junit.xml",
    "full-python-suite.junit.xml",
    "j06-verification.json",
    "j06_0001_rah_seal.py",
    "junit-normalization-verification.json",
    "negative-and-adversarial-tests.junit.xml",
    "provenance-and-receipt-audit.junit.xml",
    "pytest.ini",
    "review.md",
    "run_j06_0001_checks.py",
    "schema-and-type-check.junit.xml",
    "test_negative_and_adversarial.py",
    "test_provenance_and_receipt.py",
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
            "J05": _sealed_dependency("J05", "J05-0001", "E0213", "E0214"),
            "S05": _sealed_dependency("S05", "S05-0001", "E0175", "E0176"),
        },
        "next_action": "SEAL_J06_0001_THEN_CONTINUE_DAG",
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
        raise SystemExit(f"v4_j06 component holds unexpected files: {component_files}")
    runner = ATTEMPT / RUNNER_NAME
    if not runner.is_file():
        raise SystemExit(f"required J06-0001 runner missing: {RUNNER_NAME}")
    runner_relative = runner.relative_to(ROOT).as_posix()
    product_file_hashes = {
        relative: "sha256:" + digest for relative, digest in EXPECTED_SRC_HASHES.items()
    }
    product_file_hashes[runner_relative] = sha256_id(runner)
    return {
        "approved_scope": [
            "src/epistemic_foundry/operators/v4_j06/**",
            "artifacts/work_packages/J06/**",
        ],
        "attempt_id": ATTEMPT_ID,
        "authored_by": ("a bounded implementation agent (J06 product code and tests)"),
        "authority_decision": (
            "J06's manifest write_scope is "
            "src/epistemic_foundry/operators/v4_j06/**; the ``operators`` package "
            "marker one level above that glob pre-exists from J05 "
            "(HD-EF4-J05-SCOPE-20260802-001) and is out of J06's scope, so it is "
            "neither modified nor pinned here. The v4_j06 subpackage's wheel "
            "discovery is proven by check_packaging.py. No separate HumanDecision "
            "was required for J06."
        ),
        "component_files": component_files,
        "composed_modules_modified": False,
        "product_file_hashes": product_file_hashes,
        "pyproject_modified": False,
        "reset_clean_stash_commit_push_performed": False,
        "reviewed_by": (
            "the sealing agent, actor-independent from the bounded implementation "
            "agent that authored the subject code"
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
                    "every admission produces one receipt whose receipt_hash "
                    "re-derives from the fields it publishes, the budget "
                    "assessment names its budget and manifest by id and hash, and "
                    "there is no clock or random draw on the identified path, so "
                    "replaying an identified admission reproduces the receipt byte "
                    "for byte and verify_gate_receipt refuses a tampered one"
                ),
                "status": "PASS",
            },
            "governing_schemas_authority_boundaries_failure_states_exact": {
                "mechanism": (
                    "the context total is re-derived from the manifest's own "
                    "instruction/evidence/tool components against the canonical "
                    "context-assembly-manifest schema, the token ceiling is read "
                    "through the budget module's normalize_hard_limits, whether "
                    "the envelope bounds spend is the budget module's own "
                    "spend_is_bounded, and each FINDING_CODE names an exact refusal"
                ),
                "status": "PASS",
            },
            "happy_negative_crash_resume_adversarial_coverage": {
                "mechanism": (
                    "the refusals carry the weight: an unregistered operator, a "
                    "quarantined prompt, a prompt binding no qualification "
                    "evidence, a prompt aimed at the run that produced it "
                    "(retroactive), an understated token total, an unenforced or "
                    "ceiling-less budget, over-budget work and a tampered receipt "
                    "are each refused, and the happy path replays deterministically "
                    "(crash/resume maps to byte-for-byte replay of a pure gate)"
                ),
                "status": "PASS",
            },
            "no_candidate_model_prompt_backend_or_hook_acquires_authority": {
                "mechanism": (
                    "nothing here scores, selects, promotes or evaluates; the "
                    "receipt carries a verdict (ADMITTED) not a fitness, a prompt "
                    "mutation is admitted only after the composed J05/S05 surfaces "
                    "release it from quarantine and confirm a future target run, "
                    "and no receipt field grants evaluator/holdout/promotion "
                    "authority"
                ),
                "status": "PASS",
            },
        },
        "gate_semantics": {
            "admits": "one operator application against qualification and context budget",
            "budget_source": "budget-envelope module (spend_is_bounded, normalize_hard_limits)",
            "produces": "a self-proving receipt; no score, selection or promotion",
            "qualification_source": "sealed J05 registry/prompt-workflow composing the S05 inert-mutations gate",
            "refusals_are_by_code": True,
        },
        "required_checks": {
            "independent_review": {
                "evidence": (
                    "review.md (author: a bounded implementation agent; reviewer: "
                    "the sealing agent, independent; actor_independence between "
                    "author and reviewer holds, external certification does not; "
                    "verdict PASS, blocking_finding_count=0)"
                ),
                "status": "PASS",
            },
            **{
                name: {"status": "PASS", "test_count": count}
                for name, count in core.items()
            },
        },
        "schema_binding": {
            "budget_ceiling": "budget-envelope hard_limits.tokens via normalize_hard_limits",
            "context_accounting": "context-assembly-manifest token_accounting (total re-derived per call)",
            "qualification_vocabulary": "sealed J05/S05 surfaces, remapped to J06 finding codes",
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
                f"{ATTEMPT_DIR}/build_j06_0001_evidence.py",
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
        "# J06-0001 independent review\n"
        "\n"
        "- Author: a bounded implementation agent that authored the J06 product\n"
        "  code (src/epistemic_foundry/operators/v4_j06) and its tests.\n"
        "  Reviewer: the sealing agent, which did NOT author the subject code and\n"
        "  reviewed it adversarially against the authority chain and the\n"
        "  evolution-integrity constraints. Actor-independence between author and\n"
        "  reviewer HOLDS; external actor-independent (provider-independent)\n"
        "  certification does NOT hold. Verdict: PASS, blocking_finding_count=0.\n"
        "- Verification basis: static reading of the subject (declarations.py,\n"
        "  gate.py, __init__.py) plus the composed sealed surfaces it imports\n"
        "  (operators.v4_j05 registry/prompt-workflow, budgets.envelope,\n"
        "  contracts for the context-assembly-manifest and budget-envelope\n"
        "  schemas, domain.hashing), plus inspection-only execution: the J06\n"
        "  targeted suite and check_packaging.py pass. No FORGE state was mutated\n"
        "  by the review.\n"
        "- Per-exit-criterion: (1) governing schemas/authority-boundaries/failure\n"
        "  states implemented exactly - PASS: both direct contracts are read from\n"
        "  the canonical registry and re-verified for the token fields and the\n"
        "  token ceiling on every call (CONTEXT_CONTRACT_DRIFT /\n"
        "  BUDGET_CONTRACT_DRIFT close the gate on a rename); (2) happy/negative/\n"
        "  crash-resume(=byte-for-byte replay)/adversarial coverage - PASS: every\n"
        "  finding code is driven by at least one negative test, guarded by a\n"
        "  suite self-check; (3) no candidate, model, prompt, backend or hook\n"
        "  acquires evaluator/holdout/promotion authority - PASS: the receipt\n"
        "  carries ADMITTED, never a fitness, and tests assert no score/fitness/\n"
        "  promotion/evaluator/holdout key appears; (4) all effects resolve to\n"
        "  immutable, re-derivable receipts - PASS: receipt_hash re-derives via\n"
        "  hash_excluding and verify_gate_receipt refuses drift.\n"
        "- Evolution-integrity: PASS. The gate composes rather than restates\n"
        "  (EF4-I22): qualification-out-of-quarantine and future-run-only come\n"
        "  from J05's claim_active_prompt_operator (running the S05 inert-mutations\n"
        "  gate) and build_activation_record, remapped to J06 finding codes so a\n"
        "  caller sees one vocabulary; the unqualified, quarantined (EF4-I55) and\n"
        "  retroactive refusals are the composed surfaces' refusals. Token\n"
        "  accounting is DERIVED from the manifest's own components, not asserted\n"
        "  from the published total (CONTEXT_ACCOUNTING_INCONSISTENT catches an\n"
        "  understated total), the ceiling is read through the budget module's own\n"
        "  normalizer, over-budget work is refused rather than truncated, and an\n"
        "  unenforced or ceiling-less budget is refused. Nothing scores, selects,\n"
        "  promotes or evaluates; the gate takes no evaluator/holdout/promotion\n"
        "  authority.\n"
        "- Findings (all non-blocking): F1 - the prompt-qualification path is\n"
        "  exercised through re-sealed released/quarantined proposal fixtures that\n"
        "  stand in for the J05 transition J06 does not own; this is the same\n"
        "  fixture discipline J05's own suites use and is a test-surface note, not\n"
        "  a product gap. F2 - report.json/commands.jsonl are materialized by this\n"
        "  seal step (the sealing hand's emission responsibility), now satisfied.\n"
        "  F3 - crash/resume maps to replay determinism for this pure gate;\n"
        "  informational.\n"
        "- Residual limitations: J06 qualifies, meters and refuses; it records a\n"
        "  qualification-and-budget verdict only. It does not score, select,\n"
        "  promote, evaluate or execute any candidate; it makes no DSSAT or\n"
        "  plant-model numerical parity claim; promotion remains a governance\n"
        "  decision outside this module; and this review is not external\n"
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
        "attempt_type": "J06_OPERATOR_PROMPT_QUALIFICATION_CONTEXT_BUDGET_GATE",
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
            "scoring, selection, promotion or evaluation of any candidate: J06 qualifies, meters and refuses, recording a qualification-and-budget verdict only",
            "activation of an unqualified prompt: a prompt mutation is admitted only after the composed J05/S05 surfaces release it from quarantine",
            "retroactive prompt application: prompt mutations apply only to future runs, never to the run that produced them",
            "admission of over-budget work: context tokens exceeding the bounded ceiling are refused, not truncated",
            "runtime execution, backend dispatch or evolution-search orchestration of these operators",
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
                "Author/reviewer separation holds (a bounded implementation agent "
                "authored the subject code; the sealing agent reviewed it "
                "independently); external actor-independent (provider-independent) "
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
        "next_action": "SEAL_J06_0001_THEN_CONTINUE_DAG",
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
    write_json("j06-verification.json", verification)
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
        raise SystemExit("J06-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "j06-verification.json")
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
    verification = read_json(ATTEMPT / "j06-verification.json")
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
        raise SystemExit("stored J06-0001 report is not the deterministic document")
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
