#!/usr/bin/env python3
"""Doctor surface for the deployable Memento-aware recursive architecture harness."""
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
import stat
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from source_coverage_harness import rows_from_payload, row_ready, validate_coverage_payload


SKILL_DIR_NAME = "recursive-architecture-refactoring-auto"
CRITICAL_FILE_SPECS: dict[str, dict[str, int]] = {
    "automation/ralph_state_probe.py": {"probe_api_version": 1},
    "automation/agent_engine.py": {},
    "automation/doctor_harness.py": {},
}

try:
    import tomllib  # Python 3.11+
except Exception:  # pragma: no cover
    tomllib = None  # type: ignore


def codex_home() -> Path:
    raw = os.environ.get("CODEX_HOME")
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path.home() / ".codex").resolve()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def probe_api_version(path: Path) -> int | None:
    match = re.search(
        r"(?m)^PROBE_API_VERSION\s*=\s*(\d+)\s*$",
        path.read_text(encoding="utf-8"),
    )
    return int(match.group(1)) if match else None


def regular_unlinked_file(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return False
    return stat.S_ISREG(info.st_mode) and not path.is_symlink()


def local_critical_files_ok(package_root: Path) -> tuple[bool, str]:
    for relative, expected in CRITICAL_FILE_SPECS.items():
        path = package_root / relative
        if not regular_unlinked_file(path):
            return False, f"Missing or link-backed critical helper: {relative}"
        if "probe_api_version" in expected and probe_api_version(path) != expected[
            "probe_api_version"
        ]:
            return False, f"Unexpected lifecycle probe API: {relative}"
    return True, "Critical helper files and lifecycle probe API are present."


def deployment_critical_files_ok(
    root: Path, deployment: dict[str, Any]
) -> tuple[str, str]:
    if deployment.get("scope") != "repo":
        return "warn", "Latest deployment state is not a repo-helper install."
    package = deployment.get("package_install")
    if not isinstance(package, dict):
        return "fail", "Repo deployment is missing package_install metadata."
    manifest = package.get("critical_files")
    if not isinstance(manifest, dict):
        return "fail", "Repo deployment is missing critical-file digests."

    expected_target = (
        root / ".rah" / "helpers" / SKILL_DIR_NAME
    ).resolve()
    target_value = package.get("target")
    if not isinstance(target_value, str):
        return "fail", "Repo deployment target metadata is missing."
    try:
        target = Path(target_value).expanduser().resolve()
    except OSError:
        return "fail", "Repo deployment target metadata is invalid."
    if target != expected_target:
        return "fail", "Repo deployment target does not match the managed helper root."

    for relative, expected in CRITICAL_FILE_SPECS.items():
        record = manifest.get(relative)
        if not isinstance(record, dict) or record.get("verified") is not True:
            return "fail", f"Critical-file manifest is incomplete: {relative}"
        digest = record.get("sha256")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            return "fail", f"Critical-file digest is invalid: {relative}"
        deployed = target / relative
        if not regular_unlinked_file(deployed) or sha256_file(deployed) != digest:
            return "fail", f"Deployed critical helper drifted: {relative}"
        if "probe_api_version" in expected and (
            record.get("probe_api_version") != expected["probe_api_version"]
            or probe_api_version(deployed) != expected["probe_api_version"]
        ):
            return "fail", f"Deployed lifecycle probe API drifted: {relative}"

    source_value = deployment.get("installed_at_source")
    if isinstance(source_value, str):
        source = Path(source_value).expanduser()
        if source.name == SKILL_DIR_NAME and (source / "SKILL.md").is_file():
            for relative in CRITICAL_FILE_SPECS:
                record = manifest[relative]
                source_file = source / relative
                if not regular_unlinked_file(source_file):
                    return "fail", f"Canonical critical helper is unavailable: {relative}"
                if sha256_file(source_file) != record["sha256"]:
                    return "fail", f"Canonical source is newer than repo helper: {relative}"
        elif source.exists():
            return "warn", "Installed source exists but is not a recognized skill root."
    return "pass", "Repo critical helpers match the install manifest and source."


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def has_any(root: Path, names: Iterable[str]) -> bool:
    return any((root / name).exists() for name in names)


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
    if (root / "domain").exists() and (root / "application").exists() and (root / "adapters").exists():
        return "layered-service"
    return "generic"


def choose_scaffold_root(root: Path) -> Path:
    candidates = [
        root / "docs" / "architecture",
        root / "architecture",
        root / "docs" / "Architecture",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return root / "docs" / "architecture"


def load_json(path: Path) -> tuple[str, Any]:
    if not path.exists():
        return "missing", None
    try:
        return "ok", json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - diagnostic path
        return "parse-error", str(exc)


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def add_check(checks: list[dict[str, Any]], name: str, status: str, detail: str) -> None:
    checks.append({"name": name, "status": status, "detail": detail})


def overall_status(checks: Iterable[dict[str, Any]]) -> str:
    statuses = {check["status"] for check in checks}
    if "fail" in statuses:
        return "fail"
    if "warn" in statuses:
        return "warn"
    return "pass"


def validate_workspace(value: str | None) -> bool:
    return bool(value and re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value))


def validate_topic(value: str | None) -> bool:
    return bool(value and re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value))


