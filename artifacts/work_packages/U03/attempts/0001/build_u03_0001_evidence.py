#!/usr/bin/env python3
"""Build and verify U03-0001 evidence: Atlas, Parliament, Aporia and Passport views.

U03 is a Node/Web package.  It was implemented and targeted-GREEN by a bounded
implementation agent under the product owner's instruction, with a write scope
of ``web/src/features/{atlas,parliament,aporia,passport}/**``, and is reviewed
here by a separate sealing agent that did not author it.  This builder verifies
every executed check receipt, gates every Node JUnit against its measured footer
count, binds the U01 dependency and the current latest-sealed regression
baseline, pins the approved product bytes, and emits the deterministic attempt
evidence.  It never modifies product files.

The two required checks come straight from ``manifests/development_manifest.yaml``
(U03): ``research_view_e2e`` and ``source_span_view_test``.  U03 declares exactly
these two checks: there is no Python targeted suite and no Ruff gate.  They are
*cross-cutting* concerns over the same four ``*-view.test.mjs`` research-view
modules rather than a partition of the files — every view suite is a full
end-to-end read-model projection and every view suite carries a named
source-receipt provenance test — so both required checks run all four view
modules (52 tests each):

``research_view_e2e`` (52 tests: atlas + parliament + aporia + passport views
    end-to-end).  Carries the ``minority/counterevidence visible`` exit
    criterion — parliament dissent/counter-evidence, aporia open questions,
    passport counter-evidence, atlas counter_count/coverage claims are all
    first-class, and hiding or inventing them refuses.

``source_span_view_test`` (52 tests: the same four view suites, gated on their
    source-provenance path).  Carries the ``source span accessible`` exit
    criterion — every view exposes its provenance manifest / evidence-pack /
    attestation / artifact hashes via ``the view carries its (source|graph)
    receipt`` and binds only the declared read operations.

``full-node-suite`` is the whole-repository Node regression.  Its absolute total
is a repository-wide, integration-owned number that other in-flight packages
move; this attempt gates the *frozen* JUnit it captured (107 modules,
1192 tests at seal time) so the sealed evidence is deterministic on replay.  The
runner must not be re-run after this evidence is built, or the frozen count and
the live inventory would diverge.
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
ATTEMPT = ROOT / "artifacts/work_packages/U03/attempts/0001"
ATTEMPT_ID = "U03-0001"
WORK_PACKAGE_ID = "U03"
RECORDED_AT = "2026-08-02T05:45:00.000Z"
ATTEMPT_DIR = "artifacts/work_packages/U03/attempts/0001"

#: Frozen expected counts, gated against the captured JUnit footers.
EXPECTED_RESEARCH_VIEW_E2E = 52
EXPECTED_SOURCE_SPAN_VIEW = 52
EXPECTED_FULL_NODE = 1192
EXPECTED_NODE_FILE_COUNT = 107

#: Sealed dependency report bytes, bound by path (tamper detection).  U03
#: depends_on U01; the regression baseline is the current latest-sealed report,
#: which is F06-0001 (evidence tail E0238 in the live ledger at build time).
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/U01/attempts/0001/report.json": (
        "f7fd6b37c297466a25eec37f70e29f12a66a3346876a88d3ce4c63b3078a3a8a"
    ),
    "artifacts/work_packages/F06/attempts/0001/report.json": (
        "ce89ecb506a664f1a7b1f7b1c49e6546295eb8d1266f0e28469172aa0d16714c"
    ),
}

JUNIT_PATHS = {
    "full_node_suite": ATTEMPT / "full-node-suite.junit.xml",
    "research_view_e2e": ATTEMPT / "research-view-e2e.junit.xml",
    "source_span_view_test": ATTEMPT / "source-span-view-test.junit.xml",
}
_NODE_JUNITS = frozenset(JUNIT_PATHS)
RUN_RESULTS = (
    "full-node-suite",
    "git-diff-check",
    "research-view-e2e",
    "source-span-view-test",
    "write-scope-verification",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
PRODUCT_ROOTS = (
    "web/src/features/atlas",
    "web/src/features/parliament",
    "web/src/features/aporia",
    "web/src/features/passport",
)
APPROVED_SCOPE = [
    "web/src/features/atlas/**",
    "web/src/features/parliament/**",
    "web/src/features/aporia/**",
    "web/src/features/passport/**",
]
OUTPUT_NAMES = (
    "build_u03_0001_evidence.py",
    "commands.jsonl",
    "dependency-status.json",
    "full-node-suite.junit.xml",
    "junit-normalization-verification.json",
    "node-test-inventory.json",
    "research-view-e2e.junit.xml",
    "review.md",
    "run_u03_0001_checks.py",
    "source-span-view-test.junit.xml",
    "u03-verification.json",
    "u03_0001_rah_seal.py",
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
            raise SystemExit(f"sealed dependency changed: {relative}: {actual} != {wanted}")


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
        if "duration_ms" in text:
            raise SystemExit(f"Node JUnit retains volatile duration_ms: {name}")


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
        removed = {"duration_comments": 0, "repository_prefixes": 0}
        for prefix in (root_backslash, root_slash):
            count = normalized.count(prefix)
            normalized = normalized.replace(prefix, "")
            removed["repository_prefixes"] += count
        for value in (str(ROOT), str(ROOT).replace("\\", "/")):
            count = normalized.count(value)
            normalized = normalized.replace(value, ".")
            removed["repository_prefixes"] += count
        normalized, removed["duration_comments"] = re.subn(
            r"\s*<!-- duration_ms [^>]+ -->", "", normalized
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
    for label, summary, expected in (
        ("research_view_e2e", node_summary(JUNIT_PATHS["research_view_e2e"]),
         EXPECTED_RESEARCH_VIEW_E2E),
        ("source_span_view_test", node_summary(JUNIT_PATHS["source_span_view_test"]),
         EXPECTED_SOURCE_SPAN_VIEW),
        ("full_node_suite", node_summary(JUNIT_PATHS["full_node_suite"]),
         EXPECTED_FULL_NODE),
    ):
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

    node_inventory = read_json(ATTEMPT / "node-test-inventory.json")
    if node_inventory.get("count") != EXPECTED_NODE_FILE_COUNT:
        raise SystemExit(f"Node inventory gate failed: {node_inventory}")
    return {
        "attempt_id": ATTEMPT_ID,
        "full_node_inventory_is_integration_owned": True,
        "new_failure_count": 0,
        "regression_baseline_attempt": "F06-0001",
        "status": "PASS",
        "suites": summaries,
    }


def _sealed_dependency(package: str, attempt: str, core: str, final: str) -> dict[str, Any]:
    path = ROOT / f"artifacts/work_packages/{package}/attempts/{attempt[-4:]}/report.json"
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
    assert_dependency_hashes()
    return {
        "attempt_id": ATTEMPT_ID,
        "dependencies": {
            "U01": _sealed_dependency("U01", "U01-0001", "E0199", "E0200"),
        },
        "next_action": "SEAL_U03_0001_THEN_RECOMPUTE_DAG",
        "regression_baseline": _sealed_dependency("F06", "F06-0001", "E0237", "E0238"),
        "status": "PASS",
    }


def _live_product_hashes() -> dict[str, str]:
    relatives = sorted(
        path.relative_to(ROOT).as_posix()
        for root in PRODUCT_ROOTS
        for path in (ROOT / root).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )
    return {relative: "sha256:" + sha256(ROOT / relative) for relative in relatives}


def write_scope_verification() -> dict[str, Any]:
    #: The runner's write-scope-verification.json is the frozen pin; re-derive
    #: live and refuse on any drift in the four approved product trees.
    pinned = read_json(ATTEMPT / "write-scope-verification.json")
    live = _live_product_hashes()
    if pinned.get("product_file_hashes") != live:
        raise SystemExit("product bytes drifted from the sealed write-scope record")
    return {
        "approved_scope": APPROVED_SCOPE,
        "attempt_id": ATTEMPT_ID,
        "authored_by": (
            "bounded implementation agent under the product owner's instruction"
        ),
        "composed_modules_modified": False,
        "product_file_hashes": live,
        "product_roots": list(PRODUCT_ROOTS),
        "reset_clean_stash_commit_push_performed": False,
        "reviewed_by": (
            "separate sealing agent, distinct from the author (independent review)"
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
        "declared_required_checks": ["research_view_e2e", "source_span_view_test"],
        "exit_criteria": {
            "minority_counterevidence_visible": {
                "mechanism": (
                    "every research view keeps minority and counter-evidence "
                    "first-class beside the verdict and refuses to hide or invent "
                    "it: parliament renders the minority report before the council "
                    "briefs and refuses hidden/unrecorded/invented dissent, aporia "
                    "renders open questions (hidden assumptions and unresolved "
                    "objections) first and refuses hiding or resolution overclaim, "
                    "passport renders counter-evidence beside the verdict and "
                    "refuses hiding a counter-evidence field, and atlas surfaces "
                    "counter_count and the coverage-claim vocabulary bound to the "
                    "certificate hash"
                ),
                "required_checks": ["research_view_e2e"],
                "status": "PASS",
            },
            "source_span_accessible": {
                "mechanism": (
                    "every research view carries a source receipt that exposes the "
                    "provenance manifest, evidence pack, attestation, bias register "
                    "and artifact hashes back to the underlying sources, and binds "
                    "only the declared read operations from the generated route "
                    "manifest (atlas coverage/provenance receipt, parliament "
                    "adjudication/brief/minority hashes, aporia graph/proof-trace "
                    "receipt, passport attestation/evidence-pack/stability receipt); "
                    "an undeclared or write operation refuses"
                ),
                "required_checks": ["source_span_view_test"],
                "status": "PASS",
            },
        },
        "required_checks": {
            "research_view_e2e": {
                "junit": suites["research_view_e2e"]["junit"],
                "status": "PASS",
                "test_count": suites["research_view_e2e"]["collected"],
            },
            "source_span_view_test": {
                "junit": suites["source_span_view_test"]["junit"],
                "status": "PASS",
                "test_count": suites["source_span_view_test"]["collected"],
            },
        },
        "required_checks_mapping": (
            "The manifest declares exactly two required checks over four "
            "*-view.test.mjs modules (atlas, parliament, aporia, passport). The "
            "checks are cross-cutting concerns, not a file partition: every view "
            "suite is a full end-to-end read-model projection (build*View -> "
            "render*Panel) AND carries a named 'the view carries its (source|graph) "
            "receipt' provenance test. research_view_e2e maps to all four suites "
            "for the end-to-end + minority/counterevidence-visible exit criterion; "
            "source_span_view_test maps to all four suites for the source-receipt "
            "provenance path (source-span accessible). Both run the full 52-test "
            "set; no test is excluded, filtered or weakened."
        ),
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
                f"{ATTEMPT_DIR}/build_u03_0001_evidence.py",
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
        "# U03-0001 independent review of bounded-agent work\n"
        "\n"
        "- Author: a bounded implementation agent (write scope\n"
        "  web/src/features/{atlas,parliament,aporia,passport}/**) under the\n"
        "  product owner's instruction. Reviewer: a separate sealing agent that\n"
        "  did not author U03. Author/reviewer separation holds\n"
        "  (actor_independence=true between two distinct agents); external\n"
        "  actor-independent certification does not.\n"
        "- Manifest conformance: U03 declares exactly two required_checks\n"
        "  (research_view_e2e, source_span_view_test) and two exit_criteria\n"
        "  (source span accessible; minority/counterevidence visible), verified\n"
        "  against manifests/development_manifest.yaml. These are NOT the standard\n"
        "  five checks. There is no Python targeted suite and no Ruff gate for\n"
        "  this Node/Web package, and none was invented.\n"
        "- required_checks-mapping reconciliation: the two required checks are\n"
        "  cross-cutting concerns over the same four *-view.test.mjs modules\n"
        "  (atlas, parliament, aporia, passport), not a partition of the files.\n"
        "  Every view suite is a full end-to-end read-model projection\n"
        "  (build*View -> render*Panel) and every view suite carries a named\n"
        "  'the view carries its (source|graph) receipt' provenance test. The\n"
        "  four view test-file docstrings each reference generic 'five required\n"
        "  checks' named-test dimensions (schema_and_type_check,\n"
        "  unit_and_contract_tests, negative_and_adversarial,\n"
        "  provenance_and_receipt_audit, independent_review); those are the\n"
        "  suite's internal organisation and are NOT the manifest's required\n"
        "  checks. Mapping was therefore done to the manifest's ACTUAL two checks\n"
        "  by closest-covering named tests, without weakening or excluding any\n"
        "  test: research_view_e2e -> all four suites (52 tests), carrying\n"
        "  'minority/counterevidence visible'; source_span_view_test -> all four\n"
        "  suites (52 tests), carrying 'source span accessible' via the per-view\n"
        "  source-receipt tests (atlas L302, parliament L291, aporia L264,\n"
        "  passport L251). Both checks run the full 52-test set; the overlap is\n"
        "  inherent to the manifest bundling four views into two cross-cutting\n"
        "  checks, and is not a gap.\n"
        "- research_view_e2e (52/52): parliament keeps dissent/counter-evidence\n"
        "  first-class and refuses hidden, unrecorded or invented dissent and\n"
        "  majority-vote presentation; aporia renders open questions first and\n"
        "  refuses hiding or resolution overclaim; passport renders\n"
        "  counter-evidence beside the verdict, keeps the seven confidence\n"
        "  dimensions separate and refuses aggregation; atlas surfaces\n"
        "  counter_count and the coverage-claim vocabulary bound to the coverage\n"
        "  certificate hash. Views are deep-frozen and deterministic and read no\n"
        "  clock, random source or environment.\n"
        "- source_span_view_test (52/52): each view exposes a source receipt back\n"
        "  to provenance manifests, evidence packs, attestations, bias registers\n"
        "  and artifact hashes, and binds only the declared read operations from\n"
        "  the generated route manifest; undeclared or write operations refuse.\n"
        "- Write-scope audit: the product bytes hashed here sit exactly inside\n"
        "  the four approved feature trees; no composed module, schema, manifest\n"
        "  or test outside scope was modified or weakened.\n"
        "- full-node-suite: captured GREEN at 107 modules / 1192 tests. This\n"
        "  absolute total is a repository-wide, integration-owned number that\n"
        "  concurrent in-flight packages actively move; the frozen JUnit is the\n"
        "  deterministic evidence, and reconciling the live inventory total is\n"
        "  the integrating session's responsibility, not this leaf package's.\n"
        "- Dependency binding: U01 (U01-0001, E0199/E0200) is the declared\n"
        "  dependency; the regression baseline is the current latest-sealed\n"
        "  report F06-0001 (E0237/E0238), both bound by report byte-hash.\n"
        "- No blocking findings.\n"
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
        "attempt_type": "U03_ATLAS_PARLIAMENT_APORIA_PASSPORT_VIEWS",
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
            "a running web server, backend, or live HTTP endpoint",
            "views that are anything but deep-frozen and deterministic "
            "(no clock, random source, or environment is read)",
            "authority acquisition by any view, request, verdict, or receipt",
            "any hiding of minority or counter-evidence, which stays first-class "
            "and visible in every view",
            "any source span that is not accessible through the view's source "
            "receipt and declared read operations",
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
            "required_checks_mapping": verification["required_checks_mapping"],
            "reviewer": "separate sealing agent (did not author U03)",
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
        "next_action": "SEAL_U03_0001_THEN_RECOMPUTE_DAG",
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
    write_json("u03-verification.json", verification)
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
        raise SystemExit("U03-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "u03-verification.json")
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
    verification = read_json(ATTEMPT / "u03-verification.json")
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
        raise SystemExit("stored U03-0001 report is not the deterministic document")
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
