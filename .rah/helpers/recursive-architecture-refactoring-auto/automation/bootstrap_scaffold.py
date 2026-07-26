#!/usr/bin/env python3
"""
Memento-aware bootstrap helper for the recursive architecture refactoring harness.

Usage:
    python automation/bootstrap_scaffold.py /path/to/repo --project-name my-service
    python automation/rah.py setup /path/to/repo --project-name my-service
"""
from __future__ import annotations

import argparse

try:
    from cli_suggestions import SuggestingArgumentParser as _SuggestingArgumentParser
except Exception:  # stale repo helper tree may predate cli_suggestions
    _SuggestingArgumentParser = argparse.ArgumentParser
import csv
import json
import re
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import gitignore_contract

SKILL_NAME = "recursive-architecture-refactoring-auto"
STATUS_SCHEMA_VERSION = 3

CSV_HEADERS = {
    "notebook/source_inventory.csv": [
        "source_id_or_title",
        "source_family",
        "role_in_design",
        "supports_decision_or_module",
        "evidence_strength",
        "counterpoint_present",
        "notes",
    ],
    "notebook/query_log.csv": [
        "query_id",
        "date",
        "target_decision",
        "query_mode",
        "result_summary",
        "source_refs",
        "follow_up_needed",
    ],
    "system/dependency_matrix.csv": [
        "source_module",
        "target_module",
        "dependency_type",
        "direction",
        "strength",
        "runtime_criticality",
        "comments",
    ],
    "system/interface_inventory.csv": [
        "interface_name",
        "producer",
        "consumer",
        "contract_type",
        "stability",
        "migration_sensitivity",
        "test_coverage",
        "notes",
    ],
    "system/hotspot_register.csv": [
        "hotspot_id",
        "location",
        "issue_type",
        "symptoms",
        "operational_impact",
        "suspected_root_cause",
        "urgency",
    ],
    "implementation/change_set_log.csv": [
        "change_id",
        "linked_adr",
        "linked_module",
        "objective",
        "tests_added_or_updated",
        "regression_risk",
        "status",
        "notes",
    ],
    "review/revision_log.csv": [
        "issue_id",
        "issue_summary",
        "source_artifact",
        "action_taken",
        "status",
        "evidence_updated",
        "follow_up_needed",
    ],
}

ARCH_DIRS = [
    "notebook",
    "system",
    "architecture",
    "architecture/adrs",
    "architecture/module_specs",
    "executor",
    "implementation",
    "review",
    "delivery",
]

HARNESS_DIRS = [
    ".rah/state",
    ".rah/logs",
    ".rah/memory",
    ".rah/plans",
    ".rah/jobs",
    ".rah/ralph",
    ".rah/ralph/iterations",
    ".rah/runtime",
]

MEMENTO_STATE_FILES = [
    ".rah/state/memento_status.json",
    ".rah/memory/memento_context.json",
    ".rah/memory/memento_recall.json",
    ".rah/memory/memento_feedback.json",
    ".rah/memory/memento_reflect_draft.json",
    ".rah/memory/wakeup.md",
    ".rah/memory/case_map.json",
]

RAH_GITIGNORE_BLOCK = [gitignore_contract.BLOCK_HEADER, *gitignore_contract.DEFAULT_IGNORE_RULES]


@dataclass
class Summary:
    root: str
    scaffold_root: str
    profile: str
    mode: str
    scope: str
    created_dirs: list[str] = field(default_factory=list)
    created_files: list[str] = field(default_factory=list)
    skipped_existing: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def has_any(root: Path, names: Iterable[str]) -> bool:
    return any((root / name).exists() for name in names)


def slugify(value: str) -> str:
    collapsed = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower())
    return re.sub(r"-{2,}", "-", collapsed).strip("-") or "repo"


