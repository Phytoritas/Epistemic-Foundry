#!/usr/bin/env python3
"""Bounded, read-only projection of persisted RALPH lifecycle state.

This module is intentionally event-neutral.  It never runs RAH commands, loads
project code, acquires the writer lock, or mutates repository state.  Consumers
receive only categorical status and counts; goal text, paths, actions, and
blocker content never leave the probe.
"""

from __future__ import annotations

import argparse

try:
    from cli_suggestions import SuggestingArgumentParser as _SuggestingArgumentParser
except Exception:  # stale repo helper tree may predate cli_suggestions
    _SuggestingArgumentParser = argparse.ArgumentParser
import json
import os
import stat
import time
from pathlib import Path
from typing import Any, Mapping, Sequence


PROBE_API_VERSION = 1
STATE_SCHEMA_VERSION = 2
SKILL_NAME = "recursive-architecture-refactoring-auto"
MAX_ANCESTORS = 64
MAX_STATE_BYTES = 512 * 1024
READ_ATTEMPTS = 3
READ_RETRY_SECONDS = 0.02
TERMINAL_STATUSES = {"done", "blocked", "failed", "cancelled", "canceled"}
ACTIVE_STATUSES = {"active", "verify", "review", "decide"}
REVIEW_STATUSES = {"not_requested", "pending", "approved", "rejected", "not_required"}
SUCCESS_STATUS = "done"
IO_REPARSE_TAG_SYMLINK = getattr(stat, "IO_REPARSE_TAG_SYMLINK", 0xA000000C)
IO_REPARSE_TAG_MOUNT_POINT = getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", 0xA0000003)


def _normal_status(value: Any) -> str:
    status = str(value or "").strip().casefold()
    return "cancelled" if status == "canceled" else status or "unknown"


def _normal_path(value: str | os.PathLike[str]) -> str:
    return os.path.normcase(os.path.abspath(os.path.expanduser(os.fspath(value))))


def _exists_without_following(path: Path) -> bool:
    try:
        path.lstat()
    except (FileNotFoundError, OSError):
        return False
    return True


def _path_is_linklike(path: Path) -> bool:
    try:
        info = path.lstat()
    except (FileNotFoundError, OSError):
        return False
    if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
        return True
    tag = getattr(info, "st_reparse_tag", 0)
    return tag in {IO_REPARSE_TAG_SYMLINK, IO_REPARSE_TAG_MOUNT_POINT}


def _directory_is_linklike(path: Path) -> bool:
    return _path_is_linklike(path)


def _empty_snapshot() -> dict[str, Any]:
    return {
        "probe_api_version": PROBE_API_VERSION,
        "present": False,
        "valid": True,
        "error_codes": [],
        "status": "absent",
        "terminal": False,
        "success_ready": False,
        "done_flag": False,
        "iteration": None,
        "readiness_ready": False,
        "missing_acceptance_count": 0,
        "missing_validation_count": 0,
        "missing_closeout_count": 0,
        "source_required": False,
        "source_ready": True,
        "prd_blocks_completion": False,
        "review_required": False,
        "review_status": "absent",
        "review_ready": False,
        "loop_closeout_ready": False,
        "file_closeout_ready": False,
        "completion_report_present": False,
        "external_driver_contract_present": False,
    }


def _discover_root(start: str | os.PathLike[str]) -> tuple[Path | None, str | None]:
    current = Path(_normal_path(start))
    if current.is_file():
        current = current.parent

    for _depth in range(MAX_ANCESTORS):
        rah_dir = current / ".rah"
        if _exists_without_following(rah_dir):
            if _directory_is_linklike(rah_dir):
                return current, "rah_directory_linklike"
            ralph_dir = rah_dir / "ralph"
            if _exists_without_following(ralph_dir):
                if _directory_is_linklike(ralph_dir):
                    return current, "ralph_directory_linklike"
                if _exists_without_following(ralph_dir / "loop_state.json"):
                    return current, None

        # A nested repository must not inherit lifecycle state from an outer one.
        if _exists_without_following(current / ".git"):
            return None, None
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None, None


