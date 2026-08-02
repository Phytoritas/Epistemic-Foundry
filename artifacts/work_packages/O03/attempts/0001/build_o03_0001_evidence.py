#!/usr/bin/env python3
"""Build and verify O03-0001 dependency-cluster / Evidence Pack evidence.

O03-0001 implements `python/epistemic_foundry/retrieval/evidence_pack/**`:
typed EvidenceDependencyCluster construction (EF4-I08) and schema-exact
EvidencePack assembly with visible counter/null/boundary/method lanes
(EF4-I06).  This builder verifies the executed checks and emits the immutable
attempt evidence; it never modifies product files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/O03/attempts/0001"
ATTEMPT_ID = "O03-0001"
WORK_PACKAGE_ID = "O03"
RECORDED_AT = "2026-07-31T12:45:00.000Z"

EXPECTED_TARGETED_COUNT = 45
EXPECTED_PYTHON_COUNT = 1115
EXPECTED_NODE_COUNT = 819
EXPECTED_NODE_FILE_COUNT = 79

COMPONENT = "python/epistemic_foundry/retrieval/evidence_pack"
EXPECTED_PRODUCT_HASHES = {
    f"{COMPONENT}/__init__.py": (
        "113c7ab4436ac0a5460863dd0ca38862cb4d2e71cb6775bc770acf31f4a19114"
    ),
    f"{COMPONENT}/contracts.py": (
        "e6b98cfd434845051b059289cb38062fa9b621071e6d5944573198fca91f2a40"
    ),
    f"{COMPONENT}/test_dependency_cluster.py": (
        "46efe27a62ddd8f5b83a159982473f680e171010ee643774b62fbf48fba19638"
    ),
    f"{COMPONENT}/test_pack_diversity.py": (
        "7b362d9656a404e56b36a399e00a8d1c3e7a18b0b67cd3e8504cc013920bd60a"
    ),
}
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/O01/report.json": (
        "21cd6f07ce4caae4d7a7d673a85aec105117f35f2a560ef8310ee532cb188051"
    ),
    "artifacts/work_packages/B04/attempts/0010/report.json": (
        "40c89af4ce4d8eed6a9a6f7b9f90895bf157e6d894020d185174558ce845be54"
    ),
}
ALLOWED_CONTRACT_IMPORT_PREFIXES = (
    "from __future__",
    "import hashlib",
    "import json",
    "import re",
    "from collections.abc",
    "from dataclasses",
    "from datetime",
    "from enum",
    "from types",
    "from typing",
    "from ..planning.contracts",
)

JUNIT_PATHS = {
    "targeted_evidence_pack": ATTEMPT / "targeted-evidence-pack.junit.xml",
    "full_python": ATTEMPT / "full-python-suite.junit.xml",
    "full_node": ATTEMPT / "full-node-suite.junit.xml",
}
RUN_RESULTS = (
    "ruff-check",
    "ruff-format-check",
    "targeted-evidence-pack",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "run_o03_0001_checks.py",
    "build_o03_0001_evidence.py",
    "o03_0001_rah_seal.py",
    "dependency-status.json",
    "o03-verification.json",
    "write-scope-verification.json",
    "node-test-inventory.json",
    "junit-normalization-verification.json",
    "targeted-evidence-pack.junit.xml",
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
        if name == "full_node":
            if "duration_ms" in text:
                raise SystemExit("Node JUnit retains volatile duration_ms")
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
        if name == "full_node":
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


def regression_evidence() -> tuple[dict[str, Any], dict[str, Any]]:
    targeted = pytest_summary(JUNIT_PATHS["targeted_evidence_pack"])
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
        raise SystemExit(f"targeted O03 gate failed: {targeted}")
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
    return (
        {
            "attempt_id": ATTEMPT_ID,
            "baseline_attempt": "B04-0010",
            "component_tests_are_targeted_only": True,
            "full_node": node,
            "full_python": python,
            "new_failure_count": 0,
            "status": "PASS",
            "targeted_evidence_pack": targeted,
            "unexpected_skip_xfail_todo_or_cancellation_count": 0,
        },
        node_inventory,
    )


def dependency_status() -> dict[str, Any]:
    assert_hashes(EXPECTED_DEPENDENCY_HASHES)
    o01_path = ROOT / "artifacts/work_packages/O01/report.json"
    o01 = read_json(o01_path)
    if (
        o01.get("attempt_id") != "O01-0002"
        or o01.get("package_status") != "PASS"
        or o01.get("implementation_status") != "PASS"
    ):
        raise SystemExit("O01 dependency is not the sealed PASS attempt")
    baseline_path = ROOT / "artifacts/work_packages/B04/attempts/0010/report.json"
    baseline = read_json(baseline_path)
    rah = baseline.get("rah_state")
    if (
        baseline.get("attempt_id") != "B04-0010"
        or baseline.get("status") != "PASS"
        or not isinstance(rah, dict)
        or rah.get("core_evidence_id") != "E0109"
        or rah.get("final_closeout_evidence_id") != "E0110"
    ):
        raise SystemExit("B04-0010 regression baseline is not the sealed PASS attempt")
    return {
        "attempt_id": ATTEMPT_ID,
        "dependencies": {
            "O01": {
                "attempt_id": "O01-0002",
                "report": "artifacts/work_packages/O01/report.json",
                "report_sha256": sha256_id(o01_path),
                "status": "PASS",
            }
        },
        "regression_baseline": {
            "attempt_id": "B04-0010",
            "core_evidence_id": "E0109",
            "final_closeout_evidence_id": "E0110",
            "report": "artifacts/work_packages/B04/attempts/0010/report.json",
            "report_sha256": sha256_id(baseline_path),
            "status": "PASS",
        },
        "next_action": "SEAL_O03_0001_THEN_CONTINUE_DAG",
        "status": "PASS",
    }


def write_scope_verification() -> dict[str, Any]:
    assert_hashes(EXPECTED_PRODUCT_HASHES)
    porcelain = subprocess.run(
        ["git", "status", "--porcelain", "--", "python/"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if porcelain != "?? python/":
        raise SystemExit(
            f"python/ component tree must stay one untracked root: {porcelain!r}"
        )
    contract_text = (ROOT / COMPONENT / "contracts.py").read_text(encoding="utf-8")
    for line in contract_text.splitlines():
        if line.startswith(("import ", "from ")) and not line.startswith(
            ALLOWED_CONTRACT_IMPORT_PREFIXES
        ):
            raise SystemExit(f"unexpected O03 contract import: {line}")
    if "src.epistemic_foundry" in contract_text or "src/epistemic_foundry" in contract_text:
        raise SystemExit("component may not import the runtime source tree")
    return {
        "approved_scope": [f"{COMPONENT}/**", "artifacts/work_packages/O03/**"],
        "attempt_id": ATTEMPT_ID,
        "component_import_boundary": "stdlib + retrieval.planning public API only",
        "product_file_hashes": {
            relative: "sha256:" + digest
            for relative, digest in EXPECTED_PRODUCT_HASHES.items()
        },
        "product_files_created_by_attempt": sorted(EXPECTED_PRODUCT_HASHES),
        "python_tree_git_state": "?? python/ (single untracked root; no tracked python/ file exists or changed)",
        "reset_clean_stash_commit_push_performed": False,
        "root_canonical_source_mutation_count": 0,
        "schema_or_test_weakening_count": 0,
        "status": "PASS",
        "subagents_or_fleet_used": False,
        "write_scope_violation_count": 0,
    }


def o03_verification(regression: dict[str, Any]) -> dict[str, Any]:
    targeted = regression["targeted_evidence_pack"]
    return {
        "attempt_id": ATTEMPT_ID,
        "exit_criteria": {
            "counter_null_boundary_included": {
                "evidence": [
                    "test_pack_diversity_test_assembly_keeps_counter_null_boundary_visible",
                    "test_pack_diversity_test_silent_counterevidence_drop_fails_closed",
                    "test_pack_diversity_test_typed_unresolved_counter_result_is_visible_not_silent",
                    "test_pack_diversity_test_searched_none_counter_lane_is_honestly_empty",
                    "test_pack_diversity_test_blocked_counter_lane_is_incomplete_not_complete",
                ],
                "status": "PASS",
            },
            "shared_samples_preprints_deduplicated": {
                "evidence": [
                    "test_dependency_cluster_test_shared_dataset_and_preprint_family_merge",
                    "test_dependency_cluster_test_transitive_union_uses_weakest_confidence",
                    "test_pack_diversity_test_assembly_keeps_counter_null_boundary_visible",
                ],
                "status": "PASS",
            },
        },
        "required_checks": {
            "dependency_cluster_test": {
                "junit": targeted["junit"],
                "module": f"{COMPONENT}/test_dependency_cluster.py",
                "status": "PASS",
            },
            "pack_diversity_test": {
                "junit": targeted["junit"],
                "module": f"{COMPONENT}/test_pack_diversity.py",
                "status": "PASS",
            },
        },
        "schema_conformance": {
            "canonical_examples_validated": [
                "examples/sample_evidence-dependency-cluster.json",
                "examples/sample_evidence_pack.json",
            ],
            "draft": "2020-12",
            "emitted_instances_validated_against": [
                "schemas/evidence-dependency-cluster.schema.json",
                "schemas/evidence-pack.schema.json",
            ],
            "status": "PASS",
        },
        "status": "PASS",
        "targeted_test_count": targeted["collected"],
        "typed_failure_codes_tested": [
            "ADJUSTED_COUNT_INVALID",
            "CITATION_TARGET_UNKNOWN",
            "CLUSTER_HASH_MISMATCH",
            "DEPENDENCY_TYPE_ORDER_INVALID",
            "DEPENDENCY_TYPE_UNKNOWN",
            "EVIDENCE_ID_DUPLICATE",
            "EVIDENCE_NOT_RETRIEVED",
            "EVIDENCE_ORDER_INVALID",
            "EVIDENCE_UNACCOUNTED",
            "EVIDENCE_UNKNOWN",
            "FIELD_SET_INVALID",
            "INDEPENDENT_COUNT_INVALID",
            "INPUT_INVALID",
            "LINK_SELF_REFERENCE",
            "LINK_TARGET_UNKNOWN",
            "METADATA_ONLY_EVIDENCE",
            "PACK_RECONSTRUCTION_MISMATCH",
            "PACK_SUBJECT_MISMATCH",
            "REPRESENTATIVE_NOT_MEMBER",
            "RESULT_SILENTLY_DROPPED",
            "REVIEW_TARGET_UNKNOWN",
            "ROLE_ASSIGNMENT_CONFLICT",
            "ROLE_SET_INVALID",
            "STALE_RETRIEVAL_SNAPSHOT",
            "UNRESOLVED_CONTRADICTION",
            "UNRESOLVED_REASON_INVALID",
            "UNRESOLVED_UNKNOWN_RESULT",
        ],
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
                "artifacts/work_packages/O03/attempts/0001/build_o03_0001_evidence.py",
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
        "# O03-0001 primary-session separate adversarial review\n"
        "\n"
        "- Reviewer: primary session in a separate adversarial pass under the\n"
        "  product-owner instruction forbidding subagents and Fleet;\n"
        "  actor_independence=false is recorded, not hidden.\n"
        "- Contract fidelity: emitted EvidenceDependencyCluster and EvidencePack\n"
        "  instances validate against the canonical Draft 2020-12 schemas, and\n"
        "  the canonical repository examples validate unchanged.  Field sets are\n"
        "  exact; unknown fields, unsorted identifier lists, and non-canonical\n"
        "  dependency-type order fail closed.\n"
        "- EF4-I08: shared datasets, experiments, cohorts, preprint/journal\n"
        "  families, review chains, team series, model/code reuse, citation\n"
        "  dependencies, and declared UNKNOWN links merge transitively into one\n"
        "  cluster; adjusted support is the independent-unit count, never the\n"
        "  raw vote count; the weakest link bounds independence confidence.\n"
        "- EF4-I06: counter, null, boundary, and method lanes stay visible.\n"
        "  A SEARCHED_WITH_RESULTS lane whose results silently vanish fails\n"
        "  closed (RESULT_SILENTLY_DROPPED); exclusions require typed reasons;\n"
        "  SEARCHED_NONE stays an honest empty lane; BLOCKED lanes cannot be\n"
        "  reported complete.\n"
        "- No invention: every pack evidence unit must resolve to result IDs of\n"
        "  the sealed retrieval run (EVIDENCE_NOT_RETRIEVED otherwise), the\n"
        "  certificate is deterministically recomputed through the O01 public\n"
        "  API before assembly, and metadata-only candidates are rejected.\n"
        "- Determinism: cluster and pack bytes are permutation-invariant and\n"
        "  replay-identical; validate_evidence_pack rebuilds from bound inputs\n"
        "  and rejects any divergence.\n"
        "- Boundary: the component imports only the Python stdlib and the O01\n"
        "  planning public API; it does not import the runtime source tree and\n"
        "  does not modify any file outside its approved write scope.\n"
        "- Regression: full Python 1115/1115 and full Node 819/819 across 79\n"
        "  files are unchanged from the sealed B04-0010 baseline; component\n"
        "  tests run in the targeted gate (45/45).\n"
        "- Finding (resolved): the certificate seal type from O01 was initially\n"
        "  rejected by the O03 payload extractor; the extractor now accepts the\n"
        "  O01 sealed artifact explicitly instead of duck-typing.\n"
        "- Residual limitation: this review is not external actor-independent\n"
        "  certification, and no live corpus or retrieval provider is claimed.\n"
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
            "path": f"artifacts/work_packages/O03/attempts/0001/{name}",
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in sorted(set(output_names))
    ]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "O03_DEPENDENCY_CLUSTER_AND_EVIDENCE_PACK_IMPLEMENTATION",
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependency_state": dependencies,
        "exit_criteria": {
            "counter_null_boundary_included": "PASS",
            "shared_samples_preprints_deduplicated": "PASS",
        },
        "global_implementation_gate": "fail",
        "history_and_worktree": {
            "dirty_worktree_preserved": True,
            "prior_attempts_reports_and_rah_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
            "subagents_or_fleet_used": False,
        },
        "implementation_status": "PASS",
        "next_package": "T01-0002",
        "not_claimed": [
            "live retrieval provider or corpus availability",
            "actor-independent certification of this implementation review",
            "SourceSpan grounding against a real corpus",
            "downstream O04/O05/O06 conformance",
            "overall product completion",
            "release or production readiness",
            "completion_ready=true",
        ],
        "output_artifacts": artifacts,
        "package_status": "PASS",
        "product_files_created_by_attempt": sorted(EXPECTED_PRODUCT_HASHES),
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
    regression, _node_inventory = regression_evidence()
    dependencies = dependency_status()
    write_scope = write_scope_verification()
    verification = o03_verification(regression)
    write_json("dependency-status.json", dependencies)
    write_json("write-scope-verification.json", write_scope)
    write_json("o03-verification.json", verification)
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
        "full_node": "819/819",
        "full_python": "1115/1115",
        "next_action": "SEAL_O03_0001_THEN_CONTINUE_DAG",
        "package_status": "PASS",
        "status": "PASS",
        "targeted_evidence_pack": "45/45",
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
        raise SystemExit("O03-0001 report is already RAH-bound")
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
    regression, _node_inventory = regression_evidence()
    dependencies = read_json(ATTEMPT / "dependency-status.json")
    write_scope = read_json(ATTEMPT / "write-scope-verification.json")
    verification = read_json(ATTEMPT / "o03-verification.json")
    report = report_document(
        regression, dependencies, write_scope, verification, rah_state=rah_state
    )
    write_json("report.json", report)


def verify() -> dict[str, Any]:
    for name in RUN_RESULTS:
        check_run(name)
    normalize_junits()
    regression, _node_inventory = regression_evidence()
    assert_hashes(EXPECTED_DEPENDENCY_HASHES)
    assert_hashes(EXPECTED_PRODUCT_HASHES)
    stored = read_json(ATTEMPT / "report.json")
    dependencies = read_json(ATTEMPT / "dependency-status.json")
    write_scope = read_json(ATTEMPT / "write-scope-verification.json")
    verification = read_json(ATTEMPT / "o03-verification.json")
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
        raise SystemExit("stored O03-0001 report is not the deterministic document")
    return {
        "attempt_id": ATTEMPT_ID,
        "completion_ready": False,
        "full_node": "819/819",
        "full_python": "1115/1115",
        "next_action": "SEAL_O03_0001_THEN_CONTINUE_DAG",
        "package_status": "PASS",
        "status": "PASS",
        "targeted_evidence_pack": "45/45",
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
