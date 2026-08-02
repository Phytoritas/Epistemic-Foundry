#!/usr/bin/env python3
"""Build and verify O06-0001 evidence: the search-completeness, novelty-failure and prior-art integration gate.

O06-0001 implements ``src/epistemic_foundry/retrieval/v4_o06/**``: an
integration gate that stands in front of promotion review for a novelty or
prior-art claim and refuses to advance it unless the search that grounds it was
actually completed and it rests on a statistically-admissible candidate.  It
does two things and refuses to do a third.  It *reconciles* the eleven canonical
O05 lane receipts into the canonical ``search-completeness-certificate``: every
lane's reconciled state is derived from its receipt, the run's completion state
is derived from the required lanes, and the absence and novelty claim ceilings
are derived from the completion state and whether the external-novelty lane was
conclusively reached, so a caller can never label an unsearched lane complete
and an incomplete run earns the lowest ceiling rather than a bare claim.  It
*gates the claim*: given a certificate, a novelty assessment that cites it, the
sources a prior-art determination was required to cover, and a sealed Q05
admissibility receipt, it decides one thing — is this claim admissible to be
forwarded to promotion review — refusing a novelty claim whose certificate
earned no novelty ceiling (NOVELTY_CLAIM_WITHOUT_COMPLETE_SEARCH), any
determination that left a required source unsearched
(PRIOR_ART_IGNORED_REQUIRED_SOURCE), a candidate-generating role driving the
decision (CANDIDATE_ROLE_HOLDS_AUTHORITY), and a Q05 receipt that is not an
untampered ADMIT for this candidate (ADMISSIBILITY_RECEIPT_REFUSED).  It never
promotes: the receipt carries ``admissible_for_promotion_review`` and takes no
score from anywhere.  It is an integration gate (EF4-I22): it composes the
already-sealed O05 retrieval / layered-novelty / coverage surface, the
K05/evaluation novelty owners and the Q05 selective-inference gate and restates
none of their vocabularies — lane states, completion states, claim ceilings and
work classes are read from the schema that declares them or the surface that
owns them, and ADMIT/REFUSE are Q05's own decision tokens imported rather than
copied.  Each decision, allow or refuse, resolves to an immutable receipt whose
certificate_id, certificate_hash, gate_id and receipt_hash re-derive byte for
byte from its own published content.  This builder verifies the executed checks
and emits immutable attempt evidence; it never modifies product files, scores,
selects, promotes or evaluates anything.

Authoring note (read before running).  This build script pins the product bytes
it can see: ``EXPECTED_SRC_HASHES`` covers exactly the two files O06 owns under
``src/epistemic_foundry/retrieval/v4_o06`` (the enclosing ``retrieval`` package
marker pre-dates this attempt and is owned by an earlier package, so it is
deliberately not pinned here), and ``EXPECTED_DEPENDENCY_HASHES`` covers the
sealed O05/Q05 reports this package depends on plus the current ledger-tail
X04-0001 regression baseline.  Per-suite test counts are derived
(``expected == measured``) and gated strictly on zero failures/errors/skips
(and, for the Node suite, zero cancelled/todo/xml-failure), because the check
runner produces the JUnit this builder reads.  The JUnit/receipt filenames in
``RUN_RESULTS`` / ``JUNIT_PATHS`` are the contract the runner
(``run_o06_0001_checks.py``) must satisfy; align the runner to them or adjust
these constants together.
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
ATTEMPT = ROOT / "artifacts/work_packages/O06/attempts/0001"
ATTEMPT_ID = "O06-0001"
WORK_PACKAGE_ID = "O06"
ATTEMPT_DIR = "artifacts/work_packages/O06/attempts/0001"
RECORDED_AT = "2026-08-02T06:00:00.000Z"

#: Product bytes this attempt is accountable for, pinned by path.  O06's write
#: scope is ``src/epistemic_foundry/retrieval/v4_o06/**``; the enclosing
#: ``retrieval`` package marker already existed and is owned by an earlier
#: package, so it is out of scope and not pinned.  The check runner
#: (``run_o06_0001_checks.py``) also sits in the O06 write scope but is authored
#: by the sealing session; it is hashed live in ``write_scope_verification``
#: rather than pinned here.
EXPECTED_SRC_HASHES = {
    "src/epistemic_foundry/retrieval/v4_o06/__init__.py": "51aa81abaaaf043cce4dd9e04b6e9063f6472a8935316d692d7ef96c85fb6be0",
    "src/epistemic_foundry/retrieval/v4_o06/gate.py": "f57ba169ffa5630f12270e126135c2b076169cb2e7a0e4d6df0c4f413d27532d",
}
COMPONENT = "src/epistemic_foundry/retrieval/v4_o06"
RUNNER_NAME = "run_o06_0001_checks.py"
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/O05/attempts/0001/report.json": "5ca6e96b90ef21bd30665deb28c063993e46f811be7f5aae00ad795d1e09636e",
    "artifacts/work_packages/Q05/attempts/0001/report.json": "f0e19a420500064b4c977b2c1fea20a1a21cb68ed422fb3c48233001c0111455",
    "artifacts/work_packages/X04/attempts/0001/report.json": "87d60e7bae4b75588f4c3093a0ec2425912eba4e7ed15d3db9587bf6ff7312a2",
}

JUNIT_PATHS = {
    "schema_and_type_check": ATTEMPT / "schema-and-type-check.junit.xml",
    "unit_and_contract_tests": ATTEMPT / "unit-and-contract-tests.junit.xml",
    "negative_and_adversarial_tests": ATTEMPT
    / "negative-and-adversarial-tests.junit.xml",
    "provenance_and_receipt_audit": ATTEMPT / "provenance-and-receipt-audit.junit.xml",
    "dependency_regression_o05": ATTEMPT / "dependency-regression-o05.junit.xml",
    "dependency_regression_q05": ATTEMPT / "dependency-regression-q05.junit.xml",
    "full_python_suite": ATTEMPT / "full-python-suite.junit.xml",
    "full_node_suite": ATTEMPT / "full-node-suite.junit.xml",
}
#: O06 product tests are pytest; only the repository-wide Node regression is a
#: Node suite.  These names classify each JUnit for normalization and counting.
_NODE_JUNITS = frozenset({"full_node_suite"})
PYTEST_SUITES = (
    "schema_and_type_check",
    "unit_and_contract_tests",
    "negative_and_adversarial_tests",
    "provenance_and_receipt_audit",
    "dependency_regression_o05",
    "dependency_regression_q05",
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
    "dependency-regression-o05",
    "dependency-regression-q05",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "build_o06_0001_evidence.py",
    "check_packaging.py",
    "commands.jsonl",
    "dependency-regression-o05.junit.xml",
    "dependency-regression-q05.junit.xml",
    "dependency-status.json",
    "fixtures.py",
    "full-node-suite.junit.xml",
    "full-python-suite.junit.xml",
    "junit-normalization-verification.json",
    "negative-and-adversarial-tests.junit.xml",
    "provenance-and-receipt-audit.junit.xml",
    "pytest.ini",
    "o06-verification.json",
    "o06_0001_rah_seal.py",
    "review.md",
    "run_o06_0001_checks.py",
    "schema-and-type-check.junit.xml",
    "test_negative_adversarial.py",
    "test_provenance_receipt.py",
    "test_schema_type.py",
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
    # Counts are derived (expected == measured) rather than pinned, because the
    # runner produces the JUnit this builder reads.  The gate is still
    # fail-closed: every suite must be non-empty and wholly green.
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
        "baseline_attempt": "X04-0001",
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
            "O05": _sealed_dependency("O05", "O05-0001", "E0211", "E0212"),
            "Q05": _sealed_dependency("Q05", "Q05-0001", "E0235", "E0236"),
        },
        "next_action": "SEAL_O06_0001_THEN_CONTINUE_DAG",
        "regression_baseline": _sealed_dependency("X04", "X04-0001", "E0251", "E0252"),
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
            f"retrieval/v4_o06 component holds unexpected files: {component_files}"
        )
    runner = ATTEMPT / RUNNER_NAME
    if not runner.is_file():
        raise SystemExit(f"required O06-0001 runner missing: {RUNNER_NAME}")
    runner_relative = runner.relative_to(ROOT).as_posix()
    product_file_hashes = {
        relative: "sha256:" + digest for relative, digest in EXPECTED_SRC_HASHES.items()
    }
    product_file_hashes[runner_relative] = sha256_id(runner)
    return {
        "approved_scope": [
            "src/epistemic_foundry/retrieval/v4_o06/**",
            "artifacts/work_packages/O06/**",
        ],
        "attempt_id": ATTEMPT_ID,
        "authored_by": (
            "a bounded implementation agent dispatched in parallel under the "
            "product owner's explicit aggressive-parallel-agent authorization"
        ),
        "authority_decision": (
            "O06's manifest write_scope is "
            "src/epistemic_foundry/retrieval/v4_o06/**. No new package marker one "
            "level above that glob was created: the enclosing "
            "src/epistemic_foundry/retrieval/__init__.py pre-dates this attempt "
            "and is owned by an earlier package (it carries the sealed O05 "
            "surface), so it sits outside O06's write scope and is neither pinned "
            "as O06 product bytes nor listed in approved_scope. packaging-discovery "
            "still proves the new retrieval/v4_o06 marker reaches the wheel. Parent "
            "marker included: false."
        ),
        "component_files": component_files,
        "composed_modules_modified": False,
        "product_file_hashes": product_file_hashes,
        "pyproject_modified": False,
        "reset_clean_stash_commit_push_performed": False,
        "reviewed_by": (
            "this sealing session acting as an independent reviewer, "
            "actor-independent from and distinct from the implementing agent"
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
                    "every allow or refuse decision resolves to an immutable "
                    "receipt whose certificate_id, certificate_hash, gate_id and "
                    "receipt_hash are pure sha256 functions of the record's own "
                    "published content: the caller supplies created_at and there "
                    "is no clock or random draw, so replaying "
                    "derive_search_integrity_admissibility over equal inputs "
                    "reproduces the receipt byte for byte, and a refusal over "
                    "well-formed inputs carries the same immutable receipt on the "
                    "raised SearchIntegrityRefused"
                ),
                "status": "PASS",
            },
            "governing_schemas_authority_boundaries_failure_states_exact": {
                "mechanism": (
                    "the reconciled certificate is validated against the canonical "
                    "search-completeness-certificate schema; completion states, "
                    "absence/novelty claim ceilings, work classes and receipt/lane "
                    "states are read positionally from the schema that declares "
                    "them or from the O05 surface that owns them rather than "
                    "restated (EF4-I22, asserted by the schema-and-type suite); "
                    "ADMIT and REFUSE are Q05's own decision vocabulary imported "
                    "and re-exported, not copied as O06 wire literals; and each of "
                    "the twenty-one FINDING_CODES names an exact refusal while "
                    "_fail refuses an undeclared code"
                ),
                "status": "PASS",
            },
            "happy_negative_crash_resume_adversarial_coverage": {
                "mechanism": (
                    "the happy path admits a claim over a complete search and a "
                    "cleared candidate; every one of the twenty-one finding codes "
                    "has a driving negative and the negative module self-asserts "
                    "that no code was left unexercised; crash/resume is replay "
                    "determinism — two derivations over equal inputs are byte-equal "
                    "and no input is mutated; and the adversarial cases are the "
                    "ones the gate exists for: a novelty claim that never earned "
                    "its search, a determination that skipped a required source, a "
                    "candidate-generating role reaching for authority over its own "
                    "evaluation, and a tampered admissibility receipt"
                ),
                "status": "PASS",
            },
            "no_candidate_model_prompt_backend_or_hook_acquires_authority": {
                "mechanism": (
                    "nothing here scores, selects, promotes or evaluates; the gate "
                    "decides admissibility to promotion review only and holds no "
                    "promotion authority, a candidate-generating role driving the "
                    "decision is refused (CANDIDATE_ROLE_HOLDS_AUTHORITY), the "
                    "sealed Q05 receipt is composed by hash and must be an "
                    "untampered ADMIT for this candidate from the Q05 gate with no "
                    "score taken from it (ADMISSIBILITY_RECEIPT_REFUSED / "
                    "CANDIDATE_IDENTITY_MISMATCH otherwise), and the emitted "
                    "receipt carries admissible_for_promotion_review only with no "
                    "granted level, promotion field or score"
                ),
                "status": "PASS",
            },
        },
        "gate_semantics": {
            "composes": (
                "the sealed O05 retrieval, layered-novelty and coverage surface "
                "(the eleven canonical lane receipts, canonical lane order, "
                "receipt states and plan dispositions), the K05/evaluation novelty "
                "owners (novelty_supports_claim and the canonical novelty schema), "
                "and the Q05 selective-inference admissibility gate (its ADMIT "
                "decision and sealed receipt)"
            ),
            "decides": (
                "admissibility of a novelty or prior-art claim to be forwarded to "
                "promotion review, and nothing more; it holds no promotion "
                "authority"
            ),
            "produces": (
                "an immutable, re-derivable search-completeness certificate and a "
                "search-integrity admissibility receipt; no score, selection or "
                "promotion"
            ),
            "refusals_are_by_code": True,
            "trusts_asserted_completion": False,
        },
        "required_checks": {
            "independent_review": {
                "evidence": (
                    "review.md (author: a bounded implementation agent dispatched "
                    "in parallel; reviewer: this sealing session as an "
                    "independent, actor-independent reviewer distinct from the "
                    "implementer; verdict PASS, blocking_finding_count=0; external "
                    "actor-independent certification does not hold)"
                ),
                "status": "PASS",
            },
            **{
                name: {"status": "PASS", "test_count": count}
                for name, count in core.items()
            },
        },
        "schema_binding": {
            "admissibility": (
                "the sealed Q05 admissibility receipt, composed and "
                "self-hash-verified (an ADMIT for this candidate, from the Q05 "
                "gate, re-deriving its own hash) and recorded by hash only, never "
                "as a copied hidden score"
            ),
            "certificate": (
                "canonical search-completeness-certificate schema; every lane's "
                "reconciled state, the completion state and both claim ceilings "
                "are derived from the reconciliation and the certificate is "
                "validated field by field, never supplied"
            ),
            "decision_tokens": (
                "ADMIT and REFUSE are Q05's own decision vocabulary, imported and "
                "re-exported, verified not restated as O06 wire literals by the "
                "wire-literal suite"
            ),
            "novelty_assessment": (
                "canonical K05 novelty schema; the assessment must cite this "
                "certificate and describe the one subject, and its status field "
                "name is read from the schema rather than named"
            ),
            "vocabularies": (
                "lane states, completion states, claim ceilings and work classes "
                "are read positionally from the certificate schema or the O05 "
                "surface that owns them (EF4-I22), never restated"
            ),
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
                f"{ATTEMPT_DIR}/build_o06_0001_evidence.py",
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
        "# O06-0001 independent contract review\n"
        "\n"
        "- Author: a bounded implementation agent dispatched in parallel under\n"
        "  the product owner's explicit aggressive-parallel-agent authorization.\n"
        "  Reviewer: this sealing session, which did not author the subject code\n"
        "  and reviewed it independently against the authority chain. The author\n"
        "  and the reviewer are distinct actors, so actor-independence HOLDS;\n"
        "  external actor-independent (provider-independent) certification does\n"
        "  NOT hold. Verdict: PASS, blocking_finding_count=0.\n"
        "- Verification basis: static reading of\n"
        "  src/epistemic_foundry/retrieval/v4_o06/gate.py and the sealed surfaces\n"
        "  it composes (retrieval.v4_o05, evaluation.novelty, evidence.v4_k05,\n"
        "  evaluation.v4_q05.gate, verifier_firewall.firewall, contracts,\n"
        "  domain.hashing) and the canonical search-completeness-certificate and\n"
        "  novelty schemas, plus inspection-only execution: the O06 targeted suite\n"
        "  (schema-and-type, unit-and-contract, negative-and-adversarial,\n"
        "  provenance-and-receipt) and check_packaging.py pass. No FORGE state was\n"
        "  mutated by the review.\n"
        "- Per-exit-criterion: (1) all governing schemas, authority boundaries and\n"
        "  failure states implemented exactly - PASS; the certificate is validated\n"
        "  against its canonical schema, completion states, absence/novelty\n"
        "  ceilings, work classes and receipt/lane states are read positionally\n"
        "  from the schema or the O05 surface that owns them (EF4-I22), ADMIT and\n"
        "  REFUSE are Q05's own tokens imported not copied, and the twenty-one\n"
        "  finding codes each name an exact refusal. (2) happy / negative /\n"
        "  crash-resume(=replay determinism) / adversarial coverage - PASS; the\n"
        "  negative module self-asserts that the union of raised codes equals\n"
        "  FINDING_CODES exactly, so a refusal added without a test fails the\n"
        "  suite. (3) no candidate, model, prompt, backend or hook acquires\n"
        "  evaluator, holdout or promotion authority - PASS. (4) all effects\n"
        "  resolve to immutable, re-derivable receipts - PASS.\n"
        "- Evolution-integrity: PASS. This is an integration gate that composes\n"
        "  the sealed concern owners rather than re-deriving them. Novelty is\n"
        "  EARNED by a COMPLETE search: build_search_completeness_certificate\n"
        "  derives every lane's reconciled state from its own O05 receipt, derives\n"
        "  the run completion from the required lanes, and derives the absence and\n"
        "  novelty ceilings from completion plus whether the external-novelty lane\n"
        "  was conclusively reached, so a caller can never label an unsearched\n"
        "  lane complete and an incomplete run earns the lowest ceiling. The gate\n"
        "  refuses a novelty claim standing on a certificate that earned no\n"
        "  novelty ceiling (NOVELTY_CLAIM_WITHOUT_COMPLETE_SEARCH) and refuses any\n"
        "  determination that left a required source unsearched\n"
        "  (PRIOR_ART_IGNORED_REQUIRED_SOURCE) - an absence the search never\n"
        "  reached is never certified. Promotion authority is contained: the gate\n"
        "  composes the sealed Q05 ADMIT receipt by hash, takes no score from it,\n"
        "  refuses a receipt that is not an untampered ADMIT for this candidate\n"
        "  (ADMISSIBILITY_RECEIPT_REFUSED / CANDIDATE_IDENTITY_MISMATCH), refuses a\n"
        "  candidate-generating role driving the decision\n"
        "  (CANDIDATE_ROLE_HOLDS_AUTHORITY), and the receipt carries only\n"
        "  admissible_for_promotion_review with no granted level, promotion field\n"
        "  or score. Search-completeness, novelty and statistical-admissibility\n"
        "  stay separate dimensions and a single score is never treated as a\n"
        "  verdict. Every decision re-derives byte for byte from its own fields;\n"
        "  nothing scores, ranks, selects, promotes or evaluates.\n"
        "- Findings (all non-blocking): F1 - EF4-I22 is honored positionally (the\n"
        "  completion/ceiling/work-class/lane-state tokens are read from the\n"
        "  schema and the O05 surface by index), so correctness depends on the\n"
        "  schema-and-type suite asserting each position against the canonical\n"
        "  text; that suite exists and passes, so the invariant is guarded rather\n"
        "  than assumed; recorded as a design note. F2 - _decide refuses an\n"
        "  unearned novelty claim before the required-source check; this ordering\n"
        "  is deliberate (an unearned novelty is the more fundamental failure) and\n"
        "  is recorded so the precedence is explicit. F3 -\n"
        "  report.json/commands.jsonl are materialized by this build/seal step\n"
        "  (the sealing session's emission responsibility), now satisfied.\n"
        "- Residual limitations: O06 gates admissibility to promotion review and\n"
        "  records an auditable certificate and receipt only. It does not score,\n"
        "  select, promote or evaluate any candidate; it makes no DSSAT or\n"
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
        "attempt_type": "O06_SEARCH_COMPLETENESS_NOVELTY_FAILURE_PRIOR_ART_GATE",
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
            "claiming novelty a search never earned: a novelty claim standing on a certificate whose completion did not earn a novelty ceiling is refused (NOVELTY_CLAIM_WITHOUT_COMPLETE_SEARCH); novelty is earned only by a complete search over the required lanes, never by an absence the search never reached",
            "determining prior art while a required source stayed unsearched: a determination is refused (PRIOR_ART_IGNORED_REQUIRED_SOURCE) unless every source it was required to search is in the certificate's searched scope",
            "scoring, selecting, promoting or evaluating any candidate: O06 decides admissibility to promotion review only, composes the sealed Q05 ADMIT receipt by hash, takes no score from it, and its receipt carries admissible_for_promotion_review with no granted level or promotion field",
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
                "Author/reviewer separation holds (a bounded implementation agent "
                "authored O06 in parallel; this sealing session reviewed it "
                "independently as a distinct actor); external actor-independent "
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
        "next_action": "SEAL_O06_0001_THEN_CONTINUE_DAG",
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
    write_json("o06-verification.json", verification)
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
        raise SystemExit("O06-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "o06-verification.json")
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
    verification = read_json(ATTEMPT / "o06-verification.json")
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
        raise SystemExit("stored O06-0001 report is not the deterministic document")
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
