#!/usr/bin/env python3
"""Verify C01-SG002 without changing canonical schemas or examples.

The verifier applies only the two unavoidable C01 schema constraints in
memory: EvolutionRunSpec requires ``resolved_refs`` and PromotionDecision
uses the six A05 promotion levels.  It proves that the currently mapped
canonical examples then fail validation while both example paths remain
outside C01's manifest write scope.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[5]
PROMOTION_LEVELS = [
    "INBOX",
    "CANDIDATE",
    "LITERATURE_GROUNDED",
    "VALIDATION_SCREENED",
    "EMPIRICALLY_TESTED",
    "REPLICATED",
]

BOUND_HASHES = {
    "artifacts/authority_decisions/EF4-A05-C01-B04-SHARED-CONTRACT.human-decision.json":
        "436a69bfebf374e78e3f52711c52f2f2c02cb429fb8c0a8a5e4988720cdca2d1",
    "artifacts/work_packages/C01/commands.jsonl":
        "c6c0d5dc72995e925e493a47cef94691ae2ec5f7a88d253f772c6f2ffaf64796",
    "artifacts/work_packages/C01/openapi-authority-audit.json":
        "316939a1ef647d629d41c3eac3000eb03c79c84d2b23c81f7d7601e4d7554d41",
    "artifacts/work_packages/C01/report.json":
        "14d1815150ba37ebc416d637afbb1514fbbb024f9fe6940ed7b976ce33b60d68",
    "artifacts/work_packages/C01/review.md":
        "5781bde5fb59bc3ed82610d44b3196314dcdd7e14fa414ca8e78ab2bf4be2666",
    "artifacts/work_packages/C01/schema-meta-validation.json":
        "4e51a83f49c16eb43d0b1f590fcb0864f3280cee362f64970caa9688cdd32af9",
    "examples/sample_evolution-run-spec.json":
        "118c89f92b6050678056d79f513350ff781a352b05df717084e9fa999977ddbd",
    "examples/sample_promotion-decision.json":
        "c6238e11d1aa20b32f91537de358bb4c75b9dad1f18a6f787127ced9ae353001",
    "manifests/acceptance_matrix.yaml":
        "5b089aaf1ae1e0c524d395df0308592e98b5c7663c21655d7d60a98ce8f5d00a",
    "manifests/development_manifest.yaml":
        "9ae9090a8d02973198492f271a9e46a352ca030eaa8b272e696bf6cd9ec1896e",
    "schemas/evolution-run-spec.schema.json":
        "29fe472309463865f58413c9e6566d6b3bcb71be7f6f7c74dfe1176f6a407ee9",
    "schemas/promotion-decision.schema.json":
        "a71a125155f5690f7367b800d88ef7c49ef1f132cb607b37abb04e820924ebdc",
    "tools/validate_spec_bundle.py":
        "cae72b53db10dd80f3a048daee27e197a50836cb70b60c216f917553fd7e6dd8",
}


def _json(relative: str) -> dict[str, Any]:
    value = json.loads((ROOT / relative).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{relative} must contain a JSON object")
    return value


def _sha256(relative: str) -> str:
    return hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()


def _errors(schema: dict[str, Any], instance: dict[str, Any]) -> list[dict[str, str]]:
    validator = Draft202012Validator(schema)
    return [
        {
            "path": "/".join(map(str, error.path)) or "<root>",
            "message": error.message,
        }
        for error in sorted(validator.iter_errors(instance), key=lambda item: list(item.path))
    ]


def _c01_write_scope() -> list[str]:
    manifest = yaml.safe_load(
        (ROOT / "manifests/development_manifest.yaml").read_text(encoding="utf-8")
    )
    packages = manifest if isinstance(manifest, list) else manifest.get("work_packages", [])
    package = next(item for item in packages if item.get("id") == "C01")
    return list(package["write_scope"])


def build_evidence() -> dict[str, Any]:
    hash_checks = {
        path: {
            "expected_sha256": expected,
            "actual_sha256": _sha256(path),
            "status": "PASS" if _sha256(path) == expected else "FAIL",
        }
        for path, expected in BOUND_HASHES.items()
    }
    if any(item["status"] != "PASS" for item in hash_checks.values()):
        raise RuntimeError("one or more bound authority/history files changed")

    evolution_schema = _json("schemas/evolution-run-spec.schema.json")
    evolution_example = _json("examples/sample_evolution-run-spec.json")
    promotion_schema = _json("schemas/promotion-decision.schema.json")
    promotion_example = _json("examples/sample_promotion-decision.json")

    Draft202012Validator.check_schema(evolution_schema)
    Draft202012Validator.check_schema(promotion_schema)
    current_evolution_errors = _errors(evolution_schema, evolution_example)
    current_promotion_errors = _errors(promotion_schema, promotion_example)

    required_evolution_schema = copy.deepcopy(evolution_schema)
    required_evolution_schema["properties"]["resolved_refs"] = {
        "type": "object",
        "description": "C01 must define the complete A05 resolved-reference contract.",
    }
    if "resolved_refs" not in required_evolution_schema["required"]:
        required_evolution_schema["required"].append("resolved_refs")

    required_promotion_schema = copy.deepcopy(promotion_schema)
    required_promotion_schema["properties"]["requested_level"] = {
        "enum": PROMOTION_LEVELS
    }
    required_promotion_schema["properties"]["granted_level"] = {
        "enum": PROMOTION_LEVELS
    }
    Draft202012Validator.check_schema(required_evolution_schema)
    Draft202012Validator.check_schema(required_promotion_schema)

    required_evolution_errors = _errors(required_evolution_schema, evolution_example)
    required_promotion_errors = _errors(required_promotion_schema, promotion_example)
    write_scope = _c01_write_scope()
    example_paths = [
        "examples/sample_evolution-run-spec.json",
        "examples/sample_promotion-decision.json",
    ]
    outside_scope = [path for path in example_paths if path not in write_scope]

    acceptance_text = (ROOT / "manifests/acceptance_matrix.yaml").read_text(
        encoding="utf-8"
    )
    validator_text = (ROOT / "tools/validate_spec_bundle.py").read_text(encoding="utf-8")
    schema_example_gate = "schema_example_validation_errors" in acceptance_text
    validator_maps_by_schema_stem = (
        'f"sample_{stem}.json"' in validator_text
        and 'f"sample_{stem.replace(' in validator_text
    )

    conflict_proven = all(
        [
            not current_evolution_errors,
            not current_promotion_errors,
            any("resolved_refs" in item["message"] for item in required_evolution_errors),
            any(
                item["path"] == "requested_level"
                for item in required_promotion_errors
            ),
            any(item["path"] == "granted_level" for item in required_promotion_errors),
            len(outside_scope) == 2,
            schema_example_gate,
            validator_maps_by_schema_stem,
        ]
    )
    if not conflict_proven:
        raise RuntimeError("C01-SG002 conflict was not reproduced")

    return {
        "schema_version": 1,
        "probe_id": "C01-P002",
        "work_package_id": "C01",
        "attempt_id": "C01-0002",
        "status": "SPEC_GAP",
        "spec_gap_id": "C01-SG002",
        "authority_decision_id": "HD-EF4-A05-C01-B04-20260727-001",
        "hash_checks": hash_checks,
        "current_contract": {
            "evolution_example_validation_errors": current_evolution_errors,
            "promotion_example_validation_errors": current_promotion_errors,
            "c01_write_scope": write_scope,
            "schema_example_validation_gate_required": schema_example_gate,
            "validator_maps_examples_by_schema_stem": validator_maps_by_schema_stem,
        },
        "required_contract_simulation": {
            "repository_files_modified": False,
            "evolution_change": "make resolved_refs required",
            "evolution_example_errors": required_evolution_errors,
            "promotion_change": "restrict requested_level and granted_level to the six A05 levels",
            "promotion_levels": PROMOTION_LEVELS,
            "promotion_example_errors": required_promotion_errors,
        },
        "scope_conflict": {
            "canonical_examples_outside_c01_write_scope": outside_scope,
            "conflict_proven": True,
            "reason": (
                "C01 must strengthen the two schemas and must pass canonical schema/example "
                "validation, but the only mapped examples invalidated by those mandatory "
                "changes are outside C01's write authority."
            ),
        },
        "minimum_higher_order_decision": {
            "action": "add only the two invalidated canonical example paths to C01 write_scope",
            "paths": example_paths,
            "not_requested": [
                "examples/**",
                "examples/sample_adjudication.json",
                "examples/sample_phase-artifact-set.json",
            ],
            "rationale": (
                "The Adjudication and PhaseArtifactSet examples already remain compatible with "
                "the required C01 changes; broader example authority is unnecessary."
            ),
        },
        "fail_closed_action": (
            "No schema, OpenAPI, API documentation, test, or canonical example implementation "
            "was started after the conflict was confirmed."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", type=Path)
    args = parser.parse_args()
    if (args.output is None) == (args.check is None):
        parser.error("exactly one of --output or --check is required")

    rendered = json.dumps(build_evidence(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
        print(f"PASS: wrote {args.output}")
        return 0
    if args.check.read_text(encoding="utf-8") != rendered:
        raise SystemExit(f"evidence differs from {args.check}")
    print(f"PASS: evidence matches {args.check}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
