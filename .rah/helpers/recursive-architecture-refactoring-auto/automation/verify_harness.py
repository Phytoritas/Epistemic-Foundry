#!/usr/bin/env python3
"""Self-contained package verifier (`rah.py verify`) — R1/R3-R7.

Turns "operator-reported" quality claims into one command an external
grader can rerun: manifest contract, compile/import health, full pytest
with a test-ID baseline (supersets allowed, silent loss fails), dual-tree
parity by exact manifest, byte contracts, and the measured performance
contract. Every step is journaled into a hash-chained ``events.jsonl`` and
an ``attestation.json`` binding the whole artifact bundle; ``--replay``
re-derives every hash so a single flipped byte in the bundle is detected.

The chain proves post-hoc integrity of a bundle, not the runner's honesty —
the authoritative act is the grader rerunning the same command in a clean
checkout. Exit contract: 0 = every required check passed; 1 = a contract
gate failed; 2 = verifier/internal/environment error. Required checks that
cannot run are failures (exit 2), never silent successes.
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
except Exception:  # stale helper tree may predate cli_suggestions
    _SuggestingArgumentParser = argparse.ArgumentParser

import hashlib
import json
import os
import py_compile
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import managed_manifest

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
TEST_ID_BASELINE = "tests/test_id_baseline.txt"
SKILL_BYTE_CEILING = 16_000
SKILL_MIN_HEADROOM = 2_000
REFERENCE_TOTAL_BYTE_CEILING = 65_536
HELP_MS_CONTRACT = 300
STATUS_MS_CONTRACT = 800
PERF_SAMPLES = 7
PYTEST_TIMEOUT_SECONDS = 2400


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class EventLog:
    """Hash-chained step journal (seq + prev_record_sha256)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.prev = "0" * 64
        self.seq = 0
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")

    def record(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.seq += 1
        record = {"seq": self.seq, "prev_record_sha256": self.prev, **payload}
        canonical = json.dumps(record, ensure_ascii=False, sort_keys=True)
        record_hash = sha256_bytes(canonical.encode("utf-8"))
        record["record_sha256"] = record_hash
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        self.prev = record_hash
        return record


def run_step(
    events: EventLog,
    name: str,
    cmd: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 600,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    started = utc_now()
    t0 = time.perf_counter()
    try:
        completed = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
        )
        result = {
            "exit_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        result = {
            "exit_code": None,
            "stdout": (exc.stdout or b"").decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or ""),
            "stderr": (exc.stderr or b"").decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else (exc.stderr or ""),
            "timed_out": True,
        }
    events.record(
        {
            "step": name,
            "command": cmd,
            "started_at_utc": started,
            "ended_at_utc": utc_now(),
            "duration_ms": round((time.perf_counter() - t0) * 1000),
            "exit_code": result["exit_code"],
            "timed_out": result["timed_out"],
            "stdout_sha256": sha256_bytes(result["stdout"].encode("utf-8")),
            "stderr_sha256": sha256_bytes(result["stderr"].encode("utf-8")),
        }
    )
    return result


def check_manifest(root: Path, events: EventLog) -> dict[str, Any]:
    try:
        report = managed_manifest.verify_tree(root)
    except managed_manifest.ManifestError as exc:
        return {"name": "manifest", "status": "error", "error": str(exc)}
    status = "pass" if report["in_contract"] else "fail"
    events.record({"step": "manifest", "status": status, "root_digest": report["root_digest"]})
    return {"name": "manifest", "status": status, "report": report}


def check_compile(root: Path, events: EventLog) -> dict[str, Any]:
    failures: list[dict[str, str]] = []
    count = 0
    for rel_dir in ("automation", "tests"):
        for path in sorted((root / rel_dir).glob("*.py")):
            count += 1
            try:
                py_compile.compile(str(path), doraise=True)
            except py_compile.PyCompileError as exc:
                failures.append({"path": str(path.relative_to(root)), "error": str(exc)[:400]})
    status = "pass" if not failures else "fail"
    events.record({"step": "compile", "status": status, "files": count, "failures": len(failures)})
    return {"name": "compile", "status": status, "files": count, "failures": failures}


