#!/usr/bin/env python3
"""Autopilot surface for source-driven RALPH runs.

This helper is intentionally a coordinator. It does not decide that work is
complete; RALPH, source coverage, closeout, review, and the external driver do.
"""
from __future__ import annotations

import argparse

try:
    from cli_suggestions import SuggestingArgumentParser as _SuggestingArgumentParser
except Exception:  # stale repo helper tree may predate cli_suggestions
    _SuggestingArgumentParser = argparse.ArgumentParser
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SOURCE_EXTENSIONS = {".pdf", ".md", ".markdown", ".txt", ".rst"}
SAFE_FLEET_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
CONTROL_SOURCE_BASENAMES = {"agents.md", "agents.override.md", "skill.md", "claude.md"}
SOURCE_WORD_RE = re.compile(
    r"(\.pdf\b|\.md\b|\.markdown\b|\.txt\b|\.rst\b|pdf|paper|markdown|pasted|stdin|source material|"
    r"document|spec|checklist|artifact note|issue body|pr comment|논문|문서|자료|붙여넣|전체\s*분석|처음부터\s*끝까지|빠짐없이)",
    re.IGNORECASE,
)
REQUIREMENT_WORD_RE = re.compile(
    r"(requirements?|acceptance|criterion|criteria|checklist|pipeline|must|shall|v\d+|R\d+|"
    r"요구사항|체크리스트|개발\s*파이프라인|파이프라인|반드시|구현|개선|마무리|전체|빠짐없이|끝까지)",
    re.IGNORECASE,
)
PATH_RE = re.compile(
    r"(?P<path>[A-Za-z]:[\\/][^\r\n\"'<>|]+?\.(?:pdf|md|markdown|txt|rst)|"
    r"(?:\.{1,2}[\\/])?[^\r\n\"'<>|]+[\\/][^\r\n\"'<>|]+?\.(?:pdf|md|markdown|txt|rst))",
    re.IGNORECASE,
)
# PRD activation is explicit-only and inspects the goal text alone; the word
# "PRD" inside a source document never triggers it. Longest phrases first so
# the reported trigger phrase is the most specific match.
PRD_TRIGGER_RES = [
    (re.compile(r"product\s+requirement\s+documents?"), "product requirement document"),
    (re.compile(r"product\s+requirements"), "product requirements"),
    (re.compile(r"generate\s+(?:an?\s+)?prd"), "generate prd"),
    (re.compile(r"prd\s*(?:[를을]\s*)?생성"), "prd 생성"),
    (re.compile(r"prd\s*기반"), "prd 기반"),
    (re.compile(r"기존\s*prd"), "기존 prd"),
    (re.compile(r"from\s+(?:the\s+|an?\s+)?prd"), "from prd"),
    (re.compile(r"prd\s*로\s*정리"), "prd로 정리"),
]
# Whitespace-tolerant: Korean routinely attaches particles/verbs without a
# space ("PRD없이", "PRD만들지 말고"); opt-out must still win over the bare word.
PRD_OPT_OUT_RES = [
    (re.compile(r"prd\s*없이"), "prd 없이"),
    (re.compile(r"prd\s*(?:[를은는을]\s*)?만들\s*지\s*(?:말|않)"), "prd 만들지 말고"),
    (re.compile(r"prd\s*(?:[를은는을]\s*)?생성\s*하\s*지\s*(?:말|않)"), "prd 생성하지 말고"),
    (re.compile(r"skip\s+prd"), "skip prd"),
    (re.compile(r"without\s+(?:a\s+)?prd"), "without prd"),
    (re.compile(r"\bno\s+prd"), "no prd"),
    (re.compile(r"--prd-mode\s+off"), "--prd-mode off"),
]
# A bare operator word may activate PRD, but a path component such as
# docs/prd/spec.md is source context rather than an execution directive.
PRD_WORD_RE = re.compile(r"(?<![a-z0-9/\\])prd(?![a-z0-9/\\])")
FLEET_OPT_OUT_RES = [
    (re.compile(r"fleet\s*없이"), "fleet 없이"),
    (re.compile(r"플릿\s*없이"), "플릿 없이"),
    (re.compile(r"(?:no|without)\s+fleet"), "no fleet"),
    (re.compile(r"(?:do\s+not|don'?t)\s+use\s+fleet"), "do not use fleet"),
    (re.compile(r"skip\s+fleet"), "skip fleet"),
    (re.compile(r"fleet\s*(?:을|를)?\s*(?:사용|실행|구동)\s*하\s*지\s*(?:마|말|않)"), "fleet 사용하지 마"),
    (re.compile(r"--fleet-mode\s+off"), "--fleet-mode off"),
]
FLEET_TRIGGER_RES = [
    (re.compile(r"(?<![a-z0-9])fleet(?![a-z0-9])"), "fleet"),
    (re.compile(r"플릿"), "플릿"),
    (re.compile(r"병렬\s*(?:로\s*)?(?:구현|개발)"), "병렬 구현"),
    (re.compile(r"병렬\s*(?:worker|워커)"), "병렬 worker"),
    (re.compile(r"parallel(?:ize|ized|izing)?[\s-]+implementation"), "parallel implementation"),
    (re.compile(r"implement(?:ation|ing)?\s+(?:it\s+)?in\s+parallel"), "implement in parallel"),
]
FLEET_MONITOR_RES = [
    (re.compile(r"(?:worker|워커).*(?:대화|진행|상태).*(?:모니터|관찰|보여)"), "worker 대화 모니터링"),
    (re.compile(r"(?:모니터|관찰).*(?:worker|워커).*(?:대화|진행|상태)"), "worker 대화 모니터링"),
    (re.compile(r"(?:monitor|watch|observe).*(?:fleet|parallel\s+workers?|worker\s+conversation)"), "monitor fleet workers"),
    (re.compile(r"(?:fleet|parallel\s+workers?|worker\s+conversation).*(?:monitor|watch|observe)"), "monitor fleet workers"),
]
SESSION_BRAIN_RES = [
    (re.compile(r"검토(?:는|를)?\s*네가\s*직접"), "검토는 네가 직접"),
    (re.compile(r"세션(?:인|이|은|는)?\s*네가\s*직접\s*검토"), "세션인 네가 직접 검토"),
    (re.compile(r"calling\s+session(?:\s+(?:must|should|will|does|to))?\s+review"), "calling session review"),
    (re.compile(r"review(?:ed|ing)?\s+by\s+the\s+calling\s+session"), "review by the calling session"),
]
DRIVE_BRAIN_RES = [
    (re.compile(r"drive\s*(?:사이클|cycle)s?(?:이|가|은|는)?\s*(?:두뇌|brain)"), "drive cycle is brain"),
    (re.compile(r"drive\s+cycles?\s+(?:is|are|acts?\s+as)\s+(?:the\s+)?brain"), "drive cycle is brain"),
]
SCIENTIFIC_FLEET_RES = [
    (re.compile(r"수치\s*계약"), "수치 계약"),
    (re.compile(r"numeric(?:al)?\s+contract"), "numerical contract"),
    (re.compile(r"단위.*(?:tolerance|허용\s*오차).*보존식", re.DOTALL), "units/tolerance/conservation"),
    (re.compile(r"(?:seed|시드).*재현.*(?:nan|경계|극한|보존)", re.DOTALL), "seed reproducibility checks"),
]
SCIENTIFIC_FLEET_CONTRACT = (
    "Apply the numerical contract from the source requirements and active AGENTS.md: encode units, sign, "
    "tolerance, and conservation rules explicitly in code and tests; fix stochastic seeds for reproducibility; "
    "and verify boundary/extreme cases plus NaN handling. Do not invent numeric requirements not present in "
    "the authoritative source."
)
# PRD-only routing: "generate the PRD and stop" must never fall through to
# ralph/fleet/drive. Like the other routers here, detection reads the goal text
# only; explicit flags (--prd-only / --fleet-mode) take precedence via the
# conflict checks in main().
PRD_ONLY_RES = [
    (re.compile(r"prd\s*(?:생성|작성|projection|프로젝션)?\s*까지\s*만"), "prd 생성까지만"),
    (re.compile(r"prd\s*만\s*(?:먼저\s*)?(?:생성|작성|만들|뽑|emit)"), "prd만 생성"),
    (re.compile(r"prd\s*(?:생성|작성)\s*만\b"), "prd 생성만"),
    (re.compile(r"stop\s+after\s+(?:the\s+)?prd"), "stop after prd"),
    (re.compile(r"prd[\s-]?only"), "prd-only"),
    (re.compile(r"only\s+(?:generate|emit|produce|create)\s+(?:the\s+|a\s+)?prd"), "only generate prd"),
]
# Implementation-stop wording: with an active PRD projection it promotes the
# run to PRD-only; alone it forces --no-drive (fail safe in the dangerous
# direction — never implement against explicit "do not implement").
STOP_IMPLEMENTATION_RES = [
    (re.compile(r"구현\s*(?:[은는을이])?\s*(?:아직\s*)?(?:시작\s*)?하\s*지\s*(?:마|말|않)"), "구현은 시작하지 마"),
    (re.compile(r"구현\s*(?:은|는)?\s*(?:시작\s*)?(?:보류|중단|금지)"), "구현 보류"),
    (re.compile(r"구현\s*없이"), "구현 없이"),
    (re.compile(r"do\s+not\s+(?:start\s+)?implement"), "do not implement"),
    (re.compile(r"don'?t\s+(?:start\s+)?implement"), "don't implement"),
    (re.compile(r"without\s+implement(?:ing|ation)"), "without implementation"),
    (re.compile(r"\bno\s+implementation\b"), "no implementation"),
]