def detect_profile(root: Path) -> str:
    if has_any(root, [".git"]) and has_any(root, ["pnpm-workspace.yaml", "turbo.json", "lerna.json"]):
        return "monorepo"
    if (root / "apps").exists() and (root / "packages").exists():
        return "monorepo"
    if (root / "go.mod").exists():
        return "go-service"
    if (root / "Cargo.toml").exists():
        return "rust-service"
    if has_any(root, ["pom.xml", "build.gradle", "build.gradle.kts"]):
        return "jvm-service"
    if has_any(root, ["pyproject.toml", "requirements.txt", "poetry.lock"]) or (
        (root / "src").exists() and (root / "tests").exists()
    ):
        return "python-service"
    if (root / "package.json").exists():
        if (root / "apps" / "api").exists() and (root / "apps" / "worker").exists():
            return "backend-worker"
        return "js-ts-app"
    if (
        (root / "domain").exists()
        and (root / "application").exists()
        and (root / "adapters").exists()
    ):
        return "layered-service"
    return "generic"


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


def relative_to_root(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def run_git(root: Path, args: list[str]) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *args],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    value = completed.stdout.strip()
    return value or None


def detect_git_branch(root: Path) -> str | None:
    branch = run_git(root, ["rev-parse", "--abbrev-ref", "HEAD"])
    if branch and branch != "HEAD":
        return branch
    head_path = root / ".git" / "HEAD"
    if head_path.exists():
        content = head_path.read_text(encoding="utf-8", errors="ignore").strip()
        if content.startswith("ref: "):
            return content.rsplit("/", 1)[-1]
    return None


def detect_origin_slug(root: Path) -> str | None:
    url = run_git(root, ["config", "--get", "remote.origin.url"])
    if not url:
        return None
    url = url.strip()
    if url.endswith(".git"):
        url = url[:-4]
    if ":" in url and not url.startswith("http"):
        url = url.split(":", 1)[1]
    else:
        parts = url.split("/")
        if len(parts) >= 2:
            url = "/".join(parts[-2:])
    slug = url.split("/")[-1] if "/" in url else url
    return slugify(slug)


def detect_issue_number(branch_name: str | None) -> int | None:
    if not branch_name:
        return None
    match = re.search(r"(?:^|/)(\d+)(?:[-_/]|$)", branch_name)
    if match:
        return int(match.group(1))
    return None


def derive_memento_workspace(root: Path, override: str | None = None) -> str:
    if override:
        return slugify(override)
    origin = detect_origin_slug(root)
    if origin:
        return origin
    return slugify(root.name)


def derive_memento_topic(profile: str, override: str | None = None) -> str:
    if override:
        return slugify(override)
    topic_map = {
        "python-service": "architecture-refactor",
        "js-ts-app": "architecture-refactor",
        "monorepo": "architecture-refactor",
        "backend-worker": "architecture-refactor",
        "layered-service": "architecture-refactor",
    }
    return topic_map.get(profile, "architecture-refactor")


def derive_memento_session_id(
    workspace: str,
    issue_number: int | None,
    branch_name: str | None,
    override: str | None = None,
) -> str:
    if override:
        return override
    branch_part = slugify(branch_name or "bootstrap")
    if issue_number is not None:
        return f"{workspace}#{issue_number}:{branch_part}"
    return f"{workspace}#adhoc:{branch_part}"


def derive_memento_case_id(
    workspace: str,
    issue_number: int | None,
    branch_name: str | None,
    profile: str,
    override: str | None = None,
) -> str:
    if override:
        return override
    short_name = slugify(branch_name or profile or "architecture-bootstrap")
    issue_part = str(issue_number) if issue_number is not None else "adhoc"
    return f"case/{workspace}/{issue_part}/{short_name}"


def find_memento_config_evidence(root: Path) -> list[str]:
    candidates = [
        root / ".codex" / "config.toml",
        Path.home() / ".codex" / "config.toml",
        root / ".claude" / "settings.json",
        Path.home() / ".claude" / "settings.json",
        root / "config.toml",
    ]
    evidence: list[str] = []
    for path in candidates:
        if not path.exists():
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore").lower()
        except OSError:
            continue
        if "memento" in content or "57332" in content:
            evidence.append(str(path))
    return evidence


