#!/usr/bin/env python3
"""Build and verify I02-0001 evidence: InsightCard, falsifier and ScopeVector compiler.

This attempt was implemented by a bounded implementation agent under the product
owner's explicit instruction, with a disjoint write scope, and was reviewed by
the sealing agent (actor-independent from the author) before sealing.  The
builder verifies every executed check receipt, gates every JUnit against its
measured count, pins product and dependency bytes, and emits the deterministic
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
ATTEMPT = ROOT / "artifacts/work_packages/I02/attempts/0001"
ATTEMPT_ID = "I02-0001"
WORK_PACKAGE_ID = "I02"
RECORDED_AT = "2026-08-02T10:00:00.000Z"
ATTEMPT_DIR = "artifacts/work_packages/I02/attempts/0001"
AUTHORITY_DECISION = None

EXPECTED_PRODUCT_HASHES = {
    "artifacts/work_packages/I02/attempts/0001/check_packaging.py": "a0343885fec71e57415e96c368048b33a714bafe5b7ef8be0b4c8de52df8638c",
    "artifacts/work_packages/I02/attempts/0001/run_i02_0001_checks.py": "dfae0a433f2d90544f758428a8e394263f6fb413b76c669685fa97a955e76efd",
    "python/epistemic_foundry/intake/frame/__init__.py": "5401aea2c12d597fc627ed30cab262cc6695d1720a697f73fe603903a93dfc49",
    "python/epistemic_foundry/intake/frame/compiler.py": "eec74d16d02d7e5ee9ef80bb49ad5e012ade894e8c8406ba99e090eca9fbf4b9",
    "python/epistemic_foundry/intake/frame/test_falsifier_gate.py": "43721d8510d87492226dda4ee5162e46d891bb0cab2036313962c63482a0238a",
    "python/epistemic_foundry/intake/frame/test_frame_gold.py": "33c35e6d5e718ddd31863339847dc831fc85773750f970c3a658865f34c4c5d5",
}
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/I01/report.json": "7174f9292421996fcd7e48de8f29757657dcf9b7aff3483028bbb86be70f886a",
}

JUNIT_PATHS = {
    "falsifier_gate_test": ATTEMPT / "falsifier-gate-test.junit.xml",
    "frame_gold_test": ATTEMPT / "frame-gold-test.junit.xml",
    "full_node_suite": ATTEMPT / "full-node-suite.junit.xml",
    "full_python_suite": ATTEMPT / "full-python-suite.junit.xml",
    "wire_literal_discipline": ATTEMPT / "wire-literal-discipline.junit.xml",
}
_NODE_JUNITS = frozenset({"full_node_suite"})
RUN_RESULTS = (
    "falsifier-gate-test",
    "frame-gold-test",
    "full-node-suite",
    "full-python-suite",
    "git-diff-check",
    "packaging-discovery",
    "ruff-check",
    "wire-literal-discipline",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "build_i02_0001_evidence.py",
    "check_packaging.py",
    "commands.jsonl",
    "dependency-status.json",
    "falsifier-gate-test.junit.xml",
    "frame-gold-test.junit.xml",
    "full-node-suite.junit.xml",
    "full-python-suite.junit.xml",
    "i02-verification.json",
    "i02_0001_rah_seal.py",
    "junit-normalization-verification.json",
    "node-test-inventory.json",
    "review.md",
    "run_i02_0001_checks.py",
    "wire-literal-discipline.junit.xml",
    "write-scope-verification.json",
)

# Measured gate counts (observed at seal-prep time on the live tree).
FRAME_GOLD_COUNT = 19
FALSIFIER_GATE_COUNT = 12
WIRE_LITERAL_COUNT = 5
FULL_PYTHON_COUNT = 1261
FULL_NODE_COUNT = 1702
NODE_INVENTORY_COUNT = 136


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
    for label, summary, expected in (
        (
            "frame_gold_test",
            pytest_summary(JUNIT_PATHS["frame_gold_test"]),
            FRAME_GOLD_COUNT,
        ),
        (
            "falsifier_gate_test",
            pytest_summary(JUNIT_PATHS["falsifier_gate_test"]),
            FALSIFIER_GATE_COUNT,
        ),
        (
            "wire_literal_discipline",
            pytest_summary(JUNIT_PATHS["wire_literal_discipline"]),
            WIRE_LITERAL_COUNT,
        ),
        (
            "full_python_suite",
            pytest_summary(JUNIT_PATHS["full_python_suite"]),
            FULL_PYTHON_COUNT,
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
        ("full_node_suite", node_summary(JUNIT_PATHS["full_node_suite"]), FULL_NODE_COUNT),
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
    if node_inventory.get("count") != NODE_INVENTORY_COUNT:
        raise SystemExit(f"Node inventory gate failed: {node_inventory}")
    return {
        "attempt_id": ATTEMPT_ID,
        "component_tests_are_targeted_only": True,
        "new_failure_count": 0,
        "status": "PASS",
        "suites": summaries,
    }


def _sealed_dependency(package: str, core: str, final: str) -> dict[str, Any]:
    path = ROOT / f"artifacts/work_packages/{package}/report.json"
    report = read_json(path)
    rah = report.get("rah_state")
    if (
        report.get("status") != "PASS"
        or not isinstance(rah, dict)
        or rah.get("core_evidence_id") != core
        or rah.get("final_closeout_evidence_id") != final
    ):
        raise SystemExit(f"{package} is not the sealed PASS dependency")
    return {
        "attempt_id": str(report.get("attempt_id")),
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
            "I01": _sealed_dependency("I01", "E0068", "E0069"),
        },
        "next_action": "SEAL_I02_0001_THEN_RECOMPUTE_DAG",
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
            "python/epistemic_foundry/intake/frame/**",
            "artifacts/work_packages/I02/**",
        ],
        "attempt_id": ATTEMPT_ID,
        "authority_decision": AUTHORITY_DECISION,
        "authored_by": (
            "bounded implementation agent under the product owner's explicit "
            "instruction"
        ),
        "composed_modules_modified": False,
        "product_file_hashes": {
            relative: "sha256:" + digest
            for relative, digest in EXPECTED_PRODUCT_HASHES.items()
        },
        "pyproject_modified": False,
        "reset_clean_stash_commit_push_performed": False,
        "reviewed_by": "sealing agent (actor-independent from the author)",
        "root_canonical_source_mutation_count": 0,
        "schema_or_test_weakening_count": 0,
        "status": "PASS",
        "subagents_or_fleet_used": True,
        "write_scope_violation_count": 0,
    }


def package_verification(regression: dict[str, Any]) -> dict[str, Any]:
    suites = regression["suites"]
    required = {
        "frame_gold_test": suites["frame_gold_test"]["collected"],
        "falsifier_gate_test": suites["falsifier_gate_test"]["collected"],
    }
    return {
        "attempt_id": ATTEMPT_ID,
        "declaring_sources": {
            "closed_vocabularies": (
                "the closed UnknownSource (ABSENT/EXPLICIT_NULL/BLANK_STRING), "
                "registration-status (inbox/eligible/withdrawn), risk-class "
                "(routine/consequential/high_stakes) and SCAMPER lens_provenance "
                "vocabularies declared in "
                "python/epistemic_foundry/intake/frame/compiler.py, each bound "
                "key-for-key to schemas/insight-card.schema.json"
            ),
            "finding_codes": (
                "FALSIFIER_REQUIRED, FRAME_FIELD_REQUIRED, FRAME_FIELD_UNKNOWN, "
                "FRAME_INPUT_INVALID, FRAME_ELIGIBILITY_CONFLICT, "
                "SCOPE_INPUT_INVALID, SCOPE_FIELD_UNKNOWN, "
                "SCOPE_INTERVENTION_NAME_REQUIRED"
            ),
        },
        "exit_criteria": {
            "falsifier_mandatory_for_council": {
                "mechanism": (
                    "falsifiers are checked before any other required field and "
                    "an absent, empty, blank, or scalar falsifier list raises "
                    "FALSIFIER_REQUIRED; predictions and mechanism_path are also "
                    "mandatory, and an eligible card that retains any council "
                    "blocker is refused FRAME_ELIGIBILITY_CONFLICT so no "
                    "unfalsifiable frame can claim council readiness"
                ),
                "status": "PASS",
            },
            "scope_normalization_preserves_unknowns": {
                "mechanism": (
                    "a missing, explicit-null, or blank scalar scope position "
                    "becomes a canonical null (list/map positions become the "
                    "canonical empty [] / {}) and a typed ScopeUnknown sidecar "
                    "records ABSENT, EXPLICIT_NULL, or BLANK_STRING for that path "
                    "rather than inferring a value; an eligible card whose "
                    "required domain/population/unit_of_analysis scope is unknown "
                    "is refused instead of silently broadened"
                ),
                "status": "PASS",
            },
        },
        "required_checks": {
            "independent_review": {
                "evidence": (
                    "review.md (author: bounded implementation agent; reviewer: "
                    "the sealing agent, a distinct actor; actor_independence "
                    "between author and reviewer holds, external certification "
                    "does not)"
                ),
                "status": "PASS",
            },
            **{
                name: {"status": "PASS", "test_count": count}
                for name, count in required.items()
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
                f"{ATTEMPT_DIR}/build_i02_0001_evidence.py",
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
        "# I02-0001 independent review of bounded-agent work\n"
        "\n"
        "- Author: a bounded implementation agent (disjoint write scope, frozen\n"
        "  contracts) under the product owner's explicit instruction. Reviewer:\n"
        "  the sealing agent, which did not author this attempt; author/reviewer\n"
        "  separation holds with actor_independence=true, while external\n"
        "  actor-independent certification does not.\n"
        "- Falsifiability is mandatory before council-readiness: falsifiers are\n"
        "  checked ahead of every other required field, and an absent, empty,\n"
        "  blank, or scalar falsifier list is refused FALSIFIER_REQUIRED.\n"
        "  predictions and mechanism_path are likewise mandatory, so a frame with\n"
        "  no way to be wrong can never reach the council.\n"
        "- Scope normalization preserves unknowns without inference: a missing,\n"
        "  explicit-null, or blank scalar position becomes a canonical null while\n"
        "  list/map positions become the canonical empty [] / {}, and a typed\n"
        "  ScopeUnknown sidecar records ABSENT, EXPLICIT_NULL, or BLANK_STRING for\n"
        "  the path. Explicit empty collections are not relabelled unknown, and a\n"
        "  partial intervention keeps its nested unknowns.\n"
        "- Eligibility is fail-closed: an eligible card that retains a required\n"
        "  domain/population/unit_of_analysis unknown or an undefined construct is\n"
        "  refused FRAME_ELIGIBILITY_CONFLICT, while inbox and withdrawn cards\n"
        "  preserve their unknowns but never claim council readiness.\n"
        "- The compiler validates but never generates authority: supplied\n"
        "  insight_id, revision, created_at, registration_hash, and schema_version\n"
        "  are checked for canonical form (ID pattern, RFC 3339 with an explicit\n"
        "  offset, sha256 hex, semver) and preserved byte-for-byte; identifier,\n"
        "  timestamp, and registration-hash content generation stay outside I02.\n"
        "- Fail-closed on adversarial input: fields outside the InsightCard or\n"
        "  ScopeVector contract, non-finite scope numbers, NUL-bearing strings, a\n"
        "  domain axis outside domain_extensions, an intervention without a name,\n"
        "  and loose or invalid RFC 3339 timestamps each raise the exact finding\n"
        "  code (FRAME_FIELD_UNKNOWN, FRAME_FIELD_REQUIRED, FRAME_INPUT_INVALID,\n"
        "  SCOPE_FIELD_UNKNOWN, SCOPE_INPUT_INVALID, SCOPE_INTERVENTION_NAME_REQUIRED)\n"
        "  rather than degrading silently; a valid RFC 3339 leap second is kept.\n"
        "- Output is deterministic: canonical JSON is mapping-order independent,\n"
        "  the input proposal is never mutated, and array order is retained.\n"
        "- Disclosed non-blocking note: the compiler holds module-level enum\n"
        "  literals that match schemas/insight-card.schema.json exactly (verified\n"
        "  no drift), and the frame-gold suite cross-validates the compiled card\n"
        "  and ScopeVector against the real schemas at runtime -- the same idiom as\n"
        "  the sealed sibling I01. The enforced EF4-I22 wire-literal gate scans\n"
        "  only src/, so it does not cover this python/ component; the runtime\n"
        "  schema cross-validation is the honest guard here.\n"
        "- Integration gates at review time: ruff check clean, git diff --check\n"
        "  clean, the two required suites green at 19/19 and 12/12 (31 targeted),\n"
        "  the EF4-I22 wire-literal gate 5/5, packaging discovery PASS, full Python\n"
        "  1261/1261 and full Node 1702/1702 across the 136-file inventory. Zero\n"
        "  blocking findings.\n"
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
        "attempt_type": "I02_INSIGHTCARD_FALSIFIER_AND_SCOPEVECTOR_COMPILER",
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
            "identifier, timestamp, or registration_hash content generation: the compiler validates and preserves already-sealed values only",
            "ontology, measurement-identity, intake UI, or export-gate implementation: I03/I04 territory",
            "a canonical ScopeUnknown artifact: it is a component-local typed sidecar, not a new schema or workflow",
            "any composed code dependency on I01: it is a manifest-order dependency and the compiler imports the standard library alone (jsonschema/referencing enter at test time only)",
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
                "Author/reviewer separation holds with actor_independence=true "
                "(a bounded implementation agent authored, the sealing agent "
                "reviewed); external actor-independent certification does not."
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
        "next_action": "SEAL_I02_0001_THEN_RECOMPUTE_DAG",
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
    write_json("i02-verification.json", verification)
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
        raise SystemExit("I02-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "i02-verification.json")
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
    verification = read_json(ATTEMPT / "i02-verification.json")
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
        raise SystemExit("stored I02-0001 report is not the deterministic document")
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