def check_byte_contracts(root: Path, events: EventLog) -> dict[str, Any]:
    skill = root / "SKILL.md"
    size = len(skill.read_bytes()) if skill.is_file() else -1
    ok = 0 < size <= SKILL_BYTE_CEILING - SKILL_MIN_HEADROOM
    events.record({"step": "byte-contracts", "skill_bytes": size, "ceiling": SKILL_BYTE_CEILING, "status": "pass" if ok else "fail"})
    return {
        "name": "byte-contracts",
        "status": "pass" if ok else "fail",
        "skill_bytes": size,
        "ceiling": SKILL_BYTE_CEILING,
        "headroom": SKILL_BYTE_CEILING - size,
    }


def collect_test_ids(root: Path, events: EventLog) -> tuple[list[str] | None, dict[str, Any]]:
    result = run_step(
        events,
        "pytest-collect",
        [sys.executable, "-B", "-m", "pytest", "tests", "--collect-only", "-q"],
        cwd=root,
        timeout=300,
    )
    if result["timed_out"] or result["exit_code"] not in (0,):
        return None, {"name": "test-baseline", "status": "error", "detail": "collection failed", "stderr": result["stderr"][-800:]}
    ids = [
        line.strip()
        for line in result["stdout"].splitlines()
        if line.strip() and "::" in line and not line.startswith(("=", "warning", "no tests"))
    ]
    baseline_path = root / TEST_ID_BASELINE
    if not baseline_path.is_file():
        return ids, {"name": "test-baseline", "status": "fail", "detail": f"missing {TEST_ID_BASELINE}"}
    baseline = {
        line.strip()
        for line in baseline_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }
    current = set(ids)
    lost = sorted(baseline - current)
    status = "pass" if not lost else "fail"
    events.record({"step": "test-baseline", "baseline": len(baseline), "collected": len(current), "lost": len(lost), "status": status})
    return ids, {
        "name": "test-baseline",
        "status": status,
        "baseline_count": len(baseline),
        "collected_count": len(current),
        "lost_ids": lost[:50],
        "new_count": len(current - baseline),
    }


def check_pytest(root: Path, events: EventLog, artifacts: Path) -> dict[str, Any]:
    junit = artifacts / "tests.junit.xml"
    result = run_step(
        events,
        "pytest-full",
        [sys.executable, "-B", "-m", "pytest", "tests", "-q", f"--junit-xml={junit}"],
        cwd=root,
        timeout=PYTEST_TIMEOUT_SECONDS,
    )
    (artifacts / "pytest.stdout.txt").write_text(result["stdout"], encoding="utf-8")
    (artifacts / "pytest.stderr.txt").write_text(result["stderr"], encoding="utf-8")
    if result["timed_out"]:
        return {"name": "pytest", "status": "fail", "detail": f"suite exceeded {PYTEST_TIMEOUT_SECONDS}s", "tail": result["stdout"][-500:]}
    status = "pass" if result["exit_code"] == 0 else "fail"
    tail = result["stdout"].strip().splitlines()[-1] if result["stdout"].strip() else ""
    return {"name": "pytest", "status": status, "exit_code": result["exit_code"], "summary": tail}


def check_dual_tree_parity(root: Path, events: EventLog) -> dict[str, Any]:
    mirror = Path.home() / ".claude" / "skills" / root.name
    if not mirror.is_dir():
        events.record({"step": "parity", "status": "skip", "detail": "mirror absent"})
        return {"name": "parity", "status": "skip", "detail": "mirror absent (single-host install)", "required": False}
    try:
        manifest = managed_manifest.load_manifest(root)
        local = managed_manifest.verify_tree(root, manifest)
        remote = managed_manifest.verify_tree(mirror, manifest)
    except managed_manifest.ManifestError as exc:
        return {"name": "parity", "status": "error", "error": str(exc)}
    manifest_equal = (root / managed_manifest.MANIFEST_NAME).read_bytes() == (
        mirror / managed_manifest.MANIFEST_NAME
    ).read_bytes() if (mirror / managed_manifest.MANIFEST_NAME).is_file() else False
    ok = local["in_contract"] and remote["in_contract"] and manifest_equal
    events.record({"step": "parity", "status": "pass" if ok else "fail"})
    detail = {
        "name": "parity",
        "status": "pass" if ok else "fail",
        "canonical": {"in_contract": local["in_contract"], "findings": local["findings"]},
        "mirror": {"in_contract": remote["in_contract"], "findings": remote["findings"]},
        "manifest_files_equal": manifest_equal,
    }
    return detail