def render_phytoritas(
    project_name: str,
    profile: str,
    root: Path,
    scaffold_root: Path,
    mode: str,
    workspace: str,
    topic: str,
    session_id: str,
    case_id: str,
) -> str:
    return f"""# Phytoritas Blueprint

## Objective
Use recursive architecture design and refactoring to improve **{project_name}** in a controlled, reviewable way.

## Bound Root
`{root}`

## Scaffold Root
`{relative_to_root(scaffold_root, root)}`

## Repo Profile
`{profile}`

## Harness Mode
`{mode}`

## Authority Order
1. repo-local `AGENTS.md`
2. global `AGENTS.md`
3. live repository facts
4. `.rah/` runtime state
5. Memento recall results
6. chat memory

## Memento Identity
- workspace: `{workspace}`
- topic: `{topic}`
- sessionId: `{session_id}`
- caseId: `{case_id}`

## Stage Map
1. Setup / doctor / status
2. AGENTS and workflow intake
3. Workspace audit and current-system recon
4. Architecture and module decisions
5. Validation design
6. Implementation gate
7. Incremental implementation
8. Review and regression hardening
9. Reflect and next loop setup

## Decision Gates
- AGENTS/workflow gate
- scaffold/harness gate
- current-system recon gate
- architecture evidence gate
- implementation gate
- memento recall / feedback hygiene gate

## Loop Contract
- Keep implementation blocked until the implementation gate passes.
- Re-read the nearest `AGENTS.md` before broad writes.
- Use `.rah/` for control-plane state and `docs/architecture/` for design artifacts.
- Use Memento as a memory aid, not as a policy source.
"""

def render_workspace_audit(project_name: str) -> str:
    return f"""# Workspace Audit

## Goal
Create the first trustworthy inventory for **{project_name}**.

## Inventory Targets
- repo markers and package managers
- entrypoints and runners
- core modules and boundaries
- tests, fixtures, validation scripts
- existing architecture notes and ADRs
- scripts/helpers that should be preferred over raw CLI

## Findings
- _Fill with observed facts only._

## Risks / Unknowns
- _List what is still unclear._
"""

def render_system_brief(project_name: str, profile: str) -> str:
    return f"""# Current System Brief

## System
{project_name}

## Profile Hint
`{profile}`

## What This System Appears To Do
- _Summarize only after reading the repo._

## Major Seams
- _interfaces_
- _modules_
- _execution paths_

## Validation Surface
- _tests_
- _lint/typecheck_
- _build/smoke checks_

## Open Questions
- _unknown dependencies_
- _unclear ownership_
- _missing coverage_
"""

def render_gap_register() -> str:
    return """# Gap Register

Track missing facts, weak evidence, and unresolved design questions.

| gap_id | area | why_it_matters | current_evidence | next_probe |
| --- | --- | --- | --- | --- |
| GAP-001 | architecture | implementation gate depends on this | pending | inspect repo |
"""

def render_current_architecture_map() -> str:
    return """# Current Architecture Map

## Entry Points
- _fill after recon_

## Core Modules
- _fill after recon_

## External Interfaces
- _fill after recon_

## Coupling / Hotspots
- _fill after recon_
"""

def render_impl_gate_checklist() -> str:
    return """# Implementation Gate Checklist

Implementation remains blocked until the following are explicit.

- [ ] nearest `AGENTS.md` reviewed and active rules recorded
- [ ] current system recon completed
- [ ] architecture intent documented in `Phytoritas.md`
- [ ] interface inventory captured
- [ ] hotspots and regression risks listed
- [ ] validation path identified
- [ ] first bounded phase defined
- [ ] Memento context/recall performed for this task
- [ ] recall results reviewed and feedback plan noted
"""

def render_adr_zero(project_name: str) -> str:
    return f"""# ADR-000: Adopt Recursive Architecture Workflow

## Status
Accepted

## Context
{project_name} is being handled with a recursive architecture workflow that separates:
- design artifacts in `docs/architecture/`
- runtime/control-plane state in `.rah/`
- long-term memory in Memento

## Decision
Adopt the harness-backed recursive architecture workflow as the default way to plan, refactor, and validate non-trivial work.

## Consequences
- setup / doctor / status / resume become explicit operator surfaces
- implementation stays blocked until architecture and validation gates pass
- Memento assists recall and reflection but does not override `AGENTS.md`
"""

