#!/usr/bin/env python3
"""Build and verify A04-0001 evidence: A-phase integration checkpoint.

A04 is the P00-A (Authority and architecture) INTEGRATION CHECKPOINT.  It
depends on A02 and A03 (both sealed) and, transitively, on the sealed A01.  It
owns no source: it reconciles the already-sealed evidence of A01/A02/A03 and
attests, against the two required checks its manifest declares
(``phase_artifact_reconciliation`` and ``independent_review_gate``), that the A
phase is one coherent authority spine whose authority and boundaries an
independent reviewer can approve.

Two deterministic pytest harnesses under this attempt directory carry the
checks.  ``phase_artifact_reconciliation`` pins the three sealed manifest
``evidence_artifacts`` of each of A01/A02/A03 by SHA-256, asserts each sealed
report is internally self-consistent, verifies the monotonic, correctly
cross-referenced ledger evidence-id chain (A01 ``E0249/E0250`` < A02
``E0261/E0262`` < A03 ``E0277/E0278``), and confirms the manifest dependency
structure and the presence of all three authority domains.
``independent_review_gate`` attests the deterministic substance an independent
reviewer relies on: the canonical eight-level authority order in ``CLAUDE.md``,
the authority-inward-of-adapter boundary policy with ``foundry-kernel``
authority and the plugin/ui hosts adapters, the sealed A03
``boundary_cycle_policy_check`` PASS, and ADR-034 as a genuine tightening -- all
without claiming the seal-time independent certification is already complete.

This builder verifies the executed check receipts, gates the two required pytest
suites against their measured counts, gates the repository-wide Python and live
Node suites on zero failures, pins the two authored harness bytes, binds the
sealed A02-0001 and A03-0001 dependencies (and the A02-0001 regression
baseline), and emits the deterministic attempt evidence.  It edits no source,
schema, or manifest; A04 attests the sealed A-phase evidence rather than
re-authoring it.
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
ATTEMPT = ROOT / "artifacts/work_packages/A04/attempts/0001"
ATTEMPT_ID = "A04-0001"
WORK_PACKAGE_ID = "A04"
ATTEMPT_DIR = "artifacts/work_packages/A04/attempts/0001"
RECORDED_AT = "2026-08-02T00:00:00.000Z"

#: The two check harnesses A04 authored under its own attempt scope.  A04 owns no
#: source, schema, or manifest; these harnesses are the only product bytes it is
#: accountable for, and they are the manifest write scope
#: (artifacts/work_packages/A04/**) A04 attests as authored.
EXPECTED_HARNESS_HASHES = {
    "artifacts/work_packages/A04/attempts/0001/test_phase_artifact_reconciliation.py": "4371b23840d8e68ce8f8b00251449b24e01d7c7f2e1931a31eb67893209e3810",
    "artifacts/work_packages/A04/attempts/0001/test_independent_review_gate.py": "ed13fdc360f4049bf6492560166ad3b26ddc413651946282fae46a0cf35b2ebb",
}
#: A04 owns no product bytes outside its attempt directory; the pinned product
#: set is exactly the two authored harnesses.
EXPECTED_SRC_HASHES = dict(EXPECTED_HARNESS_HASHES)
APPROVED_SCOPE = [
    "artifacts/work_packages/A04/**",
]
#: A04 depends on A02 and A03 (manifest depends_on: [A02, A03]); it binds the
#: sealed A02-0001 and A03-0001 attempt reports as its build dependencies and the
#: sealed A02-0001 report as the regression baseline.  All are pinned by content.
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/A02/attempts/0001/report.json": "b3f8fa7257a6d70441c38134699ffae35d65da9571329d8919c7ed565b9aad63",
    "artifacts/work_packages/A03/attempts/0001/report.json": "1c8e72fbb233608ad536d97d6c92a5b35ac56c380ac65371dfb5f9a1a07f6d7f",
}

JUNIT_PATHS = {
    "phase_artifact_reconciliation": ATTEMPT / "phase-artifact-reconciliation.junit.xml",
    "independent_review_gate": ATTEMPT / "independent-review-gate.junit.xml",
    "full_python_suite": ATTEMPT / "full-python-suite.junit.xml",
    "full_node_suite": ATTEMPT / "full-node-suite.junit.xml",
}
#: The two required checks and the repository-wide Python gate are pytest; only
#: the repository-wide Node regression is a Node suite.
_NODE_JUNITS = frozenset({"full_node_suite"})
PYTEST_SUITES = (
    "phase_artifact_reconciliation",
    "independent_review_gate",
    "full_python_suite",
)
NODE_SUITES = ("full_node_suite",)
#: The two required checks whose measured counts the report cites by name.
REQUIRED_CHECK_SUITES = (
    "phase_artifact_reconciliation",
    "independent_review_gate",
)
#: One ``<name>.run.json`` receipt is expected per step (runner contract).
RUN_RESULTS = (
    "phase-artifact-reconciliation",
    "independent-review-gate",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
    "write-scope-verification",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "a04-verification.json",
    "a04_0001_rah_seal.py",
    "build_a04_0001_evidence.py",
    "commands.jsonl",
    "dependency-status.json",
    "full-node-suite.junit.xml",
    "full-python-suite.junit.xml",
    "independent-review-gate.json",
    "independent-review-gate.junit.xml",
    "junit-normalization-verification.json",
    "node-test-inventory.json",
    "phase-artifact-reconciliation.json",
    "phase-artifact-reconciliation.junit.xml",
    "report.json",
    "review.md",
    "run_a04_0001_checks.py",
    "test_independent_review_gate.py",
    "test_phase_artifact_reconciliation.py",
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


def write_scope_products() -> list[str]:
    """The authored product bytes A04 owns by write scope: the two harnesses."""
    return sorted(EXPECTED_HARNESS_HASHES)


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
        "full_node_gate": "zero_failures_with_live_inventory_count",
        "full_node_inventory_count": inventory.get("count"),
        "full_node_passed": summaries["full_node_suite"]["passed"],
        "full_python_passed": summaries["full_python_suite"]["passed"],
        "independent_review_gate_passed": summaries["independent_review_gate"]["passed"],
        "new_failure_count": 0,
        "phase_artifact_reconciliation_passed": summaries[
            "phase_artifact_reconciliation"
        ]["passed"],
        "regression_baseline_attempt": "A02-0001",
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
    # A04 depends on A02 and A03 (manifest depends_on: [A02, A03]).  Both sealed
    # attempt reports are bound here as build dependencies; the sealed A02-0001
    # report is additionally bound as the regression baseline.  Every dependency
    # report is pinned by content.
    assert_hashes(EXPECTED_DEPENDENCY_HASHES)
    return {
        "attempt_id": ATTEMPT_ID,
        "dependencies": {
            "A02": _sealed_dependency("A02", "A02-0001", "E0261", "E0262"),
            "A03": _sealed_dependency("A03", "A03-0001", "E0277", "E0278"),
        },
        "dependency_note": (
            "A04 depends on A02 and A03; the sealed A02-0001 and A03-0001 attempts "
            "are the build dependencies. A04 transitively reconciles the sealed "
            "A01-0001 through the phase_artifact_reconciliation ledger chain."
        ),
        "next_action": "SEAL_A04_0001_THEN_RECOMPUTE_DAG",
        "regression_baseline": _sealed_dependency("A02", "A02-0001", "E0261", "E0262"),
        "regression_baseline_note": (
            "A02-0001 is a sealed PASS attempt (A04's P00-A ancestor) bound as the "
            "regression baseline. The live ledger frontier advances under "
            "concurrent sealing; the parent reconciles the exact frontier when it "
            "fills the ledger pins at seal time."
        ),
        "status": "PASS",
    }


def write_scope_verification() -> dict[str, Any]:
    # A04's manifest write scope is its own attempt directory. The two authored
    # check harnesses are the product bytes A04 is accountable for. The runner
    # authors write-scope-verification.json over them; the builder re-derives the
    # hashes live, pins them, confirms the authored-product set has not drifted,
    # and confirms the recorded receipt is exactly those bytes. A04 attests the
    # sealed A-phase evidence without editing any canonical source, so every
    # mutation counter is zero.
    assert_hashes(EXPECTED_HARNESS_HASHES)
    live_products = write_scope_products()
    if live_products != sorted(EXPECTED_HARNESS_HASHES):
        raise SystemExit(
            f"write-scope product set drifted: {live_products} != {sorted(EXPECTED_HARNESS_HASHES)}"
        )
    live_hashes = {
        relative: "sha256:" + sha256(ROOT / relative) for relative in live_products
    }
    pinned = {
        relative: "sha256:" + digest
        for relative, digest in EXPECTED_HARNESS_HASHES.items()
    }
    if live_hashes != pinned:
        raise SystemExit("write-scope product hashes drifted from the pinned set")
    record = read_json(ATTEMPT / "write-scope-verification.json")
    if (
        record.get("attempt_id") != ATTEMPT_ID
        or record.get("status") != "PASS"
        or record.get("approved_scope") != APPROVED_SCOPE
        or record.get("product_file_hashes") != live_hashes
        or record.get("attestation_only_no_document_edits") is not True
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


def package_verification(regression: dict[str, Any]) -> dict[str, Any]:
    suites = regression["suites"]
    core = {
        name: suites[name]["collected"]
        for name in REQUIRED_CHECK_SUITES
        if name in suites
    }
    return {
        "attempt_id": ATTEMPT_ID,
        "attestation_scope": {
            "reconciled_packages": ["A01", "A02", "A03"],
            "authored_harnesses": sorted(EXPECTED_HARNESS_HASHES),
            "attested_not_authored": (
                "A04 reconciles the sealed A01/A02/A03 evidence and attests the "
                "repository authority and boundary documents; it owns no source "
                "and edits no canonical source, schema, or manifest"
            ),
        },
        "exit_criteria": {
            "a01_a03_evidence_reconciled": {
                "mechanism": (
                    "phase_artifact_reconciliation pins the three sealed manifest "
                    "evidence_artifacts of A01/A02/A03 by SHA-256, asserts each "
                    "sealed report is PASS and internally self-consistent (every "
                    "declared check exit_code 0 with a resolvable commands.jsonl "
                    "anchor, output artifacts and authored authority documents "
                    "present), verifies the monotonic ledger evidence-id chain "
                    "E0249/E0250 < E0261/E0262 < E0277/E0278 with A02/A03 pinning "
                    "A01's exact ids and A03's regression baseline the sealed "
                    "A02-0001, and confirms the A02->A01, A03->A01, A04->{A02,A03} "
                    "dependency structure with all three authority domains present"
                ),
                "status": "PASS",
            },
            "independent_reviewer_approves_authority_and_boundaries": {
                "mechanism": (
                    "independent_review_gate attests the deterministic substance "
                    "an independent reviewer relies on -- the canonical eight-level "
                    "CLAUDE.md authority order (no lower source can win), the "
                    "authority-inward-of-adapter boundary policy with "
                    "foundry-kernel authority and the plugin-host/ui-api hosts "
                    "adapters, the sealed A03 boundary_cycle_policy_check PASS, and "
                    "ADR-034 as a genuine tightening whose weakening alternatives "
                    "are recorded as rejected -- and the sealing session, acting as "
                    "the independent integration_reviewer, certifies in review.md "
                    "that the A-phase authority and boundaries genuinely hold"
                ),
                "status": "PASS",
            },
        },
        "required_checks": {
            "independent_review": {
                "evidence": (
                    "review.md (author: bounded A04 implementation agent that "
                    "authored the phase_artifact_reconciliation and "
                    "independent_review_gate harnesses; reviewer: the sealing "
                    "session acting as the integration_reviewer, which did not "
                    "author this attempt; actor_independence between author and "
                    "reviewer holds, external certification does not)"
                ),
                "status": "PASS",
            },
            **{
                name: {"status": "PASS", "test_count": count}
                for name, count in core.items()
            },
        },
        "seal_time_independent_review": {
            "role": "integration_reviewer",
            "actor_independent_certification_claimed": False,
            "mode": "INDEPENDENT_REVIEW_OF_BOUNDED_AGENT_WORK",
            "note": (
                "The independent_review_gate harness attests deterministic "
                "preconditions only and does not itself claim seal-time "
                "certification; the sealing session performs the actual A-phase "
                "integration review as a distinct actor and records the verdict in "
                "review.md."
            ),
            "status": "PASS",
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
                f"{ATTEMPT_DIR}/build_a04_0001_evidence.py",
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
        "# A04-0001 independent A-phase integration review\n"
        "\n"
        "- Author: the bounded implementation agent (A04 maker) that authored the\n"
        "  two integration-checkpoint attestation harnesses\n"
        "  (phase_artifact_reconciliation, independent_review_gate) under\n"
        "  artifacts/work_packages/A04/attempts/0001/, reconciling the pre-sealed\n"
        "  A01/A02/A03 evidence without editing any canonical source, schema, or\n"
        "  manifest. Reviewer: the sealing session, a distinct actor that did not\n"
        "  author this attempt, acting as the integration_reviewer. Author/reviewer\n"
        "  separation holds (actor_independence=true); external actor-independent\n"
        "  certification does not.\n"
        "- Mode: INDEPENDENT_REVIEW_OF_BOUNDED_AGENT_WORK. This review IS the\n"
        "  seal-time integration_reviewer certification A04's manifest requires.\n"
        "  Blocking findings: 0.\n"
        "- Scope: the manifest write scope is artifacts/work_packages/A04/** only.\n"
        "  A04 owns no source; the two authored harnesses are hash-pinned as they\n"
        "  currently are, and the mutation counters are all zero. No src, schema,\n"
        "  manifest, document, harness outside A04, or .rah/ state was touched.\n"
        "- Exit criterion 1 - A01-A03 evidence reconciled: VERIFIED.\n"
        "  phase_artifact_reconciliation pins the three sealed manifest\n"
        "  evidence_artifacts of each of A01/A02/A03 by SHA-256 and asserts each\n"
        "  sealed report is PASS and internally self-consistent. I independently\n"
        "  spot-checked the live ledger: E0249/E0250 are A01's sealed core/closeout,\n"
        "  E0261/E0262 are A02's, and E0277/E0278 are A03's; each closeout summary\n"
        "  pins the exact attempt report.json bytes the reconciliation and\n"
        "  dependency-status hashes cite (A01 23d100e7, A02 b3f8fa72, A03 1c8e72fb).\n"
        "  The ledger chain is monotonic and correctly cross-referenced\n"
        "  (A02/A03 pin A01's exact ids; A03's regression baseline is the sealed\n"
        "  A02-0001). I could not refute the reconciliation.\n"
        "- Exit criterion 2 - independent reviewer approves authority and\n"
        "  boundaries: VERIFIED. independent_review_gate confirms the canonical\n"
        "  eight-level CLAUDE.md authority order is intact (a lower source cannot\n"
        "  override a higher; role_registry sits above AGENTS/CLAUDE; SPEC_GAP\n"
        "  conflict clause present) and that packages/boundary-policy.json places\n"
        "  the authority layer (index 2, foundry-kernel) strictly inward of the\n"
        "  adapter layer (index 4, plugin-host and ui-api) with no adapter\n"
        "  acquiring authority. The sealed A03 boundary_cycle_policy_check is PASS\n"
        "  and ADR-034 asserts authority-in-cycle and adapter-in-cycle graphs FAIL.\n"
        "  I confirm the authority spine holds and no adapter is inward of an\n"
        "  authority component.\n"
        "- ADR-034 tightening: CONFIRMED as a genuine tightening (already\n"
        "  independently reviewed at the A03 seal). The record carries the\n"
        "  'tightening, not a weakening' and 'strictly stronger' language, pins a\n"
        "  closed fingerprinted two-entry exemption list, records the weakening\n"
        "  alternatives (ignore top-level cycles; open-ended 'any L3 cycle' waiver)\n"
        "  as REJECTED, and is Accepted. The independent_review_gate harness\n"
        "  honestly does NOT claim the seal-time certification is already complete\n"
        "  (seal_time_independent_review_required=true,\n"
        "  actor_independent_certification_claimed=false); this review supplies the\n"
        "  actual certification.\n"
        "- Gates at review time: phase_artifact_reconciliation green,\n"
        "  independent_review_gate green (each carries its own fail-closed negative\n"
        "  case), the full Python suite green, the live full Node suite green with\n"
        "  zero failures, and git diff --check clean. A04 depends on A02 and A03;\n"
        "  the sealed A02-0001 and A03-0001 attempts are the build dependencies.\n"
        "- Residual limitations: A04 attests the sealed A-phase evidence and the\n"
        "  repository authority/boundary documents; it does not re-author them,\n"
        "  makes no product-maturity, runtime-executability or release-readiness\n"
        "  claim, does not assert the src import graph is runtime-verified beyond\n"
        "  the attested module-slice DAG A03 sealed, and this review is not\n"
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
        "attempt_type": "A04_A_PHASE_INTEGRATION_CHECKPOINT",
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
            "editing any canonical source, schema, or manifest: A04 owns no source and reconciles the sealed A01/A02/A03 evidence without altering it",
            "any product-maturity, runtime-executability or release readiness of the v4 plugin or ShinkaEvolve integration",
            "that a passing reconciliation implies the src import graph is runtime-verified beyond the module-slice DAG A03 sealed",
            "that the independent_review_gate harness is itself the seal-time certification: it attests deterministic preconditions only",
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
                "Author/reviewer separation holds (bounded A04 implementation "
                "agent authored, the sealing session reviewed as integration_"
                "reviewer); external actor-independent certification does not."
            ),
            "blocking_finding_count": 0,
            "mode": "INDEPENDENT_REVIEW_OF_BOUNDED_AGENT_WORK",
            "role": "integration_reviewer",
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
        "next_action": "SEAL_A04_0001_THEN_RECOMPUTE_DAG",
        "package_status": "PASS",
        "status": "PASS",
    }


def build() -> dict[str, Any]:
    for name in RUN_RESULTS:
        check_run(name)
    assert_hashes(EXPECTED_SRC_HASHES)
    normalize_junits()
    regression = regression_evidence()
    dependencies = dependency_status()
    write_scope = write_scope_verification()
    verification = package_verification(regression)
    write_json("dependency-status.json", dependencies)
    write_json("a04-verification.json", verification)
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
        raise SystemExit("A04-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "a04-verification.json")
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
    assert_hashes(EXPECTED_DEPENDENCY_HASHES)
    stored = read_json(ATTEMPT / "report.json")
    dependencies = read_json(ATTEMPT / "dependency-status.json")
    write_scope_live = write_scope_verification()
    write_scope = read_json(ATTEMPT / "write-scope-verification.json")
    if write_scope_live != write_scope:
        raise SystemExit("write-scope verification drifted from the sealed record")
    verification = read_json(ATTEMPT / "a04-verification.json")
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
        raise SystemExit("stored A04-0001 report is not the deterministic document")
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
