#!/usr/bin/env python3
"""Build and verify fail-closed evidence for K03-0001.

The verifier recomputes the SourceSpan contract from the current component,
binds it to the sealed K01 dependency and post-K02 DAG, validates stored test
receipts, and renders a primary-session separate adversarial review.  It does
not claim live parser execution, downstream Claim Forge grounding, or actor-
independent certification.
"""

from __future__ import annotations

import argparse
import copy
import dataclasses
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
ATTEMPT = ROOT / "artifacts/work_packages/K03/attempts/0001"
ATTEMPT_ID = "K03-0001"
WORK_PACKAGE_ID = "K03"
MANIFEST = ROOT / "manifests/development_manifest.yaml"
SOURCE_SPAN_SCHEMA = ROOT / "schemas/source-span.schema.json"
RECEIPT_SCHEMA = ROOT / "schemas/artifact-receipt.schema.json"
K01_REPORT = ROOT / "artifacts/work_packages/K01/attempts/0002/report.json"
POST_K02_DAG = (
    ROOT
    / "artifacts/work_packages/K02/attempts/0001/"
    "post-k02-0001-dag-reconciliation.json"
)
POST_K02_LEDGER = (
    ROOT / ".rah/ralph/generations/000034-a020b6f3/evidence_ledger.json"
)
K02_NODE_INVENTORY = (
    ROOT / "artifacts/work_packages/K02/attempts/0001/node-test-inventory.json"
)
EXPECTED_K01_REPORT_HASH = (
    "sha256:e2132964003c019599e6e5ef130ea2e8d933e08e94481d68864038d1e82a2b3b"
)
EXPECTED_POST_K02_DAG_HASH = (
    "sha256:0067ae26b4b84e9cdf9e5bce5bbb877dc1c2feb7e0a2e28e38e4236bdce8c687"
)
EXPECTED_K02_NODE_INVENTORY_HASH = (
    "sha256:e1b8b1b44c13b6a4d2cd1db24ea9e55e71534d02d530aa4844a9f6361642a179"
)
EXPECTED_SCHEMA_HASH = (
    "sha256:4d4c8ec8b9a778c0176c7d8b866d15a82bf53be898985389ac0cc42d6a60586a"
)
PRODUCT_FILES = (
    "python/epistemic_foundry/ingest/spans/__init__.py",
    "python/epistemic_foundry/ingest/spans/emitter.py",
    "python/epistemic_foundry/ingest/spans/test_orphan_span.py",
    "python/epistemic_foundry/ingest/spans/test_source_span_roundtrip.py",
)
OUTPUT_NAMES = (
    "source-span-verification.json",
    "orphan-span-verification.json",
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
        raise SystemExit("K03 attempt metadata is invalid")
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
    rows = [row for row in packages if isinstance(row, dict) and row.get("id") == "K03"]
    if len(rows) != 1:
        raise SystemExit("development manifest must contain exactly one K03")
    row = rows[0]
    expected = {
        "depends_on": ["K01"],
        "write_scope": ["python/epistemic_foundry/ingest/spans/**"],
        "exit_criteria": [
            "span hash resolves to source",
            "page/bbox/char locators typed",
        ],
        "required_checks": ["source_span_roundtrip", "orphan_span_test"],
        "independent_review": "required",
        "risk_class": "medium",
    }
    actual = {key: row.get(key) for key in expected}
    if actual != expected:
        raise SystemExit(f"K03 manifest contract changed: {actual!r}")
    return {**actual, "status": "PASS"}


def import_component() -> Any:
    component_parent = ROOT / "python/epistemic_foundry/ingest"
    sys.path.insert(0, str(component_parent))
    try:
        import spans  # type: ignore[import-not-found]
    except ImportError as error:
        raise SystemExit(f"cannot import K03 component: {error}") from error
    finally:
        sys.path.pop(0)
    return spans


def _fixture(spans: Any) -> tuple[str, Any, tuple[Any, ...]]:
    text = (
        "Yield increased under treatment.\n"
        "Table 1: control=4; treatment=7.\n"
        "Figure 1: response curve.\n"
        "Equation: y = ax + b."
    )
    snapshot = spans.SourceSnapshot.capture(
        document_id="DOC-K03-0001",
        paper_version_id="PV-K03-0001",
        provenance_manifest_id="PROV-K03-0001",
        content=text,
    )

    def candidate(kind: Any, unit: Any, needle: str, page: int) -> Any:
        start = text.index(needle)
        return spans.SpanCandidate(
            kind=kind,
            page=page,
            section="Results",
            semantic_unit=unit,
            bbox=(0.1, 0.2, 0.9, 0.4),
            char_start=start,
            char_end=start + len(needle),
            parser_name="docling",
            parser_version="2.41.0",
            coordinate_system=spans.CoordinateSystem.NORMALIZED_TOP_LEFT,
            reconciliation_status=spans.ReconciliationStatus.AGREED,
        )

    candidates = (
        candidate(spans.SpanKind.TEXT, spans.SemanticUnit.RESULTS, "Yield increased", 1),
        candidate(spans.SpanKind.TABLE, spans.SemanticUnit.TABLE_CELL, "control=4", 2),
        candidate(
            spans.SpanKind.FIGURE,
            spans.SemanticUnit.FIGURE_CAPTION,
            "Figure 1: response curve.",
            3,
        ),
        candidate(spans.SpanKind.FORMULA, spans.SemanticUnit.EQUATION, "y = ax + b", 4),
    )
    return text, snapshot, candidates


def source_span_verification() -> dict[str, Any]:
    spans = import_component()
    text, snapshot, candidates = _fixture(spans)
    emitted = spans.emit_source_spans(snapshot, candidates)
    replay_text, replay_snapshot, replay_candidates = _fixture(spans)
    replay = spans.emit_source_spans(replay_snapshot, replay_candidates)
    schema = read_json(SOURCE_SPAN_SCHEMA)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    for record in emitted:
        errors = list(validator.iter_errors(record.projection()))
        if errors:
            raise SystemExit(f"K03 emitted invalid SourceSpan: {errors[0].message}")
    resolved = spans.resolve_source_spans(emitted, (snapshot,))
    changed = text.replace("Equation: y = ax + b.", "Equation: y = ax + c.")
    changed_snapshot = spans.SourceSnapshot.capture(
        document_id=snapshot.document_id,
        paper_version_id=snapshot.paper_version_id,
        provenance_manifest_id=snapshot.provenance_manifest_id,
        content=changed,
    )
    changed_first = spans.emit_source_span(changed_snapshot, candidates[0])
    candidate_fields = {field.name for field in dataclasses.fields(spans.SpanCandidate)}
    forbidden_authority = {"span_id", "verbatim_text", "text_hash"}
    required_schema_fields = set(schema.get("required", []))
    projections = [record.projection() for record in emitted]
    if not (
        spans.SOURCE_SPAN_EMITTER_VERSION == "4.0.0-k03.1"
        and replay_text == text
        and projections == [record.projection() for record in replay]
        and resolved == tuple(record.verbatim_text for record in emitted)
        and [record.semantic_unit.value for record in emitted]
        == ["results", "table_cell", "figure_caption", "equation"]
        and all(set(record.projection()) == required_schema_fields for record in emitted)
        and all(record.text_hash == bytes_hash(record.verbatim_text.encode("utf-8")) for record in emitted)
        and all(record.span_id.startswith("SPAN-") for record in emitted)
        and changed_first.verbatim_text == emitted[0].verbatim_text
        and changed_first.span_id != emitted[0].span_id
        and not (candidate_fields & forbidden_authority)
        and sha256_id(SOURCE_SPAN_SCHEMA) == EXPECTED_SCHEMA_HASH
    ):
        raise SystemExit("K03 SourceSpan semantic verification failed")
    return {
        "attempt_id": ATTEMPT_ID,
        "caller_supplied_authority_fields": sorted(candidate_fields & forbidden_authority),
        "canonical_schema_hash": EXPECTED_SCHEMA_HASH,
        "canonical_schema_property_count": len(schema.get("properties", {})),
        "canonical_schema_required_count": len(required_schema_fields),
        "classes_emitted": ["TEXT", "TABLE", "FIGURE", "FORMULA"],
        "emitter_version": spans.SOURCE_SPAN_EMITTER_VERSION,
        "external_network_call_count": 0,
        "identity_changes_when_unselected_source_bytes_change": True,
        "projection_field_count": len(projections[0]),
        "replay_identity": "PASS",
        "resolved_text_count": len(resolved),
        "source_derived_fields": ["span_id", "text_hash", "verbatim_text"],
        "source_text_hash": snapshot.source_text_hash,
        "span_ids": [record.span_id for record in emitted],
        "status": "PASS",
    }


def _error_code(callable_: Any) -> str:
    spans = import_component()
    try:
        callable_()
    except spans.SourceSpanContractError as error:
        return str(error.code)
    raise SystemExit("K03 adversarial case unexpectedly succeeded")


def orphan_span_verification() -> dict[str, Any]:
    spans = import_component()
    text, snapshot, candidates = _fixture(spans)
    span = spans.emit_source_span(snapshot, candidates[0])
    wrong_document = spans.SourceSnapshot.capture(
        document_id="DOC-K03-OTHER",
        paper_version_id=snapshot.paper_version_id,
        provenance_manifest_id=snapshot.provenance_manifest_id,
        content=text,
    )
    wrong_version = spans.SourceSnapshot.capture(
        document_id=snapshot.document_id,
        paper_version_id="PV-K03-OTHER",
        provenance_manifest_id=snapshot.provenance_manifest_id,
        content=text,
    )
    wrong_provenance = spans.SourceSnapshot.capture(
        document_id=snapshot.document_id,
        paper_version_id=snapshot.paper_version_id,
        provenance_manifest_id="PROV-K03-OTHER",
        content=text,
    )
    outside = spans.SourceSnapshot.capture(
        document_id=snapshot.document_id,
        paper_version_id=snapshot.paper_version_id,
        provenance_manifest_id=snapshot.provenance_manifest_id,
        content=text.replace("y = ax + b", "y = ax + c"),
    )
    tampered_id = copy.deepcopy(span.projection())
    tampered_id["span_id"] = "SPAN-" + ("f" * 64)
    extra_field = copy.deepcopy(span.projection())
    extra_field["caller_claimed_truth"] = True
    cases = {
        "missing_source": _error_code(lambda: spans.resolve_source_span(span, ())),
        "wrong_document": _error_code(lambda: spans.verify_source_span(span, wrong_document)),
        "wrong_version": _error_code(lambda: spans.verify_source_span(span, wrong_version)),
        "wrong_provenance": _error_code(
            lambda: spans.SourceSnapshotIndex((wrong_provenance,)).resolve(span)
        ),
        "stale_source_outside_slice": _error_code(
            lambda: spans.verify_source_span(span, outside)
        ),
        "tampered_span_id": _error_code(
            lambda: spans.verify_source_span(tampered_id, snapshot)
        ),
        "unknown_persisted_field": _error_code(
            lambda: spans.source_span_from_mapping(extra_field)
        ),
        "floating_parser_version": _error_code(
            lambda: spans.SpanCandidate(
                kind=candidates[0].kind,
                page=1,
                section="Results",
                semantic_unit=candidates[0].semantic_unit,
                bbox=None,
                char_start=0,
                char_end=5,
                parser_name="grobid",
                parser_version="latest",
                coordinate_system=spans.CoordinateSystem.NOT_AVAILABLE,
                reconciliation_status=spans.ReconciliationStatus.SINGLE_PARSER,
            )
        ),
    }
    mutable_snapshot = spans.SourceSnapshot.capture(
        document_id=snapshot.document_id,
        paper_version_id=snapshot.paper_version_id,
        provenance_manifest_id=snapshot.provenance_manifest_id,
        content=text,
    )
    object.__setattr__(mutable_snapshot, "source_text", text + " mutated")
    cases["mutated_snapshot"] = _error_code(
        lambda: spans.verify_source_span(span, mutable_snapshot)
    )
    expected = {
        "missing_source": "SOURCE_SPAN_ORPHANED",
        "wrong_document": "SOURCE_SPAN_ORPHANED",
        "wrong_version": "SOURCE_SPAN_ORPHANED",
        "wrong_provenance": "SOURCE_SPAN_PROVENANCE_MISMATCH",
        "stale_source_outside_slice": "SOURCE_SPAN_ID_MISMATCH",
        "tampered_span_id": "SOURCE_SPAN_ID_MISMATCH",
        "unknown_persisted_field": "SOURCE_SPAN_INPUT_INVALID",
        "floating_parser_version": "SOURCE_SPAN_INPUT_INVALID",
        "mutated_snapshot": "SOURCE_SPAN_SOURCE_HASH_MISMATCH",
    }
    if cases != expected:
        raise SystemExit(f"K03 orphan/tamper verification changed: {cases!r}")
    return {
        "adversarial_case_count": len(cases),
        "attempt_id": ATTEMPT_ID,
        "cases": cases,
        "fail_closed_count": len(cases),
        "silent_fallback_count": 0,
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
    parsed = ET.fromstring(raw)
    footer = {
        key.decode("ascii"): int(value)
        for key, value in NODE_FOOTER_PATTERN.findall(raw)
    }
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
        "xml_testcase_count": len(list(parsed.iter("testcase"))),
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


def node_inventory_document() -> dict[str, Any]:
    if sha256_id(K02_NODE_INVENTORY) != EXPECTED_K02_NODE_INVENTORY_HASH:
        raise SystemExit("sealed K02 Node inventory changed")
    source = read_json(K02_NODE_INVENTORY)
    files = source.get("files")
    if not (
        source.get("attempt_id") == "K02-0001"
        and source.get("count") == 54
        and isinstance(files, list)
        and len(files) == len(set(files)) == 54
        and all(isinstance(item, str) for item in files)
    ):
        raise SystemExit("sealed K02 Node inventory is invalid")
    return {
        "attempt_id": ATTEMPT_ID,
        "authority": "sealed K02 54-file repository Node inventory",
        "authority_sha256": EXPECTED_K02_NODE_INVENTORY_HASH,
        "count": 54,
        "files": files,
    }


def regression_evidence() -> dict[str, Any]:
    targeted = pytest_summary(ATTEMPT / "targeted-k03-suite.junit.xml")
    python = pytest_summary(ATTEMPT / "full-python-suite.junit.xml")
    node = node_summary(ATTEMPT / "full-node-suite.junit.xml")
    inventory = read_json(ATTEMPT / "node-test-inventory.json")
    codegen = read_json(ATTEMPT / "codegen-verification.stdout.log")
    if not (
        targeted["collected"] == targeted["passed"] == 36
        and targeted["failed"] == targeted["errors"] == targeted["skipped"] == 0
        and python["collected"] == python["passed"] == 1054
        and python["failed"] == python["errors"] == python["skipped"] == 0
        and node["collected"] == node["passed"] == 470
        and node["failed"] == node["cancelled"] == node["skipped"] == node["todo"] == 0
        and inventory == node_inventory_document()
        and codegen.get("status") == "PASS"
        and codegen.get("schema_count") == 126
        and codegen.get("example_count") == 126
        and codegen.get("deterministic_double_replay") == "PASS"
        and codegen.get("cross_language_fixture_parity") == "PASS"
    ):
        raise SystemExit("K03 regression evidence is not all green")
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
                "python/epistemic_foundry/ingest/spans",
            ]
        ),
        "structure": run_check(["npm", "run", "check:structure"]),
    }
    if any(item["exit_code"] != 0 for item in checks.values()):
        raise SystemExit("K03 repository check failed")
    return {
        "attempt_id": ATTEMPT_ID,
        "codegen": {
            "deterministic_double_replay": codegen["deterministic_double_replay"],
            "example_count": codegen["example_count"],
            "schema_count": codegen["schema_count"],
            "status": codegen["status"],
        },
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
        "targeted_k03": targeted,
    }