def render_module_zero() -> str:
    return """# Module Spec: module-000-architecture-pipeline

## Responsibility
Describe the workflow module that owns:
- repository audit
- design artifact generation
- runtime sidecar updates
- Memento-aware resume packets
- implementation gate discipline

## Public Artifacts
- `docs/architecture/Phytoritas.md`
- `.rah/state/status.json`
- `.rah/state/gates.json`
- `.rah/state/memento_status.json`
- `.rah/plans/current_loop.md`
- `.rah/memory/wakeup.md`

## Failure / Recovery
If runtime state drifts from repository reality:
1. re-read files and scripts
2. repair `.rah/`
3. amend Memento only after facts are confirmed
"""

def render_activity_log(now: str, mode: str, scope: str, has_agents: bool, session_id: str) -> str:
    agents_note = (
        "Repo-local AGENTS.md detected; review and integrate before trusting non-trivial writes."
        if has_agents
        else "No repo-local AGENTS.md detected at bootstrap root."
    )
    return f"""# Harness Activity Log

## Boot Event
- time_utc: {now}
- mode: {mode}
- scope: {scope}
- event: bootstrap_scaffold_initialized
- session_id: {session_id}
- note: {agents_note}

## Later Updates
Append dated entries here instead of replacing history.
"""

def render_current_loop(restart_point: str, has_agents: bool, workspace: str, topic: str) -> str:
    agents_step = (
        "1. Read the nearest repo-local `AGENTS.md` and record repo-specific workflow constraints before broad writes."
        if has_agents
        else "1. Confirm whether a deeper repo-local `AGENTS.md` exists before broad write activity."
    )
    return f"""# Current Loop

## Earliest Restart Point
{restart_point}

## Read First
- `docs/architecture/Phytoritas.md`
- `docs/architecture/00_workspace_audit.md`
- `.rah/state/status.json`
- `.rah/state/gates.json`
- `.rah/memory/wakeup.md`

## Next Actions
{agents_step}
2. Run `python automation/rah.py doctor <repo-root>` (or `python automation/doctor_harness.py <repo-root>`).
3. Run `python automation/rah.py status <repo-root>`.
4. Load Memento context + narrow recall for workspace `{workspace}` / topic `{topic}`.
5. Perform current-system recon and update `00_workspace_audit.md`.
6. Keep implementation blocked until the checklist is honestly satisfied.
"""

def render_decision_register() -> str:
    return """# Decision Register

Use this file for local operating decisions that are not yet mature enough to become ADRs.

Append dated entries instead of replacing history.
"""

def render_agents_overlay() -> str:
    return """# Harness Overlay For Recursive Architecture Refactoring

Apply this as a durable overlay only if it does not conflict with a stronger repo-local `AGENTS.md`.

## Always-On Rules
- Read and follow the nearest applicable `AGENTS.md` before non-trivial writes.
- Prefer helper scripts over raw CLI calls when the repo already provides them.
- Treat `docs/architecture/` as the design artifact spine.
- Treat `.rah/` as the harness/runtime sidecar.
- Treat Memento as a memory plane, not as a policy source.
- Rules from repo-local `AGENTS.md` outrank Memento recall.
- Do not start broad implementation before the implementation gate passes.
- Repair the earliest failed gate before creating downstream artifacts.
- Keep status, gates, wakeup, and resume files honest enough for restart.
- Use read-only exploration before broad write activity.
- Use bounded inspect-style verification for shell output and test/status checks.
- Treat team/tmux style parallelism as optional and late.
"""

