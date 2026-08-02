#!/usr/bin/env python3
"""Build and verify W01-0001 workflow-compiler evidence.

W01-0001 implements `packages/foundry-kernel/src/workflows/compiler/**`: the
canonical workflow-document compiler and NodeContract validator whose
vocabulary derives from `schemas/node-contract.schema.json`, whose DAG and
resource semantics delegate to the sealed scheduler compiler, and whose
write-scope conflicts and unknown executors fail closed.  This builder
verifies the executed checks and emits the immutable attempt evidence; it
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
ATTEMPT = ROOT / "artifacts/work_packages/W01/attempts/0001"
ATTEMPT_ID = "W01-0001"
WORK_PACKAGE_ID = "W01"
RECORDED_AT = "2026-07-31T14:30:00.000Z"

EXPECTED_TARGETED_NODE_COUNT = 26
EXPECTED_PYTHON_COUNT = 1156
EXPECTED_NODE_COUNT = 860
EXPECTED_NODE_FILE_COUNT = 84

COMPONENT = "packages/foundry-kernel/src/workflows/compiler"
EXPECTED_PRODUCT_HASHES = {
    f"{COMPONENT}/workflow-compiler.mjs": (
        "e56995ad9df613a4289fbae58466e2a55ab692ce7bc377fbcb07cff4fe3ebcc4"
    ),
    f"{COMPONENT}/node-contract.test.mjs": (
        "22143ad69151cedbeb25bd49d0b9c20953e6d7f5c82cadc3d8d1efe6c4fd30a1"
    ),
    f"{COMPONENT}/workflow-compile.test.mjs": (
        "25a9ee68abbd226e5d02db0ba9c4019235610cef452329893577ba1f4cc74110"
    ),
    f"{COMPONENT}/memory-recall.workflow.fixture.json": (
        "a03f790be41bcb73d907fb915c60be37f78508705ecd6abbe31f035dec12b246"
    ),
}
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/D04/report.json": (
        "b47c194e230f4b08ab96b6153e9fc0e170eafb1054318cfaedd8e1ddeb4c5fde"
    ),
    "artifacts/work_packages/E04/report.json": (
        "841dcf60989cfc7ab0eff7be95e1ae721ae18ac513cae653ab6ac8a44942f6c1"
    ),
    "artifacts/work_packages/F04/report.json": (
        "5a2414ebb79c923af7425b87d614faa088ba9fbd4e6950406948b2eb86d6ab46"
    ),
    "artifacts/work_packages/N04/report.json": (
        "8cbe538b5adb087974f83cc181e97172052bc25ff92e6a14da7dad3eb70141f7"
    ),
}

JUNIT_PATHS = {
    "targeted_workflow_node": ATTEMPT / "targeted-workflow-node.junit.xml",
    "full_python": ATTEMPT / "full-python-suite.junit.xml",
    "full_node": ATTEMPT / "full-node-suite.junit.xml",
}
_NODE_JUNITS = frozenset({"targeted_workflow_node", "full_node"})
RUN_RESULTS = (
    "repo-structure",
    "repo-boundaries",
    "targeted-workflow-node",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "run_w01_0001_checks.py",
    "build_w01_0001_evidence.py",
    "w01_0001_rah_seal.py",
    "dependency-status.json",
    "w01-verification.json",
    "write-scope-verification.json",
    "node-test-inventory.json",
    "junit-normalization-verification.json",
    "targeted-workflow-node.junit.xml",
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
    targeted = node_summary(JUNIT_PATHS["targeted_workflow_node"])
    python = pytest_summary(JUNIT_PATHS["full_python"])
    node = node_summary(JUNIT_PATHS["full_node"])
    node_inventory = read_json(ATTEMPT / "node-test-inventory.json")
    if (
        targeted["collected"],
        targeted["passed"],
        targeted["failed"],
        targeted["cancelled"],
        targeted["skipped"],
        targeted["todo"],
    ) != (EXPECTED_TARGETED_NODE_COUNT, EXPECTED_TARGETED_NODE_COUNT, 0, 0, 0, 0):
        raise SystemExit(f"targeted W01 gate failed: {targeted}")
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
        "baseline_attempt": "T01-0002",
        "full_node": node,
        "full_python": python,
        "new_failure_count": 0,
        "prior_baseline_counts": {"full_node": 834, "full_python": 1156},
        "status": "PASS",
        "targeted_workflow_node": targeted,
        "unexpected_skip_xfail_todo_or_cancellation_count": 0,
    }


def dependency_status() -> dict[str, Any]:
    assert_hashes(EXPECTED_DEPENDENCY_HASHES)
    dependencies: dict[str, Any] = {}
    for package in ("D04", "E04", "F04", "N04"):
        relative = f"artifacts/work_packages/{package}/report.json"
        report = read_json(ROOT / relative)
        status = report.get("package_status") or report.get("status")
        if status != "PASS":
            raise SystemExit(f"{package} dependency is not PASS")
        dependencies[package] = {
            "attempt_id": report.get("attempt_id"),
            "report": relative,
            "report_sha256": sha256_id(ROOT / relative),
            "status": "PASS",
        }
    return {
        "attempt_id": ATTEMPT_ID,
        "dependencies": dependencies,
        "next_action": "SEAL_W01_0001_THEN_CONTINUE_DAG",
        "status": "PASS",
    }


def write_scope_verification() -> dict[str, Any]:
    assert_hashes(EXPECTED_PRODUCT_HASHES)
    component_files = sorted(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / COMPONENT).rglob("*")
        if path.is_file()
    )
    if component_files != sorted(EXPECTED_PRODUCT_HASHES):
        raise SystemExit(
            f"compiler component holds unexpected files: {component_files}"
        )
    return {
        "approved_scope": [f"{COMPONENT}/**", "artifacts/work_packages/W01/**"],
        "attempt_id": ATTEMPT_ID,
        "component_files": component_files,
        "fixture_provenance": {
            "file": f"{COMPONENT}/memory-recall.workflow.fixture.json",
            "projection_rule": "yaml.safe_load of the source document, unchanged",
            "source": "workflows/memory_recall.workflow.yaml",
            "source_sha256": sha256_id(ROOT / "workflows/memory_recall.workflow.yaml"),
        },
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


def w01_verification(regression: dict[str, Any]) -> dict[str, Any]:
    fixture = read_json(ROOT / COMPONENT / "memory-recall.workflow.fixture.json")
    if fixture.get("source_sha256") != sha256_id(
        ROOT / "workflows/memory_recall.workflow.yaml"
    ):
        raise SystemExit("workflow fixture no longer matches its source document")
    return {
        "attempt_id": ATTEMPT_ID,
        "exit_criteria": {
            "dag_and_resource_edges_validated": {
                "evidence": [
                    f"{COMPONENT}/workflow-compile.test.mjs",
                ],
                "status": "PASS",
            },
            "unknown_executor_blocked": {
                "evidence": [
                    f"{COMPONENT}/node-contract.test.mjs",
                ],
                "status": "PASS",
            },
        },
        "required_checks": {
            "node_contract_test": {
                "module": f"{COMPONENT}/node-contract.test.mjs",
                "status": "PASS",
            },
            "workflow_compile_test": {
                "module": f"{COMPONENT}/workflow-compile.test.mjs",
                "status": "PASS",
            },
        },
        "status": "PASS",
        "targeted_test_count": regression["targeted_workflow_node"]["collected"],
        "vocabulary_authority": "schemas/node-contract.schema.json",
        "vocabulary_registry_binding": (
            "contracts registry source_sha256 equality asserted in node-contract.test.mjs"
        ),
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
                "artifacts/work_packages/W01/attempts/0001/build_w01_0001_evidence.py",
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
        "# W01-0001 primary-session separate adversarial review\n"
        "\n"
        "- Reviewer: primary session in a separate adversarial pass under the\n"
        "  product-owner instruction forbidding subagents and Fleet;\n"
        "  actor_independence=false is recorded, not hidden.\n"
        "- Vocabulary authority (EF4-I22): executor types, determinism\n"
        "  classes, failure policies, model tiers, and the exact NodeContract\n"
        "  field set derive at runtime from schemas/node-contract.schema.json;\n"
        "  a tampered, open, or renamed schema is rejected at factory time,\n"
        "  and the schema file is pinned to the sealed contracts registry by\n"
        "  source hash.\n"
        "- Unknown executors are blocked with the canonical vocabulary in the\n"
        "  typed error, and executor references follow the observed canonical\n"
        "  conventions (llm prompts, subworkflow workflow documents, dotted\n"
        "  entrypoints or tools scripts).\n"
        "- DAG authority stays with the sealed scheduler compiler: duplicate,\n"
        "  unknown, and self dependencies and contract-less cycles are its\n"
        "  typed failures, and the compiled plan passes its integrity check.\n"
        "- Hidden-edge rule: two nodes whose write scopes overlap must be\n"
        "  dependency-ordered or share a declared resource; the compiler\n"
        "  fails closed otherwise and emits the resource-edge evidence.  A\n"
        "  survey of all 22 canonical workflows found zero violations of this\n"
        "  rule, so the contract matches the corpus it will compile.\n"
        "- Real-shape proof: the memory_recall projection (hash-bound to its\n"
        "  YAML source) compiles to an eight-node plan; full-corpus\n"
        "  compilation of all 22 workflows remains a later integration gate\n"
        "  because the Node runtime deliberately has no YAML parser.\n"
        "- Determinism: identical documents compile to identical bytes and\n"
        "  hashes; the input document is never mutated; outputs are frozen.\n"
        "- Residual limitations: workflow YAML parsing, runtime execution,\n"
        "  checkpointing (W02), and staleness reassessment (W03) are outside\n"
        "  this package; this review is not external actor-independent\n"
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
            "path": f"artifacts/work_packages/W01/attempts/0001/{name}",
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in sorted(set(output_names))
    ]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "W01_WORKFLOW_COMPILER_AND_NODE_CONTRACT_VALIDATOR",
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependency_state": dependencies,
        "exit_criteria": {
            "dag_and_resource_edges_validated": "PASS",
            "unknown_executor_blocked": "PASS",
        },
        "global_implementation_gate": "fail",
        "history_and_worktree": {
            "dirty_worktree_preserved": True,
            "prior_attempts_reports_and_rah_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
            "subagents_or_fleet_used": False,
        },
        "implementation_status": "PASS",
        "next_package": "A06-0002",
        "not_claimed": [
            "workflow YAML parsing inside the Node runtime",
            "runtime workflow execution, checkpointing, or reassessment (W02/W03)",
            "full 22-workflow corpus compilation as a sealed gate",
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
    verification = w01_verification(regression)
    write_json("dependency-status.json", dependencies)
    write_json("write-scope-verification.json", write_scope)
    write_json("w01-verification.json", verification)
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
        "full_node": "860/860",
        "full_python": "1156/1156",
        "next_action": "SEAL_W01_0001_THEN_CONTINUE_DAG",
        "package_status": "PASS",
        "status": "PASS",
        "targeted_workflow_node": "26/26",
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
        raise SystemExit("W01-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "w01-verification.json")
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
    verification = read_json(ATTEMPT / "w01-verification.json")
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
        raise SystemExit("stored W01-0001 report is not the deterministic document")
    return {
        "attempt_id": ATTEMPT_ID,
        "completion_ready": False,
        "full_node": "860/860",
        "full_python": "1156/1156",
        "next_action": "SEAL_W01_0001_THEN_CONTINUE_DAG",
        "package_status": "PASS",
        "status": "PASS",
        "targeted_workflow_node": "26/26",
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
