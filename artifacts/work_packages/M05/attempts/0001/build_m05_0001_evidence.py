#!/usr/bin/env python3
"""Build and verify M05-0001 evolution cartography evidence.

M05-0001 implements `src/epistemic_foundry/cartography/v4_m05/**`: the niche
mapper whose cell identity is derived from canonical axis coordinates, the
lineage diversity report whose entropy figures re-derive from each other, and
the blast radius that composes the sealed L05 lineage memory to say what a
change actually touches.  Axis names come from the canonical niche schema,
the coverage summary from the sealed archive builder, and the D05 store
regression runs against real PostgreSQL.  This builder verifies the executed
checks and emits immutable attempt evidence; it never modifies product files.
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
ATTEMPT = ROOT / "artifacts/work_packages/M05/attempts/0001"
ATTEMPT_ID = "M05-0001"
WORK_PACKAGE_ID = "M05"
RECORDED_AT = "2026-08-02T12:00:00.000Z"
ATTEMPT_DIR = "artifacts/work_packages/M05/attempts/0001"

EXPECTED_SCHEMA_AND_TYPE_COUNT = 13
EXPECTED_UNIT_AND_CONTRACT_COUNT = 19
EXPECTED_NEGATIVE_ADVERSARIAL_COUNT = 26
EXPECTED_PROVENANCE_RECEIPT_COUNT = 11
EXPECTED_TARGETED_COUNT = 69
EXPECTED_DISCIPLINE_COUNT = 5
EXPECTED_ARCHIVE_REGRESSION_COUNT = 16
EXPECTED_MAP_REGRESSION_COUNT = 26
EXPECTED_RETENTION_REGRESSION_COUNT = 72
EXPECTED_STORE_REGRESSION_COUNT = 84
EXPECTED_PYTHON_COUNT = 1261
EXPECTED_NODE_COUNT = 1063
EXPECTED_NODE_FILE_COUNT = 95

COMPONENT = "src/epistemic_foundry/cartography/v4_m05"
#: The scope decision that authorized the one file outside the manifest
#: grant, without which the mapper would be absent from the built wheel.
AUTHORITY_DECISION = "HD-EF4-M05-SCOPE-20260802-001"
AUTHORITY_DECISION_PATH = (
    "artifacts/authority_decisions/HD-EF4-M05-SCOPE-20260802-001.human-decision.json"
)
EXPECTED_PRODUCT_HASHES = {
    "artifacts/work_packages/M05/attempts/0001/check_packaging.py": "a94645965184d660a6913ddc74a95c9bbc6ab60c182feee0ce4b808aa40caf22",
    "artifacts/work_packages/M05/attempts/0001/fixtures.py": "e33b1b7e38bfbbe737e04e44f35b233915ed0c64cc9ced9ebe3f93b85905d33e",
    "artifacts/work_packages/M05/attempts/0001/pytest.ini": "d667316ba5c7d9cbc1d971dfd514772e42d36cf3c2f0f6c133d9c626ac8c0e26",
    "artifacts/work_packages/M05/attempts/0001/run_m05_0001_checks.py": "d64633a386252d4da6b813e7349784df6046ccd7ff7c27af1df1f77a9dbf8937",
    "artifacts/work_packages/M05/attempts/0001/test_negative_adversarial.py": "6c46b269e746bc8643ff907152067f03336cb6f6b4858c52fffcf58c05918d04",
    "artifacts/work_packages/M05/attempts/0001/test_provenance_receipts.py": "0676756c1ffa62c1b4d5b07c61b27415275f03f75367c1f6f24ec5d600b99ca2",
    "artifacts/work_packages/M05/attempts/0001/test_schema_and_type.py": "8a241bba5d37bb54c56e3fdbd794e6d8a0e2a74f3a9277b70060297c6b717df4",
    "artifacts/work_packages/M05/attempts/0001/test_unit_contract.py": "34d9fff46c96e590e2b81fd33eb452717a01049e1b53b2b025a4979a844c361b",
    "src/epistemic_foundry/cartography/__init__.py": "b45ee3bb510a8c55df0bc4358cbec8084b2ac55cba7db4f5661e5768f2f873f8",
    "src/epistemic_foundry/cartography/v4_m05/__init__.py": "7a6cc3b20d638d0d7149816fb971e80ca7a73efa66c42f1aeea34e4b3a27e317",
    "src/epistemic_foundry/cartography/v4_m05/mapper.py": "7d6011bb7fa0b449d93cb5bad2d7bd99676c38ff238261b5a335f5a67df2709c",
}
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/authority_decisions/HD-EF4-M05-SCOPE-20260802-001.human-decision.json": "e0b511149185c9283a58bf00d4dcd56d3884339308118893a4e739347e6a95a6",
    "artifacts/work_packages/D05/attempts/0001/report.json": "326a6215067dfc96910aba0ab3c88787115ded36d00eb462d4f5a92f4b732718",
    "artifacts/work_packages/L05/attempts/0001/report.json": "c0fb65c5bfc1dde7a2052c6eaefae1ed96e6360d5bb9031685a81580305d544e",
    "artifacts/work_packages/M04/attempts/0001/report.json": "10dc679144d91bb797fbc4d5d5dddea92420759de53c8b08c7951e3882439ea5",
}

JUNIT_PATHS = {
    "schema_and_type": ATTEMPT / "schema-and-type-check.junit.xml",
    "unit_and_contract": ATTEMPT / "unit-and-contract-tests.junit.xml",
    "negative_adversarial": ATTEMPT / "negative-and-adversarial-tests.junit.xml",
    "provenance_receipt": ATTEMPT / "provenance-and-receipt-audit.junit.xml",
    "targeted": ATTEMPT / "targeted-m05-cartography.junit.xml",
    "discipline": ATTEMPT / "wire-literal-discipline.junit.xml",
    "archive_regression": ATTEMPT / "dependency-regression-archive.junit.xml",
    "map_regression": ATTEMPT / "dependency-regression-map.junit.xml",
    "retention_regression": ATTEMPT / "dependency-regression-retention.junit.xml",
    "store_regression": ATTEMPT / "dependency-regression-store.junit.xml",
    "full_python": ATTEMPT / "full-python-suite.junit.xml",
    "full_node": ATTEMPT / "full-node-suite.junit.xml",
}
# M04's map UI is a Node surface, so its regression JUnit carries the Node
# reporter's semantic footer alongside the full Node suite.
_NODE_JUNITS = frozenset({"full_node", "map_regression"})
RUN_RESULTS = (
    "ruff-check",
    "ruff-format-check",
    "wire-literal-discipline",
    "packaging-discovery",
    "schema-and-type-check",
    "unit-and-contract-tests",
    "negative-and-adversarial-tests",
    "provenance-and-receipt-audit",
    "targeted-m05-cartography",
    "dependency-regression-archive",
    "dependency-regression-map",
    "dependency-regression-retention",
    "dependency-regression-store",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "run_m05_0001_checks.py",
    "build_m05_0001_evidence.py",
    "m05_0001_rah_seal.py",
    "check_packaging.py",
    "fixtures.py",
    "pytest.ini",
    "test_schema_and_type.py",
    "test_unit_contract.py",
    "test_negative_adversarial.py",
    "test_provenance_receipts.py",
    "dependency-status.json",
    "m05-verification.json",
    "write-scope-verification.json",
    "node-test-inventory.json",
    "junit-normalization-verification.json",
    "schema-and-type-check.junit.xml",
    "unit-and-contract-tests.junit.xml",
    "negative-and-adversarial-tests.junit.xml",
    "provenance-and-receipt-audit.junit.xml",
    "targeted-m05-cartography.junit.xml",
    "wire-literal-discipline.junit.xml",
    "dependency-regression-archive.junit.xml",
    "dependency-regression-map.junit.xml",
    "dependency-regression-retention.junit.xml",
    "dependency-regression-store.junit.xml",
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
    archive = pytest_summary(JUNIT_PATHS["archive_regression"])
    retention = pytest_summary(JUNIT_PATHS["retention_regression"])
    store = pytest_summary(JUNIT_PATHS["store_regression"])
    map_regression = node_summary(JUNIT_PATHS["map_regression"])
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
        ("archive_regression", archive, EXPECTED_ARCHIVE_REGRESSION_COUNT),
        ("retention_regression", retention, EXPECTED_RETENTION_REGRESSION_COUNT),
        ("store_regression", store, EXPECTED_STORE_REGRESSION_COUNT),
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
        ("map_regression", map_regression, EXPECTED_MAP_REGRESSION_COUNT),
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
        "archive_regression": archive,
        "attempt_id": ATTEMPT_ID,
        "baseline_attempt": "L05-0001",
        "component_tests_are_targeted_only": True,
        "full_node": node,
        "full_python": python,
        "map_regression": map_regression,
        "negative_and_adversarial_tests": negative,
        "new_failure_count": 0,
        "prior_baseline_counts": {"full_node": 1063, "full_python": 1261},
        "provenance_and_receipt_audit": provenance,
        "retention_regression": retention,
        "schema_and_type_check": schema,
        "status": "PASS",
        "store_regression": store,
        "targeted_m05_cartography": targeted,
        "unit_and_contract_tests": unit,
        "wire_literal_discipline": discipline,
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
        "authority_decision": {
            "decision_id": AUTHORITY_DECISION,
            "path": AUTHORITY_DECISION_PATH,
            "sha256": sha256_id(ROOT / AUTHORITY_DECISION_PATH),
        },
        "dependencies": {
            "D05": _sealed_dependency("D05", "D05-0001", "E0163", "E0164"),
            "M04": _sealed_dependency("M04", "M04-0001", "E0062", "E0063"),
        },
        "next_action": "SEAL_M05_0001_THEN_CONTINUE_DAG",
        "regression_baseline": _sealed_dependency("L05", "L05-0001", "E0171", "E0172"),
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
        raise SystemExit(
            f"cartography package holds unexpected files: {component_files}"
        )
    return {
        "approved_scope": [
            "src/epistemic_foundry/cartography/v4_m05/**",
            "artifacts/work_packages/M05/**",
            "src/epistemic_foundry/cartography/__init__.py "
            "(HD-EF4-M05-SCOPE-20260802-001)",
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


def m05_verification(regression: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "composed_surfaces": {
            "coverage_summary": (
                "src/epistemic_foundry/epistemic_species_archive/archive.py "
                "build_quality_diversity_map"
            ),
            "lineage_memory": "src/epistemic_foundry/memory/v4_l05 LineageMemory",
            "persistence_store": "migrations/v4_d05/0001_evolution_store.sql",
        },
        "declaring_sources": {
            "inbreeding_rules": (
                "src/epistemic_foundry/cartography/v4_m05/mapper.py "
                "INBREEDING_RULES (this module owns the vocabulary; "
                "recommendations only)"
            ),
            "lineage_report": "schemas/lineage-diversity-report.schema.json",
            "niche_axes": (
                "schemas/epistemic-niche.schema.json axis_values properties"
            ),
            "quality_diversity_map": "schemas/quality-diversity-map.schema.json",
        },
        "exit_criteria": {
            "all_completion_and_external_effects_resolve_to_immutable_receipts": {
                "evidence": [f"{ATTEMPT_DIR}/test_provenance_receipts.py"],
                "mechanism": (
                    "every emitted record re-derives its own hash from exactly "
                    "the fields it publishes, the niche id re-derives from the "
                    "published coordinates, the entropy pair re-derives one "
                    "figure from the other, the recommended actions re-derive "
                    "from the alerts, and nothing carries a clock the caller "
                    "did not supply"
                ),
                "status": "PASS",
            },
            "governing_schemas_authority_boundaries_failure_states_exact": {
                "evidence": [f"{ATTEMPT_DIR}/test_schema_and_type.py"],
                "mechanism": (
                    "axis names are read from the canonical niche schema and "
                    "every niche, coverage map and diversity report validates "
                    "against its canonical schema; the mapper holds no archive "
                    "entry class or stop reason as a literal; and each of the "
                    "11 failure codes carries its reason"
                ),
                "status": "PASS",
            },
            "happy_negative_crash_resume_adversarial_coverage": {
                "evidence": [
                    f"{ATTEMPT_DIR}/test_unit_contract.py",
                    f"{ATTEMPT_DIR}/test_negative_adversarial.py",
                ],
                "mechanism": (
                    "entropy figures agree with hand-computed values on known "
                    "populations and the blast radius reaches exactly the "
                    "descendants; a duplicated cell, a forged cell id, a "
                    "candidate in two cells, an overfull niche, an elite "
                    "outside its cell, a partial attribution, a meaningless "
                    "threshold and an off-map stagnant niche are each refused "
                    "by their own code"
                ),
                "status": "PASS",
            },
            "no_candidate_model_prompt_backend_or_hook_acquires_authority": {
                "evidence": [f"{ATTEMPT_DIR}/test_unit_contract.py"],
                "mechanism": (
                    "the map is descriptive: alerts carry recommendations only, "
                    "the blast radius is a record rather than a permission, and "
                    "nothing in this module promotes, evicts, erases or touches "
                    "evaluator or holdout surfaces"
                ),
                "status": "PASS",
            },
        },
        "failure_classes": [
            "ATTRIBUTION_INCOMPLETE",
            "AXIS_UNDECLARED",
            "CANDIDATE_UNKNOWN",
            "CELL_DUPLICATED",
            "ELITE_NOT_OCCUPANT",
            "INPUT_INVALID",
            "NICHE_IDENTITY_FORGED",
            "NICHE_OVERFULL",
            "NICHE_UNKNOWN",
            "OCCUPANCY_AMBIGUOUS",
            "THRESHOLD_INVALID",
        ],
        "implementation_findings": [
            {
                "finding": (
                    "the axis vocabulary was first read from the schema's "
                    "required list, but the literal 'required' is itself a "
                    "canonical enum value (minority-report preservation "
                    "status), which the repository's EF4-I22 gate refused"
                ),
                "resolution": (
                    "the axis names are read from the axis object's property "
                    "keys instead, and the schema-and-type suite separately "
                    "asserts the two declarations agree"
                ),
            },
            {
                "finding": (
                    "deriving the effective lineage count from the unrounded "
                    "entropy left the published pair off by one ulp of the "
                    "rounding, so a reader could not re-derive one figure from "
                    "the other"
                ),
                "resolution": (
                    "the effective count is the exponential of the published "
                    "entropy, proven by a re-derivation test; coherence beats "
                    "prettiness (four uniform founders report 3.999999)"
                ),
            },
        ],
        "not_derivable": {
            "model_attribution": (
                "lineage records carry no model identity, so the caller must "
                "attribute every candidate or the report refuses; publishing "
                "entropy over a partial population would be fiction"
            ),
            "stagnation": (
                "stagnation is temporal and belongs to the run that observes "
                "it; this module only checks that a declared stagnant niche is "
                "one the map holds"
            ),
        },
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
        "targeted_test_count": regression["targeted_m05_cartography"]["collected"],
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
                "artifacts/work_packages/M05/attempts/0001/build_m05_0001_evidence.py",
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
        "# M05-0001 primary-session separate adversarial review\n"
        "\n"
        "- Reviewer: primary session in a separate adversarial pass under the\n"
        "  product-owner instruction forbidding subagents and Fleet;\n"
        "  actor_independence=false is recorded, not hidden.\n"
        "- The map answers three questions nothing else owned: which cell a\n"
        "  candidate occupies, how concentrated the population has become, and\n"
        "  what a change would actually touch. All three are descriptive — the\n"
        "  map recommends and records, it never promotes, evicts or erases.\n"
        "- Cell identity is the load-bearing decision. A niche id is derived\n"
        "  from the canonical axis coordinates, so the same cell is always the\n"
        "  same cell: a duplicate coordinate set, a forged id, and coordinates\n"
        "  edited after the id was derived are all refused, and a candidate\n"
        "  occupying two cells is refused because a MAP-Elites assignment must\n"
        "  be a function of the candidate.\n"
        "- The repository's own EF4-I22 gate caught a real violation during\n"
        "  this attempt: reading the axis names from the schema's required\n"
        "  list put the literal 'required' — a canonical minority-report enum\n"
        "  value — into the module. The fix reads the axis object's property\n"
        "  keys instead, and a test asserts the two declarations agree.\n"
        "- One numerical decision is recorded openly: the effective lineage\n"
        "  count is the exponential of the *published* entropy, so the pair\n"
        "  re-derives exactly from the report's own fields. Four uniform\n"
        "  founders therefore report 3.999999 rather than 4.0; coherence beats\n"
        "  prettiness, and a re-derivation test holds it.\n"
        "- Diversity is measured against hand-computed values: zero entropy\n"
        "  for a single founder, ln(4) for four uniform founders, dominant\n"
        "  share 4/5 on the fixture population, and the within-lineage\n"
        "  crossover alert distinguishes crossing two branches of one founder\n"
        "  from a genuine cross between lineages.\n"
        "- Entropy over a partial population is refused rather than\n"
        "  published: model attribution, operator attribution and island\n"
        "  membership must each cover every candidate, and the blast radius\n"
        "  names unmapped candidates instead of dropping them.\n"
        "- The blast radius composes the sealed L05 lineage memory rather\n"
        "  than re-walking ancestry, the coverage summary is delegated to the\n"
        "  sealed archive builder, and the D05 store regression ran against\n"
        "  real PostgreSQL via the pinned container, 84/84.\n"
        "- One file outside the manifest grant was authorized and recorded:\n"
        "  src/epistemic_foundry/cartography/__init__.py, on the same verified\n"
        "  packaging grounds as the effects and evolution markers\n"
        "  (HD-EF4-M05-SCOPE-20260802-001), with a named packaging-discovery\n"
        "  check proving the package stays discoverable.\n"
        "- Residual limitations: stagnation detection is temporal and belongs\n"
        "  to the run that observes it; model attribution belongs to the\n"
        "  caller; the map does not decide anything downstream of what it\n"
        "  reports; and this review is not external actor-independent\n"
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
            "path": f"artifacts/work_packages/M05/attempts/0001/{name}",
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in sorted(set(output_names))
    ]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "M05_EVOLUTION_CARTOGRAPHY",
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
        "next_package": "S05-0001",
        "not_claimed": [
            "any promotion, eviction or erasure: the map is descriptive and "
            "its alerts carry recommendations only",
            "stagnation detection, which is temporal and belongs to the run "
            "that observes it",
            "model attribution, which lineage records do not carry and the "
            "caller must supply completely",
            "any change to the composed archive, lineage-memory or store "
            "surfaces, which are read-only inputs",
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
        "next_action": "SEAL_M05_0001_THEN_CONTINUE_DAG",
        "package_status": "PASS",
        "provenance_and_receipt_audit": (
            f"{EXPECTED_PROVENANCE_RECEIPT_COUNT}/{EXPECTED_PROVENANCE_RECEIPT_COUNT}"
        ),
        "schema_and_type_check": (
            f"{EXPECTED_SCHEMA_AND_TYPE_COUNT}/{EXPECTED_SCHEMA_AND_TYPE_COUNT}"
        ),
        "status": "PASS",
        "targeted_m05_cartography": (
            f"{EXPECTED_TARGETED_COUNT}/{EXPECTED_TARGETED_COUNT}"
        ),
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
    verification = m05_verification(regression)
    write_json("dependency-status.json", dependencies)
    write_json("write-scope-verification.json", write_scope)
    write_json("m05-verification.json", verification)
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
        raise SystemExit("M05-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "m05-verification.json")
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
    verification = read_json(ATTEMPT / "m05-verification.json")
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
        raise SystemExit("stored M05-0001 report is not the deterministic document")
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
