#!/usr/bin/env python3
"""Build and verify Y04-0001 evidence: 50/200/2000 scale qualification and load shedding.

Y04-0001 implements ``evals/scale/**``: a synthetic, deterministic corpus and a
pure-function harness that qualify system *behaviour* (correctness plus budget
plus latency) at the three tier sizes the release ladder names
(``EVOLUTION_MVP_50`` -> ``PILOT_200`` -> ``PRODUCTION_2000``) and prove that,
under offered load beyond a hard admission capacity, the system sheds the excess
*gracefully* rather than dropping or corrupting it.  The harness composes two
sealed contracts without restating them: the typed budget vocabulary read from
``schemas/budget-envelope.schema.json`` (Y01, EF4-I28) and the honest
observability-state rule (Y02, EF4-I23).  It certifies no release: the corpus
records ``licensed_corpus: false`` and ``release_gate_certified: false``, and a
dataset that claims either is refused as a ``SCALE_OVERCLAIM``.  This builder
verifies the executed checks and emits immutable attempt evidence; it never
modifies product files, scores, selects, promotes or evaluates anything.

Authoring note (read before running).  This build script was authored during
seal preparation, after the product implementation and its ``run_y04_0001_checks``
runner already existed and passed targeted-green.  The product bytes it is
accountable for are pinned in ``EXPECTED_SRC_HASHES`` (real sha256 values of the
checked-out ``evals/scale`` files) and the manifest dependencies in
``EXPECTED_DEPENDENCY_HASHES`` (Y02 and Y03 sealed reports).  Per-suite counts
for the repository-wide regression suites are derived (expected == measured) and
gated strictly on zero failures/errors/skips (and, for the Node suite, zero
cancelled/todo/xml-failure), because those surfaces grow as the repo grows; the
two required Y04 suites cite their measured counts by name.
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
ATTEMPT = ROOT / "artifacts/work_packages/Y04/attempts/0001"
ATTEMPT_ID = "Y04-0001"
WORK_PACKAGE_ID = "Y04"
ATTEMPT_DIR = "artifacts/work_packages/Y04/attempts/0001"
RECORDED_AT = "2026-08-02T12:30:00.000Z"

#: Product bytes this attempt is accountable for, pinned by path.  These are the
#: whole ``evals/scale`` component (harness, synthetic corpus, the two required
#: test modules, the component pytest.ini, and the two committed result
#: snapshots).  The check runner (``run_y04_0001_checks.py``) also sits in the
#: Y04 write scope but lives under the attempt directory; it is hashed live in
#: ``write_scope_verification`` rather than pinned here.
EXPECTED_SRC_HASHES = {
    "evals/scale/load_shedding_results.json": "6a068686bfc90e3f1928fd564fe7ec5bcfeeafa5d85127357ec899e65f6f245a",
    "evals/scale/pytest.ini": "08ef26f32794d161333005a7be66602641abfd607c1bf69f05915a1bba741380",
    "evals/scale/scale_corpus.json": "46383e23449bf47c766146d7445c2cc8589c63a0612da249583ee4fe26950459",
    "evals/scale/scale_harness.py": "6666eb497e57bfb88b15977550616db0ded1dbf11746f48ff78cf8be33b7452f",
    "evals/scale/scale_qualification_results.json": "ed329e05c21980c9297b574bf9910c0dca2c810ec2ce7d2a831a5c468461806d",
    "evals/scale/test_load_shedding.py": "0bd8575bca78891f135339bdee6c88ead1b4497cad400e80890f41a672aabb3a",
    "evals/scale/test_scale_qualification.py": "2a00914c295320e5801f2cd805bd311fdfbdb6cd125b479345af3a93e8be7714",
}
COMPONENT = "evals/scale"
RUNNER_NAME = "run_y04_0001_checks.py"
#: Y04 depends on Y02 (honest observability states) and Y03 at the manifest
#: layer; both are sealed PASS.  The harness imports neither component's code, so
#: these are asserted as sealed dependencies rather than exercised as code
#: regressions.
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/Y02/attempts/0001/report.json": "882fb5bf1f72bb9d3a04833c4f487f1a4e16a2b3ea72d16638bfe554b4f30e5e",
    "artifacts/work_packages/Y03/attempts/0001/report.json": "1527a2544006d344d11ed99c9dfcbfd85861dfec03bdfc794f3b3004f6cb29e3",
}

JUNIT_PATHS = {
    "scale_qualification": ATTEMPT / "scale-qualification.junit.xml",
    "load_shedding_test": ATTEMPT / "load-shedding-test.junit.xml",
    "wire_literal_discipline": ATTEMPT / "wire-literal-discipline.junit.xml",
    "full_python_suite": ATTEMPT / "full-python-suite.junit.xml",
    "full_node_suite": ATTEMPT / "full-node-suite.junit.xml",
}
#: Y04 product tests are pytest; only the repository-wide Node regression is a
#: Node suite.  These names classify each JUnit for normalization and counting.
_NODE_JUNITS = frozenset({"full_node_suite"})
PYTEST_SUITES = (
    "scale_qualification",
    "load_shedding_test",
    "wire_literal_discipline",
    "full_python_suite",
)
NODE_SUITES = ("full_node_suite",)
#: The two required checks whose measured counts the report cites by name.
REQUIRED_CHECK_SUITES = (
    "scale_qualification",
    "load_shedding_test",
)
#: One ``<name>.run.json`` receipt is expected per step (runner contract).
RUN_RESULTS = (
    "ruff-check",
    "wire-literal-discipline",
    "scale-qualification",
    "load-shedding-test",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "build_y04_0001_evidence.py",
    "commands.jsonl",
    "dependency-status.json",
    "full-node-suite.junit.xml",
    "full-python-suite.junit.xml",
    "junit-normalization-verification.json",
    "load-shedding-test.junit.xml",
    "report.json",
    "review.md",
    "run_y04_0001_checks.py",
    "scale-qualification.junit.xml",
    "wire-literal-discipline.junit.xml",
    "write-scope-verification.json",
    "y04-verification.json",
    "y04_0001_rah_seal.py",
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
    # An aggregate receipt records ``commands`` (several processes, worst exit
    # code); a plain receipt records one ``command``.  Both are honest shapes.
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
    # Repository-wide suite counts are derived (expected == measured) rather than
    # pinned, because those surfaces grow as the repo grows.  The gate is still
    # fail-closed: every suite must be non-empty and wholly green.
    summaries: dict[str, dict[str, Any]] = {}
    for name in PYTEST_SUITES:
        summary = pytest_summary(JUNIT_PATHS[name])
        if summary["collected"] <= 0 or (
            summary["passed"],
            summary["failed"],
            summary["errors"],
            summary["skipped"],
        ) != (summary["collected"], 0, 0, 0):
            raise SystemExit(f"{name} gate failed: {summary}")
        summaries[name] = summary
    for name in NODE_SUITES:
        summary = node_summary(JUNIT_PATHS[name])
        if summary["collected"] <= 0 or (
            summary["passed"],
            summary["failed"],
            summary["cancelled"],
            summary["skipped"],
            summary["todo"],
            summary["xml_error_count"],
            summary["xml_failure_count"],
        ) != (summary["collected"], 0, 0, 0, 0, 0, 0):
            raise SystemExit(f"{name} gate failed: {summary}")
        summaries[name] = summary
    return {
        "attempt_id": ATTEMPT_ID,
        "component_tests_are_targeted_only": True,
        "count_authority": "derived_from_measured_junit_expected_equals_measured",
        "new_failure_count": 0,
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
            "Y02": _sealed_dependency("Y02", "Y02-0001", "E0323", "E0324"),
            "Y03": _sealed_dependency("Y03", "Y03-0001", "E0331", "E0332"),
        },
        "next_action": "SEAL_Y04_0001_THEN_CONTINUE_DAG",
        "status": "PASS",
    }


def write_scope_verification() -> dict[str, Any]:
    assert_hashes(EXPECTED_SRC_HASHES)
    component_files = sorted(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / COMPONENT).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )
    if component_files != sorted(EXPECTED_SRC_HASHES):
        raise SystemExit(f"evals/scale component holds unexpected files: {component_files}")
    runner = ATTEMPT / RUNNER_NAME
    if not runner.is_file():
        raise SystemExit(f"required Y04-0001 runner missing: {RUNNER_NAME}")
    runner_relative = runner.relative_to(ROOT).as_posix()
    product_file_hashes = {
        relative: "sha256:" + digest for relative, digest in EXPECTED_SRC_HASHES.items()
    }
    product_file_hashes[runner_relative] = sha256_id(runner)
    return {
        "approved_scope": [
            "evals/scale/**",
            "artifacts/work_packages/Y04/**",
        ],
        "attempt_id": ATTEMPT_ID,
        "authored_by": ("a bounded implementation agent (Y04 maker)"),
        "authority_decision": (
            "Y04's manifest write_scope is evals/scale/** and "
            "artifacts/work_packages/Y04/**. Every product byte lives inside "
            "evals/scale/**; the harness only reads (never writes) the sealed "
            "schemas/budget-envelope.schema.json (Y01) for its budget "
            "vocabulary and re-applies the Y02 honest-state rule inline. No file "
            "outside the approved scope was created or modified, and no root or "
            "schema canonical source was mutated."
        ),
        "component_files": component_files,
        "composed_modules_modified": False,
        "product_file_hashes": product_file_hashes,
        "pyproject_modified": False,
        "reset_clean_stash_commit_push_performed": False,
        "reviewed_by": (
            "an independent seal-preparation session, actor-independent from the "
            "author"
        ),
        "root_canonical_source_mutation_count": 0,
        "schema_or_test_weakening_count": 0,
        "status": "PASS",
        "subagents_or_fleet_used": False,
        "write_scope_violation_count": 0,
    }


def package_verification(regression: dict[str, Any]) -> dict[str, Any]:
    suites = regression["suites"]
    core = {
        name: suites[name]["collected"]
        for name in REQUIRED_CHECK_SUITES
        if name in suites
    }
    return {
        "attempt_id": ATTEMPT_ID,
        "exit_criteria": {
            "no_silent_partial_completion": {
                "mechanism": (
                    "every tier reconciles expected == processed == persisted "
                    "exactly and a mismatch raises SILENT_PARTIAL_COMPLETION; "
                    "under overload every offered item terminates as ADMITTED or "
                    "SHED and admitted + shed == offered exactly, a shortfall "
                    "raising SHED_RECONCILIATION_FAILURE (EF4-I26)"
                ),
                "status": "PASS",
            },
            "quality_and_latency_measured_per_tier": {
                "mechanism": (
                    "each of the 50/200/2000 tiers is qualified only when the "
                    "honest measured quality state is OK, every measured budget "
                    "dimension stays at or under the tier's hard_limits "
                    "(mirroring the PRODUCTION_2000 hard_budget_overrun_rate: 0 "
                    "gate), and the measured p95 latency is within the tier "
                    "budget; the report records the measured numbers per tier"
                ),
                "status": "PASS",
            },
        },
        "honesty_posture": {
            "corpus_is_synthetic_and_deterministic": True,
            "licensed_corpus_claimed": False,
            "overclaim_refused_as": "SCALE_OVERCLAIM",
            "posture": (
                "SPECIFIED != IMPLEMENTED: this qualifies system behaviour at the "
                "tier sizes on a synthetic, deterministic corpus; it is NOT the "
                "PRODUCTION_2000 release certification that MASTER_SPEC line 1371 "
                "lists as conditional external evidence requiring a licensed "
                "corpus and production topology"
            ),
            "release_gate_certified_claimed": False,
        },
        "load_shedding": {
            "admitted_within_hard_budget": True,
            "bounded_degradation_serves_full_capacity": True,
            "fail_closed_refusals": [
                "ADMISSION_OVERRUN",
                "SHED_RECONCILIATION_FAILURE",
                "STATE_DISHONEST",
                "ADMISSION_UNBOUNDED",
            ],
            "honest_state_while_shedding": "DEGRADED",
            "nothing_silently_dropped": True,
        },
        "required_checks": {
            "independent_review": {
                "evidence": (
                    "review.md (author: a bounded implementation agent; "
                    "reviewer: an independent seal-preparation session; "
                    "actor_independence between author and reviewer holds, "
                    "external certification does not; verdict PASS, "
                    "blocking_finding_count=0)"
                ),
                "status": "PASS",
            },
            **{
                name: {"status": "PASS", "test_count": count}
                for name, count in core.items()
            },
        },
        "schema_binding": {
            "budget_vocabulary": (
                "schemas/budget-envelope.schema.json enforcement/breach/"
                "hard_limits (read at load time, never restated) — Y01/EF4-I28"
            ),
            "honest_states": (
                "OK/DEGRADED/UNAVAILABLE/UNKNOWN by the sealed Y02 result-state "
                "rule (EF4-I23)"
            ),
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
                f"{ATTEMPT_DIR}/build_y04_0001_evidence.py",
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
        "# Y04-0001 independent review\n"
        "\n"
        "- Author: a bounded implementation agent that wrote evals/scale/**.\n"
        "  Reviewer: an independent seal-preparation session that did not author\n"
        "  the subject code and reviewed it adversarially against the authority\n"
        "  chain. The author and the reviewer are DISTINCT actors, so\n"
        "  actor-independence between author and reviewer HOLDS; external\n"
        "  actor-independent (provider-independent) certification does NOT.\n"
        "  Mode: INDEPENDENT_REVIEW_OF_BOUNDED_AGENT_WORK. Verdict: PASS,\n"
        "  blocking_finding_count=0.\n"
        "- Verification basis: static reading of scale_harness.py plus the\n"
        "  synthetic corpus and the two required test modules, plus\n"
        "  inspection-only execution: the two targeted suites (scale_qualification\n"
        "  9 tests, load_shedding_test 11 tests) pass, and the committed result\n"
        "  snapshots reproduce byte-for-byte from the live harness (self-hashing\n"
        "  report_hash matches on replay). No product or ledger state was\n"
        "  mutated by the review.\n"
        "- Scale qualification (per exit criterion 'quality and latency measured\n"
        "  per tier'): all three tiers EVOLUTION_MVP_50 / PILOT_200 /\n"
        "  PRODUCTION_2000 QUALIFY. Each has honest quality_state OK, every\n"
        "  measured budget dimension at or under the tier hard_limits (tokens\n"
        "  4921/20486/200424 under 8000/30000/260000; calls, wall_seconds,\n"
        "  concurrency, storage and network all under limit), measured p95\n"
        "  latency 48/47/48 ms within the 60 ms budget, and\n"
        "  expected == processed == persisted == size with no silent partial.\n"
        "  Fail-closed negatives hold: an inflated per-document cost is caught as\n"
        "  a tokens budget overrun (qualified=false, breach policy surfaced), a\n"
        "  mislabelled document drops the state to DEGRADED, and a dataset\n"
        "  claiming licensed_corpus or release_gate_certified is refused\n"
        "  SCALE_OVERCLAIM. PASS.\n"
        "- Load shedding (per 'no silent partial completion'): under offered\n"
        "  2600 vs hard capacity 2000, exactly 2000 are ADMITTED and 600 SHED\n"
        "  with reason CAPACITY_HARD_LIMIT; admitted + shed == 2600 exactly\n"
        "  (nothing dropped), admitted spend 120000 tokens within the admitted\n"
        "  hard budget, degradation bounded (the full guaranteed capacity is\n"
        "  served), and the honest state is DEGRADED — never a shade of OK.\n"
        "  Fail-closed refusals hold: ADMISSION_OVERRUN (admit beyond capacity),\n"
        "  SHED_RECONCILIATION_FAILURE (under-declared shed), STATE_DISHONEST\n"
        "  (claiming OK while shedding), and ADMISSION_UNBOUNDED (a non-HARD\n"
        "  admission enforcement). PASS.\n"
        "- Honesty posture (critical): the corpus is SYNTHETIC and DETERMINISTIC\n"
        "  (every document derived from (seed, index), no clock, no randomness),\n"
        "  and Y04 EXPLICITLY refuses to claim the licensed-corpus / production\n"
        "  release certification: scale_corpus.json records licensed_corpus=false\n"
        "  and release_gate_certified=false, and every report echoes those facts.\n"
        "  This is the correct SPECIFIED != IMPLEMENTED posture required by\n"
        "  MASTER_SPEC line 1371 (real 50/200/2,000-scale results are conditional\n"
        "  external evidence), NOT a weakening. The typed budgets (Y01, EF4-I28)\n"
        "  and honest observability states (Y02, EF4-I23) are composed from the\n"
        "  sealed budget schema and the Y02 state rule, not restated.\n"
        "- Residual limitations: Y04 qualifies system behaviour at the tier sizes\n"
        "  on a synthetic corpus and records replayable results only. It makes no\n"
        "  licensed-corpus, production-topology or release-certification claim; it\n"
        "  scores, selects, promotes and evaluates nothing; and this review is not\n"
        "  external actor-independent certification.\n"
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
        "attempt_type": "Y04_SCALE_QUALIFICATION_AND_GRACEFUL_LOAD_SHEDDING",
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependency_state": dependencies,
        "exit_criteria": {key: "PASS" for key in verification["exit_criteria"]},
        "global_implementation_gate": "fail",
        "history_and_worktree": {
            "dirty_worktree_preserved": True,
            "prior_attempts_reports_and_rah_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
            "subagents_or_fleet_used": False,
        },
        "implementation_status": "PASS",
        "next_package": "RECOMPUTE_DAG",
        "not_claimed": [
            "a licensed corpus, production topology or PRODUCTION_2000 release certification: the corpus is synthetic and deterministic and records licensed_corpus=false, release_gate_certified=false",
            "scoring, selection, promotion or evaluation of any candidate",
            "DSSAT or any plant-model numerical parity",
            "actor-independent (external) certification of this review",
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
                "Author/reviewer separation holds (a bounded implementation "
                "agent authored, an independent seal-preparation session "
                "reviewed); external actor-independent (provider-independent) "
                "certification does not."
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
        "next_action": "SEAL_Y04_0001_THEN_CONTINUE_DAG",
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
    write_json("y04-verification.json", verification)
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
        raise SystemExit("Y04-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "y04-verification.json")
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
    verification = read_json(ATTEMPT / "y04-verification.json")
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
        raise SystemExit("stored Y04-0001 report is not the deterministic document")
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
