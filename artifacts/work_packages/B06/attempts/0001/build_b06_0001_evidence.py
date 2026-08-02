#!/usr/bin/env python3
"""Build and verify B06-0001 evidence: Reproducible build and backend-pin integration gate.

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
ATTEMPT = ROOT / "artifacts/work_packages/B06/attempts/0001"
ATTEMPT_ID = "B06-0001"
WORK_PACKAGE_ID = "B06"
RECORDED_AT = "2026-08-02T16:15:00.000Z"
ATTEMPT_DIR = "artifacts/work_packages/B06/attempts/0001"
AUTHORITY_DECISION = None

EXPECTED_PRODUCT_HASHES = {
    "artifacts/work_packages/B06/attempts/0001/b06_gate.py": "0759e8fae9edd2dcee1089785cd85a6bbf8856774dc5dfd646deb45660f0f479",
    "artifacts/work_packages/B06/attempts/0001/fixtures.py": "4967d431ec9c1474876769e377b39c369716b9c847c97d2dd151fd71df83a79d",
    "artifacts/work_packages/B06/attempts/0001/pytest.ini": "78eba6ba6b57398c0f43798f6b92a935175f42114015fbfae2dd0db4d7695ab1",
    "artifacts/work_packages/B06/attempts/0001/run_b06_0001_checks.py": "6ca6b2d9e0ee062bdae434d50d35a5378cf53878c5bd9e1ae6bed9bcf9a3a6a3",
    "artifacts/work_packages/B06/attempts/0001/test_negative_adversarial.py": "00414fc90401cb403ecbda6a1498bf37d386c30e9a06db71a966cf94eebf98cb",
    "artifacts/work_packages/B06/attempts/0001/test_provenance_receipts.py": "a4be02fbeb6aca0da17d7d62b18cff6065696d1cbafb8ba53a9eda5906d8a2b7",
    "artifacts/work_packages/B06/attempts/0001/test_schema_and_type.py": "55bc7f9d199ae5bcb2aa2865ad4af0738d2b62e2f178dad1b4867f7e73b9d4f8",
    "artifacts/work_packages/B06/attempts/0001/test_unit_contract.py": "bc5a9a684e5c8031c24b8f18dfe23d105ce13a9bb2b7664105881cd3482d09bc",
}
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/B05/attempts/0001/report.json": "b296d29a541cd94f6f8acbba08adc07f9c413a2521a6e0ab3a7178a6273fc731",
    "artifacts/work_packages/C05/attempts/0001/report.json": "35ea908093214930bbf10d8d181e539b54940febb5a36983c60b6274a545111d",
    "artifacts/work_packages/S05/attempts/0001/report.json": "dbcb94e77fd885f18aa36a00dc352a9d5a788d265b979ff7a23fafd5f261c727",
}

JUNIT_PATHS = {
    "dependency_regression_b05": ATTEMPT / "dependency-regression-b05.junit.xml",
    "full_node_suite": ATTEMPT / "full-node-suite.junit.xml",
    "full_python_suite": ATTEMPT / "full-python-suite.junit.xml",
    "negative_and_adversarial_tests": ATTEMPT
    / "negative-and-adversarial-tests.junit.xml",
    "provenance_and_receipt_audit": ATTEMPT / "provenance-and-receipt-audit.junit.xml",
    "schema_and_type_check": ATTEMPT / "schema-and-type-check.junit.xml",
    "targeted_b06_build_gate": ATTEMPT / "targeted-b06-build-gate.junit.xml",
    "unit_and_contract_tests": ATTEMPT / "unit-and-contract-tests.junit.xml",
    "wire_literal_discipline": ATTEMPT / "wire-literal-discipline.junit.xml",
}
_NODE_JUNITS = frozenset({"full_node_suite"})
RUN_RESULTS = (
    "backend-pin-ledger",
    "dependency-regression-b05",
    "full-node-suite",
    "full-python-suite",
    "git-diff-check",
    "negative-and-adversarial-tests",
    "provenance-and-receipt-audit",
    "reproducible-build",
    "ruff-check",
    "ruff-format-check",
    "schema-and-type-check",
    "targeted-b06-build-gate",
    "unit-and-contract-tests",
    "wire-literal-discipline",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "b06-verification.json",
    "b06_0001_rah_seal.py",
    "b06_gate.py",
    "build_b06_0001_evidence.py",
    "commands.jsonl",
    "dependency-regression-b05.junit.xml",
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
    "run_b06_0001_checks.py",
    "schema-and-type-check.junit.xml",
    "targeted-b06-build-gate.junit.xml",
    "test_negative_adversarial.py",
    "test_provenance_receipts.py",
    "test_schema_and_type.py",
    "test_unit_contract.py",
    "unit-and-contract-tests.junit.xml",
    "wire-literal-discipline.junit.xml",
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
        (
            "dependency_regression_b05",
            pytest_summary(JUNIT_PATHS["dependency_regression_b05"]),
            62,
        ),
        ("full_python_suite", pytest_summary(JUNIT_PATHS["full_python_suite"]), 1261),
        (
            "negative_and_adversarial_tests",
            pytest_summary(JUNIT_PATHS["negative_and_adversarial_tests"]),
            48,
        ),
        (
            "provenance_and_receipt_audit",
            pytest_summary(JUNIT_PATHS["provenance_and_receipt_audit"]),
            14,
        ),
        (
            "schema_and_type_check",
            pytest_summary(JUNIT_PATHS["schema_and_type_check"]),
            12,
        ),
        (
            "targeted_b06_build_gate",
            pytest_summary(JUNIT_PATHS["targeted_b06_build_gate"]),
            93,
        ),
        (
            "unit_and_contract_tests",
            pytest_summary(JUNIT_PATHS["unit_and_contract_tests"]),
            19,
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
        ("full_node_suite", node_summary(JUNIT_PATHS["full_node_suite"]), 1276),
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
            "B05": _sealed_dependency("B05", "B05-0001", "E0153", "E0154"),
            "C05": _sealed_dependency("C05", "C05-0001", "E0155", "E0156"),
            "S05": _sealed_dependency("S05", "S05-0001", "E0175", "E0176"),
        },
        "next_action": "SEAL_B06_0001_THEN_CONTINUE_DAG",
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
            "build/v4_b06/**",
            "artifacts/work_packages/B06/**",
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
            "backend_pin_requirements": ("schemas/shinka-backend-manifest.schema.json"),
            "environment_pins": (
                "toolchains/toolchain-lock.json (SOURCE_DATE_EPOCH et al.)"
            ),
            "staging_list": (
                "scripts/build/canonical_registry/build_hooks.py _canonical_source_files"
            ),
        },
        "exit_criteria": {
            "all_completion_and_external_effects_resolve_to_immutable_receipts": {
                "mechanism": (
                    "reproducible-build.json, pin-ledger.json and gate-manifest.json re-derive their own hashes, the manifest binds both record hashes, and the build command is recorded with B02's placeholder so no machine-local path enters a receipt"
                ),
                "status": "PASS",
            },
            "governing_schemas_authority_boundaries_failure_states_exact": {
                "mechanism": (
                    "the pin ledger's field set is closed, every pin carries kind, subject, digest and source, a floating pin is refused by its own code, and the Shinka backend pin is recorded BLOCKED with digest null rather than invented"
                ),
                "status": "PASS",
            },
            "happy_negative_crash_resume_adversarial_coverage": {
                "mechanism": (
                    "a real uv build ran twice from a staged snapshot and the wheel and sdist are bit-identical under the inherited environment normalization only — no post-hoc byte rewriting and no member excluded from the comparison"
                ),
                "status": "PASS",
            },
            "no_candidate_model_prompt_backend_or_hook_acquires_authority": {
                "mechanism": (
                    "the gate builds and compares; it promotes nothing, and the backend pin requirements come from the canonical manifest schema rather than from any backend's own claims"
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
                f"{ATTEMPT_DIR}/build_b06_0001_evidence.py",
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
        "# B06-0001 primary-session review of parallel-agent work\n"
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
        "- The double build is bit-identical: wheel and sdist digests equal across two real uv builds, with environment pinning inherited from the toolchain lock (SOURCE_DATE_EPOCH cross-checked against CI).\n"
        "- A real defect in B02's scripts/build/double_build.py was found and reproduced (its staging list omits scripts/schemas/openapi and drops scripts/build by name, so it cannot build the current tree); it is B02's territory and was not modified — recorded as an inherited-debt finding for a B02 correction.\n"
        "- Snapshot is staged once and copied: double-staging a live tree under concurrent edits produced false nondeterminism (131 sdist member diffs from other agents' writes), which would have been a false BUILD_NONDETERMINISTIC report.\n"
        "- The Shinka backend pin is honestly BLOCKED (no digest exists anywhere to pin); T06 owns qualifying it.\n"
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
        "attempt_type": "B06_REPRODUCIBLE_BUILD_BACKEND_PIN_GATE",
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
        "next_package": "E06-0001",
        "not_claimed": [
            "Node workspace tarball reproducibility, which B02's build gate owns",
            "a fix for B02's double_build.py defect, which is outside this package's write scope and is recorded as a finding instead",
            "a Shinka backend digest: none exists to pin, and the ledger says BLOCKED rather than inventing one",
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
        "next_action": "SEAL_B06_0001_THEN_CONTINUE_DAG",
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
    write_json("b06-verification.json", verification)
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
        raise SystemExit("B06-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "b06-verification.json")
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
    verification = read_json(ATTEMPT / "b06-verification.json")
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
        raise SystemExit("stored B06-0001 report is not the deterministic document")
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