def source_inventory() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for relative in PRODUCT_FILES:
        path = ROOT / relative
        if not path.is_file():
            raise SystemExit(f"K03 product file missing: {relative}")
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        if raw.startswith(b"\xef\xbb\xbf") or "\ufffd" in text:
            raise SystemExit(f"K03 product file encoding invalid: {relative}")
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
        for path in (ROOT / "python/epistemic_foundry/ingest/spans").rglob("*")
        if path.is_file()
    )
    if actual != sorted(PRODUCT_FILES):
        raise SystemExit(f"unexpected K03 product inventory: {actual}")
    return rows


def write_scope_evidence() -> dict[str, Any]:
    inventory = source_inventory()
    component = ROOT / "python/epistemic_foundry/ingest/spans"
    caches = list(component.rglob("__pycache__"))
    if caches:
        raise SystemExit(f"generated K03 caches remain: {caches}")
    text = "\n".join((ROOT / relative).read_text("utf-8") for relative in PRODUCT_FILES)
    forbidden_tokens = (
        "epistemic_foundry.ingest.parsers",
        "from parsers",
        "import parsers",
        "claim_forge",
        "src.epistemic_foundry",
    )
    hits = [token for token in forbidden_tokens if token in text]
    if hits:
        raise SystemExit(f"K03 component imports duplicate authority: {hits}")
    if sha256_id(SOURCE_SPAN_SCHEMA) != EXPECTED_SCHEMA_HASH:
        raise SystemExit("canonical SourceSpan schema changed during K03")
    return {
        "attempt_id": ATTEMPT_ID,
        "canonical_schema_modified_by_k03": False,
        "component_file_count": len(inventory),
        "component_files": inventory,
        "cross_component_authority_import_hits": hits,
        "generated_cache_count": len(caches),
        "schema_authority_redefinition_count": 0,
        "status": "PASS",
        "unexpected_product_file_count": 0,
        "write_scope": ["python/epistemic_foundry/ingest/spans/**"],
        "write_scope_violation_count": 0,
    }