def detect_fleet_opt_out(goal: str) -> str | None:
    lower = (goal or "").lower()
    for pattern, canonical in FLEET_OPT_OUT_RES:
        if pattern.search(lower):
            return canonical
    return None


def detect_fleet_request(goal: str) -> dict[str, Any]:
    lower = (goal or "").lower()
    opt_out = detect_fleet_opt_out(lower)
    if opt_out:
        return {"triggered": False, "trigger_phrase": None, "opt_out_phrase": opt_out}
    for pattern, canonical in FLEET_TRIGGER_RES:
        if pattern.search(lower):
            return {"triggered": True, "trigger_phrase": canonical, "opt_out_phrase": None}
    return {"triggered": False, "trigger_phrase": None, "opt_out_phrase": None}


def detect_brain_request(goal: str) -> dict[str, Any]:
    lower = (goal or "").lower()
    # Calling-session review is the more specific safety contract when both
    # styles happen to appear in one directive.
    for pattern, canonical in SESSION_BRAIN_RES:
        if pattern.search(lower):
            return {"brain": "session", "trigger_phrase": canonical}
    for pattern, canonical in DRIVE_BRAIN_RES:
        if pattern.search(lower):
            return {"brain": "drive", "trigger_phrase": canonical}
    return {"brain": None, "trigger_phrase": None}


def detect_fleet_monitor_request(goal: str) -> str | None:
    lower = (goal or "").lower()
    for pattern, canonical in FLEET_MONITOR_RES:
        if pattern.search(lower):
            return canonical
    return None


def detect_scientific_fleet_request(goal: str) -> str | None:
    lower = (goal or "").lower()
    for pattern, canonical in SCIENTIFIC_FLEET_RES:
        if pattern.search(lower):
            return canonical
    return None


def resolve_fleet_plan(args: argparse.Namespace, goal: str) -> dict[str, Any]:
    detection = detect_fleet_request(goal)
    brain_detection = detect_brain_request(goal)
    monitor_detection = detect_fleet_monitor_request(goal)
    explicit_mode = args.fleet_mode
    explicit_brain = args.brain
    explicit_monitor = args.fleet_monitor

    if explicit_mode is not None:
        mode = explicit_mode
        mode_source = "cli"
    elif detection["opt_out_phrase"]:
        mode = "off"
        mode_source = "goal-opt-out"
    elif detection["triggered"] or monitor_detection:
        mode = "implement"
        mode_source = "goal-inference"
    else:
        mode = "off"
        mode_source = "default"

    monitor = bool(explicit_monitor) if explicit_monitor is not None else bool(monitor_detection)
    monitor_source = "cli" if explicit_monitor is not None else ("goal-inference" if monitor_detection else "default")
    if mode == "off" and mode_source == "goal-opt-out" and explicit_monitor is None:
        monitor = False
        monitor_source = "goal-opt-out"

    if explicit_brain is not None:
        brain = explicit_brain
        brain_source = "cli"
    elif monitor and mode != "off":
        brain = "session"
        brain_source = "monitor-inference"
    elif brain_detection["brain"]:
        brain = brain_detection["brain"]
        brain_source = "goal-inference"
    else:
        brain = "drive"
        brain_source = "default"

    args.fleet_mode = mode
    args.brain = brain
    args.fleet_monitor = monitor
    active = mode != "off"
    return {
        "mode": mode,
        "brain": brain if active else None,
        "trigger_phrase": detection["trigger_phrase"],
        "opt_out_phrase": detection["opt_out_phrase"] if mode_source == "goal-opt-out" else None,
        "detected_opt_out_phrase": detection["opt_out_phrase"],
        "mode_inferred": mode_source == "goal-inference",
        "mode_source": mode_source,
        "explicit_mode": explicit_mode,
        "suppressed_by_prd_only": None,
        "brain_trigger_phrase": brain_detection["trigger_phrase"],
        "brain_inferred": active and brain_source in {"goal-inference", "monitor-inference"},
        "brain_source": brain_source if active else "inactive",
        "explicit_brain": explicit_brain,
        "monitor": monitor if active else False,
        "monitor_trigger_phrase": monitor_detection,
        "monitor_source": monitor_source if active else "inactive",
        "explicit_monitor": explicit_monitor,
    }


def detect_control_directive(goal: str) -> dict[str, Any]:
    """Detect the legacy standalone continuation prompts, not arbitrary goals.

    The intentionally narrow signature requires both instruction files plus a
    durable drive/terminal contract. Operators can force the same behavior with
    --resume-current-goal when their wording does not match this signature.
    """
    lower = (goal or "").lower()
    markers = {
        "agents": "agents.md" in lower or "agents.override.md" in lower,
        "skill": "skill.md" in lower,
        "memento": "memento" in lower,
        "drive": "drive" in lower,
        "terminal": "terminal" in lower or "done/blocked/cancelled/failed" in lower,
        "ralph": "ralph" in lower,
    }
    detected = bool(
        markers["agents"]
        and markers["skill"]
        and markers["drive"]
        and markers["terminal"]
        and (markers["memento"] or markers["ralph"])
    )
    return {"detected": detected, "markers": [name for name, present in markers.items() if present]}


def detect_prd_only_request(goal: str) -> dict[str, Any]:
    lower = (goal or "").lower()
    for pattern, canonical in PRD_ONLY_RES:
        if pattern.search(lower):
            return {"prd_only": True, "phrase": canonical, "stop_phrase": None}
    for pattern, canonical in STOP_IMPLEMENTATION_RES:
        if pattern.search(lower):
            return {"prd_only": False, "phrase": None, "stop_phrase": canonical}
    return {"prd_only": False, "phrase": None, "stop_phrase": None}


def build_fleet_dispatch_command(repo_root: Path, args: argparse.Namespace) -> list[str]:
    command = [
        sys.executable,
        "-B",
        str(automation_dir() / "fleet_harness.py"),
        str(repo_root),
        "dispatch",
        "--json",
    ]
    if args.fleet_run_id:
        command.extend(["--run-id", args.fleet_run_id])
    if args.fleet_mode == "review":
        command.extend(["--template", "review"])
    if args.fleet_test_cmd:
        command.extend(["--test-cmd", args.fleet_test_cmd])
    if args.fleet_worker_contract:
        command.extend(["--worker-contract", args.fleet_worker_contract])
    if args.dangerously_bypass_approvals_and_sandbox:
        command.append("--dangerously-bypass-approvals-and-sandbox")
    return command


def build_monitored_fleet_job_command(
    repo_root: Path,
    run_id: str,
    fleet_dispatch_command: list[str],
) -> list[str]:
    """Run synchronous Fleet through RAH's existing detached job supervisor."""
    return [
        sys.executable,
        "-B",
        str(automation_dir() / "long_job_harness.py"),
        str(repo_root),
        "launch",
        "--name",
        f"Fleet monitored dispatch {run_id}",
        "--kind",
        "fleet-dispatch",
        "--json",
        "--",
        *fleet_dispatch_command,
    ]


def detect_prd_request(goal: str) -> dict[str, Any]:
    lower = (goal or "").lower()
    for pattern, canonical in PRD_OPT_OUT_RES:
        if pattern.search(lower):
            return {"triggered": False, "opt_out": True, "phrase": canonical}
    for pattern, canonical in PRD_TRIGGER_RES:
        if pattern.search(lower):
            return {"triggered": True, "opt_out": False, "phrase": canonical}
    if PRD_WORD_RE.search(lower):
        return {"triggered": True, "opt_out": False, "phrase": "prd"}
    return {"triggered": False, "opt_out": False, "phrase": None}


def resolve_prd_plan(args: argparse.Namespace, goal: str) -> dict[str, Any]:
    """Apply the PRD precedence contract: off > explicit flags > mode > auto."""
    plan = {
        "active": False,
        "mode": None,
        "from_path": args.from_prd,
        "trigger_phrase": None,
        "opt_out_phrase": None,
        "error": None,
    }
    if args.prd_mode == "off":
        if args.emit_prd or args.from_prd:
            plan["error"] = "--prd-mode off conflicts with --emit-prd/--from-prd."
        return plan
    if args.from_prd:
        plan.update({"active": True, "mode": "from-prd"})
        return plan
    if args.emit_prd or args.prd_mode == "emit":
        plan.update({"active": True, "mode": "emit"})
        return plan
    if args.prd_mode == "from-prd":
        plan["error"] = "--prd-mode from-prd requires --from-prd <path>."
        return plan
    detection = detect_prd_request(goal)
    if detection["opt_out"]:
        plan["opt_out_phrase"] = detection["phrase"]
        return plan
    if detection["triggered"]:
        plan.update({"active": True, "mode": "emit", "trigger_phrase": detection["phrase"]})
    return plan


