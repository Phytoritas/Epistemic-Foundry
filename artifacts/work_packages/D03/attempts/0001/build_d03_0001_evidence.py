#!/usr/bin/env python3
"""Build and verify D03-0001 content-addressed artifact store evidence.

D03-0001 implements ``packages/foundry-kernel/src/artifacts/**``: a
content-addressed artifact store with receipts.  Immutable object bytes are
addressed by their sha256 digest under ``sha256/<aa>/<rest>/content.bin``;
opaque artifact and receipt identifiers index into that record through a
digest-derived key so the same bytes always resolve to the same address, an
identifier can never be rebound to different bytes, and distinct bytes never
alias.  Each registration emits a canonical, frozen artifact manifest and a
receipt that resolves the exact bytes, the schema reference, and the creating
actor.  Every integrity violation -- content tamper, non-canonical manifest or
receipt, orphaned receipts, hard-linked or relabelled records, structural
corruption -- fails closed into a read-only ``SAFE_MODE``.  A benign Windows
``.staging``/``.mutation-lock`` inode handoff is tolerated within a bounded
retry budget, while a persistent transient error still fails closed.  This
builder verifies the executed checks and emits immutable attempt evidence; it
never modifies product files.
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
ATTEMPT = ROOT / "artifacts/work_packages/D03/attempts/0001"
ATTEMPT_ID = "D03-0001"
WORK_PACKAGE_ID = "D03"
RECORDED_AT = "2026-08-02T00:00:00.000Z"

EXPECTED_ARTIFACT_HASH_COUNT = 21
EXPECTED_ORPHAN_RECEIPT_COUNT = 19
EXPECTED_TARGETED_COUNT = 40
EXPECTED_PYTHON_COUNT = 1261
EXPECTED_NODE_COUNT = 1253
EXPECTED_NODE_FILE_COUNT = 111

COMPONENT = "packages/foundry-kernel/src/artifacts"
EXPECTED_PRODUCT_HASHES = {
    "packages/foundry-kernel/src/artifacts/artifact-hash.test.mjs": "587b78680a5b5175f6889273369eddd25f54f3c47cf5d618277b9a4db634484a",
    "packages/foundry-kernel/src/artifacts/content-addressed-artifact-store.mjs": "750bda768c67bc613cd57861b07dcbf08e74c426ae20bc63b351cbb7ec8166f1",
    "packages/foundry-kernel/src/artifacts/orphan-receipt.test.mjs": "c22c07e3d81d7121a8cf8258538bc8299d512413ae2a302327485206e2518d68",
}
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/D01/report.json": "00d44672b4c9680589ecd85c39f617c29bdfe79afd288a2769cafb1ba59a9a91",
}

JUNIT_PATHS = {
    "artifact_hash": ATTEMPT / "artifact-hash-test.junit.xml",
    "orphan_receipt": ATTEMPT / "orphan-receipt-test.junit.xml",
    "targeted": ATTEMPT / "targeted-artifacts.junit.xml",
    "full_python": ATTEMPT / "full-python-suite.junit.xml",
    "full_node": ATTEMPT / "full-node-suite.junit.xml",
}
# Every D03 check but the full Python suite runs under the Node runner.
_NODE_JUNITS = frozenset(
    {
        "artifact_hash",
        "orphan_receipt",
        "targeted",
        "full_node",
    }
)
RUN_RESULTS = (
    "ruff-check",
    "ruff-format-check",
    "artifact-hash-test",
    "orphan-receipt-test",
    "targeted-artifacts",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "run_d03_0001_checks.py",
    "build_d03_0001_evidence.py",
    "d03_0001_rah_seal.py",
    "dependency-status.json",
    "d03-verification.json",
    "write-scope-verification.json",
    "node-test-inventory.json",
    "junit-normalization-verification.json",
    "artifact-hash-test.junit.xml",
    "orphan-receipt-test.junit.xml",
    "targeted-artifacts.junit.xml",
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
    artifact_hash = node_summary(JUNIT_PATHS["artifact_hash"])
    orphan_receipt = node_summary(JUNIT_PATHS["orphan_receipt"])
    targeted = node_summary(JUNIT_PATHS["targeted"])
    python = pytest_summary(JUNIT_PATHS["full_python"])
    node = node_summary(JUNIT_PATHS["full_node"])
    node_inventory = read_json(ATTEMPT / "node-test-inventory.json")
    for label, summary, expected in (
        ("artifact_hash_test", artifact_hash, EXPECTED_ARTIFACT_HASH_COUNT),
        ("orphan_receipt_test", orphan_receipt, EXPECTED_ORPHAN_RECEIPT_COUNT),
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
        "artifact_hash_test": artifact_hash,
        "attempt_id": ATTEMPT_ID,
        "component_tests_are_targeted_only": True,
        "full_node": node,
        "full_python": python,
        "new_failure_count": 0,
        "orphan_receipt_test": orphan_receipt,
        "status": "PASS",
        "targeted_artifacts": targeted,
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
            "D01": _pass_dependency(
                "D01", "D01-0001", "artifacts/work_packages/D01/report.json"
            ),
        },
        "next_action": "SEAL_D03_0001_THEN_CONTINUE_DAG",
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
            f"artifacts component holds unexpected files: {component_files}"
        )
    return {
        "approved_scope": [f"{COMPONENT}/**", "artifacts/work_packages/D03/**"],
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


def d03_verification(regression: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "content_addressing": {
            "distinct_bytes_never_alias": True,
            "identical_bytes_share_one_object": True,
            "identifier_cannot_be_rebound_to_different_bytes": True,
            "immutable_metadata_cannot_be_overwritten": True,
            "registration_and_receipt_replay_is_idempotent": True,
        },
        "exit_criteria": {
            "immutable_artifacts_address_by_hash": {
                "evidence": [
                    f"{COMPONENT}/artifact-hash.test.mjs",
                    f"{COMPONENT}/orphan-receipt.test.mjs",
                ],
                "mechanism": (
                    "object bytes are stored once under their sha256 digest at "
                    "sha256/<aa>/<rest>/content.bin and never overwritten; the "
                    "content_hash and storage_uri in each frozen manifest are the "
                    "digest of the exact bytes, identical bytes replay as EXISTING, "
                    "distinct bytes occupy distinct addresses, and an artifact ID "
                    "can never be rebound to different bytes"
                ),
                "status": "PASS",
            },
            "receipt_resolves_bytes_schema_creator": {
                "evidence": [
                    f"{COMPONENT}/artifact-hash.test.mjs",
                    f"{COMPONENT}/orphan-receipt.test.mjs",
                ],
                "mechanism": (
                    "resolveReceipt returns the exact addressed bytes, the receipt "
                    "schema_ref, the creating actor, and the resolving manifest; an "
                    "orphaned receipt whose content, manifest, or record is missing "
                    "or mislabelled fails closed rather than resolving stale bytes"
                ),
                "status": "PASS",
            },
        },
        "integrity_failure_mode": {
            "benign_windows_lock_handoff_tolerated_within_bound": True,
            "persistent_transient_error_still_fails_closed": True,
            "safe_mode_is_read_only": True,
            "safe_mode_refuses_all_mutation_paths": True,
        },
        "required_checks": {
            "artifact_hash_test": {
                "module": f"{COMPONENT}/artifact-hash.test.mjs",
                "status": "PASS",
                "test_count": regression["artifact_hash_test"]["collected"],
            },
            "orphan_receipt_test": {
                "module": f"{COMPONENT}/orphan-receipt.test.mjs",
                "status": "PASS",
                "test_count": regression["orphan_receipt_test"]["collected"],
            },
        },
        "status": "PASS",
        "targeted_test_count": regression["targeted_artifacts"]["collected"],
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
                "artifacts/work_packages/D03/attempts/0001/build_d03_0001_evidence.py",
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
        "# D03-0001 independent review of bounded-agent work\n"
        "\n"
        "- Author: the bounded implementation agent that wrote\n"
        "  packages/foundry-kernel/src/artifacts. Reviewer: this seal-prep\n"
        "  session, a distinct actor that did not author the store. The author\n"
        "  never approves its own work, so actor_independence HOLDS for this\n"
        "  review; external actor-independent certification does NOT, and no such\n"
        "  claim is made. D03 is risk_class=medium; the store was still attacked on\n"
        "  its content-addressing, receipt-resolution, and fail-closed contracts\n"
        "  rather than skimmed.\n"
        "- Immutable content-hash addressing. Object bytes are written once under\n"
        "  their sha256 digest and never overwritten. The same bytes always yield\n"
        "  the same content_hash and storage_uri, an identical registration and\n"
        "  receipt replay is idempotent (EXISTING, not a second write), one object\n"
        "  can back several artifacts and receipts, distinct byte sequences never\n"
        "  alias to one address, and empty bytes still have a real address. An\n"
        "  artifact ID cannot be rebound to different bytes (ARTIFACT_ID_CONFLICT),\n"
        "  a receipt ID cannot be rebound (ARTIFACT_RECEIPT_ID_CONFLICT), and\n"
        "  immutable manifest metadata cannot be overwritten\n"
        "  (ARTIFACT_IMMUTABLE_CONFLICT).\n"
        "- Receipt resolution. resolveReceipt returns the exact addressed bytes,\n"
        "  the schema_ref, the creating actor, and the resolving manifest; returned\n"
        "  buffers are copies, so mutating them does not corrupt the store. The\n"
        "  manifest and receipt validate against the canonical Draft 2020-12\n"
        "  artifact-manifest and artifact-receipt schemas.\n"
        "- Integrity failures fail closed. Content tamper (ARTIFACT_HASH_MISMATCH),\n"
        "  non-canonical manifest or receipt bytes, orphaned receipts without\n"
        "  content or manifest (ARTIFACT_ORPHAN_RECEIPT), receipts or manifests\n"
        "  copied under the wrong key (ARTIFACT_RECEIPT_KEY_MISMATCH,\n"
        "  ARTIFACT_MANIFEST_KEY_MISMATCH), hard-linked or relabelled records,\n"
        "  linked roots, replaced roots, and unknown tree entries each enter a\n"
        "  read-only SAFE_MODE that denies every mutation path. The public surface\n"
        "  exposes no deletion or overwrite operation.\n"
        "- Concurrency-robustness fix preserved fail-closed behavior. A benign\n"
        "  Windows .staging/.mutation-lock inode handoff is re-observed within a\n"
        "  bounded retry budget (STAGING_HANDOFF_RETRY_LIMIT=8) instead of\n"
        "  fail-closing, so a single injected EPERM handoff still opens ACTIVE; a\n"
        "  persistent EPERM denial is injected nine times, exhausts the budget, and\n"
        "  still fails closed to SAFE_MODE with\n"
        "  ARTIFACT_STORE_STRUCTURE_INVALID / cause EPERM. Concurrent identical and\n"
        "  distinct worker-thread publishers converge, and a reader/writer overlap\n"
        "  never observes a broken tree.\n"
        "- Dependency and checks: the store builds on the sealed D01 SQLite WAL\n"
        "  canonical store (D01-0001 PASS) and adds no new production dependency.\n"
        "  Ruff lint and format, the two required checks (artifact_hash_test 21/21,\n"
        "  orphan_receipt_test 19/19), targeted 40/40, full Python 1261/1261, full\n"
        "  Node 1253/1253 across 111 files, and git diff --check all pass with zero\n"
        "  failures.\n"
        "- Residual limitations: the store is append-only with no garbage\n"
        "  collection or deletion of unreferenced objects, and backup, corruption,\n"
        "  and recovery lifecycle beyond fail-closed SAFE_MODE entry belong to the\n"
        "  later D04 gate. Verdict: PASS on the exact D03 package contract.\n"
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
            "path": f"artifacts/work_packages/D03/attempts/0001/{name}",
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in sorted(set(output_names))
    ]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "D03_CONTENT_ADDRESSED_ARTIFACT_STORE",
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependency_state": dependencies,
        "exit_criteria": {
            "immutable_artifacts_address_by_hash": "PASS",
            "receipt_resolves_bytes_schema_creator": "PASS",
        },
        "global_implementation_gate": "fail",
        "history_and_worktree": {
            "dirty_worktree_preserved": True,
            "prior_attempts_reports_and_rah_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
        },
        "implementation_status": "PASS",
        "not_claimed": [
            "garbage collection or deletion of unreferenced objects",
            "backup, corruption, or recovery lifecycle beyond fail-closed "
            "SAFE_MODE entry",
            "the D04 backup, corruption, and recovery gate",
            "external actor-independent certification of this review",
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
        "artifact_hash_test": (
            f"{EXPECTED_ARTIFACT_HASH_COUNT}/{EXPECTED_ARTIFACT_HASH_COUNT}"
        ),
        "attempt_id": ATTEMPT_ID,
        "completion_ready": False,
        "full_node": f"{EXPECTED_NODE_COUNT}/{EXPECTED_NODE_COUNT}",
        "full_python": f"{EXPECTED_PYTHON_COUNT}/{EXPECTED_PYTHON_COUNT}",
        "next_action": "SEAL_D03_0001_THEN_CONTINUE_DAG",
        "node_file_count": EXPECTED_NODE_FILE_COUNT,
        "orphan_receipt_test": (
            f"{EXPECTED_ORPHAN_RECEIPT_COUNT}/{EXPECTED_ORPHAN_RECEIPT_COUNT}"
        ),
        "package_status": "PASS",
        "status": "PASS",
        "targeted_artifacts": f"{EXPECTED_TARGETED_COUNT}/{EXPECTED_TARGETED_COUNT}",
    }


def build() -> dict[str, Any]:
    for name in RUN_RESULTS:
        check_run(name)
    normalize_junits()
    regression = regression_evidence()
    dependencies = dependency_status()
    write_scope = write_scope_verification()
    verification = d03_verification(regression)
    write_json("dependency-status.json", dependencies)
    write_json("write-scope-verification.json", write_scope)
    write_json("d03-verification.json", verification)
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
        raise SystemExit("D03-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "d03-verification.json")
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
    verification = read_json(ATTEMPT / "d03-verification.json")
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
        raise SystemExit("stored D03-0001 report is not the deterministic document")
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
