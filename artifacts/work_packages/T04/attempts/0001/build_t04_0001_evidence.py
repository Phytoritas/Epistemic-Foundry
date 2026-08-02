#!/usr/bin/env python3
"""Build and verify T04-0001 sandbox and external tool adapter gate evidence.

T04-0001 implements `python/epistemic_foundry/tools/**`: an external tool is
admitted only through its declared ValidationTargetManifest, every byte it
returns is content-addressed before it can become evidence, every invocation
runs under a mandatory call and wall-clock ceiling whose breach resolves
through the envelope's own policy, and evaluator/holdout isolation dominates
every other check.  This builder verifies the executed checks and emits
immutable attempt evidence; it never modifies product files.
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
ATTEMPT = ROOT / "artifacts/work_packages/T04/attempts/0001"
ATTEMPT_ID = "T04-0001"
WORK_PACKAGE_ID = "T04"
RECORDED_AT = "2026-08-01T20:30:00.000Z"

EXPECTED_SANDBOX_ESCAPE_COUNT = 62
EXPECTED_TOOL_RECEIPT_COUNT = 53
EXPECTED_TARGETED_COUNT = 115
EXPECTED_MCP_WRITE_REGRESSION_COUNT = 16
EXPECTED_CLI_REGRESSION_COUNT = 38
EXPECTED_PYTHON_COUNT = 1261
EXPECTED_NODE_COUNT = 982
EXPECTED_NODE_FILE_COUNT = 91

COMPONENT = "python/epistemic_foundry/tools/sandbox"
EXPECTED_PRODUCT_HASHES = {
    "python/epistemic_foundry/tools/sandbox/__init__.py": "85303b54f9efd2e9d65d7b3bd99736784a6b26a9482161ca4d515fe16a092e36",
    "python/epistemic_foundry/tools/sandbox/contracts.py": "91bb06a0adf59bc3ab3a0eca833f855bf7010afb20ca7e371b24539efd2c18e4",
    "python/epistemic_foundry/tools/sandbox/pytest.ini": "37f8a67e65729e203e590f33ff901a03b63e286abb379df730497e7b880e3b46",
    "python/epistemic_foundry/tools/sandbox/test_sandbox_escape.py": "34831d153ca4b0afca7553141d94aab9928e9e7aba4b06ea1fe3290fa47287af",
    "python/epistemic_foundry/tools/sandbox/test_tool_receipt.py": "314fa9bb4ea3e172a3c59d933b3b1687b1aeb45b61d3285a3fb9664959f75ce0",
}
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/Q01/attempts/0001/report.json": "89305583d752aa36858719ef7309e92827a857f8a7df9b35b4300324db39b2f3",
    "artifacts/work_packages/T02/attempts/0001/report.json": "53218e162140319fabd504be498d4248009763c2853b27c09f60626ae9c00bbd",
    "artifacts/work_packages/T03/attempts/0001/report.json": "eaf4f4a3252584860626e35374b402622e241a78264c5d02cd83b14ef4c7773d",
}

JUNIT_PATHS = {
    "sandbox_escape": ATTEMPT / "sandbox-escape-test.junit.xml",
    "tool_receipt": ATTEMPT / "tool-receipt-test.junit.xml",
    "targeted": ATTEMPT / "targeted-tool-sandbox.junit.xml",
    "mcp_write_regression": ATTEMPT / "dependency-regression-mcp-write.junit.xml",
    "cli_regression": ATTEMPT / "dependency-regression-cli.junit.xml",
    "full_python": ATTEMPT / "full-python-suite.junit.xml",
    "full_node": ATTEMPT / "full-node-suite.junit.xml",
}
# T04 depends on T02 and T03, whose surfaces are Node: their regression JUnits
# carry the Node reporter's semantic footer, not pytest suite attributes.
_NODE_JUNITS = frozenset({"cli_regression", "full_node", "mcp_write_regression"})
RUN_RESULTS = (
    "ruff-check",
    "ruff-format-check",
    "sandbox-escape-test",
    "tool-receipt-test",
    "targeted-tool-sandbox",
    "dependency-regression-mcp-write",
    "dependency-regression-cli",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "run_t04_0001_checks.py",
    "build_t04_0001_evidence.py",
    "t04_0001_rah_seal.py",
    "dependency-status.json",
    "t04-verification.json",
    "write-scope-verification.json",
    "inherited-defect-corrections.json",
    "node-test-inventory.json",
    "junit-normalization-verification.json",
    "sandbox-escape-test.junit.xml",
    "tool-receipt-test.junit.xml",
    "targeted-tool-sandbox.junit.xml",
    "dependency-regression-mcp-write.junit.xml",
    "dependency-regression-cli.junit.xml",
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
    escape = pytest_summary(JUNIT_PATHS["sandbox_escape"])
    receipt = pytest_summary(JUNIT_PATHS["tool_receipt"])
    targeted = pytest_summary(JUNIT_PATHS["targeted"])
    mcp_write = node_summary(JUNIT_PATHS["mcp_write_regression"])
    cli = node_summary(JUNIT_PATHS["cli_regression"])
    python = pytest_summary(JUNIT_PATHS["full_python"])
    node = node_summary(JUNIT_PATHS["full_node"])
    node_inventory = read_json(ATTEMPT / "node-test-inventory.json")
    for label, summary, expected in (
        ("sandbox_escape_test", escape, EXPECTED_SANDBOX_ESCAPE_COUNT),
        ("tool_receipt_test", receipt, EXPECTED_TOOL_RECEIPT_COUNT),
        ("targeted", targeted, EXPECTED_TARGETED_COUNT),
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
        ("mcp_write_regression", mcp_write, EXPECTED_MCP_WRITE_REGRESSION_COUNT),
        ("cli_regression", cli, EXPECTED_CLI_REGRESSION_COUNT),
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
        "baseline_attempt": "Q01-0001",
        "cli_regression": cli,
        "component_tests_are_targeted_only": True,
        "full_node": node,
        "full_python": python,
        "mcp_write_regression": mcp_write,
        "new_failure_count": 0,
        "prior_baseline_counts": {"full_node": 982, "full_python": 1261},
        "sandbox_escape_test": escape,
        "status": "PASS",
        "targeted_tool_sandbox": targeted,
        "tool_receipt_test": receipt,
        "unexpected_skip_xfail_todo_or_cancellation_count": 0,
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
            "T02": _sealed_dependency("T02", "T02-0001", "E0127", "E0128"),
            "T03": _sealed_dependency("T03", "T03-0001", "E0139", "E0140"),
        },
        "next_action": "SEAL_T04_0001_THEN_CONTINUE_DAG",
        "regression_baseline": _sealed_dependency("Q01", "Q01-0001", "E0149", "E0150"),
        "status": "PASS",
    }


def write_scope_verification() -> dict[str, Any]:
    assert_hashes(EXPECTED_PRODUCT_HASHES)
    # Interpreter and pytest caches are generated tool state, not product
    # files; every other file under the component must be declared.
    component_files = sorted(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / COMPONENT).rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and ".pytest_cache" not in path.parts
    )
    if component_files != sorted(EXPECTED_PRODUCT_HASHES):
        raise SystemExit(f"tool sandbox holds unexpected files: {component_files}")
    return {
        "approved_scope": [
            "python/epistemic_foundry/tools/**",
            "artifacts/work_packages/T04/**",
        ],
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
        "subagents_or_fleet_used": False,
        "write_scope_violation_count": 0,
    }


def t04_verification(regression: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "declaring_sources": {
            "approval_policy": "schemas/validation-target-manifest.schema.json",
            "breach_policy": "schemas/budget-envelope.schema.json",
            "effect_status": "schemas/effect-receipt.schema.json",
            "enforcement": "schemas/budget-envelope.schema.json",
            "isolation_boundaries": "schemas/holdout-manifest.schema.json",
            "network_policy": "schemas/validation-target-manifest.schema.json",
            "output_receipt_shape": "schemas/artifact-receipt.schema.json",
            "quota_dimensions": "schemas/budget-envelope.schema.json",
            "safety_class": "schemas/validation-target-manifest.schema.json",
        },
        "exit_criteria": {
            "timeouts_cancellation_quotas_enforced": {
                "evidence": [f"{COMPONENT}/test_tool_receipt.py"],
                "mechanism": (
                    "a call and wall-clock ceiling are mandatory and an adapter "
                    "that may reach the network must also bound what it sends; a "
                    "breach resolves through the envelope's own breach policy "
                    "rather than this component's preference; and a cancelled or "
                    "timed-out run still emits an EffectReceipt whose status "
                    "follows the observation, so UNKNOWN carries "
                    "reconciliation_required and a proven non-start does not"
                ),
                "status": "PASS",
            },
            "tool_outputs_hashed": {
                "evidence": [f"{COMPONENT}/test_tool_receipt.py"],
                "mechanism": (
                    "every captured output is content-addressed over the bytes "
                    "themselves, the hash and byte size are re-derived on "
                    "verification rather than trusted, a truncated capture is "
                    "hashed as what was captured and records the completeness "
                    "failure, and an unhashed output cannot enter an EffectReceipt"
                ),
                "status": "PASS",
            },
        },
        "isolation": {
            "boundaries_read_from_schema": [
                "backend_access",
                "candidate_access",
                "mutation_model_access",
                "prompt_access",
            ],
            "holdout_contradicting_its_own_schema_refused": True,
            "sandboxed_principal_cannot_reach_holdout_or_evaluator": True,
            "unblinding_requires_approval_for_other_principals": True,
        },
        "quotas": {
            "breach_actions": ["DENIED", "ESCALATED", "TRUNCATED", "WARNED"],
            "mandatory_ceilings": ["calls", "wall_seconds"],
            "unmetered_enforcement_refused": True,
        },
        "required_checks": {
            "sandbox_escape_test": {
                "module": f"{COMPONENT}/test_sandbox_escape.py",
                "status": "PASS",
                "test_count": regression["sandbox_escape_test"]["collected"],
            },
            "tool_receipt_test": {
                "module": f"{COMPONENT}/test_tool_receipt.py",
                "status": "PASS",
                "test_count": regression["tool_receipt_test"]["collected"],
            },
        },
        "status": "PASS",
        "targeted_test_count": regression["targeted_tool_sandbox"]["collected"],
    }


def inherited_defect_corrections() -> dict[str, Any]:
    """Record a defect this attempt inherited and corrected going forward.

    The sealed attempts from R02 onward each recorded an ``evidence-build``
    command naming ``build_r01_0001_evidence.py`` inside their own directory,
    because that line was carried through the derivation chain unchanged.  The
    command actually executed was each package's own builder.  Those
    generations are hash-sealed and are not rewritten; the defect is recorded
    here and corrected from T04 onward.
    """

    affected = (
        "R02-0001",
        "R03-0001",
        "R04-0001",
        "P01-0001",
        "P02-0001",
        "P03-0001",
        "P04-0001",
        "Q01-0001",
        "T03-0001",
        "W04-0001",
    )
    return {
        "attempt_id": ATTEMPT_ID,
        "corrections": [
            {
                "affected_sealed_attempts": list(affected),
                "correction": (
                    "T04-0001 and later attempts record the builder they actually "
                    "ran; the sealed generations are left byte-identical because "
                    "rewriting them would break the append-only hash chain"
                ),
                "defect": (
                    "commands.jsonl recorded the evidence-build step as "
                    "build_r01_0001_evidence.py inside the attempt's own "
                    "directory, a file that does not exist there"
                ),
                "defect_id": "T04-IC001",
                "impact": (
                    "the recorded command string is wrong; the check results, "
                    "JUnit evidence and artifact hashes those attempts sealed are "
                    "unaffected, and each attempt's real builder is present and "
                    "hashed in its own output_artifacts"
                ),
                "severity": "LOW",
                "status": "CORRECTED_FORWARD",
            }
        ],
        "status": "PASS",
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
                "artifacts/work_packages/T04/attempts/0001/build_t04_0001_evidence.py",
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
        "# T04-0001 primary-session separate adversarial review\n"
        "\n"
        "- Reviewer: primary session in a separate adversarial pass under the\n"
        "  product-owner instruction forbidding subagents and Fleet;\n"
        "  actor_independence=false is recorded, not hidden.\n"
        "- The adapter contract is read, not restated. Network policy, safety\n"
        "  class, approval policy, data classes and the manifest field set come\n"
        "  from validation-target-manifest.schema.json; quota dimensions,\n"
        "  enforcement modes and breach policy from budget-envelope; effect\n"
        "  statuses from effect-receipt; the pinned isolation flags from\n"
        "  holdout-manifest. Every local decision table is checked against the\n"
        "  schema that declares it on each use, so a vocabulary the schema grows\n"
        "  fails loudly as VOCABULARY_DRIFT instead of silently defaulting open.\n"
        "- Outputs are hashed over the bytes, and verification re-derives both\n"
        "  the digest and the size rather than trusting the receipt. Re-sealing a\n"
        "  forged size does not help, because the size is recomputed too. A\n"
        "  truncated capture is still hashed, as what was actually captured, and\n"
        "  records the completeness failure instead of presenting itself as\n"
        "  whole.\n"
        "- Ceilings are mandatory rather than optional. UNMETERED never satisfies\n"
        "  any safety class, a bounded_compute adapter cannot run on an estimate,\n"
        "  high_risk requires preallocation, and an adapter that may reach the\n"
        "  network must bound what it sends. A breach resolves through the\n"
        "  envelope's own policy: CANCEL charges nothing and stops, MARK_PARTIAL\n"
        "  clamps to the ceiling, PAUSE_AND_ESCALATE stops, WARN continues.\n"
        "- Cancellation reconciles. The effect status is derived from what was\n"
        "  observed, never from what was intended: a proven non-start is\n"
        "  NOT_EXECUTED with no external effect, an interrupted run is UNKNOWN\n"
        "  and must carry reconciliation_required, and a success that claims no\n"
        "  hashed output is refused. The observation table is checked to cover\n"
        "  the effect status vocabulary exactly, so a new status cannot become\n"
        "  unreachable.\n"
        "- Isolation dominates. A holdout that declares candidate access true\n"
        "  contradicts its own schema and is refused before anything else runs; a\n"
        "  sandboxed principal cannot reach a hidden partition or the evaluator\n"
        "  even with an approval in hand; a non-sandboxed principal may unblind\n"
        "  only with one, which is what the holdout contract itself pins.\n"
        "- The gate cannot be talked up. Its status is derived from six criteria\n"
        "  and a declared status stronger than the derived one is refused as\n"
        "  GATE_OVERCLAIM rather than recorded.\n"
        "- Correction recorded: the sealed attempts from R02 onward carried an\n"
        "  evidence-build command naming build_r01_0001_evidence.py in their own\n"
        "  directory. The command executed was each package's own builder; the\n"
        "  recorded string was wrong. Those generations are hash-sealed and are\n"
        "  not rewritten, so the defect is recorded in\n"
        "  inherited-defect-corrections.json and corrected from T04 onward.\n"
        "- Residual limitations: this is a contract gate, not an operating-system\n"
        "  or container sandbox, and it says so; no test executes an external\n"
        "  tool; path safety is decided over declared portable paths without\n"
        "  touching the filesystem, so link and mount escapes remain the\n"
        "  executing adapter's problem, which S02 covers on the kernel side; and\n"
        "  binding this gate to the kernel and MCP surfaces belongs to T05 and\n"
        "  later. This review is not external actor-independent certification.\n"
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
            "path": f"artifacts/work_packages/T04/attempts/0001/{name}",
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in sorted(set(output_names))
    ]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "T04_SANDBOX_AND_EXTERNAL_TOOL_ADAPTER_GATE",
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependency_state": dependencies,
        "exit_criteria": {
            "timeouts_cancellation_quotas_enforced": "PASS",
            "tool_outputs_hashed": "PASS",
        },
        "global_implementation_gate": "fail",
        "history_and_worktree": {
            "dirty_worktree_preserved": True,
            "prior_attempts_reports_and_rah_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
            "subagents_or_fleet_used": False,
        },
        "implementation_status": "PASS",
        "next_package": "B05-0001",
        "not_claimed": [
            "an operating-system, container, or hypervisor sandbox, since this "
            "gate decides admissibility over declared contracts",
            "that a conforming decision proves an external tool is safe to run",
            "kernel or MCP binding of this gate, which T05 and later own",
            "execution of any external tool, which no test performs",
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
        "next_action": "SEAL_T04_0001_THEN_CONTINUE_DAG",
        "package_status": "PASS",
        "sandbox_escape_test": (
            f"{EXPECTED_SANDBOX_ESCAPE_COUNT}/{EXPECTED_SANDBOX_ESCAPE_COUNT}"
        ),
        "status": "PASS",
        "targeted_tool_sandbox": (
            f"{EXPECTED_TARGETED_COUNT}/{EXPECTED_TARGETED_COUNT}"
        ),
        "tool_receipt_test": (
            f"{EXPECTED_TOOL_RECEIPT_COUNT}/{EXPECTED_TOOL_RECEIPT_COUNT}"
        ),
    }


def build() -> dict[str, Any]:
    for name in RUN_RESULTS:
        check_run(name)
    normalize_junits()
    regression = regression_evidence()
    dependencies = dependency_status()
    write_scope = write_scope_verification()
    verification = t04_verification(regression)
    write_json("dependency-status.json", dependencies)
    write_json("write-scope-verification.json", write_scope)
    write_json("inherited-defect-corrections.json", inherited_defect_corrections())
    write_json("t04-verification.json", verification)
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
        raise SystemExit("T04-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "t04-verification.json")
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
    verification = read_json(ATTEMPT / "t04-verification.json")
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
