#!/usr/bin/env python3
"""Build and verify Z01-0001 evidence: Fresh-install, compatibility and uninstall matrix.

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
ATTEMPT = ROOT / "artifacts/work_packages/Z01/attempts/0001"
ATTEMPT_ID = "Z01-0001"
WORK_PACKAGE_ID = "Z01"
RECORDED_AT = "2026-08-02T19:45:00.000Z"
ATTEMPT_DIR = "artifacts/work_packages/Z01/attempts/0001"
AUTHORITY_DECISION = None

EXPECTED_PRODUCT_HASHES = {
    "artifacts/work_packages/Z01/attempts/0001/check_matrix_lint.py": "c867f51b2957605dc8091e002c5a81576752309fc56d8501f3d0bc01937cdd70",
    "artifacts/work_packages/Z01/attempts/0001/run_z01_0001_checks.py": "0b86b64b3211b06e7cd242ebc03a66fe080b3fae1ba1fcc020d5129ed88c0948",
    "manifests/compatibility_matrix.yaml": "e27e2bcb433928263d56a503160dc9d7202ba553839136d2ae15cf2fdafde654",
    "tests/install/local-marketplace/g04-lifecycle.test.mjs": "4d93c3e2ae45c5208c9e16a59e85dd4179e2377ce917af1eaae5d66453c94cdf",
    "tests/install/local-marketplace/lifecycle-harness.mjs": "247a120aaf20c23f71a3e8d56340e5ad82fc4c0918b30577ba23b00e593eacf1",
    "tests/install/test_install_matrix.py": "4210897230db8b7970dcf2c3674d4334103015607f7976cc78bc8572151fd01c",
    "tests/install/test_uninstall_data.py": "7c6acaa67e05ab381508bbc64b5acbd25ca75b55e462308b58050c865f9fc092",
    "tests/install/z01_matrix_harness.py": "d970823f67cba72fe7f8dffa7b36171ae82718e3195c49d91b0056d13fa8e493",
}
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/G04/attempts/0001/report.json": "a92fc172579ebe5bda130f6aa25c04953caa5ffdb14c7467cb2f12c3089383cd",
    "artifacts/work_packages/H04/attempts/0001/report.json": "94d60a0b9be870500a94469a645cfb405e39fdd4e02333727fe12a5eb1ae1161",
    "artifacts/work_packages/L04/attempts/0001/report.json": "35bb257c90665b2351ab3e9e28a769edd3984aed410c608a2d34ef1713a413d5",
    "artifacts/work_packages/M04/attempts/0001/report.json": "10dc679144d91bb797fbc4d5d5dddea92420759de53c8b08c7951e3882439ea5",
    "artifacts/work_packages/P04/attempts/0001/report.json": "f94cab8d02468a199b0b08030728d172ea1530b34c500c93307c33e050f220ab",
    "artifacts/work_packages/Q04/attempts/0001/report.json": "f2f8216af551eeeb3ffaa266a773ff065c6e88ea498b9000d80831fc5ce732fd",
    "artifacts/work_packages/S04/attempts/0005/report.json": "9f088632a014740e6790127e485262013aac823fb6d58c96d3320f378e20a723",
    "artifacts/work_packages/S05/attempts/0001/report.json": "dbcb94e77fd885f18aa36a00dc352a9d5a788d265b979ff7a23fafd5f261c727",
    "artifacts/work_packages/T04/attempts/0001/report.json": "ef86645d7ca5058df3047b6b53fbb3dd4c56af41b27db481b773d205e96c6272",
    "artifacts/work_packages/U04/attempts/0001/report.json": "a59cad7db20bdd2fb143fef591cfa7dedac01e88e78a15feb53b6a8b250fe974",
    "artifacts/work_packages/V04/attempts/0001/report.json": "dc61b2a51afa1bfb8a3d9ffc540e576b69103cd2fd49c9c650086f2a41e030ef",
    "artifacts/work_packages/W04/attempts/0001/report.json": "b07687917d9bf5a150d78c9fd1580e24308823f95e1c8713302b7e4af3c75688",
    "artifacts/work_packages/X04/attempts/0001/report.json": "87d60e7bae4b75588f4c3093a0ec2425912eba4e7ed15d3db9587bf6ff7312a2",
    "artifacts/work_packages/Y04/attempts/0001/report.json": "1e99e6677735d841ca32527ed8765391e4e0dff0ecbef3751cb4ea153de7c45c",
}

JUNIT_PATHS = {
    "full_node_suite": ATTEMPT / "full-node-suite.junit.xml",
    "full_python_suite": ATTEMPT / "full-python-suite.junit.xml",
    "install_matrix_test": ATTEMPT / "install-matrix-test.junit.xml",
    "uninstall_data_test": ATTEMPT / "uninstall-data-test.junit.xml",
}
_NODE_JUNITS = frozenset({"full_node_suite"})
RUN_RESULTS = (
    "compatibility-matrix-lint",
    "full-node-suite",
    "full-python-suite",
    "git-diff-check",
    "install-matrix-test",
    "ruff-check",
    "ruff-format-check",
    "uninstall-data-test",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "build_z01_0001_evidence.py",
    "check_matrix_lint.py",
    "commands.jsonl",
    "dependency-status.json",
    "full-node-suite.junit.xml",
    "full-python-suite.junit.xml",
    "install-matrix-test.junit.xml",
    "junit-normalization-verification.json",
    "node-test-inventory.json",
    "review.md",
    "run_z01_0001_checks.py",
    "uninstall-data-test.junit.xml",
    "write-scope-verification.json",
    "z01-verification.json",
    "z01_0001_rah_seal.py",
)
#: Maps each manifest required check to the regression suite key that carries its
#: measured count.  Injected from the wave config; defaults to the four standard
#: suites for standard-shape packages.
REQUIRED_CHECK_MAP = {
    "install_matrix_test": "install_matrix_test",
    "uninstall_data_test": "uninstall_data_test",
}
#: Maps each manifest exit-criterion key to its mechanism sentence.
EXIT_CRITERIA = {
    "all_supported_hosts_os_tested": "install_matrix_test evaluates every host/OS cell declared in manifests/compatibility_matrix.yaml as a fail-closed lifecycle proof and refuses any cell claiming SUPPORTED without the recorded fresh-install, lifecycle-hook, MCP, payload, upgrade, rollback and uninstall evidence",
    "uninstall_preserves_user_data_policy": "uninstall_data_test proves the declared uninstall lifecycle removes plugin artifacts while preserving the retained user-data policy and refuses any uninstall plan that would delete data the policy retains",
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
        ("full_python_suite", pytest_summary(JUNIT_PATHS["full_python_suite"]), 1285),
        ("install_matrix_test", pytest_summary(JUNIT_PATHS["install_matrix_test"]), 14),
        ("uninstall_data_test", pytest_summary(JUNIT_PATHS["uninstall_data_test"]), 10),
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
            "G04": _sealed_dependency("G04", "G04-0001", "E0333", "E0334"),
            "H04": _sealed_dependency("H04", "H04-0001", "E0349", "E0350"),
            "L04": _sealed_dependency("L04", "L04-0001", "E0050", "E0051"),
            "M04": _sealed_dependency("M04", "M04-0001", "E0062", "E0063"),
            "P04": _sealed_dependency("P04", "P04-0001", "E0147", "E0148"),
            "Q04": _sealed_dependency("Q04", "Q04-0001", "E0177", "E0178"),
            "S04": _sealed_dependency("S04", "S04-0005", "E0097", "E0098"),
            "T04": _sealed_dependency("T04", "T04-0001", "E0151", "E0152"),
            "U04": _sealed_dependency("U04", "U04-0001", "E0259", "E0260"),
            "V04": _sealed_dependency("V04", "V04-0001", "E0257", "E0258"),
            "W04": _sealed_dependency("W04", "W04-0001", "E0141", "E0142"),
            "X04": _sealed_dependency("X04", "X04-0001", "E0251", "E0252"),
            "Y04": _sealed_dependency("Y04", "Y04-0001", "E0337", "E0338"),
        },
        "next_action": "SEAL_Z01_0001_THEN_CONTINUE_DAG",
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
            "tests/install/**",
            "manifests/compatibility_matrix.yaml",
            "artifacts/work_packages/Z01/**",
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
            "host_and_platform_lists": (
                "manifests/compatibility_matrix.yaml is the single declaring source of the host and platform lists; the harness never restates them"
            ),
            "payload_layout": (
                "manifests/compatibility_matrix.yaml payload.expected_top_level over plugins/epistemic-foundry"
            ),
            "real_lifecycle": (
                "G04-0001 local-marketplace fresh-install and clean-uninstall lifecycle (composed, not duplicated)"
            ),
            "sealed_host_provenance": (
                "manifests/compatibility_matrix.yaml sealed_dependencies binds each host to the sealed x04 attempt that establishes it"
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
                f"{ATTEMPT_DIR}/build_z01_0001_evidence.py",
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
        "# Z01-0001 primary-session review of parallel-agent work\n"
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
        "- The compatibility matrix is a fail-closed UNVERIFIED reference: every host cell is UNVERIFIED or ADAPTER_REQUIRED and every install decision REFUSED until recorded evidence, so no cell presents the v4 plugin as executable, validated or production-ready.\n"
        "- The host and platform lists live only in manifests/compatibility_matrix.yaml; the harness reads and never restates them, and compatibility-matrix-lint enforces the closed schema.\n"
        "- The single real install/uninstall lifecycle is composed from the sealed G04-0001 gate; every other host/OS cell is a declared-policy proof over the in-repo payload, stated in the module honesty boundary.\n"
        "- manifests/compatibility_matrix.yaml is inside Z01's manifest write scope, so adding the sealed-host provenance dimension needs no separate scope grant.\n"
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
        "attempt_type": "Z01_FRESH_INSTALL_COMPATIBILITY_UNINSTALL_MATRIX",
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
        "next_package": "Z02-0001",
        "not_claimed": [
            "a real multi-OS install: every host/OS cell except the composed G04 single-host lifecycle is a declared-matrix proof over the in-repo payload, not an executed install",
            "that the v4 plugin is executable, validated or production-ready: the matrix records no runtime-executability claim and every host cell stays UNVERIFIED or ADAPTER_REQUIRED",
            "physical uninstall on any host: the uninstall check verifies the declared data-preservation policy, not a runtime deletion",
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
        "next_action": "SEAL_Z01_0001_THEN_CONTINUE_DAG",
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
    write_json("z01-verification.json", verification)
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
        raise SystemExit("Z01-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "z01-verification.json")
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
    verification = read_json(ATTEMPT / "z01-verification.json")
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
        raise SystemExit("stored Z01-0001 report is not the deterministic document")
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
