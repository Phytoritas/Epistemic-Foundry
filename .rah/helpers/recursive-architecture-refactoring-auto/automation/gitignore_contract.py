#!/usr/bin/env python3
"""Manage the repo `.gitignore` contract for harness-generated local/private paths.

The harness creates only two root-level trees in a target repository — the
design scaffold (`docs/architecture/` by default) and the `.rah/` runtime
sidecar — plus a managed block inside `.gitignore` itself. Design artifacts and
durable `.rah` state stay tracked; this module keeps local/private runtime
residue inside `.rah/` ignored and lets the operator persist extra ignore
patterns in `.rah/state/gitignore_contract.json` so every `setup`,
auto-bootstrap, or `gitignore apply` re-run honors them.
"""
from __future__ import annotations

import argparse

try:
    from cli_suggestions import SuggestingArgumentParser as _SuggestingArgumentParser
except Exception:  # stale repo helper tree may predate cli_suggestions
    _SuggestingArgumentParser = argparse.ArgumentParser
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CONTRACT_SCHEMA_VERSION = 1
BLOCK_HEADER = "# RAH local/private runtime"

DEFAULT_IGNORE_RULES = [
    ".rah/archive/",
    ".rah/ralph/source_units/",
    ".rah/ralph/driver/cycles/",
    ".rah/jobs/*/stdout.log",
    ".rah/jobs/*/stderr.log",
    ".rah/jobs/*/wrapper_stdout.log",
    ".rah/jobs/*/wrapper_stderr.log",
    ".rah/jobs/*/events.jsonl",
    ".rah/jobs/*/checkpoints/",
    ".rah/jobs/*/result/",
    ".rah/fleet/worktrees/",
    ".rah/fleet/lock.json",
    ".rah/fleet/lock.guard",
    ".rah/fleet/runs/*/supervisor.json",
    ".rah/fleet/runs/*/mutation.lock",
    ".rah/fleet/runs/*/journal.jsonl",
    ".rah/fleet/runs/*/journal.jsonl.append.lock",
    ".rah/fleet/runs/*/conversation.jsonl",
    ".rah/fleet/runs/*/conversation.jsonl.append.lock",
    ".rah/fleet/runs/*/mailbox/",
    ".rah/fleet/runs/*/tasks/*/prompt_*.md",
    ".rah/fleet/runs/*/tasks/*/last_message_*.txt",
    ".rah/fleet/runs/*/tasks/*/stdout_*.log",
    ".rah/fleet/runs/*/tasks/*/stderr_*.log",
    ".rah/fleet/runs/*/tasks/*/test_output.log",
    ".rah/state/*.log",
    ".rah/state/*.pid",
    ".rah/state/*.lock",
    ".rah/logs/*.log",
    ".rah/tmp/",
    ".rah/cache/",
    ".rah/**/__pycache__/",
    ".rah/**/*.pyc",
]

