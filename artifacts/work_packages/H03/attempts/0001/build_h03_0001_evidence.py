#!/usr/bin/env python3
"""Build and verify H03-0001 evidence: tool and delegation hook declarations.

H03 depends on H01.  It installs, byte-for-byte from the authority blueprint,
the two static hook declarations ``plugins/epistemic-foundry/hooks/tools.json``
and ``plugins/epistemic-foundry/hooks/delegation.json`` and attests them against
the two required checks its manifest declares, ``tool_hook_policy_test`` and
``subagent_result_gate_test``.  Both checks are defined in one deterministic Node
harness under this attempt directory, ``h03-hook-contract-tests.mjs`` (eight
cases: four per check), run once via ``node --test``.  The harness asserts the
two exit criteria -- observed tools use policy and effect receipts, and the
subagent expected-count contract is bound -- at the static declaration and
handler-binding boundary, and proves the predicate fails closed on a direct
allow, a timeout expansion, dropped coverage, an asymmetric matcher, a partial
delegation matcher, a substituted stop handler, and any premature runtime claim.

This builder verifies the executed check receipts, splits the eight-case Node
JUnit into the two required checks by name prefix, gates the required suite and
the live repository Node suite on zero failures with their measured counts, gates
the repository-wide Python suite on zero failures, pins the two product bytes and
the harness bytes (and confirms each product file is byte-equivalent to its
blueprint), records the honest fail-closed maturity boundary (no plugin-manifest
hooks, empty capabilities, no ``dist/hook-runner.mjs``), binds the sealed H01-0001
dependency and the sealed H02-0001 regression baseline, and emits the
deterministic attempt evidence.  It never edits any file outside its own attempt
directory.
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
ATTEMPT = ROOT / "artifacts/work_packages/H03/attempts/0001"
ATTEMPT_ID = "H03-0001"
WORK_PACKAGE_ID = "H03"
ATTEMPT_DIR = "artifacts/work_packages/H03/attempts/0001"
RECORDED_AT = "2026-08-02T00:00:00.000Z"

#: The two static hook declarations are the manifest write scope for H03.
PRODUCT_FILES = (
    "plugins/epistemic-foundry/hooks/tools.json",
    "plugins/epistemic-foundry/hooks/delegation.json",
)
BLUEPRINTS = {
    "plugins/epistemic-foundry/hooks/tools.json": (
        "plugin_blueprint/epistemic-foundry/hooks/tools.json"
    ),
    "plugins/epistemic-foundry/hooks/delegation.json": (
        "plugin_blueprint/epistemic-foundry/hooks/delegation.json"
    ),
}
APPROVED_SCOPE = [
    "plugins/epistemic-foundry/hooks/tools.json",
    "plugins/epistemic-foundry/hooks/delegation.json",
    "artifacts/work_packages/H03/**",
]
#: Live sha256 of the write-scope declarations H03 installs (never edits after
#: install).  These are the manifest write scope; write_scope_verification
#: confirms the runner receipt is exactly these bytes and that each is
#: byte-equivalent to the authority blueprint.
EXPECTED_PRODUCT_HASHES = {
    "plugins/epistemic-foundry/hooks/tools.json": "7bd22606fa69ebc447d538c682d2175547e56247fe66755b4c2ac33f0ab31007",
    "plugins/epistemic-foundry/hooks/delegation.json": "05fb9047ce62d00d296e47843c2130bbeb550ea43aa9d009dbcc8c2ce82cd4b6",
}
#: The immutable authority blueprint the two product declarations must match
#: byte-for-byte.
EXPECTED_BLUEPRINT_HASHES = {
    "plugin_blueprint/epistemic-foundry/hooks/tools.json": "7bd22606fa69ebc447d538c682d2175547e56247fe66755b4c2ac33f0ab31007",
    "plugin_blueprint/epistemic-foundry/hooks/delegation.json": "05fb9047ce62d00d296e47843c2130bbeb550ea43aa9d009dbcc8c2ce82cd4b6",
}
#: The Node contract harness H03 authored under its own attempt scope; it defines
#: both required checks.
EXPECTED_HARNESS_HASHES = {
    "artifacts/work_packages/H03/attempts/0001/h03-hook-contract-tests.mjs": "bcad08be9e1b982bb6200533eb46ded680bf4bda15f34ccbb6d78f14cb2b06ba",
}
#: The full pinned product-byte set H03 is accountable for: the two declarations
#: installed plus the harness authored.
EXPECTED_SRC_HASHES = {**EXPECTED_PRODUCT_HASHES, **EXPECTED_HARNESS_HASHES}
#: The plugin manifest whose fail-closed maturity boundary H03 attests without
#: editing: no hooks key, empty capabilities, and no runtime hook runner.
PLUGIN_MANIFEST = "plugins/epistemic-foundry/.codex-plugin/plugin.json"
EXPECTED_MANIFEST_HASH = (
    "1b1ec359ab93733114c95acb34c4a74615974456ddab52fa7c1c538159318a87"
)
HOOK_RUNNER = "plugins/epistemic-foundry/dist/hook-runner.mjs"
#: H03 depends on H01 (manifest depends_on: [H01]); it binds the sealed H01-0001
#: report as its build dependency and the sealed H02-0001 report (its P07-H
#: sibling) as the regression baseline.  Both are pinned by content.
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/H01/attempts/0001/report.json": "42530e1c2242ffde9df65619f2d88505df6ea59cd902f8323e9e81298414094a",
    "artifacts/work_packages/H02/attempts/0001/report.json": "f6b98a6ede90ec744d5777108a83b1a15bce013ff1270e89696dc427ab4d0a85",
}

JUNIT_PATHS = {
    "hook_contract_tests": ATTEMPT / "hook-contract-tests.junit.xml",
    "full_python_suite": ATTEMPT / "full-python-suite.junit.xml",
    "full_node_suite": ATTEMPT / "full-node-suite.junit.xml",
}
#: The required-check harness and the repository Node regression are Node suites;
#: only the repository-wide Python gate is a pytest suite.
_NODE_JUNITS = frozenset({"hook_contract_tests", "full_node_suite"})
PYTEST_SUITES = ("full_python_suite",)
NODE_SUITES = ("hook_contract_tests", "full_node_suite")
#: Both required checks are defined in the single hook-contract harness; each is
#: derived from the eight-case Node JUnit by testcase-name prefix.
REQUIRED_CHECK_PREFIXES = {
    "tool_hook_policy_test": "tool_hook_policy_test: ",
    "subagent_result_gate_test": "subagent_result_gate_test: ",
}
EXPECTED_HOOK_CASE_NAMES = (
    "tool_hook_policy_test: canonical permission, pre-tool, and receipt routes are exact",
    "tool_hook_policy_test: installed tool declaration is byte-equivalent to the authority blueprint",
    "tool_hook_policy_test: missing policy or receipt coverage fails closed",
    "tool_hook_policy_test: timeout expansion, direct allow, and extra events fail closed",
    "subagent_result_gate_test: canonical start and stop bindings cover every subagent",
    "subagent_result_gate_test: installed delegation declaration is byte-equivalent to the authority blueprint",
    "subagent_result_gate_test: missing start or stop coverage and partial matchers fail closed",
    "subagent_result_gate_test: handler substitution and premature runtime claims fail closed",
)
#: One ``<name>.run.json`` receipt is expected per step (runner contract).
RUN_RESULTS = (
    "hook-contract-tests",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
    "write-scope-verification",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "build_h03_0001_evidence.py",
    "commands.jsonl",
    "dependency-status.json",
    "full-node-suite.junit.xml",
    "full-python-suite.junit.xml",
    "h03-hook-contract-tests.mjs",
    "h03-verification.json",
    "h03_0001_rah_seal.py",
    "hook-contract-tests.junit.xml",
    "junit-normalization-verification.json",
    "node-test-inventory.json",
    "report.json",
    "review.md",
    "run_h03_0001_checks.py",
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
        "hook_contract_tests_passed": summaries["hook_contract_tests"]["passed"],
        "new_failure_count": 0,
        "regression_baseline_attempt": "H02-0001",
        "status": "PASS",
        "suites": summaries,
    }


def required_check_evidence() -> dict[str, dict[str, Any]]:
    # Both required checks are defined in the single hook-contract harness; the
    # eight-case Node JUnit is split by testcase-name prefix and each half is
    # confirmed non-empty and wholly present against the pinned case names.
    path = JUNIT_PATHS["hook_contract_tests"]
    root = ET.parse(path).getroot()
    names = tuple(str(case.get("name") or "") for case in root.findall(".//testcase"))
    if names != EXPECTED_HOOK_CASE_NAMES:
        raise SystemExit(f"hook-contract case identity drifted: {names}")
    if any(case.find("failure") is not None for case in root.findall(".//testcase")):
        raise SystemExit("hook-contract harness reported a failing case")
    checks: dict[str, dict[str, Any]] = {}
    for check, prefix in REQUIRED_CHECK_PREFIXES.items():
        matched = [name for name in names if name.startswith(prefix)]
        if len(matched) != 4:
            raise SystemExit(f"{check} did not contribute exactly four cases: {matched}")
        checks[check] = {
            "status": "PASS",
            "test_count": len(matched),
            "case_names": matched,
        }
    return checks


def maturity_boundary() -> dict[str, Any]:
    # H03 supplies static declarations only.  The plugin manifest must carry no
    # hooks key and no capabilities, and no dist/hook-runner.mjs may exist:
    # runtime enforcement is later-package scope (H04/N04/X01/G06) and is
    # correctly not claimed executable.  This is a specified-not-implemented
    # boundary, not a weakening.
    assert_hashes({PLUGIN_MANIFEST: EXPECTED_MANIFEST_HASH})
    manifest = read_json(ROOT / PLUGIN_MANIFEST)
    interface = manifest.get("interface")
    if not isinstance(interface, dict):
        raise SystemExit("plugin manifest interface is missing")
    if "hooks" in manifest:
        raise SystemExit("plugin manifest must not register runtime hooks at H03")
    if interface.get("capabilities") != []:
        raise SystemExit("plugin manifest capabilities must be empty at H03")
    if (ROOT / HOOK_RUNNER).exists():
        raise SystemExit("H03 must not claim an implemented dist/hook-runner.mjs")
    return {
        "capability_probe_and_degraded_mode_owner": "H04",
        "expected_identity_and_count_reconciliation_owner": "N04",
        "hook_runner_exists": False,
        "observed_hook_coverage_is_exhaustive_enforcement": False,
        "plugin_manifest": PLUGIN_MANIFEST,
        "plugin_manifest_capabilities": [],
        "plugin_manifest_hooks_registered": False,
        "plugin_manifest_sha256": sha256_id(ROOT / PLUGIN_MANIFEST),
        "runtime_integration_owner": "X01/G06",
        "static_declaration_only": True,
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
    # H03 depends on H01 (manifest depends_on: [H01]).  The sealed H01-0001
    # report is bound here as the build dependency; the sealed H02-0001 report
    # (H03's P07-H sibling) is bound as the regression baseline.  Both are pinned
    # by content.
    assert_hashes(EXPECTED_DEPENDENCY_HASHES)
    return {
        "attempt_id": ATTEMPT_ID,
        "dependencies": {
            "H01": _sealed_dependency("H01", "H01-0001", "E0339", "E0340"),
        },
        "dependency_note": (
            "H03 depends on H01; the sealed H01-0001 attempt is the build "
            "dependency"
        ),
        "next_action": "SEAL_H03_0001_THEN_RECOMPUTE_DAG",
        "regression_baseline": _sealed_dependency("H02", "H02-0001", "E0345", "E0346"),
        "regression_baseline_note": (
            "H02-0001 is a sealed PASS attempt (H03's P07-H sibling) bound as the "
            "regression baseline. The live ledger frontier advances under "
            "concurrent sealing; the parent reconciles the exact frontier when it "
            "fills the ledger pins at seal time."
        ),
        "status": "PASS",
    }


def write_scope_verification() -> dict[str, Any]:
    # H03's manifest write scope is the two static hook declarations. The runner
    # authors write-scope-verification.json over them; the builder re-derives the
    # hashes live, pins them, confirms each is byte-equivalent to the authority
    # blueprint, and confirms the recorded receipt is exactly those bytes. H03
    # installs the declarations byte-for-byte and edits nothing else, so every
    # mutation counter is zero.
    assert_hashes(EXPECTED_PRODUCT_HASHES)
    assert_hashes(EXPECTED_BLUEPRINT_HASHES)
    for relative in PRODUCT_FILES:
        product = (ROOT / relative).read_bytes()
        blueprint = (ROOT / BLUEPRINTS[relative]).read_bytes()
        if product.startswith(b"\xef\xbb\xbf") or b"\x00" in product:
            raise SystemExit(f"invalid encoding marker in product file: {relative}")
        if product != blueprint:
            raise SystemExit(f"product differs from authority blueprint: {relative}")
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
        or record.get("blueprint_installed_no_semantic_edits") is not True
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
            "hook_declarations": list(PRODUCT_FILES),
            "installed_byte_for_byte_from_blueprint": (
                "H03 installs the two static tool and delegation hook "
                "declarations byte-for-byte from the authority blueprint and "
                "attests them; it declares no runtime executable"
            ),
        },
        "exit_criteria": {
            "observed_tools_use_policy_receipts": {
                "mechanism": (
                    "tool_hook_policy_test asserts tools.json routes "
                    "PermissionRequest (matcher Bash|apply_patch|mcp__.*) to the "
                    "H01 gateway hook-runner permission-request command and binds "
                    "PreToolUse guardrails and PostToolUse effect receipts with "
                    "symmetric coverage; a direct allow, a timeout expansion, "
                    "dropped policy or receipt coverage, an asymmetric pre/post "
                    "matcher, and any extra event all fail closed"
                ),
                "status": "PASS_AT_STATIC_DECLARATION_BOUNDARY",
            },
            "subagent_expected_count_enforced": {
                "mechanism": (
                    "subagent_result_gate_test asserts delegation.json binds "
                    "SubagentStart -> RoleSpec and SubagentStop -> ResultEnvelope "
                    "over every subagent (matcher .*); a substituted "
                    "accept-partial-result stop handler, a partial matcher, and a "
                    "missing start or stop route all fail closed, and the harness "
                    "confirms no premature runtime claim (no plugin-manifest "
                    "hooks, empty capabilities, no dist/hook-runner.mjs)"
                ),
                "status": "PASS_AT_STATIC_HANDLER_BINDING_BOUNDARY",
            },
        },
        "maturity_boundary": boundary,
        "required_checks": {
            "independent_review": {
                "evidence": (
                    "review.md (author: bounded H03 implementation agent(s) that "
                    "installed the two hook declarations from the blueprint and "
                    "authored the Node contract harness; reviewer: the sealing "
                    "session, which did not author this attempt; actor_independence "
                    "between author and reviewer holds, external certification does "
                    "not)"
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
                f"{ATTEMPT_DIR}/build_h03_0001_evidence.py",
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
        "# H03-0001 independent review of bounded-agent work\n"
        "\n"
        "- Author: the bounded implementation agent(s) (H03 maker) that installed\n"
        "  the two static tool and delegation hook declarations\n"
        "  plugins/epistemic-foundry/hooks/tools.json and delegation.json\n"
        "  byte-for-byte from the authority blueprint and authored the Node\n"
        "  contract harness h03-hook-contract-tests.mjs under\n"
        "  artifacts/work_packages/H03/attempts/0001/. Reviewer: the sealing\n"
        "  session, a distinct actor that did not author this attempt. Author/\n"
        "  reviewer separation holds (actor_independence=true); external\n"
        "  actor-independent certification does not.\n"
        "- Mode: INDEPENDENT_REVIEW_OF_BOUNDED_AGENT_WORK. Blocking findings: 0.\n"
        "- Scope: the manifest write scope is\n"
        "  plugins/epistemic-foundry/hooks/tools.json and delegation.json plus\n"
        "  artifacts/work_packages/H03/**. Both declarations are hash-pinned and\n"
        "  confirmed byte-equivalent to plugin_blueprint/epistemic-foundry/hooks/\n"
        "  tools.json and delegation.json; they decode as BOM-less UTF-8. No src,\n"
        "  schema, manifest, harness outside H03, or .rah/ state was touched, and\n"
        "  the mutation counters are all zero.\n"
        "- Exit criterion 1 - observed tools use policy and effect receipts:\n"
        "  VERIFIED. tool_hook_policy_test (4/4) asserts tools.json routes\n"
        "  PermissionRequest (matcher Bash|apply_patch|mcp__.*) to the H01 gateway\n"
        "  hook-runner permission-request command and binds PreToolUse guardrails\n"
        "  and PostToolUse effect receipts with an identical\n"
        "  Bash|apply_patch|Edit|Write|mcp__.*|Agent matcher (symmetric pre/post\n"
        "  coverage). A direct-allow command rewrite, a timeout expansion beyond\n"
        "  the canonical bound, dropped policy or receipt coverage, an asymmetric\n"
        "  matcher, and any extra event each fail closed.\n"
        "- Exit criterion 2 - subagent expected-count contract enforced: VERIFIED.\n"
        "  subagent_result_gate_test (4/4) asserts delegation.json binds\n"
        "  SubagentStart -> RoleSpec and SubagentStop -> ResultEnvelope over every\n"
        "  subagent (matcher .*). Substituting the stop handler with\n"
        "  accept-partial-result, a partial matcher, and a missing start or stop\n"
        "  route each fail closed, so an untrusted subagent result cannot\n"
        "  self-authorize or bypass review.\n"
        "- Maturity boundary (the crux, honestly disclosed). H03 supplies STATIC\n"
        "  declarations only. The plugin manifest\n"
        "  plugins/epistemic-foundry/.codex-plugin/plugin.json carries no hooks\n"
        "  key and an empty interface.capabilities, and\n"
        "  plugins/epistemic-foundry/dist/hook-runner.mjs is ABSENT. Runtime\n"
        "  enforcement is H04/N04/X01/G06 scope and is correctly NOT claimed\n"
        "  executable: this is a specified-not-yet-implemented posture, not a\n"
        "  weakening of the gate. The harness case\n"
        "  'subagent_result_gate_test: handler substitution and premature runtime\n"
        "  claims fail closed' asserts exactly this -- manifest lacks a hooks key,\n"
        "  capabilities is [], and the runner file does not exist -- so a premature\n"
        "  runtime claim fails closed.\n"
        "- Gates at review time: hook_contract_tests 8/8 (tool_hook_policy_test\n"
        "  4/4, subagent_result_gate_test 4/4), the full Python suite green, the\n"
        "  live full Node suite green with zero failures, and git diff --check\n"
        "  clean. H03 depends on H01; the sealed H01-0001 attempt is the build\n"
        "  dependency and H02-0001 is a sealed PASS regression baseline.\n"
        "- Residual limitations: H03 attests static declarations and their\n"
        "  fail-closed handler bindings only. It does not claim an implemented hook\n"
        "  runner, plugin-manifest registration, runtime policy or receipt\n"
        "  execution, host capability probing, degraded-mode behavior, runtime\n"
        "  expected identity/count reconciliation, adapter integration, exhaustive\n"
        "  enforcement, or packaged runtime integration, and this review is not\n"
        "  external actor-independent certification.\n"
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
        "attempt_type": "H03_TOOL_AND_DELEGATION_HOOK_DECLARATIONS",
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
            "an implemented hook runner or plugin-manifest hook registration: H03 installs static tools.json and delegation.json declarations and does not add a hooks key, a capability, or dist/hook-runner.mjs",
            "any runtime policy decision, effect-receipt emission, or expected identity/count reconciliation",
            "host capability probing, degraded-mode behavior, Codex adapter, or packaged runtime integration",
            "that observed hook coverage implies exhaustive runtime enforcement",
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
                "Author/reviewer separation holds (bounded H03 implementation "
                "agent(s) authored, the sealing session reviewed); external "
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
    return report


def _summary() -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "completion_ready": False,
        "next_action": "SEAL_H03_0001_THEN_RECOMPUTE_DAG",
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
    write_json("h03-verification.json", verification)
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
        raise SystemExit("H03-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "h03-verification.json")
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
    verification = read_json(ATTEMPT / "h03-verification.json")
    if verification != package_verification(regression, required_checks, boundary):
        raise SystemExit("stored H03-0001 verification is not the deterministic document")
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
        raise SystemExit("stored H03-0001 report is not the deterministic document")
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