def _read_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if _path_is_linklike(path):
        return None, "state_file_linklike"
    for attempt in range(READ_ATTEMPTS):
        try:
            before_info = path.stat()
            before = before_info.st_size
            if not stat.S_ISREG(before_info.st_mode):
                return None, "state_file_not_regular"
            if before > MAX_STATE_BYTES:
                return None, "state_file_oversized"
            with path.open("rb") as handle:
                opened_info = os.fstat(handle.fileno())
                if not stat.S_ISREG(opened_info.st_mode):
                    return None, "state_file_not_regular"
                raw = handle.read(MAX_STATE_BYTES + 1)
            if len(raw) > MAX_STATE_BYTES:
                return None, "state_file_oversized"
            if _path_is_linklike(path):
                return None, "state_file_linklike"
            after_info = path.stat()
            after = after_info.st_size
            if not stat.S_ISREG(after_info.st_mode):
                return None, "state_file_not_regular"
            if len(raw) > MAX_STATE_BYTES or after > MAX_STATE_BYTES:
                return None, "state_file_oversized"
            before_identity = (
                getattr(before_info, "st_dev", None),
                getattr(before_info, "st_ino", None),
            )
            after_identity = (
                getattr(after_info, "st_dev", None),
                getattr(after_info, "st_ino", None),
            )
            opened_identity = (
                getattr(opened_info, "st_dev", None),
                getattr(opened_info, "st_ino", None),
            )
            if (
                before != after
                or len(raw) != after
                or before_identity != after_identity
                or before_identity != opened_identity
            ):
                raise ValueError("transient state write")
            value = json.loads(raw.decode("utf-8"))
            return (value, None) if isinstance(value, dict) else (None, "state_invalid")
        except FileNotFoundError:
            return None, "state_missing"
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            if attempt + 1 < READ_ATTEMPTS:
                time.sleep(READ_RETRY_SECONDS)
                continue
            return None, "state_invalid"
    return None, "state_invalid"