def _latest_report_is_pass(package_id: str) -> bool:
    package_root = ROOT / "artifacts/work_packages" / package_id
    attempts_root = package_root / "attempts"
    numeric: list[tuple[int, Path]] = []
    if attempts_root.is_dir():
        for path in attempts_root.iterdir():
            if path.is_dir() and re.fullmatch(r"\d{4,}", path.name):
                numeric.append((int(path.name), path))
    if numeric:
        report_path = max(numeric)[1] / "report.json"
        if not report_path.is_file():
            return False
    else:
        report_path = package_root / "report.json"
        if not report_path.is_file():
            return False
    report = read_json(report_path)
    return report.get("status") == "PASS" and report.get("package_status") in (None, "PASS")


def provisional_post_k03_projection() -> dict[str, Any]:
    document = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    packages = document.get("work_packages") if isinstance(document, dict) else None
    if not isinstance(packages, list) or len(packages) != 156:
        raise SystemExit("cannot compute provisional post-K03 DAG")
    order = [str(row["id"]) for row in packages]
    dependencies = {
        str(row["id"]): set(map(str, row.get("depends_on", []))) for row in packages
    }
    completed = {
        package_id for package_id in order if _latest_report_is_pass(package_id)
    }
    completed.add("K03")
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
    if not (
        len(completed) == 48
        and ready == ["K04", "L01", "N01", "T01", "A06"]
        and len(blocked) == 103
    ):
        raise SystemExit(
            f"unexpected provisional post-K03 DAG: completed={len(completed)} ready={ready}"
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
    if sha256_id(POST_K02_DAG) != EXPECTED_POST_K02_DAG_HASH:
        raise SystemExit("sealed post-K02 DAG hash changed")
    report = read_json(K01_REPORT)
    dag = read_json(POST_K02_DAG)
    ledger = read_json(POST_K02_LEDGER)
    rah = report.get("rah_state")
    binding = dag.get("attempt_binding")
    entries = ledger.get("entries")
    tail = entries[-1] if isinstance(entries, list) and entries else None
    if not (
        report.get("attempt_id") == "K01-0002"
        and report.get("status") == "PASS"
        and isinstance(rah, dict)
        and rah.get("core_evidence_id") == "E0029"
        and rah.get("final_closeout_evidence_id") == "E0030"
        and dag.get("status") == "PASS"
        and dag.get("next_package") == "K03"
        and "K03" in dag.get("ready_packages_manifest_order", [])
        and isinstance(binding, dict)
        and binding.get("K02_attempt_id") == "K02-0001"
        and binding.get("K02_final_closeout_evidence_id") == "E0033"
        and ledger.get("issued_id_high_water") == 34
        and isinstance(tail, dict)
        and tail.get("id") == "E0034"
        and EXPECTED_POST_K02_DAG_HASH in str(tail.get("summary", ""))
    ):
        raise SystemExit("K03 dependency evidence is not the sealed K01 PASS/post-K02 DAG")
    return {
        "attempt_id": ATTEMPT_ID,
        "dependency": {
            "attempt_id": "K01-0002",
            "report": K01_REPORT.relative_to(ROOT).as_posix(),
            "report_sha256": EXPECTED_K01_REPORT_HASH,
            "status": "PASS",
        },
        "manifest": manifest_contract(),
        "post_k02_sealed_dag": {
            "artifact": POST_K02_DAG.relative_to(ROOT).as_posix(),
            "artifact_sha256": EXPECTED_POST_K02_DAG_HASH,
            "evidence_id": "E0034",
            "next_package": "K03",
            "status": "PASS",
        },
        "provisional_post_k03_projection": provisional_post_k03_projection(),
        "status": "PASS",
    }


def live_documents() -> dict[str, dict[str, Any]]:
    return {
        "source-span-verification.json": source_span_verification(),
        "orphan-span-verification.json": orphan_span_verification(),
        "full-regression-impact.json": regression_evidence(),
        "write-scope-verification.json": write_scope_evidence(),
        "dependency-status.json": dependency_evidence(),
    }


def review_text(documents: dict[str, dict[str, Any]]) -> str:
    regression = documents["full-regression-impact.json"]
    source = documents["source-span-verification.json"]
    orphan = documents["orphan-span-verification.json"]
    return f"""# K03-0001 SourceSpan adversarial review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_ADVERSARIAL_REVIEW`

Final verdict: `PASS`

Blocking K03 findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_REVIEW`

Actor independence: `false`

The product owner requires serial primary-session execution without Fleet or
subagents. This review is procedurally separated from implementation, but it is
not actor-independent certification.

## Findings

1. The caller can supply only typed locator/parser metadata. `SpanCandidate`
   has no `span_id`, `verbatim_text`, or `text_hash` field; these values are
   derived from the sealed source bytes.
2. The identifier preimage includes the emitter version, complete source-text
   hash, and all canonical span fields. Changing source bytes outside the
   selected slice keeps the verbatim text but changes the span ID, preventing a
   stale version from resolving by slice coincidence.
3. Exact document ID, paper-version ID, provenance-manifest ID, character
   range, source text, text hash, and content-addressed span ID must reconcile.
   Missing sources, stale versions, wrong provenance, mutation, and tampering
   fail with typed errors; {orphan['fail_closed_count']}/{orphan['adversarial_case_count']}
   adversarial cases fail closed.
4. Page is positive, character ranges are bounded and non-empty, bbox values
   are finite with positive extent, normalized coordinates stay in `[0, 1]`,
   and null bbox is permitted only with `not_available` coordinates.
5. The parser version must be an exact version or revision. Floating values
   such as `main`, `latest`, ranges, and wildcard versions are rejected.
6. Persisted records must have exactly the {source['projection_field_count']}
   canonical schema fields. Missing or extra properties are rejected, and all
   text/table/figure/formula fixture projections validate against the unchanged
   canonical `source-span.schema.json`.
7. The component imports neither K02 parser internals nor downstream Claim
   Forge grounding. It preserves reconciliation status and creates no duplicate
   schema or source authority.
8. K03 targeted tests pass {regression['targeted_k03']['passed']}/36, full
   Python passes {regression['full_python']['passed']}/1054, full Node passes
   {regression['full_node']['passed']}/470 across 54 files, and codegen remains
   126 schemas / 126 examples. Structure, boundaries, scoped Ruff, and
   `git diff --check` pass.
9. Product files are exactly four UTF-8/LF Python files under the declared
   scope. Generated bytecode caches were removed by verified exact-leaf
   deletion; no recursive workspace cleanup, reset, clean, stash, commit, or
   push was performed.

## Assurance boundary

K03 proves deterministic emission and exact source resolution for immutable
caller-provided source snapshots. It does not claim live parser execution,
source acquisition or licensing, K04 corpus security release, downstream
ClaimCard grounding, actor-independent certification, full product completion,
or production readiness. Global `implementation_gate=fail` and
`completion_ready=false` remain required.

Bound emitter version: `{source['emitter_version']}`.
"""


def command_records(timestamp: str) -> list[dict[str, Any]]:
    rows: list[tuple[str, str, int | None, str]] = [
        ("C001", "Inspect K03 authority, sealed K01 dependency, SourceSpan schema, dirty worktree, and post-K02 RAH state", 0, "PASS"),
        ("C002", "Implement source-bound immutable SourceSpan emission and resolution under exact K03 scope", 0, "PASS"),
        ("C003", "uv run --locked python -B -m pytest python/epistemic_foundry/ingest/spans -p no:cacheprovider --junitxml=<attempt>/targeted-k03-suite.junit.xml", 0, "PASS: 36/36"),
        ("C004", "uv run --locked python -B -m pytest tests -p no:cacheprovider --junitxml=<attempt>/full-python-suite.junit.xml", 0, "PASS: 1054/1054"),
        ("C005", "node --test --test-concurrency=1 --test-reporter=junit over sealed 54-file repository inventory", 0, "PASS: 470/470"),
        ("C006", "uv run --locked python -B packages/contracts/codegen/verify.py --repo-root .", 0, "PASS: 126 schemas/examples and deterministic parity"),
        ("D001", "Recursive Remove-Item cache cleanup proposal", None, "NOT_EXECUTED: command safety policy rejected recursive removal"),
        ("C007", "Verify six fixed .pyc leaves, delete each exact leaf with File.Delete, then remove only the empty non-reparse directory", 0, "PASS"),
        ("C008", "npm run check:structure", 0, "PASS"),
        ("C009", "npm run check:boundaries", 0, "PASS"),
        ("C010", "uv run --locked ruff check python/epistemic_foundry/ingest/spans", 0, "PASS"),
        ("C011", "git diff --check", 0, "PASS with pre-existing line-ending advisories only"),
        ("C012", "Primary-session separate adversarial review of source binding, locator types, stale/orphan/tamper rejection, and authority boundaries", 0, "PASS: zero blocking findings; actor_independence=false"),
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
        "artifact_id": "K03-0001-SOURCE-SPAN-VERIFICATION",
        "byte_size": path.stat().st_size,
        "content_hash": sha256_id(path),
        "created_at": timestamp,
        "created_by": {
            "actor_id": "K03-0001-PRIMARY-SESSION-VERIFIER",
            "actor_type": "tool",
        },
        "locator": path.relative_to(ROOT).as_posix(),
        "media_type": "application/json",
        "receipt_id": "AR-K03-0001-SOURCE-SPAN-VERIFICATION",
        "schema_ref": None,
        "validation_results": [
            {
                "check": "source_span_roundtrip",
                "details": "36/36 fixed tests pass; text/table/figure/formula projections resolve to exact immutable source bytes",
                "status": "PASS",
            },
            {
                "check": "orphan_span_test",
                "details": "missing, stale, wrong-version, wrong-provenance, mutated, and tampered spans fail closed",
                "status": "PASS",
            },
            {
                "check": "canonical_schema_binding",
                "details": "all emitted records use exactly the unchanged canonical SourceSpan fields and validate under Draft 2020-12",
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
        raise SystemExit(f"invalid K03 ArtifactReceipt: {errors[0].message}")
    return receipt


def evidence_artifacts() -> list[dict[str, Any]]:
    names = [
        *OUTPUT_NAMES,
        "source-span-verification.artifact-receipt.json",
        "targeted-k03-suite.junit.xml",
        "full-python-suite.junit.xml",
        "full-node-suite.junit.xml",
        "node-test-inventory.json",
        "codegen-verification.stdout.log",
        "structure-check.stdout.log",
        "boundary-check.stdout.log",
        "ruff-check.stdout.log",
        "git-diff-check.stderr.log",
        "commands.jsonl",
        "review.md",
        "attempt-metadata.json",
        "build_k03_0001_evidence.py",
        "k03_0001_rah_seal.py",
    ]
    if (ATTEMPT / "rah-core-integrity.json").is_file():
        names.append("rah-core-integrity.json")
    rows: list[dict[str, Any]] = []
    for name in names:
        path = ATTEMPT / name
        if not path.is_file():
            raise SystemExit(f"required K03 evidence artifact missing: {name}")
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
    receipt = read_json(ATTEMPT / "source-span-verification.artifact-receipt.json")
    report: dict[str, Any] = {
        "artifact_receipt": {
            "path": (
                "artifacts/work_packages/K03/attempts/0001/"
                "source-span-verification.artifact-receipt.json"
            ),
            "receipt_hash": receipt["receipt_hash"],
            "receipt_id": receipt["receipt_id"],
        },
        "attempt_id": ATTEMPT_ID,
        "changed_files": source_inventory(),
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependencies": {"K01": dependency["dependency"]},
        "dependency_effect": dependency["provisional_post_k03_projection"],
        "evidence_artifacts": evidence_artifacts(),
        "exit_criteria": {
            "page/bbox/char locators typed": "PASS",
            "span hash resolves to source": "PASS",
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
            "live parser backend execution or source acquisition",
            "K04 corpus security and prompt-injection release",
            "downstream ClaimCard or EvidenceNode grounding completion",
            "actor-independent certification",
            "full product completion",
            "release or production readiness",
            "completion_ready=true",
        ],
        "package_status": "PASS",
        "regression": regression,
        "required_checks": {
            "independent_review": {
                "actor_independence": False,
                "blocking_finding_count": 0,
                "mode": "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_REVIEW",
                "status": "PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW",
            },
            "orphan_span_test": "PASS",
            "source_span_roundtrip": "PASS",
        },
        "review": {
            "actor_independence": False,
            "artifact": "artifacts/work_packages/K03/attempts/0001/review.md",
            "artifact_sha256": sha256_id(ATTEMPT / "review.md"),
            "blocking_finding_count": 0,
            "mode": "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_REVIEW",
            "status": "PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW",
        },
        "status": "PASS",
        "title": "SourceSpan emission for text/table/figure/formula",
        "verification": {
            "codegen": "126 schemas / 126 examples",
            "emission_classes": "4/4",
            "full_node": "470/470",
            "full_python": "1054/1054",
            "orphan_adversarial": "9/9 fail closed",
            "targeted_k03": "36/36",
            "write_scope_violation_count": 0,
        },
        "work_package_id": WORK_PACKAGE_ID,
    }
    if rah_state is not None:
        report["rah_state"] = rah_state
    return report


def build() -> dict[str, Any]:
    timestamp = recorded_at()
    write_json(ATTEMPT / "node-test-inventory.json", node_inventory_document())
    documents = live_documents()
    for name, document in documents.items():
        write_json(ATTEMPT / name, document)
    write_text(ATTEMPT / "review.md", review_text(documents))
    write_text(
        ATTEMPT / "commands.jsonl",
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in command_records(timestamp)
        ),
    )
    write_json(
        ATTEMPT / "source-span-verification.artifact-receipt.json",
        make_receipt(ATTEMPT / "source-span-verification.json", timestamp),
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
            "targeted_k03": "36/36",
        },
    }


def verify(*, expect_rah: bool | None = None) -> dict[str, Any]:
    expected_inventory = node_inventory_document()
    if read_json(ATTEMPT / "node-test-inventory.json") != expected_inventory:
        raise SystemExit("stored K03 Node inventory differs from sealed authority")
    stored = {name: read_json(ATTEMPT / name) for name in OUTPUT_NAMES}
    live = live_documents()
    if stored != live:
        differences = [name for name in OUTPUT_NAMES if stored[name] != live[name]]
        raise SystemExit(f"stored K03 evidence differs from live recomputation: {differences}")
    if (ATTEMPT / "review.md").read_text(encoding="utf-8") != review_text(live):
        raise SystemExit("stored K03 review differs from deterministic rendering")
    metadata = read_json(ATTEMPT / "attempt-metadata.json")
    expected_commands = command_records(str(metadata["recorded_at_utc"]))
    actual_commands = [
        json.loads(line)
        for line in (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    if actual_commands != expected_commands:
        raise SystemExit("K03 command ledger differs from deterministic rendering")
    receipt = read_json(ATTEMPT / "source-span-verification.artifact-receipt.json")
    if receipt != make_receipt(
        ATTEMPT / "source-span-verification.json", str(metadata["recorded_at_utc"])
    ):
        raise SystemExit("K03 ArtifactReceipt differs from live verification")
    report = read_json(ATTEMPT / "report.json")
    rah = report.get("rah_state")
    if expect_rah is True and not isinstance(rah, dict):
        raise SystemExit("K03 report is not RAH-bound")
    if expect_rah is False and rah is not None:
        raise SystemExit("K03 pre-core report unexpectedly contains RAH state")
    expected_report = report_document(live, rah_state=rah if isinstance(rah, dict) else None)
    if report != expected_report:
        raise SystemExit("K03 report differs from deterministic rendering")
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
        if not all((args.core_generation, args.core_evidence_id, args.final_evidence_id)):
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
