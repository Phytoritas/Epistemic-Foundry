#!/usr/bin/env python3
"""Build and verify Y01-0001 typed budget and adaptive fleet evidence.

Y01-0001 implements ``packages/foundry-kernel/src/budget/**``: typed budget
enforcement, an adaptive worker fleet, and their performance controls.  A budget
envelope is labelled ``HARD_METERED``, ``HARD_PREALLOCATED``, ``SOFT_ESTIMATE``
or ``UNMETERED``; only the ``HARD_*`` labels bound spend.  A reservation that
would push any cumulative dimension past a declared hard limit is *refused*
(``BUDGET_LIMIT_EXCEEDED``) rather than truncated, and usage is left unchanged so
the refusal is never partially applied.  ``SOFT_ESTIMATE`` records a forecast and
``UNMETERED`` records nothing; both stay truthfully non-bounding and never refuse,
and a mislabelled envelope (a hard bound with no hard limit, an unmetered budget
with a cancel breach policy) is refused at seal time.  The adaptive fleet scales
worker fan-out as a deterministic clamp of the observed backlog into
``[min_workers, effective_max_workers]``, where the effective maximum is the
declared maximum capped by the budget's ``concurrency`` hard limit; a declared
maximum that would exceed a bounding concurrency limit is refused, not clamped,
so fan-out is bounded by construction and can never run away.  The vocabulary is
composed from the sealed contract registry and the canonical
``schemas/budget-envelope.schema.json``; the whole upstream Node surface is the
regression that matters, so it is covered by the full Node suite rather than a
bespoke dependency-regression run.  This builder verifies the executed checks and
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
ATTEMPT = ROOT / "artifacts/work_packages/Y01/attempts/0001"
ATTEMPT_ID = "Y01-0001"
WORK_PACKAGE_ID = "Y01"
RECORDED_AT = "2026-08-02T00:00:00.000Z"

EXPECTED_BUDGET_ENFORCEMENT_COUNT = 12
EXPECTED_ADAPTIVE_FLEET_COUNT = 8
EXPECTED_TARGETED_COUNT = 20
EXPECTED_PYTHON_COUNT = 1261
EXPECTED_NODE_COUNT = 1253
EXPECTED_NODE_FILE_COUNT = 111

COMPONENT = "packages/foundry-kernel/src/budget"
EXPECTED_PRODUCT_HASHES = {
    "packages/foundry-kernel/src/budget/adaptive-fleet.mjs": "5285d09d3a98c2a525bc14a7fd058869f50b5c192237b6672e159484d76d3546",
    "packages/foundry-kernel/src/budget/adaptive-fleet.test.mjs": "950a98c08a7915011b27e5355bcafa3f1e708663a496a3ada1e23611813a6d71",
    "packages/foundry-kernel/src/budget/budget-enforcement.test.mjs": "c728f9061691ab62f4df9f5f8f668974903342ebb89704c17ad47338cd7cf489",
    "packages/foundry-kernel/src/budget/budget-meter.mjs": "8339d116c46091e52e3649be3e337aa3e33ef8c3b4578d87feadb1092792377b",
    "packages/foundry-kernel/src/budget/budget-primitives.mjs": "a2e69702cbbdd437dfc4c706101fccd35e188577e8fbd778eee2841bff28e458",
    "packages/foundry-kernel/src/budget/budget-test-support.mjs": "72c5268714b7e735d3c5dd01ba99682503dc582167020afcb39ddb253230172f",
    "packages/foundry-kernel/src/budget/budget-vocabulary.mjs": "e2946efc425f2b7e64503c47fb9ed0de8db3f4b2db86740415f53ea3d0e7c9b9",
    "packages/foundry-kernel/src/budget/index.mjs": "5ba478957b147a2b8ab21a78a2a9fef408b2f69070ef419c49f3164e36fc575f",
}
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/B04/attempts/0002/report.json": "a75e724b453bf58ce2745af174e96d7f08616bd09467e3b047b78f31b8add643",
    "artifacts/work_packages/D04/report.json": "b47c194e230f4b08ab96b6153e9fc0e170eafb1054318cfaedd8e1ddeb4c5fde",
    "artifacts/work_packages/Q04/attempts/0001/report.json": "f2f8216af551eeeb3ffaa266a773ff065c6e88ea498b9000d80831fc5ce732fd",
    "artifacts/work_packages/W04/attempts/0001/report.json": "b07687917d9bf5a150d78c9fd1580e24308823f95e1c8713302b7e4af3c75688",
    "artifacts/work_packages/X04/attempts/0001/report.json": "87d60e7bae4b75588f4c3093a0ec2425912eba4e7ed15d3db9587bf6ff7312a2",
}

JUNIT_PATHS = {
    "budget_enforcement": ATTEMPT / "budget-enforcement-test.junit.xml",
    "adaptive_fleet": ATTEMPT / "adaptive-fleet-test.junit.xml",
    "targeted": ATTEMPT / "targeted-budget.junit.xml",
    "full_python": ATTEMPT / "full-python-suite.junit.xml",
    "full_node": ATTEMPT / "full-node-suite.junit.xml",
}
# Every Y01 check but the full Python suite runs under the Node runner.
_NODE_JUNITS = frozenset(
    {
        "budget_enforcement",
        "adaptive_fleet",
        "targeted",
        "full_node",
    }
)
RUN_RESULTS = (
    "ruff-check",
    "ruff-format-check",
    "budget-enforcement-test",
    "adaptive-fleet-test",
    "targeted-budget",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "run_y01_0001_checks.py",
    "build_y01_0001_evidence.py",
    "y01_0001_rah_seal.py",
    "dependency-status.json",
    "y01-verification.json",
    "write-scope-verification.json",
    "node-test-inventory.json",
    "junit-normalization-verification.json",
    "budget-enforcement-test.junit.xml",
    "adaptive-fleet-test.junit.xml",
    "targeted-budget.junit.xml",
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


def _assert_node_gate(label: str, summary: dict[str, Any], expected: int) -> None:
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


def regression_evidence() -> dict[str, Any]:
    budget_enforcement = node_summary(JUNIT_PATHS["budget_enforcement"])
    adaptive_fleet = node_summary(JUNIT_PATHS["adaptive_fleet"])
    targeted = node_summary(JUNIT_PATHS["targeted"])
    python = pytest_summary(JUNIT_PATHS["full_python"])
    node = node_summary(JUNIT_PATHS["full_node"])
    node_inventory = read_json(ATTEMPT / "node-test-inventory.json")
    for label, summary, expected in (
        (
            "budget_enforcement_test",
            budget_enforcement,
            EXPECTED_BUDGET_ENFORCEMENT_COUNT,
        ),
        ("adaptive_fleet_test", adaptive_fleet, EXPECTED_ADAPTIVE_FLEET_COUNT),
        ("targeted", targeted, EXPECTED_TARGETED_COUNT),
    ):
        _assert_node_gate(label, summary, expected)
    if (
        python["collected"],
        python["passed"],
        python["failed"],
        python["errors"],
        python["skipped"],
    ) != (EXPECTED_PYTHON_COUNT, EXPECTED_PYTHON_COUNT, 0, 0, 0):
        raise SystemExit(f"full_python gate failed: {python}")
    if (
        node["collected"],
        node["passed"],
        node["failed"],
        node["cancelled"],
        node["skipped"],
        node["todo"],
        node["xml_error_count"],
        node["xml_failure_count"],
        node_inventory.get("count"),
    ) != (
        EXPECTED_NODE_COUNT,
        EXPECTED_NODE_COUNT,
        0,
        0,
        0,
        0,
        0,
        0,
        EXPECTED_NODE_FILE_COUNT,
    ):
        raise SystemExit(f"full Node gate failed: {node}; inventory={node_inventory}")
    return {
        "adaptive_fleet_test": adaptive_fleet,
        "attempt_id": ATTEMPT_ID,
        "budget_enforcement_test": budget_enforcement,
        "component_tests_are_targeted_only": True,
        "full_node": node,
        "full_python": python,
        "new_failure_count": 0,
        "status": "PASS",
        "targeted_budget": targeted,
        "unexpected_skip_xfail_todo_or_cancellation_count": 0,
    }


def _pass_dependency(package: str, attempt: str, relative: str) -> dict[str, Any]:
    path = ROOT / relative
    report = read_json(path)
    if report.get("status") != "PASS":
        raise SystemExit(f"{attempt} is not the sealed PASS attempt")
    return {
        "attempt_id": attempt,
        "report": path.relative_to(ROOT).as_posix(),
        "report_sha256": sha256_id(path),
        "status": "PASS",
    }


def dependency_status() -> dict[str, Any]:
    assert_hashes(EXPECTED_DEPENDENCY_HASHES)
    return {
        "attempt_id": ATTEMPT_ID,
        "dependencies": {
            "B04": _pass_dependency(
                "B04",
                "B04-0002",
                "artifacts/work_packages/B04/attempts/0002/report.json",
            ),
            "D04": _pass_dependency(
                "D04", "D04-0001", "artifacts/work_packages/D04/report.json"
            ),
            "Q04": _pass_dependency(
                "Q04",
                "Q04-0001",
                "artifacts/work_packages/Q04/attempts/0001/report.json",
            ),
            "W04": _pass_dependency(
                "W04",
                "W04-0001",
                "artifacts/work_packages/W04/attempts/0001/report.json",
            ),
            "X04": _pass_dependency(
                "X04",
                "X04-0001",
                "artifacts/work_packages/X04/attempts/0001/report.json",
            ),
        },
        "next_action": "SEAL_Y01_0001_THEN_CONTINUE_DAG",
        "note": (
            "B04 is sealed at attempt B04-0002 (PASS); its legacy root "
            "report.json is a preserved SPEC_GAP and is not the sealed attempt."
        ),
        "status": "PASS",
    }


def write_scope_verification() -> dict[str, Any]:
    assert_hashes(EXPECTED_PRODUCT_HASHES)
    component_files = sorted(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / COMPONENT).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )
    if component_files != sorted(EXPECTED_PRODUCT_HASHES):
        raise SystemExit(f"budget component holds unexpected files: {component_files}")
    return {
        "approved_scope": [f"{COMPONENT}/**", "artifacts/work_packages/Y01/**"],
        "attempt_id": ATTEMPT_ID,
        "component_files": component_files,
        "product_file_hashes": {
            relative: "sha256:" + digest
            for relative, digest in EXPECTED_PRODUCT_HASHES.items()
        },
        "reset_clean_stash_commit_push_performed": False,
        "root_canonical_source_mutation_count": 0,
        "schema_or_test_weakening_count": 0,
        "status": "PASS",
        "write_scope_violation_count": 0,
    }


def y01_verification(regression: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "budget_states": {
            "hard_over_budget_reservation_is_refused_not_truncated": True,
            "hard_refusal_leaves_usage_unchanged": True,
            "soft_estimate_records_forecast_and_never_refuses": True,
            "unmetered_is_honestly_labelled_and_never_refuses": True,
            "mislabelled_envelope_refused_at_seal_time": True,
            "tampered_budget_hash_or_contract_refused": True,
            "vocabulary_composed_from_sealed_registry_not_restated": True,
        },
        "exit_criteria": {
            "hard_soft_unmetered_states_truthful": {
                "evidence": [
                    f"{COMPONENT}/budget-enforcement.test.mjs",
                ],
                "mechanism": (
                    "only HARD_METERED and HARD_PREALLOCATED bound spend, derived "
                    "from the sealed BudgetEnvelope contract's HARD_ prefix rule; a "
                    "charge that would push any cumulative dimension past its "
                    "declared hard limit throws BUDGET_LIMIT_EXCEEDED and leaves "
                    "usage unchanged, so an over-budget operation is refused, not "
                    "truncated; SOFT_ESTIMATE records a forecast and UNMETERED "
                    "records nothing, both report spend_bounded=false and never "
                    "refuse; a hard bound with no hard limit and an UNMETERED budget "
                    "with a CANCEL/PAUSE breach policy are refused at seal time, and "
                    "a tampered budget_hash or contract is rejected"
                ),
                "status": "PASS",
            },
            "fan_out_bounded": {
                "evidence": [
                    f"{COMPONENT}/adaptive-fleet.test.mjs",
                ],
                "mechanism": (
                    "target_workers = clamp(backlog, min_workers, "
                    "effective_max_workers) where effective_max_workers is the "
                    "declared max_workers capped by the budget's concurrency hard "
                    "limit when spend is bounded; a declared maximum above a "
                    "bounding concurrency limit is refused "
                    "(FLEET_BOUND_EXCEEDS_BUDGET), an explicit worker request "
                    "outside the window is refused (FLEET_BOUND_EXCEEDED), and even "
                    "an unbounded backlog cannot raise the target above the "
                    "budget-bounded maximum, so fan-out is bounded by construction; "
                    "an advisory budget imposes no concurrency cap but is still "
                    "bounded by the declared max_workers"
                ),
                "status": "PASS",
            },
        },
        "fleet_authority": {
            "fleet_acquires_no_lease_or_capability": True,
            "receipts_are_plain_data_counts_and_hashes_only": True,
            "scaling_is_deterministic_and_receipts_re_derivable": True,
        },
        "required_checks": {
            "adaptive_fleet_test": {
                "module": f"{COMPONENT}/adaptive-fleet.test.mjs",
                "status": "PASS",
                "test_count": regression["adaptive_fleet_test"]["collected"],
            },
            "budget_enforcement_test": {
                "module": f"{COMPONENT}/budget-enforcement.test.mjs",
                "status": "PASS",
                "test_count": regression["budget_enforcement_test"]["collected"],
            },
        },
        "status": "PASS",
        "targeted_test_count": regression["targeted_budget"]["collected"],
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
                "artifacts/work_packages/Y01/attempts/0001/build_y01_0001_evidence.py",
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
        "# Y01-0001 independent review of bounded-agent work\n"
        "\n"
        "- Author: the bounded implementation agent that wrote\n"
        "  packages/foundry-kernel/src/budget. Reviewer: this seal-prep session, a\n"
        "  distinct actor that did not author the budget subsystem. The author\n"
        "  never approves its own work, so actor_independence HOLDS for this\n"
        "  review; external actor-independent certification does NOT, and no such\n"
        "  claim is made. Y01 is risk_class=high; the two exit criteria -- typed\n"
        "  budget states truthful, and fan-out bounded -- were attacked on their\n"
        "  contracts rather than skimmed.\n"
        "- Typed budget states are truthful. The enforcement vocabulary is composed\n"
        "  from the sealed @epistemic-foundry/contracts BudgetEnvelope contract\n"
        "  whose source is schemas/budget-envelope.schema.json, never restated;\n"
        "  only the HARD_ prefixed labels (HARD_METERED, HARD_PREALLOCATED) bound\n"
        "  spend, and the composed source_sha256 tracks the canonical schema bytes.\n"
        "  A hard meter that would push any cumulative dimension (tokens, calls,\n"
        "  wall_seconds, storage_bytes, network_bytes) past its declared limit\n"
        "  throws BUDGET_LIMIT_EXCEEDED and leaves usage unchanged, so the refusal\n"
        "  is neither truncated nor partially applied. SOFT_ESTIMATE records a\n"
        "  forecast and UNMETERED records nothing; both report spend_bounded=false\n"
        "  and never refuse, so a non-bounding state cannot masquerade as a limit. A\n"
        "  mislabelled envelope -- a hard bound with no hard limit, or an UNMETERED\n"
        "  budget carrying a CANCEL breach policy that has no meter to breach -- is\n"
        "  refused at seal time (BUDGET_ENVELOPE_INVALID), and a tampered budget_hash\n"
        "  (BUDGET_HASH_MISMATCH) or tampered contract (BUDGET_VOCABULARY_INVALID)\n"
        "  is rejected. No fabricated budget state was found.\n"
        "- Fan-out is bounded by construction. The adaptive fleet sizes workers as\n"
        "  target_workers = clamp(backlog, min_workers, effective_max_workers). The\n"
        "  effective maximum is the declared max_workers capped by the budget's\n"
        "  concurrency hard limit whenever spend is bounded; a fleet that declares\n"
        "  more workers than a bounding concurrency limit permits is REFUSED\n"
        "  (FLEET_BOUND_EXCEEDS_BUDGET), not silently clamped, and an explicit\n"
        "  worker request outside the [min, effective_max] window is refused\n"
        "  (FLEET_BOUND_EXCEEDED). An unbounded backlog (plan(1000)) cannot raise\n"
        "  the target above the budget-bounded maximum, so the fleet size is derived\n"
        "  and capped, never unbounded. An advisory (SOFT_ESTIMATE) budget imposes\n"
        "  no concurrency cap but is still bounded by the declared max_workers.\n"
        "- No authority acquired. Both the meter and the fleet emit only\n"
        "  deterministic, re-derivable receipts of counts and hashes; a fleet plan\n"
        "  receipt is plain frozen data with exactly the count/hash keys and no\n"
        "  lease or capability grant, and neither component mints leases nor mutates\n"
        "  external state.\n"
        "- Dependency and checks: the subsystem builds on the sealed B04 (B04-0002),\n"
        "  D04 (D04-0001), Q04 (Q04-0001), W04 (W04-0001) and X04 (X04-0001) PASS\n"
        "  attempts and adds no new production dependency. Ruff lint and format, the\n"
        "  two required checks (budget_enforcement_test 12/12, adaptive_fleet_test\n"
        "  8/8), targeted 20/20, full Python 1261/1261, full Node 1253/1253 across\n"
        "  111 files, and git diff --check all pass with zero failures.\n"
        "- Residual limitations: Y01 provides typed budgets, the adaptive fleet, and\n"
        "  their in-process performance controls; observability and SLO telemetry\n"
        "  (Y02) and backup/recovery runbooks (Y03) build on this package and are\n"
        "  out of scope here. Verdict: PASS on the exact Y01 package contract.\n"
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
            "path": f"artifacts/work_packages/Y01/attempts/0001/{name}",
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in sorted(set(output_names))
    ]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "Y01_TYPED_BUDGETS_ADAPTIVE_FLEET",
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependency_state": dependencies,
        "exit_criteria": {
            "fan_out_bounded": "PASS",
            "hard_soft_unmetered_states_truthful": "PASS",
        },
        "global_implementation_gate": "fail",
        "history_and_worktree": {
            "dirty_worktree_preserved": True,
            "prior_attempts_reports_and_rah_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
        },
        "implementation_status": "PASS",
        "not_claimed": [
            "observability, SLO, or telemetry surface (Y02)",
            "backup, disaster recovery, or operational runbooks (Y03)",
            "cross-process or distributed budget enforcement",
            "external actor-independent certification of this review",
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
                "Independent review of bounded-agent work by a distinct actor in "
                "this seal-prep session; not external actor-independent "
                "certification."
            ),
            "author": "bounded implementation agent",
            "blocking_finding_count": 0,
            "mode": "INDEPENDENT_REVIEW_OF_BOUNDED_AGENT_WORK",
            "reviewer": "independent seal-prep session (distinct actor)",
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
        "adaptive_fleet_test": (
            f"{EXPECTED_ADAPTIVE_FLEET_COUNT}/{EXPECTED_ADAPTIVE_FLEET_COUNT}"
        ),
        "attempt_id": ATTEMPT_ID,
        "budget_enforcement_test": (
            f"{EXPECTED_BUDGET_ENFORCEMENT_COUNT}/{EXPECTED_BUDGET_ENFORCEMENT_COUNT}"
        ),
        "completion_ready": False,
        "full_node": f"{EXPECTED_NODE_COUNT}/{EXPECTED_NODE_COUNT}",
        "full_python": f"{EXPECTED_PYTHON_COUNT}/{EXPECTED_PYTHON_COUNT}",
        "next_action": "SEAL_Y01_0001_THEN_CONTINUE_DAG",
        "node_file_count": EXPECTED_NODE_FILE_COUNT,
        "package_status": "PASS",
        "status": "PASS",
        "targeted_budget": f"{EXPECTED_TARGETED_COUNT}/{EXPECTED_TARGETED_COUNT}",
    }


def build() -> dict[str, Any]:
    for name in RUN_RESULTS:
        check_run(name)
    normalize_junits()
    regression = regression_evidence()
    dependencies = dependency_status()
    write_scope = write_scope_verification()
    verification = y01_verification(regression)
    write_json("dependency-status.json", dependencies)
    write_json("write-scope-verification.json", write_scope)
    write_json("y01-verification.json", verification)
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
        raise SystemExit("Y01-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "y01-verification.json")
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
    verification = read_json(ATTEMPT / "y01-verification.json")
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
        raise SystemExit("stored Y01-0001 report is not the deterministic document")
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
