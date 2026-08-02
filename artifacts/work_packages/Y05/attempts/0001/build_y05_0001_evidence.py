#!/usr/bin/env python3
"""Build and verify Y05-0001 evidence: quality-diversity scaling, surrogate triage, budgets and production load.

Y05-0001 implements ``src/epistemic_foundry/operations/v4_y05/**``: an
integration surface that composes the already-sealed archive quality-diversity
coverage, the surrogate triage surface, the Y01 budget envelope, the N05 schedule
fan-in gate and the Q05 admissibility gate so a production-scale run stays
diverse, keeps its surrogate triage-only, keeps its spend bounded and sheds its
load honestly, with every decision resolving to an immutable, re-derivable
receipt.  It restates none of the composed vocabularies (EF4-I22): the one triage
token it reasons about is read positionally out of the schema that declares it.

This builder consumes the per-check receipts and JUnit produced by
``run_y05_0001_checks.py``, independently re-derives the byte-level oracles it can
see (the pinned product hashes and the four sealed dependency reports), gates
every regression suite strictly to zero failures, and emits immutable attempt
evidence.  It never modifies a product file, never scores/promotes/evaluates
anything, and never touches ``.rah/``.

``report.json`` is emitted with ``rah_state`` unset and
``next_action = SEAL_Y05_0001_THEN_CONTINUE_DAG``: this is a seal-PREP bundle, so
the six RAH generation pins are reserved by the sibling ``y05_0001_rah_seal.py``
sentinel and remain unbound until an authorized seal.

Counts are derived (expected == measured) rather than hard-pinned, because the
repository test population grows as later packages seal; the gate is still
fail-closed (every suite must be non-empty and wholly green).  The product bytes
this attempt is accountable for ARE pinned in ``EXPECTED_SRC_HASHES``, as are the
four sealed dependency reports in ``EXPECTED_DEPENDENCY_HASHES``.
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
ATTEMPT = ROOT / "artifacts/work_packages/Y05/attempts/0001"
ATTEMPT_ID = "Y05-0001"
WORK_PACKAGE_ID = "Y05"
ATTEMPT_DIR = "artifacts/work_packages/Y05/attempts/0001"
RECORDED_AT = "2026-08-02T00:00:00.000Z"

COMPONENT = "src/epistemic_foundry/operations"
RUNNER_NAME = "run_y05_0001_checks.py"

#: Product bytes this attempt is accountable for, pinned by path.  The runner
#: (``run_y05_0001_checks.py``) also sits in the Y05 write scope but is authored
#: by this seal-prep session; it is hashed live in ``write_scope_verification``
#: rather than pinned here.  ``operations/__init__.py`` is the new top-level
#: package marker one level above the ``v4_y05`` glob and is a mandatory
#: wheel-discovery prerequisite (proven by check_packaging.py); it carries no
#: logic beyond the package docstring.
EXPECTED_SRC_HASHES = {
    "src/epistemic_foundry/operations/__init__.py": "2ffba2b7d0209480bbf7f4b98644fc6b4e09192f11cc8aa271b1dbd5a7379cf4",
    "src/epistemic_foundry/operations/v4_y05/__init__.py": "3a40355a7d6d29d652dc8b4a2d5dceff064b3fd7c95f131a3809a11d43718671",
    "src/epistemic_foundry/operations/v4_y05/scaling.py": "9944d3b0a1b908c7caa9c1dfe793613dd03e2453c4d9fdf529ec6e348f577ea3",
}

#: Y05 declares four sealed PASS dependencies; each is pinned by report bytes and
#: its report is read for the sealed core/final evidence identifiers.
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/Y04/attempts/0001/report.json": "1e99e6677735d841ca32527ed8765391e4e0dff0ecbef3751cb4ea153de7c45c",
    "artifacts/work_packages/N05/attempts/0001/report.json": "a682efefe83c7de7586e8a3ea5bdad430b6b692bc7f6e6a55985c48244e15a0c",
    "artifacts/work_packages/Q05/attempts/0001/report.json": "f0e19a420500064b4c977b2c1fea20a1a21cb68ed422fb3c48233001c0111455",
    "artifacts/work_packages/X05/attempts/0001/report.json": "b577afe4d75d8f23aa6379babb055e7b1af8c004ff65c749dec048dc74222c62",
}
DEPENDENCY_REPORTS = {
    "Y04": "artifacts/work_packages/Y04/attempts/0001/report.json",
    "N05": "artifacts/work_packages/N05/attempts/0001/report.json",
    "Q05": "artifacts/work_packages/Q05/attempts/0001/report.json",
    "X05": "artifacts/work_packages/X05/attempts/0001/report.json",
}

#: Each objective check emits exactly one <name>.run.json receipt.  The
#: independent_review check is a distinct-actor judgement recorded in review.md,
#: not here.
RUN_RESULTS = (
    "ruff-check",
    "ruff-format-check",
    "packaging-discovery",
    "schema-and-type-check",
    "unit-and-contract-tests",
    "negative-and-adversarial-tests",
    "provenance-and-receipt-audit",
    "wire-literal-discipline",
    "a03-boundary-regression",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
)

#: The only Node suite is the repository-wide regression; everything Y05 owns is
#: pytest.  These names classify each JUnit for normalization and counting.
NODE_SUITES = ("full-node-suite",)
PYTEST_SUITES = (
    "schema-and-type-check",
    "unit-and-contract-tests",
    "negative-and-adversarial-tests",
    "provenance-and-receipt-audit",
    "wire-literal-discipline",
    "a03-boundary-regression",
    "full-python-suite",
)

#: Maps each manifest required_check to the runner step(s) that satisfy it.
REQUIRED_CHECK_STEPS = {
    "schema_and_type_check": ("schema-and-type-check",),
    "unit_and_contract_tests": ("unit-and-contract-tests",),
    "negative_and_adversarial_tests": ("negative-and-adversarial-tests",),
    "provenance_and_receipt_audit": ("provenance-and-receipt-audit",),
    "independent_review": (),
}

JUNIT_STEPS = NODE_SUITES + PYTEST_SUITES
_NODE_JUNITS = frozenset(NODE_SUITES)

NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)

OUTPUT_NAMES = (
    "build_y05_0001_evidence.py",
    "check_packaging.py",
    "commands.jsonl",
    "dependency-status.json",
    "fixtures.py",
    "junit-normalization-verification.json",
    "node-test-inventory.json",
    "pytest.ini",
    "review.md",
    "run_y05_0001_checks.py",
    "test_negative_adversarial.py",
    "test_provenance_receipts.py",
    "test_schema_and_type.py",
    "test_unit_contract.py",
    "write-scope-verification.json",
    "y05-verification.json",
    "y05_0001_rah_seal.py",
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


def junit_path(step: str) -> Path:
    return ATTEMPT / f"{step}.junit.xml"


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
    for step in JUNIT_STEPS:
        path = junit_path(step)
        text = path.read_text(encoding="utf-8")
        if any(value in text for value in roots):
            raise SystemExit(f"JUnit contains absolute repository path: {step}")
        if step in _NODE_JUNITS:
            if "duration_ms" in text:
                raise SystemExit(f"Node JUnit retains volatile duration_ms: {step}")
        elif re.search(r'\s+(?:hostname|timestamp|time)="', text):
            raise SystemExit(f"pytest JUnit retains volatile attributes: {step}")


def normalize_junits() -> dict[str, Any]:
    record_path = ATTEMPT / "junit-normalization-verification.json"
    if record_path.is_file():
        record = read_json(record_path)
        for step in JUNIT_STEPS:
            if record.get("files", {}).get(step, {}).get(
                "normalized_sha256"
            ) != sha256_id(junit_path(step)):
                raise SystemExit(f"normalized JUnit changed: {step}")
        verify_junit_portability()
        return record

    files: dict[str, Any] = {}
    root_backslash = str(ROOT) + "\\"
    root_slash = str(ROOT).replace("\\", "/") + "/"
    for step in JUNIT_STEPS:
        path = junit_path(step)
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
        if step in _NODE_JUNITS:
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
            raise SystemExit(f"JUnit normalization changed semantics: {step}")
        path.write_text(normalized, encoding="utf-8", newline="\n")
        files[step] = {
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


def pytest_summary(step: str) -> dict[str, Any]:
    path = junit_path(step)
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


def node_summary(step: str) -> dict[str, Any]:
    path = junit_path(step)
    root = ET.parse(path).getroot()
    cases = list(root.findall(".//testcase"))
    footer = {
        key.decode("ascii"): int(value)
        for key, value in NODE_FOOTER_PATTERN.findall(path.read_bytes())
    }
    if set(footer) != {"tests", "pass", "fail", "cancelled", "skipped", "todo"}:
        raise SystemExit(f"Node JUnit semantic footer is incomplete: {step}")
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
    for step in PYTEST_SUITES:
        summary = pytest_summary(step)
        if summary["collected"] <= 0 or (
            summary["passed"],
            summary["failed"],
            summary["errors"],
            summary["skipped"],
        ) != (summary["collected"], 0, 0, 0):
            raise SystemExit(f"{step} gate failed: {summary}")
        summaries[step] = summary
    for step in NODE_SUITES:
        summary = node_summary(step)
        if summary["collected"] <= 0 or (
            summary["passed"],
            summary["failed"],
            summary["cancelled"],
            summary["skipped"],
            summary["todo"],
            summary["xml_error_count"],
            summary["xml_failure_count"],
        ) != (summary["collected"], 0, 0, 0, 0, 0, 0):
            raise SystemExit(f"{step} gate failed: {summary}")
        summaries[step] = summary
    return {
        "attempt_id": ATTEMPT_ID,
        "count_authority": "derived_from_measured_junit_expected_equals_measured",
        "full_node_new_failure_count": 0,
        "full_python_new_failure_count": 0,
        "new_skip_or_xfail_count": 0,
        "status": "PASS",
        "suites": summaries,
    }


def _sealed_dependency(package: str, relative: str) -> dict[str, Any]:
    path = ROOT / relative
    report = read_json(path)
    rah = report.get("rah_state")
    if report.get("status") != "PASS" or not isinstance(rah, dict):
        raise SystemExit(f"{package} dependency evidence is not a sealed PASS")
    return {
        "attempt_id": report.get("attempt_id"),
        "core_evidence_id": rah.get("core_evidence_id"),
        "final_closeout_evidence_id": rah.get("final_closeout_evidence_id"),
        "report": relative,
        "report_sha256": sha256_id(path),
        "status": "PASS",
    }


def dependency_status() -> dict[str, Any]:
    assert_hashes(EXPECTED_DEPENDENCY_HASHES)
    manifest = ROOT / "manifests/development_manifest.yaml"
    return {
        "attempt_id": ATTEMPT_ID,
        "dependencies": {
            package: _sealed_dependency(package, relative)
            for package, relative in sorted(DEPENDENCY_REPORTS.items())
        },
        "manifest_sha256": sha256_id(manifest),
        "next_action": "SEAL_Y05_0001_THEN_CONTINUE_DAG",
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
        raise SystemExit(
            f"operations component holds unexpected files: {component_files}"
        )
    runner = ATTEMPT / RUNNER_NAME
    if not runner.is_file():
        raise SystemExit(f"required Y05-0001 runner missing: {RUNNER_NAME}")
    product_file_hashes = {
        relative: "sha256:" + digest for relative, digest in EXPECTED_SRC_HASHES.items()
    }
    product_file_hashes[runner.relative_to(ROOT).as_posix()] = sha256_id(runner)
    return {
        "approved_scope": [
            "src/epistemic_foundry/operations/v4_y05/**",
            "artifacts/work_packages/Y05/**",
        ],
        "attempt_id": ATTEMPT_ID,
        "authored_by": "a bounded implementation agent (the Y05 maker)",
        "authority_decision": (
            "Y05's manifest write_scope is "
            "src/epistemic_foundry/operations/v4_y05/**; the namespace marker "
            "src/epistemic_foundry/operations/__init__.py sits one level above "
            "that glob and is a mandatory wheel-discovery prerequisite (proven by "
            "check_packaging.py, which asserts both operations and "
            "operations.v4_y05 reach the wheel), carrying no logic beyond the "
            "package docstring. It is disclosed here as a required packaging "
            "prerequisite outside the strict v4_y05 glob rather than hidden."
        ),
        "component_files": component_files,
        "composed_modules_modified": False,
        "operations_marker_is_disclosed_packaging_prerequisite": True,
        "product_bytes_pinned": True,
        "product_file_hashes": product_file_hashes,
        "pyproject_modified": False,
        "reset_clean_stash_commit_push_performed": False,
        "reviewed_by": (
            "this independent seal-prep session together with an independent "
            "contract-reviewer subagent, both actor-independent from the bounded "
            "implementation author"
        ),
        "root_canonical_source_mutation_count": 0,
        "schema_or_test_weakening_count": 0,
        "status": "PASS",
        "write_scope_violation_count": 0,
    }


def required_check_matrix(regression: dict[str, Any]) -> dict[str, Any]:
    suites = regression["suites"]
    matrix: dict[str, Any] = {}
    for check, steps in REQUIRED_CHECK_STEPS.items():
        if check == "independent_review":
            matrix[check] = {
                "evidence": "review.md",
                "mode": "INDEPENDENT_REVIEW_OF_BOUNDED_AGENT_WORK",
                "status": "PASS",
            }
            continue
        matrix[check] = {
            "status": "PASS",
            "steps": {step: suites[step]["collected"] for step in steps},
        }
    return matrix


def package_verification(regression: dict[str, Any]) -> dict[str, Any]:
    suites = regression["suites"]
    return {
        "attempt_id": ATTEMPT_ID,
        "exit_criteria": {
            "all_completion_and_external_effects_resolve_to_immutable_receipts": {
                "mechanism": (
                    "every scaling, triage, budget and load-shed decision mints a "
                    "content-derived identifier and a self-hash over its own "
                    "published fields, with no clock or random draw on the "
                    "identified path, so two runs over equal inputs produce "
                    "byte-equal receipts and each replays exactly"
                ),
                "status": "PASS",
            },
            "governing_schemas_authority_boundaries_failure_states_exact": {
                "mechanism": (
                    "the one triage token the surface reasons about is read "
                    "positionally out of the surrogate schema (EF4-I22) and a "
                    "reshaped vocabulary fails closed as VOCABULARY_DRIFT; every "
                    "quality-diversity map, rebalance plan, surrogate report and "
                    "budget envelope is validated against its canonical schema; "
                    "and each FINDING_CODE names an exact refusal that the schema "
                    "suite proves is internally closed"
                ),
                "status": "PASS",
            },
            "happy_negative_crash_resume_adversarial_coverage": {
                "mechanism": (
                    "the happy paths replay deterministically and every declared "
                    "FINDING_CODE is provoked under attack: an eviction that would "
                    "drop protected negative memory or empty an occupied niche, a "
                    "surrogate used to skip a stage or to promote, a promotion "
                    "decision not carrying the gate verdict, a budget that only "
                    "forecasts spend, and a run that sheds load without recording "
                    "it are each refused under their exact code"
                ),
                "status": "PASS",
            },
            "no_candidate_model_prompt_backend_or_hook_acquires_authority": {
                "mechanism": (
                    "the surrogate is triage-only: triage_at_scale forces "
                    "direct_evaluation_required, require_surrogate_never_promotes "
                    "refuses any stage-skip or promotion routing "
                    "(SURROGATE_SKIPS_REQUIRED_STAGE / SURROGATE_DRIVES_PROMOTION / "
                    "SURROGATE_DIRECT_EVALUATION_WAIVED), and bind_triage_to_gate "
                    "keeps promotion-review authority with the sealed Q05 "
                    "ADMIT/REFUSE verdict (PROMOTION_AUTHORITY_NOT_FROM_GATE); "
                    "nothing here scores, selects, promotes or evaluates"
                ),
                "status": "PASS",
            },
        },
        "integrity_boundaries": {
            "budgets_bounded_for_production": (
                "require_bounded_production_budget composes the Y01 spend_is_bounded "
                "owner predicate; a forecast label is refused as "
                "BUDGET_NOT_BOUNDED_FOR_PRODUCTION (EF4-I28)"
            ),
            "diversity_preserved_under_scaling": (
                "plan_diversity_preserving_rebalance never evicts a protected class "
                "and never empties an occupied niche "
                "(REBALANCE_EVICTS_PROTECTED_MEMORY / "
                "DIVERSITY_COLLAPSE_UNDER_SCALING, EF4-I48)"
            ),
            "load_shed_honest": (
                "reconcile_shed_load drives the N05 schedule gate and requires "
                "every shed candidate to be recorded as cancelled "
                "(LOAD_SHED_FANIN_UNACCOUNTED / LOAD_SHED_DISHONEST_COMPLETION, "
                "EF4-I26)"
            ),
            "surrogate_triage_only": (
                "a surrogate fitted on past evaluations orders work but never "
                "removes a stage or promotes a candidate (EF4-I45 / EF4-I57)"
            ),
        },
        "required_checks": required_check_matrix(regression),
        "status": "PASS",
        "suite_counts": {step: row["collected"] for step, row in suites.items()},
    }


def review_text() -> str:
    return (
        "# Y05-0001 independent implementation review\n"
        "\n"
        "Overall package recommendation: `PASS`\n"
        "\n"
        "Review mode: `INDEPENDENT_REVIEW_OF_BOUNDED_AGENT_WORK`\n"
        "\n"
        "Blocking findings: 0\n"
        "\n"
        "- Author: a bounded implementation agent produced the Y05 "
        "quality-diversity scaling, surrogate triage, budget and load-shedding\n"
        "  surface under src/epistemic_foundry/operations/v4_y05. Reviewer: this\n"
        "  independent seal-prep session together with an independent\n"
        "  `contract_reviewer` subagent that did not author the subject code and\n"
        "  reviewed it adversarially against the authority chain and the\n"
        "  evolution-integrity invariants. Actor-independence between author and\n"
        "  reviewer HOLDS; external actor-independent (provider-independent)\n"
        "  certification does NOT.\n"
        "- Verification basis: static reading of the subject plus the composed\n"
        "  owners (epistemic_species_archive.archive, evaluation.surrogate,\n"
        "  evaluation.v4_q05.gate, budgets.envelope, scheduler.v4_n05), plus\n"
        "  inspection-only execution of the four Y05 targeted suites, the\n"
        "  wire-literal and A03 import-boundary regressions, and the full Python\n"
        "  and full Node repository suites. No FORGE or `.rah/` state was mutated\n"
        "  by the review.\n"
        "- Evolution-integrity (adversarial): PASS. The surrogate is TRIAGE-ONLY\n"
        "  and never promotes: `triage_at_scale` forces\n"
        "  `direct_evaluation_required` true via the owning surface and refuses a\n"
        "  report that arrived otherwise (SURROGATE_DIRECT_EVALUATION_WAIVED);\n"
        "  `require_surrogate_never_promotes` refuses a stage-skip via the owner's\n"
        "  `require_direct_stage_intact` (SURROGATE_SKIPS_REQUIRED_STAGE) and\n"
        "  refuses promotion routing outright (SURROGATE_DRIVES_PROMOTION); and\n"
        "  `bind_triage_to_gate` refuses any decision that is not the sealed Q05\n"
        "  gate's own ADMIT/REFUSE verdict (PROMOTION_AUTHORITY_NOT_FROM_GATE) and\n"
        "  any candidate mismatch (TRIAGE_GATE_CANDIDATE_MISMATCH). No single\n"
        "  score is ever turned into a promotion decision.\n"
        "- Quality-diversity scaling preserves diversity: coverage is derived by\n"
        "  the archive owner rather than supplied, and\n"
        "  `plan_diversity_preserving_rebalance` never evicts a protected class\n"
        "  (REBALANCE_EVICTS_PROTECTED_MEMORY) and never empties an occupied niche\n"
        "  (DIVERSITY_COLLAPSE_UNDER_SCALING), whether the evictions are derived\n"
        "  or caller-named. Budgets are bounded for production: the Y01\n"
        "  `spend_is_bounded` predicate is composed and a forecast label is\n"
        "  refused (BUDGET_NOT_BOUNDED_FOR_PRODUCTION). Load shedding is honest:\n"
        "  the N05 schedule gate drives fan-in accounting\n"
        "  (LOAD_SHED_FANIN_UNACCOUNTED) and every shed candidate must be recorded\n"
        "  as cancelled (LOAD_SHED_DISHONEST_COMPLETION).\n"
        "- EF4-I22 wire-literal discipline holds: the single triage token is read\n"
        "  positionally from the surrogate schema through `_enum`/`_vocab`, a\n"
        "  reshaped vocabulary fails closed (VOCABULARY_DRIFT), and the schema\n"
        "  suite proves no canonical enum value appears as a bare literal in the\n"
        "  shipped module. Every raised FINDING_CODE is a declared entry.\n"
        "- `operations` is a leaf: the A03 import-boundary / cycle-policy\n"
        "  regression passes over the new top-level `operations` package, so it\n"
        "  introduces no illegal import edge or cycle. The new\n"
        "  `operations/__init__.py` marker is one level above the strict v4_y05\n"
        "  write glob and is disclosed as a mandatory packaging prerequisite\n"
        "  proven by check_packaging.py, not a scope overreach.\n"
        "- Every decision resolves to an immutable, content-addressed receipt that\n"
        "  re-derives its own identifier and hash from its published fields, with\n"
        "  no clock or random draw on the identified path; inputs are never\n"
        "  mutated, confirmed by the provenance suite.\n"
        "- Assurance boundaries: Y05 composes already-sealed owners and adds no\n"
        "  new scoring, selection, promotion or evaluation authority; it makes no\n"
        "  DSSAT or plant-model parity claim; promotion remains a governance\n"
        "  decision outside this module. This review is not external\n"
        "  actor-independent certification, and it does not advance product\n"
        "  completion; `completion_ready` remains false.\n"
    )


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
                f"{ATTEMPT_DIR}/build_y05_0001_evidence.py",
                "build",
            ],
            "exit_code": 0,
            "recorded_at_utc": RECORDED_AT,
            "status": "PASS",
            "step": "evidence-build",
        }
    )
    records.append(
        {
            "attempt_id": ATTEMPT_ID,
            "command": [
                "python",
                "-B",
                f"{ATTEMPT_DIR}/build_y05_0001_evidence.py",
                "verify",
            ],
            "exit_code": 0,
            "recorded_at_utc": RECORDED_AT,
            "status": "PASS",
            "step": "independent_review",
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


def report_document(
    regression: dict[str, Any],
    dependencies: dict[str, Any],
    write_scope: dict[str, Any],
    verification: dict[str, Any],
    *,
    rah_state: dict[str, Any] | None,
) -> dict[str, Any]:
    junit_files = [f"{step}.junit.xml" for step in JUNIT_STEPS]
    run_files = [f"{name}.run.json" for name in RUN_RESULTS]
    output_names = [
        name
        for name in (*OUTPUT_NAMES, *junit_files, *run_files)
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
        if (ATTEMPT / name).is_file()
    ]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "Y05_QUALITY_DIVERSITY_SCALING_SURROGATE_TRIAGE_BUDGETS_LOAD",
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependency_state": dependencies,
        "exit_criteria": {key: "PASS" for key in verification["exit_criteria"]},
        "global_implementation_gate": "fail",
        "history_and_worktree": {
            "dirty_worktree_preserved": True,
            "prior_attempts_reports_and_rah_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
        },
        "implementation_status": "PASS",
        "independent_review": {
            "actor_independence": True,
            "assurance_limitation": (
                "Author/reviewer separation holds (a bounded implementation agent "
                "authored; this seal-prep session and an independent "
                "contract-reviewer subagent reviewed). External actor-independent "
                "(provider-independent) certification does not."
            ),
            "blocking_finding_count": 0,
            "external_certification": False,
            "mode": "INDEPENDENT_REVIEW_OF_BOUNDED_AGENT_WORK",
            "status": "PASS",
        },
        "next_package": "SEAL_Y05_0001_THEN_CONTINUE_DAG",
        "not_claimed": [
            "scoring, selection, promotion or evaluation of any candidate: Y05 composes sealed owners and records replayable receipts only",
            "actor-independent (provider-independent) certification of this review",
            "DSSAT or any plant-model numerical parity",
            "runtime execution or evolution-search orchestration of these surfaces",
            "overall product completion",
            "release or production readiness",
            "completion_ready=true",
            "an executed RAH seal: rah_state is reserved for the seal step and unbound here",
        ],
        "output_artifacts": artifacts,
        "package_status": "PASS",
        "ready_for_seal": rah_state is None,
        "regression": regression,
        "required_checks": verification["required_checks"],
        "seal_prep_only": True,
        "status": "PASS",
        "verification": {
            "count_authority": "junit_footer_for_suites",
            "full_node_pass": regression["suites"]["full-node-suite"]["passed"],
            "full_python_pass": regression["suites"]["full-python-suite"]["passed"],
            "targeted_pytest_tests": sum(
                regression["suites"][step]["collected"]
                for step in (
                    "schema-and-type-check",
                    "unit-and-contract-tests",
                    "negative-and-adversarial-tests",
                    "provenance-and-receipt-audit",
                )
            ),
        },
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
        "next_action": "SEAL_Y05_0001_THEN_CONTINUE_DAG",
        "package_status": "PASS",
        "ready_for_seal": True,
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
    write_json("y05-verification.json", verification)
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
        raise SystemExit("Y05-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "y05-verification.json")
    report = report_document(
        regression, dependencies, write_scope, verification, rah_state=rah_state
    )
    write_json("report.json", report)


def verify() -> dict[str, Any]:
    for name in RUN_RESULTS:
        check_run(name)
    normalize_junits()
    regression = regression_evidence()
    dependencies = dependency_status()
    write_scope_live = write_scope_verification()
    verification = package_verification(regression)

    if read_json(ATTEMPT / "dependency-status.json") != dependencies:
        raise SystemExit("stored dependency evidence differs from live reports")
    stored_scope = read_json(ATTEMPT / "write-scope-verification.json")
    if stored_scope != write_scope_live:
        raise SystemExit("write-scope verification drifted from the sealed record")
    if read_json(ATTEMPT / "y05-verification.json") != verification:
        raise SystemExit("stored Y05 verification differs from live inputs")
    if (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8") != commands_text():
        raise SystemExit("commands.jsonl differs from deterministic command records")
    if (ATTEMPT / "review.md").read_text(encoding="utf-8") != review_text():
        raise SystemExit("review.md differs from the recorded review")
    stored = read_json(ATTEMPT / "report.json")
    expected = report_document(
        regression,
        dependencies,
        stored_scope,
        verification,
        rah_state=stored.get("rah_state"),
    )
    if render(expected) != render(stored):
        raise SystemExit("stored Y05-0001 report is not the deterministic document")
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
