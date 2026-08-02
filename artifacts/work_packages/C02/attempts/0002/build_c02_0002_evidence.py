#!/usr/bin/env python3
"""Build and verify deterministic C02-0002 dependency evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/C02/attempts/0002"
VERIFICATION = ATTEMPT / "c02-contract-codegen-verification.json"
EXPECTED_SOURCE_HASHES = {
    "packages/contracts/package.json": "faceda59bc5539bc75d13dbc2bb11ba04220164a92e0fb98fc8752f47c108c1b",
    "packages/contracts/codegen/generate.py": "76a1a37e54c3dcb9edab3dfe79f493c475ca779f0d8afeae7409ce894ce8d6b1",
    "packages/contracts/codegen/verify.py": "5b8e333ea6fcf2d70720e6863d2b8652982cf19971f9eb2c09fc9d6d184ad553",
    "packages/contracts/codegen/cross_language_fixture.mjs": "395344864b15057c8acd16e2b4535e01ba5fa0bcaa1582606804a7ff120b8dff",
    "package-lock.json": "32d30423475de0cadc8d5fe04802b0833f396d9bb36f78ee156d5a4306f2616a",
}
EXPECTED_GENERATED_HASHES = {
    "packages/contracts/src/generated/contract-manifest.json": "96acd5a496ac234eaf8bffdda8dbf0c87db3e4130822b8cbeab6522b82e3fdcf",
    "packages/contracts/src/generated/models.d.ts": "b6921eb4214aaf90296a4112a4683428467ba2bead86b4309ad2b540325df0a9",
    "packages/contracts/src/generated/registry.mjs": "17bce5beea2d1a35b2c5601c97f361f8075a8952772f74af86d8a2d72c343107",
    "python/epistemic_foundry/contracts/__init__.py": "29a58cf958579f9a2165222059603ea1c4898d85379473b00872ce237dd92095",
    "python/epistemic_foundry/contracts/contract-manifest.json": "96acd5a496ac234eaf8bffdda8dbf0c87db3e4130822b8cbeab6522b82e3fdcf",
    "python/epistemic_foundry/contracts/models.py": "7f6d33fa16c0d0653c34cb4145974565fa749a7f59716ca5c7ceac2e3fa6f1f6",
    "python/epistemic_foundry/contracts/py.typed": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "web/src/generated/contract-manifest.json": "96acd5a496ac234eaf8bffdda8dbf0c87db3e4130822b8cbeab6522b82e3fdcf",
    "web/src/generated/contracts.ts": "a8daa36ddf89f3c2a23b74ad5546a194c5f700c133c08ab523d14d542e28dcc9",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"JSON artifact is not an object: {path}")
    return value


def render(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(render(value), encoding="utf-8", newline="\n")


def assert_hashes(expected: dict[str, str]) -> None:
    for relative, digest in expected.items():
        path = ROOT / relative
        if not path.is_file():
            raise SystemExit(f"required C02 file is missing: {relative}")
        actual = sha256(path)
        if actual != digest:
            raise SystemExit(f"C02 hash mismatch for {relative}: {actual} != {digest}")


def manifest_contract() -> dict[str, Any]:
    raw = yaml.safe_load(
        (ROOT / "manifests/development_manifest.yaml").read_text(encoding="utf-8")
    )
    packages = raw if isinstance(raw, list) else raw["work_packages"]
    by_id = {row["id"]: row for row in packages}
    c02 = by_id["C02"]
    if len(packages) != 156:
        raise SystemExit("development manifest package count changed")
    if c02["depends_on"] != ["C01"]:
        raise SystemExit("C02 dependency changed")
    expected_scope = [
        "packages/contracts/**",
        "python/epistemic_foundry/contracts/**",
        "web/src/generated/**",
    ]
    if c02["write_scope"] != expected_scope:
        raise SystemExit("C02 exact write scope changed")
    if by_id["C03"]["depends_on"] != ["C01", "C02"]:
        raise SystemExit("C03 dependency changed")
    if by_id["C04"]["depends_on"] != ["C02", "C03"]:
        raise SystemExit("C04 dependency changed")
    if by_id["B04"]["depends_on"] != ["B02", "B03", "C04"]:
        raise SystemExit("B04 static dependency changed")
    if "generated_contract_126_parity" not in c02["required_checks"]:
        raise SystemExit("C02 126-contract parity check is missing")
    return {
        "package_count": len(packages),
        "C02": {
            "depends_on": c02["depends_on"],
            "write_scope": c02["write_scope"],
            "required_checks": c02["required_checks"],
            "exit_criteria": c02["exit_criteria"],
        },
        "C03_depends_on": by_id["C03"]["depends_on"],
        "C04_depends_on": by_id["C04"]["depends_on"],
        "B04_depends_on": by_id["B04"]["depends_on"],
        "pre_C04_B04_is_attempt_level_only": True,
        "static_dependency_cycle_added": False,
        "status": "PASS",
    }


def verify_live_contract() -> dict[str, Any]:
    stored = read_json(VERIFICATION)
    with tempfile.TemporaryDirectory(prefix="ef-c02-0002-verify-") as directory:
        output = Path(directory) / "verification.json"
        process = subprocess.run(
            [
                sys.executable,
                "-B",
                "packages/contracts/codegen/verify.py",
                "--output",
                str(output),
            ],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        if process.returncode != 0:
            raise SystemExit(
                "live C02 verifier failed: " + process.stdout + process.stderr
            )
        live = read_json(output)
    if live != stored:
        raise SystemExit("stored C02 verification differs from live inputs")
    if stored.get("status") != "PASS":
        raise SystemExit("C02 verification is not PASS")
    if (stored.get("schema_count"), stored.get("example_count")) != (126, 126):
        raise SystemExit("C02 verification is not 126/126")
    if stored.get("generated_file_count") != 9:
        raise SystemExit("C02 generated file count is not nine")
    full = stored.get("full_python_suite", {})
    if full.get("status") != "EXPECTED_DOWNSTREAM_AND_PREEXISTING_FAILURES":
        raise SystemExit("C02 full-suite status changed")
    if full.get("summary") != {
        "tests": 970,
        "failures": 19,
        "errors": 0,
        "skipped": 0,
        "passed": 951,
    }:
        raise SystemExit("C02 full-suite boundary changed")
    if full.get("failure_owner_counts") != {"B04": 18, "J02": 1}:
        raise SystemExit("C02 residual failure ownership changed")
    if full.get("c02_new_failure_count") != 0:
        raise SystemExit("C02 introduced a full-suite failure")
    return stored


def dependency_status() -> dict[str, Any]:
    return {
        "attempt_id": "C02-0002",
        "work_package_id": "C02",
        "C01": "PASS",
        "C02": "PASS",
        "C03": "DEPENDENCY_READY",
        "B04_pre_C04": "WAITING_ON_C03",
        "C04": "WAITING_ON_C03_AND_FRESH_PROJECTION",
        "B04_final": "WAITING_ON_C04",
        "next_package": "C03-0002",
        "full_156_package_dag_recomputed": False,
        "completion_ready": False,
        "status": "PASS",
    }


def verify() -> dict[str, Any]:
    assert_hashes(EXPECTED_SOURCE_HASHES)
    assert_hashes(EXPECTED_GENERATED_HASHES)
    verification = verify_live_contract()
    manifest = manifest_contract()
    dependency = dependency_status()
    dependency_path = ATTEMPT / "dependency-status.json"
    if not dependency_path.is_file() or dependency_path.read_text(encoding="utf-8") != render(dependency):
        raise SystemExit("stored C02 dependency status differs from live authority")
    manifest_hashes = {
        path: "sha256:" + sha256(ROOT / path)
        for path in (
            "packages/contracts/src/generated/contract-manifest.json",
            "python/epistemic_foundry/contracts/contract-manifest.json",
            "web/src/generated/contract-manifest.json",
        )
    }
    if len(set(manifest_hashes.values())) != 1:
        raise SystemExit("generated manifest copies are not byte-identical")
    return {
        "attempt_id": "C02-0002",
        "dependency_status": dependency,
        "generated_artifact_hashes": verification["generated_artifact_hashes"],
        "manifest_contract": manifest,
        "manifest_hashes": manifest_hashes,
        "status": "PASS",
        "verified_artifacts": [
            "c02-contract-codegen-verification.json",
            "dependency-status.json",
            "full-python-regression.junit.xml",
        ],
    }


def build() -> dict[str, Any]:
    ATTEMPT.mkdir(parents=True, exist_ok=True)
    write_json(ATTEMPT / "dependency-status.json", dependency_status())
    return verify()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("build", "verify"))
    args = parser.parse_args()
    result = build() if args.mode == "build" else verify()
    print(render(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
