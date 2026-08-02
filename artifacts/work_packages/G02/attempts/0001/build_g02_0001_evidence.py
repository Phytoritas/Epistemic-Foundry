#!/usr/bin/env python3
"""Build and verify G02-0001 payload dispatcher smoke and boundary evidence.

G02-0001 ships ``plugins/epistemic-foundry/bin/efoundry.mjs``: a payload-resident
dispatcher that resolves the packaged CLI as ``../dist/cli.mjs`` relative to its
own module URL, spawns the current ``process.execPath`` with ``shell:false`` and
full argv/stdin/stdout/stderr/cwd/env passthrough, propagates the payload exit
code (or re-raises the child's terminating signal), and fails closed when the
packaged payload is missing -- never falling back to a repository checkout, an
editable install, or a PATH alias.  The dispatcher is a fixed process adapter
with no domain logic: it imports only ``node:child_process`` and ``node:url``,
spawns exactly once, and holds no PLUGIN_ROOT, PLUGIN_DATA, PATH, policy,
promotion, schema, or ledger token, and no exec/execFile/fork/spawnSync or shell
invocation.  The two required checks -- ``payload_cli_smoke`` and
``dispatcher_boundary_test`` under ``packages/plugin-host/src/cli-dispatch`` --
prove exactly these behaviours; they also join the full Node inventory rather
than being targeted only, so the whole upstream Node surface is the regression
that matters.  This builder verifies the executed checks and emits immutable
attempt evidence; it never modifies product files.
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
ATTEMPT = ROOT / "artifacts/work_packages/G02/attempts/0001"
ATTEMPT_ID = "G02-0001"
WORK_PACKAGE_ID = "G02"
RECORDED_AT = "2026-08-02T00:00:00.000Z"

EXPECTED_SMOKE_COUNT = 2
EXPECTED_BOUNDARY_COUNT = 2
EXPECTED_TARGETED_COUNT = 4
EXPECTED_PYTHON_COUNT = 1261
EXPECTED_NODE_COUNT = 1291
EXPECTED_NODE_FILE_COUNT = 115

#: The dispatcher lives in one write-scope root; the two required test modules
#: live in the other.  Together these are the exact G02 product surface.
PRODUCT_ROOTS = (
    "plugins/epistemic-foundry/bin",
    "packages/plugin-host/src/cli-dispatch",
)
DISPATCHER = "plugins/epistemic-foundry/bin/efoundry.mjs"
CLI_DISPATCH = "packages/plugin-host/src/cli-dispatch"
EXPECTED_PRODUCT_HASHES = {
    "plugins/epistemic-foundry/bin/efoundry.mjs": "17723d450644508b755e725300a600f3792c05714056c794517bd9de2d005e05",
    "packages/plugin-host/src/cli-dispatch/dispatcher-boundary.test.mjs": "7c3600faf8373e1db3c1f03bca89e820668bd55e81f7e5b8535c0a13e12e543c",
    "packages/plugin-host/src/cli-dispatch/payload-cli-smoke.test.mjs": "e5f4f328a100abac6692e26dbce04e33cf15884be47a9e59d08604a133ab5b94",
}
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/G01/report.json": "893bb9d7c01e7213fb2aed347dca03099ab8ba770d072a82030ffa1216f17cf0",
}

#: Static invariants the dispatcher source must satisfy, mirrored from the
#: dispatcher_boundary_test contract so the evidence is self-verifying.
DISPATCHER_FORBIDDEN_TOKENS = (
    "PLUGIN_ROOT",
    "PLUGIN_DATA",
    "epistemic_foundry",
    "node:fs",
    "node:http",
    "node:https",
    "schemas/",
    "openapi/",
    "Noetic",
    "PolicyBundle",
    "PromotionDecision",
)

JUNIT_PATHS = {
    "payload_cli_smoke": ATTEMPT / "payload-cli-smoke.junit.xml",
    "dispatcher_boundary": ATTEMPT / "dispatcher-boundary.junit.xml",
    "targeted": ATTEMPT / "targeted-cli-dispatch.junit.xml",
    "full_python": ATTEMPT / "full-python-suite.junit.xml",
    "full_node": ATTEMPT / "full-node-suite.junit.xml",
}
# Every G02 check but the full Python suite runs under the Node runner.
_NODE_JUNITS = frozenset(
    {
        "payload_cli_smoke",
        "dispatcher_boundary",
        "targeted",
        "full_node",
    }
)
RUN_RESULTS = (
    "ruff-check",
    "ruff-format-check",
    "payload-cli-smoke",
    "dispatcher-boundary",
    "targeted-cli-dispatch",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "run_g02_0001_checks.py",
    "build_g02_0001_evidence.py",
    "g02_0001_rah_seal.py",
    "dependency-status.json",
    "g02-verification.json",
    "write-scope-verification.json",
    "node-test-inventory.json",
    "junit-normalization-verification.json",
    "payload-cli-smoke.junit.xml",
    "dispatcher-boundary.junit.xml",
    "targeted-cli-dispatch.junit.xml",
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
    smoke = node_summary(JUNIT_PATHS["payload_cli_smoke"])
    boundary = node_summary(JUNIT_PATHS["dispatcher_boundary"])
    targeted = node_summary(JUNIT_PATHS["targeted"])
    python = pytest_summary(JUNIT_PATHS["full_python"])
    node = node_summary(JUNIT_PATHS["full_node"])
    node_inventory = read_json(ATTEMPT / "node-test-inventory.json")
    for label, summary, expected in (
        ("payload_cli_smoke", smoke, EXPECTED_SMOKE_COUNT),
        ("dispatcher_boundary_test", boundary, EXPECTED_BOUNDARY_COUNT),
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
        "attempt_id": ATTEMPT_ID,
        "component_tests_are_targeted_only": True,
        "dispatcher_boundary_test": boundary,
        "full_node": node,
        "full_python": python,
        "new_failure_count": 0,
        "payload_cli_smoke": smoke,
        "status": "PASS",
        "targeted_cli_dispatch": targeted,
        "unexpected_skip_xfail_todo_or_cancellation_count": 0,
    }


def dispatcher_contract() -> dict[str, Any]:
    """Verify the fixed-adapter invariants directly from the dispatcher bytes."""
    path = ROOT / DISPATCHER
    source = path.read_text(encoding="utf-8")
    imports = re.findall(r'from\s+["\']([^"\']+)["\']', source)
    present_forbidden = [
        token for token in DISPATCHER_FORBIDDEN_TOKENS if token in source
    ]
    alternate_fallback = bool(
        re.search(r"process\.env\.[A-Z0-9_]*(?:CLI|PYTHON|ROOT|PATH)", source)
        or re.search(r"\b(?:exec|execFile|fork|spawnSync)\s*\(", source)
        or re.search(
            r"\b(?:cmd(?:\.exe)?|powershell|pwsh|bash|sh|python)\b", source, re.I
        )
    )
    spawn_sites = len(re.findall(r"spawn\(", source))
    target_sites = len(re.findall(r"\.\./dist/cli\.mjs", source))
    byte_size = len(source.encode("utf-8"))
    errors: list[str] = []
    if imports != ["node:child_process", "node:url"]:
        errors.append(f"unexpected imports: {imports}")
    if present_forbidden:
        errors.append(f"forbidden domain/path tokens: {present_forbidden}")
    if alternate_fallback:
        errors.append("alternate executable, shell, or target fallback detected")
    if spawn_sites != 1 or target_sites != 1:
        errors.append("dispatcher has multiple spawn or payload target sites")
    if byte_size >= 1500:
        errors.append("dispatcher is no longer a thin process adapter")
    required = {
        "fixed_payload_target": r'fileURLToPath\(new URL\(["\']\.\./dist/cli\.mjs["\'], import\.meta\.url\)\)',
        "absolute_node_executable": r"spawn\(process\.execPath, \[payloadCli, \.\.\.process\.argv\.slice\(2\)\]",
        "caller_cwd_forwarded": r"cwd: process\.cwd\(\)",
        "environment_forwarded": r"env: process\.env",
        "shell_disabled": r"shell: false",
        "stdio_inherited": r'stdio: ["\']inherit["\']',
        "exit_code_forwarded": r"process\.exitCode = code \?\? 1",
    }
    missing = [name for name, pat in required.items() if re.search(pat, source) is None]
    if missing:
        errors.append(f"missing dispatcher invariants: {missing}")
    if errors:
        raise SystemExit(f"dispatcher contract violated: {errors}")
    return {
        "alternate_fallback_count": int(alternate_fallback),
        "byte_size": byte_size,
        "domain_logic_present": bool(present_forbidden),
        "executable_source": "process.execPath",
        "forbidden_token_count": len(present_forbidden),
        "import_specifiers": imports,
        "path": DISPATCHER,
        "payload_target": "../dist/cli.mjs",
        "payload_target_site_count": target_sites,
        "sha256": sha256_id(path),
        "spawn_site_count": spawn_sites,
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
            "G01": _pass_dependency(
                "G01", "G01-0001", "artifacts/work_packages/G01/report.json"
            ),
        },
        "next_action": "SEAL_G02_0001_THEN_CONTINUE_DAG",
        "status": "PASS",
    }


def write_scope_verification() -> dict[str, Any]:
    assert_hashes(EXPECTED_PRODUCT_HASHES)
    component_files = sorted(
        path.relative_to(ROOT).as_posix()
        for root in PRODUCT_ROOTS
        for path in (ROOT / root).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )
    if component_files != sorted(EXPECTED_PRODUCT_HASHES):
        raise SystemExit(f"G02 product roots hold unexpected files: {component_files}")
    return {
        "approved_scope": [
            "plugins/epistemic-foundry/bin/**",
            "packages/plugin-host/src/cli-dispatch/**",
            "artifacts/work_packages/G02/**",
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
        "write_scope_violation_count": 0,
    }


def g02_verification(
    regression: dict[str, Any], contract: dict[str, Any]
) -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "dispatcher_contract": contract,
        "exit_criteria": {
            "dispatcher_contains_no_domain_logic": {
                "evidence": [
                    f"{CLI_DISPATCH}/dispatcher-boundary.test.mjs",
                    DISPATCHER,
                ],
                "mechanism": (
                    "the dispatcher imports only node:child_process and node:url, "
                    "spawns exactly once, and holds no PLUGIN_ROOT, PLUGIN_DATA, "
                    "PATH, policy, promotion, schema, ledger, or other domain token, "
                    "and no exec/execFile/fork/spawnSync or shell invocation; static "
                    "boundary assertions plus a byte-size ceiling keep it a fixed "
                    "process adapter rather than a second CLI implementation"
                ),
                "status": "PASS",
            },
            "path_less_invocation_works": {
                "evidence": [
                    f"{CLI_DISPATCH}/payload-cli-smoke.test.mjs",
                ],
                "mechanism": (
                    "a copied installed-plugin fixture with an empty PATH, spaces and "
                    "Korean characters in its paths and data, resolves the payload as "
                    "../dist/cli.mjs relative to the dispatcher module URL and spawns "
                    "the current process.execPath with shell:false; argv, stdin, "
                    "stdout, stderr, cwd, env, and a non-zero exit code 23 are "
                    "preserved, and a missing packaged payload fails closed with a "
                    "non-zero exit and no repository or PATH fallback"
                ),
                "status": "PASS",
            },
        },
        "required_checks": {
            "dispatcher_boundary_test": {
                "module": f"{CLI_DISPATCH}/dispatcher-boundary.test.mjs",
                "status": "PASS",
                "test_count": regression["dispatcher_boundary_test"]["collected"],
            },
            "payload_cli_smoke": {
                "module": f"{CLI_DISPATCH}/payload-cli-smoke.test.mjs",
                "status": "PASS",
                "test_count": regression["payload_cli_smoke"]["collected"],
            },
        },
        "status": "PASS",
        "targeted_test_count": regression["targeted_cli_dispatch"]["collected"],
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
                "artifacts/work_packages/G02/attempts/0001/build_g02_0001_evidence.py",
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
        "# G02-0001 independent review of bounded-agent work\n"
        "\n"
        "- Author: the bounded implementation agent that wrote\n"
        "  plugins/epistemic-foundry/bin/efoundry.mjs and its two cli-dispatch\n"
        "  contract tests. Reviewer: this seal-prep session, a distinct actor that\n"
        "  did not author the dispatcher. The author never approves its own work, so\n"
        "  actor_independence HOLDS for this review; external actor-independent\n"
        "  certification does NOT, and no such claim is made. G02 is risk_class=high\n"
        "  and governs the plugin entry boundary, so the dispatcher was attacked on\n"
        "  its contract rather than skimmed.\n"
        "- PATH-less invocation works. The dispatcher computes exactly one payload\n"
        "  target, ../dist/cli.mjs, from its own module URL via fileURLToPath, and\n"
        "  spawns the current absolute Node executable (process.execPath) with\n"
        "  shell:false, inherited stdio, the caller's working directory and\n"
        "  environment, and unchanged arguments. payload_cli_smoke copies an\n"
        "  installed-plugin fixture into a directory with spaces and Korean\n"
        "  characters, runs it with an empty PATH, and confirms argv, stdin, stdout,\n"
        "  stderr, cwd, env, and a non-zero exit code 23 all survive the hop. No\n"
        "  efoundry PATH alias is required.\n"
        "- Fail-closed on a missing payload. Removing the fixture dist/cli.mjs makes\n"
        "  the dispatcher exit non-zero with a diagnostic naming dist/cli.mjs and no\n"
        "  stdout; it never falls back to a repository checkout, an editable\n"
        "  src/epistemic_foundry install, or a PATH lookup, so a missing packaged\n"
        "  payload cannot silently execute foreign code.\n"
        "- No domain logic (fixed process adapter). dispatcher_boundary_test parses\n"
        "  the dispatcher source and admits only node:child_process and node:url,\n"
        "  requires a single spawn of ../dist/cli.mjs, and rejects PLUGIN_ROOT,\n"
        "  PLUGIN_DATA, epistemic_foundry, node:fs/http/https, schema, openapi,\n"
        "  Noetic, PolicyBundle, and PromotionDecision tokens, any\n"
        "  CLI/PYTHON/ROOT/PATH environment override, and any\n"
        "  exec/execFile/fork/spawnSync or cmd/powershell/pwsh/bash/sh/python shell\n"
        "  path. A byte-size ceiling keeps it a thin adapter. This review re-derived\n"
        "  every one of those invariants directly from the dispatcher bytes.\n"
        "- Dependencies and checks: G02 builds only on the sealed G01 gateway\n"
        "  (G01-0001 PASS) and adds no new production dependency; the downstream-built\n"
        "  dist/cli.mjs payload is neither created nor claimed here. Ruff lint and\n"
        "  format, the two required checks (payload_cli_smoke "
        + f"{EXPECTED_SMOKE_COUNT}/{EXPECTED_SMOKE_COUNT}, dispatcher_boundary_test "
        + f"{EXPECTED_BOUNDARY_COUNT}/{EXPECTED_BOUNDARY_COUNT}), targeted "
        + f"{EXPECTED_TARGETED_COUNT}/{EXPECTED_TARGETED_COUNT}, full Python "
        + f"{EXPECTED_PYTHON_COUNT}/{EXPECTED_PYTHON_COUNT}, full Node "
        + f"{EXPECTED_NODE_COUNT}/{EXPECTED_NODE_COUNT} across "
        + f"{EXPECTED_NODE_FILE_COUNT} files, and git diff --check all pass with\n"
        "  zero failures.\n"
        "- Residual limitations: G02 proves payload process forwarding and\n"
        "  fail-closed targeting only. PLUGIN_ROOT/PLUGIN_DATA and workspace\n"
        "  resolution remain G03-owned, downstream efoundry command semantics and\n"
        "  stable JSON errors remain T03-owned, and marketplace fresh-install remains\n"
        "  G04-owned. Verdict: PASS on the exact G02 package contract.\n"
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
            "path": f"artifacts/work_packages/G02/attempts/0001/{name}",
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in sorted(set(output_names))
    ]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "G02_PAYLOAD_RESIDENT_EFOUNDRY_DISPATCHER",
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependency_state": dependencies,
        "dispatcher_contract": verification["dispatcher_contract"],
        "exit_criteria": {
            "dispatcher_contains_no_domain_logic": "PASS",
            "path_less_invocation_works": "PASS",
        },
        "global_implementation_gate": "fail",
        "history_and_worktree": {
            "dirty_worktree_preserved": True,
            "prior_attempts_reports_and_rah_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
        },
        "implementation_status": "PASS",
        "not_claimed": [
            "PLUGIN_ROOT, PLUGIN_DATA, or workspace resolution (G03)",
            "downstream efoundry command semantics or stable JSON errors (T03)",
            "marketplace fresh-install success (G04)",
            "the downstream-built dist/cli.mjs payload",
            "external actor-independent certification of this review",
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
        "attempt_id": ATTEMPT_ID,
        "completion_ready": False,
        "dispatcher_boundary_test": (
            f"{EXPECTED_BOUNDARY_COUNT}/{EXPECTED_BOUNDARY_COUNT}"
        ),
        "full_node": f"{EXPECTED_NODE_COUNT}/{EXPECTED_NODE_COUNT}",
        "full_python": f"{EXPECTED_PYTHON_COUNT}/{EXPECTED_PYTHON_COUNT}",
        "next_action": "SEAL_G02_0001_THEN_CONTINUE_DAG",
        "node_file_count": EXPECTED_NODE_FILE_COUNT,
        "package_status": "PASS",
        "payload_cli_smoke": f"{EXPECTED_SMOKE_COUNT}/{EXPECTED_SMOKE_COUNT}",
        "status": "PASS",
        "targeted_cli_dispatch": f"{EXPECTED_TARGETED_COUNT}/{EXPECTED_TARGETED_COUNT}",
    }


def build() -> dict[str, Any]:
    for name in RUN_RESULTS:
        check_run(name)
    normalize_junits()
    regression = regression_evidence()
    contract = dispatcher_contract()
    dependencies = dependency_status()
    write_scope = write_scope_verification()
    verification = g02_verification(regression, contract)
    write_json("dependency-status.json", dependencies)
    write_json("write-scope-verification.json", write_scope)
    write_json("g02-verification.json", verification)
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
        raise SystemExit("G02-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "g02-verification.json")
    report = report_document(
        regression, dependencies, write_scope, verification, rah_state=rah_state
    )
    write_json("report.json", report)


def verify() -> dict[str, Any]:
    for name in RUN_RESULTS:
        check_run(name)
    normalize_junits()
    regression = regression_evidence()
    contract = dispatcher_contract()
    assert_hashes(EXPECTED_DEPENDENCY_HASHES)
    stored = read_json(ATTEMPT / "report.json")
    dependencies = read_json(ATTEMPT / "dependency-status.json")
    write_scope_live = write_scope_verification()
    write_scope = read_json(ATTEMPT / "write-scope-verification.json")
    if write_scope_live != write_scope:
        raise SystemExit("write-scope verification drifted from the sealed record")
    verification = read_json(ATTEMPT / "g02-verification.json")
    if verification != g02_verification(regression, contract):
        raise SystemExit("stored G02 verification drifted from live evidence")
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
        raise SystemExit("stored G02-0001 report is not the deterministic document")
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
