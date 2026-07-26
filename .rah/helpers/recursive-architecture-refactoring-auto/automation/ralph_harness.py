#!/usr/bin/env python3
"""RALPH goal-loop surface for the recursive architecture harness.

RALPH is a persistent goal-loop controller. It does not replace the host
agent's reasoning or repo-local gates; it records the goal, the current
iteration, the stop conditions, and the next bounded loop packet under
`.rah/ralph/`.
"""
from __future__ import annotations

# Path-shadowing guard (see rah.py): demote the script dir so a sourceless
# stdlib-named .pyc can never preempt the real stdlib at import time.
import os as _os
import sys as _sys

_here = _os.path.dirname(_os.path.abspath(__file__))
if _sys.path and _os.path.abspath(_sys.path[0] or _os.getcwd()) == _here:
    _sys.path.pop(0)
if _here not in _sys.path:
    _sys.path.append(_here)


import argparse

try:
    from cli_suggestions import SuggestingArgumentParser as _SuggestingArgumentParser
except Exception:  # stale repo helper tree may predate cli_suggestions
    _SuggestingArgumentParser = argparse.ArgumentParser
import atexit
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import state_lock
import approval_contract
import state_store
from source_coverage_harness import (
    atomic_requirements_for_mode,
    classify_writing_unit_role,
    validate_unit_coverage_rows,
)

SKILL_NAME = "recursive-architecture-refactoring-auto"
RALPH_SCHEMA_VERSION = 2
DEFAULT_MAX_ITERATIONS = 6
DEFAULT_COMPLETION_MODE = "exhaustive"
DEFAULT_REVIEW_WAIT_TIMEOUT_MS = 3_600_000

MANAGED_BLOCK_START = "<!-- RALPH MANAGED BLOCK START -->"
MANAGED_BLOCK_END = "<!-- RALPH MANAGED BLOCK END -->"

READ_FIRST = [
    "AGENTS.md",
    "docs/architecture/Phytoritas.md",
    "docs/architecture/00_workspace_audit.md",
    ".rah/state/status.json",
    ".rah/state/gates.json",
    ".rah/memory/wakeup.md",
    ".rah/plans/current_loop.md",
    ".rah/ralph/goal.json",
    ".rah/ralph/loop_state.json",
    ".rah/ralph/evidence_ledger.json",
    ".rah/ralph/plan_graph.json",
    ".rah/ralph/goal_bridge.json",
    ".rah/ralph/review_gate.json",
    ".rah/ralph/source_documents.json",
    ".rah/ralph/source_requirement_coverage.json",
]

BASE_ACCEPTANCE = [
    "The requested goal is implemented or the remaining blocker is explicit.",
    "Repo-local validation commands have been run or their absence is documented.",
    "The diff has been reviewed for correctness, regression risk, and missing tests.",
]

BASE_VALIDATION = [
    "typecheck if the repo defines one",
    "lint if the repo defines one",
    "tests relevant to the changed surface",
    "build or smoke check if the repo defines one",
]

CLOSEOUT_REQUIRED = [
    "fresh status and resume packet after final edits",
    "durable .rah JSON state parses",
    "stale objective, branch, and obsolete status wording negative-scan is clean or documented",
    "generated-output tracking decision is recorded",
    "final validation result is recorded",
]

ACCEPTANCE_DONE_STATUSES = {"met"}
VALIDATION_DONE_STATUSES = {"passed", "documented_gap", "skipped"}
CLOSEOUT_DONE_STATUSES = {"met", "documented_gap"}
COMPLETION_MODES = {"bounded", "exhaustive"}
REVIEW_APPROVED_STATUSES = {"approved"}
TERMINAL_STATUSES = {"done", "blocked", "cancelled", "canceled", "failed"}
EVIDENCE_ELIGIBLE_KINDS = {"evidence", "documented_gap", "review", "validation", "closeout"}
SOURCE_COVERAGE_DONE_STATUSES = {
    "implemented",
    "already_covered",
    "equivalent",
    "intentionally_excluded",
    "analyzed",
    "summarized",
    "synthesized",
    "processed",
    "covered",
}
SOURCE_COVERAGE_VALID_STATUSES = SOURCE_COVERAGE_DONE_STATUSES | {"unstarted", "in_progress", "blocked", ""}
SOURCE_COVERAGE_GOAL_PATTERN = re.compile(
    r"(\.pdf\b|\.md\b|\.markdown\b|\.txt\b|\.rst\b|pdf|paper|markdown|pasted|stdin|source material|"
    r"document|spec|checklist|artifact note|issue body|pr comment|논문|문서|자료|붙여넣|전체\s*분석|처음부터\s*끝까지|빠짐없이)",
    re.IGNORECASE,
)
def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slugify(value: str) -> str:
    collapsed = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower())
    return re.sub(r"-{2,}", "-", collapsed).strip("-") or "goal"


def load_json(path: Path, *, strict: bool = False) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        if strict:
            raise SystemExit(f"Invalid JSON at {path}. Run `rah.py doctor` and recover the state before writing: {exc}")
        return None


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def relative_to_root(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path)


def safe_timestamp(value: str) -> str:
    return value.replace(":", "").replace("+00:00", "Z").replace("+", "Z")


def normalized_goal_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def terminal_status(existing_goal: dict[str, Any] | None, loop_state: dict[str, Any] | None) -> str | None:
    status = (
        (loop_state.get("status") if isinstance(loop_state, dict) else None)
        or (existing_goal.get("status") if isinstance(existing_goal, dict) else None)
    )
    status_text = str(status or "").lower()
    return status_text if status_text in TERMINAL_STATUSES else None


def retained_goal_text(existing_goal: dict[str, Any] | None, loop_state: dict[str, Any] | None) -> str:
    if isinstance(existing_goal, dict) and existing_goal.get("goal"):
        return str(existing_goal.get("goal") or "")
    if isinstance(loop_state, dict):
        for key in ("goal", "objective"):
            if loop_state.get(key):
                return str(loop_state.get(key) or "")
    return ""


def retained_goal_differs(
    existing_goal: dict[str, Any] | None,
    loop_state: dict[str, Any] | None,
    requested_goal: str | None,
) -> bool:
    if not requested_goal:
        return False
    existing_text = retained_goal_text(existing_goal, loop_state)
    if existing_text:
        return normalized_goal_text(existing_text) != normalized_goal_text(requested_goal)
    return isinstance(existing_goal, dict) or isinstance(loop_state, dict)


def unique_archive_path(repo_root: Path, now: str, reason: str) -> Path:
    archive_root = repo_root / ".rah" / "archive"
    archive_root.mkdir(parents=True, exist_ok=True)
    base = archive_root / f"ralph-{safe_timestamp(now)}-{slugify(reason)[:40]}"
    candidate = base
    counter = 2
    while candidate.exists():
        candidate = archive_root / f"{base.name}-{counter}"
        counter += 1
    return candidate


def archive_ralph_state(repo_root: Path, *, reason: str, now: str) -> dict[str, Any] | None:
    source = repo_root / ".rah" / "ralph"
    if not source.exists():
        return None
    target = unique_archive_path(repo_root, now, reason)
    shutil.move(str(source), str(target))
    return {
        "reason": reason,
        "archived_at_utc": now,
        "archive_path": relative_to_root(target, repo_root),
    }


def command_token(value: Any) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def first_existing_goal(rah_root: Path) -> dict[str, Any] | None:
    path = rah_root / "ralph" / "goal.json"
    payload = load_json(path, strict=True)
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise SystemExit(f"Invalid RALPH goal shape at {path}; expected JSON object.")
    return payload


def existing_loop_state(rah_root: Path) -> dict[str, Any] | None:
    path = rah_root / "ralph" / "loop_state.json"
    payload = load_json(path, strict=True)
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise SystemExit(f"Invalid RALPH loop state shape at {path}; expected JSON object.")
    return payload


def existing_evidence_ledger(rah_root: Path) -> dict[str, Any]:
    path = rah_root / "ralph" / "evidence_ledger.json"
    payload = load_json(path, strict=True)
    if payload is None:
        return {"schema_version": RALPH_SCHEMA_VERSION, "entries": []}
    if isinstance(payload, dict) and isinstance(payload.get("entries"), list):
        return validate_evidence_ledger(payload, source=str(path))
    raise SystemExit(f"Invalid RALPH evidence ledger shape at {path}; expected object with entries array.")


def existing_plan_graph(rah_root: Path) -> dict[str, Any] | None:
    path = rah_root / "ralph" / "plan_graph.json"
    payload = load_json(path, strict=True)
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise SystemExit(f"Invalid RALPH plan graph shape at {path}; expected JSON object.")
    return payload


def existing_goal_bridge(rah_root: Path) -> dict[str, Any] | None:
    path = rah_root / "ralph" / "goal_bridge.json"
    payload = load_json(path, strict=True)
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise SystemExit(f"Invalid RALPH goal bridge shape at {path}; expected JSON object.")
    return payload


def existing_review_gate(rah_root: Path) -> dict[str, Any] | None:
    path = rah_root / "ralph" / "review_gate.json"
    payload = load_json(path, strict=True)
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise SystemExit(f"Invalid RALPH review gate shape at {path}; expected JSON object.")
    return payload


def has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set)):
        return any(has_value(item) for item in value)
    if isinstance(value, dict):
        return any(has_value(item) for item in value.values())
    return bool(value)


def infer_source_coverage_required(goal_text: str | None) -> bool:
    return bool(goal_text and SOURCE_COVERAGE_GOAL_PATTERN.search(goal_text))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def source_row_requires_semantic_contract(row: dict[str, Any]) -> bool:
    return bool(row.get("semantic_contract_required")) or str(row.get("coverage_mode") or "").strip().lower() == "implementation"


def source_row_requires_provenance(row: dict[str, Any]) -> bool:
    return bool(row.get("provenance_evidence_required")) or source_row_requires_semantic_contract(row)


def count_atomic_requirements_for_mode(
    text: str,
    coverage_mode: str,
    *,
    locator: str | None = None,
) -> int:
    """Backward-compatible count wrapper over the canonical atomizer."""

    return len(atomic_requirements_for_mode(text, coverage_mode, locator=locator))


