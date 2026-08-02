#!/usr/bin/env python3
"""Build and verify X03-0001 evidence: model routing and fallback policy.

This attempt implements the role-router model routing and fallback policy under
the frozen write scope ``packages/role-router/src/routing/**``.  The builder
verifies every executed check receipt, gates the two required JUnit suites
against their measured counts, gates the repository-wide Node suite on zero
failures with the two X03 routing modules inside the inventory, pins product and
dependency bytes, binds the X01 dependency and the live latest-sealed regression
baseline, and emits the deterministic attempt evidence.  It never modifies
product files.
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
ATTEMPT = ROOT / "artifacts/work_packages/X03/attempts/0001"
ATTEMPT_ID = "X03-0001"
WORK_PACKAGE_ID = "X03"
RECORDED_AT = "2026-08-02T00:00:00.000Z"
ATTEMPT_DIR = "artifacts/work_packages/X03/attempts/0001"
ROUTING = "packages/role-router/src/routing"
APPROVED_SCOPE = ["packages/role-router/src/routing/**"]

EXPECTED_PRODUCT_HASHES = {
    "packages/role-router/src/routing/fallback-provenance.test.mjs": "6f6916618a207239fae512db58b3de04975cade1e4c213b732844c65da56f75b",
    "packages/role-router/src/routing/index.mjs": "2c56b07363c02687e72dbafb72a25246103fdbe56771353915f2684f959330e1",
    "packages/role-router/src/routing/route-policy-test-support.mjs": "b6a38c29fe32b48eabf83b740bc65f98654d83a1b611edb2dadbba49a4c48fc5",
    "packages/role-router/src/routing/route-policy.mjs": "9092d3214b983c29b3359978a67d9e3c8abefc8bc07cbf39c90ea5dadc793a34",
    "packages/role-router/src/routing/routing-policy.test.mjs": "b4a2396940e3cbf47e052fe5f5ae07c7b0e48713dfbcb79d1a8a8b10d0697d72",
}
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/R06/attempts/0001/report.json": "ca4f56d06df2e3675c80acccc8c74e35a3b8b1a808294537beeb1f8996e6d4c3",
    "artifacts/work_packages/X01/attempts/0001/report.json": "976e23a05d826aa10c3f757d652c3c6fd8f56ed05f9bf0dcba09aa033c2a924c",
}

JUNIT_PATHS = {
    "fallback_provenance_test": ATTEMPT / "fallback-provenance-test.junit.xml",
    "full_node_suite": ATTEMPT / "full-node-suite.junit.xml",
    "routing_policy_test": ATTEMPT / "routing-policy-test.junit.xml",
}
_NODE_JUNITS = frozenset(
    {
        "fallback_provenance_test",
        "full_node_suite",
        "routing_policy_test",
    }
)
RUN_RESULTS = (
    "fallback-provenance-test",
    "full-node-suite",
    "git-diff-check",
    "routing-policy-test",
    "write-scope-verification",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "build_x03_0001_evidence.py",
    "commands.jsonl",
    "dependency-status.json",
    "fallback-provenance-test.junit.xml",
    "full-node-suite.junit.xml",
    "junit-normalization-verification.json",
    "node-test-inventory.json",
    "review.md",
    "routing-policy-test.junit.xml",
    "run_x03_0001_checks.py",
    "write-scope-verification.json",
    "x03-verification.json",
    "x03_0001_rah_seal.py",
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
    for label, expected in (
        ("routing_policy_test", 14),
        ("fallback_provenance_test", 10),
    ):
        summary = node_summary(JUNIT_PATHS[label])
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

    # The repository-wide Node suite gates on zero failures with the two X03
    # routing modules inside the measured inventory; the passing count is the
    # live frontier count and is recorded, never frozen to a literal.
    full = node_summary(JUNIT_PATHS["full_node_suite"])
    if (
        full["failed"],
        full["cancelled"],
        full["xml_error_count"],
        full["xml_failure_count"],
    ) != (0, 0, 0, 0) or full["passed"] <= 0 or full["collected"] != (
        full["passed"] + full["skipped"] + full["todo"]
    ):
        raise SystemExit(f"full_node_suite gate failed: {full}")
    summaries["full_node_suite"] = full

    inventory = read_json(ATTEMPT / "node-test-inventory.json")
    routing = inventory.get("x03_routing_tests")
    expected_routing = [
        f"{ROUTING}/fallback-provenance.test.mjs",
        f"{ROUTING}/routing-policy.test.mjs",
    ]
    if sorted(routing or []) != sorted(expected_routing):
        raise SystemExit(f"X03 routing tests not in Node inventory: {inventory}")
    return {
        "attempt_id": ATTEMPT_ID,
        "full_node_gate": "zero_failures_with_x03_routing_in_inventory",
        "full_node_inventory_count": inventory.get("count"),
        "full_node_passed": full["passed"],
        "new_failure_count": 0,
        "regression_baseline_attempt": "R06-0001",
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
    assert_hashes(EXPECTED_DEPENDENCY_HASHES)
    return {
        "attempt_id": ATTEMPT_ID,
        "dependencies": {
            "X01": _sealed_dependency("X01", "X01-0001", "E0203", "E0204"),
        },
        "next_action": "SEAL_X03_0001_THEN_RECOMPUTE_DAG",
        "regression_baseline": _sealed_dependency("R06", "R06-0001", "E0223", "E0224"),
        "regression_baseline_note": (
            "R06-0001 is the live latest-sealed attempt (highest core generation "
            "on the ledger frontier) at the time this evidence was built."
        ),
        "status": "PASS",
    }


def write_scope_verification() -> dict[str, Any]:
    # The runner authors write-scope-verification.json over the whole approved
    # scope; the builder re-derives the product hashes live, pins them, and
    # confirms the recorded receipt is exactly those bytes.
    assert_hashes(EXPECTED_PRODUCT_HASHES)
    routing_root = ROOT / ROUTING
    relatives = sorted(
        path.relative_to(ROOT).as_posix()
        for path in routing_root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )
    live_hashes = {relative: "sha256:" + sha256(ROOT / relative) for relative in relatives}
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
        raise SystemExit(f"write-scope-verification receipt is not conformant: {record}")
    return record


def package_verification(regression: dict[str, Any]) -> dict[str, Any]:
    suites = regression["suites"]
    return {
        "attempt_id": ATTEMPT_ID,
        "declaring_sources": {
            "route_table": (
                "packages/role-router/src/routing/route-policy.mjs "
                "(declared task classes, route order, policy and reward-basis "
                "vocabulary; never invented)"
            ),
            "routing_receipt_schema": (
                "schemas/model-routing-receipt.schema.json "
                "(policy and reward_basis enums the routing vocabulary composes)"
            ),
        },
        "exit_criteria": {
            "failure_cost_and_eval_data_drive_routing": {
                "mechanism": (
                    "each task class routes over a declared, hash-bound route "
                    "order whose selection is driven by the declared reward "
                    "basis and per-route estimated cost/latency; the emitted "
                    "receipt records the policy, reward_basis, estimated_cost "
                    "and estimated_latency_ms and re-derives its own hash, so "
                    "the routing decision is content-addressed rather than "
                    "asserted"
                ),
                "status": "PASS",
            },
            "fallback_recorded_and_policy_approved": {
                "mechanism": (
                    "when a primary route is unavailable the derivation skips "
                    "to the next declared candidate, records an ordered "
                    "fallback_chain with a typed reason, and stamps a "
                    "policy-approved RFB fallback_policy_decision_id; the route "
                    "order must terminate in exactly one safe default which can "
                    "never be declared unavailable, and distinct fallback "
                    "depths yield distinct decision ids"
                ),
                "status": "PASS",
            },
        },
        "required_checks": {
            "fallback_provenance_test": {
                "status": "PASS",
                "test_count": suites["fallback_provenance_test"]["collected"],
            },
            "independent_review": {
                "evidence": (
                    "review.md (author: bounded X03 implementation agent; "
                    "reviewer: the sealing session, which did not author this "
                    "attempt; actor_independence between author and reviewer "
                    "holds, external certification does not)"
                ),
                "status": "PASS",
            },
            "routing_policy_test": {
                "status": "PASS",
                "test_count": suites["routing_policy_test"]["collected"],
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
                f"{ATTEMPT_DIR}/build_x03_0001_evidence.py",
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
        "# X03-0001 independent review of bounded-agent work\n"
        "\n"
        "- Author: a bounded implementation agent (X03 maker) that produced the\n"
        "  routing tree under the frozen write scope\n"
        "  packages/role-router/src/routing/**. Reviewer: the sealing session,\n"
        "  which did not author this attempt. Author/reviewer separation holds\n"
        "  (actor_independence=true); external actor-independent certification\n"
        "  does not.\n"
        "- Mode: INDEPENDENT_REVIEW_OF_BOUNDED_AGENT_WORK. Blocking findings: 0.\n"
        "- Scope: the write scope is packages/role-router/src/routing/** only.\n"
        "  No schema, manifest, package under packages/ outside the routing tree,\n"
        "  or .rah/ state was touched; the five product files sit exactly inside\n"
        "  the granted scope and are hash-pinned.\n"
        "- Routing is derived, never invented: the route table is content-\n"
        "  addressed and hash-bound, the policy and reward_basis vocabularies are\n"
        "  read from schemas/model-routing-receipt.schema.json rather than\n"
        "  restated, an undeclared task class and an unknown route candidate are\n"
        "  refused, and every emitted receipt re-derives its own hash.\n"
        "- Fallback provenance holds: the declared route order terminates in\n"
        "  exactly one safe default that can never be declared unavailable,\n"
        "  skipped candidates are recorded as an ordered fallback_chain with a\n"
        "  policy-approved RFB decision id, and distinct fallback depths yield\n"
        "  distinct decision ids.\n"
        "- Authority boundary: no route acquires evaluator, holdout, or\n"
        "  promotion authority; adding an *_gate task class that aliases such\n"
        "  authority is refused (ROUTE_AUTHORITY_FORBIDDEN).\n"
        "- Gates at review time: routing_policy_test 14/14, fallback_provenance_\n"
        "  test 10/10, the full Node suite green with the two X03 routing modules\n"
        "  inside the inventory, and git diff --check clean. Dependency X01-0001\n"
        "  is bound and R06-0001 is the live latest-sealed regression baseline.\n"
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
        "attempt_type": "X03_MODEL_ROUTING_FALLBACK_POLICY",
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
            "any route acquiring evaluator, holdout, or promotion authority",
            "any routing decision invented rather than derived from the declared route table",
            "provider parity or cross-vendor error independence (X04 scope)",
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
                "Author/reviewer separation holds (a bounded X03 implementation "
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
        "next_action": "SEAL_X03_0001_THEN_RECOMPUTE_DAG",
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
    write_json("x03-verification.json", verification)
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
        raise SystemExit("X03-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "x03-verification.json")
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
    verification = read_json(ATTEMPT / "x03-verification.json")
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
        raise SystemExit("stored X03-0001 report is not the deterministic document")
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