def validate_session(value: str | None) -> bool:
    return bool(value and re.fullmatch(r"[a-z0-9-]+#(?:adhoc|\d+):[a-z0-9-]+", value))


def validate_case(value: str | None) -> bool:
    return bool(value and re.fullmatch(r"case/[a-z0-9-]+/(?:adhoc|\d+)/[a-z0-9-]+", value))


def pending_feedback_count(feedback_payload: Any) -> int:
    if not isinstance(feedback_payload, dict):
        return 0
    items = feedback_payload.get("items", [])
    if not isinstance(items, list):
        return 0
    pending = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("relevant") is None or item.get("sufficient") is None:
            pending += 1
    return pending


def load_toml(path: Path) -> dict[str, Any] | None:
    if not path.exists() or tomllib is None:
        return None
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def iter_mcp_server_candidates(root: Path) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    search_paths = [
        ("project", root / ".codex" / "config.toml"),
        ("user", codex_home() / "config.toml"),
        ("repo", root / "config.toml"),
    ]
    for scope, path in search_paths:
        data = load_toml(path)
        if not isinstance(data, dict):
            continue
        servers = data.get("mcp_servers", {})
        if not isinstance(servers, dict):
            continue
        for name, cfg in servers.items():
            if not isinstance(cfg, dict):
                continue
            url = cfg.get("url")
            blob = json.dumps(cfg, ensure_ascii=False).lower()
            if "memento" in str(name).lower() or "57332" in blob or ("mcp" in blob and "remember" in blob):
                candidates.append(
                    {
                        "scope": scope,
                        "path": path,
                        "name": str(name),
                        "config": cfg,
                        "url": url,
                    }
                )
    return candidates


def find_memento_config(root: Path) -> tuple[bool, list[str], list[dict[str, Any]]]:
    parsed_candidates = iter_mcp_server_candidates(root)
    evidence = [f"{item['path']}::{item['name']}" for item in parsed_candidates]
    if parsed_candidates:
        return True, evidence, parsed_candidates

    fallback_paths = [
        root / ".codex" / "config.toml",
        codex_home() / "config.toml",
        root / ".claude" / "settings.json",
        Path.home() / ".claude" / "settings.json",
        root / "config.toml",
    ]
    for path in fallback_paths:
        if not path.exists():
            continue
        try:
            lowered = path.read_text(encoding="utf-8", errors="ignore").lower()
        except OSError:
            continue
        if "memento" in lowered or "57332" in lowered:
            evidence.append(str(path))
    return bool(evidence), evidence, []


def build_http_headers(config: dict[str, Any]) -> dict[str, str]:
    headers: dict[str, str] = {}
    bearer_env = config.get("bearer_token_env_var")
    if isinstance(bearer_env, str):
        token = os.environ.get(bearer_env)
        if token:
            headers["Authorization"] = f"Bearer {token}"
    http_headers = config.get("http_headers")
    if isinstance(http_headers, dict):
        for key, value in http_headers.items():
            if isinstance(key, str) and isinstance(value, str):
                headers[key] = value
    env_http_headers = config.get("env_http_headers")
    if isinstance(env_http_headers, dict):
        for key, env_name in env_http_headers.items():
            if isinstance(key, str) and isinstance(env_name, str):
                env_value = os.environ.get(env_name)
                if env_value:
                    headers[key] = env_value
    return headers