def source_coverage_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("requirements", "rows", "coverage", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []


def assess_prd_projection(
    root: Path,
    *,
    required: bool = False,
    source_coverage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assess the optional PRD projection gate.

    Return shape mirrors assess_source_coverage(): present/required/ready/
    blocks_completion/missing_reason plus audit id lists. PRD is a planning
    view over source coverage; it blocks completion only when explicitly
    required via the goal payload (prd_required).
    """
    del source_coverage  # readiness is recomputed live from durable artifacts
    ralph_root = root / ".rah" / "ralph"
    prd_path = ralph_root / "prd.json"
    audit_path = ralph_root / "prd_mapping_audit.json"
    base = {
        "present": False,
        "required": required,
        "audit_ready": False,
        "ready": False,
        "needs_review": False,
        "stale": False,
        "blocks_completion": bool(required),
        "missing_reason": "prd_required_without_prd_projection" if required else None,
        "path": relative_to_root(audit_path, root),
        "source_atoms_present": (ralph_root / "source_requirement_atoms.json").exists(),
        "row_coverage_ready": False,
        "atom_coverage_ready": False,
        "criteria_coverage_ready": False,
        "verification_coverage_ready": False,
        "unmapped_source_row_ids": [],
        "unmapped_required_atom_ids": [],
        "negative_atoms_without_negative_test": [],
        "high_risk_atoms_without_verification": [],
        "generic_criteria_story_ids": [],
        "raw_source_leak_story_ids": [],
        "review_reasons": [],
    }
    def _read_json_or_error(path: Path) -> tuple[Any, str | None]:
        if not path.exists():
            return None, None
        try:
            return json.loads(path.read_text(encoding="utf-8")), None
        except Exception as exc:
            return None, f"{path.name}: {exc}"

    # A broken PRD artifact must degrade this assessment, never take down the
    # whole RALPH loop: fail closed when required, warn-only otherwise.
    prd_payload, prd_error = _read_json_or_error(prd_path)
    if prd_error:
        return {
            **base,
            "present": True,
            "needs_review": True,
            "missing_reason": "prd_json_parse_error",
            "review_reasons": [prd_error],
        }
    if not isinstance(prd_payload, dict):
        return base
    base["present"] = True
    coverage_payload, coverage_error = _read_json_or_error(
        ralph_root / "source_requirement_coverage.json"
    )
    if coverage_error:
        return {
            **base,
            "needs_review": True,
            "missing_reason": "source_coverage_parse_error",
            "review_reasons": [coverage_error],
        }
    if not isinstance(coverage_payload, dict):
        base["missing_reason"] = "prd_present_without_source_coverage"
        return base
    try:
        import prd_projection_harness as prd_lib
    except Exception as exc:  # missing helper deployment: fail closed when required
        base["missing_reason"] = f"prd_projection_helper_unavailable: {exc}"
        return base
    atoms_payload, _atoms_error = _read_json_or_error(ralph_root / "source_requirement_atoms.json")
    try:
        if not isinstance(atoms_payload, dict):
            # atoms are derived; regenerate deterministically instead of failing
            atoms_payload = prd_lib.ensure_atoms_payload(coverage_payload, root, write=False)
        waivers_payload = prd_lib.load_waivers(root)
        stored_audit, _audit_error = _read_json_or_error(ralph_root / "prd_mapping_audit.json")
        fingerprint = prd_lib.audit_input_fingerprint(
            prd_payload, coverage_payload, atoms_payload, waivers_payload
        )
        if isinstance(stored_audit, dict) and stored_audit.get("input_fingerprint") == fingerprint:
            # Hot-path cache: the audit is a pure function of its inputs, so an
            # unchanged fingerprint means the stored audit is exact — skipping
            # the leak-index/text-hash file scan on every RALPH cycle. Tampering
            # with source unit FILES alone bypasses this cache, but the source
            # coverage gate (assess_source_coverage) verifies text hashes
            # independently and still blocks completion.
            audit = stored_audit
        else:
            audit = prd_lib.validate_prd_projection(
                prd_payload,
                coverage_payload,
                atoms_payload,
                waivers_payload,
                repo_root=root,
                prd_required=required,
            )
    except (SystemExit, Exception) as exc:
        return {
            **base,
            "needs_review": True,
            "missing_reason": "prd_assessment_error",
            "review_reasons": [f"{type(exc).__name__}: {exc}"],
        }
    ready = bool(audit.get("prd_ready"))
    return {
        **base,
        "missing_reason": None,
        "audit_ready": bool(audit.get("audit_ready")),
        "ready": ready,
        "needs_review": bool(audit.get("needs_review")),
        "stale": bool(audit.get("stale")),
        "blocks_completion": bool(required and not ready),
        "source_atoms_present": True,
        "row_coverage_ready": bool(audit.get("row_coverage_ready")),
        "atom_coverage_ready": bool(audit.get("atom_coverage_ready")),
        "criteria_coverage_ready": bool(audit.get("criteria_coverage_ready")),
        "verification_coverage_ready": bool(audit.get("verification_coverage_ready")),
        "unmapped_source_row_ids": audit.get("unmapped_source_row_ids", []),
        "unmapped_required_atom_ids": audit.get("unmapped_required_atom_ids", []),
        "negative_atoms_without_negative_test": audit.get("negative_atoms_without_negative_test", []),
        "high_risk_atoms_without_verification": audit.get("high_risk_atoms_without_verification", []),
        "generic_criteria_story_ids": audit.get("generic_criteria_story_ids", []),
        "raw_source_leak_story_ids": audit.get("raw_source_leak_story_ids", []),
        "review_reasons": audit.get("review_reasons", []),
    }


def assess_source_coverage(root: Path, *, required: bool = False) -> dict[str, Any]:
    ralph_root = root / ".rah" / "ralph"
    coverage_path = ralph_root / "source_requirement_coverage.json"
    source_documents_path = ralph_root / "source_documents.json"
    coverage_payload = load_json(coverage_path, strict=True)
    source_documents_payload = load_json(source_documents_path, strict=True)
    source_documents_present = source_documents_payload is not None
    if coverage_payload is None:
        missing_reason = None
        if required:
            missing_reason = "source_coverage_required_without_source_requirement_coverage"
        elif source_documents_present:
            missing_reason = "source_documents_present_without_source_requirement_coverage"
        return {
            "present": False,
            "required": required,
            "source_documents_present": source_documents_present,
            "ready": not (source_documents_present or required),
            "blocks_completion": source_documents_present or required,
            "missing_reason": missing_reason,
            "path": relative_to_root(coverage_path, root),
            "total_rows": 0,
            "missing_ids": [],
            "missing_evidence_ids": [],
            "missing_source_evidence_ids": [],
            "missing_validation_ids": [],
            "missing_semantic_validation_ids": [],
            "missing_negative_test_ids": [],
            "missing_provenance_evidence_ids": [],
            "coarse_requirement_unit_ids": [],
            "invalid_row_ids": [],
            "missing_manifest_unit_row_ids": [],
            "unknown_row_unit_ids": [],
            "hash_mismatch_ids": [],
        }

    rows = source_coverage_rows(coverage_payload)
    missing_ids: list[str] = []
    missing_evidence_ids: list[str] = []
    missing_source_evidence_ids: list[str] = []
    missing_validation_ids: list[str] = []
    missing_semantic_validation_ids: list[str] = []
    missing_negative_test_ids: list[str] = []
    missing_provenance_evidence_ids: list[str] = []
    coarse_requirement_unit_ids: list[str] = []
    invalid_row_ids: list[str] = []
    duplicate_row_ids: list[str] = []
    unknown_status_ids: list[str] = []
    missing_span_ids: list[str] = []
    missing_unit_text_ids: list[str] = []
    missing_manifest_unit_row_ids: list[str] = []
    unknown_row_unit_ids: list[str] = []
    hash_mismatch_ids: list[str] = []
    row_unit_ids: set[str] = set()
    rows_by_unit: dict[str, list[dict[str, Any]]] = {}
    unit_text_by_id: dict[str, str] = {}
    seen_row_ids: set[str] = set()
    manifest = coverage_payload.get("source_unit_manifest") if isinstance(coverage_payload, dict) else {}
    if not isinstance(manifest, dict):
        invalid_row_ids.append("__source_unit_manifest__")
        manifest = {}
    manifest_units = manifest.get("units") if isinstance(manifest.get("units"), list) else []
    if manifest.get("total_units") is not None and manifest.get("total_units") != len(manifest_units):
        invalid_row_ids.append("__source_unit_manifest_total_units__")
    known_unit_ids = {
        str(unit.get("unit_id"))
        for unit in manifest_units
        if isinstance(unit, dict) and unit.get("unit_id")
    }
    manifest_by_id = {
        str(unit.get("unit_id")): unit
        for unit in manifest_units
        if isinstance(unit, dict) and unit.get("unit_id")
    }
    for unit in manifest_units:
        if not isinstance(unit, dict):
            continue
        unit_id = str(unit.get("unit_id") or "").strip()
        if not unit_id:
            continue
        text_path_value = str(unit.get("text_path") or "").strip()
        if not text_path_value or not (root / text_path_value).exists():
            missing_unit_text_ids.append(unit_id)
            continue
        expected_sha = str(unit.get("text_sha256") or "").strip()
        expected_excerpt_hash = str(unit.get("excerpt_hash") or "").strip()
        if expected_sha or expected_excerpt_hash:
            try:
                text = (root / text_path_value).read_text(encoding="utf-8")
                unit_text_by_id[unit_id] = text
                if expected_sha and sha256_text(text) != expected_sha:
                    hash_mismatch_ids.append(unit_id)
                if expected_excerpt_hash and short_hash(text) != expected_excerpt_hash:
                    hash_mismatch_ids.append(unit_id)
            except OSError:
                missing_unit_text_ids.append(unit_id)
    blocked_unit_ids = [
        str(unit.get("unit_id"))
        for unit in manifest_units
        if isinstance(unit, dict) and str(unit.get("extraction_status") or "").lower() == "blocked"
    ]
    for idx, row in enumerate(rows, start=1):
        row_id = str(row.get("requirement_id") or row.get("id") or f"row-{idx:04d}")
        if row_id in seen_row_ids:
            duplicate_row_ids.append(row_id)
        seen_row_ids.add(row_id)
        status = str(row.get("status") or "").strip().lower()
        if status not in SOURCE_COVERAGE_VALID_STATUSES:
            unknown_status_ids.append(row_id)
        span = row.get("source_span")
        row_unit_id = str(row.get("source_unit_id") or (span.get("unit_id") if isinstance(span, dict) else "") or "").strip()
        if row_unit_id:
            row_unit_ids.add(row_unit_id)
            rows_by_unit.setdefault(row_unit_id, []).append(row)
            if known_unit_ids and row_unit_id not in known_unit_ids:
                unknown_row_unit_ids.append(row_id)
        if not isinstance(span, dict) or not span.get("unit_id") or not span.get("excerpt_hash"):
            missing_span_ids.append(row_id)
        elif known_unit_ids and str(span.get("unit_id")) not in known_unit_ids:
            missing_span_ids.append(row_id)
        elif isinstance(span, dict):
            manifest_unit = manifest_by_id.get(str(span.get("unit_id")))
            if manifest_unit and str(span.get("excerpt_hash")) != str(manifest_unit.get("excerpt_hash")):
                hash_mismatch_ids.append(row_id)
            manifest_text_path = str((manifest_unit or {}).get("text_path") or "").strip()
            row_text_path = str(row.get("source_unit_text_path") or "").strip()
            if manifest_text_path and row_text_path and row_text_path != manifest_text_path:
                hash_mismatch_ids.append(row_id)
        text_path_value = str(row.get("source_unit_text_path") or "").strip()
        if not text_path_value or not (root / text_path_value).exists():
            missing_unit_text_ids.append(row_id)
        if status not in SOURCE_COVERAGE_DONE_STATUSES:
            missing_ids.append(row_id)
            continue
        has_evidence = has_value(row.get("evidence"))
        has_source_evidence = has_value(row.get("source_evidence"))
        requires_source_evidence = bool(row.get("source_evidence_required"))
        has_validation = has_value(row.get("validation"))
        has_semantic_validation = has_value(row.get("semantic_validation"))
        has_negative_test = has_value(row.get("negative_tests"))
        has_provenance_evidence = has_value(row.get("provenance_evidence"))
        requires_semantic_contract = source_row_requires_semantic_contract(row)
        requires_provenance = source_row_requires_provenance(row)
        has_exclusion_reason = has_value(row.get("reason")) or has_value(row.get("exclusion_reason"))
        if not has_evidence:
            missing_evidence_ids.append(row_id)
        if status != "intentionally_excluded" and requires_source_evidence and not has_source_evidence:
            missing_source_evidence_ids.append(row_id)
        if status == "intentionally_excluded":
            if not has_exclusion_reason:
                invalid_row_ids.append(row_id)
        elif not has_validation:
            missing_validation_ids.append(row_id)
        if status != "intentionally_excluded" and requires_semantic_contract:
            if not has_semantic_validation:
                missing_semantic_validation_ids.append(row_id)
            if not has_negative_test:
                missing_negative_test_ids.append(row_id)
        if status != "intentionally_excluded" and requires_provenance and not has_provenance_evidence:
            missing_provenance_evidence_ids.append(row_id)

    missing_unit_text_ids = sorted(set(missing_unit_text_ids))
    missing_manifest_unit_row_ids = sorted(known_unit_ids - row_unit_ids)
    coverage_mode = str(coverage_payload.get("coverage_mode") or "").strip().lower() if isinstance(coverage_payload, dict) else ""
    for unit_id, unit_text in unit_text_by_id.items():
        unit = manifest_by_id.get(unit_id) or {}
        locator = str(unit.get("locator") or "").strip() or None
        expected_role = classify_writing_unit_role(locator) if coverage_mode == "writing" else None
        actual_role = str(unit.get("unit_role") or "").strip() or None
        unit_issues = validate_unit_coverage_rows(
            unit_id,
            unit_text,
            coverage_mode,
            locator,
            rows_by_unit.get(unit_id, []),
        )
        if actual_role != expected_role or unit_issues:
            coarse_requirement_unit_ids.append(unit_id)
    unknown_row_unit_ids = sorted(set(unknown_row_unit_ids))
    hash_mismatch_ids = sorted(set(hash_mismatch_ids))
    invalid_row_ids = sorted(
        set(
            invalid_row_ids
            + duplicate_row_ids
            + unknown_status_ids
            + missing_span_ids
            + missing_unit_text_ids
            + missing_manifest_unit_row_ids
            + unknown_row_unit_ids
            + hash_mismatch_ids
            + coarse_requirement_unit_ids
        )
    )
    ready = (
        bool(rows)
        and not missing_ids
        and not missing_evidence_ids
        and not missing_source_evidence_ids
        and not missing_validation_ids
        and not missing_semantic_validation_ids
        and not missing_negative_test_ids
        and not missing_provenance_evidence_ids
        and not coarse_requirement_unit_ids
        and not invalid_row_ids
        and not blocked_unit_ids
        and not missing_unit_text_ids
        and not missing_manifest_unit_row_ids
        and not unknown_row_unit_ids
        and not hash_mismatch_ids
    )
    return {
        "present": True,
        "required": required,
        "source_documents_present": source_documents_present,
        "ready": ready,
        "blocks_completion": not ready,
        "path": relative_to_root(coverage_path, root),
        "total_rows": len(rows),
        "coverage_mode": coverage_payload.get("coverage_mode") if isinstance(coverage_payload, dict) else None,
        "source_unit_total": manifest.get("total_units"),
        "source_unit_processed": manifest.get("processed_unit_count"),
        "source_unit_blocked_ids": blocked_unit_ids,
        "missing_ids": missing_ids,
        "missing_evidence_ids": missing_evidence_ids,
        "missing_source_evidence_ids": missing_source_evidence_ids,
        "missing_validation_ids": missing_validation_ids,
        "missing_semantic_validation_ids": missing_semantic_validation_ids,
        "missing_negative_test_ids": missing_negative_test_ids,
        "missing_provenance_evidence_ids": missing_provenance_evidence_ids,
        "coarse_requirement_unit_ids": coarse_requirement_unit_ids,
        "invalid_row_ids": invalid_row_ids,
        "duplicate_row_ids": duplicate_row_ids,
        "unknown_status_ids": unknown_status_ids,
        "missing_span_ids": missing_span_ids,
        "missing_unit_text_ids": missing_unit_text_ids,
        "missing_manifest_unit_row_ids": missing_manifest_unit_row_ids,
        "unknown_row_unit_ids": unknown_row_unit_ids,
        "hash_mismatch_ids": hash_mismatch_ids,
    }


def normalize_string_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(item).strip() for item in values if str(item).strip()]


def build_matrix(
    items: list[str],
    prefix: str,
    text_key: str,
    default_status: str,
    existing_matrix: Any,
) -> list[dict[str, Any]]:
    existing_by_text: dict[str, dict[str, Any]] = {}
    if isinstance(existing_matrix, list):
        for row in existing_matrix:
            if isinstance(row, dict):
                text = str(row.get(text_key) or row.get("description") or "").strip()
                if text:
                    existing_by_text[text] = row

    matrix: list[dict[str, Any]] = []
    for idx, item in enumerate(items, start=1):
        previous = existing_by_text.get(item, {})
        matrix.append(
            {
                "id": f"{prefix}{idx}",
                text_key: item,
                "status": previous.get("status") or default_status,
                "evidence": previous.get("evidence") if isinstance(previous.get("evidence"), list) else [],
                "last_checked_at_utc": previous.get("last_checked_at_utc"),
                "blocking_reason": previous.get("blocking_reason"),
            }
        )
    return matrix


def ensure_goal_matrices(goal: dict[str, Any]) -> None:
    definition = goal.setdefault("definition_of_done", {})
    acceptance = normalize_string_list(definition.get("acceptance_criteria"))
    validation = normalize_string_list(definition.get("validation_commands"))
    closeout = normalize_string_list(definition.get("closeout_required")) or list(CLOSEOUT_REQUIRED)
    definition["acceptance_criteria"] = acceptance
    definition["validation_commands"] = validation
    definition["closeout_required"] = closeout
    definition["acceptance_matrix"] = build_matrix(
        acceptance,
        "A",
        "criterion",
        "unmet",
        definition.get("acceptance_matrix"),
    )
    definition["validation_matrix"] = build_matrix(
        validation,
        "V",
        "check",
        "unchecked",
        definition.get("validation_matrix"),
    )
    definition["closeout_matrix"] = build_matrix(
        closeout,
        "C",
        "requirement",
        "unmet",
        definition.get("closeout_matrix"),
    )


def _ledger_high_water(ledger: dict[str, Any]) -> int:
    entries = ledger.get("entries") if isinstance(ledger.get("entries"), list) else []
    highest = 0
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        raw = str(entry.get("id") or "")
        if raw.startswith("E") and raw[1:].isdigit():
            highest = max(highest, int(raw[1:]))
    recorded = ledger.get("issued_id_high_water")
    if isinstance(recorded, int) and recorded > highest:
        highest = recorded
    return highest


def next_evidence_id(ledger: dict[str, Any]) -> str:
    # max(existing, persisted high-water)+1: deleting the highest entry must
    # not re-issue its ID either — an old row reference would silently
    # rebind to new, unrelated evidence (reviewer-reproduced R10 gap).
    return f"E{_ledger_high_water(ledger) + 1:04d}"


def validate_evidence_ledger(ledger: Any, *, source: str = "evidence ledger") -> dict[str, Any]:
    """Schema gate at every load/mutation boundary (R8).

    Duplicate or malformed IDs must fail closed BEFORE any state change:
    a duplicate silently collapses in id-indexed maps and re-interprets
    which entry a completed row's reference points to."""

    if not isinstance(ledger, dict):
        raise SystemExit(f"{source}: expected object, got {type(ledger).__name__}")
    entries = ledger.get("entries")
    if not isinstance(entries, list):
        raise SystemExit(f"{source}: entries must be a list")
    seen: set[str] = set()
    highest = 0
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise SystemExit(f"{source}: entry #{index} is not an object")
        entry_id = str(entry.get("id") or "").strip()
        if not entry_id:
            raise SystemExit(f"{source}: entry #{index} has no id")
        if not re.fullmatch(r"E\d{4,}", entry_id):
            raise SystemExit(f"{source}: malformed evidence id {entry_id!r} (expected E0000 form)")
        if entry_id in seen:
            raise SystemExit(f"{source}: duplicate evidence id {entry_id}")
        seen.add(entry_id)
        highest = max(highest, int(entry_id[1:]))
        if not str(entry.get("kind") or "").strip():
            raise SystemExit(f"{source}: entry {entry_id} has no kind")
    recorded = ledger.get("issued_id_high_water")
    if recorded is not None:
        if not isinstance(recorded, int) or recorded < highest:
            raise SystemExit(
                f"{source}: issued_id_high_water {recorded!r} is below the highest entry E{highest:04d} — "
                "a rewound high-water mark would re-issue referenced IDs"
            )
    return ledger


def add_evidence_entry(
    ledger: dict[str, Any],
    *,
    now: str,
    goal_id: str,
    iteration: int,
    kind: str,
    summary: str,
) -> str:
    entry_id = next_evidence_id(ledger)
    entry = {
        "id": entry_id,
        "created_at_utc": now,
        "goal_id": goal_id,
        "iteration": iteration,
        "kind": kind,
        "summary": summary,
    }
    ledger.setdefault("entries", []).append(entry)
    # Persist the high-water mark so even deleting this entry later can
    # never re-issue its ID (R10).
    ledger["issued_id_high_water"] = int(entry_id[1:])
    ledger["updated_at_utc"] = now
    return entry_id


def find_matrix_row(matrix: Any, row_id: str) -> dict[str, Any] | None:
    if not isinstance(matrix, list):
        return None
    for row in matrix:
        if isinstance(row, dict) and str(row.get("id")) == row_id:
            return row
    return None


def mark_matrix_rows(
    matrix: Any,
    row_ids: list[str],
    *,
    status: str,
    now: str,
    evidence_ids: list[str],
) -> list[str]:
    missing: list[str] = []
    for row_id in row_ids:
        row = find_matrix_row(matrix, row_id)
        if row is None:
            missing.append(row_id)
            continue
        row["status"] = status
        row["last_checked_at_utc"] = now
        row_evidence = row.get("evidence") if isinstance(row.get("evidence"), list) else []
        for evidence_id in evidence_ids:
            if evidence_id not in row_evidence:
                row_evidence.append(evidence_id)
        row["evidence"] = row_evidence
        row["blocking_reason"] = None
    return missing


def evidence_entries_by_id(ledger: dict[str, Any]) -> dict[str, dict[str, Any]]:
    entries = ledger.get("entries") if isinstance(ledger.get("entries"), list) else []
    return {
        str(entry.get("id")): entry
        for entry in entries
        if isinstance(entry, dict) and entry.get("id")
    }


def explicit_evidence_ids(ledger: dict[str, Any], ids: list[str]) -> tuple[list[str], list[str]]:
    entries = evidence_entries_by_id(ledger)
    valid: list[str] = []
    missing: list[str] = []
    for evidence_id in ids:
        entry = entries.get(str(evidence_id))
        if entry is None or entry.get("kind") not in EVIDENCE_ELIGIBLE_KINDS:
            missing.append(str(evidence_id))
        else:
            valid.append(str(evidence_id))
    return valid, missing


def completed_rows_missing_evidence(
    matrix: Any,
    done_statuses: set[str],
    ledger: dict[str, Any] | None = None,
    goal_id: str | None = None,
) -> list[str]:
    """Done rows with empty OR unresolvable evidence references (R9).

    Empty-only checking allowed the BOGUS-id false completion: a row could
    carry any string while one eligible entry elsewhere in the ledger
    satisfied the global existence check. Every reference on a done row must
    now resolve to an existing, eligible-kind entry of the SAME goal."""

    missing: list[str] = []
    if not isinstance(matrix, list):
        return missing
    entries = evidence_entries_by_id(ledger) if isinstance(ledger, dict) else None
    for row in matrix:
        if not isinstance(row, dict) or row.get("status") not in done_statuses:
            continue
        evidence = row.get("evidence") if isinstance(row.get("evidence"), list) else []
        if not evidence:
            missing.append(str(row.get("id") or "unknown"))
            continue
        if entries is None:
            # Fail closed (reviewer finding): without a ledger, references
            # cannot be resolved — an unresolvable reference is never proof.
            missing.append(str(row.get("id") or "unknown"))
            continue
        for reference in evidence:
            entry = entries.get(str(reference))
            if (
                entry is None
                or entry.get("kind") not in EVIDENCE_ELIGIBLE_KINDS
                or (goal_id and str(entry.get("goal_id") or "") != str(goal_id))
            ):
                missing.append(str(row.get("id") or "unknown"))
                break
    return missing


def apply_goal_progress(
    goal: dict[str, Any],
    ledger: dict[str, Any],
    args: argparse.Namespace,
    *,
    now: str,
    iteration: int,
) -> dict[str, Any]:
    goal_id = str(goal.get("goal_id") or "ralph-goal")
    created_evidence: list[str] = []
    for summary in args.record_evidence:
        created_evidence.append(
            add_evidence_entry(
                ledger,
                now=now,
                goal_id=goal_id,
                iteration=iteration,
                kind="evidence",
                summary=summary,
            )
        )
    for summary in args.record_gap:
        created_evidence.append(
            add_evidence_entry(
                ledger,
                now=now,
                goal_id=goal_id,
                iteration=iteration,
                kind="documented_gap",
                summary=summary,
            )
        )

    existing_evidence, missing_evidence = explicit_evidence_ids(ledger, args.with_evidence)
    evidence_for_rows = [*created_evidence, *existing_evidence]

    definition = goal.setdefault("definition_of_done", {})
    closeout_matrix = definition.get("closeout_matrix")
    missing_acceptance = mark_matrix_rows(
        definition.get("acceptance_matrix"),
        args.acceptance_met,
        status="met",
        now=now,
        evidence_ids=evidence_for_rows,
    )
    missing_validation = mark_matrix_rows(
        definition.get("validation_matrix"),
        args.validation_passed,
        status="passed",
        now=now,
        evidence_ids=evidence_for_rows,
    )
    missing_closeout = mark_matrix_rows(
        closeout_matrix,
        args.closeout_met,
        status="met",
        now=now,
        evidence_ids=evidence_for_rows,
    )
    missing_closeout.extend(
        mark_matrix_rows(
            closeout_matrix,
            args.closeout_documented,
            status="documented_gap",
            now=now,
            evidence_ids=evidence_for_rows,
        )
    )
    return {
        "created_evidence": created_evidence,
        "used_evidence": evidence_for_rows,
        "missing_evidence_ids": missing_evidence,
        "missing_acceptance_ids": missing_acceptance,
        "missing_validation_ids": missing_validation,
        "missing_closeout_ids": missing_closeout,
    }


def _canonical_sha(payload: Any) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_review_snapshot(
    root: Path,
    goal: dict[str, Any],
    ledger: dict[str, Any],
) -> dict[str, Any]:
    """Review-subject snapshot (R11): what exactly is being approved.

    Captured at --request-review and re-derived at approval and mark-done; a
    drifted component turns an existing approval stale (R13) instead of
    silently blessing different work. Git fields are best-effort (None on a
    non-git repo or git failure) and only non-None pairs are compared."""

    definition = goal.get("definition_of_done") if isinstance(goal.get("definition_of_done"), dict) else {}
    # Full-row binding (reviewer finding): projecting only id/status/evidence
    # let requirement/criterion text, validation notes, and proof fields
    # change under an existing approval without going stale.
    matrices = [
        [row for row in (definition.get(key) or []) if isinstance(row, dict)]
        for key in ("acceptance_matrix", "validation_matrix", "closeout_matrix")
    ]
    entries = ledger.get("entries") if isinstance(ledger.get("entries"), list) else []
    ledger_view = [e for e in entries if isinstance(e, dict)]
    coverage_view = None
    coverage_payload = load_json(root / ".rah" / "ralph" / "source_requirement_coverage.json", strict=False)
    if isinstance(coverage_payload, dict):
        coverage_view = [
            row
            for row in (coverage_payload.get("requirements") or [])
            if isinstance(row, dict)
        ]
    snapshot: dict[str, Any] = {
        "schema": 2,
        "goal_id": goal.get("goal_id"),
        "matrices_sha256": _canonical_sha(matrices),
        "ledger_head_sha256": _canonical_sha(ledger_view),
        "coverage_sha256": _canonical_sha(coverage_view) if coverage_view is not None else None,
        "git_head": None,
        "tracked_diff_sha256": None,
        "untracked_manifest_sha256": None,
    }
    if (root / ".git").exists():
        # In a git repo, a failed git command is a DEGRADED capture, not a
        # silent None (reviewer finding: request-time and approval-time
        # failures compared None == None and passed).
        def _git_bytes(*git_args: str) -> bytes | None:
            try:
                completed = subprocess.run(
                    ["git", *git_args],
                    cwd=str(root),
                    capture_output=True,
                    timeout=60,
                )
            except (OSError, subprocess.TimeoutExpired):
                return None
            if completed.returncode != 0:
                return None
            return completed.stdout

        head = _git_bytes("rev-parse", "HEAD")
        diff = _git_bytes("diff", "--binary", "HEAD")
        untracked = _git_bytes("-c", "core.quotepath=false", "ls-files", "--others", "--exclude-standard", "-z")
        snapshot["git_head"] = (
            head.decode("ascii", errors="replace").strip() if head else "<git-error>"
        )
        snapshot["tracked_diff_sha256"] = (
            hashlib.sha256(diff).hexdigest() if diff is not None else "<git-error>"
        )
        if untracked is not None:
            # Content-bound (reviewer finding): a name-only manifest let the
            # bytes of already-listed untracked files change under an
            # approval. NUL-separated unquoted names (reviewer round 2: the
            # default quoting mangled non-ASCII names into <unreadable>
            # constants). Files above the cap fall back to (size, mtime_ns)
            # — documented residual for same-size-same-mtime rewrites.
            digest = hashlib.sha256()
            names = [
                raw.decode("utf-8", errors="surrogateescape")
                for raw in untracked.split(b"\x00")
                if raw
            ]
            for rel in sorted(names):
                digest.update(rel.encode("utf-8", errors="surrogateescape") + b"\x00")
                target = root / rel
                try:
                    # Streaming content hash with NO size cap (Pro round 2
                    # reproduced a same-size-same-mtime rewrite defeating the
                    # metadata fallback — every review-bound byte counts).
                    with target.open("rb") as handle:
                        for chunk in iter(lambda: handle.read(1 << 20), b""):
                            digest.update(chunk)
                except OSError:
                    digest.update(b"<unreadable>")
                digest.update(b"\x00")
            snapshot["untracked_manifest_sha256"] = digest.hexdigest()
        else:
            snapshot["untracked_manifest_sha256"] = "<git-error>"
    return snapshot


REVIEW_SNAPSHOT_COMPARE_KEYS = (
    "goal_id",
    "matrices_sha256",
    "ledger_head_sha256",
    "coverage_sha256",
    "git_head",
    "tracked_diff_sha256",
    "untracked_manifest_sha256",
)


def review_snapshot_drift(stored: Any, current: dict[str, Any]) -> list[str]:
    # Fail-closed comparison (reviewer finding): a missing/invalid stored
    # snapshot or a component that BECAME unavailable is drift, not silence.
    if not isinstance(stored, dict):
        return ["stored_snapshot_missing"]
    changed: list[str] = []
    for key in REVIEW_SNAPSHOT_COMPARE_KEYS:
        stored_value = stored.get(key)
        current_value = current.get(key)
        if stored_value is None and current_value is None:
            continue
        if "<git-error>" in (stored_value, current_value):
            # A failed capture on EITHER side can never prove sameness
            # (reviewer round 2: double failure used to compare equal).
            changed.append(key)
            continue
        if stored_value != current_value:
            changed.append(key)
    return changed


def review_gate_status(review_gate: dict[str, Any] | None) -> str:
    if not isinstance(review_gate, dict):
        return "missing"
    return str(review_gate.get("status") or "missing").lower()


def build_review_gate(
    goal: dict[str, Any],
    existing_gate: dict[str, Any] | None,
    args: argparse.Namespace,
    now: str,
    *,
    evidence_ledger: dict[str, Any] | None = None,
    iteration: int = 0,
    review_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    gate = dict(existing_gate) if isinstance(existing_gate, dict) and not args.reset else {}
    gate.setdefault("schema_version", RALPH_SCHEMA_VERSION)
    gate.setdefault("skill", SKILL_NAME)
    gate.setdefault("goal_id", goal.get("goal_id"))
    gate.setdefault("required", True)
    gate.setdefault("status", "not_requested")
    gate.setdefault("reviewer", args.reviewer or gate.get("reviewer") or "reviewer")
    gate.setdefault("attempts", [])
    gate["wait_policy"] = {
        "pending_is_wait_state": True,
        "preferred_tool": "wait_agent",
        "wait_timeout_ms": int(args.review_wait_timeout_ms),
        "retry_until_terminal": True,
        "pending_no_response_is_terminal": False,
        "pending_no_response_allows_fallback": False,
        "fallback_requires_explicit_tool_or_runtime_failure": True,
    }
    gate["updated_at_utc"] = now

    if args.request_review:
        attempt = {
            "request_id": secrets.token_hex(8),
            "requested_at_utc": now,
            "reviewer": args.reviewer or gate.get("reviewer") or "reviewer",
            "scope": "completion",
            "objective": goal.get("goal"),
            "acceptance_matrix": (goal.get("definition_of_done") or {}).get("acceptance_matrix"),
            "validation_matrix": (goal.get("definition_of_done") or {}).get("validation_matrix"),
            "closeout_matrix": (goal.get("definition_of_done") or {}).get("closeout_matrix"),
            "note": args.review_note,
            "wait_policy": gate["wait_policy"],
        }
        gate["status"] = "pending"
        gate["reviewer"] = attempt["reviewer"]
        gate["requested_at_utc"] = now
        gate["current_attempt"] = attempt
        if review_snapshot is not None:
            gate["review_snapshot"] = review_snapshot
        gate.setdefault("attempts", []).append(attempt)

    if getattr(args, "review_fallback", None):
        attempts = gate.get("attempts") if isinstance(gate.get("attempts"), list) else []
        if gate.get("status") not in {"pending", "not_requested"}:
            raise SystemExit("--review-fallback requires a pending or not-requested review gate.")
        if not attempts:
            attempt = {
                "requested_at_utc": now,
                "reviewer": args.reviewer or gate.get("reviewer") or "reviewer",
                "scope": "completion",
                "objective": goal.get("goal"),
                "note": args.review_note,
            }
            gate.setdefault("attempts", []).append(attempt)
            gate["current_attempt"] = attempt
            gate["requested_at_utc"] = now
        fallback = {
            "recorded_at_utc": now,
            "mode": "self_review_fallback",
            "fallback_reason": args.review_fallback,
            "required_steps": [
                "record the explicit reviewer subagent or external review failure; pending/no-response review is not enough",
                "perform a main-thread diff review for correctness, regressions, security, and missing tests",
                "rerun or document the relevant verification ladder",
                "include the fallback reason in --review-approved only after concrete review evidence exists",
            ],
        }
        gate["status"] = "pending"
        gate["review_execution"] = fallback
        gate.setdefault("fallbacks", []).append(fallback)

    if args.review_approved is not None:
        approval_summary = str(args.review_approved).strip()
        if not approval_summary:
            raise SystemExit(
                "--review-approved requires a non-empty approval summary describing the concrete review outcome."
            )
        if approval_contract.is_placeholder_approval(approval_summary):
            raise SystemExit(
                "--review-approved rejects placeholder summaries (shared approval vocabulary with fleet verdicts); "
                "describe the concrete review outcome."
            )
        attempts = gate.get("attempts") if isinstance(gate.get("attempts"), list) else []
        if gate.get("status") != "pending" or not attempts:
            raise SystemExit("--review-approved requires a pending review opened by --request-review.")
        if not isinstance(evidence_ledger, dict):
            # R14: an approval that cannot be audited must not exist — direct
            # calls without a real ledger fail closed instead of silently
            # skipping the audit entry.
            raise SystemExit("review approval requires the evidence ledger (audit entry is mandatory).")
        if review_snapshot is not None:
            drift = review_snapshot_drift(gate.get("review_snapshot"), review_snapshot)
            if drift:
                # Reviewer finding: raising here discarded the stale demotion
                # (the final state commit never ran). Record the demotion on
                # the returned gate and let the caller persist it, then fail.
                gate["status"] = "stale"
                gate["stale_reason"] = f"review subject changed after request: {', '.join(drift)}"
                gate["_deferred_error"] = (
                    "review subject drifted since --request-review "
                    f"({', '.join(drift)}); the pending approval is stale — request a new review."
                )
                return gate
        referenced = [str(v) for v in (getattr(args, "review_evidence", None) or [])]
        referenced += re.findall(r"\bE\d{4,}\b", approval_summary)
        referenced = sorted(set(referenced))
        valid_refs, missing_refs = explicit_evidence_ids(evidence_ledger, referenced)
        if missing_refs:
            raise SystemExit(
                f"--review-approved references unknown or ineligible evidence ids: {missing_refs}"
            )
        if not valid_refs:
            raise SystemExit(
                "--review-approved must reference at least one eligible evidence id "
                "(--review-evidence E#### or an E#### citation in the summary) so the approval is bound to what was reviewed."
            )
        # R14 ordering: append the audit entry FIRST; only a successfully
        # audited approval may flip the gate.
        approval_evidence_id = add_evidence_entry(
            evidence_ledger,
            now=now,
            goal_id=str(goal.get("goal_id") or ""),
            iteration=iteration,
            kind="review_approval",
            summary=(
                f"review approved by {args.reviewer or gate.get('reviewer') or 'reviewer'}: "
                f"{approval_summary} (reviewed evidence: {', '.join(valid_refs)})"
            ),
        )
        gate["status"] = "approved"
        gate["approved_at_utc"] = now
        gate["reviewer"] = args.reviewer or gate.get("reviewer") or "reviewer"
        gate["approval_summary"] = approval_summary
        gate["reviewed_evidence_ids"] = valid_refs
        # kind="review_approval" is deliberately NOT in EVIDENCE_ELIGIBLE_KINDS:
        # the approval is an audit-trail record, never completion evidence
        # attachable to A/V/C rows.
        gate["approval_evidence_id"] = approval_evidence_id
        if getattr(args, "review_fallback", None):
            gate["approval_fallback_reason"] = args.review_fallback
        gate["current_attempt"] = None

    if args.review_rejected:
        attempts = gate.get("attempts") if isinstance(gate.get("attempts"), list) else []
        if gate.get("status") != "pending" or not attempts:
            raise SystemExit("--review-rejected requires a pending review opened by --request-review.")
        feedback = {
            "rejected_at_utc": now,
            "reviewer": args.reviewer or gate.get("reviewer") or "reviewer",
            "feedback": args.review_rejected,
        }
        gate["status"] = "rejected"
        gate["rejected_at_utc"] = now
        gate["rejection_feedback"] = args.review_rejected
        gate.setdefault("rejections", []).append(feedback)
        gate["current_attempt"] = None

    return gate


def assess_completion_readiness(
    goal: dict[str, Any],
    ledger: dict[str, Any],
    review_gate: dict[str, Any] | None,
    source_coverage: dict[str, Any] | None = None,
    prd_projection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    definition = goal.get("definition_of_done") if isinstance(goal.get("definition_of_done"), dict) else {}
    acceptance_matrix = definition.get("acceptance_matrix") if isinstance(definition, dict) else []
    validation_matrix = definition.get("validation_matrix") if isinstance(definition, dict) else []
    closeout_matrix = definition.get("closeout_matrix") if isinstance(definition, dict) else []
    entries = ledger.get("entries") if isinstance(ledger.get("entries"), list) else []
    review_status = review_gate_status(review_gate)
    review_required = not isinstance(review_gate, dict) or review_gate.get("required", True) is not False

    missing_acceptance = [
        row.get("id")
        for row in acceptance_matrix
        if isinstance(row, dict) and row.get("status") not in ACCEPTANCE_DONE_STATUSES
    ]
    missing_validation = [
        row.get("id")
        for row in validation_matrix
        if isinstance(row, dict) and row.get("status") not in VALIDATION_DONE_STATUSES
    ]
    missing_closeout = [
        row.get("id")
        for row in closeout_matrix
        if isinstance(row, dict) and row.get("status") not in CLOSEOUT_DONE_STATUSES
    ]
    eligible_entries = [
        entry
        for entry in entries
        if isinstance(entry, dict) and entry.get("kind") in EVIDENCE_ELIGIBLE_KINDS
    ]
    goal_id_value = str(goal.get("goal_id") or "")
    missing_acceptance_evidence = completed_rows_missing_evidence(
        acceptance_matrix, ACCEPTANCE_DONE_STATUSES, ledger, goal_id_value
    )
    missing_validation_evidence = completed_rows_missing_evidence(
        validation_matrix, VALIDATION_DONE_STATUSES, ledger, goal_id_value
    )
    missing_closeout_evidence = completed_rows_missing_evidence(
        closeout_matrix, CLOSEOUT_DONE_STATUSES, ledger, goal_id_value
    )
    missing_evidence = (
        not eligible_entries
        or bool(missing_acceptance_evidence)
        or bool(missing_validation_evidence)
        or bool(missing_closeout_evidence)
    )
    missing_review = bool(review_required and review_status not in REVIEW_APPROVED_STATUSES)
    source_coverage = source_coverage if isinstance(source_coverage, dict) else {}
    source_coverage_blocks = bool(source_coverage.get("blocks_completion"))
    prd_projection = prd_projection if isinstance(prd_projection, dict) else {}
    prd_blocks = bool(prd_projection.get("blocks_completion"))
    return {
        "ready": (
            not missing_acceptance
            and not missing_validation
            and not missing_closeout
            and not missing_evidence
            and not missing_review
            and not source_coverage_blocks
            and not prd_blocks
        ),
        "missing_acceptance_ids": missing_acceptance,
        "missing_validation_ids": missing_validation,
        "missing_closeout_ids": missing_closeout,
        "missing_evidence": missing_evidence,
        "missing_acceptance_evidence_ids": missing_acceptance_evidence,
        "missing_validation_evidence_ids": missing_validation_evidence,
        "missing_closeout_evidence_ids": missing_closeout_evidence,
        "missing_review": missing_review,
        "review_status": review_status,
        "review_required": review_required,
        "evidence_count": len(eligible_entries),
        "source_coverage_present": bool(source_coverage.get("present")),
        "source_coverage_required": bool(source_coverage.get("required")),
        "source_coverage_ready": bool(source_coverage.get("ready", True)),
        "source_coverage_total_rows": source_coverage.get("total_rows", 0),
        "source_coverage_mode": source_coverage.get("coverage_mode"),
        "source_unit_total": source_coverage.get("source_unit_total"),
        "source_unit_processed": source_coverage.get("source_unit_processed"),
        "source_unit_blocked_ids": source_coverage.get("source_unit_blocked_ids", []),
        "source_coverage_missing_ids": source_coverage.get("missing_ids", []),
        "source_coverage_missing_evidence_ids": source_coverage.get("missing_evidence_ids", []),
        "source_coverage_missing_source_evidence_ids": source_coverage.get("missing_source_evidence_ids", []),
        "source_coverage_missing_validation_ids": source_coverage.get("missing_validation_ids", []),
        "source_coverage_missing_semantic_validation_ids": source_coverage.get("missing_semantic_validation_ids", []),
        "source_coverage_missing_negative_test_ids": source_coverage.get("missing_negative_test_ids", []),
        "source_coverage_missing_provenance_evidence_ids": source_coverage.get("missing_provenance_evidence_ids", []),
        "source_coverage_coarse_requirement_unit_ids": source_coverage.get("coarse_requirement_unit_ids", []),
        "source_coverage_invalid_row_ids": source_coverage.get("invalid_row_ids", []),
        "source_coverage_duplicate_row_ids": source_coverage.get("duplicate_row_ids", []),
        "source_coverage_unknown_status_ids": source_coverage.get("unknown_status_ids", []),
        "source_coverage_missing_span_ids": source_coverage.get("missing_span_ids", []),
        "source_unit_text_missing_ids": source_coverage.get("missing_unit_text_ids", []),
        "source_coverage_missing_manifest_unit_row_ids": source_coverage.get("missing_manifest_unit_row_ids", []),
        "source_coverage_unknown_row_unit_ids": source_coverage.get("unknown_row_unit_ids", []),
        "source_coverage_hash_mismatch_ids": source_coverage.get("hash_mismatch_ids", []),
        "source_coverage_missing_reason": source_coverage.get("missing_reason"),
        "source_coverage_path": source_coverage.get("path"),
        "prd_present": bool(prd_projection.get("present")),
        "prd_required": bool(prd_projection.get("required")),
        "prd_audit_ready": bool(prd_projection.get("audit_ready")),
        "prd_ready": bool(prd_projection.get("ready")),
        "prd_needs_review": bool(prd_projection.get("needs_review")),
        "prd_stale": bool(prd_projection.get("stale")),
        "prd_blocks_completion": prd_blocks,
        "prd_missing_reason": prd_projection.get("missing_reason"),
        "source_atoms_present": bool(prd_projection.get("source_atoms_present")),
        "prd_row_coverage_ready": bool(prd_projection.get("row_coverage_ready")),
        "prd_atom_coverage_ready": bool(prd_projection.get("atom_coverage_ready")),
        "prd_criteria_coverage_ready": bool(prd_projection.get("criteria_coverage_ready")),
        "prd_verification_coverage_ready": bool(prd_projection.get("verification_coverage_ready")),
        "prd_unmapped_source_row_ids": prd_projection.get("unmapped_source_row_ids", []),
        "prd_unmapped_required_atom_ids": prd_projection.get("unmapped_required_atom_ids", []),
        "prd_negative_atoms_without_negative_test": prd_projection.get("negative_atoms_without_negative_test", []),
        "prd_high_risk_atoms_without_verification": prd_projection.get("high_risk_atoms_without_verification", []),
        "prd_generic_criteria_story_ids": prd_projection.get("generic_criteria_story_ids", []),
        "prd_raw_source_leak_story_ids": prd_projection.get("raw_source_leak_story_ids", []),
        "prd_mapping_audit_path": prd_projection.get("path"),
    }


def implementation_gate_status(status_payload: Any, gates_payload: Any) -> str:
    if isinstance(gates_payload, dict):
        gate = gates_payload.get("implementation_gate")
        if isinstance(gate, dict) and gate.get("status"):
            return str(gate["status"])
    if isinstance(status_payload, dict) and status_payload.get("implementation_gate"):
        return str(status_payload["implementation_gate"])
    return "unknown"


def derive_loop_phase(status_payload: Any, gates_payload: Any) -> str:
    gate = implementation_gate_status(status_payload, gates_payload).lower()
    phase_value = status_payload.get("phase") if isinstance(status_payload, dict) else ""
    stage_value = status_payload.get("current_stage") if isinstance(status_payload, dict) else ""
    phase = str(phase_value or "").lower()
    stage = str(stage_value or "").lower()

    if gate in {"blocked", "pending", "needs-review", "unknown"}:
        if "bootstrap" in stage or phase in {"planning", ""}:
            return "intake-and-recon"
        return "gate-work"
    if phase in {"verification", "review", "validating"}:
        return "verification"
    return "bounded-implementation"


def next_iteration_number(rah_root: Path, loop_state: dict[str, Any] | None, increment: bool) -> int:
    current = 0
    if isinstance(loop_state, dict):
        try:
            current = int(loop_state.get("current_iteration") or 0)
        except (TypeError, ValueError):
            current = 0
    if not increment:
        return max(current, 0)
    return current + 1


def derive_state_machine(loop_phase: str, loop_status: str) -> dict[str, Any]:
    phase_to_state = {
        "intake-and-recon": "intake",
        "gate-work": "plan",
        "bounded-implementation": "act",
        "verification": "verify",
    }
    if loop_status == "done":
        current_state = "done"
    elif loop_status == "blocked":
        current_state = "blocked"
    elif loop_status in {"cancelled", "canceled"}:
        current_state = "cancelled"
    elif loop_status == "failed":
        current_state = "failed"
    else:
        current_state = phase_to_state.get(loop_phase, "plan")

    allowed = {
        "intake": ["plan", "blocked"],
        "plan": ["act", "verify", "blocked"],
        "act": ["verify", "plan", "blocked"],
        "verify": ["review", "act", "blocked"],
        "review": ["decide", "act", "blocked"],
        "decide": ["done", "plan", "blocked"],
        "done": [],
        "blocked": [],
        "cancelled": [],
        "failed": [],
    }
    return {
        "states": ["intake", "plan", "act", "verify", "review", "decide", "done", "blocked", "cancelled", "failed"],
        "current_state": current_state,
        "allowed_next_states": allowed.get(current_state, []),
    }


def update_stagnation(loop_state: dict[str, Any] | None, loop_phase: str, created_evidence: list[str]) -> dict[str, Any]:
    previous = loop_state.get("stagnation") if isinstance(loop_state, dict) else {}
    previous_phase = previous.get("last_loop_phase") if isinstance(previous, dict) else None
    previous_count = previous.get("same_phase_without_evidence_count") if isinstance(previous, dict) else 0
    try:
        count = int(previous_count or 0)
    except (TypeError, ValueError):
        count = 0
    if created_evidence:
        count = 0
    elif previous_phase == loop_phase:
        count += 1
    else:
        count = 1
    return {
        "last_loop_phase": loop_phase,
        "same_phase_without_evidence_count": count,
        "pivot_required": count >= 3,
        "pivot_reason": "same loop phase repeated without new evidence" if count >= 3 else None,
    }


def build_goal_payload(
    root: Path,
    args: argparse.Namespace,
    existing_goal: dict[str, Any] | None,
    now: str,
) -> dict[str, Any]:
    if existing_goal and not args.reset and not args.goal:
        goal = dict(existing_goal)
        # Repositories can be relocated without changing the retained goal.
        # Normalize the persisted root on every canonical resume so the
        # read-only lifecycle probe does not reject otherwise valid state.
        goal["repo_root"] = str(root)
        if args.max_iterations is not None:
            goal["max_iterations"] = args.max_iterations
        if args.acceptance:
            goal.setdefault("definition_of_done", {})["acceptance_criteria"] = args.acceptance
        if args.validation:
            goal.setdefault("definition_of_done", {})["validation_commands"] = args.validation
        if args.completion_mode:
            goal["completion_mode"] = args.completion_mode
        if args.require_source_coverage:
            goal["source_coverage_required"] = True
        if args.no_require_source_coverage:
            goal["source_coverage_required"] = False
        if args.require_prd:
            goal["prd_required"] = True
        if args.no_require_prd:
            goal["prd_required"] = False
        ensure_goal_matrices(goal)
        goal["updated_at_utc"] = now
        return goal

    if not args.goal:
        raise SystemExit("--goal is required for the first RALPH run, or pass an existing .rah/ralph/goal.json")

    goal_text = args.goal.strip()
    goal_slug = slugify(goal_text)
    acceptance = args.acceptance or BASE_ACCEPTANCE
    validation = args.validation or BASE_VALIDATION
    # Re-invoking with the SAME goal text is a resume, not a new contract:
    # explicitly persisted requirement gates survive unless explicitly cleared.
    existing = existing_goal if isinstance(existing_goal, dict) else {}
    same_goal_resume = bool(existing) and not args.reset and str(existing.get("goal") or "").strip() == goal_text
    goal = {
        "schema_version": RALPH_SCHEMA_VERSION,
        "skill": SKILL_NAME,
        "goal_id": f"ralph-{goal_slug}",
        "goal": goal_text,
        "status": "active",
        "created_at_utc": now,
        "updated_at_utc": now,
        "repo_root": str(root),
        "max_iterations": args.max_iterations or DEFAULT_MAX_ITERATIONS,
        "completion_mode": args.completion_mode or DEFAULT_COMPLETION_MODE,
        "source_coverage_required": bool(
            args.require_source_coverage
            or (infer_source_coverage_required(goal_text) and not args.no_require_source_coverage)
            or (same_goal_resume and existing.get("source_coverage_required") and not args.no_require_source_coverage)
        ),
        "prd_required": bool(
            args.require_prd
            or (same_goal_resume and existing.get("prd_required") and not args.no_require_prd)
        ),
        "definition_of_done": {
            "acceptance_criteria": acceptance,
            "validation_commands": validation,
            "evidence_required": [
                "iteration note under .rah/ralph/iterations/",
                "validation output or documented validation gap",
                "diff review notes before completion",
            ],
        },
        "constraints": [
            "Follow the nearest active AGENTS.md before any write.",
            "Do not bypass the implementation gate; work on gate prerequisites when it is blocked.",
            "Keep every implementation pass bounded and verification-backed.",
            "In exhaustive mode, keep looping until completion readiness is true or a real external blocker is durable.",
            "In bounded mode, stop when the goal is done, blocked by missing information, or max_iterations is reached.",
        ],
    }
    ensure_goal_matrices(goal)
    return goal


def build_loop_state(
    root: Path,
    goal_payload: dict[str, Any],
    status_payload: Any,
    gates_payload: Any,
    evidence_ledger: dict[str, Any],
    review_gate: dict[str, Any],
    progress_update: dict[str, Any],
    loop_state: dict[str, Any] | None,
    args: argparse.Namespace,
    now: str,
    iteration: int,
) -> dict[str, Any]:
    max_iterations = int(goal_payload.get("max_iterations") or DEFAULT_MAX_ITERATIONS)
    completion_mode = str(goal_payload.get("completion_mode") or DEFAULT_COMPLETION_MODE).lower()
    if completion_mode not in COMPLETION_MODES:
        completion_mode = DEFAULT_COMPLETION_MODE
    gate = implementation_gate_status(status_payload, gates_payload)
    loop_phase = derive_loop_phase(status_payload, gates_payload)
    source_coverage_required = bool(goal_payload.get("source_coverage_required"))
    source_coverage = assess_source_coverage(root, required=source_coverage_required)
    prd_projection = assess_prd_projection(
        root, required=bool(goal_payload.get("prd_required")), source_coverage=source_coverage
    )
    completion_readiness = assess_completion_readiness(
        goal_payload, evidence_ledger, review_gate, source_coverage, prd_projection
    )
    stagnation = update_stagnation(loop_state, loop_phase, progress_update.get("created_evidence", []))
    prior_blocker = loop_state.get("blocked_reason") if isinstance(loop_state, dict) else None
    prior_status = str(
        (loop_state.get("status") if isinstance(loop_state, dict) else None)
        or goal_payload.get("status")
        or ""
    ).lower()

    if args.mark_done and completion_readiness.get("ready") and args.closeout_check:
        loop_status = "done"
        blocked_reason = None
        done = True
    elif args.mark_done:
        loop_status = "active"
        blocked_reason = None
        done = False
    elif args.block:
        loop_status = "blocked"
        blocked_reason = args.block
        done = False
    elif prior_status == "done":
        loop_status = "done"
        blocked_reason = None
        done = True
    elif prior_status == "blocked":
        loop_status = "blocked"
        blocked_reason = prior_blocker or "previous RALPH loop is blocked"
        done = False
    elif prior_status in {"cancelled", "canceled"}:
        loop_status = "cancelled"
        blocked_reason = prior_blocker or "previous RALPH loop was operator-cancelled"
        done = False
    elif prior_status == "failed":
        loop_status = "failed"
        blocked_reason = prior_blocker or "previous RALPH loop failed"
        done = False
    elif iteration > max_iterations and completion_mode == "bounded":
        loop_status = "blocked"
        blocked_reason = f"max_iterations reached ({max_iterations})"
        iteration = max_iterations
        done = False
    else:
        loop_status = "active"
        blocked_reason = prior_blocker if prior_blocker and args.no_increment else None
        done = False
    checkpoint_required = bool(completion_mode == "exhaustive" and iteration > 0 and iteration % max_iterations == 0)

    if loop_status == "done":
        next_actions = [
            "No remaining RALPH gate work; closeout, review, source coverage, and driver terminal state are complete.",
            "If /goal is active, mark it complete after final audit acceptance.",
        ]
    elif loop_status == "blocked":
        next_actions = [
            "Record or inspect the blocker in `.rah/ralph/blockers.md`.",
            "Do not continue the loop until the missing input, access, policy gate, or validation failure is resolved.",
            "If /goal is active, mark it blocked only when this durable blocker is the current stopping condition.",
        ]
    elif loop_status in {"cancelled", "failed"}:
        next_actions = [
            "Do not resume this RALPH loop implicitly.",
            "Use `rah.py ralph <repo-root> --reset --goal \"<objective>\"` to start a new loop, or `rah.py ops <repo-root> clear` to archive stale state.",
            "Inspect `.rah/ralph/cancelled.md` or driver state before restarting.",
        ]
    elif loop_phase in {"intake-and-recon", "gate-work"}:
        next_actions = [
            "Run or inspect doctor/status/resume before editing.",
            "Hydrate Memento context and task-scoped recall when available.",
            "Finish current-system recon and implementation gate prerequisites.",
            "Only implement a bounded phase after the gate is explicitly pass/ready.",
        ]
    elif loop_phase == "verification":
        next_actions = [
            "Run the repo verification ladder in order.",
            "Review the diff for regression risk and missing tests.",
            "Mark the RALPH goal done only when acceptance criteria are satisfied.",
        ]
    else:
        next_actions = [
            "Define the smallest implementation phase that advances the goal.",
            "Make bounded code or doc changes.",
            "Run targeted validation, then broaden verification if shared behavior changed.",
            "Update RALPH state and repeat until done or blocked.",
        ]
    if args.mark_done and not args.closeout_check:
        next_actions = [
            "Re-run RALPH with --mark-done --closeout-check in the same invocation.",
            "Completion readiness alone is not enough; the structured closeout audit must be fresh before persisting done.",
            "Do not report completion until closeout_check.ready is true and the done state is written atomically.",
        ]
    elif args.mark_done and not completion_readiness.get("ready"):
        next_actions = [
            "Complete the missing source-material coverage, acceptance, validation, closeout, and review rows before marking the goal done.",
            "Record concrete evidence with --record-evidence or --record-gap.",
            "Re-run RALPH with --acceptance-met, --validation-passed, --closeout-met, and reviewer gate row ids when observed.",
        ]
    elif completion_readiness.get("source_coverage_missing_ids") and loop_status == "active":
        next_actions = [
            "Continue the source-material coverage rows before marking the goal done.",
            "Open `.rah/ralph/source_requirement_coverage.json` and select the next uncovered requirement row.",
            "Update the coverage row with concrete evidence and validation before broad closeout.",
            *next_actions,
        ]
    elif (
        completion_readiness.get("source_coverage_missing_evidence_ids")
        or completion_readiness.get("source_coverage_missing_source_evidence_ids")
        or completion_readiness.get("source_coverage_missing_validation_ids")
        or completion_readiness.get("source_coverage_invalid_row_ids")
        or completion_readiness.get("source_coverage_missing_reason")
    ) and loop_status == "active":
        next_actions = [
            "Repair source-material coverage evidence/validation before closeout.",
            "Rows marked done require concrete evidence, source_evidence anchored to the original source unit/path/hash, and validation.",
            "Rows marked intentionally_excluded require a policy or user-decision reason.",
            *next_actions,
        ]
    elif completion_readiness.get("prd_blocks_completion") and loop_status == "active":
        next_actions = [
            "PRD projection is required but not ready. Run `python <active-skill-root>/automation/rah.py prd <repo-root> validate` and resolve unmapped atoms / missing verification before --mark-done --closeout-check.",
            "PRD is a planning view: fix story/criteria mapping or record a human-reviewed waiver in prd_waivers.json; completion authority stays with source coverage.",
            *next_actions,
        ]
    elif checkpoint_required and loop_status == "active":
        next_actions = [
            "Run a checkpoint review: inspect plan graph, evidence ledger, and remaining acceptance or validation rows.",
            "Refine the next active plan node instead of stopping at the iteration checkpoint.",
            *next_actions,
        ]
    elif completion_readiness.get("missing_closeout_ids") and loop_status == "active":
        next_actions = [
            "Run the closeout completeness gate before marking the goal done.",
            "Use --closeout-met for each satisfied C-row or --closeout-documented for an accepted documented gap.",
            *next_actions,
        ]
    elif completion_readiness.get("missing_review") and loop_status == "active":
        next_actions = [
            "Run or request the reviewer verification gate before marking the goal done.",
            f"If a reviewer agent/thread is pending, call wait_agent with timeout_ms={int(args.review_wait_timeout_ms)} and keep waiting/retrying until reviewer approval or rejection is received.",
            "Do not treat reviewer no-response, pending status, or wait timeout as completion, blocker, or fallback evidence.",
            "Use --request-review when ready for review, then --review-approved only after concrete reviewer approval.",
            *next_actions,
        ]
    elif stagnation.get("pivot_required") and loop_status == "active":
        next_actions = [
            "Pivot before another loop: split the goal, inspect the blocker, or tighten the next bounded phase.",
            "Record new evidence or a concrete blocker before incrementing again.",
            *next_actions,
        ]

    root_token = command_token(root)
    goal_token = command_token(goal_payload.get("goal") or "")
    state_machine = derive_state_machine(loop_phase, loop_status)
    return {
        "schema_version": RALPH_SCHEMA_VERSION,
        "skill": SKILL_NAME,
        "generated_at_utc": now,
        "updated_at_utc": now,
        "repo_root": str(root),
        "goal_id": goal_payload.get("goal_id"),
        "goal": goal_payload.get("goal"),
        "status": loop_status,
        "done": done,
        "current_iteration": iteration,
        "max_iterations": max_iterations,
        "completion_mode": completion_mode,
        "checkpoint_required": checkpoint_required,
        "loop_phase": loop_phase,
        "implementation_gate": gate,
        "current_stage": status_payload.get("current_stage") if isinstance(status_payload, dict) else None,
        "harness_phase": status_payload.get("phase") if isinstance(status_payload, dict) else None,
        "blocked_reason": blocked_reason,
        "completion_readiness": completion_readiness,
        "source_coverage": source_coverage,
        "review_gate": review_gate,
        "review_wait_policy": review_gate.get("wait_policy") if isinstance(review_gate, dict) else None,
        "mark_done_rejected": bool(args.mark_done and (not completion_readiness.get("ready") or not args.closeout_check)),
        "progress_update": progress_update,
        "stagnation": stagnation,
        "state_machine": state_machine,
        "autonomous_completion_contract": {
            "mode": completion_mode,
            "must_continue_until": [
                "completion_readiness.ready is true",
                "closeout completeness gate is satisfied",
            ],
            "may_yield_only_when": [
                "status is done",
                "status is blocked by missing user input, external access, repo policy, or irreducible validation failure",
            ],
            "iteration_limit_policy": (
                "max_iterations is a hard stop" if completion_mode == "bounded" else "max_iterations is a checkpoint, not a stop"
            ),
        },
        "external_driver_contract": {
            "command": f"python <active-skill-root>/automation/rah.py drive {root_token} --goal {goal_token} --completion-mode {completion_mode}",
            "purpose": "Wrapper loop that repeatedly invokes the host agent (codex exec under Codex, claude -p under Claude Code) until RALPH status is terminal.",
            "use_when": [
                "the user wants hard continuation outside a single model turn",
                "a long development, summarization, cleanup, or writing objective must continue across agent runs",
            ],
            "terminal_states": ["done", "blocked", "failed", "cancelled"],
            "state_path": ".rah/ralph/driver/driver_state.json",
        },
        "read_first": READ_FIRST,
        "next_actions": next_actions,
        "stop_conditions": [
            "definition_of_done_satisfied",
            "blocked_by_missing_user_input_or_external_access",
            "max_iterations_reached" if completion_mode == "bounded" else "checkpoint_review_required",
            "repo_policy_or_validation_failure_requires_attention",
        ],
        "state_paths": {
            "goal": ".rah/ralph/goal.json",
            "loop_state": ".rah/ralph/loop_state.json",
            "evidence_ledger": ".rah/ralph/evidence_ledger.json",
            "plan_graph": ".rah/ralph/plan_graph.json",
            "goal_bridge": ".rah/ralph/goal_bridge.json",
            "review_gate": ".rah/ralph/review_gate.json",
            "iterations": ".rah/ralph/iterations/",
            "completion_report": ".rah/ralph/completion_report.md",
            "blockers": ".rah/ralph/blockers.md",
            "external_jobs": ".rah/jobs/",
        },
        "command_recipes": {
            "doctor": f"python <active-skill-root>/automation/rah.py doctor {root_token}",
            "status": f"python <active-skill-root>/automation/rah.py status {root_token}",
            "resume": f"python <active-skill-root>/automation/rah.py resume {root_token}",
            "ralph": f"python <active-skill-root>/automation/rah.py ralph {root_token} --goal {goal_token}",
            "mark_closeout": f"python <active-skill-root>/automation/rah.py ralph {root_token} --record-evidence \"<closeout proof>\" --closeout-met C1 --closeout-met C2 --closeout-met C3 --closeout-met C4 --closeout-met C5",
            "closeout_check": f"python <active-skill-root>/automation/rah.py ralph {root_token} --closeout-check",
            "request_review": f"python <active-skill-root>/automation/rah.py ralph {root_token} --request-review",
            "review_fallback": f"python <active-skill-root>/automation/rah.py ralph {root_token} --review-fallback \"<explicit subagent/tool failure reason; not pending/no-response>\"",
            "approve_review": f"python <active-skill-root>/automation/rah.py ralph {root_token} --review-approved \"<review summary>\"",
            "wait_for_review": f"wait_agent(targets=[\"<reviewer-agent-id>\"], timeout_ms={int(args.review_wait_timeout_ms)})",
            "launch_job": f"python <active-skill-root>/automation/rah.py job {root_token} launch --name \"<job name>\" --kind python-compute -- python <script.py>",
            "job_status": f"python <active-skill-root>/automation/rah.py job {root_token} status <job-id>",
            "job_evidence": f"python <active-skill-root>/automation/rah.py job {root_token} evidence <job-id>",
            "source_ingest": f"python <active-skill-root>/automation/rah.py source {root_token} ingest --mode analysis --source <path>",
            "source_status": f"python <active-skill-root>/automation/rah.py source {root_token} status",
            "source_next": f"python <active-skill-root>/automation/rah.py source {root_token} next --include-text",
            "source_update": f"python <active-skill-root>/automation/rah.py source {root_token} update <row-id> --status analyzed --evidence \"<analysis evidence>\" --validation \"<coverage validation>\"",
            "ops": f"python <active-skill-root>/automation/rah.py ops {root_token} driver-status",
        },
    }


def refresh_status_for_ralph(
    root: Path,
    rah_root: Path,
    goal_payload: dict[str, Any],
    loop_payload: dict[str, Any],
    now: str,
    *,
    replacement_notice: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    status_path = rah_root / "state" / "status.json"
    gates_path = rah_root / "state" / "gates.json"
    status_payload = load_json(status_path)
    gates_payload = load_json(gates_path)
    loop_status = str(loop_payload.get("status") or "active").lower()
    goal_id = str(goal_payload.get("goal_id") or "ralph-goal")
    next_actions = loop_payload.get("next_actions") if isinstance(loop_payload.get("next_actions"), list) else []
    restart_point = f"RALPH {loop_status}: {goal_id}"
    phase = {
        "done": "completed",
        "blocked": "blocked",
        "cancelled": "blocked",
        "canceled": "blocked",
        "failed": "blocked",
    }.get(loop_status, "execution")
    stage_patch = {
        "current_stage": f"ralph-{loop_status}",
        "phase": phase,
        "earliest_restart_point": restart_point,
        "next_recommended_action": next_actions[0]
        if next_actions
        else "Run rah.py status and rah.py resume, then continue from the active RALPH loop state.",
    }
    if not isinstance(status_payload, dict):
        return stage_patch
    status_payload.update(
        {
            "root": str(root),
            "updated_at_utc": now,
            "current_stage": stage_patch["current_stage"],
            "phase": stage_patch["phase"],
            "last_completed_step": "ralph_state_refresh",
            "earliest_restart_point": stage_patch["earliest_restart_point"],
            "next_recommended_action": stage_patch["next_recommended_action"],
            "ralph_goal_id": goal_id,
            "ralph_goal": goal_payload.get("goal"),
            "ralph_status": loop_status,
            "ralph_iteration": loop_payload.get("current_iteration"),
            "ralph_completion_ready": (loop_payload.get("completion_readiness") or {}).get("ready")
            if isinstance(loop_payload.get("completion_readiness"), dict)
            else None,
        }
    )
    if replacement_notice:
        status_payload["ralph_replacement"] = replacement_notice
    write_json(status_path, status_payload)

    if isinstance(gates_payload, dict):
        gates_payload["earliest_restart_point"] = restart_point
        gates_payload["ralph_goal_gate"] = {
            "status": loop_status,
            "goal_id": goal_id,
            "completion_ready": status_payload.get("ralph_completion_ready"),
            "updated_at_utc": now,
        }
        write_json(gates_path, gates_payload)
    return stage_patch


def run_json_helper(script_name: str, args: list[str]) -> dict[str, Any]:
    command = [sys.executable, "-B", str(Path(__file__).resolve().parent / script_name), *args, "--json"]
    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    parsed: Any = None
    if stdout.strip():
        try:
            parsed = json.loads(stdout)
        except json.JSONDecodeError:
            parsed = None
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout_json": parsed,
        "stdout": stdout[-4000:],
        "stderr": stderr[-4000:],
    }


def run_git_command(root: Path, args: list[str]) -> dict[str, Any]:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return {
        "command": ["git", *args],
        "returncode": completed.returncode,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
    }


def parse_git_status_porcelain_z(stdout: str) -> list[dict[str, str]]:
    """Parse `git status --porcelain=v1 -z` without C-quoted path loss."""
    tokens = stdout.split("\0")
    entries: list[dict[str, str]] = []
    index = 0
    while index < len(tokens):
        record = tokens[index]
        index += 1
        if not record:
            continue
        status = record[:2]
        path = record[3:] if len(record) >= 3 and record[2] == " " else record[2:]
        entry = {"status": status, "path": path}
        if ("R" in status or "C" in status) and index < len(tokens):
            entry["original_path"] = tokens[index]
            index += 1
        entries.append(entry)
    return entries


def run_git_status_short(root: Path) -> dict[str, Any]:
    args = ["-c", "core.quotepath=false", "status", "--porcelain=v1", "-z", "--untracked-files=all"]
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    entries = parse_git_status_porcelain_z(completed.stdout)
    display_lines = []
    for entry in entries:
        line = f"{entry['status']} {entry['path']}"
        if entry.get("original_path"):
            line += f" <- {entry['original_path']}"
        display_lines.append(line)
    return {
        "command": ["git", *args],
        "returncode": completed.returncode,
        "stdout": "\n".join(display_lines)[-4000:],
        "stderr": completed.stderr[-4000:],
        "entries": entries,
    }


def normalized_repo_path(path: str) -> str:
    normalized = str(path).replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def generated_or_private_untracked_entries(entries: list[dict[str, str]]) -> list[str]:
    generated_prefixes = (
        "artifacts/",
        "out/",
        "runs/",
        "results/",
        "dist/",
        "build/",
        "coverage/",
        ".rah/archive/",
        ".rah/ralph/source_units/",
        ".rah/ralph/driver/cycles/",
    )
    generated_job_suffixes = (
        "/stdout.log",
        "/stderr.log",
        "/wrapper_stdout.log",
        "/wrapper_stderr.log",
        "/events.jsonl",
    )
    matches: list[str] = []
    for entry in entries:
        if entry.get("status") != "??":
            continue
        path = normalized_repo_path(entry.get("path", ""))
        if path.startswith(generated_prefixes) or (
            path.startswith(".rah/jobs/") and path.endswith(generated_job_suffixes)
        ):
            matches.append(f"?? {path}")
    return matches


def detect_git_worktree(root: Path) -> dict[str, Any]:
    result = run_git_command(root, ["rev-parse", "--is-inside-work-tree"])
    is_worktree = result.get("returncode") == 0 and result.get("stdout", "").strip().lower() == "true"
    return {
        "is_git_worktree": is_worktree,
        "result": result,
    }


def structured_incomplete_rows(goal_payload: dict[str, Any], loop_payload: dict[str, Any]) -> dict[str, Any]:
    readiness = loop_payload.get("completion_readiness") if isinstance(loop_payload.get("completion_readiness"), dict) else {}
    definition = goal_payload.get("definition_of_done") if isinstance(goal_payload.get("definition_of_done"), dict) else {}
    return {
        "acceptance": readiness.get("missing_acceptance_ids") or [],
        "validation": readiness.get("missing_validation_ids") or [],
        "closeout": readiness.get("missing_closeout_ids") or [],
        "source_coverage": (
            (readiness.get("source_coverage_missing_ids") or [])
            + (readiness.get("source_coverage_missing_evidence_ids") or [])
            + (readiness.get("source_coverage_missing_source_evidence_ids") or [])
            + (readiness.get("source_coverage_missing_validation_ids") or [])
            + (readiness.get("source_coverage_missing_semantic_validation_ids") or [])
            + (readiness.get("source_coverage_missing_negative_test_ids") or [])
            + (readiness.get("source_coverage_missing_provenance_evidence_ids") or [])
            + (readiness.get("source_coverage_coarse_requirement_unit_ids") or [])
            + (readiness.get("source_coverage_invalid_row_ids") or [])
            + (readiness.get("source_unit_blocked_ids") or [])
            + (readiness.get("source_unit_text_missing_ids") or [])
        ),
        "review": ["review_gate"] if readiness.get("missing_review") else [],
        "matrix_row_counts": {
            "acceptance": len(definition.get("acceptance_matrix") or []),
            "validation": len(definition.get("validation_matrix") or []),
            "closeout": len(definition.get("closeout_matrix") or []),
        },
    }


def closeout_check(root: Path, goal_payload: dict[str, Any], loop_payload: dict[str, Any], now: str) -> dict[str, Any]:
    ralph_root = root / ".rah" / "ralph"
    json_targets = [
        ".rah/state/status.json",
        ".rah/state/gates.json",
        ".rah/ralph/goal.json",
        ".rah/ralph/loop_state.json",
        ".rah/ralph/evidence_ledger.json",
        ".rah/ralph/plan_graph.json",
        ".rah/ralph/goal_bridge.json",
        ".rah/ralph/review_gate.json",
        ".rah/ralph/source_documents.json",
        ".rah/ralph/source_requirement_coverage.json",
    ]
    json_errors: list[str] = []
    parsed_json: list[str] = []
    for rel in json_targets:
        path = root / rel
        if not path.exists():
            continue
        try:
            json.loads(path.read_text(encoding="utf-8"))
            parsed_json.append(rel)
        except Exception as exc:
            json_errors.append(f"{rel}: {exc}")

    status_result = run_json_helper("harness_status.py", [str(root)])
    resume_result = run_json_helper("resume_harness.py", [str(root)])
    source_validate = None
    if (ralph_root / "source_requirement_coverage.json").exists():
        source_validate = run_json_helper("source_coverage_harness.py", [str(root), "validate"])
    git_worktree = detect_git_worktree(root)
    is_git_worktree = bool(git_worktree.get("is_git_worktree"))
    if is_git_worktree:
        git_diff_check = run_git_command(root, ["diff", "--check"])
        git_status = run_git_status_short(root)
    else:
        git_diff_check = {
            "command": ["git", "diff", "--check"],
            "returncode": 0,
            "stdout": "",
            "stderr": "",
            "skipped": True,
            "reason": "non_git_workspace",
        }
        git_status = {
            "command": ["git", "status", "--short", "--untracked-files=all"],
            "returncode": 0,
            "stdout": "",
            "stderr": "",
            "entries": [],
            "skipped": True,
            "reason": "non_git_workspace",
        }
    dirty_entries = git_status.get("entries") if isinstance(git_status.get("entries"), list) else []
    dirty_lines = [line for line in git_status.get("stdout", "").splitlines() if line.strip()]
    generated_or_private_untracked = generated_or_private_untracked_entries(dirty_entries)
    incomplete = structured_incomplete_rows(goal_payload, loop_payload)
    incomplete_count = sum(len(values) for key, values in incomplete.items() if isinstance(values, list))
    source_valid = True
    if isinstance(source_validate, dict):
        source_payload = source_validate.get("stdout_json")
        source_valid = bool(
            source_validate.get("returncode") == 0
            and isinstance(source_payload, dict)
            and source_payload.get("valid")
        )
    ready = bool(
        not json_errors
        and status_result.get("returncode") == 0
        and resume_result.get("returncode") == 0
        and source_valid
        and git_status.get("returncode") == 0
        and git_diff_check.get("returncode") == 0
        and not generated_or_private_untracked
        and incomplete_count == 0
    )
    payload = {
        "schema_version": RALPH_SCHEMA_VERSION,
        "generated_at_utc": now,
        "goal_id": goal_payload.get("goal_id"),
        "ready": ready,
        "workspace": {
            "kind": "git_worktree" if is_git_worktree else "non_git_workspace",
            "git_probe": git_worktree,
            "policy": "non-git vault/plain-folder closeout skips git diff/status and relies on status, resume, JSON, source, review, and artifact validation",
        },
        "json_parse": {"ready": not json_errors, "parsed": parsed_json, "errors": json_errors},
        "status": {"ready": status_result.get("returncode") == 0, "result": status_result},
        "resume": {"ready": resume_result.get("returncode") == 0, "result": resume_result},
        "source_validate": {
            "ready": source_valid,
            "result": source_validate,
            "skipped": source_validate is None,
        },
        "negative_scan": {
            "ready": incomplete_count == 0,
            "method": "structured status rows only; excludes evidence ledger prose, archive, logs, and source_units text",
            "incomplete": incomplete,
        },
        "generated_output_tracking": {
            "ready": not generated_or_private_untracked,
            "dirty_count": len(dirty_lines),
            "generated_or_private_untracked": generated_or_private_untracked,
            "policy": "classify generated/private outputs before commit; .rah/archive, .rah/ralph/source_units, and driver cycles should be ignored by default",
        },
        "git_diff_check": {"ready": git_diff_check.get("returncode") == 0, "result": git_diff_check},
        "next_actions": [] if ready else [
            "Resolve failed closeout check sections before --mark-done.",
            "Use structured matrix statuses rather than broad word scans such as uncovered.",
            "Record any accepted generated-output tracking decision as closeout evidence.",
        ],
    }
    report_path = ralph_root / "closeout_check.json"
    write_json(report_path, payload)
    write_text(
        ralph_root / "closeout_check.md",
        "\n".join(
            [
                "# RALPH Closeout Check",
                "",
                f"- generated_at_utc: `{now}`",
                f"- ready: `{ready}`",
                f"- workspace_kind: `{'git_worktree' if is_git_worktree else 'non_git_workspace'}`",
                f"- json_parse_ready: `{not json_errors}`",
                f"- source_validate_ready: `{source_valid}`",
                f"- git_diff_check_ready: `{git_diff_check.get('returncode') == 0}`",
                f"- structured_incomplete_count: `{incomplete_count}`",
                f"- generated_or_private_untracked_count: `{len(generated_or_private_untracked)}`",
                "",
                "See `.rah/ralph/closeout_check.json` for machine-readable details.",
                "",
            ]
        ),
    )
    return payload


def build_plan_graph(
    goal_payload: dict[str, Any],
    loop_payload: dict[str, Any],
    previous_graph: dict[str, Any] | None,
    now: str,
) -> dict[str, Any]:
    source_coverage = loop_payload.get("source_coverage") if isinstance(loop_payload, dict) else {}
    source_coverage = source_coverage if isinstance(source_coverage, dict) else {}
    missing_source_ids = []
    for key in (
        "missing_ids",
        "missing_evidence_ids",
        "missing_validation_ids",
        "invalid_row_ids",
            "source_unit_blocked_ids",
            "missing_unit_text_ids",
            "missing_manifest_unit_row_ids",
            "unknown_row_unit_ids",
            "hash_mismatch_ids",
        ):
        values = source_coverage.get(key)
        if isinstance(values, list):
            for value in values:
                value = str(value)
                if value and value not in missing_source_ids:
                    missing_source_ids.append(value)
    active_by_phase = {
        "intake-and-recon": "N1",
        "gate-work": "N2",
        "bounded-implementation": "N3",
        "verification": "N4",
    }
    active_node = active_by_phase.get(str(loop_payload.get("loop_phase")), "N2")
    if loop_payload.get("status") == "done":
        active_node = "N5"
    elif loop_payload.get("status") == "blocked":
        active_node = "blocked"

    previous_nodes = {}
    if isinstance(previous_graph, dict) and isinstance(previous_graph.get("nodes"), list):
        previous_nodes = {
            node.get("id"): node for node in previous_graph["nodes"] if isinstance(node, dict) and node.get("id")
        }

    node_specs = [
        ("N1", "Hydrate policy, harness state, and memory", []),
        ("N2", "Decompose the goal into the next bounded phase", ["N1"]),
        ("N3", "Perform the bounded implementation or organization pass", ["N2"]),
        ("N4", "Verify, review, and record evidence", ["N3"]),
        ("N5", "Run closeout, resume refresh, and completion report", ["N4"]),
    ]
    if missing_source_ids:
        node_specs.insert(2, ("SRC", "Process source coverage rows without omissions", ["N2"]))
        if active_node in {"N2", "N3"}:
            active_node = "SRC"
    nodes: list[dict[str, Any]] = []
    active_seen = False
    for node_id, title, depends_on in node_specs:
        previous = previous_nodes.get(node_id, {})
        if loop_payload.get("status") == "done":
            status = "verified"
        elif loop_payload.get("status") == "blocked":
            status = previous.get("status") or "pending"
        elif node_id == active_node:
            status = "active"
            active_seen = True
        elif not active_seen and node_id != active_node:
            status = previous.get("status") if previous.get("status") in {"verified", "skipped"} else "pending"
        else:
            status = "pending"
        nodes.append(
            {
                "id": node_id,
                "title": title,
                "status": status,
                "depends_on": depends_on,
                "coverage_row_ids": missing_source_ids if node_id == "SRC" else [],
                "evidence": previous.get("evidence") if isinstance(previous.get("evidence"), list) else [],
            }
        )

    return {
        "schema_version": RALPH_SCHEMA_VERSION,
        "goal_id": goal_payload.get("goal_id"),
        "updated_at_utc": now,
        "active_node": active_node,
        "nodes": nodes,
        "source_coverage_row_ids": missing_source_ids,
        "contract": [
            "Work on one active node at a time.",
            "Record evidence before marking a node verified.",
            "If source coverage rows exist, every incomplete row id must appear in a plan node or a blocker.",
            "Use the graph to survive context resets and avoid dropping large-task subparts.",
        ],
    }


def build_goal_bridge(
    root: Path,
    goal_payload: dict[str, Any],
    loop_payload: dict[str, Any],
    previous_bridge: dict[str, Any] | None,
    args: argparse.Namespace,
    now: str,
) -> dict[str, Any]:
    previous_agent_goal = {}
    if isinstance(previous_bridge, dict):
        # Read the engine-neutral key, falling back to the legacy codex_goal key.
        previous_agent_goal = previous_bridge.get("agent_goal") or previous_bridge.get("codex_goal") or {}
    goal_status = args.goal_status or (
        previous_agent_goal.get("status") if isinstance(previous_agent_goal, dict) else None
    )
    goal_objective = args.goal_objective or (
        previous_agent_goal.get("objective") if isinstance(previous_agent_goal, dict) else None
    )
    linked = bool(goal_status or goal_objective)
    return {
        "schema_version": RALPH_SCHEMA_VERSION,
        "updated_at_utc": now,
        "repo_root": str(root),
        "ralph_goal_id": goal_payload.get("goal_id"),
        "ralph_goal": goal_payload.get("goal"),
        "mode": "agent_goal_linked" if linked else "standalone",
        "agent_goal": {
            "status": goal_status or "not_checked",
            "objective": goal_objective,
            "last_synced_at_utc": now if linked else None,
        },
        "synergy_contract": [
            "RALPH must remain sufficient when /goal is not active.",
            "When /goal is active, treat it as the live objective and RALPH as the durable evidence controller.",
            "Do not mark /goal complete until RALPH completion_readiness.ready is true.",
            "Do not mark /goal blocked until RALPH records a concrete blocker or repeated no-progress loop.",
        ],
        "recommended_goal_tool_actions": {
            "when_starting": "create_goal(objective=<ralph goal>) if no active /goal exists and the user wants runtime supervision",
            "when_done": "update_goal(status='complete') only after RALPH completion readiness is true",
            "when_blocked": "update_goal(status='blocked') only after RALPH blocker evidence is durable",
        },
        "ralph_status": loop_payload.get("status"),
        "ralph_completion_ready": loop_payload.get("completion_readiness", {}).get("ready"),
    }


def render_iteration(iteration: int, goal_payload: dict[str, Any], loop_payload: dict[str, Any], now: str) -> str:
    acceptance = goal_payload.get("definition_of_done", {}).get("acceptance_criteria", [])
    validation = goal_payload.get("definition_of_done", {}).get("validation_commands", [])
    acceptance_matrix = goal_payload.get("definition_of_done", {}).get("acceptance_matrix", [])
    validation_matrix = goal_payload.get("definition_of_done", {}).get("validation_matrix", [])
    closeout_matrix = goal_payload.get("definition_of_done", {}).get("closeout_matrix", [])
    lines = [
        f"# RALPH Iteration {iteration:04d}",
        "",
        f"- generated_at_utc: `{now}`",
        f"- goal_id: `{goal_payload.get('goal_id')}`",
        f"- status: `{loop_payload.get('status')}`",
        f"- loop_phase: `{loop_payload.get('loop_phase')}`",
        f"- implementation_gate: `{loop_payload.get('implementation_gate')}`",
        "",
        "## Goal",
        "",
        str(goal_payload.get("goal") or ""),
        "",
        "## Acceptance Criteria",
        "",
    ]
    if isinstance(acceptance_matrix, list) and acceptance_matrix:
        lines.extend(
            f"- [ ] `{row.get('id')}` {row.get('criterion')} (status: `{row.get('status')}`)"
            for row in acceptance_matrix
            if isinstance(row, dict)
        )
    else:
        lines.extend(f"- [ ] {item}" for item in acceptance)
    lines.extend(["", "## Validation Ladder", ""])
    if isinstance(validation_matrix, list) and validation_matrix:
        lines.extend(
            f"- [ ] `{row.get('id')}` {row.get('check')} (status: `{row.get('status')}`)"
            for row in validation_matrix
            if isinstance(row, dict)
        )
    else:
        lines.extend(f"- [ ] {item}" for item in validation)
    lines.extend(["", "## Closeout Gate", ""])
    if isinstance(closeout_matrix, list) and closeout_matrix:
        lines.extend(
            f"- [ ] `{row.get('id')}` {row.get('requirement')} (status: `{row.get('status')}`)"
            for row in closeout_matrix
            if isinstance(row, dict)
        )
    else:
        lines.extend(f"- [ ] {item}" for item in CLOSEOUT_REQUIRED)
    lines.extend(
        [
            "",
            "## Evidence Ledger",
            "",
            "- Record observed proof in `.rah/ralph/evidence_ledger.json` through `--record-evidence` or `--record-gap`.",
            "",
            "## Loop Checklist",
            "",
            "- [ ] Read the nearest active AGENTS.md and saved harness state.",
            "- [ ] Run or inspect doctor/status/resume before broad edits.",
            "- [ ] Confirm the active node in `.rah/ralph/plan_graph.json`.",
            "- [ ] Define the smallest bounded phase that advances the goal.",
            "- [ ] Implement only within that bounded phase.",
            "- [ ] Run validation and record any remaining gap.",
            "- [ ] Review the diff for correctness, regression risk, and missing tests.",
            "- [ ] Mark acceptance or validation rows only after evidence is recorded.",
            "- [ ] Update `.rah/ralph/loop_state.json` and stop if done or blocked.",
            "",
            "## Notes",
            "",
            "- ",
            "",
        ]
    )
    return "\n".join(lines)


def render_managed_current_loop(goal_payload: dict[str, Any], loop_payload: dict[str, Any]) -> str:
    actions = loop_payload.get("next_actions") or []
    readiness = loop_payload.get("completion_readiness") if isinstance(loop_payload.get("completion_readiness"), dict) else {}
    state_machine = loop_payload.get("state_machine") if isinstance(loop_payload.get("state_machine"), dict) else {}
    review_gate = loop_payload.get("review_gate") if isinstance(loop_payload.get("review_gate"), dict) else {}
    lines = [
        "## RALPH Goal Loop",
        "",
        f"- goal_id: `{goal_payload.get('goal_id')}`",
        f"- status: `{loop_payload.get('status')}`",
        f"- iteration: `{loop_payload.get('current_iteration')}` / `{loop_payload.get('max_iterations')}`",
        f"- completion_mode: `{loop_payload.get('completion_mode')}`",
        f"- checkpoint_required: `{loop_payload.get('checkpoint_required')}`",
        f"- loop_phase: `{loop_payload.get('loop_phase')}`",
        f"- state: `{state_machine.get('current_state')}`",
        f"- implementation_gate: `{loop_payload.get('implementation_gate')}`",
        f"- completion_ready: `{readiness.get('ready')}`",
        f"- review_status: `{review_gate.get('status')}`",
        f"- missing_closeout_ids: `{readiness.get('missing_closeout_ids')}`",
        f"- blocked_reason: `{loop_payload.get('blocked_reason')}`",
        "",
        "### Next Actions",
        "",
    ]
    lines.extend(f"- {action}" for action in actions)
    lines.extend(
        [
            "",
            "### State",
            "",
            "- `.rah/ralph/goal.json`",
            "- `.rah/ralph/loop_state.json`",
            "- `.rah/ralph/evidence_ledger.json`",
            "- `.rah/ralph/plan_graph.json`",
            "- `.rah/ralph/goal_bridge.json`",
            "- `.rah/ralph/review_gate.json`",
            "- `.rah/ralph/iterations/`",
        ]
    )
    return "\n".join(lines)


def upsert_current_loop(path: Path, block: str) -> None:
    wrapped = f"{MANAGED_BLOCK_START}\n{block}\n{MANAGED_BLOCK_END}\n"
    if path.exists():
        content = path.read_text(encoding="utf-8")
    else:
        content = "# Current Loop\n"
    if MANAGED_BLOCK_START in content and MANAGED_BLOCK_END in content:
        before, rest = content.split(MANAGED_BLOCK_START, 1)
        _, after = rest.split(MANAGED_BLOCK_END, 1)
        new_content = before.rstrip() + "\n\n" + wrapped + after.lstrip()
    else:
        new_content = content.rstrip() + "\n\n" + wrapped
    write_text(path, new_content)


def render_completion_report(goal_payload: dict[str, Any], loop_payload: dict[str, Any], now: str) -> str:
    readiness = loop_payload.get("completion_readiness") if isinstance(loop_payload.get("completion_readiness"), dict) else {}
    review_gate = loop_payload.get("review_gate") if isinstance(loop_payload.get("review_gate"), dict) else {}
    return "\n".join(
        [
            "# RALPH Completion Report",
            "",
            f"- generated_at_utc: `{now}`",
            f"- goal_id: `{goal_payload.get('goal_id')}`",
            f"- status: `{loop_payload.get('status')}`",
            f"- iterations_used: `{loop_payload.get('current_iteration')}`",
            "",
            "## Goal",
            "",
            str(goal_payload.get("goal") or ""),
            "",
            "## Evidence",
            "",
            f"- completion_ready: `{readiness.get('ready')}`",
            f"- evidence_count: `{readiness.get('evidence_count')}`",
            f"- missing_closeout_ids: `{readiness.get('missing_closeout_ids')}`",
            f"- review_status: `{review_gate.get('status')}`",
            f"- review_summary: `{review_gate.get('approval_summary')}`",
            "- Evidence details are recorded in `.rah/ralph/evidence_ledger.json`.",
            "- Acceptance and validation row statuses are recorded in `.rah/ralph/goal.json`.",
            "- Reviewer verification is recorded in `.rah/ralph/review_gate.json`.",
            "",
        ]
    )


def render_blockers(goal_payload: dict[str, Any], loop_payload: dict[str, Any], now: str) -> str:
    return "\n".join(
        [
            "# RALPH Blockers",
            "",
            f"- generated_at_utc: `{now}`",
            f"- goal_id: `{goal_payload.get('goal_id')}`",
            f"- blocked_reason: `{loop_payload.get('blocked_reason')}`",
            "",
            "## Goal",
            "",
            str(goal_payload.get("goal") or ""),
            "",
            "## Required Resolution",
            "",
            "- TODO: specify the user input, external access, or repo fix needed to continue.",
            "",
        ]
    )


def main() -> int:
    parser = _SuggestingArgumentParser(description="Create or update a RALPH goal-loop packet for a repository.")
    parser.add_argument("repo_root", help="Path to the repository root")

    goal_group = parser.add_argument_group(
        "goal & progress", "Define or refine the goal and its loop settings."
    )
    goal_group.add_argument("--goal", default=None, help="Goal to pursue recursively until done or blocked.")
    goal_group.add_argument("--acceptance", action="append", default=[], help="Acceptance criterion. Can be repeated.")
    goal_group.add_argument("--validation", action="append", default=[], help="Validation command or check. Can be repeated.")
    goal_group.add_argument(
        "--completion-mode",
        choices=sorted(COMPLETION_MODES),
        default=None,
        help="bounded stops at max_iterations; exhaustive treats max_iterations as a checkpoint and loops until complete.",
    )
    goal_group.add_argument("--max-iterations", type=int, default=None, help="Maximum RALPH loop iterations.")
    goal_group.add_argument("--require-source-coverage", action="store_true", help="Require source coverage before review or done.")
    goal_group.add_argument("--no-require-source-coverage", action="store_true", help="Disable inferred source coverage requirement for this goal.")
    goal_group.add_argument("--require-prd", action="store_true", help="Require a ready PRD projection before review or done.")
    goal_group.add_argument("--no-require-prd", action="store_true", help="Clear the PRD projection requirement for this goal.")
    goal_group.add_argument(
        "--goal-status",
        "--codex-goal-status",
        dest="goal_status",
        default=None,
        help="Optional live goal-supervisor (e.g. Codex /goal) status snapshot for bridge state.",
    )
    goal_group.add_argument(
        "--goal-objective",
        "--codex-goal-objective",
        dest="goal_objective",
        default=None,
        help="Optional live goal-supervisor (e.g. Codex /goal) objective snapshot for bridge state.",
    )

    rows_group = parser.add_argument_group(
        "matrix row updates (acceptance/validation/closeout coverage rows)",
        "Mark A#/V#/C# rows; every row update needs evidence via the evidence group.",
    )
    rows_group.add_argument("--acceptance-met", action="append", default=[], help="Acceptance row id to mark met, such as A1.")
    rows_group.add_argument("--validation-passed", action="append", default=[], help="Validation row id to mark passed, such as V1.")
    rows_group.add_argument("--closeout-met", action="append", default=[], help="Closeout row id to mark met, such as C1.")
    rows_group.add_argument(
        "--closeout-documented",
        action="append",
        default=[],
        help="Closeout row id to mark documented as an acceptable gap, such as C2.",
    )

    evidence_group = parser.add_argument_group(
        "evidence", "Record observed proof; row updates attach these entries."
    )
    evidence_group.add_argument("--with-evidence", action="append", default=[], help="Existing evidence id to attach to row updates, such as E0001.")
    evidence_group.add_argument("--record-evidence", action="append", default=[], help="Observed evidence note. Can be repeated.")
    evidence_group.add_argument("--record-gap", action="append", default=[], help="Documented validation or acceptance gap. Can be repeated.")

    review_group = parser.add_argument_group(
        "review gate", "Request review first; approve/reject in a separate later invocation."
    )
    review_group.add_argument("--request-review", action="store_true", help="Open the reviewer verification gate for completion or current story.")
    review_group.add_argument("--review-approved", default=None, help="Mark reviewer verification approved with this summary.")
    review_group.add_argument("--review-rejected", default=None, help="Mark reviewer verification rejected with this feedback.")
    review_group.add_argument("--review-fallback", default=None, help="Record an explicit reviewer subagent/external review failure and require main-thread fallback review. Pending/no-response review is not enough.")
    review_group.add_argument(
        "--review-evidence",
        action="append",
        default=[],
        help="Eligible evidence id the approval is bound to (repeatable); an E#### citation inside the summary also counts.",
    )
    review_group.add_argument("--review-note", default=None, help="Optional note to include when requesting reviewer verification.")
    review_group.add_argument("--reviewer", default="reviewer", help="Reviewer label for the verification gate.")
    review_group.add_argument(
        "--review-wait-timeout-ms",
        type=int,
        default=DEFAULT_REVIEW_WAIT_TIMEOUT_MS,
        help="wait_agent timeout for pending reviewer responses. Default is 3600000 ms, the current tool maximum; pending/no-response remains a wait state.",
    )

    closeout_group = parser.add_argument_group(
        "closeout & terminal state", "--mark-done is valid only together with --closeout-check."
    )
    closeout_group.add_argument("--closeout-check", action="store_true", help="Run the structured RALPH closeout audit and write closeout_check.*.")
    closeout_group.add_argument("--mark-done", action="store_true", help="Mark the goal complete.")
    closeout_group.add_argument("--block", default=None, help="Mark the loop blocked with this reason.")
    closeout_group.add_argument("--reset", action="store_true", help="Replace the existing RALPH goal.")
    closeout_group.add_argument("--replace-terminal-goal", action="store_true", help="Archive terminal stale RALPH state when --goal differs from the retained goal.")

    output_group = parser.add_argument_group("output & bookkeeping")
    output_group.add_argument("--no-increment", action="store_true", help="Refresh state without starting a new iteration.")
    output_group.add_argument("--no-update-current-loop", action="store_true", help="Do not update .rah/plans/current_loop.md.")
    output_group.add_argument(
        "--repair-state-snapshots",
        action="store_true",
        help="Explicit recovery: regenerate flat state snapshots from the committed generation, then exit.",
    )
    output_group.add_argument("--json", action="store_true", help="Emit JSON only.")
    args = parser.parse_args()

    root = Path(args.repo_root).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        print(json.dumps({"error": f"Missing repo root: {root}"}, ensure_ascii=False))
        return 2
    # Serialize state-writing invocations: parallel `--record-evidence` next to
    # `--closeout-check` raced on evidence_ledger/loop_state and dropped
    # freshly recorded entries. atexit covers every return/SystemExit path.
    ralph_lock = state_lock.acquire_state_lock(root, "ralph_state")
    atexit.register(state_lock.release_state_lock, ralph_lock)
    if args.mark_done and args.block:
        print(json.dumps({"error": "Use only one of --mark-done or --block."}, ensure_ascii=False))
        return 2
    if args.request_review and (args.review_approved or args.review_rejected):
        print(
            json.dumps(
                {
                    "error": (
                        "--request-review must persist a pending review gate before a decision; "
                        "run --review-approved or --review-rejected in a later invocation."
                    )
                },
                ensure_ascii=False,
            )
        )
        return 2
    if args.review_approved and args.review_rejected:
        print(json.dumps({"error": "Use only one of --review-approved or --review-rejected."}, ensure_ascii=False))
        return 2
    if args.review_fallback and (args.review_approved or args.review_rejected):
        print(json.dumps({"error": "--review-fallback records a failed review path; run approval/rejection in a later command after fallback review evidence exists."}, ensure_ascii=False))
        return 2
    if args.review_wait_timeout_ms < 10000 or args.review_wait_timeout_ms > 3600000:
        print(json.dumps({"error": "--review-wait-timeout-ms must be between 10000 and 3600000."}, ensure_ascii=False))
        return 2
    if args.max_iterations is not None and args.max_iterations < 1:
        print(json.dumps({"error": "--max-iterations must be >= 1."}, ensure_ascii=False))
        return 2
    if args.require_source_coverage and args.no_require_source_coverage:
        print(json.dumps({"error": "Use only one of --require-source-coverage or --no-require-source-coverage."}, ensure_ascii=False))
        return 2
    if args.require_prd and args.no_require_prd:
        print(json.dumps({"error": "Use only one of --require-prd or --no-require-prd."}, ensure_ascii=False))
        return 2
    if args.reset and not args.goal:
        print(json.dumps({"error": "--reset requires --goal so the archived state is replaced by an explicit new objective."}, ensure_ascii=False))
        return 2

    rah_root = root / ".rah"
    ralph_state_root = rah_root / "ralph"
    if getattr(args, "repair_state_snapshots", False):
        try:
            repaired = state_store.repair_snapshots(ralph_state_root)
        except state_store.StateStoreError as exc:
            print(json.dumps({"error": str(exc)}, ensure_ascii=False))
            return 2
        print(json.dumps({"operation": "repair-state-snapshots", **repaired}, ensure_ascii=False))
        return 0
    try:
        # R16: torn state (pointer vs snapshots) refuses every operation up
        # front; recovery is explicit, never an automatic older-generation
        # fallback.
        state_store.verify_current(ralph_state_root)
    except state_store.StateStoreError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2
    ralph_root = rah_root / "ralph"
    iterations_root = ralph_root / "iterations"
    now = utc_now()
    replacement_notice = None
    if args.reset and ralph_root.exists():
        replacement_notice = archive_ralph_state(root, reason="reset", now=now)
    try:
        status_payload = load_json(rah_root / "state" / "status.json")
        gates_payload = load_json(rah_root / "state" / "gates.json")
        existing_goal = None if args.reset else first_existing_goal(rah_root)
        previous_loop = None if args.reset else existing_loop_state(rah_root)
        evidence_ledger = existing_evidence_ledger(rah_root)
        previous_plan_graph = None if args.reset else existing_plan_graph(rah_root)
        previous_goal_bridge = None if args.reset else existing_goal_bridge(rah_root)
        previous_review_gate = None if args.reset else existing_review_gate(rah_root)
    except SystemExit as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2

    stale_terminal_status = terminal_status(existing_goal, previous_loop)
    if args.goal and retained_goal_differs(existing_goal, previous_loop, args.goal):
        if stale_terminal_status:
            if stale_terminal_status == "blocked" and not args.replace_terminal_goal:
                print(
                    json.dumps(
                        {
                            "error": (
                                "Existing RALPH state is blocked with a different goal. "
                                "Use --replace-terminal-goal or --reset to archive it before starting a new goal."
                            ),
                            "existing_status": stale_terminal_status,
                        },
                        ensure_ascii=False,
                    )
                )
                return 2
            replacement_notice = archive_ralph_state(root, reason=f"replace-{stale_terminal_status}-goal", now=now)
            existing_goal = None
            previous_loop = None
            evidence_ledger = {"schema_version": RALPH_SCHEMA_VERSION, "entries": []}
            previous_plan_graph = None
            previous_goal_bridge = None
            previous_review_gate = None
        else:
            print(
                json.dumps(
                    {
                        "error": "Existing active RALPH state has a different goal. Use --reset to archive it, or omit --goal to resume.",
                        "existing_status": str(
                            (previous_loop.get("status") if isinstance(previous_loop, dict) else None)
                            or (existing_goal.get("status") if isinstance(existing_goal, dict) else None)
                            or "active"
                        ),
                    },
                    ensure_ascii=False,
                )
            )
            return 2

    try:
        goal_payload = build_goal_payload(root, args, existing_goal, now)
    except SystemExit as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2

    prior_status = str(
        (previous_loop.get("status") if isinstance(previous_loop, dict) else None)
        or goal_payload.get("status")
        or ""
    ).lower()
    row_update_requested = bool(args.acceptance_met or args.validation_passed or args.closeout_met or args.closeout_documented)
    if row_update_requested and not (args.record_evidence or args.record_gap or args.with_evidence):
        print(
            json.dumps(
                {"error": "Row updates require explicit evidence: pass --record-evidence, --record-gap, or --with-evidence E####."},
                ensure_ascii=False,
            )
        )
        return 2
    if args.with_evidence:
        _, missing_evidence = explicit_evidence_ids(evidence_ledger, args.with_evidence)
        if missing_evidence:
            print(json.dumps({"error": f"Unknown or ineligible evidence id(s): {', '.join(missing_evidence)}"}, ensure_ascii=False))
            return 2
    gate_only_operation = (
        args.request_review
        or args.review_approved
        or args.review_rejected
        or args.review_fallback
        or args.closeout_check
    )
    increment = (
        not args.no_increment
        and not args.mark_done
        and not args.block
        and not gate_only_operation
        and prior_status not in TERMINAL_STATUSES
    )
    iteration = next_iteration_number(rah_root, previous_loop, increment)
    progress_update = apply_goal_progress(goal_payload, evidence_ledger, args, now=now, iteration=iteration)
    if args.request_review or args.review_approved:
        source_coverage = assess_source_coverage(root, required=bool(goal_payload.get("source_coverage_required")))
        prd_projection = assess_prd_projection(
            root, required=bool(goal_payload.get("prd_required")), source_coverage=source_coverage
        )
        review_prereq = assess_completion_readiness(
            goal_payload,
            evidence_ledger,
            {"required": False, "status": "not_required"},
            source_coverage,
            prd_projection,
        )
        if (
            review_prereq.get("missing_acceptance_ids")
            or review_prereq.get("missing_validation_ids")
            or review_prereq.get("missing_closeout_ids")
            or review_prereq.get("missing_evidence")
            or review_prereq.get("source_coverage_missing_ids")
            or review_prereq.get("source_coverage_missing_evidence_ids")
            or review_prereq.get("source_coverage_missing_source_evidence_ids")
            or review_prereq.get("source_coverage_missing_validation_ids")
            or review_prereq.get("source_coverage_missing_semantic_validation_ids")
            or review_prereq.get("source_coverage_missing_negative_test_ids")
            or review_prereq.get("source_coverage_missing_provenance_evidence_ids")
            or review_prereq.get("source_coverage_coarse_requirement_unit_ids")
            or review_prereq.get("source_coverage_invalid_row_ids")
            or review_prereq.get("source_coverage_missing_reason")
            or review_prereq.get("prd_blocks_completion")
        ):
            gate_error = (
                "Reviewer completion gate requires source coverage, PRD projection (when required), acceptance, validation, "
                "closeout, and explicit evidence to be complete before --request-review or --review-approved."
            )
            if args.json:
                print(json.dumps({"error": gate_error, "readiness": review_prereq}, ensure_ascii=False))
            else:
                # Human/agent-readable path: the full readiness dict is ~58
                # mostly-empty fields; emit the condensed row buckets plus only
                # the populated readiness fields so the driving agent does not
                # re-read ~2KB of empty arrays on every refusal.
                incomplete = structured_incomplete_rows(
                    goal_payload, {"completion_readiness": review_prereq}
                )
                always_keep = {"ready", "missing_evidence", "review_status"}
                filtered = {
                    key: value
                    for key, value in review_prereq.items()
                    if key in always_keep or value not in (None, [], {}, "", False, 0)
                }
                print(
                    json.dumps(
                        {"error": gate_error, "incomplete": incomplete, "readiness": filtered},
                        ensure_ascii=False,
                    )
                )
            return 2
    deferred_gate_error: str | None = None
    try:
        current_review_snapshot = compute_review_snapshot(root, goal_payload, evidence_ledger)
        review_gate = build_review_gate(
            goal_payload,
            previous_review_gate,
            args,
            now,
            evidence_ledger=evidence_ledger,
            iteration=iteration,
            review_snapshot=current_review_snapshot,
        )
        deferred_gate_error = review_gate.pop("_deferred_error", None)
        if deferred_gate_error:
            # The demotion (e.g. stale-on-drift) still flows into the ONE
            # final state commit below; the invocation fails afterwards.
            print(json.dumps({"error": deferred_gate_error}, ensure_ascii=False))
        if args.review_approved is not None and review_gate.get("status") == "approved":
            # Re-anchor the snapshot to the approved state: the approval's own
            # audit entry is part of what was blessed, so it must not count as
            # post-approval drift. Anything recorded AFTER this point does.
            # The freshly recomputed snapshot replaces the invocation-start one
            # for the stale comparison below as well — comparing the anchored
            # state against the pre-approval capture would self-stale.
            current_review_snapshot = compute_review_snapshot(
                root, goal_payload, evidence_ledger
            )
            review_gate["review_snapshot"] = current_review_snapshot
        # R13: an approved review whose captured subject no longer matches the
        # live state is stale — every invocation degrades it immediately, so
        # mark-done can never ride an approval for different work.
        if review_gate.get("status") == "approved":
            stale_fields = review_snapshot_drift(
                review_gate.get("review_snapshot"), current_review_snapshot
            )
            if stale_fields:
                review_gate["status"] = "stale"
                review_gate["stale_reason"] = (
                    "review subject changed after approval: " + ", ".join(stale_fields)
                )
    except SystemExit as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2
    loop_payload = build_loop_state(
        root,
        goal_payload,
        status_payload,
        gates_payload,
        evidence_ledger,
        review_gate,
        progress_update,
        previous_loop,
        args,
        now,
        iteration,
    )
    mark_done_closeout_candidate = bool(args.mark_done and args.closeout_check and loop_payload.get("done"))
    closeout_candidate_loop_payload = None
    if mark_done_closeout_candidate:
        closeout_candidate_loop_payload = json.loads(json.dumps(loop_payload, ensure_ascii=False))
        loop_payload["status"] = "active"
        loop_payload["done"] = False
        loop_payload["closeout_pending"] = True
        loop_payload["mark_done_candidate"] = True
        loop_payload["next_actions"] = [
            "Run the structured closeout audit before persisting done.",
            "If closeout passes, persist done atomically with the closeout evidence attached.",
            "If closeout fails, fix the failed closeout sections and retry --mark-done --closeout-check.",
        ]
    iteration = int(loop_payload.get("current_iteration") or 0)
    plan_graph = build_plan_graph(goal_payload, loop_payload, previous_plan_graph, now)
    goal_bridge = build_goal_bridge(root, goal_payload, loop_payload, previous_goal_bridge, args, now)

    ralph_root.mkdir(parents=True, exist_ok=True)
    iterations_root.mkdir(parents=True, exist_ok=True)
    # R15: state writes are DEFERRED — every mutation below edits the same
    # in-memory objects and one generation commit lands at the end, so a
    # crash anywhere in this flow leaves the previous complete generation.

    if iteration > 0 and not args.no_increment and not args.mark_done and not args.block and not gate_only_operation:
        write_text(iterations_root / f"{iteration:04d}.md", render_iteration(iteration, goal_payload, loop_payload, now))

    if not args.no_update_current_loop:
        upsert_current_loop(rah_root / "plans" / "current_loop.md", render_managed_current_loop(goal_payload, loop_payload))

    status_refresh = refresh_status_for_ralph(root, rah_root, goal_payload, loop_payload, now, replacement_notice=replacement_notice)
    if isinstance(status_refresh, dict):
        loop_payload["current_stage"] = status_refresh.get("current_stage")
        loop_payload["harness_phase"] = status_refresh.get("phase")

    closeout_payload = None
    if args.closeout_check:
        closeout_payload = closeout_check(root, goal_payload, loop_payload, now)
        loop_payload["closeout_check"] = {
            "ready": closeout_payload.get("ready"),
            "path": ".rah/ralph/closeout_check.json",
            "updated_at_utc": now,
        }

    if mark_done_closeout_candidate and closeout_payload:
        if closeout_payload.get("ready") and closeout_candidate_loop_payload is not None:
            loop_payload = closeout_candidate_loop_payload
            loop_payload["closeout_check"] = {
                "ready": closeout_payload.get("ready"),
                "path": ".rah/ralph/closeout_check.json",
                "updated_at_utc": now,
            }
            plan_graph = build_plan_graph(goal_payload, loop_payload, previous_plan_graph, now)
            goal_bridge = build_goal_bridge(root, goal_payload, loop_payload, previous_goal_bridge, args, now)
            if not args.no_update_current_loop:
                upsert_current_loop(rah_root / "plans" / "current_loop.md", render_managed_current_loop(goal_payload, loop_payload))
            goal_payload["status"] = "done"
            goal_payload["updated_at_utc"] = now
            write_text(ralph_root / "completion_report.md", render_completion_report(goal_payload, loop_payload, now))
        else:
            loop_payload["status"] = "active"
            loop_payload["done"] = False
            loop_payload["mark_done_rejected"] = True
            loop_payload["closeout_pending"] = False
            loop_payload["blocked_reason"] = None
            goal_payload["status"] = "active"
            goal_payload["updated_at_utc"] = now
            report_path = ralph_root / "completion_report.md"
            if report_path.exists():
                report_path.unlink()
    elif args.mark_done and loop_payload.get("done") and closeout_payload and not closeout_payload.get("ready"):
        loop_payload["status"] = "active"
        loop_payload["done"] = False
        loop_payload["mark_done_rejected"] = True
        loop_payload["blocked_reason"] = None
        goal_payload["status"] = "active"
        goal_payload["updated_at_utc"] = now
        report_path = ralph_root / "completion_report.md"
        if report_path.exists():
            report_path.unlink()
    elif args.mark_done and loop_payload.get("done"):
        goal_payload["status"] = "done"
        goal_payload["updated_at_utc"] = now
        write_text(ralph_root / "completion_report.md", render_completion_report(goal_payload, loop_payload, now))
    elif loop_payload.get("status") == "blocked":
        goal_payload["status"] = "blocked"
        goal_payload["updated_at_utc"] = now
        write_text(ralph_root / "blockers.md", render_blockers(goal_payload, loop_payload, now))
    elif loop_payload.get("status") in {"cancelled", "failed"}:
        goal_payload["status"] = loop_payload.get("status")
        goal_payload["updated_at_utc"] = now

    status_refresh = refresh_status_for_ralph(root, rah_root, goal_payload, loop_payload, now, replacement_notice=replacement_notice)
    if isinstance(status_refresh, dict):
        loop_payload["current_stage"] = status_refresh.get("current_stage")
        loop_payload["harness_phase"] = status_refresh.get("phase")

    # R15: the ONE authoritative state commit — a complete generation plus
    # atomically-replaced flat snapshots. Everything above only mutated
    # memory; a failure here leaves the previous generation intact.
    try:
        state_store.commit_generation(
            ralph_root,
            {
                "goal.json": goal_payload,
                "loop_state.json": loop_payload,
                "evidence_ledger.json": evidence_ledger,
                "plan_graph.json": plan_graph,
                "goal_bridge.json": goal_bridge,
                "review_gate.json": review_gate,
            },
        )
    except state_store.StateStoreError as exc:
        print(json.dumps({"error": f"state commit failed; previous state intact: {exc}"}, ensure_ascii=False))
        return 2

    payload = {
        "root": str(root),
        "ralph_state": loop_payload,
        "replaced_previous_goal": replacement_notice,
        "goal_path": relative_to_root(ralph_root / "goal.json", root),
        "loop_state_path": relative_to_root(ralph_root / "loop_state.json", root),
        "evidence_ledger_path": relative_to_root(ralph_root / "evidence_ledger.json", root),
        "plan_graph_path": relative_to_root(ralph_root / "plan_graph.json", root),
        "goal_bridge_path": relative_to_root(ralph_root / "goal_bridge.json", root),
        "review_gate_path": relative_to_root(ralph_root / "review_gate.json", root),
        "source_coverage_path": relative_to_root(ralph_root / "source_requirement_coverage.json", root),
        "closeout_check_path": relative_to_root(ralph_root / "closeout_check.json", root) if closeout_payload else None,
        "closeout_check_ready": closeout_payload.get("ready") if isinstance(closeout_payload, dict) else None,
        "iteration_path": relative_to_root(iterations_root / f"{iteration:04d}.md", root) if iteration > 0 else None,
        "next_actions": loop_payload.get("next_actions"),
    }

    if deferred_gate_error:
        # The compact deferred-error line already printed is the whole output:
        # emitting the payload after it would concatenate two JSON documents
        # under --json and bury the failure under ~2KB of state in human mode.
        return 2

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        # Compact human/agent block: state lives in .rah/ralph (single pointer
        # line instead of seven per-file paths) and None-valued fields are
        # omitted — the --json payload keeps every field and path unchanged.
        print("# RALPH Goal Loop\n")
        print(f"- root: {root}")
        print(f"- goal_id: {goal_payload.get('goal_id')}")
        print(f"- status: {loop_payload.get('status')}")
        print(f"- iteration: {loop_payload.get('current_iteration')} / {loop_payload.get('max_iterations')}")
        for label, value in (
            ("completion_mode", loop_payload.get("completion_mode")),
            ("checkpoint_required", loop_payload.get("checkpoint_required")),
            ("loop_phase", loop_payload.get("loop_phase")),
        ):
            if value is not None:
                print(f"- {label}: {value}")
        print(f"- review_status: {review_gate.get('status')}")
        missing_closeout = loop_payload.get("completion_readiness", {}).get("missing_closeout_ids")
        if missing_closeout:
            print(f"- missing_closeout_ids: {missing_closeout}")
        if loop_payload.get("implementation_gate") is not None:
            print(f"- implementation_gate: {loop_payload.get('implementation_gate')}")
        if replacement_notice:
            print(f"- replaced_previous_goal: {json.dumps(replacement_notice, ensure_ascii=False)}")
        if closeout_payload:
            print(f"- closeout_check_ready: {closeout_payload.get('ready')}")
            print(f"- closeout_check_path: {payload['closeout_check_path']}")
        if loop_payload.get("blocked_reason"):
            print(f"- blocked_reason: {loop_payload.get('blocked_reason')}")
        if loop_payload.get("mark_done_rejected"):
            print("- mark_done_rejected: completion readiness is not satisfied")
        print(f"- state_dir: {relative_to_root(ralph_root, root)}")
        if payload["iteration_path"]:
            print(f"- iteration_path: {payload['iteration_path']}")
        print("- next_actions:")
        for action in loop_payload.get("next_actions") or []:
            print(f"  - {action}")
    if loop_payload.get("mark_done_rejected"):
        return 2
    if closeout_payload and not closeout_payload.get("ready"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
