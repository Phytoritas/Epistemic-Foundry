#!/usr/bin/env python3
"""Build and verify fail-closed evidence for K02-0001.

This verifier binds the component-local parser adapters to the exact K02
manifest contract, sealed K01 dependency, fixed parser fixtures, repository
regression receipts, and a primary-session separate adversarial review.
It never invokes a live parser service or treats a fallback as canonical truth.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/K02/attempts/0001"
ATTEMPT_ID = "K02-0001"
WORK_PACKAGE_ID = "K02"
MANIFEST = ROOT / "manifests/development_manifest.yaml"
RECEIPT_SCHEMA = ROOT / "schemas/artifact-receipt.schema.json"
K01_REPORT = ROOT / "artifacts/work_packages/K01/attempts/0002/report.json"
POST_K01_DAG = (
    ROOT
    / "artifacts/work_packages/K01/attempts/0002/"
    "post-k01-0002-dag-reconciliation.json"
)
POST_K01_LEDGER = (
    ROOT
    / ".rah/ralph/generations/000031-46c5cc7c/evidence_ledger.json"
)
EXPECTED_K01_REPORT_HASH = (
    "sha256:e2132964003c019599e6e5ef130ea2e8d933e08e94481d68864038d1e82a2b3b"
)
EXPECTED_POST_K01_DAG_HASH = (
    "sha256:0179528c9b07ee4df4b73467b3b0ec6a75806836f48e27075b1faf8f24d5461c"
)
PRODUCT_FILES = (
    "python/epistemic_foundry/ingest/parsers/__init__.py",
    "python/epistemic_foundry/ingest/parsers/adapters.py",
    "python/epistemic_foundry/ingest/parsers/test_fallback_status.py",
    "python/epistemic_foundry/ingest/parsers/test_parser_fixture_benchmark.py",
)
OUTPUT_NAMES = (
    "parser-verification.json",
    "fallback-status-verification.json",
    "disagreement-verification.json",
    "full-regression-impact.json",
    "write-scope-verification.json",
    "dependency-status.json",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_id(path: Path) -> str:
    return "sha256:" + sha256(path)


def bytes_hash(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return bytes_hash(encoded)


def canonical_hash_excluding(value: dict[str, Any], excluded: str) -> str:
    return canonical_hash({key: item for key, item in value.items() if key != excluded})


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


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(value), encoding="utf-8", newline="\n")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8", newline="\n")


def recorded_at() -> str:
    marker = ATTEMPT / "attempt-metadata.json"
    if marker.is_file():
        value = read_json(marker).get("recorded_at_utc")
        if isinstance(value, str):
            return value
        raise SystemExit("K02 attempt metadata is invalid")
    now = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )
    write_json(
        marker,
        {
            "attempt_id": ATTEMPT_ID,
            "recorded_at_utc": now,
            "work_package_id": WORK_PACKAGE_ID,
        },
    )
    return now


def manifest_contract() -> dict[str, Any]:
    document = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    packages = document.get("work_packages") if isinstance(document, dict) else None
    if not isinstance(packages, list):
        raise SystemExit("development manifest has no work_packages list")
    rows = [row for row in packages if isinstance(row, dict) and row.get("id") == "K02"]
    if len(rows) != 1:
        raise SystemExit("development manifest must contain exactly one K02")
    row = rows[0]
    expected = {
        "depends_on": ["K01"],
        "write_scope": ["python/epistemic_foundry/ingest/parsers/**"],
        "exit_criteria": ["parser versions pinned", "disagreement retained"],
        "required_checks": ["parser_fixture_benchmark", "fallback_status_test"],
        "independent_review": "required",
        "risk_class": "medium",
    }
    actual = {key: row.get(key) for key in expected}
    if actual != expected:
        raise SystemExit(f"K02 manifest contract changed: {actual!r}")
    return {
        "depends_on": actual["depends_on"],
        "exit_criteria": actual["exit_criteria"],
        "required_checks": actual["required_checks"],
        "risk_class": actual["risk_class"],
        "status": "PASS",
        "write_scope": actual["write_scope"],
    }


def import_component() -> tuple[Any, Any, Any]:
    component_parent = ROOT / "python/epistemic_foundry/ingest"
    sys.path.insert(0, str(component_parent))
    try:
        import parsers  # type: ignore[import-not-found]
        from parsers import test_fallback_status as fallback_fixtures  # type: ignore[import-not-found]
        from parsers import test_parser_fixture_benchmark as parser_fixtures  # type: ignore[import-not-found]
    except ImportError as error:
        raise SystemExit(f"cannot import K02 component: {error}") from error
    finally:
        sys.path.pop(0)
    return parsers, parser_fixtures, fallback_fixtures


def parser_verification() -> dict[str, Any]:
    parsers, fixtures, _ = import_component()
    grobid, docling = fixtures.successful_streams()
    try:
        fixtures.pin(parsers.ParserRole.GROBID_STRUCTURE, exact_version="latest")
    except parsers.ParserContractError as error:
        floating_code = error.code
    else:
        raise SystemExit("floating parser version was accepted")
    try:
        fixtures.pin(
            parsers.ParserRole.GROBID_STRUCTURE,
            executable_digest="sha256:abc",
        )
    except parsers.ParserContractError as error:
        digest_code = error.code
    else:
        raise SystemExit("invalid parser executable digest was accepted")
    grobid_kinds = [item.kind.value for item in grobid.elements]
    docling_kinds = [item.kind.value for item in docling.elements]
    if not (
        parsers.PARSER_ADAPTER_VERSION == "4.0.0-k02.1"
        and floating_code == "PARSER_PIN_FLOATING"
        and digest_code == "PARSER_PIN_INVALID"
        and grobid.pin.exact_version == "0.8.2"
        and docling.pin.exact_version == "2.41.0"
        and len(grobid.elements) == 4
        and len(docling.elements) == 7
        and all(item.locator.page is not None for item in docling.elements)
        and all(item.locator.bbox is not None for item in docling.elements)
        and "REFERENCE" in grobid_kinds
        and {"TABLE", "TABLE_CELL", "CAPTION", "FORMULA"} <= set(docling_kinds)
    ):
        raise SystemExit("K02 parser semantic verification failed")
    replay_grobid, replay_docling = fixtures.successful_streams()
    if (
        replay_grobid.stream_hash != grobid.stream_hash
        or replay_docling.stream_hash != docling.stream_hash
    ):
        raise SystemExit("K02 parser stream replay diverged")
    return {
        "adapter_version": parsers.PARSER_ADAPTER_VERSION,
        "attempt_id": ATTEMPT_ID,
        "backend_execution_claimed": False,
        "cwd_or_repository_fallback_count": 0,
        "docling": {
            "element_count": len(docling.elements),
            "exact_version": docling.pin.exact_version,
            "executable_digest": docling.pin.executable_digest,
            "kinds": docling_kinds,
            "profile_hash": docling.pin.profile_hash,
            "stream_hash": docling.stream_hash,
        },
        "external_network_call_count": 0,
        "floating_version_rejection_code": floating_code,
        "grobid": {
            "element_count": len(grobid.elements),
            "exact_version": grobid.pin.exact_version,
            "executable_digest": grobid.pin.executable_digest,
            "kinds": grobid_kinds,
            "profile_hash": grobid.pin.profile_hash,
            "retained_media_type": grobid.artifact.media_type,
            "stream_hash": grobid.stream_hash,
        },
        "invalid_digest_rejection_code": digest_code,
        "live_backend_dependency_count": 0,
        "replay_identity": "PASS",
        "status": "PASS",
    }


def fallback_verification() -> dict[str, Any]:
    parsers, _, fixtures = import_component()
    success = parsers.resolve_fallback(fixtures.primary_success())
    used = parsers.resolve_fallback(
        fixtures.primary_failure(), fixtures.fallback_success()
    )
    failed = parsers.resolve_fallback(
        fixtures.primary_failure(), fixtures.fallback_failure()
    )
    blocked_primary = parsers.blocked_attempt(
        fixtures.pin(parsers.ParserRole.GROBID_STRUCTURE),
        "GROBID_BACKEND_UNAVAILABLE",
        "the pinned GROBID backend is unavailable",
    )
    blocked = parsers.resolve_fallback(blocked_primary)
    replay = parsers.resolve_fallback(
        fixtures.primary_failure(), fixtures.fallback_success()
    )
    if not (
        success.disposition.value == "NOT_REQUIRED"
        and success.terminal_status.value == "PASS"
        and used.disposition.value == "FALLBACK_USED"
        and used.terminal_status.value == "PARTIAL"
        and used.primary.status.value == "FAIL"
        and used.primary.error_code == "PARSER_OUTPUT_MALFORMED"
        and used.fallback is not None
        and used.fallback.status.value == "PASS"
        and failed.disposition.value == "FALLBACK_FAILED"
        and failed.terminal_status.value == "FAIL"
        and blocked.disposition.value == "PRIMARY_BLOCKED_NO_FALLBACK"
        and blocked.terminal_status.value == "BLOCKED"
        and used.resolution_hash == replay.resolution_hash
    ):
        raise SystemExit("K02 fallback status verification failed")
    return {
        "attempt_id": ATTEMPT_ID,
        "cases": {
            "blocked_without_fallback": blocked.projection(),
            "failed_fallback": failed.projection(),
            "fallback_used": used.projection(),
            "primary_success": success.projection(),
        },
        "primary_failure_retained": True,
        "replay_identity": "PASS",
        "silent_fallback_count": 0,
        "status": "PASS",
    }


def disagreement_verification() -> dict[str, Any]:
    parsers, fixtures, _ = import_component()
    grobid, docling = fixtures.successful_streams()
    comparison = parsers.compare_parser_streams((grobid, docling))
    reverse = parsers.compare_parser_streams((docling, grobid))
    paragraph = next(
        item
        for item in comparison.disagreements
        if item.logical_address == "body/section[0]/paragraph[0]"
    )
    table = next(
        item
        for item in comparison.disagreements
        if item.logical_address == "table[0]"
    )
    roles = sorted(item.parser_role.value for item in paragraph.observations)
    if not (
        comparison.comparison_hash == reverse.comparison_hash
        and paragraph.status == "UNRESOLVED"
        and {"text_hash", "reading_order"} <= set(paragraph.differing_fields)
        and roles == ["DOCLING_LAYOUT", "GROBID_STRUCTURE"]
        and "missing_observation" in table.differing_fields
        and len(table.observations) == 1
        and not hasattr(comparison, "selected_text")
    ):
        raise SystemExit("K02 disagreement preservation verification failed")
    return {
        "attempt_id": ATTEMPT_ID,
        "comparison_hash": comparison.comparison_hash,
        "deterministic_permutation": "PASS",
        "disagreement_count": len(comparison.disagreements),
        "missing_observation_retained": True,
        "paragraph": {
            "differing_fields": list(paragraph.differing_fields),
            "logical_address": paragraph.logical_address,
            "observation_roles": roles,
            "observation_text_hashes": [
                item.text_hash for item in paragraph.observations
            ],
            "status": paragraph.status,
        },
        "selected_truth_field_present": False,
        "source_artifact_id": comparison.source_artifact_id,
        "status": "PASS",
    }


def pytest_summary(path: Path) -> dict[str, Any]:
    root = ET.parse(path).getroot()
    cases = list(root.iter("testcase"))
    failures = list(root.iter("failure"))
    errors = list(root.iter("error"))
    skipped = list(root.iter("skipped"))
    return {
        "collected": len(cases),
        "errors": len(errors),
        "failed": len(failures),
        "junit": path.relative_to(ROOT).as_posix(),
        "junit_sha256": sha256_id(path),
        "passed": len(cases) - len(failures) - len(errors) - len(skipped),
        "skipped": len(skipped),
        "xml_testcase_count": len(cases),
    }


def node_summary(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    ET.fromstring(raw)
    footer = {
        key.decode("ascii"): int(value)
        for key, value in NODE_FOOTER_PATTERN.findall(raw)
    }
    cases = len(list(ET.fromstring(raw).iter("testcase")))
    required = {"tests", "pass", "fail", "cancelled", "skipped", "todo"}
    if set(footer) != required:
        raise SystemExit("Node JUnit footer is incomplete")
    return {
        "cancelled": footer["cancelled"],
        "collected": footer["tests"],
        "failed": footer["fail"],
        "junit": path.relative_to(ROOT).as_posix(),
        "junit_sha256": sha256_id(path),
        "passed": footer["pass"],
        "skipped": footer["skipped"],
        "todo": footer["todo"],
        "xml_testcase_count": cases,
    }


def run_check(command: list[str]) -> dict[str, Any]:
    executable = command
    if sys.platform == "win32" and command[0] == "npm":
        executable = ["cmd.exe", "/d", "/c", "npm.cmd", *command[1:]]
    completed = subprocess.run(
        executable,
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return {
        "command": command,
        "exit_code": completed.returncode,
        "stderr": completed.stderr,
        "stdout": completed.stdout,
    }


def regression_evidence() -> dict[str, Any]:
    targeted = pytest_summary(ATTEMPT / "targeted-k02-suite.junit.xml")
    python = pytest_summary(ATTEMPT / "full-python-suite.junit.xml")
    node = node_summary(ATTEMPT / "full-node-suite.junit.xml")
    inventory = read_json(ATTEMPT / "node-test-inventory.json")
    codegen = read_json(ATTEMPT / "codegen-verification.stdout.log")
    if not (
        targeted["collected"] == targeted["passed"] == 40
        and targeted["failed"] == targeted["errors"] == targeted["skipped"] == 0
        and python["collected"] == python["passed"] == 1054
        and python["failed"] == python["errors"] == python["skipped"] == 0
        and node["collected"] == node["passed"] == 470
        and node["failed"] == node["cancelled"] == node["skipped"] == node["todo"] == 0
        and inventory.get("attempt_id") == ATTEMPT_ID
        and inventory.get("count") == 54
        and len(set(inventory.get("files", []))) == 54
        and codegen.get("status") == "PASS"
        and codegen.get("schema_count") == 126
        and codegen.get("example_count") == 126
        and codegen.get("deterministic_double_replay") == "PASS"
        and codegen.get("cross_language_fixture_parity") == "PASS"
    ):
        raise SystemExit("K02 regression evidence is not all green")
    checks = {
        "boundaries": run_check(["npm", "run", "check:boundaries"]),
        "diff": run_check(["git", "diff", "--check"]),
        "ruff": run_check(
            [
                "uv",
                "run",
                "--locked",
                "ruff",
                "check",
                "python/epistemic_foundry/ingest/parsers",
            ]
        ),
        "structure": run_check(["npm", "run", "check:structure"]),
    }
    if any(item["exit_code"] != 0 for item in checks.values()):
        raise SystemExit("K02 repository check failed")
    return {
        "attempt_id": ATTEMPT_ID,
        "codegen": {
            "deterministic_double_replay": codegen["deterministic_double_replay"],
            "example_count": codegen["example_count"],
            "schema_count": codegen["schema_count"],
            "status": codegen["status"],
        },
        "diagnostics_preserved": [
            {
                "classification": "FIXTURE_EXPECTATION_ERROR",
                "result": "initial targeted run: 39 passed, 1 failed; corrected without weakening contract",
            },
            {
                "classification": "INCOMPLETE_NODE_INVENTORY",
                "result": "initial 39-file Node run: 366 passed; rejected as full-suite evidence and replaced by 54-file 470/470 run",
            },
        ],
        "full_node": {**node, "test_file_count": 54},
        "full_python": python,
        "new_failure_count": 0,
        "new_skip_xfail_todo_or_cancellation_count": 0,
        "repository_checks": {
            "git_diff_check": {
                "exit_code": checks["diff"]["exit_code"],
                "status": "PASS_WITH_PREEXISTING_LINE_ENDING_ADVISORIES",
            },
            "package_boundaries": {
                "exit_code": checks["boundaries"]["exit_code"],
                "status": "PASS",
            },
            "repository_structure": {
                "exit_code": checks["structure"]["exit_code"],
                "status": "PASS",
            },
            "scoped_ruff": {
                "exit_code": checks["ruff"]["exit_code"],
                "status": "PASS",
            },
        },
        "status": "PASS",
        "targeted_k02": targeted,
    }


def source_inventory() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for relative in PRODUCT_FILES:
        path = ROOT / relative
        if not path.is_file():
            raise SystemExit(f"K02 product file missing: {relative}")
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        if raw.startswith(b"\xef\xbb\xbf") or "\ufffd" in text:
            raise SystemExit(f"K02 product file encoding invalid: {relative}")
        rows.append(
            {
                "byte_size": len(raw),
                "path": relative,
                "sha256": bytes_hash(raw),
                "uses_lf_only": b"\r\n" not in raw,
                "utf8_bom": False,
            }
        )
    actual = sorted(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "python/epistemic_foundry/ingest/parsers").rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )
    if actual != sorted(PRODUCT_FILES):
        raise SystemExit(f"unexpected K02 product inventory: {actual}")
    return rows


def write_scope_evidence() -> dict[str, Any]:
    inventory = source_inventory()
    caches = list((ROOT / "python/epistemic_foundry/ingest/parsers").rglob("__pycache__"))
    if caches:
        raise SystemExit(f"generated K02 cache directories remain: {caches}")
    return {
        "approved_evidence_scope": ["artifacts/work_packages/K02/**"],
        "approved_product_scope": ["python/epistemic_foundry/ingest/parsers/**"],
        "attempt_id": ATTEMPT_ID,
        "dirty_worktree_preserved": True,
        "generated_cache_present": False,
        "product_files_modified_by_attempt": [row["path"] for row in inventory],
        "product_write_scope_violation_count": 0,
        "reset_clean_stash_commit_push_performed": False,
        "status": "PASS",
        "subagents_or_fleet_used": False,
    }


def package_report_path(package_id: str) -> Path | None:
    root = ROOT / "artifacts/work_packages" / package_id
    attempts = root / "attempts"
    numeric: list[tuple[int, Path]] = []
    if attempts.is_dir():
        for path in attempts.iterdir():
            if path.is_dir() and re.fullmatch(r"\d{4,}", path.name):
                numeric.append((int(path.name), path))
    if numeric:
        return max(numeric)[1] / "report.json"
    path = root / "report.json"
    return path if path.is_file() else None


def current_pass(package_id: str, *, assume_k02_pass: bool = False) -> bool:
    if package_id == "K02" and assume_k02_pass:
        return True
    path = package_report_path(package_id)
    if path is None or not path.is_file():
        return False
    report = read_json(path)
    return report.get("status") == "PASS" and report.get("package_status") in (
        None,
        "PASS",
    )


def provisional_post_k02_projection() -> dict[str, Any]:
    document = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    packages = document["work_packages"]
    order = [row["id"] for row in packages]
    dependencies = {row["id"]: set(row.get("depends_on", [])) for row in packages}
    completed = {
        package_id for package_id in order if current_pass(package_id, assume_k02_pass=True)
    }
    ready = [
        package_id
        for package_id in order
        if package_id not in completed and dependencies[package_id] <= completed
    ]
    blocked = [
        package_id
        for package_id in order
        if package_id not in completed and package_id not in ready
    ]
    if len(order) != 156 or len(completed) != 47 or not ready or ready[0] != "K03":
        raise SystemExit(
            f"unexpected provisional post-K02 DAG: completed={len(completed)} ready={ready}"
        )
    return {
        "blocked_package_count": len(blocked),
        "completed_package_count": len(completed),
        "completion_ready": False,
        "next_package": ready[0],
        "ready_package_count": len(ready),
        "ready_packages_manifest_order": ready,
        "status": "PASS",
    }


def dependency_evidence() -> dict[str, Any]:
    if sha256_id(K01_REPORT) != EXPECTED_K01_REPORT_HASH:
        raise SystemExit("sealed K01 report hash changed")
    if sha256_id(POST_K01_DAG) != EXPECTED_POST_K01_DAG_HASH:
        raise SystemExit("sealed post-K01 DAG hash changed")
    report = read_json(K01_REPORT)
    dag = read_json(POST_K01_DAG)
    ledger = read_json(POST_K01_LEDGER)
    rah = report.get("rah_state")
    binding = dag.get("attempt_binding")
    entries = ledger.get("entries")
    sealed_dag_evidence = entries[-1] if isinstance(entries, list) and entries else None
    if not (
        report.get("attempt_id") == "K01-0002"
        and report.get("status") == "PASS"
        and isinstance(rah, dict)
        and rah.get("core_evidence_id") == "E0029"
        and rah.get("final_closeout_evidence_id") == "E0030"
        and dag.get("status") == "PASS"
        and dag.get("next_package") == "K02"
        and isinstance(binding, dict)
        and binding.get("K01_attempt_id") == "K01-0002"
        and binding.get("K01_core_evidence_id") == "E0029"
        and binding.get("K01_final_closeout_evidence_id") == "E0030"
        and binding.get("K01_report_sha256") == EXPECTED_K01_REPORT_HASH
        and ledger.get("issued_id_high_water") == 31
        and isinstance(sealed_dag_evidence, dict)
        and sealed_dag_evidence.get("id") == "E0031"
        and f"DAG {EXPECTED_POST_K01_DAG_HASH}"
        in str(sealed_dag_evidence.get("summary", ""))
    ):
        raise SystemExit("K02 dependency evidence is not the sealed K01 PASS/DAG")
    return {
        "attempt_id": ATTEMPT_ID,
        "dependency": {
            "attempt_id": "K01-0002",
            "report": K01_REPORT.relative_to(ROOT).as_posix(),
            "report_sha256": EXPECTED_K01_REPORT_HASH,
            "status": "PASS",
        },
        "manifest": manifest_contract(),
        "post_k01_sealed_dag": {
            "artifact": POST_K01_DAG.relative_to(ROOT).as_posix(),
            "artifact_sha256": EXPECTED_POST_K01_DAG_HASH,
            "evidence_id": "E0031",
            "next_package": "K02",
            "status": "PASS",
        },
        "provisional_post_k02_projection": provisional_post_k02_projection(),
        "status": "PASS",
    }


def live_documents() -> dict[str, dict[str, Any]]:
    return {
        "parser-verification.json": parser_verification(),
        "fallback-status-verification.json": fallback_verification(),
        "disagreement-verification.json": disagreement_verification(),
        "full-regression-impact.json": regression_evidence(),
        "write-scope-verification.json": write_scope_evidence(),
        "dependency-status.json": dependency_evidence(),
    }


def review_text(documents: dict[str, dict[str, Any]]) -> str:
    regression = documents["full-regression-impact.json"]
    parser = documents["parser-verification.json"]
    disagreement = documents["disagreement-verification.json"]
    return f"""# K02-0001 parser-adapter adversarial review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_ADVERSARIAL_REVIEW`