# Rules that would blanket-ignore tracked-by-policy roots (see references/closeout.md).
BROAD_RULE_DENYLIST = {
    ".rah",
    ".rah/",
    ".rah/**",
    "docs",
    "docs/",
    "docs/**",
    "docs/architecture",
    "docs/architecture/",
    "architecture",
    "architecture/",
    "docs/design",
    "docs/design/",
    "configs/",
    "src/",
    "tests/",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def contract_path(root: Path) -> Path:
    return root / ".rah" / "state" / "gitignore_contract.json"


def gitignore_path(root: Path) -> Path:
    return root / ".gitignore"


def choose_scaffold_root(root: Path) -> Path:
    candidates = [
        root / "docs" / "architecture",
        root / "architecture",
        root / "docs" / "design",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return root / "docs" / "architecture"


def normalize_rule(raw: str) -> str:
    rule = raw.strip().replace("\\", "/")
    while rule.startswith("./"):
        rule = rule[2:]
    return rule


def rule_rejection_reason(rule: str, allow_broad: bool) -> str | None:
    if not rule:
        return "empty pattern"
    if rule.startswith("#"):
        return "comment lines are not ignore rules"
    if re.match(r"^[A-Za-z]:/", rule) or "://" in rule:
        return "absolute or machine-specific paths are not allowed in a tracked contract"
    if not allow_broad and rule.lstrip("!") in BROAD_RULE_DENYLIST:
        return "would blanket-ignore a tracked-by-policy root (pass --allow-broad to override)"
    return None


def load_contract(root: Path) -> dict[str, Any]:
    path = contract_path(root)
    if not path.exists():
        return {"schema_version": CONTRACT_SCHEMA_VERSION, "extra_ignores": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "schema_version": CONTRACT_SCHEMA_VERSION,
            "extra_ignores": [],
            "load_warning": f"unreadable gitignore contract at {path}: {exc}",
        }
    if not isinstance(data, dict):
        return {
            "schema_version": CONTRACT_SCHEMA_VERSION,
            "extra_ignores": [],
            "load_warning": f"gitignore contract at {path} is not a JSON object",
        }
    raw_extras = data.get("extra_ignores")
    extras: list[str] = []
    if isinstance(raw_extras, list):
        for item in raw_extras:
            if not isinstance(item, str):
                continue
            rule = normalize_rule(item)
            if rule and not rule.startswith("#") and rule not in extras:
                extras.append(rule)
    data["extra_ignores"] = extras
    data.setdefault("schema_version", CONTRACT_SCHEMA_VERSION)
    return data


def save_contract(root: Path, extras: list[str]) -> Path:
    path = contract_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "updated_at_utc": utc_now(),
        "extra_ignores": extras,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def effective_rules(root: Path) -> tuple[list[str], dict[str, Any]]:
    contract = load_contract(root)
    extras = [rule for rule in contract["extra_ignores"] if rule not in DEFAULT_IGNORE_RULES]
    return [*DEFAULT_IGNORE_RULES, *extras], contract


def _read_gitignore(root: Path) -> tuple[str, set[str]]:
    path = gitignore_path(root)
    text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    return text, {line.strip() for line in text.splitlines()}


def apply_contract(root: Path, dry_run: bool = False) -> dict[str, Any]:
    rules, contract = effective_rules(root)
    path = gitignore_path(root)
    existing, existing_lines = _read_gitignore(root)
    missing = [rule for rule in rules if rule not in existing_lines]
    payload: dict[str, Any] = {
        "gitignore_path": str(path),
        "contract_path": str(contract_path(root)),
        "default_rule_count": len(DEFAULT_IGNORE_RULES),
        "extra_ignores": [rule for rule in rules if rule not in DEFAULT_IGNORE_RULES],
        "added": missing,
        "already_present": [rule for rule in rules if rule in existing_lines],
        "dry_run": dry_run,
        "changed": bool(missing) and not dry_run,
    }
    if contract.get("load_warning"):
        payload["load_warning"] = contract["load_warning"]
    if not missing or dry_run:
        return payload
    addition: list[str] = []
    if BLOCK_HEADER not in existing_lines:
        addition.append(BLOCK_HEADER)
    addition.extend(missing)
    prefix = existing
    if existing and not existing.endswith("\n"):
        prefix += "\n"
    path.write_text(prefix + "\n".join(addition) + "\n", encoding="utf-8")
    return payload


def add_rules(root: Path, patterns: list[str], allow_broad: bool, apply_after: bool) -> dict[str, Any]:
    normalized: list[str] = []
    rejected: list[dict[str, str]] = []
    for raw in patterns:
        rule = normalize_rule(raw)
        reason = rule_rejection_reason(rule, allow_broad)
        if reason is not None:
            rejected.append({"pattern": raw, "reason": reason})
        elif rule not in normalized:
            normalized.append(rule)
    payload: dict[str, Any] = {
        "action": "add",
        "contract_path": str(contract_path(root)),
        "requested": patterns,
        "rejected": rejected,
        "added_to_contract": [],
        "already_in_contract": [],
    }
    if rejected:
        payload["error"] = "no rules were added; fix the rejected patterns first"
        return payload
    contract = load_contract(root)
    if contract.get("load_warning"):
        payload["load_warning"] = contract["load_warning"]
    extras = contract["extra_ignores"]
    for rule in normalized:
        if rule in DEFAULT_IGNORE_RULES or rule in extras:
            payload["already_in_contract"].append(rule)
        else:
            extras.append(rule)
            payload["added_to_contract"].append(rule)
    if payload["added_to_contract"]:
        save_contract(root, extras)
    if apply_after:
        payload["apply"] = apply_contract(root)
    return payload


def remove_rules(root: Path, patterns: list[str], keep_gitignore_lines: bool) -> dict[str, Any]:
    contract = load_contract(root)
    extras = contract["extra_ignores"]
    removed: list[str] = []
    skipped_defaults: list[str] = []
    not_found: list[str] = []
    for raw in patterns:
        rule = normalize_rule(raw)
        if rule in DEFAULT_IGNORE_RULES:
            skipped_defaults.append(rule)
        elif rule in extras:
            extras.remove(rule)
            removed.append(rule)
        else:
            not_found.append(rule)
    if removed:
        save_contract(root, extras)
    removed_lines: list[str] = []
    if removed and not keep_gitignore_lines:
        path = gitignore_path(root)
        if path.exists():
            text = path.read_text(encoding="utf-8", errors="replace")
            kept: list[str] = []
            for line in text.splitlines():
                if line.strip() in removed:
                    removed_lines.append(line.strip())
                else:
                    kept.append(line)
            if removed_lines:
                path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    payload: dict[str, Any] = {
        "action": "remove",
        "contract_path": str(contract_path(root)),
        "gitignore_path": str(gitignore_path(root)),
        "removed_from_contract": removed,
        "removed_gitignore_lines": removed_lines,
        "skipped_defaults": skipped_defaults,
        "not_found": not_found,
    }
    if skipped_defaults:
        payload["note"] = "default rules are policy (references/closeout.md) and cannot be removed here"
    if contract.get("load_warning"):
        payload["load_warning"] = contract["load_warning"]
    return payload


def generated_roots(root: Path) -> list[dict[str, Any]]:
    scaffold = choose_scaffold_root(root)
    try:
        scaffold_rel = scaffold.relative_to(root).as_posix() + "/"
    except ValueError:
        scaffold_rel = str(scaffold)
    return [
        {
            "path": ".rah/",
            "exists": (root / ".rah").exists(),
            "role": "runtime sidecar",
            "tracking": "durable state tracked; local/private runtime ignored via this contract",
        },
        {
            "path": scaffold_rel,
            "exists": scaffold.exists(),
            "role": "design scaffold",
            "tracking": "keep tracked",
        },
        {
            "path": ".gitignore",
            "exists": gitignore_path(root).exists(),
            "role": "managed RAH ignore block",
            "tracking": "keep tracked",
        },
    ]


def status_payload(root: Path) -> dict[str, Any]:
    rules, contract = effective_rules(root)
    _, existing_lines = _read_gitignore(root)
    payload: dict[str, Any] = {
        "action": "status",
        "repo_root": str(root),
        "contract_path": str(contract_path(root)),
        "contract_exists": contract_path(root).exists(),
        "gitignore_path": str(gitignore_path(root)),
        "gitignore_exists": gitignore_path(root).exists(),
        "default_rules": DEFAULT_IGNORE_RULES,
        "extra_ignores": [rule for rule in rules if rule not in DEFAULT_IGNORE_RULES],
        "missing_in_gitignore": [rule for rule in rules if rule not in existing_lines],
        "generated_roots": generated_roots(root),
    }
    if contract.get("load_warning"):
        payload["load_warning"] = contract["load_warning"]
    return payload


def main() -> int:
    parser = _SuggestingArgumentParser(
        description=(
            "Inspect and configure the managed RAH .gitignore contract: default local/private "
            "runtime rules plus repo-persisted extra ignore patterns."
        )
    )
    parser.add_argument("repo_root", help="Path to the repository root")
    sub = parser.add_subparsers(dest="action")
    sub.add_parser("status", help="Show defaults, extras, missing rules, and harness-generated roots.")
    add_parser = sub.add_parser("add", help="Persist extra ignore patterns and apply them to .gitignore.")
    add_parser.add_argument("patterns", nargs="+", help="Ignore patterns to add (gitignore syntax).")
    add_parser.add_argument("--no-apply", action="store_true", help="Persist to the contract without editing .gitignore.")
    add_parser.add_argument("--allow-broad", action="store_true", help="Allow rules that ignore tracked-by-policy roots.")
    remove_parser = sub.add_parser("remove", help="Remove extra patterns from the contract and .gitignore.")
    remove_parser.add_argument("patterns", nargs="+", help="Previously added extra patterns to remove.")
    remove_parser.add_argument(
        "--keep-gitignore-lines",
        action="store_true",
        help="Remove from the contract only; leave matching .gitignore lines in place.",
    )
    apply_parser = sub.add_parser("apply", help="Re-apply defaults plus persisted extras to .gitignore.")
    apply_parser.add_argument("--dry-run", action="store_true", help="Report missing rules without writing.")
    args = parser.parse_args()

    root = Path(args.repo_root).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        print(json.dumps({"error": f"Missing repo root: {root}"}, ensure_ascii=False))
        return 2

    action = args.action or "status"
    if action == "status":
        payload = status_payload(root)
        exit_code = 0
    elif action == "add":
        payload = add_rules(root, args.patterns, allow_broad=args.allow_broad, apply_after=not args.no_apply)
        exit_code = 2 if payload.get("rejected") else 0
    elif action == "remove":
        payload = remove_rules(root, args.patterns, keep_gitignore_lines=args.keep_gitignore_lines)
        exit_code = 0
    else:
        payload = {"action": "apply"} | apply_contract(root, dry_run=args.dry_run)
        exit_code = 0

    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