def build_prd_commands(
    repo_root: Path, args: argparse.Namespace, plan: dict[str, Any], *, include_status: bool = False
) -> list[list[str]]:
    script = str(automation_dir() / "prd_projection_harness.py")
    commands = [[sys.executable, "-B", script, str(repo_root), "atoms", "--json"]]
    if plan.get("mode") == "from-prd":
        commands.append(
            [sys.executable, "-B", script, str(repo_root), "ingest", "--source", str(plan.get("from_path")), "--json"]
        )
    else:
        commands.append([sys.executable, "-B", script, str(repo_root), "emit", "--task", args.goal, "--json"])
    commands.append([sys.executable, "-B", script, str(repo_root), "validate", "--json"])
    if include_status:
        commands.append([sys.executable, "-B", script, str(repo_root), "status", "--json"])
    return commands


def prd_command_surface(command: list[str]) -> str:
    # [python, -B, prd_projection_harness.py, <repo-root>, <surface>, ...]
    return command[4] if len(command) > 4 else ""


def build_prd_only_summary(repo_root: Path, prd_results: list[dict[str, Any]], gate_ready: bool) -> dict[str, Any]:
    status_payload: dict[str, Any] | None = None
    for outcome in reversed(prd_results):
        parsed = outcome.get("stdout_json")
        if isinstance(parsed, dict) and parsed.get("operation") == "status":
            status_payload = parsed
            break
    audit = read_json(ralph_root(repo_root) / "prd_mapping_audit.json") or {}
    prd_payload = read_json(ralph_root(repo_root) / "prd.json") or {}
    stories = status_payload.get("stories") if isinstance(status_payload, dict) else None
    if not isinstance(stories, list):
        stories = [
            {"id": story.get("id"), "title": story.get("title"), "epic": story.get("epic")}
            for story in (prd_payload.get("stories") or [])
            if isinstance(story, dict)
        ]
    epics: list[str] = []
    for story in stories:
        epic = str((story or {}).get("epic") or "").strip()
        if epic and epic not in epics:
            epics.append(epic)
    return {
        "prd_md_path": ".rah/ralph/prd.md",
        "prd_json_path": ".rah/ralph/prd.json",
        "audit_path": ".rah/ralph/prd_mapping_audit.json",
        "gate_ready": gate_ready,
        "audit_ready": audit.get("audit_ready"),
        "prd_ready": audit.get("prd_ready"),
        "needs_review": audit.get("needs_review"),
        "review_reasons": audit.get("review_reasons") or [],
        "story_count": audit.get("story_count", len(stories)),
        "epics": epics,
        "stories": stories,
        "row_coverage": {
            "mapped": audit.get("mapped_source_row_count"),
            "total": audit.get("source_row_count"),
            "unmapped_ids": audit.get("unmapped_source_row_ids") or [],
        },
        "atom_coverage": {
            "mapped_required": audit.get("mapped_required_atom_count"),
            "required_total": audit.get("required_atom_count"),
            "unmapped_required_ids": audit.get("unmapped_required_atom_ids") or [],
        },
        "waiver_ratio": audit.get("waiver_ratio"),
        "stale": audit.get("stale"),
    }


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def automation_dir() -> Path:
    return Path(__file__).resolve().parent


def ralph_root(repo_root: Path) -> Path:
    return repo_root / ".rah" / "ralph"


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except OSError:
            pass


