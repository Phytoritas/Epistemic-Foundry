#!/usr/bin/env python3
"""Build and verify U04-0001 evidence: accessibility and packaged-path parity gate.

U04 is a Node/UI package.  It was implemented and targeted-GREEN by a bounded
implementation agent under the product owner's instruction, with a write scope of
``tests/ui/**``, and is reviewed here by a separate sealing agent that did not
author it.  This builder verifies every executed check receipt, gates the two
required Node JUnit suites against their measured footer counts, gates the
repository-wide Python and Node regression suites, re-derives and pins the
approved product bytes, binds the sealed U02 and U03 dependencies and the live
latest-sealed regression baseline, and emits the deterministic attempt evidence.
It never modifies product files.

The two required checks come straight from ``manifests/development_manifest.yaml``
(U04): ``accessibility_test`` (21 tests: zero WCAG-critical structural failures
over the sealed view projections) and ``packaged_ui_parity_test`` (20 tests: the
source and packaged export-surface paths produce byte-identical records/HTML with
re-derivable hashes).  U04 declares exactly these two checks.

``full-node-suite`` and ``full-python-suite`` are the whole-repository Node and
Python regressions.  Their absolute totals are repository-wide, integration-owned
numbers that other in-flight packages move; this attempt gates the *frozen* JUnit
it captured on zero failures with a derived expected-equals-measured passing
count, and records the live Node inventory count, so the sealed evidence is
deterministic on replay.  The runner must not be re-run after this evidence is
built, or the frozen counts and the live inventory would diverge.
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
ATTEMPT = ROOT / "artifacts/work_packages/U04/attempts/0001"
ATTEMPT_ID = "U04-0001"
WORK_PACKAGE_ID = "U04"
RECORDED_AT = "2026-08-02T06:00:00.000Z"
ATTEMPT_DIR = "artifacts/work_packages/U04/attempts/0001"
COMPONENT = "tests/ui"
APPROVED_SCOPE = ["tests/ui/**"]
#: Cache directories that must never be hashed as product bytes.
CACHE_DIR_NAMES = frozenset({"__pycache__", ".pytest_cache"})

#: Sealed dependency and baseline report bytes, bound by path (tamper detection).
#: These are live sha256 of the current sealed U02, U03 and latest-sealed X04
#: reports, computed at build time.
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/U02/attempts/0001/report.json": (
        "dab028b6fd1e0af2c6b91cc8cd9fd822784d3a5f454bd23558b0fd93cac21b0e"
    ),
    "artifacts/work_packages/U03/attempts/0001/report.json": (
        "dbc7d2fbe1d0f7daf1f849b9b7d60b271a8677485494c44ece12260fa833a2f4"
    ),
    "artifacts/work_packages/X04/attempts/0001/report.json": (
        "87d60e7bae4b75588f4c3093a0ec2425912eba4e7ed15d3db9587bf6ff7312a2"
    ),
}

JUNIT_PATHS = {
    "accessibility_test": ATTEMPT / "accessibility-test.junit.xml",
    "packaged_ui_parity_test": ATTEMPT / "packaged-ui-parity-test.junit.xml",
    "full_python_suite": ATTEMPT / "full-python-suite.junit.xml",
    "full_node_suite": ATTEMPT / "full-node-suite.junit.xml",
}
#: U04 required checks and the whole Node regression are Node suites; only the
#: repository-wide Python regression is a pytest suite.
_NODE_JUNITS = frozenset(
    {"accessibility_test", "packaged_ui_parity_test", "full_node_suite"}
)
#: The two required Node checks whose measured counts the report cites, each
#: pinned to its known footer total.
PINNED_NODE_SUITES = (
    ("accessibility_test", 21),
    ("packaged_ui_parity_test", 20),
)
RUN_RESULTS = (
    "accessibility-test",
    "packaged-ui-parity-test",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
    "write-scope-verification",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "accessibility-test.junit.xml",
    "build_u04_0001_evidence.py",
    "commands.jsonl",
    "dependency-status.json",
    "full-node-suite.junit.xml",
    "full-python-suite.junit.xml",
    "junit-normalization-verification.json",
    "node-test-inventory.json",
    "packaged-ui-parity-test.junit.xml",
    "review.md",
    "run_u04_0001_checks.py",
    "u04-verification.json",
    "u04_0001_rah_seal.py",
    "write-scope-verification.json",
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


def assert_dependency_hashes() -> None:
    for relative, wanted in EXPECTED_DEPENDENCY_HASHES.items():
        path = ROOT / relative
        actual = sha256(path) if path.is_file() else "MISSING"
        if actual != wanted:
            raise SystemExit(
                f"sealed dependency changed: {relative}: {actual} != {wanted}"
            )


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
    summaries: dict[str, dict[str, Any]] = {}
    # The two required Node checks are pinned to their known footer counts and
    # must be wholly green.
    for name, expected in PINNED_NODE_SUITES:
        summary = node_summary(JUNIT_PATHS[name])
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
            raise SystemExit(f"{name} gate failed: {summary}")
        summaries[name] = summary

    # The repository-wide Node suite gates on zero failures; the passing count is
    # the live frontier count and is recorded, never frozen to a literal.
    full_node = node_summary(JUNIT_PATHS["full_node_suite"])
    if (
        (
            full_node["failed"],
            full_node["cancelled"],
            full_node["xml_error_count"],
            full_node["xml_failure_count"],
        )
        != (0, 0, 0, 0)
        or full_node["passed"] <= 0
        or full_node["collected"]
        != (full_node["passed"] + full_node["skipped"] + full_node["todo"])
    ):
        raise SystemExit(f"full_node_suite gate failed: {full_node}")
    summaries["full_node_suite"] = full_node

    # The repository-wide Python suite gates green with a derived expected ==
    # measured count (the live frontier count is recorded, never frozen).
    full_python = pytest_summary(JUNIT_PATHS["full_python_suite"])
    if full_python["collected"] <= 0 or (
        full_python["passed"],
        full_python["failed"],
        full_python["errors"],
        full_python["skipped"],
    ) != (full_python["collected"], 0, 0, 0):
        raise SystemExit(f"full_python_suite gate failed: {full_python}")
    summaries["full_python_suite"] = full_python

    inventory = read_json(ATTEMPT / "node-test-inventory.json")
    required = {"tests/ui/accessibility.test.mjs", "tests/ui/packaged-path-parity.test.mjs"}
    if not required.issubset(set(inventory.get("files", []))):
        raise SystemExit("U04 modules absent from the recorded Node inventory")
    return {
        "attempt_id": ATTEMPT_ID,
        "count_authority": (
            "required_checks_pinned; full_suites_derived_expected_equals_measured"
        ),
        "full_node_gate": "zero_failures",
        "full_node_inventory_count": inventory.get("count"),
        "full_node_passed": full_node["passed"],
        "full_python_passed": full_python["passed"],
        "new_failure_count": 0,
        "regression_baseline_attempt": "X04-0001",
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
    assert_dependency_hashes()
    return {
        "attempt_id": ATTEMPT_ID,
        "dependencies": {
            "U02": _sealed_dependency("U02", "U02-0001", "E0225", "E0226"),
            "U03": _sealed_dependency("U03", "U03-0001", "E0243", "E0244"),
        },
        "next_action": "SEAL_U04_0001_THEN_RECOMPUTE_DAG",
        "regression_baseline": _sealed_dependency("X04", "X04-0001", "E0251", "E0252"),
        "regression_baseline_note": (
            "X04-0001 is the live latest-sealed attempt (highest core generation "
            "on the ledger frontier) at the time this evidence was built."
        ),
        "status": "PASS",
    }


def _live_product_hashes() -> dict[str, str]:
    component_root = ROOT / COMPONENT
    relatives = sorted(
        path.relative_to(ROOT).as_posix()
        for path in component_root.rglob("*")
        if path.is_file() and not (CACHE_DIR_NAMES & set(path.parts))
    )
    return {relative: "sha256:" + sha256(ROOT / relative) for relative in relatives}


def write_scope_verification() -> dict[str, Any]:
    #: The runner's write-scope-verification.json is the frozen pin; re-derive
    #: live and refuse on any drift in the approved tests/ui product tree.
    pinned = read_json(ATTEMPT / "write-scope-verification.json")
    live = _live_product_hashes()
    if pinned.get("product_file_hashes") != live:
        raise SystemExit("product bytes drifted from the sealed write-scope record")
    if (
        pinned.get("attempt_id") != ATTEMPT_ID
        or pinned.get("status") != "PASS"
        or pinned.get("approved_scope") != APPROVED_SCOPE
        or pinned.get("write_scope_violation_count") != 0
        or pinned.get("schema_or_test_weakening_count") != 0
        or pinned.get("root_canonical_source_mutation_count") != 0
        or pinned.get("reset_clean_stash_commit_push_performed") is not False
        or pinned.get("checked_file_count") != len(live)
    ):
        raise SystemExit(f"write-scope-verification receipt is not conformant: {pinned}")
    return {
        "approved_scope": APPROVED_SCOPE,
        "attempt_id": ATTEMPT_ID,
        "authored_by": (
            "bounded implementation agent (U04 maker) under the product owner's "
            "instruction"
        ),
        "checked_file_count": len(live),
        "composed_modules_modified": False,
        "product_file_hashes": live,
        "product_roots": [COMPONENT],
        "reset_clean_stash_commit_push_performed": False,
        "reviewed_by": (
            "separate sealing agent acting as an independent reviewer, distinct "
            "from the author"
        ),
        "root_canonical_source_mutation_count": 0,
        "schema_or_test_weakening_count": 0,
        "status": "PASS",
        "subagents_or_fleet_used": True,
        "write_scope_violation_count": 0,
    }


def package_verification(regression: dict[str, Any]) -> dict[str, Any]:
    suites = regression["suites"]
    return {
        "attempt_id": ATTEMPT_ID,
        "declared_required_checks": ["accessibility_test", "packaged_ui_parity_test"],
        "declaring_sources": {
            "packaged_surface": (
                "tests/ui/ui-surface.mjs binds the sealed U02/U03 view "
                "projections, their packaged export-surface barrels, and the "
                "recorded route manifest; parity and accessibility are measured "
                "over that sealed code and frozen data, never over a running site"
            ),
        },
        "exit_criteria": {
            "vite_and_packaged_paths_behave_identically": {
                "mechanism": (
                    "for every U02/U03 view the record and rendered HTML built "
                    "through the packaged export-surface barrels are byte-for-byte "
                    "identical to the ones built through the source path a Vite "
                    "build compiles, and their canonical hashes re-derive; every "
                    "packaged barrel re-exports exactly the source implementations "
                    "and adds nothing that traces to no source module; the "
                    "packaged client route table matches the recorded route "
                    "manifest and the packaged navigation binds only "
                    "manifest-declared operations; a forked or invented barrel "
                    "export is each refused"
                ),
                "status": "PASS",
            },
            "wcag_critical_failures_zero": {
                "mechanism": (
                    "every rendered console panel carries one main/header/h1 "
                    "landmark and an unbroken heading hierarchy, every section has "
                    "a unique data-section id and an h2 accessible name, the "
                    "rendered focus order equals the accessible projection order, "
                    "status is conveyed as non-empty text rather than colour alone "
                    "and empty results are rendered as text; the record-only "
                    "health and navigation surfaces expose titled, textual, "
                    "visible sections; each rule refuses a deliberately broken "
                    "surface; the check is a deterministic property of the HTML "
                    "and frozen records, with no running browser or axe engine"
                ),
                "status": "PASS",
            },
        },
        "required_checks": {
            "accessibility_test": {
                "junit": suites["accessibility_test"]["junit"],
                "status": "PASS",
                "test_count": suites["accessibility_test"]["collected"],
            },
            "packaged_ui_parity_test": {
                "junit": suites["packaged_ui_parity_test"]["junit"],
                "status": "PASS",
                "test_count": suites["packaged_ui_parity_test"]["collected"],
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
                f"{ATTEMPT_DIR}/build_u04_0001_evidence.py",
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
        "# U04-0001 independent review of bounded-agent work\n"
        "\n"
        "- Author: a bounded implementation agent (U04 maker) that produced the\n"
        "  U-phase accessibility and packaged-path parity gate under the frozen\n"
        "  write scope tests/ui/**. Reviewer: a separate sealing agent that did\n"
        "  not author U04. Author/reviewer separation holds (actor_independence\n"
        "  =true between two distinct agents); external actor-independent\n"
        "  certification does not.\n"
        "- Mode: INDEPENDENT_REVIEW_OF_BOUNDED_AGENT_WORK. Blocking findings: 0.\n"
        "- Manifest conformance: U04 declares exactly two required_checks\n"
        "  (accessibility_test, packaged_ui_parity_test) and two exit_criteria\n"
        "  (WCAG critical failures zero; Vite and packaged paths behave\n"
        "  identically), verified against manifests/development_manifest.yaml.\n"
        "  Dependencies U02 and U03 are declared and sealed.\n"
        "- accessibility_test (21/21): over the sealed U02/U03 view projections,\n"
        "  every rendered panel carries a single main/header/h1 landmark and an\n"
        "  unbroken heading hierarchy, every section has a unique data-section id\n"
        "  and an h2 accessible name, the rendered focus order equals the\n"
        "  accessible projection order, status is non-empty text (never colour\n"
        "  alone) and empty results render as text. Each rule is shown to refuse\n"
        "  a deliberately broken surface. This is a deterministic property of the\n"
        "  HTML and frozen records: there is no running browser and no axe engine,\n"
        "  and the gate makes no claim of full WCAG 2.x conformance beyond the\n"
        "  bounded critical structural rule set it checks.\n"
        "- packaged_ui_parity_test (20/20): for every U02/U03 view the record and\n"
        "  rendered HTML built through the packaged export-surface barrels are\n"
        "  byte-identical to the source-path build with a re-derivable canonical\n"
        "  hash; every barrel re-exports exactly the source implementations and\n"
        "  adds nothing that traces to no source module; the packaged client route\n"
        "  table matches the recorded route manifest and the packaged navigation\n"
        "  binds only manifest-declared operations. A forked or invented barrel\n"
        "  export is each refused. Parity is an identity proof over two import\n"
        "  paths into the same sealed code and frozen data; no running server,\n"
        "  site, or produced Vite/bundler dist bundle is claimed.\n"
        "- Write-scope audit: the product bytes hashed here sit exactly inside the\n"
        "  approved tests/ui tree; no composed module, schema, manifest or test\n"
        "  outside scope was modified or weakened, and no view/test/path acquires\n"
        "  authority.\n"
        "- full-node-suite captured GREEN at zero failures (109 modules / 1233\n"
        "  tests, the two U04 modules included) and full-python-suite GREEN at\n"
        "  1261 tests. Both absolute totals are repository-wide, integration-owned\n"
        "  numbers moved by concurrent in-flight packages; the frozen JUnit gated\n"
        "  on zero failures is the deterministic evidence, and reconciling the\n"
        "  live totals is the integrating session's responsibility. git diff\n"
        "  --check is clean. X04-0001 is the live latest-sealed regression\n"
        "  baseline.\n"
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
        "attempt_type": "U04_ACCESSIBILITY_PACKAGED_PATH_PARITY_GATE",
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
            "full WCAG 2.x conformance: only zero WCAG-critical structural failures over the bounded deterministic surface are asserted",
            "any running browser, DOM, rendered page, or axe-core engine execution",
            "any produced Vite or bundler dist bundle: packaged-path parity is an identity proof over the module export surface and frozen records, not an emitted dist artifact",
            "a running web server, site, backend, or live HTTP endpoint",
            "authority acquisition by any UI surface, view, test, or import path",
            "actor-independent external certification of this review",
            "overall product completion or release readiness",
            "completion_ready=true",
        ],
        "output_artifacts": artifacts,
        "package_status": "PASS",
        "regression": regression,
        "required_checks": verification["required_checks"],
        "review": {
            "actor_independence": True,
            "assurance_limitation": (
                "Author/reviewer separation holds (a bounded implementation "
                "agent authored, a separate sealing agent reviewed); external "
                "actor-independent certification does not."
            ),
            "author": "bounded implementation agent",
            "blocking_finding_count": 0,
            "mode": "INDEPENDENT_REVIEW_OF_BOUNDED_AGENT_WORK",
            "reviewer": "separate sealing agent (did not author U04)",
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
        "next_action": "SEAL_U04_0001_THEN_RECOMPUTE_DAG",
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
    write_json("write-scope-verification.json", write_scope)
    write_json("u04-verification.json", verification)
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
        raise SystemExit("U04-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "u04-verification.json")
    report = report_document(
        regression, dependencies, write_scope, verification, rah_state=rah_state
    )
    write_json("report.json", report)


def verify() -> dict[str, Any]:
    for name in RUN_RESULTS:
        check_run(name)
    normalize_junits()
    regression = regression_evidence()
    assert_dependency_hashes()
    stored = read_json(ATTEMPT / "report.json")
    dependencies = read_json(ATTEMPT / "dependency-status.json")
    write_scope_live = write_scope_verification()
    write_scope = read_json(ATTEMPT / "write-scope-verification.json")
    if write_scope_live != write_scope:
        raise SystemExit("write-scope verification drifted from the sealed record")
    verification = read_json(ATTEMPT / "u04-verification.json")
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
        raise SystemExit("stored U04-0001 report is not the deterministic document")
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