def _median_ms(cmd_args: list[str], samples: int, cwd: Path | None = None) -> dict[str, Any]:
    times: list[float] = []
    failures = 0
    for _ in range(samples):
        t0 = time.perf_counter()
        completed = subprocess.run(cmd_args, capture_output=True, cwd=str(cwd) if cwd else None)
        times.append((time.perf_counter() - t0) * 1000)
        if completed.returncode != 0:
            failures += 1
    ordered = sorted(times)
    return {
        "samples_ms": [round(x) for x in times],
        "median_ms": round(statistics.median(times)),
        "p95_ms": round(ordered[max(0, int(len(ordered) * 0.95) - 1)]),
        # Reviewer finding: an instantly-crashing command must never count as
        # fast success — callers gate on this.
        "nonzero_exits": failures,
    }


def check_performance(root: Path, events: EventLog) -> dict[str, Any]:
    rah = root / "automation" / "rah.py"
    help_stats = _median_ms([sys.executable, "-B", str(rah), "--help"], PERF_SAMPLES)
    with tempfile.TemporaryDirectory(prefix="rah-verify-perf-") as tmp:
        status_stats = _median_ms([sys.executable, "-B", str(rah), "status", tmp], PERF_SAMPLES)
    ok = (
        help_stats["median_ms"] <= HELP_MS_CONTRACT
        and status_stats["median_ms"] <= STATUS_MS_CONTRACT
        and help_stats["nonzero_exits"] == 0
        and status_stats["nonzero_exits"] == 0
    )
    events.record(
        {
            "step": "performance",
            "help_median_ms": help_stats["median_ms"],
            "status_median_ms": status_stats["median_ms"],
            "status": "pass" if ok else "fail",
        }
    )
    return {
        "name": "performance",
        "status": "pass" if ok else "fail",
        "help": {**help_stats, "contract_ms": HELP_MS_CONTRACT},
        "status_cmd": {**status_stats, "contract_ms": STATUS_MS_CONTRACT},
        "method": "subprocess wall-clock, cold interpreter per call",
        "platform": {"python": sys.version.split()[0], "os": os.name, "platform": sys.platform},
    }


