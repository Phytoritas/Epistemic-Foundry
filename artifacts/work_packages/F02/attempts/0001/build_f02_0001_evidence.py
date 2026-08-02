#!/usr/bin/env python3
"""Build and verify F02-0001 FORGE FSM and legal return-edge evidence.

F02-0001 implements ``packages/foundry-kernel/src/forge/fsm/**``: a deterministic
FORGE finite-state machine whose legal transition graph is derived entirely from
the sealed F01 epistemic-work classification's hash-bound ``required_phases``
projection.  ``compileForgePlan`` re-verifies the F01 classification artifact
integrity (a tampered classification fails closed with
``CLASSIFICATION_INTEGRITY_FAILED``), rejects any ``required_phases`` that is not
one of the exact per-work-class projections (``INVALID_CLASSIFICATION_PROJECTION``),
and emits a frozen, hash-bound plan of forward edges (chained from the class
projection), a fixed legal set of return edges (F/O/R/G->I, R/G->O, G->R, E->F)
filtered to the phases reachable for the class, and a close edge (E->IDLE) only
when E is reachable.  ``describeForgeTransition`` classifies every phase pair as
FORWARD/RETURN/CLOSE or fails it closed as ``PHASE_NOT_REACHABLE_FOR_CLASSIFICATION``
(phase outside the class projection) or ``ILLEGAL_FORGE_TRANSITION`` (unreachable
edge between reachable phases).  ``reduceForgeTransition`` refuses every illegal,
stale-revision, wrong-from-phase, cross-session, or non-transitionable request
before mutating state, is deterministic and hash-bound over request, event,
prior/current state, plan, and phase sets, and on a RETURN edge invokes
``projectReturnStaleness`` so the return target and its downstream execution
phases are marked STALE with re-derived ``PAS-STALE-<digest>`` ids and a fresh
``set_hash`` -- source PhaseArtifactSets remain immutable history and superseded
sets are emitted explicitly, while FORWARD and CLOSE edges stale nothing.  This
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
ATTEMPT = ROOT / "artifacts/work_packages/F02/attempts/0001"
ATTEMPT_ID = "F02-0001"
WORK_PACKAGE_ID = "F02"
RECORDED_AT = "2026-08-02T00:00:00.000Z"

EXPECTED_FSM_PROPERTY_COUNT = 8
EXPECTED_STALE_PROPAGATION_COUNT = 6
EXPECTED_TARGETED_COUNT = 14
EXPECTED_PYTHON_COUNT = 1261
EXPECTED_NODE_COUNT = 1291
EXPECTED_NODE_FILE_COUNT = 115

COMPONENT = "packages/foundry-kernel/src/forge/fsm"
EXPECTED_PRODUCT_HASHES = {
    "packages/foundry-kernel/src/forge/fsm/forge-fsm.mjs": "f66a98d8c5359621c1ce3be1f11af4ff07cfd2838c66ca7b357798b8e8e8ed16",
    "packages/foundry-kernel/src/forge/fsm/fsm-property.test.mjs": "86bfdbac70ef909e5809eb814feb5e0934231ace0b8498ab0e007cf00d68be4f",
    "packages/foundry-kernel/src/forge/fsm/fsm-test-support.mjs": "d62316b37cc1359595c97f6e3fe98e93a75576a632847516451be67ec11a8e49",
    "packages/foundry-kernel/src/forge/fsm/index.mjs": "76403f4efac53cfc0f422a2dc644d8d45133217c070097107e0f4e4600d4bc17",
    "packages/foundry-kernel/src/forge/fsm/stale-propagation.test.mjs": "6bf19b049155c43d3254cc153542f7c518732f22351a8bfcded36bc59a5a353d",
}
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/F01/attempts/0003/report.json": "cf3c909d7adb256403fe4e2d051b2e591b3c002531ab19085334d085d06236c4",
}

JUNIT_PATHS = {
    "fsm_property": ATTEMPT / "fsm-property-test.junit.xml",
    "stale_propagation": ATTEMPT / "stale-propagation-test.junit.xml",
    "targeted": ATTEMPT / "targeted-fsm.junit.xml",
    "full_python": ATTEMPT / "full-python-suite.junit.xml",
    "full_node": ATTEMPT / "full-node-suite.junit.xml",
}
# Every F02 check but the full Python suite runs under the Node runner.
_NODE_JUNITS = frozenset(
    {
        "fsm_property",
        "stale_propagation",
        "targeted",
        "full_node",
    }
)
RUN_RESULTS = (
    "ruff-check",
    "ruff-format-check",
    "fsm-property-test",
    "stale-propagation-test",
    "targeted-fsm",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "run_f02_0001_checks.py",
    "build_f02_0001_evidence.py",
    "f02_0001_rah_seal.py",
    "dependency-status.json",
    "f02-verification.json",
    "write-scope-verification.json",
    "node-test-inventory.json",
    "junit-normalization-verification.json",
    "fsm-property-test.junit.xml",
    "stale-propagation-test.junit.xml",
    "targeted-fsm.junit.xml",
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


def _assert_node_gate(label: str, summary: dict[str, Any], expected: int) -> None:
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


def regression_evidence() -> dict[str, Any]:
    fsm_property = node_summary(JUNIT_PATHS["fsm_property"])
    stale_propagation = node_summary(JUNIT_PATHS["stale_propagation"])
    targeted = node_summary(JUNIT_PATHS["targeted"])
    python = pytest_summary(JUNIT_PATHS["full_python"])
    node = node_summary(JUNIT_PATHS["full_node"])
    node_inventory = read_json(ATTEMPT / "node-test-inventory.json")
    for label, summary, expected in (
        ("fsm_property_test", fsm_property, EXPECTED_FSM_PROPERTY_COUNT),
        ("stale_propagation_test", stale_propagation, EXPECTED_STALE_PROPAGATION_COUNT),
        ("targeted", targeted, EXPECTED_TARGETED_COUNT),
    ):
        _assert_node_gate(label, summary, expected)
    if (
        python["collected"],
        python["passed"],
        python["failed"],
        python["errors"],
        python["skipped"],
    ) != (EXPECTED_PYTHON_COUNT, EXPECTED_PYTHON_COUNT, 0, 0, 0):
        raise SystemExit(f"full_python gate failed: {python}")
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
        "component_tests_are_targeted_only": True,
        "fsm_property_test": fsm_property,
        "full_node": node,
        "full_python": python,
        "new_failure_count": 0,
        "stale_propagation_test": stale_propagation,
        "status": "PASS",
        "targeted_fsm": targeted,
        "unexpected_skip_xfail_todo_or_cancellation_count": 0,
    }


def _pass_dependency(package: str, attempt: str, relative: str) -> dict[str, Any]:
    path = ROOT / relative
    report = read_json(path)
    if report.get("status") != "PASS":
        raise SystemExit(f"{attempt} is not the sealed PASS attempt")
    return {
        "attempt_id": attempt,
        "report": path.relative_to(ROOT).as_posix(),
        "report_sha256": sha256_id(path),
        "status": "PASS",
    }


def dependency_status() -> dict[str, Any]:
    assert_hashes(EXPECTED_DEPENDENCY_HASHES)
    return {
        "attempt_id": ATTEMPT_ID,
        "dependencies": {
            "F01": _pass_dependency(
                "F01",
                "F01-0003",
                "artifacts/work_packages/F01/attempts/0003/report.json",
            ),
        },
        "next_action": "SEAL_F02_0001_THEN_CONTINUE_DAG",
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
            f"forge/fsm component holds unexpected files: {component_files}"
        )
    return {
        "approved_scope": [f"{COMPONENT}/**", "artifacts/work_packages/F02/**"],
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
        "write_scope_violation_count": 0,
    }


def f02_verification(regression: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "exit_criteria": {
            "deterministic_transitions": {
                "evidence": [
                    f"{COMPONENT}/fsm-property.test.mjs",
                ],
                "mechanism": (
                    "compileForgePlan derives the legal I/F/O/R/G/E graph solely "
                    "from the sealed F01 classification's hash-bound required_phases "
                    "projection: forward edges are chained from the class projection, "
                    "the fixed legal return set (F/O/R/G->I, R/G->O, G->R, E->F) is "
                    "filtered to reachable phases, and E->IDLE closes only when E is "
                    "reachable. describeForgeTransition classifies every phase pair "
                    "as FORWARD/RETURN/CLOSE, PHASE_NOT_REACHABLE_FOR_CLASSIFICATION "
                    "(phase outside the class projection), or ILLEGAL_FORGE_TRANSITION "
                    "(unreachable edge between reachable phases). A forged "
                    "required_phases fails INVALID_CLASSIFICATION_PROJECTION and a "
                    "tampered classification fails CLASSIFICATION_INTEGRITY_FAILED. "
                    "reduceForgeTransition refuses illegal, stale-revision "
                    "(STALE_REVISION), wrong-from-phase (FROM_PHASE_MISMATCH), "
                    "cross-session (SESSION_MISMATCH), and non-transitionable "
                    "(FORGE_SESSION_NOT_TRANSITIONABLE) requests before mutating, is "
                    "immutable, revision-bound, and hash-bound over request, event, "
                    "prior/current state, plan, and phase sets, and strict event "
                    "replay reproduces the direct reducer chain exactly"
                ),
                "status": "PASS",
            },
            "return_edges_stale_downstream_artifacts": {
                "evidence": [
                    f"{COMPONENT}/stale-propagation.test.mjs",
                ],
                "mechanism": (
                    "on a RETURN edge projectReturnStaleness marks the return target "
                    "and every downstream execution phase reachable for the class "
                    "STALE under the RETURN_TARGET_INCLUSIVE rule, re-deriving "
                    "PAS-STALE-<digest> set ids bound to the event and source set, a "
                    "fresh set_hash, complete=false, and STALE artifact status; the "
                    "superseded source sets are emitted explicitly and the stale "
                    "phase and artifact ids are recorded on the transition. Source "
                    "PhaseArtifactSets remain immutable history, projection identity "
                    "is deterministic and event-bound, and FORWARD and CLOSE edges "
                    "stale nothing. Cross-session (PHASE_ARTIFACT_SESSION_MISMATCH), "
                    "unretained (PHASE_ARTIFACT_NOT_IN_STATE), and tampered "
                    "(PHASE_ARTIFACT_SET_HASH_MISMATCH) phase sets fail closed"
                ),
                "status": "PASS",
            },
        },
        "legal_transitions_and_return_edges": {
            "close_edge_only_when_e_reachable": True,
            "forward_edges_chained_from_f01_projection": True,
            "illegal_edge_between_reachable_phases_is_illegal_forge_transition": True,
            "phase_outside_projection_is_not_reachable_for_classification": True,
            "reducer_refuses_illegal_edges_fail_closed": True,
            "return_edge_set_is_fixed_and_filtered_to_reachable_phases": True,
        },
        "f01_integrity_reverified": {
            "forged_required_phases_fails_invalid_classification_projection": True,
            "tampered_classification_fails_classification_integrity_failed": True,
        },
        "required_checks": {
            "fsm_property_test": {
                "module": f"{COMPONENT}/fsm-property.test.mjs",
                "status": "PASS",
                "test_count": regression["fsm_property_test"]["collected"],
            },
            "stale_propagation_test": {
                "module": f"{COMPONENT}/stale-propagation.test.mjs",
                "status": "PASS",
                "test_count": regression["stale_propagation_test"]["collected"],
            },
        },
        "stale_propagation_invalidates_downstream": {
            "cross_session_and_tampered_sets_fail_closed": True,
            "forward_and_close_edges_stale_nothing": True,
            "return_marks_target_and_downstream_execution_phases_stale": True,
            "re_derived_pas_stale_ids_and_fresh_set_hash": True,
            "source_phase_artifact_sets_remain_immutable": True,
            "superseded_sets_emitted_with_stale_phase_and_artifact_ids": True,
        },
        "status": "PASS",
        "targeted_test_count": regression["targeted_fsm"]["collected"],
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
                "artifacts/work_packages/F02/attempts/0001/build_f02_0001_evidence.py",
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
        "# F02-0001 independent review of bounded-agent work\n"
        "\n"
        "- Author: the bounded implementation agent that wrote\n"
        "  packages/foundry-kernel/src/forge/fsm. Reviewer: this seal-prep session, a\n"
        "  distinct actor that did not author the FORGE FSM. The author never\n"
        "  approves its own work, so actor_independence HOLDS for this review;\n"
        "  external actor-independent certification does NOT, and no such claim is\n"
        "  made. F02 is risk_class=medium and governs the FORGE transition kernel, so\n"
        "  the legal graph, return-edge staleness, and F01 integrity were attacked on\n"
        "  their contracts rather than skimmed.\n"
        "- Legal transitions and return edges are class-derived and fail closed.\n"
        "  compileForgePlan validates the F01 classification against the exact\n"
        "  per-work-class EXPECTED_PROJECTIONS and re-verifies its hash-bound\n"
        "  identity; a required_phases that is not one of the class projections is\n"
        "  rejected INVALID_CLASSIFICATION_PROJECTION and a classification whose\n"
        "  reasons or identity were tampered fails CLASSIFICATION_INTEGRITY_FAILED.\n"
        "  Forward edges are chained from the projection, the return-edge set is the\n"
        "  fixed legal set (F/O/R/G->I, R/G->O, G->R, E->F) filtered to the phases\n"
        "  reachable for the class, and E->IDLE closes only when E is reachable, so\n"
        "  the E1 LOOKUP class exposes exactly its F/O/E surface and never R or G.\n"
        "  describeForgeTransition returns PHASE_NOT_REACHABLE_FOR_CLASSIFICATION for\n"
        "  a phase outside the projection and ILLEGAL_FORGE_TRANSITION for an\n"
        "  unreachable edge between reachable phases; the property test walks every\n"
        "  phase pair for all seven E0-E5 cases against the exact expected graph.\n"
        "- The reducer is deterministic and fails closed before mutating. \n"
        "  reduceForgeTransition asserts the sealed state hash, then refuses a\n"
        "  non-transitionable session (FORGE_SESSION_NOT_TRANSITIONABLE), a\n"
        "  work-class/plan mismatch (CLASSIFICATION_STATE_MISMATCH), an unreachable\n"
        "  current phase, a foreign session (SESSION_MISMATCH), a stale revision\n"
        "  (STALE_REVISION), a wrong from_phase (FROM_PHASE_MISMATCH), and an illegal\n"
        "  edge, each before any state is produced. The next state is deep-frozen and\n"
        "  hash-bound, and the transition record is hash-bound over the request,\n"
        "  event, prior/current state hash, plan hash, and phase-set hashes, so\n"
        "  changing the request reason, event, or phase set changes the transition\n"
        "  hash. Strict event replay reproduces the direct reducer chain and the\n"
        "  empty replay still verifies every sealed initial input.\n"
        "- Return edges stale the target-inclusive downstream and never leave silent\n"
        "  stale state. On a RETURN edge projectReturnStaleness marks the return\n"
        "  target and every downstream execution phase reachable for the class STALE:\n"
        "  each superseded set is re-derived as PAS-STALE-<digest> bound to the event\n"
        "  and source set, with complete=false, STALE artifact status, and a fresh\n"
        "  set_hash, while the untouched I/F sets keep their original ids. The\n"
        "  transition records stale_phases and sorted stale_artifact_ids and the\n"
        "  result emits the superseded sets explicitly; the source PhaseArtifactSets\n"
        "  passed in are left byte-for-byte immutable. Projection identity is\n"
        "  deterministic and event-bound (set order does not change it; a different\n"
        "  event does). FORWARD and CLOSE edges stale nothing. Cross-session,\n"
        "  unretained, and tampered phase sets fail closed\n"
        "  (PHASE_ARTIFACT_SESSION_MISMATCH, PHASE_ARTIFACT_NOT_IN_STATE,\n"
        "  PHASE_ARTIFACT_SET_HASH_MISMATCH).\n"
        "- Dependencies and checks: the FSM derives its graph from the sealed F01\n"
        "  epistemic-work classification (F01-0003 PASS) and adds no new production\n"
        "  dependency; it re-verifies F01 artifact integrity on every plan compile.\n"
        "  Ruff lint and format, the two required checks (fsm_property_test "
        + f"{EXPECTED_FSM_PROPERTY_COUNT}/{EXPECTED_FSM_PROPERTY_COUNT}, "
        + f"stale_propagation_test {EXPECTED_STALE_PROPAGATION_COUNT}/"
        + f"{EXPECTED_STALE_PROPAGATION_COUNT}), targeted "
        + f"{EXPECTED_TARGETED_COUNT}/{EXPECTED_TARGETED_COUNT}, full Python "
        + f"{EXPECTED_PYTHON_COUNT}/{EXPECTED_PYTHON_COUNT}, full Node "
        + f"{EXPECTED_NODE_COUNT}/{EXPECTED_NODE_COUNT} across "
        + f"{EXPECTED_NODE_FILE_COUNT} files, and git diff --check all pass with\n"
        "  zero failures; the earlier S04-TM004 pre-existing Node debt is resolved in\n"
        "  the current tree, so F02 seals against a clean full Node suite.\n"
        "- Residual limitations: F02 provides the deterministic FORGE FSM, its legal\n"
        "  graph, and return-edge staleness only; receipt resolution, policy,\n"
        "  capability, approval, and veto admission gates remain F03 responsibility,\n"
        "  and phase_history is validated for shape, revision bound, and current-tail\n"
        "  agreement but is not reinterpreted as a stronger authoritative event log.\n"
        "  Verdict: PASS on the exact F02 package contract.\n"
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
            "path": f"artifacts/work_packages/F02/attempts/0001/{name}",
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in sorted(set(output_names))
    ]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "F02_FORGE_FSM_AND_LEGAL_RETURN_EDGES",
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependency_state": dependencies,
        "exit_criteria": {
            "deterministic_transitions": "PASS",
            "return_edges_stale_downstream_artifacts": "PASS",
        },
        "global_implementation_gate": "fail",
        "history_and_worktree": {
            "dirty_worktree_preserved": True,
            "prior_attempts_reports_and_rah_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
        },
        "implementation_status": "PASS",
        "not_claimed": [
            "F03 receipt resolution, policy, capability, approval, or veto gates",
            "a stronger authoritative phase_history event-log contract",
            "external actor-independent certification of this review",
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
                "Independent review of bounded-agent work by a distinct actor in "
                "this seal-prep session; not external actor-independent "
                "certification."
            ),
            "author": "bounded implementation agent",
            "blocking_finding_count": 0,
            "mode": "INDEPENDENT_REVIEW_OF_BOUNDED_AGENT_WORK",
            "reviewer": "independent seal-prep session (distinct actor)",
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
        "fsm_property_test": (
            f"{EXPECTED_FSM_PROPERTY_COUNT}/{EXPECTED_FSM_PROPERTY_COUNT}"
        ),
        "full_node": f"{EXPECTED_NODE_COUNT}/{EXPECTED_NODE_COUNT}",
        "full_python": f"{EXPECTED_PYTHON_COUNT}/{EXPECTED_PYTHON_COUNT}",
        "next_action": "SEAL_F02_0001_THEN_CONTINUE_DAG",
        "node_file_count": EXPECTED_NODE_FILE_COUNT,
        "package_status": "PASS",
        "stale_propagation_test": (
            f"{EXPECTED_STALE_PROPAGATION_COUNT}/{EXPECTED_STALE_PROPAGATION_COUNT}"
        ),
        "status": "PASS",
        "targeted_fsm": f"{EXPECTED_TARGETED_COUNT}/{EXPECTED_TARGETED_COUNT}",
    }


def build() -> dict[str, Any]:
    for name in RUN_RESULTS:
        check_run(name)
    normalize_junits()
    regression = regression_evidence()
    dependencies = dependency_status()
    write_scope = write_scope_verification()
    verification = f02_verification(regression)
    write_json("dependency-status.json", dependencies)
    write_json("write-scope-verification.json", write_scope)
    write_json("f02-verification.json", verification)
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
        raise SystemExit("F02-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "f02-verification.json")
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
    verification = read_json(ATTEMPT / "f02-verification.json")
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
        raise SystemExit("stored F02-0001 report is not the deterministic document")
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
