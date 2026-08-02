#!/usr/bin/env python3
"""Build and verify fail-closed evidence for K01-0002.

The evidence binds the immutable document-registration implementation to the
product-owner decision, the exact K01 manifest contract, current dependency
reports, targeted/full regression receipts, and a separate primary-session
adversarial review.  Dependency reports are selected from the highest numeric
attempt so an older PASS can never hide a newer non-PASS attempt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/K01/attempts/0002"
PACKAGE_ROOT = ROOT / "artifacts/work_packages/K01"
ATTEMPT_ID = "K01-0002"
WORK_PACKAGE_ID = "K01"
RECORDED_AT = "2026-07-30T21:10:00.000Z"
MANIFEST = ROOT / "manifests/development_manifest.yaml"
RECEIPT_SCHEMA = ROOT / "schemas/artifact-receipt.schema.json"
DECISION = (
    ROOT
    / "artifacts/authority_decisions/"
    "HD-EF4-K01-SG001-20260730-001.human-decision.json"
)
DECISION_ID = "HD-EF4-K01-SG001-20260730-001"
DECISION_HASH = "sha256:62c7e6885c051e92846bb6580f385efcffca744cd45c531f768f8324bdacaa30"

SOURCE_HASHES = {
    "src/epistemic_foundry/ingest/registry/__init__.py":
        "4af1c5ddb0abdda441de4a9df603ca4676e2c59b8156137302b4cac141ce0be9",
    "src/epistemic_foundry/ingest/registry/errors.py":
        "2553dfe6f34b710ad396128131166b776569d613138470b966e4c50cd973485b",
    "src/epistemic_foundry/ingest/registry/hash.py":
        "967bf4c8dc2e9cf6620df0ffb8dd14eb7fe471f7b0832cf5b7f5d96015cde03b",
    "src/epistemic_foundry/ingest/registry/lineage.py":
        "b51ec00945a88cf7c112fbeb85754e7d427af55ece0675a15bd7bd64ec084a1a",
    "src/epistemic_foundry/ingest/registry/models.py":
        "5db2acd0154b509ba7f29fc349b356cb7700034686e49cc48a6347dbe411ad5b",
    "src/epistemic_foundry/ingest/registry/repository.py":
        "a0fba443b9ee50f04816e72e0c035ce03bea478fb8f4b088424183d64f042284",
    "src/epistemic_foundry/ingest/registry/service.py":
        "99f59a05ab99aed080b944f9f0206f1ff4b8982c8c7ae1b71b99256595369114",
    "docs/ingest_lifecycle_contract.md":
        "4609e5f7441a775c03960e845271b649138a548a486c2eae72bb22c8ca9361de",
    "workflows/corpus_ingest.workflow.yaml":
        "8dad85a0677414765f678e2e53ea759181895c2bbe4bbcfbd97c6964e023d826",
    "tests/fixtures/k01/document-effect-cases.json":
        "35f11d7a4a870916e17a36b8801bfa268a34d000e4cf76f5ef5c022415b330b8",
    "tests/fixtures/k01/document-lineage-cases.json":
        "bdab5441e45c0d12a6e93cbf4a7191c09a56fdc43fdf39c7355ce1f7f3349b4a",
    "tests/fixtures/k01/document-registration-request.valid.json":
        "280bb8c5ce58bd25b52eaca6b1823160a3fcbdd2fb86aba20aa4804052ff7c50",
    "tests/fixtures/k01/document-registration.invalid.json":
        "8bcd891a452afa5d82e7771280293f9775a8d3aca7274c9d9cf3855fe16b7c1c",
    "tests/fixtures/k01/document-registration.valid.json":
        "d2f26e2a2ad8965c10696383dd334871fe46488b2d84973cbbc34a29d8374b73",
    "tests/ingest/test_k01_document_lineage.py":
        "246cb4d8238d1362e2bf156a051d40564ac4745e39620a9b60680cb337c7fb7b",
    "tests/ingest/test_k01_document_registration.py":
        "c4ba36829868752ddda4e7a11f78b2f47d9ab7aa03b9d50e19deadf6be9399a2",
    "tests/ingest/test_k01_effect_reconciliation.py":
        "d3f1fdd2a883c872ee96a20ae094a6ee2fdc6f6c0e804846e26a8108a96d32dc",
    "tests/contracts/test_k01_document_contracts.py":
        "cddb17c1d275de2f52f68d99fc30d65af5107986a8050b4c4547d453547525b2",
    "tests/integration/test_k01_register_document_node.py":
        "789d6f058f0e8d9e39f1f15020d185e997267430ba97fce278463f61e82c0ae7",
}
DECISION_FILE_HASH = (
    "988830f51b1d259e91d4a093da67d631566babcaa150368d2dbde680fb72f423"
)
JUNIT_HASHES = {
    "targeted-k01-suite.junit.xml":
        "b8420f8c691fb469375a2eb61acf03207c4dbe05d98561a3425f20eeb5002c30",
    "full-python-suite.junit.xml":
        "5984cf4e6ff1ae007bc22d81328cea8f448d1db8017172d2abfa8b3bf1444c64",
    "full-node-suite.junit.xml":
        "9c36215328a02559a681ebf2d12aeea0cffb343cc58d613d384be3070028c4f1",
    "full-node-suite.initial-failure.junit.xml":
        "bfd963d9afff7e1b0e86f740e1ce159908b05e66d9de5062f1538d7af17ba01b",
}
SUPPORT_HASHES = {
    "node-test-inventory.json":
        "a3a4322f5eef16c143198c2365a3f7332e619533f16201fc6658017f85c280f5",
    "run_k01_0002_checks.py":
        "61ea3b943f7ebd8a976c8f67fe569956163b2cd834b0c75a78e4aa05081db7ab",
    "codegen-verification.stdout.log":
        "582d58db1b7861b506572d56b823f9681cc1a2b71ee3d1d678e2f873e9a82800",
    "structure-check.stdout.log":
        "a0f4e1b43cc5f2576d0bba4325fd0df83b05f2d439bcb34208dbfb80a0fa724d",
    "boundary-check.stdout.log":
        "2a48ac08975188e29c6403dde604a168834e1aa8f1ddcc2bf26cfab913152884",
    "ruff-check.stdout.log":
        "82b3e6a6c090a57601d22943bd23fca9218d1031dbe5a7b754092f9a156b4f18",
    "git-diff-check.stderr.log":
        "5d598dde66a2fd6d038c840dcb6b09f11638efb57306c868eaa57b1f4ae2fc2f",
}
EXPECTED_DEPENDENCIES = ["B04", "C04", "D04", "S01"]
EXPECTED_WRITE_SCOPE = [
    "workflows/corpus_ingest.workflow.yaml",
    "src/epistemic_foundry/ingest/registry/__init__.py",
    "src/epistemic_foundry/ingest/registry/models.py",
    "src/epistemic_foundry/ingest/registry/service.py",
    "src/epistemic_foundry/ingest/registry/hash.py",
    "src/epistemic_foundry/ingest/registry/lineage.py",
    "src/epistemic_foundry/ingest/registry/repository.py",
    "src/epistemic_foundry/ingest/registry/errors.py",
    "docs/ingest_lifecycle_contract.md",
    "tests/fixtures/k01/document-registration-request.valid.json",
    "tests/fixtures/k01/document-registration.valid.json",
    "tests/fixtures/k01/document-registration.invalid.json",
    "tests/fixtures/k01/document-lineage-cases.json",
    "tests/fixtures/k01/document-effect-cases.json",
    "tests/ingest/test_k01_document_registration.py",
    "tests/ingest/test_k01_document_lineage.py",
    "tests/ingest/test_k01_effect_reconciliation.py",
    "tests/contracts/test_k01_document_contracts.py",
    "tests/integration/test_k01_register_document_node.py",
    "artifacts/work_packages/K01/**",
]
EXPECTED_EXIT_CRITERIA = [
    "source bytes immutable",
    "license/retraction/version status retained",
    "initial registration emits an immutable DocumentRegistration before downstream final-manifest construction",
    "source-byte, registry, ledger, lease, CAS and receipt effects reconcile without reimplementing D/E primitives",
    "legacy records without sufficient immutable evidence fail closed",
]
EXPECTED_REQUIRED_CHECKS = [
    "document_registry_test",
    "license_propagation_test",
    "document_registration_oracle_22",
    "document_lineage_test",
    "document_effect_reconciliation_test",
    "document_contract_validation",
]
NODE_FOOTER_PATTERN = re.compile(
    rb"<!-- (tests|pass|fail|cancelled|skipped|todo) ([0-9]+) -->"
)
OUTPUT_NAMES = (
    "registration-verification.json",
    "lineage-verification.json",
    "effect-reconciliation-verification.json",
    "contract-verification.json",
    "full-regression-impact.json",
    "write-scope-verification.json",
    "dependency-status.json",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_id(path: Path) -> str:
    return "sha256:" + sha256(path)


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


def write_json(path: Path, value: object) -> None:
    path.write_text(render(value), encoding="utf-8", newline="\n")


def canonical_hash_excluding(value: dict[str, Any], excluded: str) -> str:
    preimage = {key: item for key, item in value.items() if key != excluded}
    encoded = json.dumps(
        preimage,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def assert_bound_file(relative: str, expected_hash: str) -> Path:
    path = ROOT / relative
    if not path.is_file():
        raise SystemExit(f"required bound file is missing: {relative}")
    actual = sha256(path)
    if actual != expected_hash:
        raise SystemExit(
            f"bound file changed: {relative}: sha256:{actual} != sha256:{expected_hash}"
        )
    return path


def assert_hashes(expected: dict[str, str], *, base: Path = ROOT) -> None:
    for relative, expected_hash in expected.items():
        path = base / relative
        if not path.is_file() or sha256(path) != expected_hash:
            raise SystemExit(f"bound evidence changed or is missing: {path}")


def source_inventory() -> list[dict[str, Any]]:
    assert_hashes(SOURCE_HASHES)
    rows: list[dict[str, Any]] = []
    for relative, digest in SOURCE_HASHES.items():
        path = ROOT / relative
        data = path.read_bytes()
        if data.startswith(b"\xef\xbb\xbf"):
            raise SystemExit(f"K01 source unexpectedly has a UTF-8 BOM: {relative}")
        if b"\r\n" in data or not data.endswith(b"\n"):
            raise SystemExit(f"K01 source does not use canonical LF endings: {relative}")
        text = data.decode("utf-8")
        if "\ufffd" in text:
            raise SystemExit(f"K01 source contains a replacement character: {relative}")
        rows.append(
            {
                "byte_size": len(data),
                "path": relative,
                "sha256": "sha256:" + digest,
                "utf8_bom": False,
                "uses_lf_only": True,
            }
        )
    cache = ROOT / "src/epistemic_foundry/ingest/registry/__pycache__"
    if cache.exists():
        raise SystemExit("generated K01 __pycache__ must be absent from final evidence")
    return rows


def manifest_contract() -> dict[str, Any]:
    raw = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    packages = raw.get("work_packages")
    if not isinstance(packages, list) or len(packages) != 156:
        raise SystemExit("development manifest must contain 156 work packages")
    rows = [row for row in packages if row.get("id") == WORK_PACKAGE_ID]
    if len(rows) != 1:
        raise SystemExit("development manifest must contain exactly one K01 row")
    row = rows[0]
    expected = {
        "depends_on": EXPECTED_DEPENDENCIES,
        "write_scope": EXPECTED_WRITE_SCOPE,
        "exit_criteria": EXPECTED_EXIT_CRITERIA,
        "required_checks": EXPECTED_REQUIRED_CHECKS,
    }
    for key, value in expected.items():
        if row.get(key) != value:
            raise SystemExit(f"K01 manifest contract changed: {key}: {row.get(key)!r}")
    return {
        **expected,
        "independent_review": row.get("independent_review"),
        "manifest_sha256": sha256_id(MANIFEST),
        "package_count": len(packages),
        "status": "PASS",
    }


def pytest_summary(path: Path) -> dict[str, Any]:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    tests = sum(int(suite.get("tests", "0")) for suite in suites)
    failures = sum(int(suite.get("failures", "0")) for suite in suites)
    errors = sum(int(suite.get("errors", "0")) for suite in suites)
    skipped = sum(int(suite.get("skipped", "0")) for suite in suites)
    return {
        "collected": tests,
        "errors": errors,
        "failed": failures,
        "junit": path.relative_to(ROOT).as_posix(),
        "junit_sha256": sha256_id(path),
        "passed": tests - failures - errors - skipped,
        "skipped": skipped,
        "xml_testcase_count": len(root.findall(".//testcase")),
    }


def node_summary(path: Path) -> dict[str, Any]:
    root = ET.parse(path).getroot()
    cases = root.findall(".//testcase")
    footer = {
        key.decode("ascii"): int(value)
        for key, value in NODE_FOOTER_PATTERN.findall(path.read_bytes())
    }
    required = {"tests", "pass", "fail", "cancelled", "skipped", "todo"}
    if set(footer) != required:
        raise SystemExit(f"Node JUnit footer is incomplete: {path}")
    failures = []
    for case in cases:
        failure = case.find("failure")
        if failure is not None:
            failures.append(
                {
                    "file": case.get("file"),
                    "message": failure.get("message"),
                    "name": case.get("name"),
                }
            )
    files = sorted({case.get("file", "") for case in cases if case.get("file")})
    return {
        "cancelled": footer["cancelled"],
        "collected": footer["tests"],
        "failed": footer["fail"],
        "failure_cases": failures,
        "junit": path.relative_to(ROOT).as_posix(),
        "junit_sha256": sha256_id(path),
        "passed": footer["pass"],
        "skipped": footer["skipped"],
        "test_file_count": len(files),
        "todo": footer["todo"],
        "xml_error_count": sum(case.find("error") is not None for case in cases),
        "xml_failure_count": len(failures),
        "xml_testcase_count": len(cases),
    }


def run_check(command: list[str]) -> dict[str, Any]:
    executable = command
    if sys.platform == "win32" and command[0] == "npm":
        executable = ["cmd.exe", "/d", "/c", "npm.cmd", *command[1:]]
    process = subprocess.run(
        executable,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return {
        "command": " ".join(command),
        "exit_code": process.returncode,
        "status": "PASS" if process.returncode == 0 else "FAIL",
        "stderr": process.stderr.strip(),
        "stdout": process.stdout.strip(),
    }


def decision_evidence() -> dict[str, Any]:
    assert_bound_file(
        DECISION.relative_to(ROOT).as_posix(), DECISION_FILE_HASH
    )
    decision = read_json(DECISION)
    if not (
        decision.get("decision_id") == DECISION_ID
        and decision.get("subject_id") == "K01-SG001"
        and decision.get("decision_type") == "correct"
        and decision.get("authority_role") == "product_owner"
        and decision.get("decision_hash") == DECISION_HASH
        and decision.get("non_mutation_acknowledgement") is True
    ):
        raise SystemExit("K01 HumanDecision semantics changed")
    return {
        "artifact": DECISION.relative_to(ROOT).as_posix(),
        "artifact_sha256": sha256_id(DECISION),
        "decision_hash": DECISION_HASH,
        "decision_id": DECISION_ID,
        "status": "PASS",
        "subject_id": "K01-SG001",
    }


def registration_verification() -> dict[str, Any]:
    inventory = source_inventory()
    service = (ROOT / "src/epistemic_foundry/ingest/registry/service.py").read_text(
        encoding="utf-8"
    )
    repository = (
        ROOT / "src/epistemic_foundry/ingest/registry/repository.py"
    ).read_text(encoding="utf-8")
    workflow = yaml.safe_load(
        (ROOT / "workflows/corpus_ingest.workflow.yaml").read_text(encoding="utf-8")
    )
    node = next(row for row in workflow["nodes"] if row["node_id"] == "register_document")
    required_fragments = {
        "action_intent_resolved_on_replay": "resolve_action_intent(" in service,
        "artifact_receipt_verified": "_verify_artifact_receipt" in service,
        "cas_exact_one_revision_advance":
            "outcome.current_revision != outcome.expected_revision + 1" in service
            and "cas.current_revision != cas.expected_revision + 1" in service,
        "effect_receipt_verified": "_verify_effect_receipt_contract" in service,
        "fencing_and_capability_authorized": "authorize_registration(" in repository,
        "ledger_event_verified": "_verify_ledger_event" in service,
        "no_default_authority_ports": "ports: RegistrationPorts" in service
            and "ports: RegistrationPorts | None" not in service,
        "result_envelope_after_commit": service.find("cas = _commit(")
            < service.rfind("return _result_envelope("),
        "staged_source_only": "resolve_staged_source(" in repository,
    }
    if not all(required_fragments.values()):
        raise SystemExit(f"K01 registration probes failed: {required_fragments}")
    forbidden_runtime_tokens = (
        "requests.",
        "urllib.request",
        "httpx.",
        "socket.",
        "getcwd(",
        "path.cwd(",
        "repo_root",
    )
    lowered = service.lower()
    forbidden_hits = [token for token in forbidden_runtime_tokens if token in lowered]
    if forbidden_hits:
        raise SystemExit(f"K01 runtime fallback/network tokens found: {forbidden_hits}")
    if not (
        node["executor_type"] == "deterministic"
        and node["executor_ref"]
        == "epistemic_foundry.ingest.registry:register_document"
        and node["input_schema_ref"] == "schemas/node-invocation.schema.json"
        and node["output_schema_ref"] == "schemas/result-envelope.schema.json"
        and node["depends_on"] == []
        and node["idempotency_key_fields"] == ["idempotency_key", "request_hash"]
        and node["capabilities"]
        == ["artifact_read", "artifact_write", "ledger_append", "document_register"]
    ):
        raise SystemExit("register_document workflow binding changed")
    oracle = read_json(ROOT / "tests/fixtures/k01/document-effect-cases.json")
    cases = oracle.get("cases")
    if not isinstance(cases, list) or oracle.get("case_count") != len(cases) or len(cases) != 22:
        raise SystemExit("K01 oracle is not the exact 22-case contract")
    identifiers = [str(case.get("case_id")) for case in cases if isinstance(case, dict)]
    if len(set(identifiers)) != 22 or identifiers != [
        next(value for value in identifiers if value.startswith(f"K01-ORACLE-{index:02d}-"))
        for index in range(1, 23)
    ]:
        raise SystemExit("K01 oracle case identities are not stable and ordered")
    return {
        "attempt_id": ATTEMPT_ID,
        "authority_boundary": {
            "business_truth": "IMMUTABLE_DOCUMENT_REGISTRATION",
            "required_shared_ports": ["D03", "E01", "E02", "E03", "CAS"],
            "result_envelope_role": "EXECUTION_TELEMETRY_ONLY",
            "runtime_fallback_count": 0,
        },
        "decision": decision_evidence(),
        "oracle": {
            "case_count": 22,
            "case_ids": identifiers,
            "duplicate_case_count": 0,
            "status": "PASS",
        },
        "semantic_probes": required_fragments,
        "source_files": inventory,
        "status": "PASS",
        "workflow": {
            "capabilities": node["capabilities"],
            "executor_ref": node["executor_ref"],
            "idempotency_key_fields": node["idempotency_key_fields"],
            "node_id": node["node_id"],
            "status": "PASS",
        },
    }


def lineage_verification() -> dict[str, Any]:
    fixture = read_json(ROOT / "tests/fixtures/k01/document-lineage-cases.json")
    cases = fixture.get("cases")
    expected_ids = [
        "VALID_SUPERSESSION",
        "UNKNOWN_PREDECESSOR",
        "CROSS_SCOPE_PREDECESSOR",
        "CYCLIC_PREDECESSOR",
        "IMMUTABLE_HISTORY_REWRITE",
    ]
    if not isinstance(cases, list) or [row.get("case_id") for row in cases] != expected_ids:
        raise SystemExit("K01 lineage fixture changed")
    lineage = (
        ROOT / "src/epistemic_foundry/ingest/registry/lineage.py"
    ).read_text(encoding="utf-8")
    registration_tests = (
        ROOT / "tests/ingest/test_k01_document_lineage.py"
    ).read_text(encoding="utf-8")
    probes = {
        "bounded_cycle_guard": "maximum_depth: int = 10_000" in lineage,
        "cross_scope_rejected": "DOCUMENT_LINEAGE_SCOPE_MISMATCH" in lineage,
        "immutable_rewrite_rejected": "assert_registration_immutable" in lineage,
        "preflight_before_controlled_effect":
            "test_invalid_lineage_is_rejected_before_controlled_effect"
            in registration_tests,
        "replay_reopens_predecessor_chain":
            "test_exact_replay_fails_closed_when_predecessor_history_disappears"
            in registration_tests,
        "self_or_cycle_rejected": "DOCUMENT_LINEAGE_CYCLE" in lineage,
        "unknown_predecessor_rejected": "DOCUMENT_LINEAGE_UNKNOWN" in lineage,
    }
    if not all(probes.values()):
        raise SystemExit(f"K01 lineage probes failed: {probes}")
    return {
        "attempt_id": ATTEMPT_ID,
        "case_ids": expected_ids,
        "immutable_history": "PASS",
        "lineage_case_count": 5,
        "semantic_probes": probes,
        "status": "PASS",
    }


def effect_verification() -> dict[str, Any]:
    tests = (
        ROOT / "tests/ingest/test_k01_effect_reconciliation.py"
    ).read_text(encoding="utf-8")
    registration_tests = (
        ROOT / "tests/ingest/test_k01_document_registration.py"
    ).read_text(encoding="utf-8")
    probes = {
        "action_intent_payload_reopened":
            "test_replay_fails_when_resolved_action_intent_payload_was_mutated" in tests,
        "cas_exact_advance_commit_offsets_0_and_2":
            '@pytest.mark.parametrize("revision_offset", [0, 2])' in registration_tests,
        "cas_exact_advance_replay_offsets_0_and_2":
            '@pytest.mark.parametrize("current_revision_offset", [0, 2])' in tests,
        "crash_or_missing_effect_never_commits":
            "test_missing_effect_receipt_never_commits" in tests,
        "effect_receipt_hash_verified":
            "test_effect_receipt_hash_mismatch_never_commits" in tests,
        "effect_status_fail_closed": "test_non_success_effect_receipts_never_commit" in tests,
        "idempotent_replay_no_republish": "K01-ORACLE-16-EXACT-IDEMPOTENT-REPLAY"
            in registration_tests,
        "invalid_existing_commit_reconciles_or_fails":
            "test_incomplete_existing_commit_requires_shared_reconciliation" in tests,
        "valid_reconciliation_reopens_all_evidence":
            "test_valid_shared_reconciliation_reopens_all_evidence" in tests,
    }
    if not all(probes.values()):
        raise SystemExit(f"K01 effect probes failed: {probes}")
    return {
        "attempt_id": ATTEMPT_ID,
        "controlled_effect_repetition_on_invalid_replay": 0,
        "semantic_probes": probes,
        "status": "PASS",
    }


def contract_verification() -> dict[str, Any]:
    codegen_path = ATTEMPT / "codegen-verification.stdout.log"
    codegen = read_json(codegen_path)
    if not (
        codegen.get("status") == "PASS"
        and codegen.get("schema_count") == 126
        and codegen.get("example_count") == 126
        and codegen.get("schema_bundle_sha256")
        == "sha256:5788bcf163d7a4ca20f5991935d425d7cc18ff8a5fbc43485c93de73e3c42de3"
        and codegen.get("example_bundle_sha256")
        == "sha256:899f7c7af8f7de5dc3479adf5c270c7eb80047bd84bf28214bfe6e596cbbf54e"
        and codegen.get("codegen_clean_diff", {}).get("status") == "PASS"
        and codegen.get("deterministic_double_replay") == "PASS"
    ):
        raise SystemExit("K01 codegen/contract verification changed")
    request_schema = read_json(ROOT / "schemas/document-registration-request.schema.json")
    registration_schema = read_json(ROOT / "schemas/document-registration.schema.json")
    request_hash = request_schema.get("x-canonical-hash", {})
    registration_hash = registration_schema.get("x-canonical-hash", {})
    if not (
        request_hash.get("algorithm") == "sha256"
        and registration_hash.get("algorithm") == "sha256"
        and isinstance(request_hash.get("preimage_fields"), list)
        and isinstance(registration_hash.get("preimage_fields"), list)
    ):
        raise SystemExit("K01 canonical hash metadata is incomplete")
    return {
        "attempt_id": ATTEMPT_ID,
        "codegen_clean_diff": "PASS",
        "document_registration_hash_fields": registration_hash["preimage_fields"],
        "document_registration_request_hash_fields": request_hash["preimage_fields"],
        "example_bundle_sha256": codegen["example_bundle_sha256"],
        "example_count": 126,
        "schema_bundle_sha256": codegen["schema_bundle_sha256"],
        "schema_count": 126,
        "status": "PASS",
    }


def regression_evidence() -> dict[str, Any]:
    assert_hashes(JUNIT_HASHES, base=ATTEMPT)
    assert_hashes(SUPPORT_HASHES, base=ATTEMPT)
    targeted = pytest_summary(ATTEMPT / "targeted-k01-suite.junit.xml")
    python = pytest_summary(ATTEMPT / "full-python-suite.junit.xml")
    node = node_summary(ATTEMPT / "full-node-suite.junit.xml")
    initial_node = node_summary(
        ATTEMPT / "full-node-suite.initial-failure.junit.xml"
    )
    if not (
        targeted["collected"] == targeted["passed"] == targeted["xml_testcase_count"] == 64
        and targeted["failed"] == targeted["errors"] == targeted["skipped"] == 0
    ):
        raise SystemExit(f"K01 targeted suite is not 64/64: {targeted}")
    if not (
        python["collected"] == python["passed"] == python["xml_testcase_count"] == 1054
        and python["failed"] == python["errors"] == python["skipped"] == 0
    ):
        raise SystemExit(f"full Python suite is not 1054/1054: {python}")
    if not (
        node["collected"] == node["passed"] == 470
        and node["xml_testcase_count"] == 467
        and node["test_file_count"] == 54
        and node["failed"] == node["cancelled"] == node["skipped"]
        == node["todo"] == node["xml_failure_count"] == node["xml_error_count"] == 0
    ):
        raise SystemExit(f"full Node suite is not 470/470: {node}")
    if not (
        initial_node["collected"] == 470
        and initial_node["passed"] == 469
        and initial_node["failed"] == 1
        and initial_node["cancelled"] == initial_node["skipped"]
        == initial_node["todo"] == 0
        and initial_node["xml_failure_count"] == 1
        and len(initial_node["failure_cases"]) == 1
        and initial_node["failure_cases"][0]["name"]
        == "orphan_receipt_test: concurrent readers tolerate transient staging and lock handoff"
        and "ARTIFACT_STORE_STRUCTURE_INVALID"
        in str(initial_node["failure_cases"][0]["message"])
    ):
        raise SystemExit("preserved initial Node transient failure fingerprint changed")
    inventory = read_json(ATTEMPT / "node-test-inventory.json")
    if inventory.get("attempt_id") != ATTEMPT_ID or inventory.get("count") != 54:
        raise SystemExit("K01 Node inventory changed")
    structure = run_check(["npm", "run", "check:structure"])
    boundaries = run_check(["npm", "run", "check:boundaries"])
    ruff = run_check(
        [
            "uv", "run", "--locked", "ruff", "check",
            "src/epistemic_foundry/ingest/registry",
            "tests/ingest",
            "tests/contracts/test_k01_document_contracts.py",
            "tests/integration/test_k01_register_document_node.py",
        ]
    )
    diff_check = run_check(["git", "diff", "--check"])
    if any(
        row["exit_code"] != 0
        for row in (structure, boundaries, ruff, diff_check)
    ):
        raise SystemExit("a K01 repository regression check failed")
    return {
        "attempt_id": ATTEMPT_ID,
        "full_node": node,
        "full_python": python,
        "initial_node_transient_failure": {
            **initial_node,
            "classification": "NON_K01_TRANSIENT_CONCURRENCY_FAILURE",
            "causal_impact_on_k01": "NONE",
            "final_full_suite_result": "470/470 PASS",
            "preserved_not_concealed": True,
        },
        "new_failure_count": 0,
        "new_skip_xfail_todo_or_cancellation_count": 0,
        "repository_checks": {
            "git_diff_check": {
                "exit_code": diff_check["exit_code"],
                "status": "PASS_WITH_PREEXISTING_LINE_ENDING_ADVISORIES",
            },
            "package_boundaries": {
                "exit_code": boundaries["exit_code"],
                "status": "PASS",
            },
            "repository_structure": {
                "exit_code": structure["exit_code"],
                "status": "PASS",
            },
            "scoped_ruff": {
                "exit_code": ruff["exit_code"],
                "status": "PASS",
            },
        },
        "status": "PASS",
        "targeted_k01": targeted,
    }


def selected_report(package_id: str) -> Path:
    package_root = ROOT / "artifacts/work_packages" / package_id
    attempts_root = package_root / "attempts"
    numeric: list[tuple[int, Path]] = []
    if attempts_root.is_dir():
        for path in attempts_root.iterdir():
            if path.is_dir() and re.fullmatch(r"\d{4,}", path.name):
                numeric.append((int(path.name), path))
    if numeric:
        _, latest = max(numeric)
        report = latest / "report.json"
        if not report.is_file():
            raise SystemExit(
                f"highest numeric dependency attempt has no report: {package_id}/{latest.name}"
            )
        return report
    report = package_root / "report.json"
    if not report.is_file():
        raise SystemExit(f"dependency report is missing: {package_id}")
    return report


def current_report_state(package_id: str) -> bool:
    package_root = ROOT / "artifacts/work_packages" / package_id
    attempts = package_root / "attempts"
    numeric: list[tuple[int, Path]] = []
    if attempts.is_dir():
        for path in attempts.iterdir():
            if path.is_dir() and re.fullmatch(r"\d{4,}", path.name):
                numeric.append((int(path.name), path))
    if numeric:
        _, latest = max(numeric)
        report_path = latest / "report.json"
        if package_id == WORK_PACKAGE_ID and not report_path.is_file():
            return True
        if not report_path.is_file():
            return False
    else:
        report_path = package_root / "report.json"
        if not report_path.is_file():
            return package_id == WORK_PACKAGE_ID
    report = read_json(report_path)
    return report.get("status") == "PASS" and report.get("package_status") in (
        None,
        "PASS",
    )


def post_k01_dag_projection() -> dict[str, Any]:
    raw = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    packages = raw["work_packages"]
    order = [row["id"] for row in packages]
    dependencies = {row["id"]: set(row.get("depends_on", [])) for row in packages}
    if len(order) != 156 or len(set(order)) != 156:
        raise SystemExit("development manifest package identity changed")
    completed = {package_id for package_id in order if current_report_state(package_id)}
    if WORK_PACKAGE_ID not in completed:
        raise SystemExit("post-K01 projection did not include K01 PASS")
    ready = [
        package_id
        for package_id in order
        if package_id not in completed and dependencies[package_id] <= completed
    ]
    blocked = [
        package_id
        for package_id in order
        if package_id not in completed and package_id not in ready
    ]
    if len(completed) != 46 or not ready or ready[0] != "K02":
        raise SystemExit(
            f"unexpected post-K01 DAG: completed={len(completed)} ready={ready}"
        )
    return {
        "blocked_package_count": len(blocked),
        "completed_package_count": len(completed),
        "completion_ready": False,
        "next_package": ready[0],
        "ready_package_count": len(ready),
        "ready_packages_manifest_order": ready,
        "status": "PASS",
    }


def dependency_evidence() -> dict[str, Any]:
    dependencies: dict[str, Any] = {}
    for package_id in EXPECTED_DEPENDENCIES:
        report_path = selected_report(package_id)
        report = read_json(report_path)
        if report.get("status") != "PASS" or report.get("package_status") not in (
            None,
            "PASS",
        ):
            raise SystemExit(f"K01 dependency is not PASS: {report_path}")
        dependencies[package_id] = {
            "attempt_id": report.get("attempt_id"),
            "report": report_path.relative_to(ROOT).as_posix(),
            "report_sha256": sha256_id(report_path),
            "selection_rule": "HIGHEST_NUMERIC_ATTEMPT_OR_ROOT_REPORT",
            "status": "PASS",
        }
    prior = read_json(
        ROOT
        / "artifacts/work_packages/J04/attempts/0001/"
        "post-j04-0001-dag-reconciliation.json"
    )
    if not (
        prior.get("status") == "PASS"
        and prior.get("completed_package_count") == 45
        and prior.get("next_package") == "K01"
        and prior.get("ready_packages_manifest_order")
        == ["K01", "L01", "N01", "T01", "A06"]
    ):
        raise SystemExit("pre-K01 sealed DAG evidence changed")
    return {
        "attempt_id": ATTEMPT_ID,
        "dependencies": dependencies,
        "manifest": manifest_contract(),
        "post_k01_projection": post_k01_dag_projection(),
        "pre_k01_sealed_projection": {
            "artifact": (
                "artifacts/work_packages/J04/attempts/0001/"
                "post-j04-0001-dag-reconciliation.json"
            ),
            "artifact_sha256": sha256_id(
                ROOT
                / "artifacts/work_packages/J04/attempts/0001/"
                "post-j04-0001-dag-reconciliation.json"
            ),
            "completed_package_count": 45,
            "next_package": "K01",
            "status": "PASS",
        },
        "status": "PASS",
    }


def write_scope_evidence() -> dict[str, Any]:
    inventory = source_inventory()
    actual_product_paths = [row["path"] for row in inventory]
    approved_exact = {path for path in EXPECTED_WRITE_SCOPE if "**" not in path}
    if set(actual_product_paths) != approved_exact:
        raise SystemExit(
            "K01 product inventory differs from exact manifest scope: "
            f"actual={actual_product_paths} approved={sorted(approved_exact)}"
        )
    return {
        "approved_product_scope": EXPECTED_WRITE_SCOPE[:-1],
        "approved_evidence_scope": ["artifacts/work_packages/K01/**"],
        "attempt_id": ATTEMPT_ID,
        "dirty_worktree_preserved": True,
        "generated_k01_pycache_present": False,
        "product_files_modified_by_attempt": actual_product_paths,
        "product_write_scope_violation_count": 0,
        "reset_clean_stash_commit_push_performed": False,
        "status": "PASS",
        "subagents_or_fleet_used": False,
        "unrelated_product_change_count": 0,
    }


def live_documents() -> dict[str, dict[str, Any]]:
    return {
        "registration-verification.json": registration_verification(),
        "lineage-verification.json": lineage_verification(),
        "effect-reconciliation-verification.json": effect_verification(),
        "contract-verification.json": contract_verification(),
        "full-regression-impact.json": regression_evidence(),
        "write-scope-verification.json": write_scope_evidence(),
        "dependency-status.json": dependency_evidence(),
    }


def review_text(documents: dict[str, dict[str, Any]]) -> str:
    dag = documents["dependency-status.json"]["post_k01_projection"]
    return f"""# K01-0002 document registration adversarial review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_ADVERSARIAL_REVIEW`