def render_wakeup(
    workspace: str,
    topic: str,
    session_id: str,
    case_id: str,
    branch_name: str | None,
    issue_number: int | None,
    agents_status: str,
) -> str:
    issue_value = str(issue_number) if issue_number is not None else "adhoc"
    branch_value = branch_name or "unknown"
    case_mode = "True" if case_id else "False"
    keywords = [workspace, topic, branch_value, f"issue-{issue_value}", "architecture-refactor"]
    keywords = [item for idx, item in enumerate(keywords) if item and item not in keywords[:idx]]
    keyword_text = ", ".join(f'"{k}"' for k in keywords)
    return f"""# Wakeup Packet

## Identity
- workspace: `{workspace}`
- topic: `{topic}`
- sessionId: `{session_id}`
- caseId: `{case_id}`
- issue: `{issue_value}`
- branch: `{branch_value}`

## Current State
- current_stage: `bootstrap-complete`
- implementation_gate: `blocked`
- agents_and_workflow_gate: `{agents_status}`

## Read First
1. nearest `AGENTS.md`
2. `docs/architecture/Phytoritas.md`
3. `.rah/state/status.json`
4. `.rah/state/gates.json`
5. `.rah/plans/current_loop.md`

## Memento Start Recipe
```python
context(types=["preference", "procedure", "error", "decision"], workspace="{workspace}", sessionId="{session_id}")
recall(
    keywords=[{keyword_text}],
    topic="{topic}",
    workspace="{workspace}",
    sessionId="{session_id}",
    caseMode={case_mode},
    depth="standard",
    contextText="bootstrap -> recon -> architecture intake"
)
```

## Feedback Reminder
If recall results are useful or misleading, record `tool_feedback()` and update `.rah/memory/memento_feedback.json`.
"""

def build_status(
    root: Path,
    scaffold_root: Path,
    profile: str,
    mode: str,
    scope: str,
    restart_point: str,
    has_agents: bool,
    now: str,
    workspace: str,
    topic: str,
    session_id: str,
    case_id: str,
    branch_name: str | None,
    issue_number: int | None,
) -> dict[str, Any]:
    return {
        "schema_version": STATUS_SCHEMA_VERSION,
        "skill": SKILL_NAME,
        "generated_at_utc": now,
        "mode": mode,
        "scope": scope,
        "root": str(root),
        "scaffold_root": relative_to_root(scaffold_root, root),
        "profile": profile,
        "current_stage": "bootstrap-complete",
        "phase": "planning",
        "last_completed_step": "scaffold_initialize",
        "doctor_state": "not-run",
        "implementation_gate": "blocked",
        "earliest_restart_point": restart_point,
        "next_recommended_action": "Run doctor and status, hydrate Memento context/recall, then perform current-system recon before any broad implementation.",
        "agents_file_detected": has_agents,
        "memento_workspace": workspace,
        "memento_topic": topic,
        "memento_session_id": session_id,
        "memento_case_id": case_id,
        "branch_name": branch_name,
        "issue_number": issue_number,
        "memento_last_context_at": None,
        "memento_last_recall_at": None,
        "memento_last_reflect_at": None,
        "last_search_event_id": None,
        "memory_freshness": "not-hydrated",
        "pending_feedback_count": 0,
        "wakeup_path": ".rah/memory/wakeup.md",
        "reflect_draft_path": ".rah/memory/memento_reflect_draft.json",
    }

def build_gates(
    root: Path,
    scaffold_root: Path,
    profile: str,
    restart_point: str,
    has_agents: bool,
    memento_configured: bool,
) -> dict[str, Any]:
    agents_status = "needs-review" if has_agents else "no-file-detected"
    agents_note = (
        "Repo-local AGENTS.md exists at the bootstrap root; review it before trusting non-trivial writes."
        if has_agents
        else "No repo-local AGENTS.md detected at the bootstrap root. A deeper AGENTS.md may still exist."
    )
    return {
        "schema_version": STATUS_SCHEMA_VERSION,
        "root_and_capability_gate": {
            "status": "pass",
            "evidence": [str(root), profile, relative_to_root(scaffold_root, root)],
        },
        "agents_and_workflow_gate": {
            "status": agents_status,
            "note": agents_note,
        },
        "scaffold_bootstrap_gate": {
            "status": "pass",
            "note": "Starter architecture scaffold created or preserved.",
        },
        "harness_state_gate": {
            "status": "pass",
            "note": "Starter .rah runtime sidecar created or preserved.",
        },
        "phytoritas_gate": {
            "status": "pass",
            "note": "Phytoritas starter artifact created or preserved.",
        },
        "artifact_audit_gate": {
            "status": "pending",
            "note": "Workspace audit and current-system recon still need real content.",
        },
        "memento_connectivity_gate": {
            "status": "pass" if memento_configured else "needs-review",
            "note": (
                "Memento-related config appears to exist locally; live connectivity is still unverified."
                if memento_configured
                else "No obvious local Memento config was detected. Review config if this repo should use memory-assisted resume."
            ),
        },
        "memento_recall_gate": {
            "status": "pending",
            "note": "Run context() and narrow recall() for the current workspace/topic before relying on memory-assisted resume.",
        },
        "memento_feedback_gate": {
            "status": "pending",
            "note": "Record tool_feedback() after meaningful recall results.",
        },
        "implementation_gate": {
            "status": "blocked",
            "note": "Implementation stays blocked until architecture, interfaces, seams, validation, regression protection, and memory-assisted recon are explicit.",
        },
        "earliest_restart_point": restart_point,
    }

