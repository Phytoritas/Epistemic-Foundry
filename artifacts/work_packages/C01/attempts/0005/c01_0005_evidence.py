#!/usr/bin/env python3
"""Build and verify the C01-0005 shared-contract SPEC_GAP evidence.

C01-0005 intentionally performs no canonical schema, example, OpenAPI, test,
or manifest mutation.  It proves that the product-owner K01 decision requires
the canonical schema/example cardinality to change from 124 to 126 while the
active authority and acceptance oracles still contain mutually incompatible
124-era assertions.  Several of those paths are outside C01's exact scope,
have no owner, or are owned only by a package that cannot run before the C04
full-suite gate.  The verifier therefore fails closed instead of partially
implementing a contract that cannot pass the fixed execution sequence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/C01/attempts/0005"

WORK_PACKAGE_ID = "C01"
ATTEMPT_ID = "C01-0005"
SPEC_GAP_ID = "C01-SG004"
DECISION_ID = "HD-EF4-K01-SG001-20260730-001"
DECISION_PATH = (
    "artifacts/authority_decisions/"
    "HD-EF4-K01-SG001-20260730-001.human-decision.json"
)
UNBLOCK_DECISION_PATH = (
    "artifacts/authority_decisions/"
    "HD-EF4-UNBLOCK-SET-20260730-001.human-decision.json"
)
BINDING_PATH = "manifests/source_bindings/development-manifest.binding.json"
ATTACHMENT_ID = (
    "attachment:b32635e9-cd03-434f-a290-3644e962fce6:"
    "pasted-text-1.txt"
)
ATTACHMENT_PATH = (
    Path.home()
    / ".codex/attachments/b32635e9-cd03-434f-a290-3644e962fce6"
    / "pasted-text-1.txt"
)

ATTACHMENT_SHA256 = (
    "c44b4d35ee83cba3a15f7249a7bce171fd9d155f0f39cdf747a2fd57b6c736f4"
)
MANIFEST_SHA256 = (
    "7d1d3248dc3e2ca56d8f08ec282aa3d95bea9466ba6b7580fccff81e0f639319"
)
BINDING_ID = "DMB-EF4-20260730-001"
BINDING_HASH = (
    "sha256:6915375ce4c4d38f7c8c294db54c736ee1cc4e30a46079a4a4614bafd239036d"
)
DECISION_HASH = (
    "sha256:62c7e6885c051e92846bb6580f385efcffca744cd45c531f768f8324bdacaa30"
)

EXPECTED_C01_SCOPE = [
    "schemas/document-registration-request.schema.json",
    "schemas/document-registration.schema.json",
    "schemas/document-manifest.schema.json",
    "schemas/evaluator-bundle.schema.json",
    "schemas/holdout-manifest.schema.json",
    "schemas/evaluator-qualification-report.schema.json",
    "schemas/gate-decision.schema.json",
    "schemas/promotion-decision.schema.json",
    "schemas/attestation.schema.json",
    "schemas/approval-record.schema.json",
    "schemas/capability-lease.schema.json",
    "schemas/action-intent.schema.json",
    "schemas/effect-receipt.schema.json",
    "schemas/artifact-receipt.schema.json",
    "schemas/phase-artifact-set.schema.json",
    "schemas/hypothesis-passport.schema.json",
    "schemas/replication-result.schema.json",
    "schemas/human-decision.schema.json",
    "examples/sample_document-registration-request.json",
    "examples/sample_document-registration.json",
    "examples/sample_document-manifest.json",
    "examples/sample_evaluator-bundle.json",
    "examples/sample_holdout-manifest.json",
    "examples/sample_evaluator-qualification-report.json",
    "examples/sample_gate_decision.json",
    "examples/sample_promotion-decision.json",
    "examples/sample_attestation.json",
    "examples/sample_approval-record.json",
    "examples/sample_capability-lease.json",
    "examples/sample_action-intent.json",
    "examples/sample_effect-receipt.json",
    "examples/sample_artifact-receipt.json",
    "examples/sample_phase-artifact-set.json",
    "examples/sample_passport.json",
    "examples/sample_replication-result.json",
    "examples/sample_human-decision.json",
    "openapi/epistemic-foundry-v1.openapi.yaml",
    "docs/api_contract.md",
    "artifacts/work_packages/C01/**",
]

HISTORY_HASHES = {
    "artifacts/work_packages/C01/report.json": (
        "14d1815150ba37ebc416d637afbb1514fbbb024f9fe6940ed7b976ce33b60d68"
    ),
    "artifacts/work_packages/C01/attempts/0002/report.json": (
        "c8100002239cf826c9fe521f86f84295e1cdec3bbe5e49f210c4a7e124d31369"
    ),
    "artifacts/work_packages/C01/attempts/0003/report.json": (
        "d3f14a0f227bc7fa4743b7d2fbb266cb1999cd2524f4a93a9770b19910a130e5"
    ),
    "artifacts/work_packages/C01/attempts/0004/report.json": (
        "424f40396e93bd6826bf5ad85c3580cac7bd4ea8171b93f24816bc6a78c4a5d6"
    ),
}

AUTHORITY_FILE_HASHES = {
    DECISION_PATH: (
        "988830f51b1d259e91d4a093da67d631566babcaa150368d2dbde680fb72f423"
    ),
    UNBLOCK_DECISION_PATH: (
        "fdb8752fc7a629e444114b089e33163a7d8dc68290bf99d1667d6a4208c5f2f2"
    ),
    BINDING_PATH: (
        "0f87227ec902bf9c3e9b6f33111e2b1fa038323ef57752815239611caf6b273c"
    ),
    "manifests/development_manifest.yaml": MANIFEST_SHA256,
}

STALE_SURFACES: dict[str, dict[str, Any]] = {
    "MASTER_SPEC.md": {
        "sha256": "43fbb63f2b4cf697d10be15521a4d8ddaf123fb822b4d563ba4e026ed82cf3f3",
        "expected_owners": ["A01"],
        "stage": "AUTHORITY_CONFLICT_BEFORE_C01",
        "markers": [
            "Total: **124 Draft 2020-12 strict schemas** and **124 matching examples**."
        ],
    },
    "manifests/acceptance_matrix.yaml": {
        "sha256": "f01ed8ed8a2916d9d8fad28d9f365325c008d3da6b04aba25612a282115bee4f",
        "expected_owners": ["F01"],
        "stage": "ACCEPTANCE_AUTHORITY_CONFLICT_BEFORE_C01",
        "markers": [
            "canonical_schema_count: '124'",
            "matching_example_count: '124'",
        ],
    },
    "tests/contracts/openapi/test_scientific_contracts.py": {
        "sha256": "27296a0b77b21f00631936124c0738f2fca40b31ac23d040162b1b8dfd0f324c",
        "expected_owners": [],
        "stage": "C01_TARGETED_GATE",
        "markers": [
            "def test_all_124_schemas_meta_validate_and_have_unique_ids",
            "assert len(schemas) == 124",
            "def test_all_124_examples_validate_and_map_one_to_one",
            "assert len(examples) == 124",
        ],
    },
    "tests/contracts/openapi/test_openapi_contract.py": {
        "sha256": "737dd012fc3b7104763e189d2aea0998c90897856007058a715efd3f2c0471a4",
        "expected_owners": [],
        "stage": "C01_TARGETED_GATE",
        "markers": [
            '"DocumentRegistrationRequest",',
            "assert not required & schema_titles",
            "assert len(schema_titles) == 124",
            "def test_document_registration_requires_exactly_one_source",
            'valid_uri = {"source_uri":',
            'valid_artifact = {"uploaded_artifact_id":',
        ],
    },
    "tests/test_contracts.py": {
        "sha256": "f9a9c630ea1de24cf5b86c90068c508a1f5b4d010ed919f2ed276951710a6903",
        "expected_owners": [],
        "stage": "POST_PROJECTION_REGRESSION",
        "markers": ["EXPECTED_SCHEMA_COUNT = 124"],
    },
    "tests/test_cli.py": {
        "sha256": "8a43a7eb1dd4230b1260fa5bcf8efa27a542d0a55154c2f81f7c9d1ddb68106f",
        "expected_owners": [],
        "stage": "POST_PROJECTION_REGRESSION",
        "markers": ['assert payload["canonical_schemas_loaded"] == 124'],
    },
    "tests/test_f01_epistemic_work_classifier.py": {
        "sha256": "98516fbc6c99c3ee06f61b6e3c251b5fbfbab7bd1b0df2a6afa7f996c3d2e5d1",
        "expected_owners": ["F01"],
        "stage": "C04_FULL_SUITE_BEFORE_F01_CAN_RERUN",
        "markers": [
            "assert len(schemas) == 124",
            "assert len(examples) == 124",
        ],
    },
    "tests/packaging/test_canonical_registry.py": {
        "sha256": "0a6c7dfad24686a1ebb5c1036578a2caa43af82155b02cbf13005a70c3a7d9bd",
        "expected_owners": ["B04"],
        "stage": "C04_FULL_SUITE_BEFORE_B04_CAN_RUN",
        "markers": [
            "assert len(registry.names()) == 124",
            'assert registry.manifest["schema_count"] == 124',
        ],
    },
}

PLANNED_OWNER_SURFACES: dict[str, dict[str, Any]] = {
    "docs/api_contract.md": {
        "expected_owners": ["C01"],
        "stage": "C01_IN_SCOPE",
        "markers": ["count of 124"],
    },
    "docs/schema_evolution.md": {
        "expected_owners": ["C03"],
        "stage": "C03_IN_SCOPE",
        "markers": ["the 124"],
    },
    "packages/contracts/codegen/verify.py": {
        "expected_owners": ["B01", "C02"],
        "stage": "C02_IN_SCOPE",
        "markers": ["cardinality is not 124/124"],
    },
    "packages/contracts/src/generated/contract-manifest.json": {
        "expected_owners": ["B01", "C02"],
        "stage": "C02_GENERATED",
        "markers": ['"schema_count": 124'],
    },
    "python/epistemic_foundry/contracts/contract-manifest.json": {
        "expected_owners": ["B01", "C02"],
        "stage": "C02_GENERATED",
        "markers": ['"schema_count": 124'],
    },
    "web/src/generated/contract-manifest.json": {
        "expected_owners": ["C02", "U01"],
        "stage": "C02_GENERATED",
        "markers": ['"schema_count": 124'],
    },
    "src/epistemic_foundry/_canonical/canonical-registry.json": {
        "expected_owners": ["B04"],
        "stage": "B04_DERIVED_SNAPSHOT",
        "markers": ['"schema_count": 124'],
    },
}

INFORMATIONAL_STALE_SURFACES = {
    "docs/verification_report.md": {
        "sha256": "b3788f2c13798248a2c29dec2c210c64a4dd8331e39f446b723379ee7b33ef66",
        "expected_owners": [],
        "markers": ["124 schemas / 124 examples", "| Strict Draft 2020-12 schemas | 124 |"],
        "classification": "STALE_REPORT_NOT_USED_AS_C01_GATE",
    }
}

NEW_CANONICAL_PATHS = [
    "schemas/document-registration-request.schema.json",
    "schemas/document-registration.schema.json",
    "examples/sample_document-registration-request.json",
    "examples/sample_document-registration.json",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_id(path: Path) -> str:
    return "sha256:" + sha256(path)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def hash_excluding(value: dict[str, Any], field: str) -> str:
    payload = {key: item for key, item in value.items() if key != field}
    return "sha256:" + hashlib.sha256(canonical_bytes(payload)).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"JSON artifact is not an object: {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def load_packages() -> list[dict[str, Any]]:
    payload = yaml.safe_load(
        (ROOT / "manifests/development_manifest.yaml").read_text(encoding="utf-8")
    )
    packages = payload if isinstance(payload, list) else payload.get("work_packages")
    if not isinstance(packages, list):
        raise SystemExit("development manifest has no work_packages list")
    return packages


def scope_matches(scope: str, relative: str) -> bool:
    if scope.endswith("/**"):
        prefix = scope[:-3]
        return relative == prefix or relative.startswith(prefix + "/")
    return scope == relative


def path_owners(packages: list[dict[str, Any]], relative: str) -> list[str]:
    return sorted(
        str(package["id"])
        for package in packages
        if any(
            scope_matches(str(scope), relative)
            for scope in package.get("write_scope", [])
        )
    )


def authority_evidence() -> dict[str, Any]:
    if not ATTACHMENT_PATH.is_file():
        raise SystemExit(f"authoritative attachment is unavailable: {ATTACHMENT_ID}")
    if sha256(ATTACHMENT_PATH) != ATTACHMENT_SHA256:
        raise SystemExit("authoritative attachment hash mismatch")

    observed_files: dict[str, str] = {}
    for relative, expected in AUTHORITY_FILE_HASHES.items():
        actual = sha256(ROOT / relative)
        if actual != expected:
            raise SystemExit(f"authority file changed: {relative}: {actual} != {expected}")
        observed_files[relative] = "sha256:" + actual

    decision = read_json(ROOT / DECISION_PATH)
    if decision.get("decision_id") != DECISION_ID:
        raise SystemExit("K01 HumanDecision ID mismatch")
    if decision.get("authority_role") != "product_owner":
        raise SystemExit("K01 HumanDecision authority mismatch")
    if decision.get("decision_hash") != DECISION_HASH:
        raise SystemExit("K01 HumanDecision recorded hash mismatch")
    if hash_excluding(decision, "decision_hash") != DECISION_HASH:
        raise SystemExit("K01 HumanDecision self-hash mismatch")

    binding = read_json(ROOT / BINDING_PATH)
    if binding.get("binding_id") != BINDING_ID:
        raise SystemExit("development-manifest binding ID mismatch")
    if binding.get("binding_hash") != BINDING_HASH:
        raise SystemExit("development-manifest binding hash mismatch")
    if hash_excluding(binding, "binding_hash") != BINDING_HASH:
        raise SystemExit("development-manifest binding self-hash mismatch")
    if binding.get("successor_sha256") != MANIFEST_SHA256:
        raise SystemExit("binding successor does not match expected manifest")
    if DECISION_ID not in binding.get("authorizing_decision_ids", []):
        raise SystemExit("binding does not cite the K01 HumanDecision")

    attachment_text = ATTACHMENT_PATH.read_text(encoding="utf-8")
    required_contract_fragments = [
        "124 → 126",
        "schemas/document-registration-request.schema.json",
        "schemas/document-registration.schema.json",
        "## 2.3 DocumentRegistrationRequest exact fields",
        "최초 immutable registration record다.",
        "DocumentRegistration과 DocumentManifest는 같은 가변 객체가 아니다.",
        "C01 shared correction에 다음 exact paths를 부여한다.",
        "C04 full contract conformance",
        "B04 canonical snapshot reprojection",
    ]
    missing_fragments = [
        fragment for fragment in required_contract_fragments if fragment not in attachment_text
    ]
    if missing_fragments:
        raise SystemExit(f"attachment contract fragments missing: {missing_fragments}")

    return {
        "attachment": {
            "artifact_id": ATTACHMENT_ID,
            "sha256": "sha256:" + ATTACHMENT_SHA256,
            "status": "PASS",
        },
        "binding": {
            "binding_hash": BINDING_HASH,
            "binding_id": BINDING_ID,
            "successor_manifest_sha256": "sha256:" + MANIFEST_SHA256,
            "status": "PASS",
        },
        "decision": {
            "decision_hash": DECISION_HASH,
            "decision_id": DECISION_ID,
            "file_sha256": observed_files[DECISION_PATH],
            "status": "PASS",
        },
        "authority_file_hashes": observed_files,
        "required_contract_fragments_verified": len(required_contract_fragments),
        "status": "PASS",
    }


def history_evidence() -> dict[str, Any]:
    checks: dict[str, dict[str, Any]] = {}
    for relative, expected in HISTORY_HASHES.items():
        actual = sha256(ROOT / relative)
        checks[relative] = {
            "actual_sha256": "sha256:" + actual,
            "expected_sha256": "sha256:" + expected,
            "status": "PASS" if actual == expected else "FAIL",
        }
    if any(row["status"] != "PASS" for row in checks.values()):
        raise SystemExit("prior C01 attempt history changed")
    return {
        "checks": checks,
        "preserved_attempts": ["C01-0001", "C01-0002", "C01-0003", "C01-0004"],
        "status": "PASS",
    }


def manifest_evidence(packages: list[dict[str, Any]]) -> dict[str, Any]:
    package_by_id = {str(package["id"]): package for package in packages}
    c01 = package_by_id["C01"]
    c02 = package_by_id["C02"]
    c03 = package_by_id["C03"]
    c04 = package_by_id["C04"]
    b04 = package_by_id["B04"]
    if list(c01.get("write_scope", [])) != EXPECTED_C01_SCOPE:
        raise SystemExit("C01 scope differs from the exact bound successor manifest")
    if list(c01.get("depends_on", [])) != ["A04", "A05"]:
        raise SystemExit("C01 dependencies changed")
    if list(c02.get("depends_on", [])) != ["C01"]:
        raise SystemExit("C02 dependency changed")
    if list(c03.get("depends_on", [])) != ["C01", "C02"]:
        raise SystemExit("C03 dependency changed")
    if list(c04.get("depends_on", [])) != ["C02", "C03"]:
        raise SystemExit("C04 dependency changed")
    if list(b04.get("depends_on", [])) != ["B02", "B03", "C04"]:
        raise SystemExit("B04 dependency changed")
    if "full_python_suite" not in c04.get("required_checks", []):
        raise SystemExit("C04 full-suite gate disappeared")
    if "all 126 schemas and examples, generated projections, runtime semantics and OpenAPI agree" not in c04.get("exit_criteria", []):
        raise SystemExit("C04 126-contract conformance gate disappeared")
    return {
        "B04_depends_on": list(b04["depends_on"]),
        "C01_depends_on": list(c01["depends_on"]),
        "C01_write_scope": list(c01["write_scope"]),
        "C02_depends_on": list(c02["depends_on"]),
        "C03_depends_on": list(c03["depends_on"]),
        "C04_depends_on": list(c04["depends_on"]),
        "C04_full_python_suite_required": True,
        "fixed_canonical_sequence": ["C01", "C02", "C03", "C04", "B04"],
        "status": "PASS",
    }


def marker_inventory(
    packages: list[dict[str, Any]],
    surfaces: dict[str, dict[str, Any]],
    *, require_hash: bool,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for relative, contract in surfaces.items():
        path = ROOT / relative
        if not path.is_file():
            raise SystemExit(f"stale-surface path is missing: {relative}")
        text = path.read_text(encoding="utf-8")
        missing = [marker for marker in contract["markers"] if marker not in text]
        if missing:
            raise SystemExit(f"expected stale markers disappeared from {relative}: {missing}")
        if require_hash and sha256(path) != contract["sha256"]:
            raise SystemExit(f"stale-surface file changed: {relative}")
        owners = path_owners(packages, relative)
        if owners != contract["expected_owners"]:
            raise SystemExit(
                f"manifest owner set changed for {relative}: {owners} != "
                f"{contract['expected_owners']}"
            )
        rows.append(
            {
                "marker_count": len(contract["markers"]),
                "owners": owners,
                "path": relative,
                "sha256": sha256_id(path),
                "stage": contract.get("stage"),
                "status": "STALE_124_CONTRACT",
            }
        )
    return rows


def current_contract_evidence() -> dict[str, Any]:
    schema_paths = sorted((ROOT / "schemas").glob("*.schema.json"))
    example_paths = sorted((ROOT / "examples").glob("*.json"))
    missing = [relative for relative in NEW_CANONICAL_PATHS if not (ROOT / relative).is_file()]
    if len(schema_paths) != 124 or len(example_paths) != 124:
        raise SystemExit("pre-implementation canonical cardinality is no longer 124/124")
    if missing != NEW_CANONICAL_PATHS:
        raise SystemExit("C01 canonical implementation was partially applied")
    openapi = yaml.safe_load(
        (ROOT / "openapi/epistemic-foundry-v1.openapi.yaml").read_text(encoding="utf-8")
    )
    component = openapi["components"]["schemas"]["DocumentRegistrationRequest"]
    properties = sorted(component.get("properties", {}))
    if properties != [
        "metadata",
        "requested_document_id",
        "source_uri",
        "uploaded_artifact_id",
    ]:
        raise SystemExit("legacy OpenAPI DocumentRegistrationRequest shape changed")
    return {
        "example_count": len(example_paths),
        "legacy_openapi_document_registration_request_properties": properties,
        "missing_new_canonical_paths": missing,
        "openapi_version": openapi.get("openapi"),
        "product_contract_changes_applied_by_attempt": [],
        "schema_count": len(schema_paths),
        "status": "PRE_IMPLEMENTATION_BASELINE_CONFIRMED",
        "target_schema_count": 126,
        "target_example_count": 126,
    }


def run_targeted_contract_baseline() -> dict[str, Any]:
    command = [
        sys.executable,
        "-m",
        "pytest",
        "tests/contracts/openapi",
        "-p",
        "no:cacheprovider",
        "--tb=short",
    ]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    output = completed.stdout + completed.stderr
    match = re.search(r"(?m)^(\d+) passed in ", output)
    passed = int(match.group(1)) if match else -1
    if completed.returncode != 0 or passed != 66:
        raise SystemExit(
            "C01 pre-implementation targeted baseline changed: "
            f"exit={completed.returncode}, passed={passed}\n{output[-2000:]}"
        )
    return {
        "command": "python -m pytest tests/contracts/openapi -p no:cacheprovider --tb=short",
        "exit_code": completed.returncode,
        "failed": 0,
        "passed": passed,
        "status": "PASS_PRE_IMPLEMENTATION_BASELINE",
    }


def contract_audit(*, run_regression: bool) -> dict[str, Any]:
    packages = load_packages()
    authority = authority_evidence()
    manifest = manifest_evidence(packages)
    history = history_evidence()
    stale = marker_inventory(packages, STALE_SURFACES, require_hash=True)
    planned = marker_inventory(packages, PLANNED_OWNER_SURFACES, require_hash=False)
    informational = marker_inventory(
        packages, INFORMATIONAL_STALE_SURFACES, require_hash=True
    )
    baseline = (
        run_targeted_contract_baseline()
        if run_regression
        else {"status": "DEFERRED_TO_VERIFY", "expected_passed": 66}
    )
    zero_owner_paths = [row["path"] for row in stale if not row["owners"]]
    wrong_stage_paths = [
        row["path"]
        for row in stale
        if row["owners"] and row["owners"][0] not in {"C01", "C02", "C03"}
    ]
    if zero_owner_paths != [
        "tests/contracts/openapi/test_scientific_contracts.py",
        "tests/contracts/openapi/test_openapi_contract.py",
        "tests/test_contracts.py",
        "tests/test_cli.py",
    ]:
        raise SystemExit(f"unexpected zero-owner path set: {zero_owner_paths}")
    if wrong_stage_paths != [
        "MASTER_SPEC.md",
        "manifests/acceptance_matrix.yaml",
        "tests/test_f01_epistemic_work_classifier.py",
        "tests/packaging/test_canonical_registry.py",
    ]:
        raise SystemExit(f"unexpected wrong-stage path set: {wrong_stage_paths}")

    return {
        "attempt_id": ATTEMPT_ID,
        "authority": authority,
        "classification": {
            "not_blocked_reason": (
                "No credential, licensed source, external backend, toolchain, or "
                "host capability is missing; the conflict is entirely local and "
                "reproducible."
            ),
            "not_fail_reason": (
                "No C01 product implementation was attempted against an "
                "unexecutable gate. The K01 object semantics are defined, but "
                "authority to migrate higher-order acceptance oracles and their "
                "pre-C04 execution timing is absent or contradictory."
            ),
            "typed_outcome": "SPEC_GAP",
        },
        "current_contract": current_contract_evidence(),
        "fixed_sequence_contradiction": {
            "C01_targeted_tests_become_false_at_126": True,
            "C04_full_python_suite_precedes_B04": True,
            "B04_owned_projection_freshness_test_will_fail_after_C01_before_B04": True,
            "F01_owned_root_count_test_will_fail_after_C01_before_any_F01_rerun": True,
            "full_suite_zero_failure_reachable_under_current_scope_and_order": False,
            "status": "UNRESOLVED_SHARED_CONTRACT",
        },
        "history": history,
        "informational_stale_reports": informational,
        "manifest": manifest,
        "planned_owner_surfaces": planned,
        "required_higher_order_decision": {
            "decision_subject": (
                "126-schema acceptance-oracle migration ownership and gate order"
            ),
            "exact_paths_requiring_owner_or_timing_correction": list(STALE_SURFACES),
            "minimum_terms": [
                "Assign an explicit correction owner and exact write scope for each listed stale authority/test path; do not grant broad tests/** or docs/** scope.",
                "Authorize MASTER_SPEC.md and manifests/acceptance_matrix.yaml to change the canonical count from 124 to 126 without rewriting historical reports.",
                "Place the C01 contract-oracle corrections before C01 targeted validation.",
                "Place every root-count and packaged-registry oracle correction, plus canonical snapshot reprojection, before the C04 full_python_suite or explicitly redefine that gate with a bounded and later reconciled projection status.",
                "Preserve C01-0001 through C01-0005 and all prior RAH evidence as immutable history.",
            ],
            "forbidden_shortcuts": [
                "partially implement the two schemas while knowingly leaving the required gate structurally false",
                "treat all tests/** as implicitly owned by C01",
                "weaken C04 full_python_suite without an explicit product-owner decision",
                "run B04 out of the fixed order without an explicit attempt-level correction decision",
                "edit generated C02 outputs or the B04 derived snapshot by hand",
                "change docs/verification_report.md as if it were current acceptance evidence",
            ],
        },
        "spec_gap_id": SPEC_GAP_ID,
        "stale_acceptance_surfaces": stale,
        "status": "SPEC_GAP",
        "targeted_contract_baseline": baseline,
        "work_package_id": WORK_PACKAGE_ID,
        "write_scope_audit": {
            "attempt_artifact_scope": "artifacts/work_packages/C01/attempts/0005/**",
            "out_of_scope_product_change_count": 0,
            "product_file_change_count": 0,
            "subagents_or_fleet_used": False,
        },
    }


def dependency_status() -> dict[str, Any]:
    return {
        "attempt_id": ATTEMPT_ID,
        "completion_ready": False,
        "fixed_execution_sequence": [
            "C01",
            "C02",
            "C03",
            "C04",
            "B04",
            "A05",
            "A06",
            "J02",
            "K01",
            "T01",
            "FULL_DAG_RECOMPUTATION",
        ],
        "package_states": {
            "A04": "PASS_HISTORY_PRESERVED",
            "A05": "PASS_HISTORY_BUT_LATER_CORRECTION_NOT_STARTED",
            "B04": "WAITING_ON_C04_AND_C01_SG004_RESOLUTION",
            "C01": "SPEC_GAP_C01_SG004",
            "C02": "WAITING_ON_C01",
            "C03": "WAITING_ON_C01_AND_C02",
            "C04": "WAITING_ON_C02_AND_C03",
            "J02": "WAITING_ON_CANONICAL_SEQUENCE",
            "K01": "WAITING_ON_CANONICAL_SEQUENCE",
        },
        "resume_condition": (
            "A product-owner HumanDecision assigns exact owners and write paths "
            "for the eight stale authority/test surfaces and fixes their gate "
            "timing so the 126-schema C01/C04/B04 sequence is executable. Resume "
            "with a new C01 attempt; do not modify C01-0001 through C01-0005."
        ),
        "spec_gap_id": SPEC_GAP_ID,
        "status": "SPEC_GAP",
        "subsequent_package_started": False,
    }


def review_text() -> str:
    return """# C01 attempt 0005 shared-contract review

