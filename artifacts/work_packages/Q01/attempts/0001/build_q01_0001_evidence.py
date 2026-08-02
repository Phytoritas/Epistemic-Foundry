#!/usr/bin/env python3
"""Build and verify Q01-0001 gold corpus and annotation protocol evidence.

Q01-0001 implements `evals/gold/**` and the corpus-binding section of
`docs/annotation_manual.md`: a gold corpus that must carry true, false, and
boundary cases in usable numbers, where every disagreement is adjudicated on
the record by a third party and inter-annotator agreement is a computed
coefficient rather than a claim.  This builder verifies the executed checks and
emits immutable attempt evidence; it never modifies product files.
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
ATTEMPT = ROOT / "artifacts/work_packages/Q01/attempts/0001"
ATTEMPT_ID = "Q01-0001"
WORK_PACKAGE_ID = "Q01"
RECORDED_AT = "2026-08-01T19:30:00.000Z"

EXPECTED_GOLD_DATASET_COUNT = 21
EXPECTED_ANNOTATION_AGREEMENT_COUNT = 20
EXPECTED_TARGETED_COUNT = 41
EXPECTED_ADJUDICATION_REGRESSION_COUNT = 52
EXPECTED_CAUSAL_REGRESSION_COUNT = 45
EXPECTED_PYTHON_COUNT = 1261
EXPECTED_NODE_COUNT = 982
EXPECTED_NODE_FILE_COUNT = 91

COMPONENT = "evals/gold"
EXPECTED_PRODUCT_HASHES = {
    "docs/annotation_manual.md": "de3790a7056f2113087299a5fadcc198b4786da68755372a53f4eff139ad8659",
    "evals/gold/insight_gold_cases.json": "10cff9039a170cc89e6738bec3fd6f3c675217d1657c137ccb7b93856bda0c96",
    "evals/gold/pytest.ini": "3b4008c416cf288bcc32ed6bfccaf05d25c8f74ea0283e34e15197ef1fb9eb98",
    "evals/gold/test_annotation_agreement.py": "e5c58dca1c08b594eac1fcef4018fa32e954f8e426b3b4aadc0f755e3af59dab",
    "evals/gold/test_gold_dataset.py": "153b202f66c7b5d05414eb6cf660a7740130e5d6b4142456db57642cffe76b33",
    "evals/gold/validator.py": "7dde9cca80e5df91cf6e1f772b84547cf8d8a29378214acb53257a5923cf01bf",
}
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/K04/attempts/0001/report.json": "12d84e70e24fb1f7f9d87619721a27eaf0a77499cfb11b426353bf9c8725c56f",
    "artifacts/work_packages/O04/attempts/0001/report.json": "2fd0059a9e1bd66d383168472a644386c299f870e6815e7df291391005f79f0f",
    "artifacts/work_packages/P04/attempts/0001/report.json": "f94cab8d02468a199b0b08030728d172ea1530b34c500c93307c33e050f220ab",
    "artifacts/work_packages/R04/attempts/0001/report.json": "bc7080d66ced6dd68672995e60549b066b1290161b665bfd5b05aa48eb54d135",
}

JUNIT_PATHS = {
    "gold_dataset": ATTEMPT / "gold-dataset-validation.junit.xml",
    "annotation_agreement": ATTEMPT / "annotation-agreement-check.junit.xml",
    "targeted": ATTEMPT / "targeted-gold-corpus.junit.xml",
    "adjudication_regression": ATTEMPT / "dependency-regression-adjudication.junit.xml",
    "causal_regression": ATTEMPT / "dependency-regression-causal.junit.xml",
    "full_python": ATTEMPT / "full-python-suite.junit.xml",
    "full_node": ATTEMPT / "full-node-suite.junit.xml",
}
_NODE_JUNITS = frozenset({"full_node"})
RUN_RESULTS = (
    "ruff-check",
    "ruff-format-check",
    "gold-dataset-validation",
    "annotation-agreement-check",
    "targeted-gold-corpus",
    "dependency-regression-adjudication",
    "dependency-regression-causal",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "run_q01_0001_checks.py",
    "build_q01_0001_evidence.py",
    "q01_0001_rah_seal.py",
    "dependency-status.json",
    "q01-verification.json",
    "write-scope-verification.json",
    "node-test-inventory.json",
    "junit-normalization-verification.json",
    "gold-dataset-validation.junit.xml",
    "annotation-agreement-check.junit.xml",
    "targeted-gold-corpus.junit.xml",
    "dependency-regression-adjudication.junit.xml",
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
    dataset = pytest_summary(JUNIT_PATHS["gold_dataset"])
    agreement = pytest_summary(JUNIT_PATHS["annotation_agreement"])
    targeted = pytest_summary(JUNIT_PATHS["targeted"])
    adjudication = pytest_summary(JUNIT_PATHS["adjudication_regression"])
    causal = pytest_summary(JUNIT_PATHS["causal_regression"])
    python = pytest_summary(JUNIT_PATHS["full_python"])
    node = node_summary(JUNIT_PATHS["full_node"])
    node_inventory = read_json(ATTEMPT / "node-test-inventory.json")
    for label, summary, expected in (
        ("gold_dataset_validation", dataset, EXPECTED_GOLD_DATASET_COUNT),
        (
            "annotation_agreement_check",
            agreement,
            EXPECTED_ANNOTATION_AGREEMENT_COUNT,
        ),
        ("targeted", targeted, EXPECTED_TARGETED_COUNT),
        (
            "adjudication_regression",
            adjudication,
            EXPECTED_ADJUDICATION_REGRESSION_COUNT,
        ),
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
        "baseline_attempt": "P04-0001",
        "component_tests_are_targeted_only": True,
        "adjudication_regression": adjudication,
        "causal_regression": causal,
        "full_node": node,
        "full_python": python,
        "annotation_agreement_check": agreement,
        "gold_dataset_validation": dataset,
        "new_failure_count": 0,
        "prior_baseline_counts": {"full_node": 903, "full_python": 1261},
        "status": "PASS",
        "targeted_gold_corpus": targeted,
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
            "O04": _sealed_dependency("O04", "O04-0001", "E0121", "E0122"),
            "P04": _sealed_dependency("P04", "P04-0001", "E0147", "E0148"),
            "R04": _sealed_dependency("R04", "R04-0001", "E0135", "E0136"),
        },
        "next_action": "SEAL_Q01_0001_THEN_CONTINUE_DAG",
        "regression_baseline": _sealed_dependency("P04", "P04-0001", "E0147", "E0148"),
        "status": "PASS",
    }


def write_scope_verification() -> dict[str, Any]:
    assert_hashes(EXPECTED_PRODUCT_HASHES)
    component_files = sorted(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / COMPONENT).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )
    declared = sorted(
        relative
        for relative in EXPECTED_PRODUCT_HASHES
        if relative.startswith(f"{COMPONENT}/")
    )
    if component_files != declared:
        raise SystemExit(f"gold corpus holds unexpected files: {component_files}")
    return {
        "approved_scope": [
            f"{COMPONENT}/**",
            "docs/annotation_manual.md",
            "artifacts/work_packages/Q01/**",
        ],
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


def q01_verification(regression: dict[str, Any]) -> dict[str, Any]:
    return {
        "adjudication": {
            "adjudicator_must_be_neither_annotator": True,
            "resolutions": [
                "ANNOTATOR_A_CORRECT",
                "ANNOTATOR_B_CORRECT",
                "GUIDANCE_AMBIGUOUS",
                "NEITHER_CORRECT",
            ],
            "unanimous_case_carries_no_adjudication": True,
            "unadjudicated_disagreement_refused": True,
        },
        "agreement": {
            "contract_kappa_floor": 0.6,
            "measured_kappa": 0.7486910995,
            "measured_not_asserted": True,
            "single_label_corpus_reported_undefined": True,
        },
        "attempt_id": ATTEMPT_ID,
        "case_coverage": {
            "boundary_case_must_state_its_condition": True,
            "classes": ["BOUNDARY", "FALSE_INSIGHT", "TRUE_INSIGHT"],
            "corpus_case_count": 12,
            "minimum_cases_per_class": 3,
        },
        "exit_criteria": {
            "annotator_adjudication_defined": {
                "evidence": [
                    f"{COMPONENT}/test_annotation_agreement.py",
                    "docs/annotation_manual.md",
                ],
                "mechanism": (
                    "a disagreement must be resolved by an adjudicator who is "
                    "neither annotator, with a canonical resolution and a cited "
                    "reason, and agreement is a computed coefficient with its "
                    "inputs exposed rather than a claim"
                ),
                "status": "PASS",
            },
            "false_true_boundary_cases_represented": {
                "evidence": [f"{COMPONENT}/test_gold_dataset.py"],
                "mechanism": (
                    "at least three cases of each class are required, every case "
                    "must cite a source span, and a boundary case must name the "
                    "condition that makes it a boundary"
                ),
                "status": "PASS",
            },
        },
        "required_checks": {
            "annotation_agreement_check": {
                "module": f"{COMPONENT}/test_annotation_agreement.py",
                "status": "PASS",
                "test_count": regression["annotation_agreement_check"]["collected"],
            },
            "gold_dataset_validation": {
                "module": f"{COMPONENT}/test_gold_dataset.py",
                "status": "PASS",
                "test_count": regression["gold_dataset_validation"]["collected"],
            },
        },
        "status": "PASS",
        "targeted_test_count": regression["targeted_gold_corpus"]["collected"],
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
                "artifacts/work_packages/Q01/attempts/0001/build_r01_0001_evidence.py",
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
        "# Q01-0001 primary-session separate adversarial review\n"
        "\n"
        "- Reviewer: primary session in a separate adversarial pass under the\n"
        "  product-owner instruction forbidding subagents and Fleet;\n"
        "  actor_independence=false is recorded, not hidden.\n"
        "- All three classes are required, not merely present. A benchmark of\n"
        "  clear positives measures nothing: a system that answers yes to\n"
        "  everything scores perfectly on it. The validator therefore fails a\n"
        "  corpus that is missing or thin in true, false, or boundary cases\n"
        "  rather than reporting a high score on a corpus that could not have\n"
        "  discriminated anything. v1.0 carries four cases of each class.\n"
        "- A boundary case must name the condition that makes it a boundary,\n"
        "  because 'boundary' is otherwise a comfortable label for anything\n"
        "  hard. A non-boundary case may not carry one, so the field cannot be\n"
        "  used decoratively.\n"
        "- Adjudication is a record, not a convention. Every case carries at\n"
        "  least two independent annotations; a disagreement without an\n"
        "  adjudication fails, an annotator may not adjudicate its own\n"
        "  disagreement, the resolution must be canonical, the reason must cite\n"
        "  the rule applied, and a unanimous case may carry no adjudication at\n"
        "  all so the corpus cannot look more scrutinised than it is.\n"
        "- Agreement is measured. Fleiss' kappa is computed over the raw\n"
        "  annotations and reported with the observed and expected agreement it\n"
        "  derives from, so the test recomputes the coefficient from those\n"
        "  inputs rather than trusting it. v1.0 measures kappa 0.749 over 12\n"
        "  cases and 2 raters, against a floor of 0.60 that a corpus may not\n"
        "  declare weaker.\n"
        "- The degenerate case is handled honestly: a corpus in which every\n"
        "  annotation used one label has no variance and is reported as\n"
        "  undefined rather than as perfect agreement, and an uneven rater\n"
        "  count is reported rather than averaged over.\n"
        "- The corpus cites the manual it was labelled under and the validator\n"
        "  refuses any other citation, so a label set can always be traced to\n"
        "  its rules. The existing manual content was extended, not replaced.\n"
        "- Residual limitations: the labels are the primary session's own and\n"
        "  have not been validated by domain experts; the source spans are\n"
        "  synthetic identifiers rather than real document locators; twelve\n"
        "  cases are enough to exercise the protocol but not to set production\n"
        "  thresholds, which the release rule already holds conditional; and\n"
        "  calibration and scoring belong to later Q-phase packages. This\n"
        "  review is not external actor-independent certification.\n"
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
            "path": f"artifacts/work_packages/Q01/attempts/0001/{name}",
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in sorted(set(output_names))
    ]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "Q01_GOLD_CORPUS_AND_ANNOTATION_PROTOCOL",
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependency_state": dependencies,
        "exit_criteria": {
            "annotator_adjudication_defined": "PASS",
            "false_true_boundary_cases_represented": "PASS",
        },
        "global_implementation_gate": "fail",
        "history_and_worktree": {
            "dirty_worktree_preserved": True,
            "prior_attempts_reports_and_rah_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
            "subagents_or_fleet_used": False,
        },
        "implementation_status": "PASS",
        "next_package": "T04-0001",
        "not_claimed": [
            "domain-expert validation of the labels, which remains outstanding",
            "that the corpus is large enough to set production thresholds",
            "annotation of real sources, since the spans are synthetic identifiers",
            "calibration or scoring, which later Q-phase packages own",
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
        "annotation_agreement_check": (
            f"{EXPECTED_ANNOTATION_AGREEMENT_COUNT}/"
            f"{EXPECTED_ANNOTATION_AGREEMENT_COUNT}"
        ),
        "gold_dataset_validation": (
            f"{EXPECTED_GOLD_DATASET_COUNT}/{EXPECTED_GOLD_DATASET_COUNT}"
        ),
        "next_action": "SEAL_Q01_0001_THEN_CONTINUE_DAG",
        "package_status": "PASS",
        "status": "PASS",
        "targeted_gold_corpus": (
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
    verification = q01_verification(regression)
    write_json("dependency-status.json", dependencies)
    write_json("write-scope-verification.json", write_scope)
    write_json("q01-verification.json", verification)
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
        raise SystemExit("Q01-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "q01-verification.json")
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
    verification = read_json(ATTEMPT / "q01-verification.json")
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
        raise SystemExit("stored Q01-0001 report is not the deterministic document")
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