Final verdict: `PASS`

Blocking K02 findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_REVIEW`

Actor independence: `false`

The product owner requires serial primary-session execution without Fleet or
subagents. This review is procedurally separate from implementation, but it is
not actor-independent certification.

## Findings

1. K02 is an output-validation boundary, not a claim that GROBID, Docling, or
   a fallback backend was installed or executed. It performs no network,
   subprocess, CWD, repository-root, or source-tree discovery.
2. Every parser requires a closed role, exact non-floating version/revision,
   immutable executable digest, adapter version, and profile hash. Output must
   echo the sealed version and profile or fail `PARSER_PIN_OUTPUT_MISMATCH`.
3. GROBID TEI bytes remain retained and content-addressed; malformed XML and
   DTD/entity declarations become typed failures. Docling JSON is closed and
   preserves page/bbox, reading order, tables, cells, captions, figures, and
   formulas without inventing absent values.
4. Each element retains source-artifact, parser-artifact, parser identity,
   text hash, and a page or character locator. Captions require an addressable
   target, and table cells require both row and column header addresses.
5. A successful primary cannot be replaced by fallback output. Primary FAIL or
   BLOCKED remains visible when fallback is used; the terminal result is
   `PARTIAL`, not a fabricated PASS. Failed or unavailable fallback remains
   typed and no stream is selected.
6. Cross-parser comparison never chooses a truth value. The fixture has
   {disagreement['disagreement_count']} explicit disagreements, retains both
   GROBID and Docling paragraph observations, and records missing observations.
   Stream permutation produces the same comparison hash.
7. Deterministic fixture checks pass {regression['targeted_k02']['passed']}/40,
   full Python passes {regression['full_python']['passed']}/1054, full Node
   passes {regression['full_node']['passed']}/470 across 54 files, and contract
   codegen remains 126 schemas / 126 examples.
8. The initial 39/40 fixture failure and incomplete 39-file/366-test Node run
   are preserved as diagnostics. Neither was presented as final evidence; the
   fixture classification was corrected and the authoritative Node inventory
   was expanded to the sealed 54-file baseline.
9. Structure, boundaries, scoped Ruff, and `git diff --check` pass. K02 product
   writes are confined to `python/epistemic_foundry/ingest/parsers/**`; prior
   reports, RAH generations, and the dirty worktree remain preserved.

## Assurance boundary

K02 proves deterministic validation and comparison of caller-supplied immutable
parser outputs. It does not claim live backend qualification, parser service
availability, K03 SourceSpan emission, K04 ingest release, the full product,
actor-independent certification, or production readiness. Global
`implementation_gate=fail` and `completion_ready=false` remain required.

Bound adapter version: `{parser['adapter_version']}`.
"""


def command_records(timestamp: str) -> list[dict[str, Any]]:
    rows = [
        ("C001", "Inspect K02 authority, sealed K01 dependency, workflow parser contracts, dirty worktree, and RAH state", 0, "PASS"),
        ("C002", "Implement pinned GROBID/Docling/fallback output adapters and deterministic disagreement comparison under exact K02 scope", 0, "PASS"),
        ("D001", "Initial K02 targeted pytest", 1, "PRESERVED_DIAGNOSTIC: 39 passed, 1 fixture error-code expectation failed"),
        ("C003", "Correct exact_version edge-whitespace classification without weakening pin validation", 0, "PASS"),
        ("C004", "uv run --locked python -B -m pytest python/epistemic_foundry/ingest/parsers -p no:cacheprovider --junitxml=<attempt>/targeted-k02-suite.junit.xml", 0, "PASS: 40/40"),
        ("C005", "uv run --locked python -B -m pytest tests -p no:cacheprovider --junitxml=<attempt>/full-python-suite.junit.xml", 0, "PASS: 1054/1054"),
        ("D002", "node --test over packages and tests/node only", 0, "REJECTED_INCOMPLETE_EVIDENCE: 39 files / 366 tests, not the repository baseline"),
        ("C006", "node --test --test-concurrency=1 --test-reporter=junit over sealed 54-file packages/tests/web inventory", 0, "PASS: 470/470"),
        ("C007", "uv run --locked python -B packages/contracts/codegen/verify.py --repo-root .", 0, "PASS: 126 schemas/examples and deterministic parity"),
        ("C008", "npm run check:structure", 0, "PASS"),
        ("C009", "npm run check:boundaries", 0, "PASS"),
        ("C010", "uv run --locked ruff check python/epistemic_foundry/ingest/parsers", 0, "PASS"),
        ("C011", "git diff --check", 0, "PASS with pre-existing line-ending advisories only"),
        ("C012", "Primary-session separate adversarial review of pins, provenance, fallback, disagreement, XML safety, and no-discovery boundary", 0, "PASS: zero blocking findings; actor_independence=false"),
    ]
    return [
        {
            "command": command,
            "command_id": f"{ATTEMPT_ID}-{identifier}",
            "exit_code": exit_code,
            "recorded_at_utc": timestamp,
            "result": result,
            "scope": ATTEMPT_ID,
        }
        for identifier, command, exit_code, result in rows
    ]


def make_receipt(path: Path, timestamp: str) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "action_intent_id": None,
        "artifact_id": "K02-0001-PARSER-VERIFICATION",
        "byte_size": path.stat().st_size,
        "content_hash": sha256_id(path),
        "created_at": timestamp,
        "created_by": {
            "actor_id": "K02-0001-PRIMARY-SESSION-VERIFIER",
            "actor_type": "tool",
        },
        "locator": path.relative_to(ROOT).as_posix(),
        "media_type": "application/json",
        "receipt_id": "AR-K02-0001-PARSER-VERIFICATION",
        "schema_ref": None,
        "validation_results": [
            {
                "check": "parser_fixture_benchmark",
                "details": "40/40 fixed parser and fallback fixtures passed with exact deterministic projections",
                "status": "PASS",
            },
            {
                "check": "parser_versions_pinned",
                "details": "exact version, executable digest, profile hash, and adapter version are mandatory; floating refs fail closed",
                "status": "PASS",
            },
            {
                "check": "fallback_status_test",
                "details": "primary failure/blocking is retained and fallback never silently upgrades authority",
                "status": "PASS",
            },
            {
                "check": "disagreement_retention",
                "details": "both parser observations and missing observations remain explicit and unresolved",
                "status": "PASS",
            },
            {
                "check": "full_regression",
                "details": "Python 1054/1054, Node 470/470, codegen 126/126, structure/boundaries/Ruff/diff checks passed",
                "status": "PASS",
            },
        ],
    }
    receipt["receipt_hash"] = canonical_hash_excluding(receipt, "receipt_hash")
    schema = read_json(RECEIPT_SCHEMA)
    Draft202012Validator.check_schema(schema)
    errors = list(Draft202012Validator(schema).iter_errors(receipt))
    if errors:
        raise SystemExit(f"invalid K02 ArtifactReceipt: {errors[0].message}")
    return receipt


def evidence_artifacts() -> list[dict[str, Any]]:
    names = [
        *OUTPUT_NAMES,
        "parser-verification.artifact-receipt.json",
        "targeted-k02-suite.junit.xml",
        "full-python-suite.junit.xml",
        "full-node-suite.junit.xml",
        "node-test-inventory.json",
        "codegen-verification.stdout.log",
        "commands.jsonl",
        "review.md",
        "attempt-metadata.json",
        "build_k02_0001_evidence.py",
        "k02_0001_rah_seal.py",
    ]
    if (ATTEMPT / "rah-core-integrity.json").is_file():
        names.append("rah-core-integrity.json")
    rows: list[dict[str, Any]] = []
    for name in names:
        path = ATTEMPT / name
        if not path.is_file():
            raise SystemExit(f"required K02 evidence artifact missing: {name}")
        rows.append(
            {
                "byte_size": path.stat().st_size,
                "path": path.relative_to(ROOT).as_posix(),
                "sha256": sha256_id(path),
            }
        )
    return rows


def report_document(
    documents: dict[str, dict[str, Any]],
    *,
    rah_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    regression = documents["full-regression-impact.json"]
    dependency = documents["dependency-status.json"]
    receipt = read_json(ATTEMPT / "parser-verification.artifact-receipt.json")
    report: dict[str, Any] = {
        "artifact_receipt": {
            "path": (
                "artifacts/work_packages/K02/attempts/0001/"
                "parser-verification.artifact-receipt.json"
            ),
            "receipt_hash": receipt["receipt_hash"],
            "receipt_id": receipt["receipt_id"],
        },
        "attempt_id": ATTEMPT_ID,
        "changed_files": source_inventory(),
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependencies": {"K01": dependency["dependency"]},
        "dependency_effect": dependency["provisional_post_k02_projection"],
        "evidence_artifacts": evidence_artifacts(),
        "exit_criteria": {
            "disagreement retained": "PASS",
            "parser versions pinned": "PASS",
        },
        "global_implementation_gate": "fail",
        "history_and_worktree": {
            "dirty_worktree_preserved": True,
            "prior_attempts_reports_and_rah_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
            "subagents_or_fleet_used": False,
        },
        "implementation_status": "PASS",
        "not_claimed": [
            "live GROBID, Docling, or fallback backend execution or availability",
            "K03 SourceSpan emission",
            "K04 ingest release",
            "actor-independent certification",
            "full product completion",
            "release or production readiness",
            "completion_ready=true",
        ],
        "package_status": "PASS",
        "regression": regression,
        "required_checks": {
            "fallback_status_test": "PASS",
            "independent_review": {
                "actor_independence": False,
                "blocking_finding_count": 0,
                "mode": "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_REVIEW",
                "status": "PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW",
            },
            "parser_fixture_benchmark": "PASS",
        },
        "review": {
            "actor_independence": False,
            "artifact": "artifacts/work_packages/K02/attempts/0001/review.md",
            "artifact_sha256": sha256_id(ATTEMPT / "review.md"),
            "blocking_finding_count": 0,
            "mode": "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_REVIEW",
            "status": "PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW",
        },
        "status": "PASS",
        "title": "GROBID/Docling and fallback parser adapters",
        "verification": {
            "codegen": "126 schemas / 126 examples",
            "disagreement_status": "UNRESOLVED_RETAINED",
            "full_node": "470/470",
            "full_python": "1054/1054",
            "silent_fallback_count": 0,
            "targeted_k02": "40/40",
            "write_scope_violation_count": 0,
        },
        "work_package_id": WORK_PACKAGE_ID,
    }
    if rah_state is not None:
        report["rah_state"] = rah_state
    return report


def build() -> dict[str, Any]:
    timestamp = recorded_at()
    documents = live_documents()
    for name, document in documents.items():
        write_json(ATTEMPT / name, document)
    write_text(ATTEMPT / "review.md", review_text(documents))
    commands = command_records(timestamp)
    write_text(
        ATTEMPT / "commands.jsonl",
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in commands),
    )
    write_json(
        ATTEMPT / "parser-verification.artifact-receipt.json",
        make_receipt(ATTEMPT / "parser-verification.json", timestamp),
    )
    write_json(ATTEMPT / "report.json", report_document(documents))
    verify(expect_rah=False)
    return {
        "attempt_id": ATTEMPT_ID,
        "mode": "build",
        "status": "PASS",
        "verification": {
            "full_node": "470/470",
            "full_python": "1054/1054",
            "targeted_k02": "40/40",
        },
    }


def verify(*, expect_rah: bool | None = None) -> dict[str, Any]:
    stored = {name: read_json(ATTEMPT / name) for name in OUTPUT_NAMES}
    live = live_documents()
    if stored != live:
        differences = [name for name in OUTPUT_NAMES if stored[name] != live[name]]
        raise SystemExit(f"stored K02 evidence differs from live recomputation: {differences}")
    if (ATTEMPT / "review.md").read_text(encoding="utf-8") != review_text(live):
        raise SystemExit("stored K02 review differs from deterministic rendering")
    metadata = read_json(ATTEMPT / "attempt-metadata.json")
    expected_commands = command_records(str(metadata["recorded_at_utc"]))
    actual_commands = [
        json.loads(line)
        for line in (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    if actual_commands != expected_commands:
        raise SystemExit("K02 command ledger differs from deterministic rendering")
    receipt = read_json(ATTEMPT / "parser-verification.artifact-receipt.json")
    if receipt != make_receipt(
        ATTEMPT / "parser-verification.json", str(metadata["recorded_at_utc"])
    ):
        raise SystemExit("K02 ArtifactReceipt differs from live verification")
    report = read_json(ATTEMPT / "report.json")
    rah = report.get("rah_state")
    if expect_rah is True and not isinstance(rah, dict):
        raise SystemExit("K02 report is not RAH-bound")
    if expect_rah is False and rah is not None:
        raise SystemExit("K02 pre-core report unexpectedly contains RAH state")
    expected_report = report_document(live, rah_state=rah if isinstance(rah, dict) else None)
    if report != expected_report:
        raise SystemExit("K02 report differs from deterministic rendering")
    return {
        "attempt_id": ATTEMPT_ID,
        "evidence_artifact_count": len(report["evidence_artifacts"]),
        "mode": "verify",
        "rah_bound": isinstance(rah, dict),
        "report_sha256": sha256_id(ATTEMPT / "report.json"),
        "status": "PASS",
    }


def bind_rah_state(
    *,
    core_generation: str,
    core_evidence_id: str,
    final_closeout_evidence_id: str,
) -> dict[str, Any]:
    documents = {name: read_json(ATTEMPT / name) for name in OUTPUT_NAMES}
    rah_state = {
        "completion_ready": False,
        "core_evidence_id": core_evidence_id,
        "core_generation": core_generation,
        "final_closeout_evidence_id": final_closeout_evidence_id,
        "implementation_gate": "fail",
        "status": "active",
    }
    write_json(ATTEMPT / "report.json", report_document(documents, rah_state=rah_state))
    return verify(expect_rah=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("build", "verify", "bind-rah"))
    parser.add_argument("--core-generation")
    parser.add_argument("--core-evidence-id")
    parser.add_argument("--final-evidence-id")
    args = parser.parse_args()
    if args.mode == "build":
        result = build()
    elif args.mode == "verify":
        result = verify()
    else:
        if not all(
            (args.core_generation, args.core_evidence_id, args.final_evidence_id)
        ):
            raise SystemExit("bind-rah requires core generation and evidence IDs")
        result = bind_rah_state(
            core_generation=args.core_generation,
            core_evidence_id=args.core_evidence_id,
            final_closeout_evidence_id=args.final_evidence_id,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
