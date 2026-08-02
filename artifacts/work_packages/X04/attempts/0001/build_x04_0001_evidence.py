#!/usr/bin/env python3
"""Build and verify X04-0001 evidence: cross-provider parity and diversity gate.

This attempt implements the cross-provider parity and error-correlation
evaluation under the frozen write scope ``evals/provider_parity/**`` (the seal
scripts live in the second granted scope ``artifacts/work_packages/X04/**``).
The builder verifies every executed check receipt, gates the two required pytest
suites against their measured counts, gates the repository-wide Python and Node
suites, pins product and dependency bytes, binds the sealed X02 and X03
dependencies and the live latest-sealed regression baseline, and emits the
deterministic attempt evidence.  It never modifies product files, invokes any
live provider, scores, selects, promotes or evaluates any candidate.
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
ATTEMPT = ROOT / "artifacts/work_packages/X04/attempts/0001"
ATTEMPT_ID = "X04-0001"
WORK_PACKAGE_ID = "X04"
RECORDED_AT = "2026-08-02T00:00:00.000Z"
ATTEMPT_DIR = "artifacts/work_packages/X04/attempts/0001"
COMPONENT = "evals/provider_parity"
APPROVED_SCOPE = [
    "evals/provider_parity/**",
    "artifacts/work_packages/X04/**",
]
#: Cache directories pytest/CPython scatter through the component and that must
#: never be hashed as product bytes.
CACHE_DIR_NAMES = frozenset({"__pycache__", ".pytest_cache"})

EXPECTED_PRODUCT_HASHES = {
    "evals/provider_parity/provider_parity_cases.json": "9f8e3a468170d1c6edab727e094632c8f55b1dd828b3ecf3f252c92f83a35117",
    "evals/provider_parity/provider_parity_harness.py": "49a0ee9766ad63effb97d68737989c3824b91c40fb79141f884bdeb1e6266e28",
    "evals/provider_parity/provider_parity_results.json": "13925568b95f87c428a4c74edf1d54ea9f9554eeea4a5d17d4ee1c1176a43f31",
    "evals/provider_parity/pytest.ini": "3153ca34deeaa382490cc029ced5c24015b69ba0a7d7061a270329393734ec78",
    "evals/provider_parity/test_error_correlation.py": "f54a347385e5ea4114b526ee38abb251af07ebac3f24aad2be4962db01ef5ed3",
    "evals/provider_parity/test_provider_parity.py": "8f0b76c2bddb744ad87b1a71cca8361fc1280c006c7ce417b9103e80725155e7",
}
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/G06/attempts/0001/report.json": "6486d22cb242c64924c06d1179e95aa8f47830032c597031756c855425cdc859",
    "artifacts/work_packages/X02/attempts/0001/report.json": "e61b255de0940f06c0fd468b3e9492e6f9246b4e3ca23907fe39085670f58941",
    "artifacts/work_packages/X03/attempts/0001/report.json": "bde8bd3a3e1b724f5abe09776cad672656b3d001898476b6d2378c188f2fb122",
}

JUNIT_PATHS = {
    "provider_parity_eval": ATTEMPT / "provider-parity-eval.junit.xml",
    "error_correlation_eval": ATTEMPT / "error-correlation-eval.junit.xml",
    "full_python_suite": ATTEMPT / "full-python-suite.junit.xml",
    "full_node_suite": ATTEMPT / "full-node-suite.junit.xml",
}
#: X04 product tests are pytest; only the repository-wide Node regression is a
#: Node suite.  These names classify each JUnit for normalization and counting.
_NODE_JUNITS = frozenset({"full_node_suite"})
PYTEST_SUITES = (
    "provider_parity_eval",
    "error_correlation_eval",
    "full_python_suite",
)
NODE_SUITES = ("full_node_suite",)
#: The two required checks whose measured counts the report cites, each pinned.
PINNED_PYTEST_SUITES = (
    ("provider_parity_eval", 8),
    ("error_correlation_eval", 8),
)
RUN_RESULTS = (
    "provider-parity-eval",
    "error-correlation-eval",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
    "write-scope-verification",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "build_x04_0001_evidence.py",
    "commands.jsonl",
    "dependency-status.json",
    "error-correlation-eval.junit.xml",
    "full-node-suite.junit.xml",
    "full-python-suite.junit.xml",
    "junit-normalization-verification.json",
    "node-test-inventory.json",
    "provider-parity-eval.junit.xml",
    "review.md",
    "run_x04_0001_checks.py",
    "write-scope-verification.json",
    "x04-verification.json",
    "x04_0001_rah_seal.py",
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
    summaries: dict[str, dict[str, Any]] = {}
    # The two required-check evals are pinned to their known counts; the whole
    # suite must be non-empty and wholly green.
    for name, expected in PINNED_PYTEST_SUITES:
        summary = pytest_summary(JUNIT_PATHS[name])
        if (
            summary["collected"],
            summary["passed"],
            summary["failed"],
            summary["errors"],
            summary["skipped"],
        ) != (expected, expected, 0, 0, 0):
            raise SystemExit(f"{name} gate failed: {summary}")
        summaries[name] = summary

    # The repository-wide Python suite gates green with a derived expected ==
    # measured count (the live frontier count is recorded, never frozen).
    full_python = pytest_summary(JUNIT_PATHS["full_python_suite"])
    if full_python["collected"] <= 0 or (
        full_python["passed"],
        full_python["failed"],
        full_python["errors"],
        full_python["skipped"],
    ) != (full_python["collected"], 0, 0, 0):
        raise SystemExit(f"full_python_suite gate failed: {full_python}")
    summaries["full_python_suite"] = full_python

    # The repository-wide Node suite gates on zero failures; the passing count is
    # the live frontier count and is recorded, never frozen to a literal.
    full_node = node_summary(JUNIT_PATHS["full_node_suite"])
    if (
        (
            full_node["failed"],
            full_node["cancelled"],
            full_node["xml_error_count"],
            full_node["xml_failure_count"],
        )
        != (0, 0, 0, 0)
        or full_node["passed"] <= 0
        or full_node["collected"]
        != (full_node["passed"] + full_node["skipped"] + full_node["todo"])
    ):
        raise SystemExit(f"full_node_suite gate failed: {full_node}")
    summaries["full_node_suite"] = full_node

    inventory = read_json(ATTEMPT / "node-test-inventory.json")
    return {
        "attempt_id": ATTEMPT_ID,
        "count_authority": (
            "required_evals_pinned; full_suites_derived_expected_equals_measured"
        ),
        "full_node_gate": "zero_failures",
        "full_node_inventory_count": inventory.get("count"),
        "full_node_passed": full_node["passed"],
        "full_python_passed": full_python["passed"],
        "new_failure_count": 0,
        "regression_baseline_attempt": "G06-0001",
        "status": "PASS",
        "suites": summaries,
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
        "core_generation": rah.get("core_generation"),
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
            "X02": _sealed_dependency("X02", "X02-0001", "E0245", "E0246"),
            "X03": _sealed_dependency("X03", "X03-0001", "E0227", "E0228"),
        },
        "next_action": "SEAL_X04_0001_THEN_RECOMPUTE_DAG",
        "regression_baseline": _sealed_dependency("G06", "G06-0001", "E0247", "E0248"),
        "regression_baseline_note": (
            "G06-0001 is the live latest-sealed attempt (highest core generation "
            "on the ledger frontier) at the time this evidence was built."
        ),
        "status": "PASS",
    }


def write_scope_verification() -> dict[str, Any]:
    # The runner authors write-scope-verification.json over the whole approved
    # product scope evals/provider_parity/**; the builder re-derives the product
    # hashes live, pins them, and confirms the recorded receipt is exactly those
    # bytes.
    assert_hashes(EXPECTED_PRODUCT_HASHES)
    component_root = ROOT / COMPONENT
    relatives = sorted(
        path.relative_to(ROOT).as_posix()
        for path in component_root.rglob("*")
        if path.is_file() and not (CACHE_DIR_NAMES & set(path.parts))
    )
    if relatives != sorted(EXPECTED_PRODUCT_HASHES):
        raise SystemExit(
            f"provider_parity component holds unexpected files: {relatives}"
        )
    live_hashes = {
        relative: "sha256:" + sha256(ROOT / relative) for relative in relatives
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
        or record.get("checked_file_count") != len(relatives)
    ):
        raise SystemExit(
            f"write-scope-verification receipt is not conformant: {record}"
        )
    return record


def package_verification(regression: dict[str, Any]) -> dict[str, Any]:
    suites = regression["suites"]
    return {
        "attempt_id": ATTEMPT_ID,
        "declaring_sources": {
            "adapter_surfaces": (
                "adapters/codex (X01) and adapters/claude-code (X02) committed "
                "surfaces are evaluated as they stand; parity is measured over "
                "the sealed adapter role maps, never over live provider calls"
            ),
            "parity_surface": (
                "manifests/role_registry.yaml (the canonical role set is read "
                "from the registry, never restated in the eval)"
            ),
        },
        "exit_criteria": {
            "canonical_outputs_comparable": {
                "mechanism": (
                    "both the Codex and Claude Code adapters are measured against "
                    "the canonical role registry: the role set aligns, each role "
                    "carries the registry output-schema reference on both "
                    "adapters, the host agent type and Claude surface are uniform, "
                    "and write-capable roles stay isolation-tracked; a dropped "
                    "role, a rebound output schema, an unnamed host descriptor, or "
                    "isolation that stops tracking a write scope is each refused "
                    "with its own typed finding"
                ),
                "status": "PASS",
            },
            "vendor_diversity_not_assumed_independent": {
                "mechanism": (
                    "provider diversity is reported as a number, not an "
                    "assumption: the 2x2 error contingency and phi coefficient are "
                    "recomputed from the raw synthetic trials, the observed "
                    "joint-error rate is shown to exceed the rate independence "
                    "would predict, and a fixture asserting independence or a "
                    "provider presented as live is each refused; the committed "
                    "results artifact is re-derived from the sealed surfaces and "
                    "any drift breaks its own hash"
                ),
                "status": "PASS",
            },
        },
        "required_checks": {
            "error_correlation_eval": {
                "status": "PASS",
                "test_count": suites["error_correlation_eval"]["collected"],
            },
            "independent_review": {
                "evidence": (
                    "review.md (author: bounded X04 implementation agent; "
                    "reviewer: the sealing session, which did not author this "
                    "attempt; actor_independence between author and reviewer "
                    "holds, external certification does not)"
                ),
                "status": "PASS",
            },
            "provider_parity_eval": {
                "status": "PASS",
                "test_count": suites["provider_parity_eval"]["collected"],
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
                f"{ATTEMPT_DIR}/build_x04_0001_evidence.py",
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
        "# X04-0001 independent review of bounded-agent work\n"
        "\n"
        "- Author: a bounded implementation agent (X04 maker) that produced the\n"
        "  cross-provider parity and error-correlation evaluation under the frozen\n"
        "  write scope evals/provider_parity/**. Reviewer: the sealing session,\n"
        "  which did not author this attempt. Author/reviewer separation holds\n"
        "  (actor_independence=true); external actor-independent certification\n"
        "  does not.\n"
        "- Mode: INDEPENDENT_REVIEW_OF_BOUNDED_AGENT_WORK. Blocking findings: 0.\n"
        "- Scope: the product write scope is evals/provider_parity/** only (the\n"
        "  seal scripts sit in the second granted scope\n"
        "  artifacts/work_packages/X04/**). No schema, manifest, adapter surface\n"
        "  or .rah/ state was touched; the six product files sit exactly inside\n"
        "  the granted scope and are hash-pinned.\n"
        "- Parity is derived from the sealed adapter surfaces, never invented: the\n"
        "  canonical role set is read from manifests/role_registry.yaml, the Codex\n"
        "  (X01) and Claude Code (X02) adapter role maps are measured as they\n"
        "  stand, and a dropped role, a rebound canonical output schema, an\n"
        "  unnamed host agent type, a non-uniform Claude surface, and isolation\n"
        "  that stops tracking a write scope are each refused with a typed\n"
        "  finding; the refusal cases mutate in-memory copies so the sealed\n"
        "  adapter files on disk are never touched.\n"
        "- Diversity is measured, not assumed independent: the 2x2 error\n"
        "  contingency and phi coefficient are recomputed from the raw synthetic\n"
        "  trials, the observed joint-error rate exceeds what independence would\n"
        "  predict (positively correlated), and a fixture asserting independence\n"
        "  or a provider presented as live is each refused. The committed results\n"
        "  artifact is re-derived from the sources and any edit breaks its own\n"
        "  hash.\n"
        "- Authority and provider boundary: nothing here scores, selects,\n"
        "  promotes or evaluates any candidate, no eval or fixture acquires\n"
        "  evaluator/holdout/promotion authority, and no live provider is invoked\n"
        "  (every provider is declared synthetic).\n"
        "- Gates at review time: provider_parity_eval 8/8, error_correlation_eval\n"
        "  8/8, the full Python suite and the full Node suite green, and git diff\n"
        "  --check clean. Dependencies X02-0001 and X03-0001 are bound and\n"
        "  G06-0001 is the live latest-sealed regression baseline.\n"
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
        "attempt_type": "X04_CROSS_PROVIDER_PARITY_DIVERSITY_GATE",
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
            "provider parity derived from anything other than the sealed adapter surfaces (no live provider call)",
            "vendor diversity asserted as statistical independence: it is measured as a correlation number only",
            "any live-provider invocation: every provider in the fixture is declared synthetic",
            "any adapter, eval or fixture acquiring evaluator, holdout, or promotion authority",
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
            "actor_independence": True,
            "assurance_limitation": (
                "Author/reviewer separation holds (a bounded X04 implementation "
                "agent authored, the sealing session reviewed); external "
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
        "next_action": "SEAL_X04_0001_THEN_RECOMPUTE_DAG",
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
    write_json("x04-verification.json", verification)
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
        raise SystemExit("X04-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "x04-verification.json")
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
    verification = read_json(ATTEMPT / "x04-verification.json")
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
        raise SystemExit("stored X04-0001 report is not the deterministic document")
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