def wait_for_monitored_fleet_readiness(
    repo_root: Path,
    run_id: str,
    job_id: str | None,
    *,
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    """Handshake detached launch with Fleet state or a terminal job result."""
    if not SAFE_FLEET_RUN_ID_RE.fullmatch(run_id):
        return {
            "status": "failed",
            "reason": "monitored Fleet run id is not a safe path component",
            "returncode": 2,
        }
    if not job_id:
        return {
            "status": "failed",
            "reason": "job launch returned no job_id",
            "returncode": 2,
        }
    fleet_state_path = repo_root / ".rah" / "fleet" / "runs" / run_id / "state.json"
    job_status_path = repo_root / ".rah" / "jobs" / job_id / "status.json"
    terminal = {"succeeded", "failed", "cancelled", "lost", "orphaned"}
    deadline = time.monotonic() + max(0.1, timeout_seconds)
    while True:
        fleet_state = read_json(fleet_state_path)
        job_state = read_json(job_status_path)
        job_status = str((job_state or {}).get("status") or "") if isinstance(job_state, dict) else ""
        if job_status in terminal and job_status != "succeeded":
            exit_code = int((job_state or {}).get("exit_code") or 0)
            return {
                "status": "failed",
                "run_id": None,
                "job_id": job_id,
                "returncode": exit_code or 2,
                "reason": str((job_state or {}).get("failure_reason") or f"job terminal status: {job_status}"),
            }
        state_is_current = False
        if isinstance(fleet_state, dict) and isinstance(job_state, dict):
            supervisor = read_json(fleet_state_path.parent / "supervisor.json")
            supervisor_job = str((supervisor or {}).get("job_id") or "") if isinstance(supervisor, dict) else ""
            state_created = str(fleet_state.get("created_at_utc") or "")
            job_created = str(job_state.get("created_at_utc") or job_state.get("launched_at_utc") or "")
            state_is_current = not supervisor_job or supervisor_job == job_id
            if state_created and job_created and state_created < job_created:
                state_is_current = False
        if isinstance(fleet_state, dict) and state_is_current:
            supervisor = {
                "schema_version": 1,
                "job_id": job_id,
                "fleet_run_id": run_id,
                "kind": "fleet-dispatch",
                "linked_at_utc": utc_now(),
            }
            write_json_atomic(fleet_state_path.parent / "supervisor.json", supervisor)
            return {
                "status": "ready",
                "run_id": run_id,
                "job_id": job_id,
                "fleet_status": fleet_state.get("status"),
            }
        if job_status in terminal:
            exit_code = int((job_state or {}).get("exit_code") or 0) if isinstance(job_state, dict) else 2
            if job_status == "succeeded" and exit_code == 0:
                stdout_value = str((job_state or {}).get("stdout_path") or "")
                stdout_path = repo_root / stdout_value if stdout_value else None
                child_payload = read_json(stdout_path) if stdout_path and stdout_path.is_file() else None
                return {
                    "status": "noop" if isinstance(child_payload, dict) and child_payload.get("run_id") is None else "failed",
                    "run_id": None,
                    "job_id": job_id,
                    "returncode": 0 if isinstance(child_payload, dict) and child_payload.get("run_id") is None else 2,
                    "reason": (
                        str(child_payload.get("note") or "nothing to dispatch")
                        if isinstance(child_payload, dict) and child_payload.get("run_id") is None
                        else "Fleet job succeeded without creating the requested run state"
                    ),
                }
        if time.monotonic() >= deadline:
            return {
                "status": "pending",
                "run_id": run_id,
                "job_id": job_id,
                "reason": "Fleet state handshake is still pending; inspect the durable job before monitoring the run.",
            }
        time.sleep(0.1)


def run_command(command: list[str], *, input_text: str | None = None) -> dict[str, Any]:
    # Children must emit UTF-8 on their pipes: without this, a stock Korean
    # Windows install writes cp949 and the strict UTF-8 decode below crashes.
    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    completed = subprocess.run(
        command,
        input=input_text,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    parsed: Any = None
    if completed.stdout.strip():
        try:
            parsed = json.loads(completed.stdout)
        except json.JSONDecodeError:
            parsed = None
    # When stdout parsed cleanly, stdout_json carries the full structured
    # result; the raw-string copy is pure duplication (each child's payload is
    # already multi-KB), so drop it. On parse failure the raw tail is the only
    # diagnostic, so keep it.
    return {
        "command": command,
        "returncode": int(completed.returncode),
        "stdout": None if parsed is not None else completed.stdout[-8000:],
        "stderr": completed.stderr[-8000:],
        "stdout_json": parsed,
    }


def _summarize_stdout_json(parsed: Any) -> Any:
    """Curated one-level summary of a child's structured stdout for the final
    aggregated print — the full object already lives in the child's own log.
    Unknown shapes fall back to the intersection of a few common keys."""
    if not isinstance(parsed, dict):
        return parsed
    ralph_state = parsed.get("ralph_state")
    if isinstance(ralph_state, dict):
        readiness = ralph_state.get("completion_readiness")
        return {
            "status": ralph_state.get("status"),
            "goal_id": ralph_state.get("goal_id"),
            "completion_ready": readiness.get("ready") if isinstance(readiness, dict) else None,
        }
    summary = {key: parsed.get(key) for key in ("run_id", "operation", "status", "ready", "error") if key in parsed}
    job = parsed.get("job")
    if isinstance(job, dict) and job.get("job_id"):
        summary["job_id"] = job.get("job_id")
    return summary or {"keys": sorted(parsed.keys())[:8]}


def _compact_result_entry(entry: Any) -> Any:
    if isinstance(entry, list):
        return [_compact_result_entry(item) for item in entry]
    if not isinstance(entry, dict):
        return entry
    if "skipped" in entry:
        return dict(entry)  # skipped markers are pinned by callers/tests — verbatim
    compact: dict[str, Any] = {}
    for key in ("command", "returncode", "reason", "error", "readiness"):
        if key in entry:
            compact[key] = entry[key]
    if "stdout_json" in entry:
        compact["summary"] = _summarize_stdout_json(entry["stdout_json"])
    if entry.get("returncode") not in (0, None):
        if entry.get("stderr"):
            compact["stderr"] = str(entry["stderr"])[-2000:]
        if entry.get("stdout"):
            compact["stdout"] = str(entry["stdout"])[-2000:]
    return compact


def compact_results_for_print(results: dict[str, Any]) -> dict[str, Any]:
    """Success-path view of the aggregated child results: each child's raw and
    full-structured stdout is collapsed to a small summary so the driving agent
    does not re-read every child's multi-KB payload. Early-return failure prints
    keep the full ``results`` for diagnostics."""
    return {key: _compact_result_entry(value) for key, value in results.items()}


def clean_candidate(value: str) -> str:
    cleaned = value.strip().strip("`\"'")
    while cleaned and cleaned[-1] in ".,;:)]}":
        cleaned = cleaned[:-1].rstrip()
    return cleaned


def candidate_path_variants(value: str) -> list[str]:
    cleaned = clean_candidate(value)
    variants = [cleaned] if cleaned else []
    drive_match = re.search(r"[A-Za-z]:[\\/].*", cleaned)
    if drive_match:
        variants.append(clean_candidate(drive_match.group(0)))
    relative_match = re.search(r"(?:\.{1,2}[\\/]).*", cleaned)
    if relative_match:
        variants.append(clean_candidate(relative_match.group(0)))
    # POSIX absolute recovery: the anchor keeps a relative path's "/suffix" (e.g.
    # /pipeline.md inside docs/pipeline.md) from being promoted to an absolute path.
    posix_match = re.search(r"(?:^|(?<=\s))/[^\r\n\"'<>|]+", cleaned)
    if posix_match:
        variants.append(clean_candidate(posix_match.group(0)))
    # Leading-word strip: PATH_RE may swallow words before a path; only variants
    # that actually resolve to files survive resolve_source(), so extras are inert.
    tokens = cleaned.split(" ")
    for start in range(1, len(tokens)):
        variants.append(clean_candidate(" ".join(tokens[start:])))
    unique: list[str] = []
    seen: set[str] = set()
    for variant in variants:
        key = variant.lower()
        if variant and key not in seen:
            seen.add(key)
            unique.append(variant)
    return unique


def resolve_source(value: str, repo_root: Path) -> Path | None:
    for variant in candidate_path_variants(value):
        candidate = Path(variant).expanduser()
        # The CLI contract defines relative --source values against repo_root.
        # Looking in the caller's cwd first can silently select an unrelated
        # control file when both locations contain (for example) AGENTS.md.
        candidates = [candidate] if candidate.is_absolute() else [repo_root / candidate]
        for path in candidates:
            try:
                resolved = path.resolve()
            except OSError:
                continue
            if resolved.exists() and resolved.is_file() and resolved.suffix.lower() in SOURCE_EXTENSIONS:
                return resolved
    return None


def collect_sources(goal: str, repo_root: Path, explicit_sources: list[str]) -> tuple[list[Path], list[str]]:
    seen: set[str] = set()
    sources: list[Path] = []
    unresolved_explicit: list[str] = []
    for raw in explicit_sources:
        resolved = resolve_source(raw, repo_root)
        if resolved is None:
            unresolved_explicit.append(raw)
            continue
        key = str(resolved).lower()
        if key not in seen:
            seen.add(key)
            sources.append(resolved)
    for match in PATH_RE.finditer(goal or ""):
        resolved = resolve_source(match.group("path"), repo_root)
        if resolved is None or resolved.name.lower() in CONTROL_SOURCE_BASENAMES:
            continue
        key = str(resolved).lower()
        if key not in seen:
            seen.add(key)
            sources.append(resolved)
    return sources, unresolved_explicit


def infer_sources(goal: str, repo_root: Path, explicit_sources: list[str]) -> list[Path]:
    """Compatibility wrapper for callers that only need successfully resolved sources."""
    sources, _ = collect_sources(goal, repo_root, explicit_sources)
    return sources


def retained_ralph_goal(repo_root: Path) -> str | None:
    ralph = ralph_root(repo_root)
    for path in (ralph / "goal.json", ralph / "loop_state.json"):
        payload = read_json(path)
        if isinstance(payload, dict) and str(payload.get("goal") or "").strip():
            return str(payload["goal"]).strip()
    return None


def merge_extra_prompt(existing: str | None, directive: str) -> str:
    directive_block = "Operator continuation directive (routing/control only; do not replace the retained goal):\n" + directive.strip()
    if existing and existing.strip():
        return "\n\n".join([existing.strip(), directive_block])
    return directive_block


def infer_mode(goal: str, sources: list[Path], requested_mode: str) -> str:
    if requested_mode != "auto":
        return requested_mode
    lower_goal = (goal or "").lower()
    if any(source.suffix.lower() == ".pdf" for source in sources) or any(token in lower_goal for token in ["논문", "paper"]):
        return "paper"
    if any(token in lower_goal for token in ["구현", "implement", "개발", "refactor", "fix"]):
        return "implementation"
    if any(token in lower_goal for token in ["synthesis", "종합", "비교"]):
        return "synthesis"
    if any(token in lower_goal for token in ["작성", "writing", "draft"]):
        return "writing"
    if any(token in lower_goal for token in ["요약", "summary", "정리"]):
        return "summary"
    return "analysis"


def long_goal_text(goal: str) -> bool:
    text = goal or ""
    nonempty_lines = [line for line in text.splitlines() if line.strip()]
    bullet_like_lines = [
        line
        for line in nonempty_lines
        if re.match(r"\s*(?:[-*+]|\d+[.)]|R\d+[:.)-])\s+", line, re.IGNORECASE)
    ]
    keyword_hit = bool(REQUIREMENT_WORD_RE.search(text))
    return (
        len(text) >= 1200
        or len(nonempty_lines) >= 10
        or len(bullet_like_lines) >= 4
        or (keyword_hit and (len(text) >= 300 or len(nonempty_lines) >= 4))
    )


def should_ingest_goal_as_source(goal: str, sources: list[Path], stdin_requested: bool, mode: str) -> bool:
    if mode == "off":
        return False
    if sources or stdin_requested:
        return False
    if mode == "always":
        return True
    return long_goal_text(goal)


def source_required(
    goal: str,
    sources: list[Path],
    stdin_requested: bool,
    force_required: bool,
    allow_without: bool,
    goal_as_source: bool = False,
) -> bool:
    if allow_without:
        return False
    return bool(force_required or sources or stdin_requested or goal_as_source or SOURCE_WORD_RE.search(goal or ""))


def build_source_ingest_command(
    repo_root: Path,
    sources: list[Path],
    mode: str,
    args: argparse.Namespace,
    *,
    stdin_requested: bool,
    stdin_label: str,
) -> list[str] | None:
    if not sources and not stdin_requested:
        return None
    command = [
        sys.executable,
        "-B",
        str(automation_dir() / "source_coverage_harness.py"),
        str(repo_root),
        "ingest",
        "--mode",
        mode,
        "--task",
        args.goal,
        "--json",
    ]
    for source in sources:
        command.extend(["--source", str(source)])
    if stdin_requested:
        command.append("--stdin")
        command.extend(["--label", stdin_label])
    if args.redact_excerpts_for_tracking:
        command.append("--redact-excerpts-for-tracking")
    if args.force_source_ingest:
        command.append("--force")
    if args.ocr:
        command.extend(["--ocr", args.ocr])
    if args.ocr_lang:
        command.extend(["--ocr-lang", args.ocr_lang])
    if args.ocr_tessdata:
        command.extend(["--ocr-tessdata", args.ocr_tessdata])
    if args.ocr_max_pages is not None:
        command.extend(["--ocr-max-pages", str(args.ocr_max_pages)])
    return command


def build_ralph_command(
    repo_root: Path, args: argparse.Namespace, require_source: bool, *, require_prd: bool = False
) -> list[str]:
    command = [
        sys.executable,
        "-B",
        str(automation_dir() / "ralph_harness.py"),
        str(repo_root),
        "--goal",
        args.goal,
        "--completion-mode",
        args.completion_mode,
        "--max-iterations",
        str(args.max_iterations),
    ]
    if require_source:
        command.append("--require-source-coverage")
    elif args.allow_without_source_coverage:
        command.append("--no-require-source-coverage")
    if require_prd:
        command.append("--require-prd")
    if args.reset:
        command.append("--reset")
    if args.replace_terminal_goal:
        command.append("--replace-terminal-goal")
    if args.json:
        command.append("--json")
    return command


def build_drive_command(
    repo_root: Path,
    args: argparse.Namespace,
    *,
    prd_active: bool = False,
    fleet_pending: bool = False,
    fleet_opt_out: str | None = None,
) -> list[str]:
    autopilot_prompt = (
        "Autopilot mode is active. A no-response, pending review, active job, or cycle timeout is not completion and not a fallback trigger. "
        "If reviewer verification is pending and a reviewer agent/thread exists, call wait_agent with the maximum practical timeout and keep waiting/retrying until approval or rejection arrives. "
        "If reviewer subagent spawning explicitly fails because a thread or agent limit is reached, record --review-fallback with the exact failure reason, "
        "perform the main-thread review, rerun validation, then approve only with concrete review evidence. "
        "If source coverage is incomplete, process source rows before broad closeout."
    )
    if prd_active:
        autopilot_prompt += (
            " A PRD projection exists at .rah/ralph/prd.json. Treat it only as a planning view. "
            "Completion authority remains source_requirement_coverage.json and RALPH readiness. "
            "Do not mark any PRD story complete directly. Work through source coverage rows. "
            "If the PRD projection is stale relative to source coverage, re-run `rah.py prd <repo-root> validate` "
            "or regenerate atoms/PRD before relying on the PRD view."
        )
    if fleet_pending:
        autopilot_prompt += (
            " If the just-dispatched fleet run has stories awaiting verdicts, YOU are the brain for this cycle: read "
            ".rah/fleet/runs/<run-id>/review_packet.md, review each patch diff yourself, record "
            "`rah.py fleet <repo-root> verdict <run-id> --story <id> --approve --evidence ... "
            "--validation ... --semantic ... --provenance ... --negative-test ...` or "
            "`--reject --rework ...` per story, then `rah.py fleet <repo-root> resume <run-id>`. "
            "All five approval proof fields must be brain-authored after inspection. Workers are "
            "implementation-only; never approve on a worker's claim alone."
        )
    if fleet_opt_out:
        autopilot_prompt += (
            f" The user opted out of fleet (\"{fleet_opt_out}\"): do not use the fleet surface in this run."
        )
    if args.extra_prompt:
        # ralph_driver's --extra-prompt is last-wins in argparse; merge here so a
        # user prompt never silently replaces the guardrails above.
        autopilot_prompt = "\n\n".join([autopilot_prompt, args.extra_prompt])
    command = [
        sys.executable,
        "-B",
        str(automation_dir() / "ralph_driver.py"),
        str(repo_root),
        "--goal",
        args.goal,
        "--completion-mode",
        args.completion_mode,
        "--max-iterations",
        str(args.max_iterations),
        "--max-cycles",
        str(args.max_cycles),
        "--max-idle-cycles",
        str(args.max_idle_cycles),
        "--cycle-timeout-seconds",
        str(args.cycle_timeout_seconds),
        "--job-poll-seconds",
        str(args.job_poll_seconds),
        "--job-max-wait-seconds",
        str(args.job_max_wait_seconds),
        "--extra-prompt",
        autopilot_prompt,
    ]
    if args.replace_terminal_goal:
        command.append("--replace-terminal-goal")
    if args.engine and args.engine != "auto":
        command.extend(["--engine", args.engine])
    if args.model:
        command.extend(["--model", args.model])
    # Codex engine passthrough
    if args.codex_bin:
        command.extend(["--codex-bin", args.codex_bin])
    if args.sandbox:
        command.extend(["--sandbox", args.sandbox])
    for item in args.codex_arg:
        command.extend(["--codex-arg", item])
    if args.dangerously_bypass_approvals_and_sandbox:
        command.append("--dangerously-bypass-approvals-and-sandbox")
    # Claude Code engine passthrough
    if args.claude_bin:
        command.extend(["--claude-bin", args.claude_bin])
    if args.permission_mode:
        command.extend(["--permission-mode", args.permission_mode])
    for item in args.claude_arg:
        command.extend(["--claude-arg", item])
    if args.dangerously_skip_permissions:
        command.append("--dangerously-skip-permissions")
    if args.extra_prompt_file:
        command.extend(["--extra-prompt-file", args.extra_prompt_file])
    if args.dry_run:
        command.append("--dry-run")
    if args.json:
        command.append("--json")
    return command


def should_run_source_ingest(command: list[str] | None, force: bool, repo_root: Path) -> bool:
    if command is None:
        return False
    if force:
        return True
    coverage = ralph_root(repo_root) / "source_requirement_coverage.json"
    return not coverage.exists()


def ralph_replacement_expected(repo_root: Path, args: argparse.Namespace) -> bool:
    """Predict whether the ralph step will archive .rah/ralph (reset/replace).

    When it will, autopilot must run ralph BEFORE ingest/PRD so freshly
    generated coverage/PRD/driver directives are not swept into the archive.
    This mirrors ralph_harness's terminal_status/retained_goal_differs checks;
    a false negative only reverts that corner to the pre-fix ordering, while
    replacement authority itself stays with ralph_harness.
    """
    ralph = ralph_root(repo_root)
    if args.reset:
        return ralph.exists()
    if not args.replace_terminal_goal:
        return False
    goal_payload = read_json(ralph / "goal.json")
    loop_payload = read_json(ralph / "loop_state.json")
    existing_goal_text = ""
    for payload in (goal_payload, loop_payload):
        if isinstance(payload, dict) and str(payload.get("goal") or "").strip():
            existing_goal_text = str(payload.get("goal")).strip()
            break
    if not existing_goal_text or existing_goal_text == (args.goal or "").strip():
        return False
    status = ""
    for payload in (loop_payload, goal_payload):
        if isinstance(payload, dict) and payload.get("status"):
            status = str(payload.get("status")).strip().lower()
            break
    return status in {"done", "cancelled", "canceled", "failed", "blocked"}


def main() -> int:
    parser = _SuggestingArgumentParser(description="Automatically prepare and drive an exhaustive RALPH run.")
    parser.add_argument("repo_root", help="Path to the repository or workspace root.")
    parser.add_argument("--goal", required=True, help="Full objective to pursue.")
    parser.add_argument("--source", action="append", default=[], help="Source file to ingest before RALPH. Can repeat.")
    parser.add_argument("--stdin", action="store_true", help="Read pasted source text from stdin and ingest it.")
    parser.add_argument("--label", default=None, help="Label for --stdin source text.")
    parser.add_argument(
        "--goal-as-source",
        choices=["auto", "always", "off"],
        default="auto",
        help="Ingest the natural-language goal itself as source coverage when no explicit source/stdin exists. Auto triggers for long requirement-like goals.",
    )
    parser.add_argument("--goal-source-label", default="goal-requirements", help="Label used when --goal-as-source ingests the goal text.")
    parser.add_argument("--source-mode", choices=["auto", "implementation", "analysis", "paper", "summary", "synthesis", "writing"], default="auto")
    parser.add_argument("--completion-mode", choices=["bounded", "exhaustive"], default="exhaustive")
    parser.add_argument("--max-iterations", type=int, default=12)
    parser.add_argument("--max-cycles", type=int, default=0, help="Driver cycle limit. 0 means unlimited until terminal.")
    parser.add_argument(
        "--max-idle-cycles",
        type=int,
        default=0,
        help="Optional idle-cycle blocker forwarded to drive. Default 0 means no automatic stop for no-progress/no-response cycles.",
    )
    parser.add_argument(
        "--cycle-timeout-seconds",
        type=int,
        default=86400,
        help="Maximum seconds for one nested agent cycle (codex exec / claude -p). Default is 86400 (24 hours); 0 disables the per-cycle timeout.",
    )
    parser.add_argument("--job-poll-seconds", type=int, default=30)
    parser.add_argument("--job-max-wait-seconds", type=int, default=0)
    parser.add_argument("--redact-excerpts-for-tracking", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--force-source-ingest", action="store_true", help="Replace existing source coverage during ingest.")
    parser.add_argument("--require-source-coverage", action="store_true", help="Force source coverage requirement even if no source path is detected.")
    parser.add_argument("--allow-without-source-coverage", action="store_true", help="Disable inferred source coverage requirement.")
    parser.add_argument(
        "--prd-mode",
        choices=["auto", "off", "emit", "from-prd"],
        default="auto",
        help="PRD projection routing. 'auto' activates only on explicit PRD wording in the goal; opt-out wording wins.",
    )
    parser.add_argument("--emit-prd", action="store_true", help="Emit a PRD projection from source coverage before RALPH.")
    parser.add_argument("--from-prd", default=None, help="Ingest an existing PRD (.md or .json) as the projection.")
    parser.add_argument(
        "--prd-only",
        action="store_true",
        help=(
            "Generate source coverage + PRD projection, report story/epic composition and the mapping audit, "
            "then STOP: no RALPH goal, no fleet, no drive. Also auto-activates on goal wording such as "
            "'PRD 생성까지만' or explicit PRD wording combined with '구현은 시작하지 마'."
        ),
    )
    parser.add_argument(
        "--fleet-mode",
        choices=["off", "implement", "review"],
        default=None,
        help="Parallel implementation-only workers with a brain checkpoint. If omitted, fleet/parallel-implementation wording can infer implement mode.",
    )
    parser.add_argument(
        "--brain",
        choices=["drive", "session"],
        default=None,
        help="Who reviews fleet output. If omitted, legacy drive-brain/calling-session wording is inferred, then defaults to drive.",
    )
    parser.add_argument(
        "--fleet-monitor",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Keep the calling session available by launching Fleet through the native RAH job supervisor, "
            "then use fleet monitor/reply. Worker-conversation monitoring wording can infer this mode."
        ),
    )
    parser.add_argument("--fleet-run-id", default=None, help="Optional stable run id for monitored Fleet dispatch.")
    parser.add_argument("--fleet-test-cmd", default=None, help="Pre-gate test command run inside each fleet worktree.")
    parser.add_argument("--fleet-worker-contract", default=None, help="Additional brain-authored contract embedded in every fleet worker brief.")
    parser.add_argument("--replace-terminal-goal", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--resume-current-goal",
        action="store_true",
        help="Treat --goal text as a continuation directive, retain the existing RALPH goal, and merge the directive into the driver prompt.",
    )
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--no-drive", action="store_true", help="Initialize RALPH and source coverage but do not invoke the external driver.")
    parser.add_argument("--dry-run", action="store_true", help="Show planned commands without mutating or driving.")
    parser.add_argument("--ocr", choices=["auto", "off", "force"], default="auto")
    parser.add_argument("--ocr-lang", default=os.environ.get("RAH_OCR_LANG", "eng"))
    parser.add_argument("--ocr-tessdata", default=None)
    parser.add_argument("--ocr-max-pages", type=int, default=None)
    parser.add_argument(
        "--engine",
        choices=["auto", "codex", "claude"],
        default="auto",
        help="Host agent for drive cycles. 'auto' detects the runtime (Claude Code -> claude, Codex -> codex).",
    )
    parser.add_argument("--model", default=None)
    # Codex engine options
    parser.add_argument("--codex-bin", default=None)
    parser.add_argument("--sandbox", default=None)
    parser.add_argument("--codex-arg", action="append", default=[])
    parser.add_argument("--dangerously-bypass-approvals-and-sandbox", action="store_true")
    # Claude Code engine options
    parser.add_argument("--claude-bin", default=None)
    parser.add_argument("--permission-mode", default=None)
    parser.add_argument("--claude-arg", action="append", default=[])
    parser.add_argument("--dangerously-skip-permissions", action="store_true")
    parser.add_argument("--extra-prompt", default=None)
    parser.add_argument("--extra-prompt-file", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).expanduser().resolve()
    requested_goal = args.goal
    directive_detection = detect_control_directive(requested_goal)
    resume_current_goal = bool(args.resume_current_goal or directive_detection["detected"])
    routing_goal = requested_goal
    retained_goal: str | None = None
    if resume_current_goal:
        retained_goal = retained_ralph_goal(repo_root)
        if not retained_goal:
            print(
                json.dumps(
                    {
                        "operation": "autopilot",
                        "error": "Continuation/current-goal routing was requested, but no retained RALPH goal exists.",
                        "resume_current_goal": {
                            "active": True,
                            "explicit": bool(args.resume_current_goal),
                            "natural_detection": bool(directive_detection["detected"]),
                            "markers": directive_detection["markers"],
                        },
                        "hint": "Start autopilot with an actual objective first, or remove --resume-current-goal/control-only wording.",
                    },
                    ensure_ascii=False,
                )
            )
            return 2
        args.goal = retained_goal
        args.extra_prompt = merge_extra_prompt(args.extra_prompt, requested_goal)

    sources, unresolved_sources = collect_sources(routing_goal, repo_root, args.source)
    if unresolved_sources:
        print(
            json.dumps(
                {
                    "operation": "autopilot",
                    "error": "One or more explicit --source paths could not be resolved to an existing supported source file.",
                    "unresolved_sources": unresolved_sources,
                    "supported_extensions": sorted(SOURCE_EXTENSIONS),
                    "hint": "Pass an existing path (absolute or relative to repo_root), or remove the invalid --source argument.",
                },
                ensure_ascii=False,
            )
        )
        return 2

    prd_plan = resolve_prd_plan(args, routing_goal)
    fleet_plan = resolve_fleet_plan(args, routing_goal)
    scientific_fleet_trigger = detect_scientific_fleet_request(routing_goal)
    if prd_plan.get("error"):
        print(json.dumps({"error": prd_plan["error"]}, ensure_ascii=False))
        return 2
    if prd_plan["active"] and prd_plan.get("mode") == "from-prd":
        from_path = Path(str(prd_plan.get("from_path"))).expanduser()
        if not from_path.is_absolute():
            from_path = (repo_root / from_path).resolve()
        if not from_path.exists() or not from_path.is_file():
            print(json.dumps({"error": f"Missing --from-prd file: {from_path}"}, ensure_ascii=False))
            return 2
        prd_plan["from_path"] = str(from_path)
        coverage_exists = (ralph_root(repo_root) / "source_requirement_coverage.json").exists()
        if not sources and not args.stdin and not coverage_exists:
            # Standalone PRD cannot prove source-driven completion: ingest the
            # PRD itself as source coverage first, then project it.
            sources = [from_path]
    prd_only_detection = detect_prd_only_request(routing_goal)
    prd_only_phrase = prd_only_detection["phrase"]
    stop_phrase = prd_only_detection["stop_phrase"]
    prd_only = bool(args.prd_only or prd_only_detection["prd_only"])
    if not prd_only and stop_phrase and prd_plan["active"]:
        # Explicit PRD request + "do not implement" wording = generate the
        # projection, report it, and stop.
        prd_only = True
        prd_only_phrase = stop_phrase
    implementation_stop = stop_phrase if (stop_phrase and not prd_only) else None
    if (prd_only or implementation_stop) and args.fleet_mode != "off":
        blocker = prd_only_phrase or stop_phrase or "--prd-only"
        if fleet_plan.get("mode_source") == "goal-inference" and fleet_plan.get("explicit_mode") is None:
            # A stop directive is safer and more specific than an incidental
            # natural-language fleet mention. Explicit CLI implementation
            # still conflicts and fails closed below.
            args.fleet_mode = "off"
            args.fleet_monitor = False
            fleet_plan.update(
                {
                    "mode": "off",
                    "brain": None,
                    "mode_inferred": False,
                    "mode_source": "prd-stop-precedence",
                    "suppressed_by_prd_only": blocker,
                    "monitor": False,
                }
            )
        else:
            print(
                json.dumps(
                    {
                        "error": (
                            f"Explicit --fleet-mode {args.fleet_mode} conflicts with the PRD-only/no-implementation "
                            f"request ({blocker!r}): fleet implies implementation. Drop --fleet-mode or remove the "
                            "stop wording/flag."
                        )
                    },
                    ensure_ascii=False,
                )
            )
            return 2
    if prd_only:
        if args.prd_mode == "off" or prd_plan.get("opt_out_phrase"):
            conflict = prd_plan.get("opt_out_phrase") or "--prd-mode off"
            print(
                json.dumps(
                    {"error": f"PRD-only run conflicts with PRD opt-out ({conflict!r}); nothing would be generated."},
                    ensure_ascii=False,
                )
            )
            return 2
        if not prd_plan["active"]:
            # The flag itself is an explicit PRD request.
            prd_plan.update({"active": True, "mode": "emit"})
    if implementation_stop:
        # Fail safe in the dangerous direction: never launch the driver against
        # explicit "do not implement" wording; the operator can run drive later.
        args.no_drive = True
    if args.fleet_monitor and args.fleet_mode == "off":
        print(
            json.dumps(
                {"error": "--fleet-monitor requires an active Fleet mode."},
                ensure_ascii=False,
            )
        )
        return 2
    if args.fleet_monitor and args.brain != "session":
        print(
            json.dumps(
                {
                    "error": (
                        "Monitored Fleet keeps the calling session in the loop and therefore requires "
                        "--brain session. Remove --brain drive or disable --fleet-monitor."
                    )
                },
                ensure_ascii=False,
            )
        )
        return 2
    scientific_fleet_active = bool(
        scientific_fleet_trigger and args.fleet_mode != "off" and not prd_only
    )
    if scientific_fleet_active and not args.fleet_test_cmd:
        print(
            json.dumps(
                {
                    "operation": "autopilot",
                    "error": (
                        "Scientific/numerical fleet intent requires an exact repo test command before dispatch; "
                        "automatic test-command guessing is unsafe."
                    ),
                    "scientific_fleet_trigger": scientific_fleet_trigger,
                    "fleet": {"mode": args.fleet_mode, "brain": args.brain},
                    "hint": "Inspect the target module, then rerun with --fleet-test-cmd \"<exact command>\".",
                },
                ensure_ascii=False,
            )
        )
        return 2
    scientific_contract_source = None
    if scientific_fleet_active:
        operator_contract = str(args.fleet_worker_contract or "").strip()
        args.fleet_worker_contract = SCIENTIFIC_FLEET_CONTRACT
        scientific_contract_source = "fixed"
        if operator_contract:
            args.fleet_worker_contract += f"\n\nAdditional operator contract:\n{operator_contract}"
            scientific_contract_source = "fixed+operator"
    # A continuation directive is control-plane text, never source material for
    # the retained goal (even when --goal-as-source always was supplied).
    goal_as_source = False if resume_current_goal else should_ingest_goal_as_source(
        routing_goal, sources, args.stdin, args.goal_as_source
    )
    stdin_requested = bool(args.stdin or goal_as_source)
    stdin_label = args.label or (args.goal_source_label if goal_as_source else "pasted-source")
    mode_routing_text = "\n".join([args.goal, routing_goal]) if resume_current_goal else routing_goal
    mode = infer_mode(mode_routing_text, sources, args.source_mode)
    retained_goal_payload = read_json(ralph_root(repo_root) / "goal.json") if resume_current_goal else None
    retained_source_required = bool(
        resume_current_goal
        and (
            (isinstance(retained_goal_payload, dict) and retained_goal_payload.get("source_coverage_required"))
            or (ralph_root(repo_root) / "source_requirement_coverage.json").exists()
        )
    )
    require_source = source_required(
        "" if resume_current_goal else routing_goal,
        sources,
        stdin_requested,
        bool(args.require_source_coverage or retained_source_required),
        args.allow_without_source_coverage,
        goal_as_source=goal_as_source,
    )
    stdin_text = None
    if not args.dry_run:
        if args.stdin:
            stdin_text = sys.stdin.read()
        elif goal_as_source:
            stdin_text = args.goal
    source_command = build_source_ingest_command(
        repo_root,
        sources,
        mode,
        args,
        stdin_requested=stdin_requested,
        stdin_label=stdin_label,
    )
    prd_commands = (
        build_prd_commands(repo_root, args, prd_plan, include_status=prd_only) if prd_plan["active"] else None
    )
    # The drive guardrail prompt keys on projection PRESENCE, not this run's
    # activation: a resume without PRD wording must still warn the nested agent.
    prd_present = bool(prd_plan["active"] or (ralph_root(repo_root) / "prd.json").exists())
    fleet_active = args.fleet_mode != "off" and not prd_only
    fleet_opt_out = fleet_plan["opt_out_phrase"]
    session_brain = bool(fleet_active and args.brain == "session")
    if fleet_active and args.fleet_monitor and not args.fleet_run_id:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        digest = hashlib.sha256(f"{routing_goal}|{stamp}".encode("utf-8")).hexdigest()[:6]
        args.fleet_run_id = f"run-monitor-{stamp}-{digest}"
    if (
        fleet_active
        and args.fleet_monitor
        and not SAFE_FLEET_RUN_ID_RE.fullmatch(str(args.fleet_run_id or ""))
    ):
        raise SystemExit(
            "--fleet-run-id must start with a letter or digit, contain only letters, digits, dot, "
            "underscore, or dash, and be at most 128 characters."
        )
    fleet_dispatch_command = build_fleet_dispatch_command(repo_root, args) if fleet_active else None
    fleet_command = fleet_dispatch_command
    if fleet_dispatch_command and args.fleet_monitor:
        fleet_command = build_monitored_fleet_job_command(
            repo_root,
            str(args.fleet_run_id),
            fleet_dispatch_command,
        )
    ralph_command = (
        None if prd_only else build_ralph_command(repo_root, args, require_source, require_prd=prd_plan["active"])
    )
    drive_command = (
        None
        if (prd_only or args.no_drive or session_brain)
        else build_drive_command(
            repo_root,
            args,
            prd_active=prd_present,
            fleet_pending=bool(fleet_active and args.brain == "drive"),
            fleet_opt_out=fleet_opt_out,
        )
    )
    ralph_first = bool(not prd_only and ralph_replacement_expected(repo_root, args))
    planned = {
        "operation": "autopilot",
        "generated_at_utc": utc_now(),
        "repo_root": str(repo_root),
        "goal": args.goal,
        "requested_goal": requested_goal,
        "routing_goal": routing_goal,
        "resume_current_goal": {
            "active": resume_current_goal,
            "explicit": bool(args.resume_current_goal),
            "natural_detection": bool(directive_detection["detected"]),
            "markers": directive_detection["markers"],
            "retained_goal": retained_goal,
            "directive_merged_into_extra_prompt": resume_current_goal,
        },
        "detected_sources": [str(source) for source in sources],
        "goal_as_source": goal_as_source,
        "goal_as_source_suppressed_reason": "continuation-control-directive" if resume_current_goal else None,
        "stdin_source_label": stdin_label if stdin_requested else None,
        "source_mode": mode,
        "source_coverage_required": require_source,
        "retained_source_coverage_required": retained_source_required if resume_current_goal else None,
        "redact_excerpts_for_tracking": args.redact_excerpts_for_tracking,
        "prd": {
            "active": prd_plan["active"],
            "present": prd_present,
            "mode": prd_plan.get("mode"),
            "from_prd": prd_plan.get("from_path") if prd_plan.get("mode") == "from-prd" else None,
            "opt_out_phrase": prd_plan.get("opt_out_phrase"),
        },
        "prd_trigger_phrase": prd_plan.get("trigger_phrase"),
        "prd_only": {
            "active": prd_only,
            "flag": bool(args.prd_only),
            "phrase": prd_only_phrase,
        },
        "implementation_stop_phrase": implementation_stop,
        # When a goal reset/replacement will archive .rah/ralph, ralph runs
        # BEFORE ingest/PRD so fresh artifacts are not swept into the archive.
        "ralph_first": ralph_first,
        "fleet": {
            "mode": args.fleet_mode,
            "brain": args.brain if fleet_active else None,
            "opt_out_phrase": fleet_opt_out,
            "detected_opt_out_phrase": fleet_plan["detected_opt_out_phrase"],
            "trigger_phrase": fleet_plan["trigger_phrase"],
            "mode_inferred": fleet_plan["mode_inferred"],
            "mode_source": fleet_plan["mode_source"],
            "explicit_mode": fleet_plan["explicit_mode"],
            "suppressed_by_prd_only": fleet_plan.get("suppressed_by_prd_only"),
            "brain_trigger_phrase": fleet_plan["brain_trigger_phrase"],
            "brain_inferred": fleet_plan["brain_inferred"],
            "brain_source": fleet_plan["brain_source"],
            "explicit_brain": fleet_plan["explicit_brain"],
            "scientific_contract_trigger": scientific_fleet_trigger,
            "scientific_contract_active": scientific_fleet_active,
            "scientific_contract_source": scientific_contract_source,
            "worker_contract": args.fleet_worker_contract if fleet_active else None,
            "test_command": args.fleet_test_cmd if fleet_active else None,
            "session_brain_returns_after_dispatch": session_brain,
            "monitor": bool(args.fleet_monitor and fleet_active),
            "monitor_trigger_phrase": fleet_plan.get("monitor_trigger_phrase"),
            "monitor_source": fleet_plan.get("monitor_source"),
            "explicit_monitor": fleet_plan.get("explicit_monitor"),
            "run_id": args.fleet_run_id if fleet_active else None,
            "background_supervisor": "rah-job" if args.fleet_monitor and fleet_active else None,
        },
        "commands": {
            "source_ingest": source_command,
            "prd": prd_commands,
            "fleet": fleet_command,
            "fleet_dispatch": fleet_dispatch_command if args.fleet_monitor and fleet_active else None,
            "ralph": ralph_command,
            "drive": drive_command,
        },
    }
    if args.dry_run:
        print(json.dumps({**planned, "dry_run": True}, indent=2, ensure_ascii=False))
        return 0

    results: dict[str, Any] = {}

    def run_ralph_step() -> int | None:
        # Snapshot/restore a pre-written driver directive file: goal replacement
        # archives all of .rah/ralph, including --extra-prompt-file targets, and
        # drive fails closed at launch when that file is missing.
        extra_prompt_file_path: Path | None = None
        extra_prompt_file_snapshot: str | None = None
        if args.extra_prompt_file:
            extra_prompt_file_path = Path(args.extra_prompt_file).expanduser().resolve()
            if extra_prompt_file_path.exists():
                extra_prompt_file_snapshot = extra_prompt_file_path.read_text(encoding="utf-8")
        results["ralph"] = run_command(ralph_command or [])
        if results["ralph"]["returncode"] != 0:
            print(json.dumps({**planned, "results": results}, indent=2, ensure_ascii=False))
            return int(results["ralph"]["returncode"])
        if (
            extra_prompt_file_path is not None
            and extra_prompt_file_snapshot is not None
            and not extra_prompt_file_path.exists()
        ):
            extra_prompt_file_path.parent.mkdir(parents=True, exist_ok=True)
            extra_prompt_file_path.write_text(extra_prompt_file_snapshot, encoding="utf-8")
            results["extra_prompt_file_restored"] = str(extra_prompt_file_path)
        return None

    if prd_only:
        results["ralph"] = {"skipped": True, "reason": "prd-only run stops before RALPH goal creation"}
    elif ralph_first:
        # The pending reset/replacement archives .rah/ralph; run it before
        # ingest/PRD so fresh artifacts are not swept into the archive.
        ralph_rc = run_ralph_step()
        if ralph_rc is not None:
            return ralph_rc

    if should_run_source_ingest(source_command, args.force_source_ingest, repo_root):
        results["source_ingest"] = run_command(source_command or [], input_text=stdin_text)
        if results["source_ingest"]["returncode"] != 0:
            print(json.dumps({**planned, "results": results}, indent=2, ensure_ascii=False))
            return int(results["source_ingest"]["returncode"])
    else:
        results["source_ingest"] = {
            "skipped": True,
            "reason": "no source command or existing source coverage; pass --force-source-ingest to replace",
        }

    if prd_only:
        coverage_file = ralph_root(repo_root) / "source_requirement_coverage.json"
        if not coverage_file.exists():
            print(
                json.dumps(
                    {
                        **planned,
                        "results": results,
                        "error": "PRD-only run needs source coverage: pass --source/--stdin (or ingest first), then rerun.",
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 2
        prd_only_results: list[dict[str, Any]] = []
        results["prd"] = prd_only_results
        gate_ready = True
        for command in prd_commands or []:
            outcome = run_command(command)
            prd_only_results.append(outcome)
            if outcome["returncode"] == 0:
                continue
            if outcome["returncode"] == 1 and prd_command_surface(command) in {"emit", "ingest", "validate"}:
                # Exit 1 from a gate command means artifacts were written but the
                # audit is not ready — reporting exactly that is this mode's job.
                gate_ready = False
                continue
            print(json.dumps({**planned, "results": results}, indent=2, ensure_ascii=False))
            return int(outcome["returncode"])
        results["fleet"] = {"skipped": True, "reason": "prd-only"}
        results["drive"] = {"skipped": True, "reason": "prd-only"}
        report = build_prd_only_summary(repo_root, prd_only_results, gate_ready)
        if results["source_ingest"].get("skipped") and (sources or stdin_requested):
            report.setdefault("warnings", []).append(
                "Existing source coverage was retained; pass --force-source-ingest to re-ingest the provided sources."
            )
        next_actions = [
            "Review .rah/ralph/prd.md (story/epic composition) and prd_only_report (row/atom coverage, needs_review reasons).",
            "Implementation did NOT start: no RALPH goal, no fleet, no drive were launched in this run.",
            "To proceed after operator approval, rerun autopilot without the PRD-only wording/flag "
            "(e.g. add --fleet-mode implement, --brain session for session-reviewed parallel work).",
        ]
        print(
            json.dumps(
                {**planned, "results": compact_results_for_print(results), "prd_only_report": report, "next_actions": next_actions},
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    if prd_commands:
        prd_results: list[dict[str, Any]] = []
        results["prd"] = prd_results
        for command in prd_commands:
            outcome = run_command(command)
            prd_results.append(outcome)
            if outcome["returncode"] != 0:
                # Fail closed: an unready PRD projection must surface before RALPH/fleet/drive.
                print(json.dumps({**planned, "results": results}, indent=2, ensure_ascii=False))
                return int(outcome["returncode"])

    if not prd_only and not ralph_first:
        ralph_rc = run_ralph_step()
        if ralph_rc is not None:
            return ralph_rc

    if fleet_command:
        if args.fleet_monitor:
            requested_state = (
                repo_root
                / ".rah"
                / "fleet"
                / "runs"
                / str(args.fleet_run_id)
                / "state.json"
            )
            if requested_state.exists():
                results["fleet"] = {
                    "returncode": 2,
                    "error": f"Monitored Fleet run already exists: {args.fleet_run_id}",
                }
                print(json.dumps({**planned, "results": results}, indent=2, ensure_ascii=False))
                return 2
        results["fleet"] = run_command(fleet_command)
        if results["fleet"]["returncode"] != 0:
            print(json.dumps({**planned, "results": results}, indent=2, ensure_ascii=False))
            return int(results["fleet"]["returncode"])
        fleet_readiness: dict[str, Any] | None = None
        if args.fleet_monitor:
            launch_payload = results["fleet"].get("stdout_json") or {}
            launch_job = launch_payload.get("job") if isinstance(launch_payload, dict) else None
            launch_job_id = launch_job.get("job_id") if isinstance(launch_job, dict) else None
            fleet_readiness = wait_for_monitored_fleet_readiness(
                repo_root,
                str(args.fleet_run_id),
                str(launch_job_id) if launch_job_id else None,
            )
            results["fleet"]["readiness"] = fleet_readiness
            if fleet_readiness.get("status") == "failed":
                results["fleet"]["returncode"] = int(fleet_readiness.get("returncode") or 2)
                print(json.dumps({**planned, "results": results}, indent=2, ensure_ascii=False))
                return int(results["fleet"]["returncode"])
        if session_brain:
            fleet_payload = results["fleet"].get("stdout_json") or {}
            if args.fleet_monitor:
                run_id = (
                    fleet_readiness.get("run_id")
                    if isinstance(fleet_readiness, dict)
                    else args.fleet_run_id
                )
                job_payload = fleet_payload.get("job") if isinstance(fleet_payload, dict) else None
                job_id = job_payload.get("job_id") if isinstance(job_payload, dict) else None
                readiness_status = str((fleet_readiness or {}).get("status") or "pending")
                if readiness_status == "noop":
                    next_actions = ["Fleet had nothing to dispatch (stories already ready); continue with drive or closeout."]
                elif readiness_status == "pending":
                    next_actions = [
                        f"Fleet state is not ready yet. Inspect the durable job first: rah.py job <repo-root> status {job_id}.",
                        f"After the run appears, monitor it with: rah.py fleet <repo-root> monitor {run_id} --since 0 --wait-seconds 30 --json.",
                    ]
                else:
                    next_actions = [
                        f"Monitor explicit worker/brain messages: rah.py fleet <repo-root> monitor {run_id} --since 0 --wait-seconds 30 --include-content --json.",
                        f"If a worker asks a question, answer with: rah.py fleet <repo-root> reply {run_id} --question <id> --message-file <path>; then rah.py fleet <repo-root> resume {run_id}.",
                        f"When status reaches awaiting_verdicts, review .rah/fleet/runs/{run_id}/review_packet.md, record strict verdicts, and resume.",
                    ]
                if job_id:
                    next_actions.insert(0, f"Background Fleet supervisor job: {job_id} (inspect with rah.py job <repo-root> status {job_id}).")
            else:
                run_id = fleet_payload.get("run_id")
            if not args.fleet_monitor and run_id is None:
                next_actions = ["Fleet had nothing to dispatch (stories already ready); run drive for the leftovers."]
            elif not args.fleet_monitor and args.fleet_mode == "review":
                next_actions = [
                    f"Read .rah/fleet/runs/{run_id}/review_packet.md — finder findings are data for you to adjudicate; review runs end at the packet (no verdict/resume).",
                ]
            elif not args.fleet_monitor:
                next_actions = [
                    f"Read .rah/fleet/runs/{run_id}/review_packet.md and review each patch diff yourself.",
                    f"Record verdicts: rah.py fleet <repo-root> verdict {run_id} --story <id> --approve --evidence \"...\" --validation \"...\" --semantic \"...\" --provenance \"...\" --negative-test \"...\" | --reject --rework \"...\"",
                    f"Apply/redispatch: rah.py fleet <repo-root> resume {run_id} (repeat until stories are applied), then hand leftovers to drive.",
                ]
            # Checkpoint-return: the CALLING session model is the brain; hand it
            # the review packet instead of driving on.
            print(
                json.dumps(
                    {
                        **planned,
                        "results": compact_results_for_print(results),
                        "brain": "session",
                        "fleet_run_id": run_id,
                        "next_actions": next_actions,
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 0

    if drive_command is not None:
        if args.json:
            results["drive"] = run_command(drive_command)
        else:
            completed = subprocess.run(drive_command, check=False)
            results["drive"] = {"command": drive_command, "returncode": int(completed.returncode)}
    else:
        results["drive"] = {"skipped": True, "reason": "--no-drive"}

    drive_rc = results.get("drive", {}).get("returncode")
    payload = {**planned, "results": compact_results_for_print(results)}
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return int(drive_rc) if isinstance(drive_rc, int) else 0


if __name__ == "__main__":
    raise SystemExit(main())