def build_memento_status(
    workspace: str,
    topic: str,
    session_id: str,
    case_id: str,
    branch_name: str | None,
    issue_number: int | None,
    configured: bool,
    config_evidence: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": STATUS_SCHEMA_VERSION,
        "enabled": True,
        "configured": configured,
        "reachable": None,
        "connectivity": "configured-local-unverified" if configured else "not-detected",
        "workspace": workspace,
        "topic": topic,
        "session_id": session_id,
        "case_id": case_id,
        "branch_name": branch_name,
        "issue_number": issue_number,
        "last_context_at": None,
        "last_recall_at": None,
        "last_reflect_at": None,
        "last_search_event_id": None,
        "stale_results": False,
        "no_results_recently": False,
        "pending_feedback_count": 0,
        "active_errors": [],
        "config_evidence": config_evidence,
        "config_scope": None,
        "config_path": None,
        "server_name": None,
        "mcp_url": None,
        "health_url": None,
        "health_checked_at": None,
        "health_http_status": None,
        "health_payload": None,
        "status_note": "This helper cannot directly query MCP. Treat connectivity as configured/unverified until the runtime actually performs context/recall or doctor --live-memento.",
    }

def build_memento_context(workspace: str, session_id: str) -> dict[str, Any]:
    return {
        "workspace": workspace,
        "sessionId": session_id,
        "timestamp": None,
        "types": ["preference", "procedure", "error", "decision"],
        "fragment_counts": {},
        "top_fragments": [],
        "quality_notes": "Populate after the first successful context() call.",
    }

def build_memento_recall(workspace: str, topic: str, session_id: str, case_id: str) -> dict[str, Any]:
    return {
        "workspace": workspace,
        "topic": topic,
        "sessionId": session_id,
        "caseId": case_id,
        "timestamp": None,
        "query_mode": "narrow",
        "keywords": [workspace, topic, "architecture-refactor"],
        "contextText": "bootstrap -> recon -> architecture intake",
        "caseMode": True,
        "depth": "standard",
        "fragment_ids": [],
        "_searchEventId": None,
        "quality_notes": "Populate after the first task-scoped recall() call.",
    }

def build_memento_feedback() -> dict[str, Any]:
    return {
        "items": [],
        "note": "Append recall feedback entries here after meaningful memory use.",
    }

def build_memento_reflect_draft(root: Path, scaffold_root: Path) -> dict[str, Any]:
    return {
        "summary": [],
        "decisions": [],
        "errors_resolved": [],
        "new_procedures": [],
        "open_questions": [],
        "source_paths": [
            relative_to_root(scaffold_root / "Phytoritas.md", root),
            ".rah/logs/activity_log.md",
            ".rah/memory/decision_register.md",
            ".rah/plans/current_loop.md",
        ],
        "note": "Fill this from observed work, then use it as the source for reflect().",
    }

def build_case_map(
    workspace: str,
    topic: str,
    session_id: str,
    case_id: str,
    branch_name: str | None,
    issue_number: int | None,
    profile: str,
) -> dict[str, Any]:
    return {
        "workspace": workspace,
        "topic": topic,
        "sessionId": session_id,
        "caseId": case_id,
        "phase": "planning",
        "issue_number": issue_number,
        "branch": branch_name,
        "profile": profile,
    }

