#!/usr/bin/env python3
"""Build and verify G04-0001 local-marketplace fresh-install and uninstall evidence.

G04-0001 adds ``tests/install/local-marketplace/**``: an isolated lifecycle
harness and a single Node test that install the sealed ``epistemic-foundry``
plugin package shell from a disposable local marketplace into an isolated,
temporary ``CODEX_HOME`` using the real ``codex`` host, observe enable / disable
/ re-enable state, prove the installed cache is a byte-for-byte hash-equal copy
of the source that survives detaching the marketplace source, invoke the
absolute installed dispatcher from an empty ``PATH`` and empty cwd so no
repository checkout is assumed and no command success is fabricated, then remove
the plugin and marketplace and prove zero residue with the real user's
``~/.codex/config.toml`` and selector cache byte-identical before and after.
Both required checks -- ``fresh_install_test`` and ``clean_uninstall_test`` --
are asserted inside ``g04-lifecycle.test.mjs``, so a single 1/1 pass of that
module is the evidence for both, and that module also runs inside the full Node
regression.  This builder verifies the executed checks and emits immutable
attempt evidence; it never modifies product files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/G04/attempts/0001"
PACKAGE_ROOT = ROOT / "artifacts/work_packages/G04"
# The three manifest-declared evidence_artifacts live at the package root; the
# canonical bytes are authored in the attempt directory and projected up so the
# manifest paths always resolve to the current superseding document.
ROOT_PROJECTIONS = ("report.json", "commands.jsonl", "review.md")
ATTEMPT_ID = "G04-0001"
WORK_PACKAGE_ID = "G04"
RECORDED_AT = "2026-08-02T00:00:00.000Z"

EXPECTED_LIFECYCLE_COUNT = 1
EXPECTED_PYTHON_COUNT = 1261
EXPECTED_NODE_COUNT = 1291
EXPECTED_NODE_FILE_COUNT = 115

COMPONENT = "tests/install/local-marketplace"
LIFECYCLE_MODULE = f"{COMPONENT}/g04-lifecycle.test.mjs"
EXPECTED_PRODUCT_HASHES = {
    "tests/install/local-marketplace/g04-lifecycle.test.mjs": "4d93c3e2ae45c5208c9e16a59e85dd4179e2377ce917af1eaae5d66453c94cdf",
    "tests/install/local-marketplace/lifecycle-harness.mjs": "247a120aaf20c23f71a3e8d56340e5ad82fc4c0918b30577ba23b00e593eacf1",
}
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/G02/report.json": "0ff22dc37020f244390469edf77fd956150e6838c5717dc812d62c2c528a9e92",
    "artifacts/work_packages/G03/report.json": "48a55dec265fd3f0d7d740af221e44049cc1c5da6774241b49ce5787f03a6570",
}

JUNIT_PATHS = {
    "lifecycle": ATTEMPT / "lifecycle-test.junit.xml",
    "full_python": ATTEMPT / "full-python-suite.junit.xml",
    "full_node": ATTEMPT / "full-node-suite.junit.xml",
}
# Every G04 check but the full Python suite runs under the Node runner.
_NODE_JUNITS = frozenset({"lifecycle", "full_node"})
RUN_RESULTS = (
    "ruff-check",
    "ruff-format-check",
    "lifecycle-test",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "run_g04_0001_checks.py",
    "build_g04_0001_evidence.py",
    "g04_0001_rah_seal.py",
    "dependency-status.json",
    "g04-verification.json",
    "write-scope-verification.json",
    "node-test-inventory.json",
    "junit-normalization-verification.json",
    "lifecycle-test.junit.xml",
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
    lifecycle = node_summary(JUNIT_PATHS["lifecycle"])
    python = pytest_summary(JUNIT_PATHS["full_python"])
    node = node_summary(JUNIT_PATHS["full_node"])
    node_inventory = read_json(ATTEMPT / "node-test-inventory.json")
    _assert_node_gate("lifecycle_test", lifecycle, EXPECTED_LIFECYCLE_COUNT)
    lifecycle_names = [
        str(case.get("name") or "")
        for case in ET.parse(JUNIT_PATHS["lifecycle"]).getroot().findall(".//testcase")
    ]
    if lifecycle_names != [
        "fresh_install_test and clean_uninstall_test: isolated local marketplace lifecycle"
    ]:
        raise SystemExit(f"lifecycle module inventory changed: {lifecycle_names}")
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
    node_case_names = [
        str(case.get("name") or "")
        for case in ET.parse(JUNIT_PATHS["full_node"]).getroot().findall(".//testcase")
    ]
    if node_case_names.count(lifecycle_names[0]) != 1:
        raise SystemExit(
            "G04 lifecycle test is missing or duplicated in full Node suite"
        )
    return {
        "attempt_id": ATTEMPT_ID,
        "full_node": node,
        "full_python": python,
        "lifecycle_test": lifecycle,
        "lifecycle_test_is_targeted_and_full_node_member": True,
        "new_failure_count": 0,
        "status": "PASS",
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
            "G02": _pass_dependency(
                "G02", "G02-0001", "artifacts/work_packages/G02/report.json"
            ),
            "G03": _pass_dependency(
                "G03", "G03-0001", "artifacts/work_packages/G03/report.json"
            ),
        },
        "next_action": "SEAL_G04_0001_THEN_CONTINUE_DAG",
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
        raise SystemExit(
            f"local-marketplace component holds unexpected files: {component_files}"
        )
    return {
        "approved_scope": [f"{COMPONENT}/**", "artifacts/work_packages/G04/**"],
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


def g04_verification(regression: dict[str, Any]) -> dict[str, Any]:
    lifecycle_count = regression["lifecycle_test"]["collected"]
    return {
        "attempt_id": ATTEMPT_ID,
        "clean_uninstall_leaves_no_residue": {
            "installed_cache_absent_after_remove": True,
            "installed_selector_and_marketplace_removed_from_config": True,
            "marketplace_removed_and_absent_from_listing": True,
            "real_user_config_toml_byte_identical_before_and_after": True,
            "real_user_selector_cache_never_created": True,
            "residue_counts_are_zero": True,
            "temporary_root_torn_down_after_run": True,
        },
        "exit_criteria": {
            "install_enable_disable_uninstall": {
                "evidence": [LIFECYCLE_MODULE],
                "mechanism": (
                    "The real codex host adds the disposable local marketplace, "
                    "lists it as available without the personal marketplace, installs "
                    "the epistemic-foundry plugin into an isolated CODEX_HOME cache, "
                    "and reports the initial enabled, headless-disabled, and "
                    "re-enabled states; plugin remove and marketplace remove then "
                    "leave zero cache or config residue"
                ),
                "status": "PASS",
            },
            "repository_checkout_not_required": {
                "evidence": [LIFECYCLE_MODULE],
                "mechanism": (
                    "The installed cache is enumerated after the marketplace source "
                    "is detached, and the absolute installed dispatcher is invoked "
                    "from an empty cwd with an empty PATH; the fail-closed exit names "
                    "the installed dist target with zero repository-checkout fallback "
                    "and no fabricated command success"
                ),
                "status": "PASS",
            },
        },
        "fresh_install_is_functional": {
            "available_listing_excludes_personal_marketplace": True,
            "disable_then_reenable_state_observed_through_host": True,
            "installed_cache_is_byte_for_byte_hash_equal_copy_of_source": True,
            "installed_cache_survives_marketplace_source_detachment": True,
            "installed_manifest_valid_with_empty_capabilities": True,
            "no_repository_checkout_or_leftover_state_assumed": True,
            "path_less_dispatcher_invocation_fails_honestly_not_fabricated": True,
            "plugin_installed_into_isolated_codex_home_cache": True,
        },
        "required_checks": {
            "clean_uninstall_test": {
                "module": LIFECYCLE_MODULE,
                "status": "PASS",
                "test_count": lifecycle_count,
            },
            "fresh_install_test": {
                "module": LIFECYCLE_MODULE,
                "status": "PASS",
                "test_count": lifecycle_count,
            },
        },
        "status": "PASS",
        "targeted_test_count": lifecycle_count,
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
                "artifacts/work_packages/G04/attempts/0001/build_g04_0001_evidence.py",
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
        "# G04-0001 independent review of bounded-agent work\n"
        "\n"
        "- Author: the bounded implementation agent that wrote\n"
        "  tests/install/local-marketplace (lifecycle-harness.mjs and\n"
        "  g04-lifecycle.test.mjs). Reviewer: this seal-prep session, a distinct\n"
        "  actor that did not author the harness. The author never approves its own\n"
        "  work, so actor_independence HOLDS for this review; external\n"
        "  actor-independent certification does NOT, and no such claim is made. G04\n"
        "  is risk_class=high and gates fresh install and clean uninstall, so the\n"
        "  harness was attacked on its isolation and residue contracts rather than\n"
        "  skimmed.\n"
        "- Fresh install works and is functional. The test builds an isolated,\n"
        "  uniquely named OS-temp root holding a disposable local marketplace, an\n"
        "  isolated CODEX_HOME, an isolated user profile with AppData roots, and an\n"
        "  empty cwd, all under spaced non-ASCII paths. The real codex host adds the\n"
        "  marketplace, lists the plugin as available without the personal\n"
        "  marketplace, and installs epistemic-foundry into the isolated plugin\n"
        "  cache. The installed cache is a byte-for-byte hash-equal copy of the four\n"
        "  source files (zero missing, extra, or mismatched paths), its manifest is\n"
        "  valid with an empty capability set, and enable/disable/re-enable is\n"
        "  observed through the host after edits confined to isolated config.\n"
        "- The install survives marketplace-source detachment. The marketplace\n"
        "  plugin source is renamed away and the installed cache still enumerates\n"
        "  identically and lists enabled, proving no repository checkout or live\n"
        "  source is assumed. The absolute installed dispatcher is then invoked from\n"
        "  an empty cwd with an empty PATH; it fails closed naming the installed\n"
        "  dist/cli.mjs target, does not leak the repository path, and no command\n"
        "  success is fabricated because the T03-owned CLI payload is intentionally\n"
        "  not yet packaged.\n"
        "- Clean uninstall leaves no residue. Plugin remove deletes the installed\n"
        "  cache and removes the selector from isolated config; marketplace remove\n"
        "  drops it from the listing with zero G04 marketplace residue. The real\n"
        "  user's ~/.codex/config.toml file state and selector cache are captured\n"
        "  before the run, asserted absent during it, and compared byte-identical in\n"
        "  a finally block that also tears the owned temp root down after verifying\n"
        "  its OS-temp parent, owned prefix, directory type, and non-link identity.\n"
        "- Evidence hygiene. Command evidence stores normalized argv, status, and\n"
        "  byte-size/sha256 of normalized stdout and stderr only; no raw output,\n"
        "  username, absolute repository path, or random temp path is retained, and\n"
        "  every recorded command is a successful bounded call.\n"
        "- Dependencies and checks: the harness installs the G02/G03-sealed plugin\n"
        "  package shell (G02-0001 PASS, G03-0001 PASS) and adds no new production\n"
        "  dependency. Ruff lint and format, the two required checks "
        f"(fresh_install_test and clean_uninstall_test, both asserted in the "
        f"{EXPECTED_LIFECYCLE_COUNT}/{EXPECTED_LIFECYCLE_COUNT} lifecycle module), "
        f"full Python {EXPECTED_PYTHON_COUNT}/{EXPECTED_PYTHON_COUNT}, full Node "
        f"{EXPECTED_NODE_COUNT}/{EXPECTED_NODE_COUNT} across "
        f"{EXPECTED_NODE_FILE_COUNT} files, and git diff --check all pass with\n"
        "  zero failures.\n"
        "- Residual limitations: G04 verifies the current capability-free plugin\n"
        "  shell's local-marketplace install, state observation, cache independence,\n"
        "  and clean removal only; the T03 CLI payload and command semantics, remote\n"
        "  marketplace publication, OS-enforced sandboxing, and release readiness\n"
        "  remain later packages. Verdict: PASS on the exact G04 package contract.\n"
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
            "path": f"artifacts/work_packages/G04/attempts/0001/{name}",
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in sorted(set(output_names))
    ]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "G04_LOCAL_MARKETPLACE_FRESH_INSTALL_AND_CLEAN_UNINSTALL",
        "changed_files": [
            {
                "byte_size": (ROOT / relative).stat().st_size,
                "path": relative,
                "sha256": "sha256:" + digest,
            }
            for relative, digest in sorted(EXPECTED_PRODUCT_HASHES.items())
        ],
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependency_state": dependencies,
        "exit_criteria": {
            "install_enable_disable_uninstall": "PASS",
            "repository_checkout_not_required": "PASS",
        },
        "global_implementation_gate": "fail",
        "history_and_worktree": {
            "dirty_worktree_preserved": True,
            "prior_attempts_reports_and_rah_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
        },
        "implementation_status": "PASS",
        "not_claimed": [
            "T03 CLI payload or command semantics",
            "remote marketplace publication",
            "OS-enforced sandboxing",
            "release or production readiness",
            "external actor-independent certification of this review",
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
        "title": "G-phase local marketplace fresh-install gate",
        "work_package_id": WORK_PACKAGE_ID,
        "write_scope": write_scope,
    }
    if rah_state is not None:
        report["rah_state"] = rah_state
    return report


def project_root() -> None:
    PACKAGE_ROOT.mkdir(parents=True, exist_ok=True)
    for name in ROOT_PROJECTIONS:
        shutil.copyfile(ATTEMPT / name, PACKAGE_ROOT / name)


def verify_root_projection() -> None:
    for name in ROOT_PROJECTIONS:
        if (PACKAGE_ROOT / name).read_bytes() != (ATTEMPT / name).read_bytes():
            raise SystemExit(
                f"G04 root projection differs from attempt artifact: {name}"
            )


def _summary() -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "completion_ready": False,
        "full_node": f"{EXPECTED_NODE_COUNT}/{EXPECTED_NODE_COUNT}",
        "full_python": f"{EXPECTED_PYTHON_COUNT}/{EXPECTED_PYTHON_COUNT}",
        "lifecycle_test": f"{EXPECTED_LIFECYCLE_COUNT}/{EXPECTED_LIFECYCLE_COUNT}",
        "next_action": "SEAL_G04_0001_THEN_CONTINUE_DAG",
        "node_file_count": EXPECTED_NODE_FILE_COUNT,
        "package_status": "PASS",
        "required_checks": ["fresh_install_test", "clean_uninstall_test"],
        "status": "PASS",
    }


def build() -> dict[str, Any]:
    for name in RUN_RESULTS:
        check_run(name)
    normalize_junits()
    regression = regression_evidence()
    dependencies = dependency_status()
    write_scope = write_scope_verification()
    verification = g04_verification(regression)
    write_json("dependency-status.json", dependencies)
    write_json("write-scope-verification.json", write_scope)
    write_json("g04-verification.json", verification)
    (ATTEMPT / "commands.jsonl").write_text(
        commands_text(), encoding="utf-8", newline="\n"
    )
    (ATTEMPT / "review.md").write_text(review_text(), encoding="utf-8", newline="\n")
    report = report_document(
        regression, dependencies, write_scope, verification, rah_state=None
    )
    write_json("report.json", report)
    project_root()
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
        raise SystemExit("G04-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "g04-verification.json")
    report = report_document(
        regression, dependencies, write_scope, verification, rah_state=rah_state
    )
    write_json("report.json", report)
    project_root()


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
    verification = read_json(ATTEMPT / "g04-verification.json")
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
        raise SystemExit("stored G04-0001 report is not the deterministic document")
    verify_root_projection()
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
