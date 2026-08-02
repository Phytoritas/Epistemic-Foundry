#!/usr/bin/env python3
"""Verify deterministic C02 generation and cross-language fixture parity."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import py_compile
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence

import generate


LEGACY_VALUES = ("PIL" + "OT", "HYPOTHESIS_PASSPORT" + "_ONLY")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
    }


def add_failure(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def validate_schemas_and_examples(root: Path, contracts: Sequence[generate.Contract]) -> dict[str, Any]:
    try:
        from jsonschema import Draft202012Validator
        from referencing import Registry, Resource
    except ImportError as exc:
        raise generate.GenerationError(f"Required locked validation dependency unavailable: {exc}") from exc

    resources = []
    for contract in contracts:
        Draft202012Validator.check_schema(contract.schema)
        resources.append((contract.schema_id, Resource.from_contents(contract.schema)))
    registry = Registry().with_resources(resources)
    invalid: list[dict[str, Any]] = []
    for contract in contracts:
        validator = Draft202012Validator(contract.schema, registry=registry)
        errors = sorted(validator.iter_errors(contract.example), key=lambda error: list(error.path))
        if errors:
            invalid.append(
                {
                    "example": contract.example_file,
                    "errors": [error.message for error in errors],
                }
            )
    return {
        "status": "PASS" if not invalid else "FAIL",
        "schema_count": len(contracts),
        "valid_example_count": len(contracts) - len(invalid),
        "invalid": invalid,
    }


def run_node(root: Path) -> tuple[int, dict[str, Any], str]:
    command = ["node", "packages/contracts/codegen/cross_language_fixture.mjs"]
    process = subprocess.run(command, cwd=root, capture_output=True, text=True, encoding="utf-8")
    try:
        payload = json.loads(process.stdout)
    except json.JSONDecodeError:
        payload = {}
    return process.returncode, payload, process.stderr.strip()


def verify_python_models(root: Path, expected_count: int) -> dict[str, Any]:
    path = root / "python/epistemic_foundry/contracts/models.py"
    with tempfile.TemporaryDirectory(prefix="ef-c02-pycompile-") as directory:
        py_compile.compile(path, cfile=str(Path(directory) / "models.pyc"), doraise=True)
    spec = importlib.util.spec_from_file_location("ef_c02_generated_models", path)
    if spec is None or spec.loader is None:
        raise generate.GenerationError("Could not create an import spec for generated Python models")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    names = tuple(module.MODEL_NAMES)
    missing = [name for name in names if not hasattr(module, name)]
    return {
        "status": "PASS" if len(names) == expected_count and not missing else "FAIL",
        "model_count": len(names),
        "missing_models": missing,
        "schema_id_count": len(module.SCHEMA_IDS),
        "bundle_sha256": module.CONTRACT_BUNDLE_SHA256,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    root = args.repo_root.resolve() if args.repo_root else generate.repository_root()
    failures: list[str] = []

    contracts, schema_bundle, example_bundle = generate.load_contracts(root)
    add_failure(failures, len(contracts) == 127, "canonical schema/example cardinality is not 127/127")
    expected = generate.expected_files(root)
    checked_in_failures = generate.check_files(root, expected)
    failures.extend(checked_in_failures)

    with tempfile.TemporaryDirectory(prefix="ef-c02-replay-a-") as first_directory, tempfile.TemporaryDirectory(prefix="ef-c02-replay-b-") as second_directory:
        first = Path(first_directory)
        second = Path(second_directory)
        generate.write_files(first, expected)
        generate.write_files(second, expected)
        replay_a = tree_bytes(first)
        replay_b = tree_bytes(second)
        deterministic = replay_a == replay_b and replay_a == {
            path.as_posix(): value for path, value in expected.items()
        }
        add_failure(failures, deterministic, "independent codegen replays differ")

    manifests = {
        "typescript": load_json(root / "packages/contracts/src/generated/contract-manifest.json"),
        "python": load_json(root / "python/epistemic_foundry/contracts/contract-manifest.json"),
        "ui": load_json(root / "web/src/generated/contract-manifest.json"),
    }
    manifest_parity = manifests["typescript"] == manifests["python"] == manifests["ui"]
    add_failure(failures, manifest_parity, "generated projection manifests differ")
    manifest = manifests["typescript"]
    add_failure(failures, manifest.get("schema_count") == len(contracts), "schema count drift")
    add_failure(failures, manifest.get("example_count") == len(contracts), "example count drift")
    add_failure(failures, manifest.get("schema_bundle_sha256") == schema_bundle, "schema bundle hash drift")
    add_failure(failures, manifest.get("example_bundle_sha256") == example_bundle, "example bundle hash drift")

    validation = validate_schemas_and_examples(root, contracts)
    add_failure(failures, validation["status"] == "PASS", "canonical schema/example validation failed")

    python_models = verify_python_models(root, len(contracts))
    add_failure(failures, python_models["status"] == "PASS", "generated Python models failed")
    add_failure(
        failures,
        python_models["bundle_sha256"] == schema_bundle,
        "generated Python bundle binding differs",
    )

    node_exit, node_result, node_stderr = run_node(root)
    add_failure(failures, node_exit == 0, f"Node fixture verifier failed: {node_stderr}")
    add_failure(failures, node_result.get("status") == "PASS", "Node fixture parity status failed")
    node_fixtures = node_result.get("fixtures", {})
    python_fixtures = {contract.example_file: contract.example for contract in contracts}
    semantic_fixture_parity = node_fixtures == python_fixtures
    add_failure(failures, semantic_fixture_parity, "Node/Python parsed fixture values differ")

    active_generated = b"\n".join((root / path).read_bytes() for path in sorted(expected))
    legacy_hits = [value for value in LEGACY_VALUES if value.encode("utf-8") in active_generated]
    add_failure(failures, not legacy_hits, "legacy promotion values occur in generated artifacts")

    projection_hashes = {
        path.as_posix(): f"sha256:{sha256(root / path)}" for path in sorted(expected)
    }
    result = {
        "work_package_id": "C02",
        "check": "c02_contract_codegen_verification",
        "status": "FAIL" if failures else "PASS",
        "source_authority": "schemas/*.schema.json",
        "schema_count": len(contracts),
        "example_count": len(contracts),
        "schema_bundle_sha256": schema_bundle,
        "example_bundle_sha256": example_bundle,
        "generated_file_count": len(expected),
        "codegen_clean_diff": {
            "status": "PASS" if not checked_in_failures else "FAIL",
            "failures": checked_in_failures,
        },
        "deterministic_double_replay": "PASS" if deterministic else "FAIL",
        "manifest_parity": "PASS" if manifest_parity else "FAIL",
        "schema_example_validation": validation,
        "python_models": python_models,
        "node_fixture_check": {
            "status": node_result.get("status", "FAIL"),
            "exit_code": node_exit,
            "schema_count": node_result.get("schema_count"),
            "example_count": node_result.get("example_count"),
            "failures": node_result.get("failures", []),
            "stderr": node_stderr,
        },
        "cross_language_fixture_parity": "PASS" if semantic_fixture_parity else "FAIL",
        "verification_boundary": {
            "status": "PASS",
            "codegen_checks_are_attempt_independent": True,
            "full_repository_regression_owner": "work-package attempt evidence and C04",
            "cross_package_immutable_history_owner": "RAH and work-package attempt evidence",
        },
        "write_scope": [
            "packages/contracts/**",
            "python/epistemic_foundry/contracts/**",
            "web/src/generated/**",
            "artifacts/work_packages/C02/** (manifest-declared evidence artifacts)",
        ],
        "legacy_promotion_value_hits": legacy_hits,
        "generated_artifact_hashes": projection_hashes,
        "failures": failures,
    }
    output = args.output
    if output:
        output = output if output.is_absolute() else root / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (generate.GenerationError, OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({"work_package_id": "C02", "status": "FAIL", "error": str(exc)}, indent=2), file=sys.stderr)
        raise SystemExit(1) from exc
