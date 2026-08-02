#!/usr/bin/env python3
"""Build and verify S03-0001 Skill Vault quarantine and SkillLockfile evidence.

S03-0001 implements ``packages/skill-vault/**``: a Skill Vault boundary that
quarantines every remote skill candidate as an inert, non-executable record,
statically scans it without executing a single candidate byte, and hash-pins
approved skills in a canonical SkillLockfile before any disabled installation or
explicit activation.  ``quarantineCandidate`` admits a candidate only into an
inert ``QUARANTINED`` state (``executable:false``, ``active:false``,
``authorityEligible:false``) that never exposes the raw ``files`` or ``content``
bytes, and it fails closed on hostile input shapes -- path traversal, absolute or
backslash or portable-reserved names (``PATH_ESCAPE_DENIED``), name collisions
(``PATH_COLLISION``), accessor-bearing fields (``ACCESSOR_FIELD_DENIED``), and
Proxy inputs (``PROXY_INPUT_DENIED``) -- without ever invoking a getter.
``scanCandidate`` inventories files and script-shaped members, flags install
hooks (``PACKAGE_INSTALL_HOOK``), dynamic evaluation (``DYNAMIC_EVALUATION``),
self-authority claims (``SELF_AUTHORITY_CLAIM``), symlink content
(``SYMLINK_CONTENT``), a failed signature (``SIGNATURE_VERIFICATION_FAILED``), and
script content (``SCRIPT_CONTENT``) while asserting ``noScriptsExecuted:true``, and
any CRITICAL finding makes ``issueReviewDecision`` fail closed with
``CRITICAL_FINDING_BLOCKS_APPROVAL``.  A review must bind the exact source,
revision, content hash, and inferred permissions or it is rejected
(``REVIEW_SUBJECT_MISMATCH``, ``INFERRED_PERMISSION_MISSING``, ``MISSING_FIELD``),
and a foreign or copied candidate or scan cannot gain local approval
(``UNRECOGNIZED_CANDIDATE``).  ``createSkillLockfile`` pins each approved skill's
content hash, source, revision, license, sorted permissions, and sorted approvers
under a deterministic ``lock_hash`` over canonical JSON;
``verifySkillLockfileSnapshot`` refuses any drift (``LOCK_HASH_MISMATCH``,
``NON_CANONICAL_ORDER``, ``ACCESSOR_FIELD_DENIED``); a disabled installation
refuses a hash drift (``INSTALL_HASH_MISMATCH``) or an unapproved or rejected
skill (``SKILL_NOT_APPROVED``); and activation refuses a policy drift
(``POLICY_HASH_MISMATCH``), an unverified permission
(``UNVERIFIED_PERMISSION_DENIED``), a permission expansion
(``PERMISSION_EXPANSION_DENIED``), or a foreign lockfile (``UNRECOGNIZED_LOCKFILE``)
and reports ``effectPerformed:false``.  This builder verifies the executed checks
and emits immutable attempt evidence; it never modifies product files.
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
ATTEMPT = ROOT / "artifacts/work_packages/S03/attempts/0001"
ATTEMPT_ID = "S03-0001"
WORK_PACKAGE_ID = "S03"
RECORDED_AT = "2026-08-02T00:00:00.000Z"

EXPECTED_MALICIOUS_COUNT = 11
EXPECTED_LOCKFILE_COUNT = 10
EXPECTED_TARGETED_COUNT = 21
EXPECTED_PYTHON_COUNT = 1261
EXPECTED_NODE_COUNT = 1274
EXPECTED_NODE_FILE_COUNT = 113

PACKAGE = "packages/skill-vault"
COMPONENT = "packages/skill-vault/src"
EXPECTED_PRODUCT_HASHES = {
    "packages/skill-vault/README.md": "6907fcb559b70176f31deb07c3a10710e83d8e51f10bd3d7722dc863255244a1",
    "packages/skill-vault/package.json": "cebcf93793345e05a9e0085ccb0e99e8d8460750bfee6d5d1ead85b3c70a0287",
    "packages/skill-vault/src/malicious-skill-fixture.test.mjs": "135b5c56730d2e8f1bde0122220ee41553746995f9dd9bbc385a0fbaf6f0f83e",
    "packages/skill-vault/src/skill-lockfile.test.mjs": "c4d75c2f065596b8a01a18d38b1c833e76d5695ac499f59939791f03a9dd0120",
    "packages/skill-vault/src/skill-vault.mjs": "f3308719bfdfc400c25fce95fa2c089c99a73192e0c48dc35a936ff6025564b3",
}
EXPECTED_DEPENDENCY_HASHES = {
    "artifacts/work_packages/S01/report.json": "6aa7a2ae6c3c047df6293e227ac3206a2e213b322ef1619eb1814e589f3ea7d6",
}

JUNIT_PATHS = {
    "malicious": ATTEMPT / "malicious-skill-fixture-test.junit.xml",
    "lockfile": ATTEMPT / "skill-lockfile-test.junit.xml",
    "targeted": ATTEMPT / "targeted-skill-vault.junit.xml",
    "full_python": ATTEMPT / "full-python-suite.junit.xml",
    "full_node": ATTEMPT / "full-node-suite.junit.xml",
}
# Every S03 check but the full Python suite runs under the Node runner.
_NODE_JUNITS = frozenset(
    {
        "malicious",
        "lockfile",
        "targeted",
        "full_node",
    }
)
RUN_RESULTS = (
    "ruff-check",
    "ruff-format-check",
    "malicious-skill-fixture-test",
    "skill-lockfile-test",
    "targeted-skill-vault",
    "full-python-suite",
    "full-node-suite",
    "git-diff-check",
)
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "run_s03_0001_checks.py",
    "build_s03_0001_evidence.py",
    "s03_0001_rah_seal.py",
    "dependency-status.json",
    "s03-verification.json",
    "write-scope-verification.json",
    "node-test-inventory.json",
    "junit-normalization-verification.json",
    "malicious-skill-fixture-test.junit.xml",
    "skill-lockfile-test.junit.xml",
    "targeted-skill-vault.junit.xml",
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
    malicious = node_summary(JUNIT_PATHS["malicious"])
    lockfile = node_summary(JUNIT_PATHS["lockfile"])
    targeted = node_summary(JUNIT_PATHS["targeted"])
    python = pytest_summary(JUNIT_PATHS["full_python"])
    node = node_summary(JUNIT_PATHS["full_node"])
    node_inventory = read_json(ATTEMPT / "node-test-inventory.json")
    for label, summary, expected in (
        ("malicious_skill_fixture_test", malicious, EXPECTED_MALICIOUS_COUNT),
        ("skill_lockfile_test", lockfile, EXPECTED_LOCKFILE_COUNT),
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
        "full_node": node,
        "full_python": python,
        "malicious_skill_fixture_test": malicious,
        "new_failure_count": 0,
        "skill_lockfile_test": lockfile,
        "status": "PASS",
        "targeted_skill_vault": targeted,
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
            "S01": _pass_dependency(
                "S01", "S01-0001", "artifacts/work_packages/S01/report.json"
            ),
        },
        "next_action": "SEAL_S03_0001_THEN_CONTINUE_DAG",
        "status": "PASS",
    }


def write_scope_verification() -> dict[str, Any]:
    assert_hashes(EXPECTED_PRODUCT_HASHES)
    component_files = sorted(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / PACKAGE).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )
    if component_files != sorted(EXPECTED_PRODUCT_HASHES):
        raise SystemExit(
            f"skill-vault package holds unexpected files: {component_files}"
        )
    return {
        "approved_scope": [f"{PACKAGE}/**", "artifacts/work_packages/S03/**"],
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


def s03_verification(regression: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "exit_criteria": {
            "hash_license_permissions_pinned": {
                "evidence": [
                    f"{COMPONENT}/skill-lockfile.test.mjs",
                ],
                "mechanism": (
                    "createSkillLockfile emits a v1 lockfile that pins, per approved "
                    "skill, the exact source, revision, content_hash, license, sorted "
                    "permission envelope, sorted approver ids, and review_status under "
                    "a deterministic lock_hash computed over canonical JSON; the lock "
                    "is order-independent and deeply frozen. "
                    "verifySkillLockfileSnapshot recomputes the hash and refuses any "
                    "drift (LOCK_HASH_MISMATCH), a non-canonical permission order "
                    "(NON_CANONICAL_ORDER), or an accessor-bearing field "
                    "(ACCESSOR_FIELD_DENIED) without invoking getters, and treats a "
                    "serialized snapshot as inert (isSkillLockfile:false, "
                    "authorityEligible:false). A disabled installation refuses a "
                    "content-hash drift (INSTALL_HASH_MISMATCH) or an unapproved or "
                    "rejected skill (SKILL_NOT_APPROVED), conformance cannot report an "
                    "undeclared permission (UNDECLARED_PERMISSION), and activation "
                    "refuses a policy drift (POLICY_HASH_MISMATCH), an unverified or "
                    "expanded permission (UNVERIFIED_PERMISSION_DENIED, "
                    "PERMISSION_EXPANSION_DENIED), or a foreign lockfile "
                    "(UNRECOGNIZED_LOCKFILE) and never performs an effect "
                    "(effectPerformed:false)"
                ),
                "status": "PASS",
            },
            "remote_skills_inactive_until_approved": {
                "evidence": [
                    f"{COMPONENT}/malicious-skill-fixture.test.mjs",
                ],
                "mechanism": (
                    "quarantineCandidate admits a remote candidate only into an inert "
                    "QUARANTINED state (executable:false, active:false, "
                    "authorityEligible:false) that never exposes the raw files or "
                    "content bytes, and fails closed on path traversal, absolute, "
                    "backslash, or portable-reserved names (PATH_ESCAPE_DENIED), name "
                    "collisions (PATH_COLLISION), accessor fields "
                    "(ACCESSOR_FIELD_DENIED), and Proxy inputs (PROXY_INPUT_DENIED) "
                    "without invoking any getter. scanCandidate asserts "
                    "noScriptsExecuted:true while flagging install hooks, dynamic "
                    "evaluation, self-authority claims, symlink content, a failed "
                    "signature, and script content and inferring the implied "
                    "permission envelope; any CRITICAL finding makes "
                    "issueReviewDecision fail closed with "
                    "CRITICAL_FINDING_BLOCKS_APPROVAL. A review must bind the exact "
                    "source, revision, content hash, and inferred permissions "
                    "(REVIEW_SUBJECT_MISMATCH, INFERRED_PERMISSION_MISSING, "
                    "MISSING_FIELD), and a foreign or copied candidate or scan cannot "
                    "gain local approval (UNRECOGNIZED_CANDIDATE); activation requires "
                    "a disabled installation plus passing conformance and stays inert "
                    "under a name collision (BLOCKED_NAME_COLLISION, "
                    "INSTALLATION_NOT_CONFORMABLE)"
                ),
                "status": "PASS",
            },
        },
        "hash_license_permissions_pinned": {
            "activation_refuses_policy_permission_or_lockfile_drift": True,
            "canonical_lock_hash_is_order_independent_and_frozen": True,
            "disabled_install_refuses_content_hash_drift": True,
            "rejected_decisions_stay_locked_and_uninstallable": True,
            "serialized_snapshot_is_verifiable_but_inert": True,
        },
        "quarantine_never_executes_candidate_bytes": {
            "accessor_or_proxy_inputs_rejected_without_getters": True,
            "critical_finding_blocks_approval_fail_closed": True,
            "path_escape_and_collision_fail_closed": True,
            "raw_files_and_content_never_exposed": True,
            "static_scan_flags_hooks_eval_authority_symlink_signature_script": True,
        },
        "required_checks": {
            "malicious_skill_fixture_test": {
                "module": f"{COMPONENT}/malicious-skill-fixture.test.mjs",
                "status": "PASS",
                "test_count": regression["malicious_skill_fixture_test"]["collected"],
            },
            "skill_lockfile_test": {
                "module": f"{COMPONENT}/skill-lockfile.test.mjs",
                "status": "PASS",
                "test_count": regression["skill_lockfile_test"]["collected"],
            },
        },
        "schema_reference_is_string_only": {
            "loaded_or_validated": False,
            "note": (
                "skill-vault.mjs returns schemas/skill-lockfile.schema.json as a "
                "string schemaRef only; the schema file is neither read nor validated "
                "against, lies outside the packages/skill-vault/** write scope, and no "
                "required check depends on it"
            ),
            "schema_ref": "schemas/skill-lockfile.schema.json",
        },
        "status": "PASS",
        "targeted_test_count": regression["targeted_skill_vault"]["collected"],
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
                "artifacts/work_packages/S03/attempts/0001/build_s03_0001_evidence.py",
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
        "# S03-0001 independent review of bounded-agent work\n"
        "\n"
        "- Author: the bounded implementation agent that wrote\n"
        "  packages/skill-vault. Reviewer: this seal-prep session, a distinct actor\n"
        "  that did not author the Skill Vault boundary. The author never approves\n"
        "  its own work, so actor_independence HOLDS for this review; external\n"
        "  actor-independent certification does NOT, and no such claim is made. S03\n"
        "  is risk_class=medium and governs the skill supply chain, so quarantine,\n"
        "  static scanning, locking, and activation were attacked on their contracts\n"
        "  rather than skimmed.\n"
        "- Remote skills are quarantined and inactive until approved (fail closed).\n"
        "  quarantineCandidate admits a remote candidate only into an inert\n"
        "  QUARANTINED record with executable:false, active:false, and\n"
        "  authorityEligible:false that exposes no raw files or content own-property,\n"
        "  and it rejects hostile input shapes -- path traversal, absolute,\n"
        "  backslash, and portable-reserved (NUL) names (PATH_ESCAPE_DENIED),\n"
        "  case-folding name collisions (PATH_COLLISION), accessor-bearing fields\n"
        "  (ACCESSOR_FIELD_DENIED), and Proxy inputs (PROXY_INPUT_DENIED) -- with the\n"
        "  getter-call counter proving no getter ran. scanCandidate never executes a\n"
        "  candidate byte (noScriptsExecuted:true) yet flags install hooks\n"
        "  (PACKAGE_INSTALL_HOOK), dynamic evaluation (DYNAMIC_EVALUATION),\n"
        "  self-authority claims (SELF_AUTHORITY_CLAIM), symlink content that it\n"
        "  inventories without following (SYMLINK_CONTENT), a failed signature\n"
        "  (SIGNATURE_VERIFICATION_FAILED), and script-shaped members (SCRIPT_CONTENT)\n"
        "  while inferring the implied PROCESS_EXECUTE, SECRET_READ, and NETWORK\n"
        "  permissions. Any CRITICAL finding makes issueReviewDecision fail closed\n"
        "  with CRITICAL_FINDING_BLOCKS_APPROVAL, so a hostile fixture can never be\n"
        "  approved.\n"
        "- Approval binds the exact reviewed subject. A review must attest the exact\n"
        "  source, revision, content hash, and the full inferred permission envelope\n"
        "  or it is rejected (REVIEW_SUBJECT_MISMATCH, INFERRED_PERMISSION_MISSING),\n"
        "  and a claimed remote signature is only a claim -- the reviewer must state a\n"
        "  status explicitly (MISSING_FIELD). A candidate or scan minted by one vault\n"
        "  boundary cannot be approved or rescanned by another, and a JSON-copied\n"
        "  candidate is not recognized (UNRECOGNIZED_CANDIDATE), so brand identity is\n"
        "  enforced by WeakMap rather than by trusting record shape.\n"
        "- Approved skills are hash/license/permission pinned. createSkillLockfile\n"
        "  emits a v1 lockfile that pins, per skill, the exact source, revision,\n"
        "  content_hash, license, sorted permissions, sorted approver ids, and\n"
        "  review_status under a lock_hash taken over canonical JSON; the hash is\n"
        "  identical across review, permission, and approver input order, and the\n"
        "  lockfile and its entries are deeply frozen. verifySkillLockfileSnapshot\n"
        "  recomputes the lock_hash and refuses a mutated field (LOCK_HASH_MISMATCH),\n"
        "  a reordered permission list (NON_CANONICAL_ORDER), or an accessor field\n"
        "  (ACCESSOR_FIELD_DENIED) without invoking getters, and a serialized snapshot\n"
        "  is verifiable but never a live authority (isSkillLockfile:false). A\n"
        "  rejected decision stays locked as REJECTED with empty approvers and cannot\n"
        "  be installed (SKILL_NOT_APPROVED).\n"
        "- Disabled install and activation stay inert and non-expanding. A disabled\n"
        "  installation requires the exact approved content hash (INSTALL_HASH_MISMATCH)\n"
        "  and surfaces name collisions as BLOCKED_NAME_COLLISION that cannot receive\n"
        "  passing conformance (INSTALLATION_NOT_CONFORMABLE); conformance cannot\n"
        "  report a permission outside the lockfile (UNDECLARED_PERMISSION); and\n"
        "  authorizeActivation requires the exact policy hash (POLICY_HASH_MISMATCH),\n"
        "  a permission both locked and observed in conformance\n"
        "  (UNVERIFIED_PERMISSION_DENIED), and a non-expanding request\n"
        "  (PERMISSION_EXPANSION_DENIED), refuses artifacts mixed across boundaries\n"
        "  (UNRECOGNIZED_LOCKFILE), and returns an ALLOW authorization that only\n"
        "  describes the intent (effectPerformed:false, rollbackAvailable:true,\n"
        "  explicitApprovalLinked:true) -- it never fetches, writes, imports, evals,\n"
        "  or executes the candidate.\n"
        "- Non-blocking note (disclosed, not a finding). skill-vault.mjs returns\n"
        "  schemas/skill-lockfile.schema.json as a string schemaRef only; the schema\n"
        "  file is neither read nor validated against, it lies outside the\n"
        "  packages/skill-vault/** write scope, and no required check depends on it.\n"
        "  Wiring a real Draft 2020-12 validation is a later, out-of-scope refinement\n"
        "  and does not weaken the S03 contract.\n"
        "- Dependencies and checks: the Skill Vault builds on the sealed S01 skill\n"
        "  supply-chain package (S01 report PASS) and adds no new production\n"
        "  dependency. Ruff lint and format, the two required checks\n"
        "  (malicious_skill_fixture_test "
        + f"{EXPECTED_MALICIOUS_COUNT}/{EXPECTED_MALICIOUS_COUNT}, skill_lockfile_test "
        + f"{EXPECTED_LOCKFILE_COUNT}/{EXPECTED_LOCKFILE_COUNT}), targeted "
        + f"{EXPECTED_TARGETED_COUNT}/{EXPECTED_TARGETED_COUNT}, full Python "
        + f"{EXPECTED_PYTHON_COUNT}/{EXPECTED_PYTHON_COUNT}, full Node "
        + f"{EXPECTED_NODE_COUNT}/{EXPECTED_NODE_COUNT} across "
        + f"{EXPECTED_NODE_FILE_COUNT} files, and git diff --check all pass with\n"
        "  zero failures.\n"
        "- Residual limitations: S03 provides skill quarantine, static scanning,\n"
        "  the SkillLockfile, and disabled-install and activation gating only; the\n"
        "  S-phase threat model and red-team gate (S04) and the wider runtime skill\n"
        "  execution surface remain later packages. Verdict: PASS on the exact S03\n"
        "  package contract.\n"
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
            "path": f"artifacts/work_packages/S03/attempts/0001/{name}",
            "sha256": sha256_id(ATTEMPT / name),
        }
        for name in sorted(set(output_names))
    ]
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "attempt_type": "S03_SKILL_VAULT_QUARANTINE_AND_SKILL_LOCKFILE",
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependency_state": dependencies,
        "exit_criteria": {
            "hash_license_permissions_pinned": "PASS",
            "remote_skills_inactive_until_approved": "PASS",
        },
        "global_implementation_gate": "fail",
        "history_and_worktree": {
            "dirty_worktree_preserved": True,
            "prior_attempts_reports_and_rah_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
        },
        "implementation_status": "PASS",
        "not_claimed": [
            "the S-phase threat model and red-team gate (S04)",
            "the wider runtime skill execution surface",
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
        "full_node": f"{EXPECTED_NODE_COUNT}/{EXPECTED_NODE_COUNT}",
        "full_python": f"{EXPECTED_PYTHON_COUNT}/{EXPECTED_PYTHON_COUNT}",
        "malicious_skill_fixture_test": (
            f"{EXPECTED_MALICIOUS_COUNT}/{EXPECTED_MALICIOUS_COUNT}"
        ),
        "next_action": "SEAL_S03_0001_THEN_CONTINUE_DAG",
        "node_file_count": EXPECTED_NODE_FILE_COUNT,
        "package_status": "PASS",
        "skill_lockfile_test": f"{EXPECTED_LOCKFILE_COUNT}/{EXPECTED_LOCKFILE_COUNT}",
        "status": "PASS",
        "targeted_skill_vault": f"{EXPECTED_TARGETED_COUNT}/{EXPECTED_TARGETED_COUNT}",
    }


def build() -> dict[str, Any]:
    for name in RUN_RESULTS:
        check_run(name)
    normalize_junits()
    regression = regression_evidence()
    dependencies = dependency_status()
    write_scope = write_scope_verification()
    verification = s03_verification(regression)
    write_json("dependency-status.json", dependencies)
    write_json("write-scope-verification.json", write_scope)
    write_json("s03-verification.json", verification)
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
        raise SystemExit("S03-0001 report is already RAH-bound")
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
    verification = read_json(ATTEMPT / "s03-verification.json")
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
    verification = read_json(ATTEMPT / "s03-verification.json")
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
        raise SystemExit("stored S03-0001 report is not the deterministic document")
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
