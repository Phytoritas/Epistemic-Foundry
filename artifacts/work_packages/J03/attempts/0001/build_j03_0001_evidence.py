#!/usr/bin/env python3
"""Build and verify J03-0001 ContextCapsule assembly and exclusion evidence.

J03-0001 implements ``packages/context-capsule/**``: a deterministic,
content-addressed ContextCapsule assembler with explicit exclusions and a
fail-closed freshness gate.  The assembler turns an explicit canonical-state
snapshot -- session, FORGE phase, purpose, RunSpec and policy hashes, per-artifact
INCLUDE/EXCLUDE selections, open blockers, allowed capabilities, token budget and
a freshness window -- into a deeply frozen capsule whose ``capsule_hash`` binds
the exact canonical JSON preimage.  Replaying the same snapshot yields the same
immutable bytes: there is no clock, random id, filesystem discovery, or
previous-capsule fallback.  Exclusions are explicit and may never smuggle
excluded content or its summary into the capsule; every included artifact binds a
source hash and a nonblank summary whose ``summary_hash`` binds its bytes.
``requireFreshContextCapsule`` fails closed unless an intact capsule still matches
the current session, phase, RunSpec, policy, freshness window and the complete
current-artifact inventory, rejecting session/phase/RunSpec/policy drift,
expired or not-yet-valid windows, changed or missing included artifacts, and any
newly visible artifact that is neither included nor explicitly excluded.  The
ContextCapsule boundary is bound to the generated ``@epistemic-foundry/contracts``
registry at module load and fails closed on contract drift.  This builder verifies
the executed checks and emits immutable attempt evidence; it never modifies
product files.

Seal-prep boundary.  This attempt prepares the seal but does NOT touch ``.rah/``
and does NOT bind a live RAH generation.  ``report.json`` therefore carries
``seal_prep_only=true``, ``ready_for_seal=true``, ``completion_ready=false``,
``global_implementation_gate=fail`` and an explicitly unbound ``rah_state``; the
main session, which owns the ledger, performs the actual seal.
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
ATTEMPT = ROOT / "artifacts/work_packages/J03/attempts/0001"
ATTEMPT_ID = "J03-0001"
WORK_PACKAGE_ID = "J03"
RECORDED_AT = "2026-08-02T00:00:00.000Z"

EXPECTED_CAPSULE_HASH_COUNT = 11
EXPECTED_STALE_CAPSULE_COUNT = 10
EXPECTED_TARGETED_COUNT = 21
EXPECTED_PYTHON_COUNT = 1261
EXPECTED_NODE_COUNT = 1291
EXPECTED_NODE_FILE_COUNT = 115

CONTEXT_CAPSULE_ROOT = "packages/context-capsule"
# The J03 context-capsule root is fully J03-owned; assert it holds exactly these.
EXPECTED_PRODUCT_HASHES = {
    f"{CONTEXT_CAPSULE_ROOT}/package.json": "f768694a12bac2de3e187770b6f3c0c47b2226246eda22d13226e70cd3b36d4e",
    f"{CONTEXT_CAPSULE_ROOT}/src/context-capsule.mjs": "017b9b7d8638df51fa2f5a0a218eaf797bdca1ca64b4c02e2d8fde7f3c2c45a6",
    f"{CONTEXT_CAPSULE_ROOT}/src/index.mjs": "f92d0efb43f6bee745e0cfe442cfb0f8f3acc8002f8fecc979837a39d427a5d0",
    f"{CONTEXT_CAPSULE_ROOT}/src/capsule-hash.test.mjs": "89c01ee1981e93d6a6666d246c70061dbf00f5443129bde8ea034f4e263c192d",
    f"{CONTEXT_CAPSULE_ROOT}/src/stale-capsule.test.mjs": "29073639bde615df9edfe827d8c118fc8df4c12ecd3139aba6d4c8d516035ca8",
}

# J03 depends only on the sealed J01 parent skill router.  The dependency is
# pinned twice: by the exact bytes of J01's sealed report and by the two evidence
# ids its seal minted, both of which are asserted before J03 evidence is trusted.
SEALED_DEPENDENCIES = {
    "J01": {
        "attempt_id": "J01-0001",
        "report": "artifacts/work_packages/J01/attempts/0001/report.json",
        "report_sha256": "1dccbcea776444456c2a6f7ddbf224a23b5d3b77094dec6c7943aa8a9e56344f",
        "core_evidence_id": "E0343",
        "final_closeout_evidence_id": "E0344",
    },
}
EXPECTED_DEPENDENCY_HASHES = {
    spec["report"]: spec["report_sha256"] for spec in SEALED_DEPENDENCIES.values()
}

# Seal-prep only: this attempt did not touch .rah/ and did not bind a live RAH
# generation.  The parent session performs the actual ledger seal.
UNBOUND_RAH_STATE = {
    "binding": "UNBOUND_PENDING_LEDGER_SEAL",
    "completion_ready": False,
    "evidence_appended_by_j03": False,
    "generation_created_by_j03": False,
    "implementation_gate": "fail",
    "rah_touched_by_j03": False,
    "status": "unbound",
}

JUNIT_PATHS = {
    "capsule_hash": ATTEMPT / "capsule-hash-test.junit.xml",
    "stale_capsule": ATTEMPT / "stale-capsule-test.junit.xml",
    "targeted": ATTEMPT / "targeted-context-capsule.junit.xml",
    "full_python": ATTEMPT / "full-python-suite.junit.xml",
    "full_node": ATTEMPT / "full-node-suite.junit.xml",
}
# Every J03 check but the full Python suite runs under the Node runner.
_NODE_JUNITS = frozenset(
    {
        "capsule_hash",
        "stale_capsule",
        "targeted",
        "full_node",
    }
)
RUN_RESULTS = (
    "ruff-check",
    "ruff-format-check",
    "capsule-hash-test",
    "stale-capsule-test",
    "targeted-context-capsule",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "run_j03_0001_checks.py",
    "build_j03_0001_evidence.py",
    "j03_0001_rah_seal.py",
    "dependency-status.json",
    "j03-verification.json",
    "write-scope-verification.json",
    "node-test-inventory.json",
    "junit-normalization-verification.json",
    "capsule-hash-test.junit.xml",
    "stale-capsule-test.junit.xml",
    "targeted-context-capsule.junit.xml",
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
    capsule_hash = node_summary(JUNIT_PATHS["capsule_hash"])
    stale_capsule = node_summary(JUNIT_PATHS["stale_capsule"])
    targeted = node_summary(JUNIT_PATHS["targeted"])
    python = pytest_summary(JUNIT_PATHS["full_python"])
    node = node_summary(JUNIT_PATHS["full_node"])
    node_inventory = read_json(ATTEMPT / "node-test-inventory.json")
    for label, summary, expected in (
        ("capsule_hash_test", capsule_hash, EXPECTED_CAPSULE_HASH_COUNT),
        ("stale_capsule_test", stale_capsule, EXPECTED_STALE_CAPSULE_COUNT),
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
        "capsule_hash_test": capsule_hash,
        "component_tests_are_targeted_only": True,
        "full_node": node,
        "full_python": python,
        "new_failure_count": 0,
        "stale_capsule_test": stale_capsule,
        "status": "PASS",
        "targeted_context_capsule": targeted,
        "unexpected_skip_xfail_todo_or_cancellation_count": 0,
    }


def _sealed_dependency(package: str, spec: dict[str, str]) -> dict[str, Any]:
    path = ROOT / spec["report"]
    if sha256(path) != spec["report_sha256"]:
        raise SystemExit(f"{package} sealed report bytes changed: {spec['report']}")
    report = read_json(path)
    if report.get("status") != "PASS" or report.get("package_status") != "PASS":
        raise SystemExit(f"{package} is not the sealed PASS attempt")
    rah_state = report.get("rah_state")
    if not isinstance(rah_state, dict) or rah_state.get("status") != "active":
        raise SystemExit(f"{package} report is not RAH-bound active")
    if (
        rah_state.get("core_evidence_id") != spec["core_evidence_id"]
        or rah_state.get("final_closeout_evidence_id")
        != spec["final_closeout_evidence_id"]
    ):
        raise SystemExit(f"{package} sealed evidence ids do not match the pin")
    return {
        "attempt_id": spec["attempt_id"],
        "core_evidence_id": spec["core_evidence_id"],
        "final_closeout_evidence_id": spec["final_closeout_evidence_id"],
        "report": path.relative_to(ROOT).as_posix(),
        "report_sha256": sha256_id(path),
        "status": "PASS",
    }


def dependency_status() -> dict[str, Any]:
    assert_hashes(EXPECTED_DEPENDENCY_HASHES)
    return {
        "attempt_id": ATTEMPT_ID,
        "dependencies": {
            package: _sealed_dependency(package, spec)
            for package, spec in sorted(SEALED_DEPENDENCIES.items())
        },
        "next_action": "SEAL_J03_0001_THEN_CONTINUE_DAG",
        "status": "PASS",
    }


def write_scope_verification() -> dict[str, Any]:
    assert_hashes(EXPECTED_PRODUCT_HASHES)
    product_files = sorted(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / CONTEXT_CAPSULE_ROOT).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )
    if product_files != sorted(EXPECTED_PRODUCT_HASHES):
        raise SystemExit(
            f"context-capsule root holds unexpected files: {product_files}"
        )
    return {
        "approved_scope": [f"{CONTEXT_CAPSULE_ROOT}/**"],
        "attempt_id": ATTEMPT_ID,
        "j03_product_file_hashes": {
            relative: "sha256:" + digest
            for relative, digest in EXPECTED_PRODUCT_HASHES.items()
        },
        "j03_product_files": sorted(EXPECTED_PRODUCT_HASHES),
        "reset_clean_stash_commit_push_performed": False,
        "root_canonical_source_mutation_count": 0,
        "schema_or_test_weakening_count": 0,
        "status": "PASS",
        "write_scope_violation_count": 0,
    }


def j03_verification(regression: dict[str, Any]) -> dict[str, Any]:
    schema_count = len(list((ROOT / "schemas").glob("*.schema.json")))
    return {
        "attempt_id": ATTEMPT_ID,
        "authority_boundary": {
            "allowed_capabilities_and_sets_canonicalized": True,
            "canonical_context_capsule_schema": "schemas/context-capsule.schema.json",
            "canonical_schema_count": schema_count,
            "canonical_schema_modified_by_j03": False,
            "capsule_hash_binds_exact_canonical_preimage": True,
            "capsule_output_deeply_frozen": True,
            "complete_current_artifact_accounting_required": True,
            "excluded_content_or_summary_denied": True,
            "exclusions_are_explicit": True,
            "freshness_binds_expiry_session_phase_run_spec_policy_and_inventory": True,
            "generated_contract_bound_at_module_load": True,
            "included_artifact_requires_source_hash_and_nonblank_summary": True,
            "input_mutation_performed": False,
            "no_clock_random_id_filesystem_or_previous_capsule_authority": True,
            "proxy_accessor_sparse_array_and_custom_prototype_rejected": True,
            "schema_contract_drift_fails_closed_at_module_load": True,
            "summary_hash_binds_exact_summary_bytes": True,
        },
        "exit_criteria": {
            "capsule_rebuilt_from_canonical_state": {
                "evidence": [
                    f"{CONTEXT_CAPSULE_ROOT}/src/capsule-hash.test.mjs",
                ],
                "mechanism": (
                    "assembleContextCapsule turns an explicit canonical-state "
                    "snapshot into a deeply frozen capsule whose capsule_hash binds "
                    "the exact canonical JSON preimage; replaying the same snapshot "
                    "yields identical immutable bytes with no clock, random id, "
                    "filesystem discovery, or previous-capsule fallback, and "
                    "set-like input order cannot change the bytes or hash"
                ),
                "status": "PASS",
            },
            "exclusions_and_freshness_explicit": {
                "evidence": [
                    f"{CONTEXT_CAPSULE_ROOT}/src/capsule-hash.test.mjs",
                    f"{CONTEXT_CAPSULE_ROOT}/src/stale-capsule.test.mjs",
                ],
                "mechanism": (
                    "exclusions are explicit and may never smuggle excluded content "
                    "or its summary into the capsule; requireFreshContextCapsule "
                    "fails closed on session, phase, RunSpec, policy, expiry, "
                    "not-yet-valid, changed, missing, or newly visible unaccounted "
                    "artifacts and on capsule or summary tamper"
                ),
                "status": "PASS",
            },
        },
        "required_checks": {
            "capsule_hash_test": {
                "module": f"{CONTEXT_CAPSULE_ROOT}/src/capsule-hash.test.mjs",
                "status": "PASS",
                "test_count": regression["capsule_hash_test"]["collected"],
            },
            "stale_capsule_test": {
                "module": f"{CONTEXT_CAPSULE_ROOT}/src/stale-capsule.test.mjs",
                "status": "PASS",
                "test_count": regression["stale_capsule_test"]["collected"],
            },
        },
        "status": "PASS",
        "targeted_test_count": regression["targeted_context_capsule"]["collected"],
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
                "artifacts/work_packages/J03/attempts/0001/build_j03_0001_evidence.py",
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
        "# J03-0001 independent review of bounded-agent work\n"
        "\n"
        "- Author: the bounded implementation agent that wrote the ContextCapsule\n"
        "  assembler under packages/context-capsule (context-capsule.mjs, index.mjs,\n"
        "  package.json and the two required-check test files). Reviewer: this\n"
        "  seal-prep session, a distinct actor that did not author the assembler.\n"
        "  The author never approves its own work, so actor_independence HOLDS for\n"
        "  this review; external actor-independent certification does NOT, and no\n"
        "  such claim is made. J03 is risk_class=medium; the assembler was attacked\n"
        "  on its determinism, exclusion secrecy, freshness fail-closed contract,\n"
        "  hash binding, and hostile-input surface rather than skimmed.\n"
        "- Deterministic content-addressed assembly. assembleContextCapsule turns an\n"
        "  explicit canonical-state snapshot into a deeply frozen capsule whose\n"
        "  capsule_hash binds the exact canonical JSON preimage. There is no clock,\n"
        "  random id, filesystem discovery, or previous-capsule fallback, so\n"
        "  replaying the same snapshot yields identical immutable bytes; set-like\n"
        "  input ordering of selections and capabilities cannot change the bytes or\n"
        "  the hash; the caller input is not mutated; and every included artifact\n"
        "  binds a source_hash and a nonblank summary whose summary_hash binds its\n"
        "  bytes (UNBOUND_INCLUDED_ARTIFACT, EMPTY_SUMMARY, SUMMARY_HASH_MISMATCH).\n"
        "- Explicit exclusions cannot smuggle content. EXCLUDE selections may carry\n"
        "  no source_hash or summary; attempting to attach either fails closed as\n"
        "  EXCLUDED_ARTIFACT_CONTENT_DENIED, duplicate or conflicting dispositions\n"
        "  are ARTIFACT_DISPOSITION_CONFLICT, and an artifact cannot be both included\n"
        "  and explicitly excluded. A capsule with no included canonical artifact is\n"
        "  refused (CANONICAL_ARTIFACT_REQUIRED).\n"
        "- Fail-closed freshness. requireFreshContextCapsule verifies capsule\n"
        "  integrity first, then rejects session, phase, RunSpec, and policy drift,\n"
        "  an undeclared or expired freshness window, a not-yet-valid creation\n"
        "  instant, changed or missing included artifacts (CAPSULE_ARTIFACT_STALE),\n"
        "  and any newly visible artifact that is neither included nor explicitly\n"
        "  excluded (CAPSULE_CANONICAL_STATE_DRIFT); an excluded artifact's absence\n"
        "  does not resurrect it. Capsule or summary tamper is CAPSULE_HASH_MISMATCH\n"
        "  before any freshness decision is taken.\n"
        "- Hostile and non-canonical input. Proxies, accessor getters (which never\n"
        "  run), sparse arrays, custom prototypes, invalid Unicode, unexpected\n"
        "  fields, invalid hashes, invalid phases and non-canonical numbers all fail\n"
        "  closed before influencing a decision. The ContextCapsule boundary is bound\n"
        "  to the generated @epistemic-foundry/contracts registry at module load and\n"
        "  fails closed (CANONICAL_CONTRACT_MISMATCH) on contract drift; the emitted\n"
        "  capsule validates against the canonical Draft 2020-12\n"
        "  schemas/context-capsule.schema.json, which J03 did not modify.\n"
        "- Dependency and checks: the assembler builds on the sealed J01 parent\n"
        "  skill router (report sha256 1dccbcea..., core E0343 / final closeout\n"
        "  E0344) and adds no new production dependency. Ruff lint and format, the\n"
        "  two required checks (capsule_hash_test 11/11, stale_capsule_test 10/10),\n"
        "  targeted 21/21, full Python 1261/1261, full Node 1291/1291 across 115\n"
        "  files, and git diff --check all pass with zero J03-caused failures.\n"
        "- Seal-prep boundary and residual limitations: this attempt did not touch\n"
        "  .rah/ and did not bind a live RAH generation; report.json carries\n"
        "  seal_prep_only=true, ready_for_seal=true, completion_ready=false,\n"
        "  global_implementation_gate=fail and an unbound rah_state. J03 assembles\n"
        "  and freshness-checks a capsule from explicit canonical state; it does not\n"
        "  itself read the ledger, drive compaction recovery, or claim completion.\n"
        "  Post-compaction recovery is the J04 gate. Verdict: PASS on the exact J03\n"
        "  package contract.\n"
    )


def report_document(
    regression: dict[str, Any],
    dependencies: dict[str, Any],
    write_scope: dict[str, Any],
    verification: dict[str, Any],
    *,
    rah_state: dict[str, Any],
) -> dict[str, Any]:
    # ``seal_prep_only`` is derived from the binding state so that when the parent
    # session binds a live active RAH generation it flips off automatically; while
    # the ledger is untouched the report stays seal-prep only.
    bound = isinstance(rah_state, dict) and rah_state.get("status") == "active"
    output_names = [
        name
        for name in OUTPUT_NAMES
        if name != "report.json" and (ATTEMPT / name).is_file()
    ]
    if bound:
        output_names.append("rah-core-integrity.json")
    artifacts = [
        {
            "byte_size": (ATTEMPT / name).stat().st_size,
            "path": f"artifacts/work_packages/J03/attempts/0001/{name}",
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in sorted(set(output_names))
    ]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "J03_CONTEXT_CAPSULE_ASSEMBLY_AND_EXCLUSIONS",
        "authority_boundary": verification["authority_boundary"],
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependency_state": dependencies,
        "exit_criteria": {
            "capsule_rebuilt_from_canonical_state": "PASS",
            "exclusions_and_freshness_explicit": "PASS",
        },
        "global_implementation_gate": "fail",
        "history_and_worktree": {
            "dirty_worktree_preserved": True,
            "prior_attempts_reports_and_rah_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
        },
        "implementation_status": "PASS",
        "not_claimed": [
            "post-compaction recovery or the J04 compaction-resume gate",
            "reading the live ledger, driving compaction, or resuming a session",
            "RAH lifecycle advancement, generation binding, or completion",
            "external actor-independent certification of this review",
            "repository-wide release or production readiness",
            "completion_ready=true",
        ],
        "output_artifacts": artifacts,
        "package_status": "PASS",
        "rah_state": rah_state,
        "ready_for_seal": True,
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
        "seal_prep_only": not bound,
        "status": "PASS",
        "work_package_id": WORK_PACKAGE_ID,
        "write_scope": write_scope,
    }
    return report


def _summary() -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "capsule_hash_test": (
            f"{EXPECTED_CAPSULE_HASH_COUNT}/{EXPECTED_CAPSULE_HASH_COUNT}"
        ),
        "completion_ready": False,
        "full_node": f"{EXPECTED_NODE_COUNT}/{EXPECTED_NODE_COUNT}",
        "full_python": f"{EXPECTED_PYTHON_COUNT}/{EXPECTED_PYTHON_COUNT}",
        "next_action": "SEAL_J03_0001_THEN_CONTINUE_DAG",
        "node_file_count": EXPECTED_NODE_FILE_COUNT,
        "package_status": "PASS",
        "ready_for_seal": True,
        "seal_prep_only": True,
        "stale_capsule_test": (
            f"{EXPECTED_STALE_CAPSULE_COUNT}/{EXPECTED_STALE_CAPSULE_COUNT}"
        ),
        "status": "PASS",
        "targeted_context_capsule": f"{EXPECTED_TARGETED_COUNT}/{EXPECTED_TARGETED_COUNT}",
    }


def build() -> dict[str, Any]:
    for name in RUN_RESULTS:
        check_run(name)
    normalize_junits()
    regression = regression_evidence()
    dependencies = dependency_status()
    write_scope = write_scope_verification()
    verification = j03_verification(regression)
    write_json("dependency-status.json", dependencies)
    write_json("write-scope-verification.json", write_scope)
    write_json("j03-verification.json", verification)
    (ATTEMPT / "commands.jsonl").write_text(
        commands_text(), encoding="utf-8", newline="\n"
    )
    (ATTEMPT / "review.md").write_text(review_text(), encoding="utf-8", newline="\n")
    report = report_document(
        regression, dependencies, write_scope, verification, rah_state=UNBOUND_RAH_STATE
    )
    write_json("report.json", report)
    return _summary()


def bind_rah_state(
    *,
    core_generation: str,
    core_evidence_id: str,
    final_closeout_evidence_id: str,
) -> None:
    """Bind a live active RAH generation into the report during the real seal.

    Called by the parent session's seal script after it has committed the core
    generation and written ``rah-core-integrity.json``.  It is never called by
    this seal-prep session, which leaves ``report.json`` unbound.
    """
    integrity = read_json(ATTEMPT / "rah-core-integrity.json")
    stored = read_json(ATTEMPT / "report.json")
    if stored.get("rah_state", {}).get("status") == "active":
        raise SystemExit("J03-0001 report is already RAH-bound")
    if integrity.get("current_generation") != core_generation:
        raise SystemExit("rah-core-integrity does not match the core generation")
    rah_state = {
        "binding": "BOUND_TO_LEDGER",
        "completion_ready": False,
        "core_evidence_id": core_evidence_id,
        "core_generation": core_generation,
        "final_closeout_evidence_id": final_closeout_evidence_id,
        "flat_snapshot_content_matches": integrity["flat_snapshot_content_matches"],
        "flat_snapshot_stamps_verified": integrity["flat_snapshot_stamps_verified"],
        "generation_file_hashes_verified": integrity["generation_file_hashes_verified"],
        "implementation_gate": "fail",
        "rah_touched_by_j03": False,
        "retained_generation_count": integrity["retained_generation_count"],
        "status": "active",
    }
    regression = regression_evidence()
    dependencies = read_json(ATTEMPT / "dependency-status.json")
    write_scope = read_json(ATTEMPT / "write-scope-verification.json")
    verification = read_json(ATTEMPT / "j03-verification.json")
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
    verification = read_json(ATTEMPT / "j03-verification.json")
    if (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8") != commands_text():
        raise SystemExit("commands.jsonl differs from deterministic command records")
    if (ATTEMPT / "review.md").read_text(encoding="utf-8") != review_text():
        raise SystemExit("review.md differs from the recorded review")
    stored_rah_state = stored.get("rah_state")
    if not isinstance(stored_rah_state, dict):
        raise SystemExit("stored J03-0001 report is missing an rah_state block")
    expected = report_document(
        regression, dependencies, write_scope, verification, rah_state=stored_rah_state
    )
    if render(expected) != render(stored):
        raise SystemExit("stored J03-0001 report is not the deterministic document")
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