def marker_names(root: Path) -> list[str]:
    candidates = [
        ".git",
        "pyproject.toml",
        "requirements.txt",
        "package.json",
        "pnpm-workspace.yaml",
        "turbo.json",
        "go.mod",
        "Cargo.toml",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
    ]
    return [candidate for candidate in candidates if (root / candidate).exists()]

def ensure_dir(path: Path, summary: Summary) -> None:
    if path.exists():
        return
    path.mkdir(parents=True, exist_ok=True)
    summary.created_dirs.append(str(path))

def write_text(path: Path, content: str, force: bool, summary: Summary) -> None:
    if path.exists() and not force:
        summary.skipped_existing.append(str(path))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    summary.created_files.append(str(path))

def write_json(path: Path, payload: dict[str, Any], force: bool, summary: Summary) -> None:
    write_text(path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n", force, summary)

def ensure_gitignore_contract(root: Path, summary: Summary) -> None:
    result = gitignore_contract.apply_contract(root)
    if result.get("load_warning"):
        summary.warnings.append(result["load_warning"])
    if result["changed"]:
        summary.created_files.append(result["gitignore_path"])
    else:
        summary.skipped_existing.append(result["gitignore_path"])

def write_csv_header(path: Path, header: list[str], force: bool, summary: Summary) -> None:
    if path.exists() and not force:
        summary.skipped_existing.append(str(path))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
    summary.created_files.append(str(path))

def main() -> int:
    parser = _SuggestingArgumentParser(description="Bootstrap a repository into the recursive architecture harness.")
    parser.add_argument("repo_root", help="Path to the repository root")
    parser.add_argument("--project-name", help="Human-readable project name", default=None)
    parser.add_argument("--scope", choices=["project", "user"], default="project")
    parser.add_argument("--mode", choices=["auto-bootstrap", "assisted", "hybrid"], default="auto-bootstrap")
    parser.add_argument("--force", action="store_true", help="Overwrite existing scaffold starter files.")
    parser.add_argument("--memento-workspace", default=None)
    parser.add_argument("--memento-topic", default=None)
    parser.add_argument("--memento-session-id", default=None)
    parser.add_argument("--memento-case-id", default=None)
    parser.add_argument("--branch-name", default=None)
    parser.add_argument("--issue-number", type=int, default=None)
    parser.add_argument(
        "--gitignore-extra",
        action="append",
        default=None,
        metavar="PATTERN",
        help="Extra .gitignore pattern persisted to .rah/state/gitignore_contract.json (repeatable).",
    )
    args = parser.parse_args()

    root = Path(args.repo_root).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        print(json.dumps({"error": f"Missing repo root: {root}"}, ensure_ascii=False))
        return 2

    project_name = args.project_name or root.name
    profile = detect_profile(root)
    scaffold_root = choose_scaffold_root(root)
    summary = Summary(
        root=str(root),
        scaffold_root=str(scaffold_root),
        profile=profile,
        mode=args.mode,
        scope=args.scope,
    )

    for rel in ARCH_DIRS:
        ensure_dir(scaffold_root / rel, summary)
    for rel in HARNESS_DIRS:
        ensure_dir(root / rel, summary)
    if args.gitignore_extra:
        extra_result = gitignore_contract.add_rules(root, args.gitignore_extra, allow_broad=False, apply_after=False)
        for item in extra_result["rejected"]:
            summary.warnings.append(f"gitignore extra rejected: {item['pattern']} ({item['reason']})")
    ensure_gitignore_contract(root, summary)

    branch_name = args.branch_name or detect_git_branch(root)
    issue_number = args.issue_number if args.issue_number is not None else detect_issue_number(branch_name)
    workspace = derive_memento_workspace(root, args.memento_workspace)
    topic = derive_memento_topic(profile, args.memento_topic)
    session_id = derive_memento_session_id(workspace, issue_number, branch_name, args.memento_session_id)
    case_id = derive_memento_case_id(workspace, issue_number, branch_name, profile, args.memento_case_id)
    config_evidence = find_memento_config_evidence(root)
    memento_configured = bool(config_evidence)

    has_agents = (root / "AGENTS.md").exists()
    restart_point = "Stage -2. AGENTS And Workflow Intake Gate" if has_agents else "Stage -1. Doctor Surface"
    now = utc_now()

    text_files = {
        scaffold_root / "Phytoritas.md": render_phytoritas(
            project_name, profile, root, scaffold_root, args.mode, workspace, topic, session_id, case_id
        ),
        scaffold_root / "00_workspace_audit.md": render_workspace_audit(project_name),
        scaffold_root / "01_system_brief.md": render_system_brief(project_name, profile),
        scaffold_root / "gap_register.md": render_gap_register(),
        scaffold_root / "system/current_architecture_map.md": render_current_architecture_map(),
        scaffold_root / "implementation/implementation_gate_checklist.md": render_impl_gate_checklist(),
        scaffold_root / "architecture/adrs/ADR-000-adopt-recursive-architecture-workflow.md": render_adr_zero(project_name),
        scaffold_root / "architecture/module_specs/module-000-architecture-pipeline.md": render_module_zero(),
        root / ".rah/logs/activity_log.md": render_activity_log(now, args.mode, args.scope, has_agents, session_id),
        root / ".rah/plans/current_loop.md": render_current_loop(restart_point, has_agents, workspace, topic),
        root / ".rah/memory/decision_register.md": render_decision_register(),
        root / ".rah/runtime/AGENTS.overlay.md": render_agents_overlay(),
        root / ".rah/memory/wakeup.md": render_wakeup(workspace, topic, session_id, case_id, branch_name, issue_number, "needs-review" if has_agents else "no-file-detected"),
    }

    for path, content in text_files.items():
        write_text(path, content, args.force, summary)

    for rel, header in CSV_HEADERS.items():
        write_csv_header(scaffold_root / rel, header, args.force, summary)

    json_files = {
        root / ".rah/setup-scope.json": {
            "schema_version": STATUS_SCHEMA_VERSION,
            "skill": SKILL_NAME,
            "generated_at_utc": now,
            "scope": args.scope,
            "mode": args.mode,
            "root": str(root),
            "workspace": workspace,
            "topic": topic,
            "sessionId": session_id,
            "caseId": case_id,
        },
        root / ".rah/state/status.json": build_status(
            root, scaffold_root, profile, args.mode, args.scope, restart_point, has_agents, now, workspace, topic, session_id, case_id, branch_name, issue_number
        ),
        root / ".rah/state/gates.json": build_gates(
            root, scaffold_root, profile, restart_point, has_agents, memento_configured
        ),
        root / ".rah/state/memento_status.json": build_memento_status(
            workspace, topic, session_id, case_id, branch_name, issue_number, memento_configured, config_evidence
        ),
        root / ".rah/memory/memento_context.json": build_memento_context(workspace, session_id),
        root / ".rah/memory/memento_recall.json": build_memento_recall(workspace, topic, session_id, case_id),
        root / ".rah/memory/memento_feedback.json": build_memento_feedback(),
        root / ".rah/memory/memento_reflect_draft.json": build_memento_reflect_draft(root, scaffold_root),
        root / ".rah/memory/case_map.json": build_case_map(workspace, topic, session_id, case_id, branch_name, issue_number, profile),
    }

    for path, payload in json_files.items():
        write_json(path, payload, args.force, summary)

    bootstrap_report = summary.to_dict() | {
        "generated_at_utc": now,
        "markers": marker_names(root),
        "has_repo_local_agents": has_agents,
        "restart_point": restart_point,
        "memento_workspace": workspace,
        "memento_topic": topic,
        "memento_session_id": session_id,
        "memento_case_id": case_id,
        "memento_configured": memento_configured,
        "memento_config_evidence": config_evidence,
        "memento_files": MEMENTO_STATE_FILES,
        "gitignore_contract_path": str(gitignore_contract.contract_path(root)),
    }
    write_json(root / ".rah/state/bootstrap_summary.json", bootstrap_report, True, summary)

    print(summary.to_json())
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
