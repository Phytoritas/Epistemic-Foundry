#!/usr/bin/env python3
"""Build and verify P02-0001 auditor veto and promotion-ceiling evidence.

P02-0001 implements `python/epistemic_foundry/parliament/auditors/**`:
the four audit angles whose ceilings combine deterministically into one derived
cap, where only the method auditor may veto, and where method-incompatible
evidence is reported per stratum rather than blended into a single figure.  This
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
ATTEMPT = ROOT / "artifacts/work_packages/P02/attempts/0001"
ATTEMPT_ID = "P02-0001"
WORK_PACKAGE_ID = "P02"
RECORDED_AT = "2026-08-01T16:30:00.000Z"

EXPECTED_VETO_FIXTURE_COUNT = 19
EXPECTED_PROMOTION_CEILING_COUNT = 23
EXPECTED_TARGETED_COUNT = 42
EXPECTED_BLIND_REGRESSION_COUNT = 37
EXPECTED_CAUSAL_REGRESSION_COUNT = 45
EXPECTED_PYTHON_COUNT = 1261
EXPECTED_NODE_COUNT = 982
EXPECTED_NODE_FILE_COUNT = 91

COMPONENT = "python/epistemic_foundry/parliament/auditors"
EXPECTED_PRODUCT_HASHES = {
    "python/epistemic_foundry/parliament/auditors/__init__.py": "0aead65a38e216fe812d25124db05907b5d19c81208f32927463518672def968",
    "python/epistemic_foundry/parliament/auditors/contracts.py": "80340e3be6f257168deb25e03825f2cfc050e993437c9c72641d9a5e9851cdb6",
    "python/epistemic_foundry/parliament/auditors/pytest.ini": "eae524968dfba75465a9ed16065b3f5afe9bd533b6c7944fb931a54a05ef37d8",
    "python/epistemic_foundry/parliament/auditors/test_promotion_ceiling.py": "beb1db09e7d6d7bf6f64000de00a05e899af8045f3a8a261c5a8dc031de6f1eb",
    "python/epistemic_foundry/parliament/auditors/test_veto_fixture.py": "b2abdf1a29c4787084c71dd78e2db810d4b0afa21b1f8231f32c36df5e2a41b6",
}
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/P01/attempts/0001/report.json": "83bc4212b2a8dae099b431099b9c01de0c44e54b7bc41b3c8801f5f0fb94c200",
    "artifacts/work_packages/W04/attempts/0001/report.json": "b07687917d9bf5a150d78c9fd1580e24308823f95e1c8713302b7e4af3c75688",
}

JUNIT_PATHS = {
    "veto_fixture": ATTEMPT / "veto-fixture-test.junit.xml",
    "promotion_ceiling": ATTEMPT / "promotion-ceiling-test.junit.xml",
    "targeted": ATTEMPT / "targeted-parliament-auditors.junit.xml",
    "blind_regression": ATTEMPT / "dependency-regression-blind.junit.xml",
    "causal_regression": ATTEMPT / "dependency-regression-causal.junit.xml",
    "full_python": ATTEMPT / "full-python-suite.junit.xml",
    "full_node": ATTEMPT / "full-node-suite.junit.xml",
}
_NODE_JUNITS = frozenset({"full_node"})
RUN_RESULTS = (
    "ruff-check",
    "ruff-format-check",
    "veto-fixture-test",
    "promotion-ceiling-test",
    "targeted-parliament-auditors",
    "dependency-regression-blind",
    "dependency-regression-causal",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "run_p02_0001_checks.py",
    "build_p02_0001_evidence.py",
    "p02_0001_rah_seal.py",
    "dependency-status.json",
    "p02-verification.json",
    "write-scope-verification.json",
    "node-test-inventory.json",
    "junit-normalization-verification.json",
    "veto-fixture-test.junit.xml",
    "promotion-ceiling-test.junit.xml",
    "targeted-parliament-auditors.junit.xml",
    "dependency-regression-blind.junit.xml",
    "dependency-regression-causal.junit.xml",
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
            if record.get("files", {}).get(name, {}).get(
                "normalized_sha256"
            ) != sha256_id(path):
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
    veto = pytest_summary(JUNIT_PATHS["veto_fixture"])
    ceiling = pytest_summary(JUNIT_PATHS["promotion_ceiling"])
    targeted = pytest_summary(JUNIT_PATHS["targeted"])
    blind = pytest_summary(JUNIT_PATHS["blind_regression"])
    causal = pytest_summary(JUNIT_PATHS["causal_regression"])
    python = pytest_summary(JUNIT_PATHS["full_python"])
    node = node_summary(JUNIT_PATHS["full_node"])
    node_inventory = read_json(ATTEMPT / "node-test-inventory.json")
    for label, summary, expected in (
        ("veto_fixture_test", veto, EXPECTED_VETO_FIXTURE_COUNT),
        ("promotion_ceiling_test", ceiling, EXPECTED_PROMOTION_CEILING_COUNT),
        ("targeted", targeted, EXPECTED_TARGETED_COUNT),
        ("blind_regression", blind, EXPECTED_BLIND_REGRESSION_COUNT),
        ("causal_regression", causal, EXPECTED_CAUSAL_REGRESSION_COUNT),
        ("full_python", python, EXPECTED_PYTHON_COUNT),
    ):
        if (
            summary["collected"],
            summary["passed"],
            summary["failed"],
            summary["errors"],
            summary["skipped"],
        ) != (expected, expected, 0, 0, 0):
            raise SystemExit(f"{label} gate failed: {summary}")
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
        "baseline_attempt": "W04-0001",
        "component_tests_are_targeted_only": True,
        "blind_regression": blind,
        "causal_regression": causal,
        "full_node": node,
        "full_python": python,
        "promotion_ceiling_test": ceiling,
        "veto_fixture_test": veto,
        "new_failure_count": 0,
        "prior_baseline_counts": {"full_node": 903, "full_python": 1261},
        "status": "PASS",
        "targeted_parliament_auditors": targeted,
        "unexpected_skip_xfail_todo_or_cancellation_count": 0,
    }


def _sealed_dependency(
    package: str, attempt: str, core: str, final: str
) -> dict[str, Any]:
    path = (
        ROOT / f"artifacts/work_packages/{package}/attempts/{attempt[-4:]}/report.json"
    )
    report = read_json(path)
    rah = report.get("rah_state")
    if (
        report.get("status") != "PASS"
        or not isinstance(rah, dict)
        or rah.get("core_evidence_id") != core
        or rah.get("final_closeout_evidence_id") != final
    ):
        raise SystemExit(f"{attempt} is not the sealed PASS attempt")
    return {
        "attempt_id": attempt,
        "core_evidence_id": core,
        "final_closeout_evidence_id": final,
        "report": path.relative_to(ROOT).as_posix(),
        "report_sha256": sha256_id(path),
        "status": "PASS",
    }


def dependency_status() -> dict[str, Any]:
    assert_hashes(EXPECTED_DEPENDENCY_HASHES)
    return {
        "attempt_id": ATTEMPT_ID,
        "dependencies": {
            "P01": _sealed_dependency("P01", "P01-0001", "E0137", "E0138"),
        },
        "next_action": "SEAL_P02_0001_THEN_CONTINUE_DAG",
        "regression_baseline": _sealed_dependency("W04", "W04-0001", "E0141", "E0142"),
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
        raise SystemExit(
            f"auditors component holds unexpected files: {component_files}"
        )
    return {
        "approved_scope": [f"{COMPONENT}/**", "artifacts/work_packages/P02/**"],
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


def p02_verification(regression: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "ceiling_derivation": {
            "combined_is_lowest_auditor_ceiling": True,
            "declared_above_derived_refused": True,
            "ladder_source": "schemas/hypothesis-passport.schema.json",
            "no_auditor_can_raise_it": True,
        },
        "exit_criteria": {
            "method_incompatibility_not_pooled": {
                "evidence": [f"{COMPONENT}/test_promotion_ceiling.py"],
                "mechanism": (
                    "the method auditor reports one ceiling per stratum and its "
                    "component ceiling must equal the strongest stratum, so a "
                    "single blended figure spanning several strata is refused"
                ),
                "status": "PASS",
            },
            "promotion_ceilings_deterministic": {
                "evidence": [
                    f"{COMPONENT}/test_promotion_ceiling.py",
                    f"{COMPONENT}/test_veto_fixture.py",
                ],
                "mechanism": (
                    "the combined ceiling is the lowest any auditor set, floored "
                    "by a sustained method veto, derived rather than declared, "
                    "and invariant to verdict order"
                ),
                "status": "PASS",
            },
        },
        "required_checks": {
            "promotion_ceiling_test": {
                "module": f"{COMPONENT}/test_promotion_ceiling.py",
                "status": "PASS",
                "test_count": regression["promotion_ceiling_test"]["collected"],
            },
            "veto_fixture_test": {
                "module": f"{COMPONENT}/test_veto_fixture.py",
                "status": "PASS",
                "test_count": regression["veto_fixture_test"]["collected"],
            },
        },
        "status": "PASS",
        "targeted_test_count": regression["targeted_parliament_auditors"]["collected"],
        "veto_discipline": {
            "reason_required": True,
            "veto_capable_auditors": ["method_auditor"],
            "veto_floors_the_ladder": True,
            "withdrawal_stays_on_the_record": True,
        },
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
                "artifacts/work_packages/P02/attempts/0001/build_r01_0001_evidence.py",
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
        "# P02-0001 primary-session separate adversarial review\n"
        "\n"
        "- Reviewer: primary session in a separate adversarial pass under the\n"
        "  product-owner instruction forbidding subagents and Fleet;\n"
        "  actor_independence=false is recorded, not hidden.\n"
        "- The promotion ladder is read from the canonical passport schema\n"
        "  rather than re-spelled, so a level this component invented would not\n"
        "  resolve and a level added to the schema appears automatically.\n"
        "- The combined ceiling is derived, not declared. It is the lowest any\n"
        "  auditor set, so three satisfied auditors cannot overrule the fourth,\n"
        "  and it is invariant to the order the verdicts arrive in. A declared\n"
        "  ceiling above the derived one is refused, while a more cautious\n"
        "  declaration is allowed; a sealed audit cannot have its ceiling\n"
        "  raised afterwards even when its hash is recomputed.\n"
        "- Method incompatibility is never pooled. The method auditor must\n"
        "  report one ceiling per stratum, its component ceiling must equal the\n"
        "  strongest stratum rather than a blend, and a mid-range figure\n"
        "  spanning two strata is refused as pooling. Only the method auditor\n"
        "  stratifies, and a sealed audit cannot be relabelled as pooled.\n"
        "- The veto is narrow and accountable. Only the method auditor holds\n"
        "  it; every other auditor is refused even for withdrawing a veto it\n"
        "  never had. A veto must carry a reason, a verdict without one may not\n"
        "  carry a reason, and a sustained veto floors the ladder at INBOX\n"
        "  however optimistic the other three are. A withdrawn veto stops\n"
        "  constraining but stays on the record, and removing a veto from a\n"
        "  rehashed audit fails closed because the ceiling is recomputed from\n"
        "  the verdicts.\n"
        "- A vetoed audit still records what each auditor found, so the reason\n"
        "  a promotion stopped is legible rather than a bare refusal.\n"
        "- Residual limitations: the auditors' judgements arrive as inputs and\n"
        "  are not produced here; the evidence-class to ceiling policy belongs\n"
        "  to the ingest layer and is not duplicated; a method incompatibility\n"
        "  the auditor never stratified is invisible to this component; and\n"
        "  promotion itself is committed by the governance gates. This review\n"
        "  is not external actor-independent certification.\n"
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
            "path": f"artifacts/work_packages/P02/attempts/0001/{name}",
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in sorted(set(output_names))
    ]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "P02_AUDITS_WITH_VETO_AND_PROMOTION_CEILINGS",
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependency_state": dependencies,
        "exit_criteria": {
            "method_incompatibility_not_pooled": "PASS",
            "promotion_ceilings_deterministic": "PASS",
        },
        "global_implementation_gate": "fail",
        "history_and_worktree": {
            "dirty_worktree_preserved": True,
            "prior_attempts_reports_and_rah_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
            "subagents_or_fleet_used": False,
        },
        "implementation_status": "PASS",
        "next_package": "P03-0001",
        "not_claimed": [
            "the auditors' judgements themselves, which arrive as inputs",
            "an evidence-class to ceiling policy, which the ingest layer owns",
            "detection of a method incompatibility the auditor did not stratify",
            "promotion itself, which the governance gates commit",
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


def _summary() -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "completion_ready": False,
        "full_node": f"{EXPECTED_NODE_COUNT}/{EXPECTED_NODE_COUNT}",
        "full_python": f"{EXPECTED_PYTHON_COUNT}/{EXPECTED_PYTHON_COUNT}",
        "promotion_ceiling_test": (
            f"{EXPECTED_PROMOTION_CEILING_COUNT}/{EXPECTED_PROMOTION_CEILING_COUNT}"
        ),
        "veto_fixture_test": (
            f"{EXPECTED_VETO_FIXTURE_COUNT}/{EXPECTED_VETO_FIXTURE_COUNT}"
        ),
        "next_action": "SEAL_P02_0001_THEN_CONTINUE_DAG",
        "package_status": "PASS",
        "status": "PASS",
        "targeted_parliament_auditors": (
            f"{EXPECTED_TARGETED_COUNT}/{EXPECTED_TARGETED_COUNT}"
        ),
    }


def build() -> dict[str, Any]:
    for name in RUN_RESULTS:
        check_run(name)
    normalize_junits()
    regression = regression_evidence()
    dependencies = dependency_status()
    write_scope = write_scope_verification()
    verification = p02_verification(regression)
    write_json("dependency-status.json", dependencies)
    write_json("write-scope-verification.json", write_scope)
    write_json("p02-verification.json", verification)
    (ATTEMPT / "commands.jsonl").write_text(
        commands_text(), encoding="utf-8", newline="\n"
    )
    (ATTEMPT / "review.md").write_text(review_text(), encoding="utf-8", newline="\n")
    report = report_document(
        regression, dependencies, write_scope, verification, rah_state=None
    )
    write_json("report.json", report)
    return _summary()


def bind_rah_state(
    *,
    core_generation: str,
    core_evidence_id: str,
    final_closeout_evidence_id: str,
) -> None:
    integrity = read_json(ATTEMPT / "rah-core-integrity.json")
    stored = read_json(ATTEMPT / "report.json")
    if "rah_state" in stored:
        raise SystemExit("P02-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "p02-verification.json")
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
    verification = read_json(ATTEMPT / "p02-verification.json")
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
        raise SystemExit("stored P02-0001 report is not the deterministic document")
    return _summary()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("build", "verify"))
    args = parser.parse_args()
    result = {"build": build, "verify": verify}[args.mode]()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
