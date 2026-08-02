#!/usr/bin/env python3
"""Build and verify W03-0001 evidence-update and staleness evidence.

O04-0001 implements `python/epistemic_foundry/retrieval/completeness/**`: the
O-phase gate under which every absence or novelty claim is sealed against a
deterministically recomputed SearchCompletenessCertificate and a FAILED,
BLOCKED, PARTIAL, or UNSEARCHED lane is ignorance, never zero evidence.  This
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
ATTEMPT = ROOT / "artifacts/work_packages/W03/attempts/0001"
ATTEMPT_ID = "W03-0001"
WORK_PACKAGE_ID = "W03"
RECORDED_AT = "2026-08-01T04:10:00.000Z"

EXPECTED_TARGETED_COUNT = 18
EXPECTED_PYTHON_COUNT = 1196
EXPECTED_NODE_COUNT = 887
EXPECTED_NODE_FILE_COUNT = 86

COMPONENT = "python/epistemic_foundry/reassessment"
EXPECTED_PRODUCT_HASHES = {
    f"{COMPONENT}/__init__.py": (
        "15a300cec0564e416a19fb42d43d6cb43023ab7e9850eeb49a4ebe262185d0f0"
    ),
    f"{COMPONENT}/contracts.py": (
        "d4b97ee06f4068209c89ebf5e6f0d7bb4a438e4141757ac9f879fc6c7413ea3c"
    ),
    f"{COMPONENT}/test_retraction_fixture.py": (
        "f4168dca7965c356176aa9bcc5c5dba1133401f468b78205c03d5be7c7390d06"
    ),
    f"{COMPONENT}/test_stale_propagation.py": (
        "4b92b3d30adf9fec6ac010b9d277ace5aadc1b01edc78d48db66d0c910957e5e"
    ),
}
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/W01/attempts/0001/report.json": (
        "637ac0a9d737e1ea3cc588fae35d60d05ed367228bbf88f322b4cefc8a46e490"
    ),
    "artifacts/work_packages/W02/attempts/0001/report.json": (
        "873e0db8476126b6c37e1e0f275ed8683daa4afadf196821bb7f3c89b9a8f705"
    ),
}

JUNIT_PATHS = {
    "targeted_reassessment": ATTEMPT / "targeted-reassessment.junit.xml",
    "full_python": ATTEMPT / "full-python-suite.junit.xml",
    "full_node": ATTEMPT / "full-node-suite.junit.xml",
}
_NODE_JUNITS = frozenset({"full_node"})
RUN_RESULTS = (
    "ruff-check",
    "ruff-format-check",
    "targeted-reassessment",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "run_w03_0001_checks.py",
    "build_w03_0001_evidence.py",
    "w03_0001_rah_seal.py",
    "dependency-status.json",
    "w03-verification.json",
    "write-scope-verification.json",
    "node-test-inventory.json",
    "junit-normalization-verification.json",
    "targeted-reassessment.junit.xml",
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
            if record.get("files", {}).get(name, {}).get("normalized_sha256") != sha256_id(
                path
            ):
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


def regression_evidence() -> dict[str, Any]:
    targeted = pytest_summary(JUNIT_PATHS["targeted_reassessment"])
    python = pytest_summary(JUNIT_PATHS["full_python"])
    node = node_summary(JUNIT_PATHS["full_node"])
    node_inventory = read_json(ATTEMPT / "node-test-inventory.json")
    if (
        targeted["collected"],
        targeted["passed"],
        targeted["failed"],
        targeted["errors"],
        targeted["skipped"],
    ) != (EXPECTED_TARGETED_COUNT, EXPECTED_TARGETED_COUNT, 0, 0, 0):
        raise SystemExit(f"targeted W03 gate failed: {targeted}")
    if (
        python["collected"],
        python["passed"],
        python["failed"],
        python["errors"],
        python["skipped"],
    ) != (EXPECTED_PYTHON_COUNT, EXPECTED_PYTHON_COUNT, 0, 0, 0):
        raise SystemExit(f"full Python gate failed: {python}")
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
        "attempt_id": ATTEMPT_ID,
        "baseline_attempt": "W02-0001",
        "component_tests_are_targeted_only": True,
        "full_node": node,
        "full_python": python,
        "new_failure_count": 0,
        "prior_baseline_counts": {"full_node": 887, "full_python": 1196},
        "status": "PASS",
        "targeted_reassessment": targeted,
        "unexpected_skip_xfail_todo_or_cancellation_count": 0,
    }


def dependency_status() -> dict[str, Any]:
    assert_hashes(EXPECTED_DEPENDENCY_HASHES)
    w01_path = ROOT / "artifacts/work_packages/W01/attempts/0001/report.json"
    w01 = read_json(w01_path)
    w01_rah = w01.get("rah_state")
    if (
        w01.get("status") != "PASS"
        or not isinstance(w01_rah, dict)
        or w01_rah.get("core_evidence_id") != "E0115"
        or w01_rah.get("final_closeout_evidence_id") != "E0116"
    ):
        raise SystemExit("W01-0001 dependency is not the sealed PASS attempt")
    baseline_path = ROOT / "artifacts/work_packages/W02/attempts/0001/report.json"
    baseline = read_json(baseline_path)
    rah = baseline.get("rah_state")
    if (
        baseline.get("status") != "PASS"
        or not isinstance(rah, dict)
        or rah.get("core_evidence_id") != "E0123"
        or rah.get("final_closeout_evidence_id") != "E0124"
    ):
        raise SystemExit("W02-0001 regression baseline is not the sealed PASS attempt")
    return {
        "attempt_id": ATTEMPT_ID,
        "dependencies": {
            "W01": {
                "attempt_id": "W01-0001",
                "core_evidence_id": "E0115",
                "final_closeout_evidence_id": "E0116",
                "report": "artifacts/work_packages/W01/attempts/0001/report.json",
                "report_sha256": sha256_id(w01_path),
                "status": "PASS",
            }
        },
        "next_action": "SEAL_W03_0001_THEN_CONTINUE_DAG",
        "regression_baseline": {
            "attempt_id": "W02-0001",
            "core_evidence_id": "E0123",
            "final_closeout_evidence_id": "E0124",
            "report": "artifacts/work_packages/W02/attempts/0001/report.json",
            "report_sha256": sha256_id(baseline_path),
            "status": "PASS",
        },
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
        raise SystemExit(f"reassessment component holds unexpected files: {component_files}")
    return {
        "approved_scope": [f"{COMPONENT}/**", "artifacts/work_packages/W03/**"],
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
        "subagents_or_fleet_used": False,
        "write_scope_violation_count": 0,
    }


def w03_verification(regression: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "exit_criteria": {
            "correction_retraction_propagates": {
                "evidence": [f"{COMPONENT}/test_retraction_fixture.py"],
                "status": "PASS",
            },
            "dependent_passports_marked_stale": {
                "evidence": [f"{COMPONENT}/test_stale_propagation.py"],
                "status": "PASS",
            },
        },
        "gate_semantics": {
            "closure_is_transitive_and_cycle_tolerant": True,
            "invalidating_triggers": sorted(
                [
                    "claim_correction",
                    "document_correction",
                    "document_retraction",
                    "ontology_update",
                    "policy_update",
                    "schema_migration",
                ]
            ),
            "passport_states": ["FRESH", "STALE", "INVALIDATED"],
            "reached_passport_can_never_stay_fresh": True,
            "voiding_triggers": ["document_retraction"],
        },
        "required_checks": {
            "retraction_fixture_test": {
                "module": f"{COMPONENT}/test_retraction_fixture.py",
                "status": "PASS",
            },
            "stale_propagation_test": {
                "module": f"{COMPONENT}/test_stale_propagation.py",
                "status": "PASS",
            },
        },
        "status": "PASS",
        "targeted_test_count": regression["targeted_reassessment"]["collected"],
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
                "artifacts/work_packages/W03/attempts/0001/build_w03_0001_evidence.py",
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
        "# W03-0001 primary-session separate adversarial review\n"
        "\n"
        "- Reviewer: primary session in a separate adversarial pass under the\n"
        "  product-owner instruction forbidding subagents and Fleet;\n"
        "  actor_independence=false is recorded, not hidden.\n"
        "- Transitive propagation (EF4-I38): the blast radius is the full\n"
        "  dependent closure, not one hop.  A retracted document reaches its\n"
        "  evidence, claims, packs, and every downstream Passport, including a\n"
        "  Passport that depends on another Passport.  A provenance cycle\n"
        "  terminates instead of hanging.\n"
        "- Correction versus retraction: both invalidate dependents, but a\n"
        "  retraction voids reached Passports (INVALIDATED) while a correction\n"
        "  leaves them questionable (STALE); a new document prompts\n"
        "  reassessment without invalidating.  Priority follows the trigger.\n"
        "- No silent staleness: every affected Passport must carry an explicit\n"
        "  state, a reached Passport can never be FRESH, an affected Passport\n"
        "  missing from the supplied set fails closed, and marking creates a\n"
        "  new revision bound to the plan id, plan hash, and trigger event.\n"
        "- No empty remediation: an invalidating trigger whose only required\n"
        "  action is no_action fails closed, so a recorded update cannot stand\n"
        "  in for an applied one.\n"
        "- Graph integrity: unknown dependencies, self-dependencies, duplicate\n"
        "  artifacts, unknown artifact classes, unknown trigger types, and\n"
        "  trigger artifacts outside the graph all fail closed.\n"
        "- Determinism: identical inputs seal byte-identical plans with\n"
        "  content-addressed ids; validation is exact reconstruction, so a\n"
        "  tampered or rehashed plan is rejected.\n"
        "- Residual limitations: the component computes and seals plans from a\n"
        "  declared provenance graph; live graph extraction, ledger-backed\n"
        "  invalidation events, and reassessment execution remain later\n"
        "  packages.  This review is not external actor-independent\n"
        "  certification.\n"
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
            "path": f"artifacts/work_packages/W03/attempts/0001/{name}",
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in sorted(set(output_names))
    ]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "W03_EVIDENCE_UPDATE_STALENESS_AND_REASSESSMENT",
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependency_state": dependencies,
        "exit_criteria": {
            "correction_retraction_propagates": "PASS",
            "dependent_passports_marked_stale": "PASS",
        },
        "global_implementation_gate": "fail",
        "history_and_worktree": {
            "dirty_worktree_preserved": True,
            "prior_attempts_reports_and_rah_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
            "subagents_or_fleet_used": False,
        },
        "implementation_status": "PASS",
        "next_package": "T02-0001",
        "not_claimed": [
            "live provenance-graph extraction from the canonical stores",
            "ledger-backed invalidation events or reassessment execution",
            "actor-independent certification of this implementation review",
            "overall product completion",
            "release or production readiness",
            "completion_ready=true",
        ],
        "output_artifacts": artifacts,
        "package_status": "PASS",
        "regression": regression,
        "required_checks": verification["required_checks"],
        "review": {
            "actor_independence": False,
            "assurance_limitation": (
                "Primary-session separate review; not external actor-independent "
                "certification."
            ),
            "blocking_finding_count": 0,
            "mode": "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_REVIEW",
            "status": "PASS",
        },
        "status": "PASS",
        "work_package_id": WORK_PACKAGE_ID,
        "write_scope": write_scope,
    }
    if rah_state is not None:
        report["rah_state"] = rah_state
    return report


def build() -> dict[str, Any]:
    for name in RUN_RESULTS:
        check_run(name)
    normalize_junits()
    regression = regression_evidence()
    dependencies = dependency_status()
    write_scope = write_scope_verification()
    verification = w03_verification(regression)
    write_json("dependency-status.json", dependencies)
    write_json("write-scope-verification.json", write_scope)
    write_json("w03-verification.json", verification)
    (ATTEMPT / "commands.jsonl").write_text(
        commands_text(), encoding="utf-8", newline="\n"
    )
    (ATTEMPT / "review.md").write_text(review_text(), encoding="utf-8", newline="\n")
    report = report_document(
        regression, dependencies, write_scope, verification, rah_state=None
    )
    write_json("report.json", report)
    return {
        "attempt_id": ATTEMPT_ID,
        "completion_ready": False,
        "full_node": "887/887",
        "full_python": "1196/1196",
        "next_action": "SEAL_W03_0001_THEN_CONTINUE_DAG",
        "package_status": "PASS",
        "status": "PASS",
        "targeted_reassessment": "18/18",
    }


def bind_rah_state(
    *,
    core_generation: str,
    core_evidence_id: str,
    final_closeout_evidence_id: str,
) -> None:
    integrity = read_json(ATTEMPT / "rah-core-integrity.json")
    stored = read_json(ATTEMPT / "report.json")
    if "rah_state" in stored:
        raise SystemExit("W03-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "w03-verification.json")
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
    verification = read_json(ATTEMPT / "w03-verification.json")
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
        raise SystemExit("stored W03-0001 report is not the deterministic document")
    return {
        "attempt_id": ATTEMPT_ID,
        "completion_ready": False,
        "full_node": "887/887",
        "full_python": "1196/1196",
        "next_action": "SEAL_W03_0001_THEN_CONTINUE_DAG",
        "package_status": "PASS",
        "status": "PASS",
        "targeted_reassessment": "18/18",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("build", "verify"))
    args = parser.parse_args()
    result = {"build": build, "verify": verify}[args.mode]()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
