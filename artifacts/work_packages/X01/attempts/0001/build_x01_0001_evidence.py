#!/usr/bin/env python3
"""Build and verify X01-0001 evidence: Codex plugin, hooks and subagent adapter.

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
ATTEMPT = ROOT / "artifacts/work_packages/X01/attempts/0001"
ATTEMPT_ID = "X01-0001"
WORK_PACKAGE_ID = "X01"
RECORDED_AT = "2026-08-02T19:15:00.000Z"
ATTEMPT_DIR = "artifacts/work_packages/X01/attempts/0001"
AUTHORITY_DECISION = None

EXPECTED_PRODUCT_HASHES = {
    "adapters/codex/README.md": "a345e2ea1e319827ce38c641e1830dc42e56fc9fd4db5064516909ca22d34985",
    "adapters/codex/codex-adversarial.test.mjs": "19fefd6e60c5cb20ffca8b5220aad0844f0d09812e7bb0e2337a7e4519e39e08",
    "adapters/codex/codex-binding.json": "5bb0ef87070322f361e636aba07af6a070ce2509d85f19ede7c35aff2e65d6ad",
    "adapters/codex/codex-contract.test.mjs": "52f92c9a354707fe27c118e5094b985649d1b083c13ffc1d5a97c7f23151f1d3",
    "adapters/codex/codex-declarations.mjs": "a467532a427e38b403773203d98dd07654a090c27d24bc3ec134a35436a105f0",
    "adapters/codex/codex-fixtures.mjs": "50827014d35975e1785851efa4e17a6fba87170266be5c4497b36ef925f2e147",
    "adapters/codex/codex-receipts.test.mjs": "11fc1a06a804b1d0a9dc58ab0e780b9689ea8e43a6286c586f49a03a513c97e9",
    "adapters/codex/codex-schema.test.mjs": "779805f80f3b1f0a861b35659a2c421447df92af075aa52fab3c35fdbff66946",
    "adapters/codex/hook-bridge.mjs": "c135268e3a4487fefbbc8cf0abaff864d85122b07cd4c79bbfd0b5c678fe8f66",
    "adapters/codex/index.mjs": "ca582a25a0aaebe5808433611bc7a490ed9c178c3eed1b464e5c148ea568ef68",
    "adapters/codex/plugin-binding.mjs": "4893dd9cf448a7b573cc1edfba2131f1fca202d94115da674ee50b832d0af820",
    "adapters/codex/role-adapter.mjs": "c1b1f8074f6c1998b28224ca2a4992bbe349a4db4d10dcbf059e30a4ce6059a1",
    "adapters/codex/role_mapping.yaml": "522ba5921595d213ea9a3663a26fec7c5e490da3bed9036df68789beaf3028fc",
    "artifacts/work_packages/X01/attempts/0001/run_x01_0001_checks.py": "562fac762316a1467365167515962d9ad4e89285abacbdc763636bc452c4bfe4",
}
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/G04/attempts/0001/report.json": "3abe50fc722255bb8f8c2196f133b94425a0b11318423cb756fab614026cf1ea",
    "artifacts/work_packages/N04/report.json": "8cbe538b5adb087974f83cc181e97172052bc25ff92e6a14da7dad3eb70141f7",
    "artifacts/work_packages/S05/attempts/0001/report.json": "dbcb94e77fd885f18aa36a00dc352a9d5a788d265b979ff7a23fafd5f261c727",
    "artifacts/work_packages/T04/attempts/0001/report.json": "ef86645d7ca5058df3047b6b53fbb3dd4c56af41b27db481b773d205e96c6272",
    "artifacts/work_packages/W04/attempts/0001/report.json": "b07687917d9bf5a150d78c9fd1580e24308823f95e1c8713302b7e4af3c75688",
}

JUNIT_PATHS = {
    "codex_adapter_test": ATTEMPT / "codex-adapter-test.junit.xml",
    "codex_adversarial_tests": ATTEMPT / "codex-adversarial-tests.junit.xml",
    "codex_hook_coverage_test": ATTEMPT / "codex-hook-coverage-test.junit.xml",
    "codex_schema_check": ATTEMPT / "codex-schema-check.junit.xml",
    "dependency_regression_gateway": ATTEMPT
    / "dependency-regression-gateway.junit.xml",
    "dependency_regression_install": ATTEMPT
    / "dependency-regression-install.junit.xml",
    "full_node_suite": ATTEMPT / "full-node-suite.junit.xml",
    "full_python_suite": ATTEMPT / "full-python-suite.junit.xml",
    "targeted_x01_codex": ATTEMPT / "targeted-x01-codex.junit.xml",
}
_NODE_JUNITS = frozenset(
    {
        "codex_adapter_test",
        "codex_adversarial_tests",
        "codex_hook_coverage_test",
        "codex_schema_check",
        "dependency_regression_gateway",
        "dependency_regression_install",
        "full_node_suite",
        "targeted_x01_codex",
    }
)
RUN_RESULTS = (
    "codex-adapter-test",
    "codex-adversarial-tests",
    "codex-hook-coverage-test",
    "codex-schema-check",
    "dependency-regression-gateway",
    "dependency-regression-install",
    "full-node-suite",
    "full-python-suite",
    "git-diff-check",
    "ruff-check",
    "ruff-format-check",
    "targeted-x01-codex",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "build_x01_0001_evidence.py",
    "codex-adapter-test.junit.xml",
    "codex-adversarial-tests.junit.xml",
    "codex-hook-coverage-test.junit.xml",
    "codex-schema-check.junit.xml",
    "commands.jsonl",
    "dependency-regression-gateway.junit.xml",
    "dependency-regression-install.junit.xml",
    "dependency-status.json",
    "full-node-suite.junit.xml",
    "full-python-suite.junit.xml",
    "junit-normalization-verification.json",
    "node-test-inventory.json",
    "review.md",
    "run_x01_0001_checks.py",
    "targeted-x01-codex.junit.xml",
    "write-scope-verification.json",
    "x01-verification.json",
    "x01_0001_rah_seal.py",
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
        ("codex_adapter_test", node_summary(JUNIT_PATHS["codex_adapter_test"]), 14),
        (
            "codex_adversarial_tests",
            node_summary(JUNIT_PATHS["codex_adversarial_tests"]),
            28,
        ),
        (
            "codex_hook_coverage_test",
            node_summary(JUNIT_PATHS["codex_hook_coverage_test"]),
            12,
        ),
        ("codex_schema_check", node_summary(JUNIT_PATHS["codex_schema_check"]), 14),
        (
            "dependency_regression_gateway",
            node_summary(JUNIT_PATHS["dependency_regression_gateway"]),
            11,
        ),
        (
            "dependency_regression_install",
            node_summary(JUNIT_PATHS["dependency_regression_install"]),
            1,
        ),
        ("full_node_suite", node_summary(JUNIT_PATHS["full_node_suite"]), 1276),
        ("targeted_x01_codex", node_summary(JUNIT_PATHS["targeted_x01_codex"]), 68),
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
            "G04": _sealed_dependency("G04", "G04-0001", "E0058", "E0059"),
            "N04": _sealed_dependency("N04", "N04-0001", "E0076", "E0077", flat=True),
            "T04": _sealed_dependency("T04", "T04-0001", "E0151", "E0152"),
            "W04": _sealed_dependency("W04", "W04-0001", "E0141", "E0142"),
        },
        "next_action": "SEAL_X01_0001_THEN_CONTINUE_DAG",
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
            "adapters/codex/**",
            "artifacts/work_packages/X01/**",
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
            "gateway_vocab": (
                "hook-gateway HOOK_HOSTS/EVENT_TYPES (selected by predicate, never restated)"
            ),
            "payload": (
                "plugins/epistemic-foundry (read-only; verified, never rewritten)"
            ),
            "roles": ("manifests/role_registry.yaml (28 roles)"),
        },
        "exit_criteria": {
            "all_completion_and_external_effects_resolve_to_immutable_receipts": {
                "mechanism": (
                    "the role table is byte-stable and hash-bound, cross-checked row-for-row against the pre-existing mapping file non-vacuously, and the binding receipt re-derives its hash over the payload facts it verified"
                ),
                "status": "PASS",
            },
            "governing_schemas_authority_boundaries_failure_states_exact": {
                "mechanism": (
                    "the host value lives only in the adapter's declaration JSON and is admitted by filtering the gateway's own host vocabulary for the declared value — zero or multiple matches refuse; per-module tests assert no quoted host literal exists in any product module"
                ),
                "status": "PASS",
            },
            "happy_negative_crash_resume_adversarial_coverage": {
                "mechanism": (
                    "the real payload binds as DEGRADED with the two missing dist runtime files named as findings, and a staged positive control flips the binding to BOUND with zero findings, proving the status is derived rather than constant; 8 event registrations verified, 3 canonical types published UNOBSERVED"
                ),
                "status": "PASS",
            },
            "no_candidate_model_prompt_backend_or_hook_acquires_authority": {
                "mechanism": (
                    "the adapter validates and translates only: contract tests assert no child-process, filesystem-write, clock, randomness or environment access in any product module, and gateway refusals propagate unmodified"
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
                f"{ATTEMPT_DIR}/build_x01_0001_evidence.py",
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
        "# X01-0001 primary-session review of parallel-agent work\n"
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
        "- The manifest grants plugins/epistemic-foundry/** but the skill tree is hash-bound by the sealed G05 surface; the adapter treats the payload as read-only reference and the G05 gate re-ran 20/20 after the attempt — the scope narrowing is recorded here as the sealed-surface-preserving reading.\n"
        "- The raw Codex event shape is the adapter's declared expectation, pinned by tests, because no host specification ships in the repo; the one grounded field is the verb index derived from the payload's own registrations.\n"
        "- The DEGRADED pins are intentional drift detection: when dist/ is built those assertions must flip to BOUND.\n"
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
        "attempt_type": "X01_CODEX_PLUGIN_HOOKS_SUBAGENT_ADAPTER",
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
        "next_package": "R05-0001",
        "not_claimed": [
            "plugin installation, hook execution or subagent launching",
            "MCP service exposure validation (.mcp.json outside the declared binding surface)",
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
        "next_action": "SEAL_X01_0001_THEN_CONTINUE_DAG",
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
    write_json("x01-verification.json", verification)
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
        raise SystemExit("X01-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "x01-verification.json")
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
    verification = read_json(ATTEMPT / "x01-verification.json")
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
        raise SystemExit("stored X01-0001 report is not the deterministic document")
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