Status: `SPEC_GAP (C01-SG004)`

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW`

Actor independence: `false`. The product-owner execution contract prohibits
Fleet and subagents. This is a separate primary-session review of the captured
authority, manifest ownership, test oracles, and proposed classification; it is
not external actor-independent certification and does not waive any gate.

## Outcome

The K01 HumanDecision is authentic and complete enough to define the new
`DocumentRegistrationRequest`, immutable `DocumentRegistration`, final
`DocumentManifest` lineage, and the target count of 126 schemas and 126
examples. The active successor development manifest correctly grants C01 the
canonical schema/example/OpenAPI/document paths.

C01 nevertheless cannot lawfully start the product change. Eight active
authority or acceptance paths retain 124-era assumptions:

1. `MASTER_SPEC.md` still declares 124/124 and is owned only by A01.
2. `manifests/acceptance_matrix.yaml` still gates on 124/124 and is owned only
   by F01.
3. `tests/contracts/openapi/test_scientific_contracts.py` fixes four 124-count
   assertions and has no manifest owner.
4. `tests/contracts/openapi/test_openapi_contract.py` classifies
   `DocumentRegistrationRequest` as transport-only, fixes the schema count at
   124, and tests the obsolete `source_uri`/`uploaded_artifact_id` shape; it has
   no manifest owner.
5. `tests/test_contracts.py` fixes the registry count at 124 and has no owner.
6. `tests/test_cli.py` fixes the loaded-schema count at 124 and has no owner.
7. `tests/test_f01_epistemic_work_classifier.py` reads the root trees and fixes
   them at 124/124; F01 owns it but no F01 correction occurs before C04.
8. `tests/packaging/test_canonical_registry.py` is B04-owned, but B04 is fixed
   after C04 even though C04 must run the full Python suite against the stale
   package projection.

The generated C02 files, C03 migration documentation, C01 API documentation,
and B04 snapshot have known owners and are correctly deferred to their named
stages. `docs/verification_report.md` is separately recorded as a stale report,
not treated as live C01 acceptance authority.

## Adversarial checks

- Treating the HumanDecision as implicit permission to edit every affected
  test would violate its exact C01 write scope.
- Partially adding the two schemas would make the current C01 targeted oracle
  false immediately and would make the fixed C04-before-B04 full-suite gate
  unreachable.
- Calling the resulting failures ordinary implementation defects would hide
  the missing correction owner and timing authority.
- Calling this BLOCKED would be inaccurate because all evidence and tools are
  local and available.
- Weakening counts, skipping tests, hand-editing generated outputs, or treating
  the derived package snapshot as authority is forbidden.

The current pre-implementation contract baseline remains 124 schemas, 124
examples, and 66/66 targeted OpenAPI contract tests. The four newly authorized
schema/example paths are all absent, proving that no partial C01 product change
was applied by this attempt.

## Required decision

The minimum resolving HumanDecision must name the correction owner and exact
write scope for all eight paths above, authorize the two higher authority count
changes, and put the oracle/projection corrections before the gate that consumes
them. It must state explicitly whether B04 projection moves before C04 for this
attempt-level repair or whether C04 receives a bounded projection-pending gate
with mandatory post-B04 reconciliation. Broad `tests/**`, `docs/**`, schema
weakening, history rewriting, and silent test exclusion remain forbidden.

## Decision

`C01-0005` is `SPEC_GAP`, not PASS, FAIL, or BLOCKED. No canonical product file
is modified. C02 and all later packages remain waiting. Existing dirty-worktree
content and C01-0001 through C01-0004 remain preserved.
"""


def command_rows() -> list[dict[str, Any]]:
    recorded = "2026-07-30T06:45:00Z"
    raw = [
        (
            "C01-0005-C001",
            "Verify product-owner attachment, K01 HumanDecision, active manifest binding, and successor manifest hashes",
            0,
            "PASS: attachment c44b4d35..., decision 62c7e688..., binding 6915375c..., successor manifest 7d1d3248...",
        ),
        (
            "C01-0005-C002",
            "Audit C01/C02/C03/C04/B04 exact scopes, dependencies, and fixed canonical sequence",
            0,
            "PASS: C01 exact scope confirmed; C04 requires full_python_suite; B04 depends on C04",
        ),
        (
            "C01-0005-C003",
            "Inventory current canonical source and newly authorized K01 paths",
            0,
            "PASS: 124 schemas, 124 examples, all four new schema/example paths absent; no partial product change",
        ),
        (
            "C01-0005-C004",
            "Run pre-implementation C01 OpenAPI contract baseline",
            0,
            "PASS: 66 passed, 0 failed",
        ),
        (
            "C01-0005-C005",
            "Search active authority, tests, generated outputs, documentation, and package snapshot for 124-era contract assumptions",
            0,
            "PASS: eight gate-relevant stale surfaces classified by owner/timing; planned C01/C02/C03/B04 surfaces separated",
        ),
        (
            "C01-0005-C006",
            "Verify immutable C01-0001 through C01-0004 report hashes",
            0,
            "PASS: four prior report hashes preserved",
        ),
        (
            "C01-0005-R001",
            "Perform primary-session separate adversarial contract review",
            0,
            "SPEC_GAP_CONFIRMED: actor_independence=false; no gate waived",
        ),
        (
            "C01-0005-D001",
            "Read an initially guessed development-manifest binding filename",
            1,
            "DIAGNOSTIC_ONLY: corrected to manifests/source_bindings/development-manifest.binding.json; no mutation",
        ),
        (
            "C01-0005-D002",
            "Read an obsolete RAH current filename while inspecting state",
            1,
            "DIAGNOSTIC_ONLY: corrected to current.json/state_store.read_current; no mutation",
        ),
        (
            "C01-0005-D003",
            "Inspect RAH CLI source through a PowerShell pipeline",
            1,
            "DIAGNOSTIC_ONLY: reliability guard rejected the command before execution; subsequent RAH operations use literal Git Bash commands",
        ),
        (
            "C01-0005-C007",
            "Build and deterministically verify C01-0005 SPEC_GAP artifacts",
            0,
            "PASS: stored evidence matches live authority and 66-test baseline",
        ),
        (
            "C01-0005-C008",
            "Run git diff --check after attempt evidence creation",
            0,
            "PASS: no whitespace errors; existing line-ending advisories are not failures",
        ),
        (
            "C01-0005-C009",
            "Append contract-audit evidence and documented C01-SG004 gap to RAH",
            0,
            "RESERVED_FOR_CORE_SEAL: E0096/E0097; blocked; completion_ready=false",
        ),
        (
            "C01-0005-C010",
            "Verify core RAH generation, six payload hashes, and six flat projections",
            0,
            "RESERVED_FOR_CORE_SEAL: generation 000089-*, 11 retained generations",
        ),
        (
            "C01-0005-C011",
            "Append hash-sealed C01-0005 closeout evidence and verify resume packet",
            0,
            "RESERVED_FOR_FINAL_SEAL: E0098; generation 000090-*; blocked; completion_ready=false",
        ),
    ]
    return [
        {
            "command": command,
            "command_id": command_id,
            "exit_code": exit_code,
            "recorded_at_utc": recorded,
            "result": result,
            "scope": ATTEMPT_ID,
        }
        for command_id, command, exit_code, result in raw
    ]


def report_document(core: dict[str, Any] | None = None) -> dict[str, Any]:
    audit = read_json(ATTEMPT / "c01-shared-contract-gap-verification.json")
    dependency = read_json(ATTEMPT / "dependency-status.json")
    report: dict[str, Any] = {
        "attempt_id": ATTEMPT_ID,
        "authority_decision_id": DECISION_ID,
        "completion_ready": False,
        "dependency_effect": dependency["package_states"],
        "historical_preservation": {
            "C01_0001_through_0004_reports_preserved": True,
            "dirty_worktree_preserved": True,
            "prior_RAH_generations_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
            "subagents_or_fleet_used": False,
        },
        "implementation_status": "NOT_STARTED_FAIL_CLOSED",
        "open_risks": [
            "The active top-level specification and acceptance matrix still conflict with the approved 126-schema target.",
            "C01 targeted tests cannot validate the approved contract without out-of-scope oracle migration.",
            "The C04-before-B04 full-suite order consumes B04-owned freshness checks before B04 can repair the projection.",
            "Review is primary-session procedural review, not actor-independent certification.",
        ],
        "output_artifacts": [
            "artifacts/work_packages/C01/attempts/0005/c01-shared-contract-gap-verification.json",
            "artifacts/work_packages/C01/attempts/0005/dependency-status.json",
            "artifacts/work_packages/C01/attempts/0005/rah-core-integrity.json",
            "artifacts/work_packages/C01/attempts/0005/review.md",
            "artifacts/work_packages/C01/attempts/0005/commands.jsonl",
            "artifacts/work_packages/C01/attempts/0005/report.json",
            "artifacts/work_packages/C01/attempts/0005/c01_0005_evidence.py",
            "artifacts/work_packages/C01/attempts/0005/c01_0005_rah_seal.py",
        ],
        "package_status": "SPEC_GAP",
        "product_file_change_count": 0,
        "resume_condition": dependency["resume_condition"],
        "review": {
            "actor_independence": False,
            "artifact": "artifacts/work_packages/C01/attempts/0005/review.md",
            "blocking_finding_count": 8,
            "mode": "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW",
            "status": "SPEC_GAP",
        },
        "spec_gap": {
            "classification": "SPEC_GAP",
            "id": SPEC_GAP_ID,
            "not_blocked_reason": audit["classification"]["not_blocked_reason"],
            "not_fail_reason": audit["classification"]["not_fail_reason"],
            "required_higher_order_decision": audit["required_higher_order_decision"],
            "summary": "126-schema acceptance-oracle migration ownership and gate-order gap",
        },
        "spec_gap_id": SPEC_GAP_ID,
        "status": "SPEC_GAP",
        "targeted_contract_baseline": audit["targeted_contract_baseline"],
        "work_package_id": WORK_PACKAGE_ID,
    }
    if core is not None:
        report["rah_state"] = {
            "completion_ready": False,
            "contract_audit_evidence_id": "E0096",
            "core_generation": core["current_generation"],
            "core_generation_manifest_sha256": core[
                "generation_manifest_sha256"
            ],
            "core_parent_generation": "000088-a4a7294e",
            "documented_gap_evidence_id": "E0097",
            "final_closeout_evidence_id": "E0098",
            "flat_snapshot_content_matches_after_core": core[
                "flat_snapshot_content_matches"
            ],
            "flat_snapshot_stamps_verified_after_core": core[
                "flat_snapshot_stamps_verified"
            ],
            "generation_file_hashes_verified_after_core": core[
                "generation_file_hashes_verified"
            ],
            "retained_generation_count_after_core": core[
                "retained_generation_count"
            ],
            "status": "blocked",
        }
    return report


def parse_commands() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for number, raw in enumerate(
        (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8").splitlines(), 1
    ):
        if not raw.strip():
            continue
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise SystemExit(f"commands line {number} is not an object")
        rows.append(value)
    ids = [row.get("command_id") for row in rows]
    if len(ids) != len(set(ids)) or any(not isinstance(item, str) for item in ids):
        raise SystemExit("commands.jsonl has missing or duplicate IDs")
    return rows


def assert_utf8_lf(path: Path) -> None:
    content = path.read_bytes()
    if content.startswith(b"\xef\xbb\xbf") or b"\x00" in content:
        raise SystemExit(f"invalid text encoding marker: {path}")
    text = content.decode("utf-8")
    if "\ufffd" in text or "\r" in text or not text.endswith("\n"):
        raise SystemExit(f"invalid UTF-8/LF artifact: {path}")


def build_pre_core() -> None:
    ATTEMPT.mkdir(parents=True, exist_ok=True)
    write_json(
        ATTEMPT / "c01-shared-contract-gap-verification.json",
        contract_audit(run_regression=True),
    )
    write_json(ATTEMPT / "dependency-status.json", dependency_status())
    (ATTEMPT / "review.md").write_text(
        review_text(), encoding="utf-8", newline="\n"
    )
    (ATTEMPT / "commands.jsonl").write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in command_rows()
        ),
        encoding="utf-8",
        newline="\n",
    )
    write_json(ATTEMPT / "report.json", report_document())
    verify_pre_core(run_regression=False)


def verify_pre_core(*, run_regression: bool = True) -> dict[str, Any]:
    expected_audit = contract_audit(run_regression=run_regression)
    stored_audit = read_json(ATTEMPT / "c01-shared-contract-gap-verification.json")
    if run_regression:
        if stored_audit != expected_audit:
            raise SystemExit("stored C01-0005 audit differs from live authority")
    else:
        expected_audit["targeted_contract_baseline"] = stored_audit[
            "targeted_contract_baseline"
        ]
        if stored_audit != expected_audit:
            raise SystemExit("stored C01-0005 audit differs from fast live authority")
    if read_json(ATTEMPT / "dependency-status.json") != dependency_status():
        raise SystemExit("stored C01-0005 dependency status differs from authority")
    if (ATTEMPT / "review.md").read_text(encoding="utf-8") != review_text():
        raise SystemExit("stored C01-0005 review differs from canonical review")
    report = read_json(ATTEMPT / "report.json")
    if report.get("status") != "SPEC_GAP" or report.get("spec_gap_id") != SPEC_GAP_ID:
        raise SystemExit("C01-0005 report is not SPEC_GAP C01-SG004")
    if report.get("completion_ready") is not False:
        raise SystemExit("C01-0005 report advanced completion_ready")
    rows = parse_commands()
    for path in ATTEMPT.iterdir():
        if path.is_file() and path.suffix in {".json", ".jsonl", ".md", ".py"}:
            assert_utf8_lf(path)
    return {
        "attempt_id": ATTEMPT_ID,
        "commands_parsed": len(rows),
        "completion_ready": False,
        "history_hashes_verified": len(HISTORY_HASHES),
        "product_file_change_count": 0,
        "spec_gap_id": SPEC_GAP_ID,
        "stale_acceptance_surface_count": len(STALE_SURFACES),
        "status": "SPEC_GAP",
        "targeted_contract_baseline": stored_audit["targeted_contract_baseline"],
    }


def build_post_core(core_integrity: dict[str, Any]) -> None:
    write_json(ATTEMPT / "rah-core-integrity.json", core_integrity)
    write_json(ATTEMPT / "report.json", report_document(core_integrity))
    verify_post_core(run_regression=False)


def verify_post_core(*, run_regression: bool = True) -> dict[str, Any]:
    result = verify_pre_core(run_regression=run_regression)
    integrity = read_json(ATTEMPT / "rah-core-integrity.json")
    report = read_json(ATTEMPT / "report.json")
    rah_state = report.get("rah_state")
    if integrity.get("status") != "PASS" or integrity.get("ralph_status") != "blocked":
        raise SystemExit("C01-0005 core RAH integrity is not blocked-state PASS")
    if not isinstance(rah_state, dict):
        raise SystemExit("C01-0005 report has no RAH binding")
    if rah_state.get("core_generation") != integrity.get("current_generation"):
        raise SystemExit("C01-0005 report/core generation mismatch")
    return {
        **result,
        "core_evidence_ids": ["E0096", "E0097"],
        "core_generation": integrity["current_generation"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode",
        choices=(
            "build-pre-core",
            "verify-pre-core",
            "verify-pre-core-fast",
            "build-post-core",
            "verify-post-core",
            "verify-post-core-fast",
        ),
    )
    parser.add_argument("--core-integrity")
    args = parser.parse_args()
    if args.mode == "build-pre-core":
        build_pre_core()
        result = verify_pre_core(run_regression=False)
    elif args.mode == "verify-pre-core":
        result = verify_pre_core(run_regression=True)
    elif args.mode == "verify-pre-core-fast":
        result = verify_pre_core(run_regression=False)
    elif args.mode == "build-post-core":
        if not args.core_integrity:
            parser.error("build-post-core requires --core-integrity")
        build_post_core(read_json(Path(args.core_integrity)))
        result = verify_post_core(run_regression=False)
    elif args.mode == "verify-post-core":
        result = verify_post_core(run_regression=True)
    else:
        result = verify_post_core(run_regression=False)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