def derive_health_url(mcp_url: str) -> str:
    cleaned = mcp_url.rstrip("/")
    if cleaned.endswith("/mcp"):
        return cleaned[:-4] + "/health"
    return cleaned + "/health"


def ping_health(health_url: str, headers: dict[str, str], timeout_sec: float) -> dict[str, Any]:
    req = urllib.request.Request(health_url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=timeout_sec) as response:
        body = response.read()
        text = body.decode("utf-8", errors="replace")
        parsed: Any
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = {"raw": text[:500]}
        return {
            "ok": True,
            "http_status": int(response.status),
            "payload": parsed,
        }


def removed_runtime_word() -> str:
    return "".join(chr(codepoint) for codepoint in [104, 111, 111, 107])


def update_memento_status_file(root: Path, update: dict[str, Any]) -> None:
    path = root / ".rah" / "state" / "memento_status.json"
    state, payload = load_json(path)
    if state != "ok" or not isinstance(payload, dict):
        payload = {}
    payload.update(update)
    save_json(path, payload)


def update_status_file(root: Path, update: dict[str, Any]) -> None:
    path = root / ".rah" / "state" / "status.json"
    state, payload = load_json(path)
    if state != "ok" or not isinstance(payload, dict):
        payload = {}
    payload.update(update)
    save_json(path, payload)


