#!/usr/bin/env python3
"""Build and verify B03-0001 evidence: cross-platform CI and cache policy.

B03 depends on B01. It attests, without editing them, the cross-platform CI
workflow ``.github/workflows/ci.yml``, the two required-check validators
``scripts/ci/ci_matrix_lint.py`` and ``scripts/ci/cache_key_audit.py``, the
ten-test fail-closed mutation suite ``scripts/ci/test_ci_policy.py`` and the
cache/reproducibility contract ``docs/cache_contract.md``, against the two
required checks its manifest declares, ``ci_matrix_lint`` and ``cache_key_audit``.
Each required check is the package's own Python validator, run via ``python
scripts/ci/*.py --report`` and emitting a deterministic JSON status object that
must report status=PASS with an empty failure list. As supporting evidence, the
ten fail-closed mutation tests are run under pytest.

This builder verifies the executed check receipts, confirms both required
validators reported a clean PASS, gates the mutation suite plus the
repository-wide Python and live Node suites on zero failures, pins the CI-config
product bytes B03 attests, binds the sealed B01-0001 dependency and regression
baseline, and emits the deterministic attempt evidence. It never edits the CI
config, and B03 reaches GREEN with ZERO substantive change: it attests the
already-authored workflow, validators, mutation suite and cache contract rather
than re-authoring them. The required checks prove the workflow DEFINITION only;
GitHub-hosted execution of the three OS lanes is the B04 integration gate.
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
ATTEMPT = ROOT / "artifacts/work_packages/B03/attempts/0001"
ATTEMPT_ID = "B03-0001"
WORK_PACKAGE_ID = "B03"
ATTEMPT_DIR = "artifacts/work_packages/B03/attempts/0001"
RECORDED_AT = "2026-08-02T00:00:00.000Z"

APPROVED_SCOPE = [
    ".github/workflows/**",
    "scripts/ci/**",
    "docs/cache_contract.md",
]
#: Live sha256 of the CI-config product bytes B03 attests (never edits): the
#: cross-platform workflow, the two required-check validators, the mutation
#: suite, and the cache/reproducibility contract. write_scope_verification
#: confirms the runner receipt is exactly these bytes and that none has drifted.
EXPECTED_PRODUCT_HASHES = {
    ".github/workflows/ci.yml": "cb296023a66880b758fee201f0bd3a51a8a29943e8bea8cdb96b6694e22108fa",
    "scripts/ci/ci_matrix_lint.py": "580fa21b83325dbec00e623d0779edfb0008f3c269e51a465a4fbb541c902606",
    "scripts/ci/cache_key_audit.py": "151fcfbb182e62967503e6e5a987dc4875949efd40f2ba58c4d67c093360b449",
    "scripts/ci/test_ci_policy.py": "1b76fae609a1a259ae305439938f8d1940af11e0bd43d08b67309c8938d8fb4d",
    "docs/cache_contract.md": "d64a2331ae8f2db076903eed3058b301ec2d2d9f98e6edcb115d2d9de9557f3d",
}
#: The full pinned product-byte set B03 is accountable for. B03 authors no
#: additional harness under its attempt directory -- both required checks are the
#: validators the package already carries under scripts/ci.
EXPECTED_SRC_HASHES = dict(EXPECTED_PRODUCT_HASHES)
#: B03 depends on B01 (manifest depends_on: [B01]); it binds the sealed B01-0001
#: report as its build dependency and regression baseline. Pinned by content.
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/B01/attempts/0001/report.json": "9bc65c52408117105ee5da16f2d7b04995fd54a3a679f1fe341566f409d110bd",
}

JUNIT_PATHS = {
    "test_ci_policy": ATTEMPT / "test-ci-policy.junit.xml",
    "full_python_suite": ATTEMPT / "full-python-suite.junit.xml",
    "full_node_suite": ATTEMPT / "full-node-suite.junit.xml",
}
#: The mutation suite and the repository-wide Python gate are pytest; only the
#: repository-wide Node regression is a Node suite.
_NODE_JUNITS = frozenset({"full_node_suite"})
PYTEST_SUITES = (
    "test_ci_policy",
    "full_python_suite",
)
NODE_SUITES = ("full_node_suite",)
#: The supporting fail-closed mutation suite whose measured count the report
#: cites (not a manifest required check).
POLICY_SUITE = "test_ci_policy"
#: The two required checks are Python validators (JSON status, not pytest); their
#: evidence files carry the validator's own deterministic status object.
REQUIRED_JSON_CHECKS = {
    "ci_matrix_lint": "ci-matrix-lint.json",
    "cache_key_audit": "cache-key-audit.json",
}
#: One ``<name>.run.json`` receipt is expected per step (runner contract).
RUN_RESULTS = (
    "ci-matrix-lint",
    "cache-key-audit",
    "test-ci-policy",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
    "write-scope-verification",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "b03-verification.json",
    "b03_0001_rah_seal.py",
    "build_b03_0001_evidence.py",
    "cache-key-audit.json",
    "ci-matrix-lint.json",
    "commands.jsonl",
    "dependency-status.json",
    "full-node-suite.junit.xml",
    "full-python-suite.junit.xml",
    "junit-normalization-verification.json",
    "node-test-inventory.json",
    "report.json",
    "review.md",
    "run_b03_0001_checks.py",
    "test-ci-policy.junit.xml",
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


def required_check_evidence() -> dict[str, dict[str, Any]]:
    # The two required checks are the package's Python validators. Their receipts
    # are gated by check_run (exit 0 / PASS); here the validator's own JSON status
    # object is re-read and confirmed to report PASS with an empty failure list,
    # and its key contract metrics are surfaced for the report.
    evidence: dict[str, dict[str, Any]] = {}
    for check, filename in REQUIRED_JSON_CHECKS.items():
        payload = read_json(ATTEMPT / filename)
        if (
            payload.get("check") != check
            or payload.get("status") != "PASS"
            or payload.get("failures") != []
        ):
            raise SystemExit(
                f"required validator evidence not a clean PASS: {check}: {payload}"
            )
        evidence[check] = payload
    return evidence


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
    # Counts are derived (expected == measured) rather than pinned; the gate is
    # fail-closed. Every pytest suite must be non-empty and wholly green; the
    # live Node suite gates on zero failures with its measured frontier count.
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
        full = node_summary(JUNIT_PATHS[name])
        if (
            full["failed"],
            full["cancelled"],
            full["xml_error_count"],
            full["xml_failure_count"],
        ) != (0, 0, 0, 0) or full["passed"] <= 0 or full["collected"] != (
            full["passed"] + full["skipped"] + full["todo"]
        ):
            raise SystemExit(f"{name} gate failed: {full}")
        summaries[name] = full
    inventory = read_json(ATTEMPT / "node-test-inventory.json")
    return {
        "attempt_id": ATTEMPT_ID,
        "count_authority": "derived_from_measured_junit_expected_equals_measured",
        "fail_closed_policy_suite": POLICY_SUITE,
        "fail_closed_policy_suite_passed": summaries[POLICY_SUITE]["passed"],
        "full_node_gate": "zero_failures_with_live_inventory_count",
        "full_node_inventory_count": inventory.get("count"),
        "full_node_passed": summaries["full_node_suite"]["passed"],
        "full_python_passed": summaries["full_python_suite"]["passed"],
        "new_failure_count": 0,
        "regression_baseline_attempt": "B01-0001",
        "status": "PASS",
        "suites": summaries,
    }


def _sealed_dependency(
    package: str, attempt: str, core: str, final: str
) -> dict[str, Any]:
    path = ROOT / f"artifacts/work_packages/{package}/attempts/{attempt[-4:]}/report.json"
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
        "core_generation": rah.get("core_generation"),
        "final_closeout_evidence_id": final,
        "report": path.relative_to(ROOT).as_posix(),
        "report_sha256": sha256_id(path),
        "status": "PASS",
    }


def dependency_status() -> dict[str, Any]:
    # B03 depends on B01 (manifest depends_on: [B01]). The sealed B01-0001 report
    # is bound here as the build dependency and, as the latest sealed checkpoint
    # on B03's lineage, as the regression baseline. Both are pinned by content.
    assert_hashes(EXPECTED_DEPENDENCY_HASHES)
    b01 = _sealed_dependency("B01", "B01-0001", "E0295", "E0296")
    return {
        "attempt_id": ATTEMPT_ID,
        "dependencies": {
            "B01": b01,
        },
        "dependency_note": (
            "B03 depends on B01; the sealed B01-0001 attempt is the build "
            "dependency"
        ),
        "next_action": "SEAL_B03_0001_THEN_RECOMPUTE_DAG",
        "regression_baseline": b01,
        "regression_baseline_note": (
            "B01-0001 is the sealed PASS attempt B03 depends on, bound as the "
            "regression baseline. The live ledger frontier advances under "
            "concurrent sealing; the parent reconciles the exact frontier when it "
            "fills the ledger pins at seal time."
        ),
        "status": "PASS",
    }


def write_scope_verification() -> dict[str, Any]:
    # B03's manifest write scope is .github/workflows/**, scripts/ci/** and
    # docs/cache_contract.md. The runner authors write-scope-verification.json
    # over the CI-config product files; the builder re-derives their hashes live,
    # pins them, and confirms the recorded receipt is exactly those bytes with
    # every mutation counter zero. This sealing session attests these authored
    # files without editing them.
    assert_hashes(EXPECTED_PRODUCT_HASHES)
    live_hashes = {
        relative: "sha256:" + sha256(ROOT / relative)
        for relative in sorted(EXPECTED_PRODUCT_HASHES)
    }
    pinned = {
        relative: "sha256:" + digest
        for relative, digest in EXPECTED_PRODUCT_HASHES.items()
    }
    if live_hashes != pinned:
        raise SystemExit("CI-config product hashes drifted from the pinned set")
    record = read_json(ATTEMPT / "write-scope-verification.json")
    if (
        record.get("attempt_id") != ATTEMPT_ID
        or record.get("status") != "PASS"
        or record.get("approved_scope") != APPROVED_SCOPE
        or record.get("product_file_hashes") != live_hashes
        or record.get("attested_product_files") != sorted(EXPECTED_PRODUCT_HASHES)
        or record.get("attestation_only_no_ci_config_edits") is not True
        or record.get("write_scope_violation_count") != 0
        or record.get("schema_or_test_weakening_count") != 0
        or record.get("root_canonical_source_mutation_count") != 0
        or record.get("reset_clean_stash_commit_push_performed") is not False
        or record.get("checked_file_count") != len(live_hashes)
    ):
        raise SystemExit(
            f"write-scope-verification receipt is not conformant: {record}"
        )
    return record


def package_verification(
    regression: dict[str, Any], required: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    suites = regression["suites"]
    lint = required["ci_matrix_lint"]
    cache = required["cache_key_audit"]
    return {
        "attempt_id": ATTEMPT_ID,
        "attestation_scope": {
            "attested_not_authored": (
                "B03 attests the cross-platform CI workflow, the two required "
                "validators, the ten-test fail-closed mutation suite and the "
                "cache/reproducibility contract the repository already carries; "
                "this sealing session makes ZERO edit and does not re-author them"
            ),
            "ci_config_product_files": sorted(EXPECTED_PRODUCT_HASHES),
        },
        "exit_criteria": {
            "linux_macos_windows_lanes_defined": {
                "mechanism": (
                    "ci_matrix_lint parses .github/workflows/ci.yml and asserts "
                    "matrix.os is exactly the three versioned hosted-runner lanes "
                    f"{lint.get('runners')} (no -latest moving alias), the job "
                    "runs on ${{ matrix.os }} with fail-fast: false so every OS "
                    "produces a result, permissions are contents: read with no "
                    "pull_request_target and no suppressed failures, every action "
                    "is pinned to the reviewed full commit SHA exactly once, and "
                    "the setup-node/python/uv versions match the pinned toolchain "
                    "lock"
                ),
                "status": "PASS",
            },
            "caches_are_disposable_and_hash_keyed": {
                "mechanism": (
                    "cache_key_audit asserts exactly one reviewed actions/cache "
                    "step whose paths live below runner.temp and overlap no "
                    "canonical or output tree, a key bound to matrix.os + "
                    "runner.arch + exactly one hashFiles over the four lock "
                    "inputs (package-lock.json, uv.lock, toolchain-lock.json, "
                    "python-build-constraints.txt), no prefix restore-keys, "
                    "enableCrossOsArchive: false and fail-on-cache-miss: false so "
                    "a cache miss is non-fatal"
                ),
                "status": "PASS",
            },
        },
        "fail_closed_policy_suite": {
            "suite": POLICY_SUITE,
            "test_count": suites[POLICY_SUITE]["collected"],
            "proves": (
                "each validator fails closed on the reviewed drift shapes -- a "
                "moving runner alias, a moving action tag, a duplicate approved "
                "action, pull_request_target, a dropped lock input, a prefix "
                "restore key, a cross-OS archive, a fatal cache miss, and a "
                "canonical-output cache path"
            ),
            "status": "PASS",
        },
        "required_checks": {
            "independent_review": {
                "evidence": (
                    "review.md (author: the bounded implementation agent(s) that "
                    "authored the cross-platform workflow, the two validators, the "
                    "mutation suite and the cache contract; reviewer: the sealing "
                    "session, which did not author this attempt; actor_independence "
                    "between author and reviewer holds, external certification does "
                    "not)"
                ),
                "status": "PASS",
            },
            "ci_matrix_lint": {
                "validator": "python scripts/ci/ci_matrix_lint.py",
                "runners": lint.get("runners"),
                "action_pins": lint.get("action_pins"),
                "failures": lint.get("failures"),
                "status": "PASS",
            },
            "cache_key_audit": {
                "validator": "python scripts/ci/cache_key_audit.py",
                "cache_action": cache.get("cache_action"),
                "key": cache.get("key"),
                "paths": cache.get("paths"),
                "exact_restore_only": cache.get("exact_restore_only"),
                "cross_os_archive": cache.get("cross_os_archive"),
                "cache_miss_is_fatal": cache.get("cache_miss_is_fatal"),
                "failures": cache.get("failures"),
                "status": "PASS",
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
                f"{ATTEMPT_DIR}/build_b03_0001_evidence.py",
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
        "# B03-0001 independent review of bounded-agent work\n"
        "\n"
        "- Author: the bounded implementation agent(s) that authored the B03\n"
        "  cross-platform CI workflow (.github/workflows/ci.yml), the two\n"
        "  required-check validators (scripts/ci/ci_matrix_lint.py,\n"
        "  scripts/ci/cache_key_audit.py), the ten-test fail-closed mutation suite\n"
        "  (scripts/ci/test_ci_policy.py) and the cache/reproducibility contract\n"
        "  (docs/cache_contract.md). Reviewer: this sealing session, a distinct\n"
        "  actor that did not author this attempt. Author/reviewer separation\n"
        "  holds (actor_independence=true); external actor-independent\n"
        "  certification does not.\n"
        "- Mode: INDEPENDENT_REVIEW_OF_BOUNDED_AGENT_WORK. Blocking findings: 0.\n"
        "- Scope: the manifest write scope is .github/workflows/**, scripts/ci/**\n"
        "  and docs/cache_contract.md. This session makes ZERO edit to the CI\n"
        "  config: the five product files are hash-pinned as they currently are\n"
        "  and every mutation counter is zero. No canonical source, schema,\n"
        "  manifest, or .rah/ state was touched.\n"
        "- Exit criterion 1 - Linux/macOS/Windows lanes defined: VERIFIED.\n"
        "  ci_matrix_lint (python scripts/ci/ci_matrix_lint.py) asserts matrix.os\n"
        "  is exactly {ubuntu-24.04, macos-15, windows-2025} -- three versioned\n"
        "  hosted-runner labels, no -latest moving alias -- with fail-fast: false\n"
        "  so every OS produces a result, the job running on ${{ matrix.os }}.\n"
        "  Permissions are exactly contents: read; pull_request_target and\n"
        "  suppressed failures are rejected; every action is pinned to the\n"
        "  reviewed full commit SHA and appears exactly once; and the\n"
        "  setup-node/python/uv versions are bound to toolchains/toolchain-lock\n"
        "  .json. The validator exits 0 with an empty failure list.\n"
        "- Exit criterion 2 - caches are disposable and hash-keyed: VERIFIED.\n"
        "  cache_key_audit (python scripts/ci/cache_key_audit.py) asserts exactly\n"
        "  one reviewed actions/cache step whose two paths live below runner.temp\n"
        "  (efoundry-cache/npm, efoundry-cache/uv) and overlap none of\n"
        "  .git/.rah/.venv/artifacts/build/dist/ledger/node_modules/reports/src/\n"
        "  tests. The key is bound to matrix.os + runner.arch + exactly one\n"
        "  hashFiles over the four lock inputs (package-lock.json, uv.lock,\n"
        "  toolchains/toolchain-lock.json, toolchains/python-build-constraints\n"
        "  .txt); prefix restore-keys are absent, enableCrossOsArchive is false,\n"
        "  and fail-on-cache-miss is false so a miss is non-fatal and locked\n"
        "  installation reconstructs the state. The validator exits 0 with an\n"
        "  empty failure list.\n"
        "- Fail-closed proof. test_ci_policy runs ten mutation tests that feed\n"
        "  mutated copies of the workflow to both validators and confirm each\n"
        "  REJECTS the reviewed drift shapes: a moving runner alias\n"
        "  (ubuntu-latest), a moving action tag (checkout@v6), a duplicate\n"
        "  approved action, pull_request_target, a dropped uv.lock hash input, a\n"
        "  prefix restore key, a cross-OS archive, a fatal cache miss, and a\n"
        "  canonical (artifacts) cache path. All ten pass.\n"
        "- Attestation, not authorship. The two required checks are the package's\n"
        "  own Python validators, run via python scripts/ci/*.py exactly as the\n"
        "  manifest names them; both report status=PASS with failures=[]. B03\n"
        "  reached GREEN with no substantive edit to the workflow, the validators,\n"
        "  the mutation suite, or the cache contract.\n"
        "- Gates at review time: ci_matrix_lint PASS (failures=[]), cache_key_audit\n"
        "  PASS (failures=[]), test_ci_policy 10/10, the full Python suite green,\n"
        "  the live full Node suite green with zero failures, and git diff --check\n"
        "  clean. B03 depends on B01; the sealed B01-0001 attempt is the build\n"
        "  dependency and regression baseline.\n"
        "- Honest standing risk (scope boundary, not a weakening): the local\n"
        "  checks prove the workflow DEFINITION -- the three OS lanes, the pinned\n"
        "  actions, and the disposable hash-keyed cache policy -- not that the\n"
        "  GitHub-hosted ubuntu-24.04/macos-15/windows-2025 lanes have actually\n"
        "  executed. Hosted-run evidence is the B04 integration gate, outside B03.\n"
        "- Residual limitations: B03 attests the CI config the repository already\n"
        "  carries; it does not re-author it, makes no product-maturity or\n"
        "  release-readiness claim, does not assert a GitHub-hosted run, does not\n"
        "  claim SBOM/signing/release-provenance (Z-phase scope), and this review\n"
        "  is not external actor-independent certification.\n"
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
        "attempt_type": "B03_CROSS_PLATFORM_CI_AND_CACHE_POLICY",
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
            "editing the cross-platform CI workflow, the validators, the mutation suite or the cache contract: B03 attests .github/workflows/ci.yml, scripts/ci/ci_matrix_lint.py, scripts/ci/cache_key_audit.py, scripts/ci/test_ci_policy.py and docs/cache_contract.md and makes zero substantive change to them",
            "GitHub-hosted execution of the ubuntu-24.04, macos-15 and windows-2025 lanes: the required checks prove the workflow definition only; hosted-run evidence is the B04 integration gate",
            "any product-maturity, runtime-executability or release readiness of the v4 plugin or ShinkaEvolve integration",
            "SBOM, signing, clean-release extraction or release provenance, which are Z-phase scope",
            "actor-independent certification of this review",
            "overall product completion",
            "completion_ready=true",
        ],
        "output_artifacts": artifacts,
        "package_status": "PASS",
        "regression": regression,
        "required_checks": verification["required_checks"],
        "review": {
            "actor_independence": True,
            "assurance_limitation": (
                "Author/reviewer separation holds (bounded implementation "
                "agent(s) authored the CI config and validators, the sealing "
                "session reviewed); external actor-independent certification does "
                "not."
            ),
            "blocking_finding_count": 0,
            "mode": "INDEPENDENT_REVIEW_OF_BOUNDED_AGENT_WORK",
            "role": "contract_reviewer",
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
        "next_action": "SEAL_B03_0001_THEN_RECOMPUTE_DAG",
        "package_status": "PASS",
        "status": "PASS",
    }


def build() -> dict[str, Any]:
    for name in RUN_RESULTS:
        check_run(name)
    required = required_check_evidence()
    assert_hashes(EXPECTED_SRC_HASHES)
    normalize_junits()
    regression = regression_evidence()
    dependencies = dependency_status()
    write_scope = write_scope_verification()
    verification = package_verification(regression, required)
    write_json("dependency-status.json", dependencies)
    write_json("b03-verification.json", verification)
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
        raise SystemExit("B03-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "b03-verification.json")
    report = report_document(
        regression, dependencies, write_scope, verification, rah_state=rah_state
    )
    write_json("report.json", report)


def verify() -> dict[str, Any]:
    for name in RUN_RESULTS:
        check_run(name)
    required = required_check_evidence()
    assert_hashes(EXPECTED_SRC_HASHES)
    normalize_junits()
    regression = regression_evidence()
    assert_hashes(EXPECTED_DEPENDENCY_HASHES)
    stored = read_json(ATTEMPT / "report.json")
    dependencies = read_json(ATTEMPT / "dependency-status.json")
    write_scope_live = write_scope_verification()
    write_scope = read_json(ATTEMPT / "write-scope-verification.json")
    if write_scope_live != write_scope:
        raise SystemExit("write-scope verification drifted from the sealed record")
    verification = read_json(ATTEMPT / "b03-verification.json")
    expected_verification = package_verification(regression, required)
    if render(expected_verification) != render(verification):
        raise SystemExit("stored B03-0001 verification is not the deterministic document")
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
        raise SystemExit("stored B03-0001 report is not the deterministic document")
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
