#!/usr/bin/env python3
"""Build and verify X02-0001 evidence: Claude Code skills, agents and worktree
adapter.

This attempt implements the Claude Code adapter under the frozen write scope
``adapters/claude-code/**``.  The builder verifies every executed check receipt,
gates the required product JUnit suites and the sealed X01 dependency-regression
suite against their measured counts, gates the repository-wide Node suite on
zero failures with this package's five Claude Code test modules inside the
inventory, pins product and dependency bytes, binds the X01 dependency and the
live latest-sealed regression baseline, and emits the deterministic attempt
evidence.  It never modifies product files.
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
ATTEMPT = ROOT / "artifacts/work_packages/X02/attempts/0001"
ATTEMPT_ID = "X02-0001"
WORK_PACKAGE_ID = "X02"
RECORDED_AT = "2026-08-02T00:00:00.000Z"
ATTEMPT_DIR = "artifacts/work_packages/X02/attempts/0001"
COMPONENT = "adapters/claude-code"
APPROVED_SCOPE = ["adapters/claude-code/**"]

EXPECTED_PRODUCT_HASHES = {
    "adapters/claude-code/README.md": "9e15c3893f8c07fb7227519d5862ce987d8f0ea1299d920ad8e6e5a12fe4ccaf",
    "adapters/claude-code/agent-binding.mjs": "50e6a4557ebe51691e0657894ad3684943a58ae810d93351d5e4d0b52198deb4",
    "adapters/claude-code/claude-adversarial.test.mjs": "9842a869e64bed833db16230a9a028b2ca2b8a0832d8815a696efd37a453f3ba",
    "adapters/claude-code/claude-binding.json": "a9e770f3a98bf04c8464b8e8b583c65f5fbca99716bf958c1260b4d988e607a7",
    "adapters/claude-code/claude-contract.test.mjs": "f3c1bd628f6c14dfd138cffbcf653a83d0fc789b45f1c7eeb75de362ddfbc99f",
    "adapters/claude-code/claude-declarations.mjs": "8c509f16439941e4b3ef60896f13d831d677daf644c2a1e194adf50bd3d509aa",
    "adapters/claude-code/claude-fixtures.mjs": "728e9cba63fa48d23458254e2a9a6ce570f54905911dcae4c3b00b760e2e242f",
    "adapters/claude-code/claude-receipts.test.mjs": "f7c9ef2f328342a600f32339a69ef1b8f2e73b15e2383ac414bfef75f7a3b0ce",
    "adapters/claude-code/claude-schema.test.mjs": "aa90669d2480c7f736dbeb35d210bbfce576647b755a55b2f26045c2554c8063",
    "adapters/claude-code/claude-worktree.test.mjs": "31dd424556fcd2d205971944b89d5315023aa75217639f465208b918d9053028",
    "adapters/claude-code/ef-abductive-mediator.md": "dce18df9bb01220bc56f394e3194506121c7ff2fb7c7cfa1918afccdbdddf967",
    "adapters/claude-code/ef-causal-auditor.md": "09fc246ae512be20ba3a430d29b2c3a45c8fb1344d86143e8f94b60cfa454162",
    "adapters/claude-code/ef-claim-extractor.md": "e6e20618a4a505e31f75684447e3b195e680e83d0ac0532a343a4004d383e9a2",
    "adapters/claude-code/ef-contract-reviewer.md": "f3410402866b104984e9c81f5ac5c02134e0ed2f115ac45e35c4ee072a5c5325",
    "adapters/claude-code/ef-deductivist.md": "5e89c3cf5488e01bd36a1555243e57c06d7f7d4498d3b87c7fc79ad812f69aea",
    "adapters/claude-code/ef-defender.md": "13394f0754e30277c223a372a255b183a063a679b31dea7b9e8e647ce7c89a91",
    "adapters/claude-code/ef-evidence-scout.md": "696e7f45c54ea90e8b5c569b38c0198a235ee073a3cf1923f8d8ce20a3d9992c",
    "adapters/claude-code/ef-independent-attestor.md": "157e6d94bd4fbc6dfd9817981b673cc8c29a98193f4139055e4a6a7130afaff2",
    "adapters/claude-code/ef-inductivist.md": "9c5e942735666f8b3f0de76b951ebd9f91c8fc36c0adacab1c15b025e063cbb1",
    "adapters/claude-code/ef-judge.md": "e29f9fc83c44ef23b55ea1841b4b6d48ee800b6e25f9ae70f06a0e92869e5882",
    "adapters/claude-code/ef-method-auditor.md": "86d7d59f998131859268622eaaa8bef2493b4c0acf70590bec4e533b40a6a797",
    "adapters/claude-code/ef-minority-reporter.md": "086a44461df56ea2e56054c172d5afcb66654f8af05d7b424c38ac60014dd77d",
    "adapters/claude-code/ef-novelty-examiner.md": "b6fee6f0d37f2e57fce594196b87ad8ced65098fcf53f786c591e30ac3b9da15",
    "adapters/claude-code/ef-prosecutor.md": "16089a96fa2e6444d010a4c7f172033690dd56eac122f74c5f5e8d461ecabb67",
    "adapters/claude-code/ef-scope-auditor.md": "e0e7a3e58ef0fbca60e04ee277580c67651fbba5fc6ba7fc4a9eb228d0206a2e",
    "adapters/claude-code/ef-validation-executor.md": "e282f6223addd196162be8376e7f8bcf48f0da8da930fa4c043fbd7599d20ca9",
    "adapters/claude-code/index.mjs": "3a1080fd2c6aae3b2d3948d7d74241bc441c5de714d2b66a23a2daf03200cb1e",
    "adapters/claude-code/role-adapter.mjs": "7719e8025fb0dc2f671940ad86fd3c2dda23dd808e54761e249e5fd33a6fa72c",
    "adapters/claude-code/role_mapping.yaml": "c9b387472f672318d9e65bb66c7c13746af2e65fa5d2a9b1c54748b35fe5256f",
    "adapters/claude-code/worktree-plan.mjs": "79be5ca44e52896636304d8b459030c0705e863761b785818f463b750e9d4bfb",
}
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/V03/attempts/0001/report.json": "63ebb4c43c819d1a9863dca6c76e538bf3031669f32abfb4802c79bc42f8ad31",
    "artifacts/work_packages/X01/attempts/0001/report.json": "976e23a05d826aa10c3f757d652c3c6fd8f56ed05f9bf0dcba09aa033c2a924c",
}

JUNIT_PATHS = {
    "claude_adapter_test": ATTEMPT / "claude-adapter-test.junit.xml",
    "claude_adversarial_tests": ATTEMPT / "claude-adversarial-tests.junit.xml",
    "claude_receipts": ATTEMPT / "claude-receipts.junit.xml",
    "claude_schema_check": ATTEMPT / "claude-schema-check.junit.xml",
    "claude_worktree_isolation_test": ATTEMPT
    / "claude-worktree-isolation-test.junit.xml",
    "dependency_regression_codex_adapter": ATTEMPT
    / "dependency-regression-codex-adapter.junit.xml",
    "full_node_suite": ATTEMPT / "full-node-suite.junit.xml",
}
_NODE_JUNITS = frozenset(JUNIT_PATHS)
RUN_RESULTS = (
    "claude-adapter-test",
    "claude-adversarial-tests",
    "claude-receipts",
    "claude-schema-check",
    "claude-worktree-isolation-test",
    "dependency-regression-codex-adapter",
    "full-node-suite",
    "git-diff-check",
    "write-scope-verification",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "build_x02_0001_evidence.py",
    "claude-adapter-test.junit.xml",
    "claude-adversarial-tests.junit.xml",
    "claude-receipts.junit.xml",
    "claude-schema-check.junit.xml",
    "claude-worktree-isolation-test.junit.xml",
    "commands.jsonl",
    "dependency-regression-codex-adapter.junit.xml",
    "dependency-status.json",
    "full-node-suite.junit.xml",
    "junit-normalization-verification.json",
    "node-test-inventory.json",
    "review.md",
    "run_x02_0001_checks.py",
    "write-scope-verification.json",
    "x02-verification.json",
    "x02_0001_rah_seal.py",
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
    commanded = isinstance(value.get("command"), list) or isinstance(
        value.get("commands"), list
    )
    if (
        value.get("attempt_id") != ATTEMPT_ID
        or value.get("check") != name
        or value.get("exit_code") != 0
        or value.get("status") != "PASS"
        or not commanded
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
    summaries: dict[str, dict[str, Any]] = {}
    for label, expected in (
        ("claude_schema_check", 12),
        ("claude_adapter_test", 10),
        ("claude_adversarial_tests", 21),
        ("claude_worktree_isolation_test", 9),
        ("claude_receipts", 10),
        ("dependency_regression_codex_adapter", 68),
    ):
        summary = node_summary(JUNIT_PATHS[label])
        if (
            summary["collected"],
            summary["passed"],
            summary["failed"],
            summary["cancelled"],
            summary["skipped"],
            summary["todo"],
            summary["xml_error_count"],
            summary["xml_failure_count"],
        ) != (expected, expected, 0, 0, 0, 0, 0, 0):
            raise SystemExit(f"{label} gate failed: {summary}")
        summaries[label] = summary

    # The repository-wide Node suite gates on zero failures with the five X02
    # Claude Code modules inside the measured inventory; the passing count is the
    # live frontier count and is recorded, never frozen to a literal.
    full = node_summary(JUNIT_PATHS["full_node_suite"])
    if (
        (
            full["failed"],
            full["cancelled"],
            full["xml_error_count"],
            full["xml_failure_count"],
        )
        != (0, 0, 0, 0)
        or full["passed"] <= 0
        or full["collected"] != (full["passed"] + full["skipped"] + full["todo"])
    ):
        raise SystemExit(f"full_node_suite gate failed: {full}")
    summaries["full_node_suite"] = full

    inventory = read_json(ATTEMPT / "node-test-inventory.json")
    claude = inventory.get("x02_claude_tests")
    expected_claude = [
        f"{COMPONENT}/claude-adversarial.test.mjs",
        f"{COMPONENT}/claude-contract.test.mjs",
        f"{COMPONENT}/claude-receipts.test.mjs",
        f"{COMPONENT}/claude-schema.test.mjs",
        f"{COMPONENT}/claude-worktree.test.mjs",
    ]
    if sorted(claude or []) != sorted(expected_claude):
        raise SystemExit(f"X02 Claude Code tests not in Node inventory: {inventory}")
    return {
        "attempt_id": ATTEMPT_ID,
        "full_node_gate": "zero_failures_with_x02_claude_tests_in_inventory",
        "full_node_inventory_count": inventory.get("count"),
        "full_node_passed": full["passed"],
        "new_failure_count": 0,
        "regression_baseline_attempt": "V03-0001",
        "status": "PASS",
        "suites": summaries,
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
        "core_generation": rah.get("core_generation"),
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
            "X01": _sealed_dependency("X01", "X01-0001", "E0203", "E0204"),
        },
        "next_action": "SEAL_X02_0001_THEN_RECOMPUTE_DAG",
        "regression_baseline": _sealed_dependency("V03", "V03-0001", "E0239", "E0240"),
        "regression_baseline_note": (
            "V03-0001 is the live latest-sealed attempt (highest core generation "
            "on the ledger frontier) at the time this evidence was built."
        ),
        "status": "PASS",
    }


def write_scope_verification() -> dict[str, Any]:
    # The runner authors write-scope-verification.json over the whole approved
    # scope; the builder re-derives the product hashes live, pins them, and
    # confirms the recorded receipt is exactly those bytes.
    assert_hashes(EXPECTED_PRODUCT_HASHES)
    component_root = ROOT / COMPONENT
    relatives = sorted(
        path.relative_to(ROOT).as_posix()
        for path in component_root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )
    live_hashes = {
        relative: "sha256:" + sha256(ROOT / relative) for relative in relatives
    }
    pinned = {
        relative: "sha256:" + digest
        for relative, digest in EXPECTED_PRODUCT_HASHES.items()
    }
    if live_hashes != pinned:
        raise SystemExit("write-scope product hashes drifted from the pinned set")
    record = read_json(ATTEMPT / "write-scope-verification.json")
    if (
        record.get("attempt_id") != ATTEMPT_ID
        or record.get("status") != "PASS"
        or record.get("approved_scope") != APPROVED_SCOPE
        or record.get("product_file_hashes") != live_hashes
        or record.get("write_scope_violation_count") != 0
        or record.get("schema_or_test_weakening_count") != 0
        or record.get("root_canonical_source_mutation_count") != 0
        or record.get("reset_clean_stash_commit_push_performed") is not False
        or record.get("checked_file_count") != len(relatives)
    ):
        raise SystemExit(
            f"write-scope-verification receipt is not conformant: {record}"
        )
    return record


def package_verification(regression: dict[str, Any]) -> dict[str, Any]:
    suites = regression["suites"]
    adapter_covering = (
        "claude_schema_check",
        "claude_adapter_test",
        "claude_adversarial_tests",
        "claude_receipts",
    )
    return {
        "attempt_id": ATTEMPT_ID,
        "declaring_sources": {
            "host_binding": (
                "adapters/claude-code/claude-binding.json (the declared Claude "
                "Code host binding; admitted, never invented)"
            ),
            "role_mapping": (
                "adapters/claude-code/role_mapping.yaml cross-checked row-for-row "
                "against manifests/role_registry.yaml (roles are read, not "
                "restated)"
            ),
        },
        "exit_criteria": {
            "parallel_writes_isolated": {
                "mechanism": (
                    "each parallel write request yields a worktree plan whose "
                    "branch, path and write scope are disjoint from every other "
                    "plan in the wave; overlapping scopes are refused and the "
                    "plan never claims isolation it does not prove — the "
                    "worktree-isolation test asserts disjointness and refusal"
                ),
                "status": "PASS",
            },
            "role_specs_generate_custom_agents": {
                "mechanism": (
                    "each RoleSpec in the declared mapping generates exactly one "
                    "custom agent definition whose frontmatter and tool grants are "
                    "derived from the role registry; the binding receipt "
                    "re-derives its own content hash over the payload facts it "
                    "verified"
                ),
                "status": "PASS",
            },
        },
        "required_checks": {
            "claude_adapter_test": {
                "covered_by": list(adapter_covering),
                "status": "PASS",
                "test_count": sum(
                    suites[name]["collected"] for name in adapter_covering
                ),
            },
            "independent_review": {
                "evidence": (
                    "review.md (author: bounded X02 implementation agent; "
                    "reviewer: the sealing session, which did not author this "
                    "attempt; actor_independence between author and reviewer "
                    "holds, external certification does not)"
                ),
                "status": "PASS",
            },
            "worktree_isolation_test": {
                "covered_by": ["claude_worktree_isolation_test"],
                "status": "PASS",
                "test_count": suites["claude_worktree_isolation_test"]["collected"],
            },
        },
        "status": "PASS",
        "suite_counts": {name: row["collected"] for name, row in suites.items()},
    }


def command_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for name in RUN_RESULTS:
        value = read_json(ATTEMPT / f"{name}.run.json")
        record = {
            "attempt_id": ATTEMPT_ID,
            "exit_code": value["exit_code"],
            "recorded_at_utc": RECORDED_AT,
            "status": value["status"],
            "step": name,
        }
        if "command" in value:
            record["command"] = value["command"]
        else:
            record["commands"] = value["commands"]
        records.append(record)
    records.append(
        {
            "attempt_id": ATTEMPT_ID,
            "command": [
                "python",
                "-B",
                f"{ATTEMPT_DIR}/build_x02_0001_evidence.py",
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
        "# X02-0001 independent review of bounded-agent work\n"
        "\n"
        "- Author: a bounded implementation agent (X02 maker) that produced the\n"
        "  Claude Code adapter under the frozen write scope\n"
        "  adapters/claude-code/**. Reviewer: the sealing session, which did not\n"
        "  author this attempt. Author/reviewer separation holds\n"
        "  (actor_independence=true); external actor-independent certification\n"
        "  does not.\n"
        "- Mode: INDEPENDENT_REVIEW_OF_BOUNDED_AGENT_WORK. Blocking findings: 0.\n"
        "- Scope: the write scope is adapters/claude-code/** only. No schema,\n"
        "  manifest, adapter tree outside claude-code, or .rah/ state was touched;\n"
        "  the product files sit exactly inside the granted scope and are\n"
        "  hash-pinned.\n"
        "- Mappings are declared, never invented: role_mapping.yaml is\n"
        "  cross-checked row-for-row against manifests/role_registry.yaml, the\n"
        "  Claude Code host binding is read from claude-binding.json, and every\n"
        "  emitted binding and worktree-plan receipt re-derives its own hash.\n"
        "- RoleSpecs generate custom agents: each declared role maps to exactly\n"
        "  one custom agent definition whose frontmatter and tool grants are\n"
        "  derived from the registry rather than restated; an undeclared role and\n"
        "  an unknown role candidate are refused.\n"
        "- Parallel writes are isolated: each parallel write yields a worktree\n"
        "  plan with a disjoint branch, path and write scope; overlapping scopes\n"
        "  are refused, and the plan never claims isolation it does not prove.\n"
        "- Authority boundary: no adapter, role or worktree plan acquires\n"
        "  evaluator, holdout or promotion authority, and the adapter launches no\n"
        "  agent and creates no worktree (it plans and translates only).\n"
        "- Gates at review time: claude-schema-check 12/12, claude-adapter-test\n"
        "  10/10, claude-adversarial-tests 21/21, claude-worktree-isolation-test\n"
        "  9/9, claude-receipts 10/10, the sealed X01 Codex adapter dependency\n"
        "  regression 68/68, the full Node suite green with the five X02 Claude\n"
        "  Code modules inside the inventory, and git diff --check clean.\n"
        "  Dependency X01-0001 is bound and V03-0001 is the live latest-sealed\n"
        "  regression baseline.\n"
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
            "path": f"{ATTEMPT_DIR}/{name}",
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in sorted(set(output_names))
    ]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "X02_CLAUDE_CODE_SKILLS_AGENTS_WORKTREE_ADAPTER",
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependency_state": dependencies,
        "exit_criteria": {key: "PASS" for key in verification["exit_criteria"]},
        "global_implementation_gate": "fail",
        "history_and_worktree": {
            "dirty_worktree_preserved": True,
            "prior_attempts_reports_and_rah_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
            "subagents_or_fleet_used": True,
        },
        "implementation_status": "PASS",
        "next_package": "RECOMPUTE_DAG",
        "not_claimed": [
            "any adapter, role or worktree plan acquiring evaluator, holdout, or promotion authority",
            "any role mapping or host binding invented rather than declared and cross-checked",
            "launching any custom agent or creating any git worktree (the adapter plans and translates only)",
            "actor-independent certification of this review",
            "overall product completion",
            "release or production readiness",
            "completion_ready=true",
        ],
        "output_artifacts": artifacts,
        "package_status": "PASS",
        "regression": regression,
        "required_checks": verification["required_checks"],
        "review": {
            "actor_independence": True,
            "assurance_limitation": (
                "Author/reviewer separation holds (a bounded X02 implementation "
                "agent authored, the sealing session reviewed); external "
                "actor-independent certification does not."
            ),
            "blocking_finding_count": 0,
            "mode": "INDEPENDENT_REVIEW_OF_BOUNDED_AGENT_WORK",
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
        "next_action": "SEAL_X02_0001_THEN_RECOMPUTE_DAG",
        "package_status": "PASS",
        "status": "PASS",
    }


def build() -> dict[str, Any]:
    for name in RUN_RESULTS:
        check_run(name)
    normalize_junits()
    regression = regression_evidence()
    dependencies = dependency_status()
    write_scope = write_scope_verification()
    verification = package_verification(regression)
    write_json("dependency-status.json", dependencies)
    write_json("x02-verification.json", verification)
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
        raise SystemExit("X02-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "x02-verification.json")
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
    verification = read_json(ATTEMPT / "x02-verification.json")
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
        raise SystemExit("stored X02-0001 report is not the deterministic document")
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