def check_usability(root: Path, events: EventLog) -> dict[str, Any]:
    """R37: the usability surface as a numeric, gated contract."""

    import importlib.util as _ilu

    rah = root / "automation" / "rah.py"
    metrics: dict[str, Any] = {"schema": "rah-usability-v1"}
    failures: list[str] = []

    # Bounds are two-sided and exit codes are gated (reviewer finding: an
    # instantly-crashing help printed 0 verbs/0 options and passed every
    # upper bound).
    help_run = subprocess.run(
        [sys.executable, "-B", str(rah), "--help"], capture_output=True, text=True, encoding="utf-8"
    )
    if help_run.returncode != 0:
        failures.append(f"rah --help exited {help_run.returncode}")
    help_out = help_run.stdout
    listed = [
        line.split()[0]
        for line in help_out.splitlines()
        if line.startswith("  ") and line.strip() and not line.strip().startswith("-")
    ]
    metrics["public_verbs"] = len(listed)
    if len(listed) != 4:
        failures.append(f"public verbs {listed} (expected exactly 4)")

    run_help_run = subprocess.run(
        [sys.executable, "-B", str(rah), "run", "--help"], capture_output=True, text=True, encoding="utf-8"
    )
    if run_help_run.returncode != 0:
        failures.append(f"rah run --help exited {run_help_run.returncode}")
    run_help = run_help_run.stdout
    run_options = [
        line.strip().split()[0]
        for line in run_help.splitlines()
        if line.strip().startswith("--")
    ]
    metrics["run_default_options"] = len(run_options)
    if not 4 <= len(run_options) <= 8:
        failures.append(f"run curated options {run_options} (expected 4..8)")

    references = sorted((root / "references").glob("*.md"))
    metrics["human_reference_documents"] = len(references)
    reference_total = sum(ref.stat().st_size for ref in references)
    metrics["human_reference_total_bytes"] = reference_total
    if not 1 <= len(references) <= 7:
        failures.append(f"{len(references)} reference documents (expected 1..7)")
    if reference_total > REFERENCE_TOTAL_BYTE_CEILING:
        failures.append(
            f"references total {reference_total}B exceeds ceiling {REFERENCE_TOTAL_BYTE_CEILING}B"
        )

    skill_bytes = len((root / "SKILL.md").read_bytes())
    metrics["skill_bytes"] = skill_bytes
    metrics["skill_headroom_bytes"] = SKILL_BYTE_CEILING - skill_bytes
    if skill_bytes > SKILL_BYTE_CEILING - SKILL_MIN_HEADROOM:
        failures.append(f"SKILL.md {skill_bytes}B breaks the headroom contract")

    registry = json.loads((root / "contract-registry.json").read_text(encoding="utf-8"))
    rules = registry.get("legacy_rules", {})
    baseline = set((root / TEST_ID_BASELINE).read_text(encoding="utf-8").split())
    mapped = 0
    for rule_id, spec in rules.items():
        ok = spec.get("invariant") in registry.get("invariants", {})
        if spec.get("enforcement_type") == "gate":
            ok = ok and bool(spec.get("negative_tests")) and all(
                test_id in baseline for test_id in spec["negative_tests"]
            )
        mapped += 1 if ok else 0
    metrics["legacy_rules_expected"] = 18
    metrics["legacy_rules_mapped"] = mapped
    if mapped != 18 or len(rules) != 18:
        failures.append(f"legacy rule mapping {mapped}/18")

    # sibling suggestion leak: a dispatch-only flag typo under `status` must
    # not be advertised as a drop-in
    leak = subprocess.run(
        [sys.executable, "-B", str(root / "automation" / "fleet_harness.py"), "x", "status", "--modle"],
        capture_output=True, text=True, encoding="utf-8",
    )
    leak_output = leak.stdout + leak.stderr
    leaked = "did you mean --model or" in leak_output or (
        "did you mean --model?" in leak_output and "valid under" not in leak_output
    )
    metrics["sibling_option_leaks"] = 1 if leaked else 0
    if leaked:
        failures.append("sibling suggestion leak")

    # facade equivalence: verbs and legacy names resolve identically
    spec_obj = _ilu.spec_from_file_location("rah_usability_facade", rah)
    module = _ilu.module_from_spec(spec_obj)
    sys.modules[spec_obj.name] = module
    equivalence_failures = 0
    try:
        spec_obj.loader.exec_module(module)
        pairs = [
            (("run", ["r", "--goal", "g"]), ("autopilot", ["r", "--goal", "g"])),
            (("inspect", ["r"]), ("status", ["r"])),
            (("inspect", ["r", "--doctor"]), ("doctor", ["r"])),
            (("inspect", ["r", "--resume"]), ("resume", ["r"])),
            (("admin", ["parity", "--json"]), ("parity", ["--json"])),
        ]
        for (verb, verb_args), (legacy, legacy_args) in pairs:
            verb_result = module._resolve_dispatch(verb, verb_args)
            legacy_result = module._resolve_dispatch(legacy, legacy_args)
            if verb_result[1] != legacy_result[1] or verb_result[2] != legacy_result[2]:
                equivalence_failures += 1
    finally:
        sys.modules.pop(spec_obj.name, None)
    metrics["legacy_equivalence_failures"] = equivalence_failures
    if equivalence_failures:
        failures.append(f"{equivalence_failures} facade equivalence failures")

    status = "pass" if not failures else "fail"
    events.record({"step": "usability", "status": status, **{k: v for k, v in metrics.items() if isinstance(v, (int, str))}})
    return {"name": "usability", "status": status, "metrics": metrics, "failures": failures}


