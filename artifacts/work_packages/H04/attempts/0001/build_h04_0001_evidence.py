#!/usr/bin/env python3
"""Build and verify H04-0001 evidence: capability probe, trust and degraded mode.

H04 depends on H02 and H03.  Its product is the bounded capability-probe module
``packages/plugin-host/src/capability-probe/capability-probe.mjs`` and its two
compatibility test suites ``tests/compatibility/hooks/hook-feature-probe.test.mjs``
and ``tests/compatibility/hooks/hook-degraded-mode.test.mjs``, which are the two
required checks its manifest declares (``hook_feature_probe_test`` and
``hook_degraded_mode_test``).  Both checks run through one deterministic Node
harness under this attempt directory, ``h04-capability-probe-tests.mjs``
(eighteen cases: eleven ``hook_feature_probe_test`` and seven
``hook_degraded_mode_test``), run once via ``node --test``.  The suites assert
the two exit criteria -- unsupported/unobserved coverage is explicit and never
optimistic, and changed or removed active hook bytes force exact re-trust -- and
prove the predicate fails closed on forged trust, hostile/non-plain inputs,
duplicate active hashes, undeclared capabilities, and a missing degraded-mode
fallback.

This builder verifies the executed check receipts, splits the eighteen-case Node
JUnit into the two required checks by name prefix, gates the required suite and
the live repository Node suite on zero failures with their measured counts, gates
the repository-wide Python suite on zero failures, pins the three product bytes
and the harness bytes, records the honest fail-closed maturity boundary (bounded
observation projection only: no live cross-host discovery adapter, no plugin
manifest hooks, empty capabilities, and no ``dist/hook-runner.mjs``), binds the
sealed H02-0001 and H03-0001 dependencies by content, and emits the deterministic
attempt evidence.  It never edits any file outside its own attempt directory.
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
ATTEMPT = ROOT / "artifacts/work_packages/H04/attempts/0001"
ATTEMPT_ID = "H04-0001"
WORK_PACKAGE_ID = "H04"
ATTEMPT_DIR = "artifacts/work_packages/H04/attempts/0001"
RECORDED_AT = "2026-08-02T00:00:00.000Z"

#: The bounded capability-probe module and its two compatibility test suites are
#: the manifest write scope for H04.  There is no separate authority blueprint:
#: the two suites are the product's own required checks.
PRODUCT_FILES = (
    "packages/plugin-host/src/capability-probe/capability-probe.mjs",
    "tests/compatibility/hooks/hook-feature-probe.test.mjs",
    "tests/compatibility/hooks/hook-degraded-mode.test.mjs",
)
APPROVED_SCOPE = [
    "packages/plugin-host/src/capability-probe/**",
    "tests/compatibility/hooks/**",
    "artifacts/work_packages/H04/**",
]
#: Live sha256 of the write-scope product H04 authors (never edits after the
#: attempt is frozen).  write_scope_verification confirms the runner receipt is
#: exactly these bytes.
EXPECTED_PRODUCT_HASHES = {
    "packages/plugin-host/src/capability-probe/capability-probe.mjs": "1b419ca7902d4dfcceaaec92f9c533c3d4990ec7c42afc4b7ce45b2827e0d2b4",
    "tests/compatibility/hooks/hook-feature-probe.test.mjs": "a55247f3eccf223d49c187843be681f056cd40c25681111a2b9f15d50751d4b3",
    "tests/compatibility/hooks/hook-degraded-mode.test.mjs": "7a5c6bbf507b7524f786dfae9aa961817548a5f5c9c45f725b948186335843db",
}
#: The Node contract harness H04 authored under its own attempt scope; it maps
#: both required checks onto one run.
EXPECTED_HARNESS_HASHES = {
    "artifacts/work_packages/H04/attempts/0001/h04-capability-probe-tests.mjs": "004025bff195165b23b94b5cc2b47f1728214e6567e3794a46348ee1208fb838",
}
#: The full pinned product-byte set H04 is accountable for: the three write-scope
#: files plus the harness authored.
EXPECTED_SRC_HASHES = {**EXPECTED_PRODUCT_HASHES, **EXPECTED_HARNESS_HASHES}
#: The plugin manifest whose fail-closed maturity boundary H04 attests without
#: editing: no hooks key, empty capabilities, and no runtime hook runner.
PLUGIN_MANIFEST = "plugins/epistemic-foundry/.codex-plugin/plugin.json"
EXPECTED_MANIFEST_HASH = (
    "1b1ec359ab93733114c95acb34c4a74615974456ddab52fa7c1c538159318a87"
)
HOOK_RUNNER = "plugins/epistemic-foundry/dist/hook-runner.mjs"
#: H04 depends on H02 and H03 (manifest depends_on: [H02, H03]); it binds both
#: sealed attempts by content-hash and by their sealed core/final evidence ids.
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/H02/attempts/0001/report.json": "f6b98a6ede90ec744d5777108a83b1a15bce013ff1270e89696dc427ab4d0a85",
    "artifacts/work_packages/H03/attempts/0001/report.json": "153e69b78f1e7b7ca085825e29fb5f0815f9fa4aeb8fdba5948c6730d5a2416d",
}

JUNIT_PATHS = {
    "capability_probe_tests": ATTEMPT / "capability-probe-tests.junit.xml",
    "full_python_suite": ATTEMPT / "full-python-suite.junit.xml",
    "full_node_suite": ATTEMPT / "full-node-suite.junit.xml",
}
#: The required-check harness and the repository Node regression are Node suites;
#: only the repository-wide Python gate is a pytest suite.
_NODE_JUNITS = frozenset({"capability_probe_tests", "full_node_suite"})
PYTEST_SUITES = ("full_python_suite",)
NODE_SUITES = ("capability_probe_tests", "full_node_suite")
#: Both required checks run through the single capability-probe harness; each is
#: derived from the eighteen-case Node JUnit by testcase-name prefix.  The two
#: suites contribute eleven and seven cases respectively.
REQUIRED_CHECK_PREFIXES = {
    "hook_feature_probe_test": "hook_feature_probe_test: ",
    "hook_degraded_mode_test": "hook_degraded_mode_test: ",
}
REQUIRED_CHECK_COUNTS = {
    "hook_feature_probe_test": 11,
    "hook_degraded_mode_test": 7,
}
EXPECTED_HOOK_CASE_NAMES = (
    "hook_feature_probe_test: report is schema-shaped, hash-bound, and explicit about unobserved paths",
    "hook_feature_probe_test: declaration order cannot change trust or report hashes",
    "hook_feature_probe_test: changed active hook bytes require exact re-trust",
    "hook_feature_probe_test: removed hook hashes also invalidate prior trust",
    "hook_feature_probe_test: removing every formerly trusted hook remains explicit",
    "hook_feature_probe_test: a hook observation error cannot be weakened by trust state",
    "hook_feature_probe_test: disabled changed hooks retain re-trust debt",
    "hook_feature_probe_test: duplicate active hook hashes fail closed",
    "hook_feature_probe_test: missing observations fail closed to UNKNOWN rather than optimistic support",
    "hook_feature_probe_test: empty event and tool scopes never prove FULL coverage",
    "hook_feature_probe_test: unsupported claims, forged trust, and hostile inputs fail closed",
    "hook_degraded_mode_test: complete observed support is FULL and health PASS",
    "hook_degraded_mode_test: unavailable optional hooks select the declared DEGRADED behavior",
    "hook_degraded_mode_test: a required capability without a fallback is BLOCKED",
    "hook_degraded_mode_test: explicit READ_ONLY and SAFE_MODE mappings use the strongest mode",
    "hook_degraded_mode_test: incomplete event coverage cannot remain FULL",
    "hook_degraded_mode_test: re-trust debt is visible in health and cannot be masked by FULL",
    "hook_degraded_mode_test: undeclared fallback and report tampering fail closed",
)
#: One ``<name>.run.json`` receipt is expected per step (runner contract).
RUN_RESULTS = (
    "capability-probe-tests",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
    "write-scope-verification",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "build_h04_0001_evidence.py",
    "capability-probe-tests.junit.xml",
    "commands.jsonl",
    "dependency-status.json",
    "full-node-suite.junit.xml",
    "full-python-suite.junit.xml",
    "h04-capability-probe-tests.mjs",
    "h04-verification.json",
    "h04_0001_rah_seal.py",
    "junit-normalization-verification.json",
    "node-test-inventory.json",
    "report.json",
    "review.md",
    "run_h04_0001_checks.py",
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
    # fail-closed. The pytest suite must be non-empty and wholly green; the
    # required-check harness and the live Node suite gate on zero failures with
    # their measured frontier counts.
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
        "full_node_gate": "zero_failures_with_live_inventory_count",
        "full_node_inventory_count": inventory.get("count"),
        "full_node_passed": summaries["full_node_suite"]["passed"],
        "full_python_passed": summaries["full_python_suite"]["passed"],
        "capability_probe_tests_passed": summaries["capability_probe_tests"]["passed"],
        "new_failure_count": 0,
        "regression_baseline_attempt": "H03-0001",
        "status": "PASS",
        "suites": summaries,
    }


def required_check_evidence() -> dict[str, dict[str, Any]]:
    # Both required checks run through the single capability-probe harness; the
    # eighteen-case Node JUnit is split by testcase-name prefix and each part is
    # confirmed to contribute exactly its expected non-empty count against the
    # pinned case names.
    path = JUNIT_PATHS["capability_probe_tests"]
    root = ET.parse(path).getroot()
    names = tuple(str(case.get("name") or "") for case in root.findall(".//testcase"))
    if names != EXPECTED_HOOK_CASE_NAMES:
        raise SystemExit(f"capability-probe case identity drifted: {names}")
    if any(case.find("failure") is not None for case in root.findall(".//testcase")):
        raise SystemExit("capability-probe harness reported a failing case")
    checks: dict[str, dict[str, Any]] = {}
    for check, prefix in REQUIRED_CHECK_PREFIXES.items():
        matched = [name for name in names if name.startswith(prefix)]
        if len(matched) != REQUIRED_CHECK_COUNTS[check]:
            raise SystemExit(
                f"{check} did not contribute exactly "
                f"{REQUIRED_CHECK_COUNTS[check]} cases: {matched}"
            )
        checks[check] = {
            "status": "PASS",
            "test_count": len(matched),
            "case_names": matched,
        }
    return checks


def maturity_boundary() -> dict[str, Any]:
    # H04 supplies a bounded capability-probe module that projects supplied
    # observations into hash-bound HostCapabilityReport / PluginHealthReport
    # documents.  It performs no live host I/O (the module imports node:crypto and
    # node:util only, plus the sealed H01 gateway canonicalizer) and registers no
    # runtime hook runner.  The plugin manifest must carry no hooks key and no
    # capabilities, and no dist/hook-runner.mjs may exist: runtime hook execution
    # is later-package scope (H05/H06/X01/G06) and is correctly not claimed
    # executable.  This is a specified-not-implemented boundary, not a weakening.
    assert_hashes({PLUGIN_MANIFEST: EXPECTED_MANIFEST_HASH})
    manifest = read_json(ROOT / PLUGIN_MANIFEST)
    interface = manifest.get("interface")
    if not isinstance(interface, dict):
        raise SystemExit("plugin manifest interface is missing")
    if "hooks" in manifest:
        raise SystemExit("plugin manifest must not register runtime hooks at H04")
    if interface.get("capabilities") != []:
        raise SystemExit("plugin manifest capabilities must be empty at H04")
    if (ROOT / HOOK_RUNNER).exists():
        raise SystemExit("H04 must not claim an implemented dist/hook-runner.mjs")
    return {
        "bounded_observation_projection_only": True,
        "evolution_holdout_observability_owner": "H05",
        "hook_disabled_hosted_tool_integration_owner": "H06",
        "hook_runner_exists": False,
        "hosted_tool_interception_claimed": False,
        "live_cross_host_discovery_adapter_claimed": False,
        "observed_hook_coverage_is_exhaustive_enforcement": False,
        "plugin_manifest": PLUGIN_MANIFEST,
        "plugin_manifest_capabilities": [],
        "plugin_manifest_hooks_registered": False,
        "plugin_manifest_sha256": sha256_id(ROOT / PLUGIN_MANIFEST),
        "runtime_hook_runner_registration_claimed": False,
        "runtime_integration_owner": "X01/G06",
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
    # H04 depends on H02 and H03 (manifest depends_on: [H02, H03]).  Both sealed
    # attempts are bound here as build dependencies, pinned by content-hash and by
    # their sealed core/final evidence ids.
    assert_hashes(EXPECTED_DEPENDENCY_HASHES)
    return {
        "attempt_id": ATTEMPT_ID,
        "dependencies": {
            "H02": _sealed_dependency("H02", "H02-0001", "E0345", "E0346"),
            "H03": _sealed_dependency("H03", "H03-0001", "E0347", "E0348"),
        },
        "dependency_note": (
            "H04 depends on H02 and H03; both sealed attempts are build "
            "dependencies pinned by content-hash and sealed core/final evidence "
            "ids. The live ledger frontier advances under concurrent sealing; the "
            "parent reconciles the exact frontier when it fills the ledger pins at "
            "seal time."
        ),
        "next_action": "SEAL_H04_0001_THEN_RECOMPUTE_DAG",
        "status": "PASS",
    }


def write_scope_verification() -> dict[str, Any]:
    # H04's manifest write scope is the bounded capability-probe module and the
    # two compatibility test suites that are its required checks. The runner
    # authors write-scope-verification.json over them; the builder re-derives the
    # hashes live, pins them, and confirms the recorded receipt is exactly those
    # bytes. There is no separate authority blueprint (the suites are the
    # product's own checks), and H04 edits nothing else, so every mutation counter
    # is zero.
    assert_hashes(EXPECTED_PRODUCT_HASHES)
    for relative in PRODUCT_FILES:
        product = (ROOT / relative).read_bytes()
        if product.startswith(b"\xef\xbb\xbf") or b"\x00" in product:
            raise SystemExit(f"invalid encoding marker in product file: {relative}")
        if "�" in product.decode("utf-8"):
            raise SystemExit(f"replacement character in product file: {relative}")
    live_hashes = {
        relative: "sha256:" + sha256(ROOT / relative)
        for relative in sorted(PRODUCT_FILES)
    }
    pinned = {
        relative: "sha256:" + digest
        for relative, digest in EXPECTED_PRODUCT_HASHES.items()
    }
    if live_hashes != pinned:
        raise SystemExit("write-scope product hashes drifted from the pinned set")
    record = read_json(ATTEMPT / "write-scope-verification.json")
    if (
        record.get("attempt_id") != ATTEMPT_ID
        or record.get("status") != "PASS"
        or record.get("approved_scope") != APPROVED_SCOPE
        or record.get("product_file_hashes") != live_hashes
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
    regression: dict[str, Any],
    required_checks: dict[str, dict[str, Any]],
    boundary: dict[str, Any],
) -> dict[str, Any]:
    suites = regression["suites"]
    return {
        "attempt_id": ATTEMPT_ID,
        "attestation_scope": {
            "capability_probe_module": PRODUCT_FILES[0],
            "compatibility_test_suites": list(PRODUCT_FILES[1:]),
            "bounded_observation_projection": (
                "H04 authors a capability-probe module that projects supplied "
                "observations into hash-bound HostCapabilityReport and "
                "PluginHealthReport documents and attests it with the two "
                "compatibility suites; it declares no runtime executable"
            ),
        },
        "exit_criteria": {
            "unsupported_coverage_explicit": {
                "mechanism": (
                    "hook_feature_probe_test asserts missing observations fall to "
                    "UNKNOWN rather than optimistic support, empty event/tool "
                    "scopes never prove FULL, unobserved hosted tool paths stay "
                    "explicit, and unsupported/forged/hostile inputs fail closed"
                ),
                "status": "PASS_AT_BOUNDED_OBSERVATION_PROJECTION_BOUNDARY",
            },
            "changed_hooks_require_retrust": {
                "mechanism": (
                    "hook_feature_probe_test asserts changed active hook bytes, "
                    "removed hook hashes, and disabled-but-changed hooks each force "
                    "exact re-trust (state UNKNOWN, HOOK_RETRUST_REQUIRED), and "
                    "hook_degraded_mode_test asserts re-trust debt is visible in "
                    "health and cannot be masked as FULL"
                ),
                "status": "PASS_AT_HOOK_TRUST_BOUNDARY",
            },
        },
        "maturity_boundary": boundary,
        "required_checks": {
            "independent_review": {
                "evidence": (
                    "review.md (author: the bounded H04 implementation agent that "
                    "authored the capability-probe module and its two compatibility "
                    "suites; reviewer: the independent seal-prep session, which did "
                    "not author this attempt; actor_independence between author and "
                    "reviewer holds, external certification does not)"
                ),
                "status": "PASS",
            },
            **{
                name: {"status": "PASS", "test_count": row["test_count"]}
                for name, row in required_checks.items()
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
                f"{ATTEMPT_DIR}/build_h04_0001_evidence.py",
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
        "# H04-0001 independent review of bounded-agent work\n"
        "\n"
        "- Author: the bounded implementation agent(s) (H04 maker) that authored\n"
        "  the capability-probe module\n"
        "  packages/plugin-host/src/capability-probe/capability-probe.mjs and its\n"
        "  two compatibility test suites\n"
        "  tests/compatibility/hooks/hook-feature-probe.test.mjs and\n"
        "  hook-degraded-mode.test.mjs, plus the Node contract harness\n"
        "  h04-capability-probe-tests.mjs under\n"
        "  artifacts/work_packages/H04/attempts/0001/. Reviewer: the seal-prep\n"
        "  session, a distinct actor that did not author this attempt. Author/\n"
        "  reviewer separation holds (actor_independence=true); external\n"
        "  actor-independent certification does not.\n"
        "- Mode: INDEPENDENT_REVIEW_OF_BOUNDED_AGENT_WORK. Blocking findings: 0.\n"
        "- Scope: the manifest write scope is\n"
        "  packages/plugin-host/src/capability-probe/** and\n"
        "  tests/compatibility/hooks/** plus artifacts/work_packages/H04/**. The\n"
        "  three product files are hash-pinned and decode as BOM-less UTF-8. No\n"
        "  src, schema, manifest, harness outside H04, or .rah/ state was touched,\n"
        "  and the mutation counters are all zero.\n"
        "- Exit criterion 1 - unsupported coverage explicit: VERIFIED.\n"
        "  hook_feature_probe_test (11/11) asserts missing observations fall to\n"
        "  UNKNOWN rather than optimistic support, empty hook-event and tool\n"
        "  scopes never prove FULL, unobserved hosted tool paths stay explicit,\n"
        "  and unsupported claims, forged hook-trust, undeclared capabilities, and\n"
        "  hostile/non-plain inputs (proxies, accessors, sparse arrays) each fail\n"
        "  closed. Reports are schema-shaped, hash-bound, and deeply frozen.\n"
        "- Exit criterion 2 - changed hooks require re-trust: VERIFIED.\n"
        "  hook_feature_probe_test asserts changed active hook bytes, removed hook\n"
        "  hashes, and disabled-but-changed hooks each force exact re-trust\n"
        "  (state UNKNOWN, HOOK_RETRUST_REQUIRED, stale/untrusted hash detail), and\n"
        "  hook_degraded_mode_test (7/7) asserts re-trust debt is visible in the\n"
        "  PluginHealthReport and cannot be masked as FULL, that the strongest\n"
        "  declared degraded mode (DEGRADED/READ_ONLY/SAFE_MODE) is selected, and\n"
        "  that a required capability without a declared fallback is BLOCKED.\n"
        "- Maturity boundary (the crux, honestly disclosed). H04 supplies a\n"
        "  BOUNDED OBSERVATION PROJECTION only. The capability-probe module is a\n"
        "  pure function over supplied observations (it imports node:crypto and\n"
        "  node:util and the sealed H01 gateway canonicalizer; it performs no\n"
        "  node:fs or child_process live host I/O). The plugin manifest\n"
        "  plugins/epistemic-foundry/.codex-plugin/plugin.json carries no hooks key\n"
        "  and an empty interface.capabilities, and\n"
        "  plugins/epistemic-foundry/dist/hook-runner.mjs is ABSENT. Live\n"
        "  cross-host discovery, runtime hook-runner registration, and hosted-tool\n"
        "  interception are H05/H06/X01/G06 scope and are correctly NOT claimed\n"
        "  executable: this is a specified-not-yet-implemented posture, not a\n"
        "  weakening of the gate.\n"
        "- Gates at review time: capability-probe-tests 18/18\n"
        "  (hook_feature_probe_test 11/11, hook_degraded_mode_test 7/7), the full\n"
        "  Python suite green, the live full Node suite green with zero failures,\n"
        "  and git diff --check clean. H04 depends on H02 and H03; both sealed\n"
        "  PASS attempts are bound as build dependencies.\n"
        "- Residual limitations: H04 projects bounded observations and attests\n"
        "  its trust/coverage/degraded-mode logic only. It does not claim a live\n"
        "  cross-host discovery adapter, exhaustive enforcement from observed\n"
        "  hooks, runtime hook-runner registration, hosted-tool interception,\n"
        "  evolution/holdout observability, packaged runtime integration, or\n"
        "  release readiness, and this review is not external actor-independent\n"
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
            "path": f"{ATTEMPT_DIR}/{name}",
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in sorted(set(output_names))
    ]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "H04_CAPABILITY_PROBE_TRUST_AND_DEGRADED_MODE",
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
        "maturity_boundary": verification["maturity_boundary"],
        "next_package": "RECOMPUTE_DAG",
        "not_claimed": [
            "a live cross-host feature-discovery adapter or runtime hook-runner registration: H04 projects supplied observations into hash-bound HostCapabilityReport and PluginHealthReport documents and adds no hooks key, capability, or dist/hook-runner.mjs",
            "exhaustive runtime enforcement from observed hook coverage, or hosted-tool interception",
            "evolution/holdout observability (H05) or hook-disabled hosted-tool integration (H06)",
            "any runtime hook execution, effect-receipt emission, or packaged runtime integration",
            "any product-maturity, runtime-executability or release readiness of the v4 plugin or ShinkaEvolve integration",
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
                "Author/reviewer separation holds (the bounded H04 implementation "
                "agent authored, the seal-prep session reviewed); external "
                "actor-independent certification does not."
            ),
            "blocking_finding_count": 0,
            "mode": "INDEPENDENT_REVIEW_OF_BOUNDED_AGENT_WORK",
            "status": "PASS",
        },
        "status": "PASS",
        "work_package_id": WORK_PACKAGE_ID,
        "write_scope": write_scope,
    }
    if rah_state is not None:
        report["rah_state"] = rah_state
    else:
        # Seal-prep deliverable state: the attempt is fully verified and ready
        # for the parent to perform the actual ledger seal, but this session
        # binds no rah_state itself.  These two flags disappear once the parent
        # binds rah_state, leaving the sealed report clean.
        report["ready_for_seal"] = True
        report["seal_prep_only"] = True
    return report


def _summary() -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "completion_ready": False,
        "next_action": "SEAL_H04_0001_THEN_RECOMPUTE_DAG",
        "package_status": "PASS",
        "status": "PASS",
    }


def build() -> dict[str, Any]:
    for name in RUN_RESULTS:
        check_run(name)
    assert_hashes(EXPECTED_SRC_HASHES)
    normalize_junits()
    regression = regression_evidence()
    required_checks = required_check_evidence()
    boundary = maturity_boundary()
    dependencies = dependency_status()
    write_scope = write_scope_verification()
    verification = package_verification(regression, required_checks, boundary)
    write_json("dependency-status.json", dependencies)
    write_json("h04-verification.json", verification)
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
        raise SystemExit("H04-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "h04-verification.json")
    report = report_document(
        regression, dependencies, write_scope, verification, rah_state=rah_state
    )
    write_json("report.json", report)


def verify() -> dict[str, Any]:
    for name in RUN_RESULTS:
        check_run(name)
    assert_hashes(EXPECTED_SRC_HASHES)
    normalize_junits()
    regression = regression_evidence()
    required_checks = required_check_evidence()
    boundary = maturity_boundary()
    assert_hashes(EXPECTED_DEPENDENCY_HASHES)
    stored = read_json(ATTEMPT / "report.json")
    dependencies = read_json(ATTEMPT / "dependency-status.json")
    write_scope_live = write_scope_verification()
    write_scope = read_json(ATTEMPT / "write-scope-verification.json")
    if write_scope_live != write_scope:
        raise SystemExit("write-scope verification drifted from the sealed record")
    verification = read_json(ATTEMPT / "h04-verification.json")
    if verification != package_verification(regression, required_checks, boundary):
        raise SystemExit("stored H04-0001 verification is not the deterministic document")
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
        raise SystemExit("stored H04-0001 report is not the deterministic document")
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