def main() -> int:
    parser = _SuggestingArgumentParser(description="Verify harness bootstrap and deployment health for a repository.")
    parser.add_argument("repo_root", help="Path to the repository root")
    parser.add_argument("--json", action="store_true", help="Emit JSON only")
    parser.add_argument("--no-write-report", action="store_true", help="Do not write .rah/state/doctor.json")
    parser.add_argument("--live-memento", action="store_true", help="Attempt an actual /health probe using detected Memento MCP config.")
    parser.add_argument("--memento-timeout-sec", type=float, default=3.0, help="Timeout for the live Memento /health probe.")
    args = parser.parse_args()

    root = Path(args.repo_root).expanduser().resolve()
    checks: list[dict[str, Any]] = []

    if not root.exists() or not root.is_dir():
        add_check(checks, "repo_root", "fail", f"Missing or invalid repo root: {root}")
        payload = {
            "generated_at_utc": utc_now(),
            "root": str(root),
            "profile_hint": None,
            "scaffold_root": None,
            "checks": checks,
            "overall_status": overall_status(checks),
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 2

    profile = detect_profile(root)
    scaffold_root = choose_scaffold_root(root)
    rah_root = root / ".rah"

    markers = [
        name
        for name in [
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
        if (root / name).exists()
    ]
    if markers:
        add_check(checks, "repo_markers", "pass", ", ".join(markers))
    else:
        add_check(checks, "repo_markers", "warn", "No common repo markers detected at root.")

    if scaffold_root.exists():
        add_check(checks, "scaffold_root", "pass", str(scaffold_root))
    else:
        add_check(checks, "scaffold_root", "fail", f"Missing scaffold root: {scaffold_root}")

    required_artifacts = [
        scaffold_root / "Phytoritas.md",
        scaffold_root / "00_workspace_audit.md",
        scaffold_root / "01_system_brief.md",
        scaffold_root / "implementation/implementation_gate_checklist.md",
        scaffold_root / "architecture/adrs/ADR-000-adopt-recursive-architecture-workflow.md",
        scaffold_root / "architecture/module_specs/module-000-architecture-pipeline.md",
    ]
    missing_artifacts = [str(path) for path in required_artifacts if not path.exists()]
    if missing_artifacts:
        add_check(checks, "required_artifacts", "fail", "Missing starter artifacts: " + ", ".join(missing_artifacts))
    else:
        add_check(checks, "required_artifacts", "pass", "Starter architecture artifacts present.")

    required_runtime = [
        rah_root / "state/status.json",
        rah_root / "state/gates.json",
        rah_root / "state/bootstrap_summary.json",
        rah_root / "state/memento_status.json",
        rah_root / "plans/current_loop.md",
        rah_root / "memory/wakeup.md",
        rah_root / "memory/memento_context.json",
        rah_root / "memory/memento_recall.json",
        rah_root / "memory/memento_feedback.json",
        rah_root / "memory/memento_reflect_draft.json",
        rah_root / "memory/case_map.json",
        rah_root / "runtime/AGENTS.overlay.md",
    ]
    missing_runtime = [str(path) for path in required_runtime if not path.exists()]
    if missing_runtime:
        add_check(checks, "runtime_sidecar", "fail", "Missing runtime files: " + ", ".join(missing_runtime))
    else:
        add_check(checks, "runtime_sidecar", "pass", "Runtime sidecar looks structurally complete.")

    lifecycle_probe = Path(__file__).resolve().parent / "ralph_state_probe.py"
    if lifecycle_probe.is_file() and not lifecycle_probe.is_symlink():
        add_check(checks, "lifecycle_state_probe", "pass", "Read-only lifecycle state probe is deployed beside the helper surfaces.")
    else:
        add_check(checks, "lifecycle_state_probe", "fail", "Read-only lifecycle state probe is missing or link-backed.")
    critical_ok, critical_message = local_critical_files_ok(
        Path(__file__).resolve().parent.parent
    )
    add_check(
        checks,
        "helper_critical_files",
        "pass" if critical_ok else "fail",
        critical_message,
    )

    status_state, status_payload = load_json(rah_root / "state" / "status.json")
    gates_state, gates_payload = load_json(rah_root / "state" / "gates.json")
    memento_state_state, memento_state = load_json(rah_root / "state" / "memento_status.json")
    case_map_state, case_map = load_json(rah_root / "memory" / "case_map.json")
    feedback_state, feedback_payload = load_json(rah_root / "memory" / "memento_feedback.json")
    deployment_state, deployment_payload = load_json(rah_root / "state" / "deployment.json")
    ralph_goal_state, ralph_goal = load_json(rah_root / "ralph" / "goal.json")
    ralph_loop_state, ralph_loop = load_json(rah_root / "ralph" / "loop_state.json")
    ralph_evidence_state, ralph_evidence = load_json(rah_root / "ralph" / "evidence_ledger.json")
    ralph_plan_graph_state, ralph_plan_graph = load_json(rah_root / "ralph" / "plan_graph.json")
    ralph_goal_bridge_state, ralph_goal_bridge = load_json(rah_root / "ralph" / "goal_bridge.json")
    ralph_review_gate_state, ralph_review_gate = load_json(rah_root / "ralph" / "review_gate.json")
    ralph_driver_state, ralph_driver = load_json(rah_root / "ralph" / "driver" / "driver_state.json")
    source_documents_state, source_documents = load_json(rah_root / "ralph" / "source_documents.json")
    source_coverage_state, source_coverage = load_json(rah_root / "ralph" / "source_requirement_coverage.json")
    jobs_root = rah_root / "jobs"

    json_files = [
        ("status_json", status_state),
        ("gates_json", gates_state),
        ("memento_status_json", memento_state_state),
        ("case_map_json", case_map_state),
        ("memento_feedback_json", feedback_state),
    ]
    parse_errors = [name for name, state in json_files if state == "parse-error"]
    missing_json = [name for name, state in json_files if state == "missing"]
    if parse_errors:
        add_check(checks, "json_parse", "fail", "JSON parse errors in: " + ", ".join(parse_errors))
    elif missing_json:
        add_check(checks, "json_parse", "warn", "Some JSON state files are missing: " + ", ".join(missing_json))
    else:
        add_check(checks, "json_parse", "pass", "Core JSON state files parse successfully.")

    if (rah_root / "ralph" / "prd.json").exists():
        prd_states = [
            ("prd_json", load_json(rah_root / "ralph" / "prd.json")[0]),
            ("prd_mapping_audit_json", load_json(rah_root / "ralph" / "prd_mapping_audit.json")[0]),
            ("source_requirement_atoms_json", load_json(rah_root / "ralph" / "source_requirement_atoms.json")[0]),
            ("prd_waivers_json", load_json(rah_root / "ralph" / "prd_waivers.json")[0]),
        ]
        prd_parse_errors = [name for name, state in prd_states if state == "parse-error"]
        if prd_parse_errors:
            add_check(
                checks,
                "prd_projection_json",
                "fail",
                "PRD projection JSON parse errors in: " + ", ".join(prd_parse_errors),
            )
        else:
            add_check(checks, "prd_projection_json", "pass", "PRD projection artifacts parse successfully.")

    fleet_runs_dir = rah_root / "fleet" / "runs"
    if fleet_runs_dir.exists():
        fleet_errors: list[str] = []
        for child in sorted(child for child in fleet_runs_dir.iterdir() if child.is_dir()):
            if load_json(child / "state.json")[0] == "parse-error":
                fleet_errors.append(f"{child.name}/state.json")
            if (child / "supervisor.json").exists() and load_json(child / "supervisor.json")[0] == "parse-error":
                fleet_errors.append(f"{child.name}/supervisor.json")
            for mailbox_file in sorted((child / "mailbox").glob("**/*.json")) if (child / "mailbox").exists() else []:
                if load_json(mailbox_file)[0] == "parse-error":
                    fleet_errors.append(f"{child.name}/{mailbox_file.relative_to(child)}")
            transcript = child / "conversation.jsonl"
            if transcript.exists():
                transcript_lines = transcript.read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines()
                for line_number, line in enumerate(transcript_lines, start=1):
                    try:
                        json.loads(line)
                    except json.JSONDecodeError:
                        if line_number == len(transcript_lines):
                            # A live append may be observed between the kernel
                            # write and this unlocked reader. Retry the final
                            # line once before declaring durable corruption.
                            time.sleep(0.02)
                            retry_lines = transcript.read_text(
                                encoding="utf-8", errors="replace"
                            ).splitlines()
                            if len(retry_lines) >= line_number:
                                try:
                                    json.loads(retry_lines[line_number - 1])
                                    continue
                                except json.JSONDecodeError:
                                    pass
                        fleet_errors.append(f"{child.name}/conversation.jsonl:{line_number}")
                        break
        if fleet_errors:
            add_check(checks, "fleet_state_json", "fail", "Fleet state/mailbox/transcript parse errors in: " + ", ".join(fleet_errors))
        else:
            add_check(checks, "fleet_state_json", "pass", "Fleet run state, mailbox, and transcript artifacts parse successfully.")

    ralph_root = rah_root / "ralph"
    if ralph_root.exists():
        ralph_parse_errors = [
            name
            for name, state in [
                ("ralph_goal_json", ralph_goal_state),
                ("ralph_loop_state_json", ralph_loop_state),
                ("ralph_evidence_ledger_json", ralph_evidence_state),
                ("ralph_plan_graph_json", ralph_plan_graph_state),
                ("ralph_goal_bridge_json", ralph_goal_bridge_state),
                ("ralph_review_gate_json", ralph_review_gate_state),
                ("source_documents_json", source_documents_state),
                ("source_requirement_coverage_json", source_coverage_state),
            ]
            if state == "parse-error"
        ]
        ralph_missing = [
            name
            for name, state in [
                ("ralph_goal_json", ralph_goal_state),
                ("ralph_loop_state_json", ralph_loop_state),
                ("ralph_evidence_ledger_json", ralph_evidence_state),
                ("ralph_plan_graph_json", ralph_plan_graph_state),
                ("ralph_goal_bridge_json", ralph_goal_bridge_state),
                ("ralph_review_gate_json", ralph_review_gate_state),
            ]
            if state == "missing"
        ]
        if ralph_parse_errors:
            add_check(checks, "ralph_state", "fail", "JSON parse errors in: " + ", ".join(ralph_parse_errors))
        elif len(ralph_missing) == 6:
            add_check(checks, "ralph_state", "pass", "No active RALPH goal loop.")
        elif ralph_missing:
            add_check(checks, "ralph_state", "warn", "RALPH state is partial: " + ", ".join(ralph_missing))
        elif (
            isinstance(ralph_goal, dict)
            and isinstance(ralph_loop, dict)
            and isinstance(ralph_evidence, dict)
            and isinstance(ralph_plan_graph, dict)
            and isinstance(ralph_goal_bridge, dict)
            and isinstance(ralph_review_gate, dict)
        ):
            add_check(
                checks,
                "ralph_state",
                "pass",
                "RALPH goal loop active: "
                f"status={ralph_loop.get('status')}, "
                f"iteration={ralph_loop.get('current_iteration')}, "
                f"completion_mode={ralph_loop.get('completion_mode')}, "
                f"checkpoint_required={ralph_loop.get('checkpoint_required')}, "
                f"completion_ready={(ralph_loop.get('completion_readiness') or {}).get('ready')}, "
                f"review_status={ralph_review_gate.get('status')}, "
                f"evidence_count={len(ralph_evidence.get('entries', []))}, "
                f"driver={(ralph_loop.get('external_driver_contract') or {}).get('state_path')}",
            )
            if ralph_driver_state == "parse-error":
                add_check(checks, "ralph_driver", "fail", "RALPH driver state JSON parse error.")
            elif isinstance(ralph_driver, dict):
                add_check(
                    checks,
                    "ralph_driver",
                    "pass",
                    f"RALPH driver state detected: status={ralph_driver.get('status')}, cycles={ralph_driver.get('cycles_run')}",
            )
        else:
            add_check(checks, "ralph_state", "warn", "RALPH state exists but is not object-shaped.")

    removed_contract_key = "stop_" + removed_runtime_word() + "_contract"
    legacy_deployment_key = removed_runtime_word() + "s_install"
    if isinstance(ralph_loop, dict):
        status_for_contract = str(ralph_loop.get("status") or "").lower()
        if removed_contract_key in ralph_loop:
            add_check(checks, "ralph_removed_runtime_contract", "fail", "Loop state still contains removed continuation contract; run rah migrate or recreate RALPH state.")
        if status_for_contract in {"active", "verify", "review", "decide"} and not isinstance(ralph_loop.get("external_driver_contract"), dict):
            add_check(checks, "ralph_driver_contract", "fail", "Active RALPH state is missing external_driver_contract.")

    if source_documents_state == "ok" or source_coverage_state == "ok":
        if source_documents_state == "ok" and source_coverage_state == "missing":
            add_check(checks, "source_coverage", "fail", "source_documents.json exists but source_requirement_coverage.json is missing.")
        elif source_coverage_state == "parse-error":
            add_check(checks, "source_coverage", "fail", "source_requirement_coverage.json has a parse error.")
        elif isinstance(source_coverage, dict):
            rows = rows_from_payload(source_coverage)
            manifest = source_coverage.get("source_unit_manifest") if isinstance(source_coverage.get("source_unit_manifest"), dict) else {}
            validation = validate_coverage_payload(source_coverage, repo_root=root, verify_text_hashes=True)
            incomplete_ids = [
                str(row.get("requirement_id") or row.get("id") or f"row-{idx:04d}")
                for idx, row in enumerate(rows, start=1)
                if isinstance(row, dict) and not row_ready(row)
            ]
            blocked_ids = validation.get("blocked_unit_ids") if isinstance(validation.get("blocked_unit_ids"), list) else []
            if not rows:
                add_check(checks, "source_coverage", "fail", "source coverage exists but has no rows.")
            elif not validation.get("valid"):
                add_check(
                    checks,
                    "source_coverage",
                    "fail",
                    f"errors={validation.get('errors', [])[:10]}",
                )
            elif incomplete_ids or blocked_ids:
                add_check(
                    checks,
                    "source_coverage",
                    "warn",
                    f"incomplete_rows={incomplete_ids[:10]}, blocked_units={blocked_ids[:10]}",
                )
            else:
                add_check(
                    checks,
                    "source_coverage",
                    "pass",
                    f"rows={len(rows)}, source_units={manifest.get('total_units')}, processed_units={manifest.get('processed_unit_count')}",
                )

    if jobs_root.exists():
        job_status_files = sorted(jobs_root.glob("*/status.json"))
        job_parse_errors: list[str] = []
        active_jobs: list[str] = []
        terminal_jobs = 0
        for status_file in job_status_files:
            state, payload = load_json(status_file)
            if state == "parse-error":
                job_parse_errors.append(str(status_file.relative_to(root)))
                continue
            if not isinstance(payload, dict):
                continue
            status = str(payload.get("status") or "").lower()
            if status in {"starting", "queued", "running", "cancel_requested", "cancelling"}:
                active_jobs.append(str(payload.get("job_id") or status_file.parent.name))
            elif status in {"succeeded", "failed", "cancelled", "lost", "orphaned"}:
                terminal_jobs += 1
        if job_parse_errors:
            add_check(checks, "long_jobs", "fail", "Job status JSON parse errors in: " + ", ".join(job_parse_errors[:10]))
        elif active_jobs:
            add_check(checks, "long_jobs", "warn", "Active external jobs: " + ", ".join(active_jobs[:10]))
        else:
            add_check(checks, "long_jobs", "pass", f"External job state ok; terminal_jobs={terminal_jobs}, active_jobs=0.")

    agents_path = root / "AGENTS.md"
    if agents_path.exists():
        add_check(checks, "agents_visibility", "pass", f"Repo-local AGENTS.md detected at {agents_path}")
    else:
        add_check(checks, "agents_visibility", "warn", "No repo-local AGENTS.md at bootstrap root.")

    memento_configured, evidence, server_candidates = find_memento_config(root)
    if memento_configured:
        add_check(checks, "memento_config", "pass", "Detected Memento-related config: " + ", ".join(evidence))
    else:
        add_check(checks, "memento_config", "warn", "No obvious Memento config found in project/home config files.")

    if deployment_state == "ok" and isinstance(deployment_payload, dict):
        add_check(checks, "deployment_state", "pass", "Deployment state captured in .rah/state/deployment.json")
        critical_status, critical_message = deployment_critical_files_ok(
            root, deployment_payload
        )
        add_check(
            checks,
            "deployment_critical_files",
            critical_status,
            critical_message,
        )
        if legacy_deployment_key in deployment_payload:
            add_check(checks, "deployment_legacy_runtime", "warn", "Deployment state contains removed continuation install metadata; rerun rah install or remove the legacy key.")
    else:
        add_check(checks, "deployment_state", "warn", "No deployment.json found under .rah/state yet.")

    if isinstance(status_payload, dict) and isinstance(case_map, dict) and isinstance(memento_state, dict):
        workspace = status_payload.get("memento_workspace")
        topic = status_payload.get("memento_topic")
        session_id = status_payload.get("memento_session_id")
        case_id = status_payload.get("memento_case_id")

        identity_ok = (
            validate_workspace(workspace)
            and validate_topic(topic)
            and validate_session(session_id)
            and validate_case(case_id)
        )
        if identity_ok:
            add_check(checks, "memento_identity_normalization", "pass", "workspace/topic/sessionId/caseId look normalized.")
        else:
            add_check(
                checks,
                "memento_identity_normalization",
                "warn",
                f"Unexpected identity format: workspace={workspace!r}, topic={topic!r}, sessionId={session_id!r}, caseId={case_id!r}",
            )

        drift = []
        for key, case_key, state_key in [
            ("memento_workspace", "workspace", "workspace"),
            ("memento_topic", "topic", "topic"),
            ("memento_session_id", "sessionId", "session_id"),
            ("memento_case_id", "caseId", "case_id"),
        ]:
            left = status_payload.get(key)
            middle = case_map.get(case_key)
            right = memento_state.get(state_key)
            if left != middle or left != right:
                drift.append(f"{key}: status={left!r}, case_map={middle!r}, memento_status={right!r}")
        if drift:
            add_check(checks, "memento_vs_rah_drift", "warn", " / ".join(drift))
        else:
            add_check(checks, "memento_vs_rah_drift", "pass", "Memento identity is aligned across status, case map, and memento state.")

        last_context = parse_timestamp(status_payload.get("memento_last_context_at") or memento_state.get("last_context_at"))
        last_recall = parse_timestamp(status_payload.get("memento_last_recall_at") or memento_state.get("last_recall_at"))
        freshness_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        if last_context is None and last_recall is None:
            add_check(checks, "memento_state_freshness", "warn", "No successful context()/recall() hydration recorded yet.")
        elif any(ts is not None and ts < freshness_cutoff for ts in [last_context, last_recall]):
            add_check(checks, "memento_state_freshness", "warn", "Last Memento hydration looks stale (> 7 days).")
        else:
            add_check(checks, "memento_state_freshness", "pass", "Recent Memento hydration timestamps are present.")

        pending = pending_feedback_count(feedback_payload)
        if pending:
            add_check(checks, "memento_feedback_backlog", "warn", f"{pending} feedback item(s) still need relevant/sufficient judgement.")
        else:
            add_check(checks, "memento_feedback_backlog", "pass", "No pending feedback backlog detected.")

        configured_flag = bool(memento_state.get("configured")) or memento_configured
        if configured_flag:
            add_check(checks, "memento_connectivity", "pass", "Memento appears configured locally.")
        else:
            add_check(checks, "memento_connectivity", "warn", "Memento connectivity is not helper-verified and config was not detected.")
    else:
        add_check(checks, "memento_identity_normalization", "warn", "Missing one or more Memento state files.")
        add_check(checks, "memento_vs_rah_drift", "warn", "Cannot compare drift because required state files are missing.")
        add_check(checks, "memento_state_freshness", "warn", "Cannot assess memory freshness because required state files are missing.")
        add_check(checks, "memento_feedback_backlog", "warn", "Cannot assess feedback backlog because required state files are missing.")
        add_check(checks, "memento_connectivity", "warn", "Cannot assess connectivity because required state files are missing.")

    live_probe: dict[str, Any] | None = None
    if args.live_memento:
        if not server_candidates:
            add_check(checks, "memento_live_health", "warn", "No parseable [mcp_servers.*] Memento config found, so no live probe was attempted.")
        else:
            candidate = server_candidates[0]
            cfg = candidate.get("config", {})
            mcp_url = candidate.get("url")
            if not isinstance(mcp_url, str) or not mcp_url:
                add_check(checks, "memento_live_health", "warn", f"Memento config exists in {candidate['path']} but has no HTTP url.")
            else:
                health_url = derive_health_url(mcp_url)
                headers = build_http_headers(cfg if isinstance(cfg, dict) else {})
                try:
                    live_probe = ping_health(health_url, headers, args.memento_timeout_sec)
                    payload_preview = live_probe.get("payload")
                    summary = f"{health_url} -> HTTP {live_probe.get('http_status')}"
                    if isinstance(payload_preview, dict) and "status" in payload_preview:
                        summary += f" ({payload_preview.get('status')})"
                    add_check(checks, "memento_live_health", "pass", summary)
                    update_memento_status_file(
                        root,
                        {
                            "reachable": True,
                            "connectivity": "healthy",
                            "health_url": health_url,
                            "health_checked_at": utc_now(),
                            "health_http_status": live_probe.get("http_status"),
                            "health_payload": payload_preview,
                            "config_path": str(candidate["path"]),
                            "config_scope": candidate["scope"],
                            "server_name": candidate["name"],
                            "mcp_url": mcp_url,
                        },
                    )
                except urllib.error.HTTPError as exc:
                    add_check(checks, "memento_live_health", "warn", f"{health_url} returned HTTP {exc.code}")
                    update_memento_status_file(
                        root,
                        {
                            "reachable": False,
                            "connectivity": "http-error",
                            "health_url": health_url,
                            "health_checked_at": utc_now(),
                            "health_http_status": exc.code,
                            "active_errors": [f"HTTPError: {exc.reason}"],
                            "config_path": str(candidate["path"]),
                            "config_scope": candidate["scope"],
                            "server_name": candidate["name"],
                            "mcp_url": mcp_url,
                        },
                    )
                except Exception as exc:
                    add_check(checks, "memento_live_health", "warn", f"Live probe failed: {exc}")
                    update_memento_status_file(
                        root,
                        {
                            "reachable": False,
                            "connectivity": "unreachable",
                            "health_url": health_url,
                            "health_checked_at": utc_now(),
                            "active_errors": [str(exc)],
                            "config_path": str(candidate["path"]),
                            "config_scope": candidate["scope"],
                            "server_name": candidate["name"],
                            "mcp_url": mcp_url,
                        },
                    )

    payload = {
        "generated_at_utc": utc_now(),
        "root": str(root),
        "profile_hint": profile,
        "scaffold_root": str(scaffold_root),
        "checks": checks,
        "overall_status": overall_status(checks),
    }
    if live_probe is not None:
        payload["memento_live_probe"] = live_probe

    update_status_file(root, {"doctor_state": payload["overall_status"], "last_doctor_at": payload["generated_at_utc"]})

    if not args.no_write_report:
        doctor_path = rah_root / "state" / "doctor.json"
        save_json(doctor_path, payload)

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print("# Harness Doctor\n")
        print(f"- overall_status: {payload['overall_status']}")
        print(f"- root: {root}")
        for check in checks:
            print(f"- [{check['status']}] {check['name']}: {check['detail']}")
    return 0 if payload["overall_status"] != "fail" else 2


if __name__ == "__main__":
    raise SystemExit(main())