def write_bundle(artifacts: Path, payload: dict[str, Any], events: EventLog) -> dict[str, Any]:
    result_path = artifacts / "verify-result.json"
    result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    env_path = artifacts / "environment.json"
    env_allowlist = {
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "os_name": os.name,
        "cwd_is_package": str(PACKAGE_ROOT),
    }
    env_path.write_text(json.dumps(env_allowlist, ensure_ascii=False, indent=1), encoding="utf-8")
    files = []
    for path in sorted(artifacts.rglob("*")):
        if path.is_file() and path.name != "attestation.json":
            files.append(
                {
                    "path": path.relative_to(artifacts).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_bytes(path.read_bytes()),
                }
            )
    canonical = json.dumps([(f["path"], f["bytes"], f["sha256"]) for f in files], sort_keys=True)
    attestation = {
        "schema": "rah-verify-attestation/v1",
        "created_at_utc": utc_now(),
        "event_chain_head": events.prev,
        "bundle_root_sha256": sha256_bytes(canonical.encode("utf-8")),
        "files": files,
        "note": "hash chain proves post-hoc bundle integrity only; authority is rerunning verify in a clean checkout",
    }
    (artifacts / "attestation.json").write_text(
        json.dumps(attestation, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return attestation


def replay_bundle(bundle: Path) -> int:
    att_path = bundle / "attestation.json"
    if not att_path.is_file():
        print(json.dumps({"error": "missing attestation.json"}, ensure_ascii=False))
        return 2
    attestation = json.loads(att_path.read_text(encoding="utf-8"))
    mismatches: list[dict[str, Any]] = []
    listed = {str(spec.get("path")) for spec in attestation.get("files", [])}
    for path in sorted(bundle.rglob("*")):
        if path.is_file() and path.name != "attestation.json":
            rel = path.relative_to(bundle).as_posix()
            if rel not in listed:
                # Reviewer finding: unlisted extras were silently ignored.
                mismatches.append({"path": rel, "error": "unlisted extra file"})
    for spec in attestation.get("files", []):
        path = bundle / spec["path"]
        if not path.is_file():
            mismatches.append({"path": spec["path"], "error": "missing"})
            continue
        actual = sha256_bytes(path.read_bytes())
        if actual != spec["sha256"]:
            mismatches.append({"path": spec["path"], "expected": spec["sha256"], "actual": actual})
    # Reviewer finding: the attestation's own root field was never
    # recomputed, so editing bundle_root_sha256 (or the files list wholesale)
    # went unnoticed. Recompute from the LISTED entries; the trust anchor for
    # a wholly-rewritten attestation stays the externally recorded root
    # digest (evidence ledger / report), which is exactly what this value
    # feeds.
    canonical = json.dumps(
        [(f["path"], f["bytes"], f["sha256"]) for f in attestation.get("files", [])],
        sort_keys=True,
    )
    recomputed_root = sha256_bytes(canonical.encode("utf-8"))
    root_ok = recomputed_root == attestation.get("bundle_root_sha256")
    if not root_ok:
        mismatches.append(
            {
                "path": "attestation.json",
                "error": "bundle_root_sha256 does not match its own files list",
                "expected": attestation.get("bundle_root_sha256"),
                "actual": recomputed_root,
            }
        )
    events_path = bundle / "events.jsonl"
    chain_ok = True
    prev = "0" * 64
    if events_path.is_file():
        for line in events_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            claimed = record.pop("record_sha256", None)
            if record.get("prev_record_sha256") != prev:
                chain_ok = False
                break
            canonical = json.dumps(record, ensure_ascii=False, sort_keys=True)
            if sha256_bytes(canonical.encode("utf-8")) != claimed:
                chain_ok = False
                break
            prev = claimed
        if chain_ok and prev != attestation.get("event_chain_head"):
            chain_ok = False
    else:
        chain_ok = False
    ok = not mismatches and chain_ok
    print(
        json.dumps(
            {
                "operation": "replay",
                "bundle": str(bundle),
                "files_checked": len(attestation.get("files", [])),
                "mismatches": mismatches[:20],
                "event_chain_valid": chain_ok,
                "bundle_root_sha256": attestation.get("bundle_root_sha256"),
                "trust_anchor": (
                    "attestation-relative: compare bundle_root_sha256 against the externally "
                    "recorded digest (evidence ledger / report) to defeat wholesale rewrites"
                ),
                "verified": ok,
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    return 0 if ok else 1


def main() -> int:
    parser = _SuggestingArgumentParser(description="Self-contained RAH package verifier with a replayable evidence bundle.")
    parser.add_argument("--tier", choices=["smoke", "full"], default="smoke", help="smoke: manifest/compile/byte contracts. full: adds pytest+baseline, dual-tree parity, performance.")
    parser.add_argument("--artifacts-dir", default=None, help="Bundle output directory (default: ./verify-artifacts-<utc>).")
    parser.add_argument("--replay", default=None, help="Verify an existing bundle instead of running checks.")
    parser.add_argument("--usability", action="store_true", help="Also run the numeric usability contract (R37).")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.replay:
        return replay_bundle(Path(args.replay).expanduser().resolve())

    root = PACKAGE_ROOT
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    artifacts = Path(args.artifacts_dir).expanduser().resolve() if args.artifacts_dir else Path.cwd() / f"verify-artifacts-{stamp}"
    artifacts.mkdir(parents=True, exist_ok=True)
    events = EventLog(artifacts / "events.jsonl")
    events.record({"step": "start", "tier": args.tier, "package_root": str(root), "started_at_utc": utc_now()})

    checks: list[dict[str, Any]] = []
    checks.append(check_manifest(root, events))
    checks.append(check_compile(root, events))
    checks.append(check_byte_contracts(root, events))

    if args.usability:
        checks.append(check_usability(root, events))
    if args.tier == "full":
        ids, baseline_check = collect_test_ids(root, events)
        checks.append(baseline_check)
        if ids is not None:
            (artifacts / "test-ids.txt").write_text("\n".join(ids) + "\n", encoding="utf-8")
        checks.append(check_pytest(root, events, artifacts))
        checks.append(check_dual_tree_parity(root, events))
        checks.append(check_performance(root, events))

    errors = [c for c in checks if c.get("status") == "error"]
    failures = [c for c in checks if c.get("status") == "fail"]
    # A skip counts as success ONLY when the check explicitly declared itself
    # optional (reviewer finding: a generic skip==pass rule would let a
    # required check opt out silently).
    passed = (
        all(
            c.get("status") == "pass"
            or (c.get("status") == "skip" and c.get("required") is False)
            for c in checks
        )
        and not errors
    )
    payload = {
        "schema": "rah-verify-result/v1",
        "tier": args.tier,
        "generated_at_utc": utc_now(),
        "package_root": str(root),
        "checks": checks,
        "passed": passed,
        "failed_checks": [c["name"] for c in failures],
        "error_checks": [c["name"] for c in errors],
        "reproduce": f"python automation/rah.py verify --tier {args.tier} --artifacts-dir <dir>",
    }
    attestation = write_bundle(artifacts, payload, events)
    payload["bundle_root_sha256"] = attestation["bundle_root_sha256"]
    payload["artifacts_dir"] = str(artifacts)
    print(json.dumps(payload if args.json else {k: v for k, v in payload.items() if k != "checks"} | {"checks": [{"name": c["name"], "status": c["status"]} for c in checks]}, ensure_ascii=False, indent=1))
    if errors:
        return 2
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