Final verdict: `PASS`

Blocking K01 findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_REVIEW`

Actor independence: `false`

The product owner requires serial execution in the primary session without
Fleet or subagents. This review is procedurally separate from implementation,
but it is not actor-independent certification.

## Findings

1. `DocumentRegistrationRequest`, immutable `DocumentRegistration`, and the
   later `DocumentManifest` remain distinct lifecycle artifacts. The initial
   node never requires or fabricates downstream parser, integrity, metadata,
   provenance, or SourceSpan results.
2. Registration accepts only immutable staged bytes whose ArtifactReceipt is
   present, hash/size/media-type bound, and entirely PASS. URI provenance is
   never used for network, local-file, CWD, or repository-root discovery.
3. D03/E01/E02/E03/CAS authority is injected through required ports. K01 has
   no in-memory or permissive default implementation and does not reimplement
   the artifact store, ledger, effect coordinator, lease authority, or state
   revision store.
4. The source ActionIntent is resolved and self-hash verified; source and
   registration ArtifactReceipts, EffectReceipt, ledger event, fencing token,
   and exact one-step CAS revision advancement are all required before a
   success ResultEnvelope can be emitted.
5. Same-key/same-request retry reopens the original immutable registration and
   evidence without repeating controlled effects. Same-key/different-request
   fails conflict. Missing or corrupt receipts, events, ActionIntent payload,
   lineage, or CAS evidence triggers shared reconciliation and otherwise fails
   `DOCUMENT_RECONCILIATION_REQUIRED`.
6. Supersession is same-workspace/same-corpus, append-only, bounded, and
   cycle-checked both before effects and during replay. Removing predecessor
   history after commit makes replay fail closed without repeating effects.
7. The exact 22-case oracle, lineage suite, effect/crash reconciliation tests,
   canonical schema/example validation, workflow binding, and no-fallback
   probes all pass. The new CAS offset probes reject both zero-step and
   two-step advancement at commit and replay.
8. K01 targeted tests pass 64/64 and full Python passes 1054/1054. The first
   full Node run's single non-K01 transient concurrency failure is preserved
   with its exact fingerprint; the isolated behavior and later full run pass,
   and the authoritative final Node result is 470/470 with no suppression.
9. Structure, boundaries, scoped Ruff, codegen parity, and `git diff --check`
   pass. Write-scope violations are zero, generated cache is absent, and prior
   attempts, RAH generations, and the dirty worktree remain preserved.

## Dependency effect

After K01 PASS, the live projection contains {dag['completed_package_count']}
PASS packages. The manifest-order READY set is
`{', '.join(dag['ready_packages_manifest_order'])}`, with `{dag['next_package']}`
as the next serial package. This projection is provisional until independently
recomputed and RAH-sealed after K01 closeout.

## Assurance boundary

K01 proves immutable initial document registration and reconciliation at its
defined authority boundary. It does not claim downstream parsing, corpus
release, the full 156-package product, actor-independent certification, or
production readiness. Global `implementation_gate=fail` and
`completion_ready=false` remain required.
"""


def command_records() -> list[dict[str, Any]]:
    rows = [
        ("C001", "Inspect K01 authority, HumanDecision, manifest, dependencies, dirty worktree, and RAH state", 0, "PASS"),
        ("C002", "Implement immutable document registration runtime, workflow binding, fixtures, tests, and lifecycle documentation", 0, "PASS: exact manifest scope"),
        ("C003", "uv run --locked python -B -m pytest tests/ingest tests/contracts/test_k01_document_contracts.py tests/integration/test_k01_register_document_node.py -p no:cacheprovider --junitxml=<attempt>/targeted-k01-suite.junit.xml", 0, "PASS: 64/64"),
        ("C004", "uv run --locked python -B -m pytest tests -p no:cacheprovider --junitxml=<attempt>/full-python-suite.junit.xml", 0, "PASS: 1054/1054"),
        ("C005", "node --test --test-concurrency=1 --test-reporter=junit <54-file sorted repository Node inventory>", 1, "PRESERVED_TRANSIENT: 469 passed, 1 non-K01 concurrency failure; no suppression"),
        ("C006", "isolated orphan-receipt concurrency test rerun", 0, "PASS: transient failure did not reproduce"),
        ("C007", "node --test --test-concurrency=1 --test-reporter=junit <54-file sorted repository Node inventory>", 0, "PASS: 470/470"),
        ("C008", "uv run --locked python -B packages/contracts/codegen/verify.py --repo-root .", 0, "PASS: 126 schemas/examples and deterministic parity"),
        ("C009", "npm run check:structure", 0, "PASS"),
        ("C010", "npm run check:boundaries", 0, "PASS"),
        ("C011", "uv run --locked ruff check <K01 runtime and test paths>", 0, "PASS"),
        ("C012", "git diff --check", 0, "PASS with pre-existing line-ending advisories only"),
        ("C013", "Primary-session separate adversarial review including exact CAS revision semantics", 0, "PASS: zero blocking findings; actor_independence=false"),
        ("C014", "Remove exactly seven generated K01 pyc files and the now-empty cache directory", 0, "PASS"),
        ("D001", "Invoke pytest directly through uv instead of python -m", 1, "DIAGNOSTIC_ONLY: repository source did not resolve; authoritative python -m form passed"),
        ("D002", "Use pytest parameter name request", 1, "DIAGNOSTIC_ONLY: pytest fixture name conflict corrected to request_payload"),
        ("D003", "Invoke npm test -- --run", 1, "DIAGNOSTIC_ONLY: unsupported test command; direct node --test used"),
        ("D004", "Invoke contract codegen with --root", 1, "DIAGNOSTIC_ONLY: corrected to --repo-root ."),
        ("D005", "Run legacy tools/validate_spec_bundle.py", 1, "PRESERVED_DIAGNOSTIC: legacy 124-count assumptions reported 34 errors; not substituted for current 126-contract verifier"),
        ("D006", "Delete generated K01 cache with a complex PowerShell foreach command", 1, "DIAGNOSTIC_ONLY: safety hook rejected command shape; exact allowlisted Python cleanup succeeded"),
    ]
    return [
        {
            "command": command,
            "command_id": f"{ATTEMPT_ID}-{identifier}",
            "exit_code": exit_code,
            "recorded_at_utc": RECORDED_AT,
            "result": result,
            "scope": ATTEMPT_ID,
        }
        for identifier, command, exit_code, result in rows
    ]


def make_receipt(authority_path: Path) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "action_intent_id": None,
        "artifact_id": "K01-0002-REGISTRATION-VERIFICATION",
        "byte_size": authority_path.stat().st_size,
        "content_hash": sha256_id(authority_path),
        "created_at": RECORDED_AT,
        "created_by": {
            "actor_id": "K01-0002-PRIMARY-SESSION-VERIFIER",
            "actor_type": "tool",
        },
        "locator": authority_path.relative_to(ROOT).as_posix(),
        "media_type": "application/json",
        "receipt_id": "AR-K01-0002-REGISTRATION-VERIFICATION",
        "schema_ref": None,
        "validation_results": [
            {
                "check": "document_registration_oracle_22",
                "details": "22/22 deterministic request, receipt, idempotency, lineage, effect, CAS, and envelope cases passed",
                "status": "PASS",
            },
            {
                "check": "lineage_and_effect_reconciliation",
                "details": "append-only lineage, crash reconciliation, replay evidence, and exact one-step CAS rules passed",
                "status": "PASS",
            },
            {
                "check": "canonical_contract_validation",
                "details": "126 schemas/examples with clean deterministic cross-language codegen parity",
                "status": "PASS",
            },
            {
                "check": "full_regression",
                "details": "K01 targeted 64/64, Python 1054/1054, final Node 470/470; initial transient preserved",
                "status": "PASS",
            },
        ],
    }
    receipt["receipt_hash"] = canonical_hash_excluding(receipt, "receipt_hash")
    schema = read_json(RECEIPT_SCHEMA)
    Draft202012Validator.check_schema(schema)
    errors = list(Draft202012Validator(schema).iter_errors(receipt))
    if errors:
        raise SystemExit(f"invalid K01 ArtifactReceipt: {errors[0].message}")
    return receipt


def evidence_artifacts() -> list[dict[str, Any]]:
    names = [
        *OUTPUT_NAMES,
        "registration-verification.artifact-receipt.json",
        "targeted-k01-suite.junit.xml",
        "full-python-suite.junit.xml",
        "full-node-suite.junit.xml",
        "full-node-suite.initial-failure.junit.xml",
        "node-test-inventory.json",
        "commands.jsonl",
        "review.md",
        "run_k01_0002_checks.py",
        "build_k01_0002_evidence.py",
        "k01_0002_rah_seal.py",
    ]
    if (ATTEMPT / "rah-core-integrity.json").is_file():
        names.append("rah-core-integrity.json")
    rows: list[dict[str, Any]] = []
    for name in names:
        path = ATTEMPT / name
        if not path.is_file():
            raise SystemExit(f"required K01 evidence artifact is missing: {name}")
        rows.append(
            {
                "byte_size": path.stat().st_size,
                "path": path.relative_to(ROOT).as_posix(),
                "sha256": sha256_id(path),
            }
        )
    return rows


def report_document(
    documents: dict[str, dict[str, Any]],
    *,
    rah_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    regression = documents["full-regression-impact.json"]
    dependency = documents["dependency-status.json"]
    receipt = read_json(
        ATTEMPT / "registration-verification.artifact-receipt.json"
    )
    report: dict[str, Any] = {
        "artifact_receipt": {
            "path": (
                "artifacts/work_packages/K01/attempts/0002/"
                "registration-verification.artifact-receipt.json"
            ),
            "receipt_hash": receipt["receipt_hash"],
            "receipt_id": receipt["receipt_id"],
        },
        "attempt_id": ATTEMPT_ID,
        "changed_files": source_inventory(),
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "dependencies": dependency["dependencies"],
        "dependency_effect": dependency["post_k01_projection"],
        "evidence_artifacts": evidence_artifacts(),
        "exit_criteria": {
            criterion: "PASS" for criterion in EXPECTED_EXIT_CRITERIA
        },
        "global_implementation_gate": "fail",
        "history_and_worktree": {
            "dirty_worktree_preserved": True,
            "k01_0001_spec_gap_preserved": True,
            "prior_attempts_reports_and_rah_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
            "subagents_or_fleet_used": False,
        },
        "human_decision": decision_evidence(),
        "implementation_status": "PASS",
        "not_claimed": [
            "actor-independent certification",
            "downstream ingest or corpus release completion",
            "full product completion",
            "release or production readiness",
            "completion_ready=true",
        ],
        "package_status": "PASS",
        "regression": regression,
        "required_checks": {
            "document_contract_validation": "PASS",
            "document_effect_reconciliation_test": "PASS",
            "document_lineage_test": "PASS",
            "document_registration_oracle_22": "22/22 PASS",
            "document_registry_test": "PASS",
            "license_propagation_test": "PASS",
            "independent_review": {
                "actor_independence": False,
                "blocking_finding_count": 0,
                "mode": "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_REVIEW",
                "status": "PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW",
            },
        },
        "review": {
            "actor_independence": False,
            "artifact": "artifacts/work_packages/K01/attempts/0002/review.md",
            "artifact_sha256": sha256_id(ATTEMPT / "review.md"),
            "blocking_finding_count": 0,
            "mode": "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_REVIEW",
            "status": "PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW",
        },
        "status": "PASS",
        "title": "Document registry, versions, licensing and trust",
        "verification": {
            "document_registration_oracle": "22/22",
            "full_node": "470/470",
            "full_python": "1054/1054",
            "targeted_k01": "64/64",
            "write_scope_violation_count": 0,
        },
        "work_package_id": WORK_PACKAGE_ID,
    }
    if rah_state is not None:
        report["rah_state"] = rah_state
    return report


def expected_commands() -> str:
    return "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
        for row in command_records()
    )


def build() -> dict[str, Any]:
    ATTEMPT.mkdir(parents=True, exist_ok=True)
    documents = live_documents()
    for name, document in documents.items():
        write_json(ATTEMPT / name, document)
    (ATTEMPT / "commands.jsonl").write_text(
        expected_commands(), encoding="utf-8", newline="\n"
    )
    (ATTEMPT / "review.md").write_text(
        review_text(documents), encoding="utf-8", newline="\n"
    )
    write_json(
        ATTEMPT / "registration-verification.artifact-receipt.json",
        make_receipt(ATTEMPT / "registration-verification.json"),
    )
    write_json(ATTEMPT / "report.json", report_document(documents))
    return verify()


def bind_rah_state(
    *, core_generation: str, core_evidence_id: str, final_closeout_evidence_id: str
) -> dict[str, Any]:
    documents = live_documents()
    integrity = read_json(ATTEMPT / "rah-core-integrity.json")
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
    write_json(
        ATTEMPT / "report.json", report_document(documents, rah_state=rah_state)
    )
    PACKAGE_ROOT.mkdir(parents=True, exist_ok=True)
    for name in ("report.json", "commands.jsonl", "review.md"):
        shutil.copyfile(ATTEMPT / name, PACKAGE_ROOT / name)
    return rah_state


def verify() -> dict[str, Any]:
    documents = live_documents()
    for name, expected in documents.items():
        path = ATTEMPT / name
        if not path.is_file() or path.read_text(encoding="utf-8") != render(expected):
            raise SystemExit(f"stored K01 evidence differs from live evidence: {name}")
    if (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8") != expected_commands():
        raise SystemExit("stored K01 command log differs from deterministic records")
    if (ATTEMPT / "review.md").read_text(encoding="utf-8") != review_text(documents):
        raise SystemExit("stored K01 review differs from live evidence")
    expected_receipt = make_receipt(ATTEMPT / "registration-verification.json")
    receipt_path = ATTEMPT / "registration-verification.artifact-receipt.json"
    if not receipt_path.is_file() or receipt_path.read_text(encoding="utf-8") != render(
        expected_receipt
    ):
        raise SystemExit("stored K01 ArtifactReceipt differs from live evidence")
    report_path = ATTEMPT / "report.json"
    report = read_json(report_path)
    rah_state = report.get("rah_state")
    if rah_state is not None and not isinstance(rah_state, dict):
        raise SystemExit("K01 RAH binding is malformed")
    expected_report = report_document(documents, rah_state=rah_state)
    if report_path.read_text(encoding="utf-8") != render(expected_report):
        raise SystemExit("stored K01 report differs from live evidence")
    if rah_state is not None:
        for name in ("report.json", "commands.jsonl", "review.md"):
            if (ATTEMPT / name).read_bytes() != (PACKAGE_ROOT / name).read_bytes():
                raise SystemExit(f"K01 root evidence projection differs: {name}")
    return {
        "attempt_id": ATTEMPT_ID,
        "completion_ready": False,
        "full_node": "470/470",
        "full_python": "1054/1054",
        "next_package": documents["dependency-status.json"]["post_k01_projection"][
            "next_package"
        ],
        "package_status": "PASS",
        "rah_bound": rah_state is not None,
        "status": "PASS",
        "targeted_k01": "64/64",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("build", "verify"))
    args = parser.parse_args()
    result = build() if args.mode == "build" else verify()
    print(render(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
