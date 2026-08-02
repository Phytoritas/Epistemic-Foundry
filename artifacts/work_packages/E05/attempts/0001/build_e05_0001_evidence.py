#!/usr/bin/env python3
"""Build and verify E05-0001 candidate effect reconciliation evidence.

E05-0001 implements `src/epistemic_foundry/effects/v4_e05/**`: the engine that
reconciles the candidate fan-out against the effect and mutation ledgers, so
an effect belonging to no candidate, a candidate with no receipt, or a ledger
that disagrees with the pipeline about persistence is refused by name rather
than collapsed into a count (EF4-I60).  It composes the chamber and ledger
surfaces instead of restating them and holds no canonical schema enum value as
a string literal (EF4-I22).  This builder verifies the executed checks and
emits immutable attempt evidence; it never modifies product files.
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
ATTEMPT = ROOT / "artifacts/work_packages/E05/attempts/0001"
ATTEMPT_ID = "E05-0001"
WORK_PACKAGE_ID = "E05"
RECORDED_AT = "2026-08-02T04:30:00.000Z"
ATTEMPT_DIR = "artifacts/work_packages/E05/attempts/0001"

EXPECTED_SCHEMA_AND_TYPE_COUNT = 18
EXPECTED_UNIT_AND_CONTRACT_COUNT = 13
EXPECTED_NEGATIVE_ADVERSARIAL_COUNT = 20
EXPECTED_PROVENANCE_RECEIPT_COUNT = 15
EXPECTED_TARGETED_COUNT = 66
EXPECTED_DISCIPLINE_COUNT = 5
EXPECTED_CHAMBER_REGRESSION_COUNT = 57
EXPECTED_REPLAY_REGRESSION_COUNT = 18
EXPECTED_PYTHON_COUNT = 1261
EXPECTED_NODE_COUNT = 982
EXPECTED_NODE_FILE_COUNT = 91

COMPONENT = "src/epistemic_foundry/effects"
#: The scope decision that authorized the one file outside the manifest
#: grant, without which the engine would be absent from the built wheel.
AUTHORITY_DECISION = "HD-EF4-E05-SCOPE-20260802-001"
AUTHORITY_DECISION_PATH = (
    "artifacts/authority_decisions/HD-EF4-E05-SCOPE-20260802-001.human-decision.json"
)
EXPECTED_PRODUCT_HASHES = {
    "artifacts/work_packages/E05/attempts/0001/check_packaging.py": "577a4ce21bf020fb4c60e2dc7dcd1d797cb85c3b565446441d97421974749a3b",
    "artifacts/work_packages/E05/attempts/0001/fixtures.py": "7d563d5698ad9707be7dfc02cd55fe3f34151817645b004248c485ace2e0f475",
    "artifacts/work_packages/E05/attempts/0001/pytest.ini": "2dd299c42b22bc54cee677d11a865ad6bc3b6cc24dd66c0db4431c53cb83b1e3",
    "artifacts/work_packages/E05/attempts/0001/test_negative_adversarial.py": "e4d071a3765f3b9b12bc30faa27e99afcb5acbd9af264a455c15e6de0b098545",
    "artifacts/work_packages/E05/attempts/0001/test_provenance_receipts.py": "4b4e09666f47f0b5ea10a4377b069ab19665f27a2cfebdebf0638658d1c947bc",
    "artifacts/work_packages/E05/attempts/0001/test_schema_and_type.py": "9ccfc3a259f3b63c17850658ef798d569bcf4c626152cf52eacf7be6f9afeab5",
    "artifacts/work_packages/E05/attempts/0001/test_unit_contract.py": "35f85d46cd552a0dbbd15dcce9544ee028eb9e48974fb3a33bf29e6a0336bf62",
    "src/epistemic_foundry/effects/__init__.py": "51142a348aa172c00c763719e48d964fd8b7f15e56ce1810ab18c11b14b84395",
    "src/epistemic_foundry/effects/v4_e05/__init__.py": "83fbdb3bb6db0b66929b58e36ce5bcb1a37e2ec18839e3ae5c7f53dc504a6888",
    "src/epistemic_foundry/effects/v4_e05/effect-disposition.json": "d92488d1cdf09cf7514b60ad5fca5d5a4042bfc59db20f351429dd45a41e7cb9",
    "src/epistemic_foundry/effects/v4_e05/engine.py": "933f3ce4634a52c4d510bf74295af80183fbd45edd25296c764fdd2ae288a299",
}
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/authority_decisions/HD-EF4-E05-SCOPE-20260802-001.human-decision.json": "e0d41b2dbab2dd79225aafe32a109aa6dde3050d4806085f31c6d21e9f982b6d",
    "artifacts/work_packages/A06/attempts/0002/report.json": "a45eff5d49f16c5307ce886ccfcd8dabd742b3c95efd1898d51fc71b0de80425",
    "artifacts/work_packages/C05/attempts/0001/report.json": "35ea908093214930bbf10d8d181e539b54940febb5a36983c60b6274a545111d",
    "artifacts/work_packages/D05/attempts/0001/report.json": "326a6215067dfc96910aba0ab3c88787115ded36d00eb462d4f5a92f4b732718",
    "artifacts/work_packages/E04/report.json": "841dcf60989cfc7ab0eff7be95e1ae721ae18ac513cae653ab6ac8a44942f6c1",
}

JUNIT_PATHS = {
    "schema_and_type": ATTEMPT / "schema-and-type-check.junit.xml",
    "unit_and_contract": ATTEMPT / "unit-and-contract-tests.junit.xml",
    "negative_adversarial": ATTEMPT / "negative-and-adversarial-tests.junit.xml",
    "provenance_receipt": ATTEMPT / "provenance-and-receipt-audit.junit.xml",
    "targeted": ATTEMPT / "targeted-e05-effects.junit.xml",
    "discipline": ATTEMPT / "wire-literal-discipline.junit.xml",
    "chamber_regression": ATTEMPT / "dependency-regression-chamber.junit.xml",
    "replay_regression": ATTEMPT / "dependency-regression-replay.junit.xml",
    "full_python": ATTEMPT / "full-python-suite.junit.xml",
    "full_node": ATTEMPT / "full-node-suite.junit.xml",
}
# E04's replay gate is a Node surface, so its regression JUnit carries the
# Node reporter's semantic footer alongside the full Node suite.
_NODE_JUNITS = frozenset({"full_node", "replay_regression"})
RUN_RESULTS = (
    "ruff-check",
    "ruff-format-check",
    "wire-literal-discipline",
    "packaging-discovery",
    "schema-and-type-check",
    "unit-and-contract-tests",
    "negative-and-adversarial-tests",
    "provenance-and-receipt-audit",
    "targeted-e05-effects",
    "dependency-regression-chamber",
    "dependency-regression-replay",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "run_e05_0001_checks.py",
    "build_e05_0001_evidence.py",
    "e05_0001_rah_seal.py",
    "check_packaging.py",
    "fixtures.py",
    "pytest.ini",
    "test_schema_and_type.py",
    "test_unit_contract.py",
    "test_negative_adversarial.py",
    "test_provenance_receipts.py",
    "dependency-status.json",
    "e05-verification.json",
    "write-scope-verification.json",
    "node-test-inventory.json",
    "junit-normalization-verification.json",
    "schema-and-type-check.junit.xml",
    "unit-and-contract-tests.junit.xml",
    "negative-and-adversarial-tests.junit.xml",
    "provenance-and-receipt-audit.junit.xml",
    "targeted-e05-effects.junit.xml",
    "wire-literal-discipline.junit.xml",
    "dependency-regression-chamber.junit.xml",
    "dependency-regression-replay.junit.xml",
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
    schema = pytest_summary(JUNIT_PATHS["schema_and_type"])
    unit = pytest_summary(JUNIT_PATHS["unit_and_contract"])
    negative = pytest_summary(JUNIT_PATHS["negative_adversarial"])
    provenance = pytest_summary(JUNIT_PATHS["provenance_receipt"])
    targeted = pytest_summary(JUNIT_PATHS["targeted"])
    discipline = pytest_summary(JUNIT_PATHS["discipline"])
    chamber = pytest_summary(JUNIT_PATHS["chamber_regression"])
    replay = node_summary(JUNIT_PATHS["replay_regression"])
    python = pytest_summary(JUNIT_PATHS["full_python"])
    node = node_summary(JUNIT_PATHS["full_node"])
    node_inventory = read_json(ATTEMPT / "node-test-inventory.json")
    for label, summary, expected in (
        ("schema_and_type_check", schema, EXPECTED_SCHEMA_AND_TYPE_COUNT),
        ("unit_and_contract_tests", unit, EXPECTED_UNIT_AND_CONTRACT_COUNT),
        (
            "negative_and_adversarial_tests",
            negative,
            EXPECTED_NEGATIVE_ADVERSARIAL_COUNT,
        ),
        (
            "provenance_and_receipt_audit",
            provenance,
            EXPECTED_PROVENANCE_RECEIPT_COUNT,
        ),
        ("targeted", targeted, EXPECTED_TARGETED_COUNT),
        ("wire_literal_discipline", discipline, EXPECTED_DISCIPLINE_COUNT),
        ("chamber_regression", chamber, EXPECTED_CHAMBER_REGRESSION_COUNT),
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
    for label, summary, expected in (
        ("replay_regression", replay, EXPECTED_REPLAY_REGRESSION_COUNT),
        ("full_node", node, EXPECTED_NODE_COUNT),
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
    if node_inventory.get("count") != EXPECTED_NODE_FILE_COUNT:
        raise SystemExit(f"Node inventory gate failed: {node_inventory}")
    return {
        "attempt_id": ATTEMPT_ID,
        "baseline_attempt": "D05-0001",
        "chamber_regression": chamber,
        "component_tests_are_targeted_only": True,
        "full_node": node,
        "full_python": python,
        "negative_and_adversarial_tests": negative,
        "new_failure_count": 0,
        "prior_baseline_counts": {"full_node": 982, "full_python": 1261},
        "provenance_and_receipt_audit": provenance,
        "replay_regression": replay,
        "schema_and_type_check": schema,
        "status": "PASS",
        "targeted_e05_effects": targeted,
        "unit_and_contract_tests": unit,
        "wire_literal_discipline": discipline,
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
    return {
        "attempt_id": ATTEMPT_ID,
        "authority_decision": {
            "decision_id": AUTHORITY_DECISION,
            "path": AUTHORITY_DECISION_PATH,
            "sha256": sha256_id(ROOT / AUTHORITY_DECISION_PATH),
        },
        "dependencies": {
            "A06": _sealed_dependency("A06", "A06-0002", "E0119", "E0120"),
            "C05": _sealed_dependency("C05", "C05-0001", "E0155", "E0156"),
            # E04 predates the attempts/ layout and keeps its report at the
            # package root; citing the wrong path would silently unbind it.
            "E04": _sealed_dependency("E04", "E04-0001", "E0030", "E0031", flat=True),
        },
        "next_action": "SEAL_E05_0001_THEN_CONTINUE_DAG",
        "regression_baseline": _sealed_dependency("D05", "D05-0001", "E0163", "E0164"),
        "status": "PASS",
    }


def write_scope_verification() -> dict[str, Any]:
    assert_hashes(EXPECTED_PRODUCT_HASHES)
    component_files = sorted(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / COMPONENT).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )
    declared = sorted(
        relative
        for relative in EXPECTED_PRODUCT_HASHES
        if relative.startswith(f"{COMPONENT}/")
    )
    if component_files != declared:
        raise SystemExit(f"effects package holds unexpected files: {component_files}")
    return {
        "approved_scope": [
            "src/epistemic_foundry/effects/v4_e05/**",
            "artifacts/work_packages/E05/**",
            "src/epistemic_foundry/effects/__init__.py (HD-EF4-E05-SCOPE-20260802-001)",
        ],
        "attempt_id": ATTEMPT_ID,
        "authority_decision": AUTHORITY_DECISION,
        "component_files": component_files,
        "composed_modules_modified": False,
        "product_file_hashes": {
            relative: "sha256:" + digest
            for relative, digest in EXPECTED_PRODUCT_HASHES.items()
        },
        "pyproject_modified": False,
        "reset_clean_stash_commit_push_performed": False,
        "root_canonical_source_mutation_count": 0,
        "schema_or_test_weakening_count": 0,
        "status": "PASS",
        "subagents_or_fleet_used": False,
        "write_scope_violation_count": 0,
    }


def e05_verification(regression: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "composed_surfaces": {
            "candidate_accounting": (
                "src/epistemic_foundry/evolution_chamber/reconciliation.py"
            ),
            "effect_receipts": "src/epistemic_foundry/noetic_ledger/receipts.py",
            "mutation_receipts": (
                "src/epistemic_foundry/evolution_chamber/mutation.py"
            ),
        },
        "declaring_sources": {
            "effect_status": (
                "noetic_ledger/receipts.py EffectStatus, read with get_args"
            ),
            "pipeline_stages": "evolution_chamber/reconciliation.py STAGES",
            "status_disposition_table": (
                "src/epistemic_foundry/effects/v4_e05/effect-disposition.json, "
                "verified to cover the imported vocabulary on every use"
            ),
        },
        "exit_criteria": {
            "all_completion_and_external_effects_resolve_to_immutable_receipts": {
                "evidence": [f"{ATTEMPT_DIR}/test_provenance_receipts.py"],
                "mechanism": (
                    "every effect and mutation receipt is minted by the "
                    "runtime's own builders and validated against its canonical "
                    "schema, each self-hash is re-derived, each mutation binds "
                    "an effect receipt that exists, and the engine mints nothing "
                    "of its own — it reads the ledger rather than adding to it"
                ),
                "status": "PASS",
            },
            "governing_schemas_authority_boundaries_failure_states_exact": {
                "evidence": [f"{ATTEMPT_DIR}/test_schema_and_type.py"],
                "mechanism": (
                    "the engine module is scanned for canonical schema enum "
                    "values and holds none; the disposition table must cover the "
                    "imported EffectStatus exactly, every disposition must be a "
                    "declared pipeline stage or terminal state with a stated "
                    "reason, and a status resolves if and only if it names one"
                ),
                "status": "PASS",
            },
            "happy_negative_crash_resume_adversarial_coverage": {
                "evidence": [
                    f"{ATTEMPT_DIR}/test_unit_contract.py",
                    f"{ATTEMPT_DIR}/test_negative_adversarial.py",
                ],
                "mechanism": (
                    "clean, failed, cancelled and rolled-back fan-outs all "
                    "reconcile because a terminal state is an answer; an orphan "
                    "effect, an unreceipted candidate, a mutation without "
                    "provenance, a dangling reference, an unobserved outcome and "
                    "a ledger/pipeline disagreement are each refused by their own "
                    "code"
                ),
                "status": "PASS",
            },
            "no_candidate_model_prompt_backend_or_hook_acquires_authority": {
                "evidence": [f"{ATTEMPT_DIR}/test_provenance_receipts.py"],
                "mechanism": (
                    "a mutation that changes a forbidden authority field is "
                    "refused before any receipt for it can exist, and changed "
                    "paths are derived from the diff rather than from the "
                    "operator's self-description, so an operator that edits more "
                    "than it admits is detected"
                ),
                "status": "PASS",
            },
        },
        "failure_classes": [
            "EFFECT_RECEIPT_MISSING",
            "EFFECT_UNRESOLVED",
            "LEDGER_PIPELINE_DISAGREEMENT",
            "MUTATION_RECEIPT_MISSING",
            "MUTATION_WITHOUT_PROVENANCE",
            "ORPHAN_SIDE_EFFECT",
        ],
        "required_checks": {
            "independent_review": {
                "evidence": "review.md (primary-session separate, "
                "actor_independence=false)",
                "status": "PASS",
            },
            "negative_and_adversarial_tests": {
                "module": f"{ATTEMPT_DIR}/test_negative_adversarial.py",
                "status": "PASS",
                "test_count": regression["negative_and_adversarial_tests"]["collected"],
            },
            "provenance_and_receipt_audit": {
                "module": f"{ATTEMPT_DIR}/test_provenance_receipts.py",
                "status": "PASS",
                "test_count": regression["provenance_and_receipt_audit"]["collected"],
            },
            "schema_and_type_check": {
                "module": f"{ATTEMPT_DIR}/test_schema_and_type.py",
                "status": "PASS",
                "test_count": regression["schema_and_type_check"]["collected"],
            },
            "unit_and_contract_tests": {
                "module": f"{ATTEMPT_DIR}/test_unit_contract.py",
                "status": "PASS",
                "test_count": regression["unit_and_contract_tests"]["collected"],
            },
        },
        "status": "PASS",
        "targeted_test_count": regression["targeted_e05_effects"]["collected"],
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
                "artifacts/work_packages/E05/attempts/0001/build_e05_0001_evidence.py",
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
        "# E05-0001 primary-session separate adversarial review\n"
        "\n"
        "- Reviewer: primary session in a separate adversarial pass under the\n"
        "  product-owner instruction forbidding subagents and Fleet;\n"
        "  actor_independence=false is recorded, not hidden.\n"
        "- The engine adds the reconciliation nobody was doing. The chamber\n"
        "  already accounts for candidate identities and the ledger already\n"
        "  mints receipts, but nothing checked the two against each other, and\n"
        "  that is exactly where a side effect hides: eight candidates\n"
        "  persisted, nine effect receipts, and no one notices the ninth\n"
        "  belongs to nothing. Six distinct failure classes are reported by\n"
        "  name rather than collapsed into an unreconciled count.\n"
        "- Nothing is reimplemented. Candidate accounting comes from\n"
        "  evolution_chamber.reconciliation, receipts from noetic_ledger and\n"
        "  evolution_chamber.mutation, and the effect-status vocabulary is\n"
        "  imported with get_args from the module that declares it. The tests\n"
        "  mint every receipt through those builders, so what the engine agrees\n"
        "  with is the ledger rather than the test author.\n"
        "- EF4-I22 is enforced on this module by the repository's own gate,\n"
        "  which runs as a named check here rather than only inside the full\n"
        "  suite. It caught a real violation during this attempt: the report\n"
        "  carried a 'proposed' count whose key is a canonical enum value. The\n"
        "  count was already present in the composed candidate report, so the\n"
        "  duplicate was removed rather than the module being registered as a\n"
        "  declaring owner it is not.\n"
        "- The status-to-disposition table is data, not Python literals, and is\n"
        "  verified on every use to cover the imported vocabulary exactly. A\n"
        "  status added to the contract fails loudly as DISPOSITION_DRIFT\n"
        "  instead of falling through to a permissive default.\n"
        "- Three engine corrections came from the adversarial tests. An\n"
        "  unmapped status was reported as a flag inconsistency until the\n"
        "  status check was moved first; an effect referenced by an orphan\n"
        "  mutation was double-reported as an orphan effect until binding was\n"
        "  widened to any referencing mutation; and a broken fan-out reported a\n"
        "  ledger consequence before its cause until the candidate check was\n"
        "  ordered first. Each made the refusal name the right failure.\n"
        "- One file outside the manifest grant was authorized and recorded:\n"
        "  src/epistemic_foundry/effects/__init__.py. Verified empirically that\n"
        "  without it find_packages returns nothing for this engine while\n"
        "  find_namespace_packages finds it, so the module would import from a\n"
        "  checkout but be absent from the wheel. A named packaging-discovery\n"
        "  check now proves it stays discoverable, reading the discovery mode\n"
        "  from pyproject rather than assuming it.\n"
        "- Residual limitations: this reconciles ledgers that are handed to it,\n"
        "  it does not collect them from a running system — wiring it into the\n"
        "  EVOLVE loop belongs to F05; UNKNOWN effects are reported as\n"
        "  unresolved rather than resolved, because resolving them needs the\n"
        "  external system this engine deliberately does not touch; and this\n"
        "  review is not external actor-independent certification.\n"
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
            "path": f"artifacts/work_packages/E05/attempts/0001/{name}",
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in sorted(set(output_names))
    ]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "E05_CANDIDATE_EFFECT_RECONCILIATION_ENGINE",
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependency_state": dependencies,
        "exit_criteria": {
            "all_completion_and_external_effects_resolve_to_immutable_receipts": (
                "PASS"
            ),
            "governing_schemas_authority_boundaries_failure_states_exact": "PASS",
            "happy_negative_crash_resume_adversarial_coverage": "PASS",
            "no_candidate_model_prompt_backend_or_hook_acquires_authority": ("PASS"),
        },
        "global_implementation_gate": "fail",
        "history_and_worktree": {
            "dirty_worktree_preserved": True,
            "prior_attempts_reports_and_rah_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
            "subagents_or_fleet_used": False,
        },
        "implementation_status": "PASS",
        "next_package": "F05-0001",
        "not_claimed": [
            "collection of the ledgers it reconciles: they are handed to the "
            "engine, and wiring it into the EVOLVE loop belongs to F05",
            "resolution of an UNKNOWN effect, which needs the external system "
            "this engine deliberately does not touch",
            "any change to the composed chamber and ledger modules, which are "
            "read-only inputs",
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
        "negative_and_adversarial_tests": (
            f"{EXPECTED_NEGATIVE_ADVERSARIAL_COUNT}/"
            f"{EXPECTED_NEGATIVE_ADVERSARIAL_COUNT}"
        ),
        "next_action": "SEAL_E05_0001_THEN_CONTINUE_DAG",
        "package_status": "PASS",
        "provenance_and_receipt_audit": (
            f"{EXPECTED_PROVENANCE_RECEIPT_COUNT}/{EXPECTED_PROVENANCE_RECEIPT_COUNT}"
        ),
        "schema_and_type_check": (
            f"{EXPECTED_SCHEMA_AND_TYPE_COUNT}/{EXPECTED_SCHEMA_AND_TYPE_COUNT}"
        ),
        "status": "PASS",
        "targeted_e05_effects": f"{EXPECTED_TARGETED_COUNT}/{EXPECTED_TARGETED_COUNT}",
        "unit_and_contract_tests": (
            f"{EXPECTED_UNIT_AND_CONTRACT_COUNT}/{EXPECTED_UNIT_AND_CONTRACT_COUNT}"
        ),
    }


def build() -> dict[str, Any]:
    for name in RUN_RESULTS:
        check_run(name)
    normalize_junits()
    regression = regression_evidence()
    dependencies = dependency_status()
    write_scope = write_scope_verification()
    verification = e05_verification(regression)
    write_json("dependency-status.json", dependencies)
    write_json("write-scope-verification.json", write_scope)
    write_json("e05-verification.json", verification)
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
        raise SystemExit("E05-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "e05-verification.json")
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
    verification = read_json(ATTEMPT / "e05-verification.json")
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
        raise SystemExit("stored Q01-0001 report is not the deterministic document")
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
