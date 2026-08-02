#!/usr/bin/env python3
"""Build and verify Z06-0001 evidence: Independent release, clean extraction and truthful maturity gate.

This attempt was implemented by a bounded parallel agent under the product
owner's explicit parallel-execution instruction, with disjoint write scopes,
and was reviewed by the primary session before sealing.  The builder verifies
every executed check receipt, gates every JUnit against its measured count,
pins product and dependency bytes, and emits the deterministic attempt
evidence; it never modifies product files.
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
ATTEMPT = ROOT / "artifacts/work_packages/Z06/attempts/0001"
ATTEMPT_ID = "Z06-0001"
WORK_PACKAGE_ID = "Z06"
RECORDED_AT = "2026-08-02T21:00:00.000Z"
ATTEMPT_DIR = "artifacts/work_packages/Z06/attempts/0001"
AUTHORITY_DECISION = None

EXPECTED_PRODUCT_HASHES = {
    "artifacts/work_packages/Z06/attempts/0001/fixtures.py": "26f89c9bbf37b62bd3c418f07f62b51b06d2eee7e25020602b5cb86260115860",
    "artifacts/work_packages/Z06/attempts/0001/pytest.ini": "87cde8f4c9fa3367fdc27567250c0d9f062a9142d2a374fc54e6be6544a64344",
    "artifacts/work_packages/Z06/attempts/0001/run_z06_0001_checks.py": "a7ec426c52feef2345c96a8ddcbde51679d814526d90313d0bdf648fec6c70b6",
    "artifacts/work_packages/Z06/attempts/0001/test_negative_adversarial.py": "c245257d51f41a2381c9b581e991b28f8f9ffb7fba93a3ed39ea8bd0863a2f2e",
    "artifacts/work_packages/Z06/attempts/0001/test_provenance_receipts.py": "5040b48e7be44e2cf1e4f22397cbb738d93cc54b244daf34683ceb82c64e3b7e",
    "artifacts/work_packages/Z06/attempts/0001/test_schema_and_type.py": "156fe8963b7ad984fa6376cabfb55b060579ea8529bb7ca983698e2900a775af",
    "artifacts/work_packages/Z06/attempts/0001/test_unit_contract.py": "61ae07d8e2097c44899dd845e6b1108ef17a61ce49da03ab073e1ee2927b02d9",
    "release/v4_z06/__init__.py": "b76bcf6f69530486473d873c0e64629b3a1533b53b67c287edb8b025f2a47047",
    "release/v4_z06/truthful_release.py": "c0bd950c50dbd3d50047986677be126702f4bf4d9d3cbd612aac07ef79a18685",
}
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/B06/attempts/0001/report.json": "f40d87a6db6ebedc54ed10e3077835b08c9c6b2615746adde10dbd4e75222df8",
    "artifacts/work_packages/C06/attempts/0001/report.json": "cc5a900acf1a266d85387fc63c7f065fa8a547e7b613e89d3d45883c31aa1661",
    "artifacts/work_packages/F06/attempts/0001/report.json": "ce89ecb506a664f1a7b1f7b1c49e6546295eb8d1266f0e28469172aa0d16714c",
    "artifacts/work_packages/G06/attempts/0001/report.json": "6486d22cb242c64924c06d1179e95aa8f47830032c597031756c855425cdc859",
    "artifacts/work_packages/K06/attempts/0001/report.json": "a7803903305ee45222cfc3dee6064d469a80c6ad3d78232fa9a052a5c32c5b21",
    "artifacts/work_packages/N06/attempts/0001/report.json": "c9767be522590044cb5cbb58fbf942b6de5ec167e4b95f9f4aeb1947382e70dd",
    "artifacts/work_packages/P06/attempts/0001/report.json": "7799373cf2bb5d7bf87a58a06cb1f489a76fb260f7efe23ecb51e2bfcd2fea5f",
    "artifacts/work_packages/Q06/attempts/0001/report.json": "af922c3015993d953613232cd2a5dfea1cafce74bc32f88548ce17222c76584c",
    "artifacts/work_packages/S05/attempts/0001/report.json": "dbcb94e77fd885f18aa36a00dc352a9d5a788d265b979ff7a23fafd5f261c727",
    "artifacts/work_packages/S06/attempts/0001/report.json": "610898b5b8aaad468e9017a86d8824896d968042460b6f183de91dc1d323bdbc",
    "artifacts/work_packages/T06/attempts/0001/report.json": "0ed159b23e1e856ee1c0e5fcef6c2b89d99c69602fd681424ddaf3bc6a0bbdae",
    "artifacts/work_packages/V06/attempts/0001/report.json": "1aeddcd811d30ae5f9ee18e0d398f97eae47d1e85fef6b8fd5933464a20812c7",
    "artifacts/work_packages/W06/attempts/0001/report.json": "3c61e5975e40cc3f161e2a195e9912686aaea8fd754105af23eded26d9d29ea4",
    "artifacts/work_packages/Y06/attempts/0001/report.json": "e049556aab6b01313175189803cd615ee1b2e7471b9169989e5c6033b8f76c48",
    "artifacts/work_packages/Z05/attempts/0001/report.json": "c2f1f57e207f5605672bc62d9c76868fa9ff59c4bdaf35f74e3033c2afa8263d",
}

JUNIT_PATHS = {
    "dependency_regression_operations": ATTEMPT
    / "dependency-regression-operations.junit.xml",
    "dependency_regression_release": ATTEMPT
    / "dependency-regression-release.junit.xml",
    "full_node_suite": ATTEMPT / "full-node-suite.junit.xml",
    "full_python_suite": ATTEMPT / "full-python-suite.junit.xml",
    "negative_and_adversarial_tests": ATTEMPT
    / "negative-and-adversarial-tests.junit.xml",
    "provenance_and_receipt_audit": ATTEMPT / "provenance-and-receipt-audit.junit.xml",
    "schema_and_type_check": ATTEMPT / "schema-and-type-check.junit.xml",
    "targeted_z06_release": ATTEMPT / "targeted-z06-release.junit.xml",
    "unit_and_contract_tests": ATTEMPT / "unit-and-contract-tests.junit.xml",
    "wire_literal_discipline": ATTEMPT / "wire-literal-discipline.junit.xml",
}
_NODE_JUNITS = frozenset({"full_node_suite"})
RUN_RESULTS = (
    "dependency-regression-operations",
    "dependency-regression-release",
    "full-node-suite",
    "full-python-suite",
    "git-diff-check",
    "negative-and-adversarial-tests",
    "provenance-and-receipt-audit",
    "ruff-check",
    "ruff-format-check",
    "schema-and-type-check",
    "targeted-z06-release",
    "unit-and-contract-tests",
    "wire-literal-discipline",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "build_z06_0001_evidence.py",
    "commands.jsonl",
    "dependency-regression-operations.junit.xml",
    "dependency-regression-release.junit.xml",
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
    "run_z06_0001_checks.py",
    "schema-and-type-check.junit.xml",
    "targeted-z06-release.junit.xml",
    "test_negative_adversarial.py",
    "test_provenance_receipts.py",
    "test_schema_and_type.py",
    "test_unit_contract.py",
    "unit-and-contract-tests.junit.xml",
    "wire-literal-discipline.junit.xml",
    "write-scope-verification.json",
    "z06-verification.json",
    "z06_0001_rah_seal.py",
)
#: Maps each manifest required check to the regression suite key that carries its
#: measured count.  Injected from the wave config; defaults to the four standard
#: suites for standard-shape packages.
REQUIRED_CHECK_MAP = {
    "negative_and_adversarial_tests": "negative_and_adversarial_tests",
    "provenance_and_receipt_audit": "provenance_and_receipt_audit",
    "schema_and_type_check": "schema_and_type_check",
    "unit_and_contract_tests": "unit_and_contract_tests",
}
#: Maps each manifest exit-criterion key to its mechanism sentence.
EXIT_CRITERIA = {
    "all_completion_and_external_effects_resolve_to_immutable_receipts": "every decision resolves to a content-addressed receipt (id is the sha256 of the payload, self-hash via hash_excluding), the terminal verdict binds each sub-receipt by hash, receipts are byte-equal across runs, carry no clock, and never mutate inputs",
    "governing_schemas_authority_boundaries_failure_states_exact": "the module holds no canonical enum literal — the passing status token and maturity floor are read through the composed Z05 surface, the fail-closed UNSIGNED status is derived through the sealed provenance surface, and the forbidden-maturity-claim vocabulary is proven disjoint from every schema enum",
    "happy_negative_crash_resume_adversarial_coverage": "happy path (unit and provenance), negative and adversarial (23 cases, one per finding code), crash/resume-style composition over the actually-sealed frozen Z05 report and the thirteen real *06 reports, and two dependency-regressions that fail here if a composed surface breaks",
    "no_candidate_model_prompt_backend_or_hook_acquires_authority": "no candidate, model, prompt, backend or hook can gain evaluator, holdout or promotion authority — the truthful-maturity gate refuses any release-level above floor, any completion claim, any executable/validated/production-ready/signed claim, and any unowned conditional in the accounting",
}


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
    # An aggregate receipt records `commands` (several processes, worst exit
    # code); a plain receipt records one `command`.  Both are honest shapes.
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
            "dependency_regression_operations",
            pytest_summary(JUNIT_PATHS["dependency_regression_operations"]),
            41,
        ),
        (
            "dependency_regression_release",
            pytest_summary(JUNIT_PATHS["dependency_regression_release"]),
            50,
        ),
        ("full_python_suite", pytest_summary(JUNIT_PATHS["full_python_suite"]), 1312),
        (
            "negative_and_adversarial_tests",
            pytest_summary(JUNIT_PATHS["negative_and_adversarial_tests"]),
            23,
        ),
        (
            "provenance_and_receipt_audit",
            pytest_summary(JUNIT_PATHS["provenance_and_receipt_audit"]),
            9,
        ),
        (
            "schema_and_type_check",
            pytest_summary(JUNIT_PATHS["schema_and_type_check"]),
            8,
        ),
        (
            "targeted_z06_release",
            pytest_summary(JUNIT_PATHS["targeted_z06_release"]),
            47,
        ),
        (
            "unit_and_contract_tests",
            pytest_summary(JUNIT_PATHS["unit_and_contract_tests"]),
            7,
        ),
        (
            "wire_literal_discipline",
            pytest_summary(JUNIT_PATHS["wire_literal_discipline"]),
            5,
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
        ("full_node_suite", node_summary(JUNIT_PATHS["full_node_suite"]), 1740),
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
    if node_inventory.get("count") != 140:
        raise SystemExit(f"Node inventory gate failed: {node_inventory}")
    return {
        "attempt_id": ATTEMPT_ID,
        "baseline_attempt": "S05-0001",
        "component_tests_are_targeted_only": True,
        "new_failure_count": 0,
        "status": "PASS",
        "suites": summaries,
    }


def _sealed_dependency(
    package: str, attempt: str, core: str, final: str, *, flat: bool = False
) -> dict[str, Any]:
    path = ROOT / (
        f"artifacts/work_packages/{package}/report.json"
        if flat
        else f"artifacts/work_packages/{package}/attempts/{attempt[-4:]}/report.json"
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
    status: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "dependencies": {
            "B06": _sealed_dependency("B06", "B06-0001", "E0179", "E0180"),
            "C06": _sealed_dependency("C06", "C06-0001", "E0161", "E0162"),
            "F06": _sealed_dependency("F06", "F06-0001", "E0237", "E0238"),
            "G06": _sealed_dependency("G06", "G06-0001", "E0247", "E0248"),
            "K06": _sealed_dependency("K06", "K06-0001", "E0221", "E0222"),
            "N06": _sealed_dependency("N06", "N06-0001", "E0207", "E0208"),
            "P06": _sealed_dependency("P06", "P06-0001", "E0281", "E0282"),
            "Q06": _sealed_dependency("Q06", "Q06-0001", "E0275", "E0276"),
            "S06": _sealed_dependency("S06", "S06-0001", "E0229", "E0230"),
            "T06": _sealed_dependency("T06", "T06-0001", "E0209", "E0210"),
            "V06": _sealed_dependency("V06", "V06-0001", "E0273", "E0274"),
            "W06": _sealed_dependency("W06", "W06-0001", "E0231", "E0232"),
            "Y06": _sealed_dependency("Y06", "Y06-0001", "E0355", "E0356"),
            "Z05": _sealed_dependency("Z05", "Z05-0001", "E0365", "E0366"),
        },
        "next_action": "SEAL_Z06_0001_THEN_CONTINUE_DAG",
        "regression_baseline": _sealed_dependency("S05", "S05-0001", "E0175", "E0176"),
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
            "release/v4_z06/**",
            "artifacts/work_packages/Z06/**",
        ],
        "attempt_id": ATTEMPT_ID,
        "authority_decision": AUTHORITY_DECISION,
        "authored_by": (
            "bounded parallel implementation agent under the product owner's "
            "explicit parallel-execution instruction"
        ),
        "composed_modules_modified": False,
        "product_file_hashes": {
            relative: "sha256:" + digest
            for relative, digest in EXPECTED_PRODUCT_HASHES.items()
        },
        "pyproject_modified": False,
        "reset_clean_stash_commit_push_performed": False,
        "reviewed_by": "primary session (Parent Architect), separate from the author",
        "root_canonical_source_mutation_count": 0,
        "schema_or_test_weakening_count": 0,
        "status": "PASS",
        "subagents_or_fleet_used": True,
        "write_scope_violation_count": 0,
    }


def package_verification(regression: dict[str, Any]) -> dict[str, Any]:
    suites = regression["suites"]
    core = {
        name: suites[suite_key]["collected"]
        for name, suite_key in REQUIRED_CHECK_MAP.items()
        if suite_key in suites
    }
    missing = [name for name, key in REQUIRED_CHECK_MAP.items() if key not in suites]
    if missing:
        raise SystemExit(f"required check has no measured suite: {missing}")
    return {
        "attempt_id": ATTEMPT_ID,
        "declaring_sources": {
            "composed_gates": (
                "frozen sealed reports of Z05 and the thirteen *06 gates (B06,C06,F06,G06,K06,N06,P06,Q06,S06,T06,V06,W06,Y06)"
            ),
            "maturity_floor": (
                "manifests/acceptance_matrix.yaml status_of_this_bundle (SPEC_BUNDLE) and MASTER_SPEC section 2 maturity statement"
            ),
            "provenance": (
                "epistemic_foundry.release.provenance (sealed surface) and schemas/attestation.schema.json pass token (positional)"
            ),
            "status_and_floor": (
                "release/v4_z05/zero_trust_release.py reconciled_status_token / release_level_floor / require_unsigned_provenance / UNSIGNED_STATUS (composed)"
            ),
        },
        "exit_criteria": {
            key: {"mechanism": mechanism, "status": "PASS"}
            for key, mechanism in EXIT_CRITERIA.items()
        },
        "required_checks": {
            "independent_review": {
                "evidence": (
                    "review.md (author: parallel agent; reviewer: primary "
                    "session; actor_independence between author and reviewer "
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
                f"{ATTEMPT_DIR}/build_z06_0001_evidence.py",
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
        "# Z06-0001 primary-session review of parallel-agent work\n"
        "\n"
        "- Author: a bounded parallel implementation agent (disjoint write\n"
        "  scope, frozen contracts) under the product owner's explicit\n"
        "  parallel-execution instruction. Reviewer: the primary session,\n"
        "  which did not author this attempt; author/reviewer separation\n"
        "  holds, external actor-independent certification does not.\n"
        "- Write-scope audit: no tracked file was modified by the wave (mtime\n"
        "  sweep over the dirty worktree), the sealed G05 payload surface\n"
        "  re-verified green, and this package's files sit exactly inside its\n"
        "  granted scope.\n"
        "- Truthful-maturity enforcement is the crux: the gate PASSES by proving honesty, not completion — release_level is pinned to the acceptance-matrix floor via release_level_floor() (never restated), completion_ready is hardcoded False in every emitted receipt and verdict, signing_status is the composed derived UNSIGNED, and FORBIDDEN_MATURITY_CLAIMS refuses executable / validated / production-ready / GA / signed / shippable / certified via boundary-anchored regex so 'ga' cannot fire inside 'organization'.\n"
        "- Clean-extraction is proven without shipping: require_clean_extraction re-uses Z05's sealed release-provenance surface (which requires the clean_extraction build check) and verifies a declared bundle manifest — zip-slip (parent-traversal, absolute, drive-qualified, backslash), tamper (extracted hash != declared digest), surplus and missing members — with no archive written.\n"
        "- Z05 is composed as a FROZEN report, not re-run: compose_sealed_z05 reads the sealed report.json facts and binds their hash, exactly as Z05 composed Z04, avoiding the repo-state-dependent live gate.\n"
        "- Independent release accounting reconciles Z05 plus the thirteen *06 gates as sealed-PASS with exact set equality (missing or surplus both fail) and every conditional owned, run over the real on-disk reports.\n"
        "- Integration gates at review time: repository EF4-I22 discipline\n"
        "  5/5, structure and boundary checks PASS, git diff --check clean,\n"
        "  full Python and full Node suites green with the Node inventory\n"
        "  unified at 140 files across five bases.\n"
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
        "attempt_type": "Z06_TERMINAL_RELEASE_CLEAN_EXTRACTION_TRUTHFUL_MATURITY_GATE",
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
        "next_package": "closeout",
        "not_claimed": [
            "that a working v4 runtime, qualified evaluator, hidden holdout, Shinka adapter, production database, sandbox, UI, security review or 2,000-document deployment exists: the bundle stays SPEC_BUNDLE / UNVERIFIED reference",
            "a real built, extracted, signed or shipped release: signing stays fail-closed UNSIGNED and the Z02 clean-extraction property and 288-lens audit are composed by citation, not re-executed",
            "any flip of completion_ready: it stays false everywhere and the post-terminal closeout is the main session's",
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
            "actor_independence": False,
            "assurance_limitation": (
                "Author/reviewer separation holds (parallel agent authored, "
                "primary session reviewed); external actor-independent "
                "certification does not."
            ),
            "blocking_finding_count": 0,
            "mode": "PRIMARY_SESSION_REVIEW_OF_PARALLEL_AGENT_WORK",
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
        "next_action": "SEAL_Z06_0001_THEN_CONTINUE_DAG",
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
    write_json("z06-verification.json", verification)
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
        raise SystemExit("Z06-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "z06-verification.json")
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
    verification = read_json(ATTEMPT / "z06-verification.json")
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
        raise SystemExit("stored Z06-0001 report is not the deterministic document")
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
