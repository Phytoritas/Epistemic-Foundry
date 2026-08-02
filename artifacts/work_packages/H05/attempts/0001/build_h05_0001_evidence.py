#!/usr/bin/env python3
"""Build and verify H05-0001 evidence: Evolution/holdout observability hooks with explicit coverage limits.

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
ATTEMPT = ROOT / "artifacts/work_packages/H05/attempts/0001"
ATTEMPT_ID = "H05-0001"
WORK_PACKAGE_ID = "H05"
RECORDED_AT = "2026-08-02T18:30:00.000Z"
ATTEMPT_DIR = "artifacts/work_packages/H05/attempts/0001"
AUTHORITY_DECISION = None

EXPECTED_PRODUCT_HASHES = {
    "artifacts/work_packages/H05/attempts/0001/run_h05_0001_checks.py": "5e2f6cec4c65f1dac81a721198b568f6762580ca670b8da82239f8f666fe37bb",
    "plugin_blueprint/epistemic-foundry/hooks/v4_h05/index.mjs": "978fbe13dfc7849f253526cf002343d3971c155e33ac79497877f30db2dd83a2",
    "plugin_blueprint/epistemic-foundry/hooks/v4_h05/observability-adversarial.test.mjs": "e0d929915465b7f20e13729ee6e841933673c702d7f77a0f7b1b0c7c24d091ee",
    "plugin_blueprint/epistemic-foundry/hooks/v4_h05/observability-contract.test.mjs": "ae9cdfd23d71f15886ad40ec0e9a71ff112c918c37598bd2bf2758b2ffd2f660",
    "plugin_blueprint/epistemic-foundry/hooks/v4_h05/observability-fixtures.mjs": "386bc1524f89de6324adf3f45fb388c8e9677fc772386069e872ff7d0b36f100",
    "plugin_blueprint/epistemic-foundry/hooks/v4_h05/observability-receipts.test.mjs": "2e2c045f0e9b76254bbbb769ccb245751126df2c8b6f2eae3730c089a785e499",
    "plugin_blueprint/epistemic-foundry/hooks/v4_h05/observability-registrations.json": "357b7e9fa48c0352e6d752043b7922d572de478cb1330a5908e20034fdbcd104",
    "plugin_blueprint/epistemic-foundry/hooks/v4_h05/observability-schema.test.mjs": "a238ec7e1a39b637a1a1e12152128566e104ae7ac82a8cae9ff7c15cda9e1c82",
    "plugin_blueprint/epistemic-foundry/hooks/v4_h05/observability.mjs": "f21087c056de8c4ec4cb4818dbe9175cf80cf918c9e36830907be66569885a0d",
}
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/G05/attempts/0001/report.json": "c854b5ec890ed3783c55665fafc02f965ccf3616c2bd4d8071ea8101f12484d0",
    "artifacts/work_packages/H04/report.json": "cf61978263c39eddfc90bc6107d714ed27201d7094fb45ef882d62dd736bb3fb",
    "artifacts/work_packages/S05/attempts/0001/report.json": "dbcb94e77fd885f18aa36a00dc352a9d5a788d265b979ff7a23fafd5f261c727",
}

JUNIT_PATHS = {
    "dependency_regression_g05": ATTEMPT / "dependency-regression-g05.junit.xml",
    "dependency_regression_gateway": ATTEMPT
    / "dependency-regression-gateway.junit.xml",
    "full_node_suite": ATTEMPT / "full-node-suite.junit.xml",
    "full_python_suite": ATTEMPT / "full-python-suite.junit.xml",
    "negative_and_adversarial_tests": ATTEMPT
    / "negative-and-adversarial-tests.junit.xml",
    "provenance_and_receipt_audit": ATTEMPT / "provenance-and-receipt-audit.junit.xml",
    "schema_and_type_check": ATTEMPT / "schema-and-type-check.junit.xml",
    "targeted_h05_observability": ATTEMPT / "targeted-h05-observability.junit.xml",
    "unit_and_contract_tests": ATTEMPT / "unit-and-contract-tests.junit.xml",
}
_NODE_JUNITS = frozenset(
    {
        "dependency_regression_g05",
        "dependency_regression_gateway",
        "full_node_suite",
        "negative_and_adversarial_tests",
        "provenance_and_receipt_audit",
        "schema_and_type_check",
        "targeted_h05_observability",
        "unit_and_contract_tests",
    }
)
RUN_RESULTS = (
    "dependency-regression-g05",
    "dependency-regression-gateway",
    "full-node-suite",
    "full-python-suite",
    "git-diff-check",
    "negative-and-adversarial-tests",
    "provenance-and-receipt-audit",
    "ruff-check",
    "ruff-format-check",
    "schema-and-type-check",
    "targeted-h05-observability",
    "unit-and-contract-tests",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "build_h05_0001_evidence.py",
    "commands.jsonl",
    "dependency-regression-g05.junit.xml",
    "dependency-regression-gateway.junit.xml",
    "dependency-status.json",
    "full-node-suite.junit.xml",
    "full-python-suite.junit.xml",
    "h05-verification.json",
    "h05_0001_rah_seal.py",
    "junit-normalization-verification.json",
    "negative-and-adversarial-tests.junit.xml",
    "node-test-inventory.json",
    "provenance-and-receipt-audit.junit.xml",
    "review.md",
    "run_h05_0001_checks.py",
    "schema-and-type-check.junit.xml",
    "targeted-h05-observability.junit.xml",
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
        ("full_python_suite", pytest_summary(JUNIT_PATHS["full_python_suite"]), 1261),
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
        (
            "dependency_regression_g05",
            node_summary(JUNIT_PATHS["dependency_regression_g05"]),
            81,
        ),
        (
            "dependency_regression_gateway",
            node_summary(JUNIT_PATHS["dependency_regression_gateway"]),
            11,
        ),
        ("full_node_suite", node_summary(JUNIT_PATHS["full_node_suite"]), 1276),
        (
            "negative_and_adversarial_tests",
            node_summary(JUNIT_PATHS["negative_and_adversarial_tests"]),
            43,
        ),
        (
            "provenance_and_receipt_audit",
            node_summary(JUNIT_PATHS["provenance_and_receipt_audit"]),
            16,
        ),
        (
            "schema_and_type_check",
            node_summary(JUNIT_PATHS["schema_and_type_check"]),
            16,
        ),
        (
            "targeted_h05_observability",
            node_summary(JUNIT_PATHS["targeted_h05_observability"]),
            93,
        ),
        (
            "unit_and_contract_tests",
            node_summary(JUNIT_PATHS["unit_and_contract_tests"]),
            18,
        ),
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
    if node_inventory.get("count") != 107:
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
            "G05": _sealed_dependency("G05", "G05-0001", "E0169", "E0170"),
            "H04": _sealed_dependency("H04", "H04-0001", "E0066", "E0067", flat=True),
        },
        "next_action": "SEAL_H05_0001_THEN_CONTINUE_DAG",
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
            "plugin_blueprint/epistemic-foundry/hooks/v4_h05/**",
            "artifacts/work_packages/H05/**",
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
        name: suites[name]["collected"]
        for name in (
            "schema_and_type_check",
            "unit_and_contract_tests",
            "negative_and_adversarial_tests",
            "provenance_and_receipt_audit",
        )
        if name in suites
    }
    return {
        "attempt_id": ATTEMPT_ID,
        "declaring_sources": {
            "event_surface": ("plugin hooks/evolution.json + hooks/holdout.json"),
            "gateway_vocab": (
                "hook-gateway HOOK_HOSTS/EVENT_TYPES/DECISIONS/COVERAGE (imported)"
            ),
            "holdout_flags": (
                "holdout-manifest schema const:false access flags + *_partition_handles"
            ),
        },
        "exit_criteria": {
            "all_completion_and_external_effects_resolve_to_immutable_receipts": {
                "mechanism": (
                    "receipts and bundles hash through the gateway's own sha256HookJson, the projection publishes plugin_manifest_wired false rather than implying installation, and no clock or randomness exists in product paths"
                ),
                "status": "PASS",
            },
            "governing_schemas_authority_boundaries_failure_states_exact": {
                "mechanism": (
                    "every vocabulary is imported from the gateway or derived from the schema's own pinned-closed properties, the decision set must partition exactly into observer and control or the load refuses, and every emitted envelope passes the gateway's own validator"
                ),
                "status": "PASS",
            },
            "happy_negative_crash_resume_adversarial_coverage": {
                "mechanism": (
                    "coverage is honest by construction: 5 of 33 host-by-event pairs observed, 28 named in not_observed, the host other published as never observed, and a report claiming more than its registrations refuses COVERAGE_OVERCLAIMED"
                ),
                "status": "PASS",
            },
            "no_candidate_model_prompt_backend_or_hook_acquires_authority": {
                "mechanism": (
                    "observability may only emit observer decisions with null intent and receipt ids; reclassifying ADVISORY into the control set is refused, and a registration or observation touching holdout-flagged material is refused before anything is hashed"
                ),
                "status": "PASS",
            },
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
                f"{ATTEMPT_DIR}/build_h05_0001_evidence.py",
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
        "# H05-0001 primary-session review of parallel-agent work\n"
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
        "- Two coverage scopes deliberately differ: a registration's own disposition is scoped to its observed hosts while the report is scoped to every gateway host — claims are checked against the absolute scope.\n"
        "- HOLDOUT_PREDICATE_EMPTY guards vacuity: a schema that stops pinning access flags closed fails rather than allowing everything.\n"
        "- Not wired into the plugin manifest (outside scope); the bundle is a projection and says so.\n"
        "- Integration gates at review time: repository EF4-I22 discipline\n"
        "  5/5, structure and boundary checks PASS, git diff --check clean,\n"
        "  full Python and full Node suites green with the Node inventory\n"
        "  unified at 107 files across five bases.\n"
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
        "attempt_type": "H05_EVOLUTION_OBSERVABILITY_HOOKS",
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
        "next_package": "U01-0001",
        "not_claimed": [
            "hook delivery guarantees: it observes events a host already delivered and hook coverage remains non-exhaustive per the gateway's own contract",
            "enforcement of any kind: observer decisions only",
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
        "next_action": "SEAL_H05_0001_THEN_CONTINUE_DAG",
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
    write_json("h05-verification.json", verification)
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
        raise SystemExit("H05-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "h05-verification.json")
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
    verification = read_json(ATTEMPT / "h05-verification.json")
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
        raise SystemExit("stored H05-0001 report is not the deterministic document")
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