def _count_list(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def _schema_ok(value: Mapping[str, Any] | None) -> bool:
    return bool(
        value
        and value.get("schema_version") == STATE_SCHEMA_VERSION
        and value.get("skill") == SKILL_NAME
    )


def inspect_state(start: str | os.PathLike[str]) -> dict[str, Any]:
    """Return a privacy-safe snapshot for the nearest repository state."""

    snapshot = _empty_snapshot()
    root, discovery_error = _discover_root(start)
    if root is None:
        return snapshot
    snapshot["present"] = True
    if discovery_error:
        snapshot.update(
            valid=False, status="inconsistent", error_codes=[discovery_error]
        )
        return snapshot

    state_dir = root / ".rah" / "ralph"
    payloads: dict[str, dict[str, Any] | None] = {}
    errors: list[str] = []
    for name in ("loop_state", "goal", "review_gate"):
        payload, error = _read_json(state_dir / f"{name}.json")
        payloads[name] = payload
        if error:
            errors.append(f"{name}_{error}")

    loop = payloads["loop_state"]
    goal = payloads["goal"]
    review = payloads["review_gate"]
    if not _schema_ok(loop):
        errors.append("loop_schema_mismatch")
    if not _schema_ok(goal):
        errors.append("goal_schema_mismatch")
    if not _schema_ok(review):
        errors.append("review_schema_mismatch")

    if (
        not isinstance(loop, Mapping)
        or not isinstance(goal, Mapping)
        or not isinstance(review, Mapping)
    ):
        snapshot.update(
            valid=False, status="inconsistent", error_codes=sorted(set(errors))
        )
        return snapshot

    expected_root = _normal_path(root)
    for label, value in (("loop", loop), ("goal", goal)):
        repo_root = value.get("repo_root")
        if not isinstance(repo_root, str) or _normal_path(repo_root) != expected_root:
            errors.append(f"{label}_repo_root_mismatch")

    goal_id = loop.get("goal_id")
    if not isinstance(goal_id, str) or not goal_id:
        errors.append("goal_id_missing")
    if goal.get("goal_id") != goal_id or review.get("goal_id") != goal_id:
        errors.append("goal_id_mismatch")

    status = _normal_status(loop.get("status"))
    goal_status = _normal_status(goal.get("status"))
    if status not in ACTIVE_STATUSES | TERMINAL_STATUSES:
        errors.append("status_unknown")
    if status != goal_status:
        errors.append("status_mismatch")
    if not isinstance(loop.get("done"), bool):
        errors.append("done_flag_invalid")
    readiness = loop.get("completion_readiness")
    if not isinstance(readiness, Mapping):
        readiness = {}
        errors.append("readiness_missing")

    if not isinstance(review.get("required"), bool):
        errors.append("review_required_invalid")
    for field in (
        "missing_acceptance_ids",
        "missing_validation_ids",
        "missing_closeout_ids",
    ):
        if not isinstance(readiness.get(field), list):
            errors.append(f"{field}_invalid")
    for field in (
        "ready",
        "missing_evidence",
        "missing_review",
        "source_coverage_required",
        "source_coverage_ready",
        "prd_blocks_completion",
    ):
        if not isinstance(readiness.get(field), bool):
            errors.append(f"{field}_invalid")

    review_required = review.get("required") is True
    review_status = _normal_status(review.get("status"))
    if review_status not in REVIEW_STATUSES:
        errors.append("review_status_unknown")
        review_status = "unknown"
    review_ready = (not review_required) or review_status == "approved"
    source_required = readiness.get("source_coverage_required") is True
    source_ready = (not source_required) or readiness.get(
        "source_coverage_ready"
    ) is True
    prd_blocks = readiness.get("prd_blocks_completion") is True
    loop_closeout = loop.get("closeout_check")
    loop_closeout_ready = (
        isinstance(loop_closeout, Mapping) and loop_closeout.get("ready") is True
    )

    closeout, closeout_error = _read_json(state_dir / "closeout_check.json")
    closeout_expected = status == SUCCESS_STATUS or loop.get("done") is True
    if closeout_error and closeout_error != "state_missing":
        errors.append(f"closeout_{closeout_error}")
    if closeout_expected and closeout_error:
        errors.append(f"closeout_{closeout_error}")
    file_closeout_ready = False
    if closeout is not None:
        if closeout.get("schema_version") != STATE_SCHEMA_VERSION:
            errors.append("closeout_schema_mismatch")
        if closeout.get("goal_id") != goal_id:
            errors.append("closeout_goal_id_mismatch")
        file_closeout_ready = closeout.get("ready") is True
        if closeout_expected:
            loop_timestamp = (
                loop_closeout.get("updated_at_utc")
                if isinstance(loop_closeout, Mapping)
                else None
            )
            file_timestamp = closeout.get("generated_at_utc")
            if (
                not isinstance(loop_timestamp, str)
                or not loop_timestamp
                or loop_timestamp != file_timestamp
            ):
                errors.append("closeout_timestamp_mismatch")

    report_path = state_dir / "completion_report.md"
    completion_report_present = bool(
        report_path.is_file() and not report_path.is_symlink()
    )
    missing_acceptance_count = _count_list(readiness.get("missing_acceptance_ids"))
    missing_validation_count = _count_list(readiness.get("missing_validation_ids"))
    missing_closeout_count = _count_list(readiness.get("missing_closeout_ids"))
    readiness_ready = bool(
        readiness.get("ready") is True
        and missing_acceptance_count == 0
        and missing_validation_count == 0
        and missing_closeout_count == 0
        and not readiness.get("missing_evidence")
        and not readiness.get("missing_review")
        and source_ready
        and not prd_blocks
    )
    done_flag = loop.get("done") is True
    success_ready = bool(
        not errors
        and status == SUCCESS_STATUS
        and goal_status == SUCCESS_STATUS
        and done_flag
        and readiness_ready
        and review_ready
        and loop_closeout_ready
        and file_closeout_ready
        and completion_report_present
    )

    snapshot.update(
        valid=not errors,
        error_codes=sorted(set(errors)),
        status=status if not errors else "inconsistent",
        terminal=status in TERMINAL_STATUSES,
        success_ready=success_ready,
        done_flag=done_flag,
        iteration=loop.get("current_iteration")
        if isinstance(loop.get("current_iteration"), int)
        else None,
        readiness_ready=readiness_ready,
        missing_acceptance_count=missing_acceptance_count,
        missing_validation_count=missing_validation_count,
        missing_closeout_count=missing_closeout_count,
        source_required=source_required,
        source_ready=source_ready,
        prd_blocks_completion=prd_blocks,
        review_required=review_required,
        review_status=review_status,
        review_ready=review_ready,
        loop_closeout_ready=loop_closeout_ready,
        file_closeout_ready=file_closeout_ready,
        completion_report_present=completion_report_present,
        external_driver_contract_present=isinstance(
            loop.get("external_driver_contract"), Mapping
        ),
    )
    return snapshot


def completion_blocker_codes(snapshot: Mapping[str, Any]) -> list[str]:
    """Classify why a present snapshot cannot support a success claim."""

    if not snapshot.get("present") or snapshot.get("success_ready") is True:
        return []
    if snapshot.get("valid") is not True:
        return ["state_inconsistent"]
    status = _normal_status(snapshot.get("status"))
    if status not in TERMINAL_STATUSES:
        return ["loop_nonterminal"]
    if status != SUCCESS_STATUS:
        return ["terminal_not_success"]
    blockers: list[str] = []
    if snapshot.get("readiness_ready") is not True:
        blockers.append("readiness_incomplete")
    if snapshot.get("review_ready") is not True:
        blockers.append("review_not_approved")
    if (
        snapshot.get("loop_closeout_ready") is not True
        or snapshot.get("file_closeout_ready") is not True
    ):
        blockers.append("closeout_unverified")
    if snapshot.get("completion_report_present") is not True:
        blockers.append("completion_report_missing")
    return blockers or ["success_state_inconsistent"]


def context_summary(snapshot: Mapping[str, Any]) -> str | None:
    """Render a fixed-vocabulary summary without untrusted state text."""

    if not snapshot.get("present"):
        return None
    if snapshot.get("valid") is not True:
        return (
            "RAH lifecycle state=inconsistent; success_ready=false. "
            "Treat successful completion as unverified until canonical validation repairs the state. "
            "The external drive remains the sole hard-continuation authority."
        )
    source = "ready" if snapshot.get("source_ready") else "pending"
    if not snapshot.get("source_required"):
        source = "not-required"
    review = "ready" if snapshot.get("review_ready") else "pending"
    closeout = (
        "ready"
        if snapshot.get("loop_closeout_ready") and snapshot.get("file_closeout_ready")
        else "pending"
    )
    return (
        f"RAH lifecycle status={_normal_status(snapshot.get('status'))}; "
        f"terminal={str(bool(snapshot.get('terminal'))).lower()}; "
        f"success_ready={str(bool(snapshot.get('success_ready'))).lower()}; "
        f"source={source}; review={review}; closeout={closeout}. "
        "This observer is read-only; the external drive remains the sole hard-continuation authority."
    )


def build_parser() -> argparse.ArgumentParser:
    parser = _SuggestingArgumentParser(description=__doc__)
    parser.add_argument(
        "path", nargs="?", default=".", help="Starting directory for bounded discovery."
    )
    parser.add_argument("--json", action="store_true", help="Emit compact JSON.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = inspect_state(args.path)
    print(
        json.dumps(
            result,
            ensure_ascii=False,
            separators=(",", ":") if args.json else None,
            indent=None if args.json else 2,
        )
    )
    return 0 if result.get("valid") else 2


if __name__ == "__main__":
    raise SystemExit(main())
