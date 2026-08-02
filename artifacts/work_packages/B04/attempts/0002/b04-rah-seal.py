#!/usr/bin/env python3
"""Seal B04-0002 evidence while retaining every prior RAH generation."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts" / "work_packages" / "B04" / "attempts" / "0002"
AUTOMATION = (
    ROOT
    / ".rah"
    / "helpers"
    / "recursive-architecture-refactoring-auto"
    / "automation"
)
sys.path.insert(0, str(AUTOMATION))

import ralph_harness as rh  # noqa: E402
import state_store  # noqa: E402


CORE_PARENT = "000012-47c7beaa"
CORE_EVIDENCE_ID = "E0014"
FINAL_EVIDENCE_ID = "E0015"

STABLE_HASHES = {
    "artifacts/work_packages/B04/attempts/0002/b04-packaging-verification.json": (
        "6f07659db311b9689e45b9bd3643dc5a0c148a152ce1d1ef6e43002df02e2739"
    ),
    "artifacts/work_packages/B04/attempts/0002/full-python-suite.junit.xml": (
        "6000a3ce26bff3ed54daa5defab3f1f4950f9ddc1b039242b8150dee073c33ac"
    ),
    "artifacts/work_packages/B04/attempts/0002/review.md": (
        "d379140efd9ceea2f386fc06af62381434d64ea52deaa202847e241e266cab4d"
    ),
    "artifacts/work_packages/B04/attempts/0002/phase-artifact-reconciliation.json": (
        "abf14c868f7e109abd4e5c547f36a72263b7596c47dd6974e6452e0477428632"
    ),
    "artifacts/work_packages/B04/attempts/0002/dependency-status.json": (
        "d363e99e5e13a64c629ad5d1fddbf8912e889c4a213105b74b48fc24a0712a6b"
    ),
    "artifacts/work_packages/B04/attempts/0002/wheel.artifact-receipt.json": (
        "42be19558ed802ea14150c9557bc5c93a1941d0e76624075a8e550ab6ebb03c0"
    ),
    "artifacts/work_packages/B04/attempts/0002/sdist.artifact-receipt.json": (
        "7c922b3c8cdfa3d8c31457e77167859dd02206d1841b72223bd8f44f63d60c2c"
    ),
    "artifacts/work_packages/B04/attempts/0002/verification-runs/0001-sdist-reproducibility-fail.json": (
        "4964199846af15826922d0f3c72ddb469ac031d57bd59f118aa6d9e568b53c83"
    ),
    "artifacts/work_packages/B04/attempts/0002/b04-dag-reconciliation.py": (
        "d51e1ab460e5de83d25aa3cfefb9862b612c3fae5d4ebe3cbff203e5264fa075"
    ),
    "artifacts/work_packages/B04/attempts/0002/b04-artifact-receipts.py": (
        "dea48473ce3da68df6305e73853cef15006e371079d4163f8d3fbd27fb1526cc"
    ),
    "artifacts/work_packages/B04/attempts/0002/normalize-junit.py": (
        "44639b934fb3cf242b7f8efbe415c8f9213464d3d5fec265e8d74af308de43f3"
    ),
    "scripts/build/canonical_registry/verify_packaging.py": (
        "d1a4fc94edcc21275d84bbc540d09db78d1298c4a194e4392e47118d0457bd3f"
    ),
    "scripts/build/canonical_registry/materialize.py": (
        "14d10a98420384873e4200e6eabd860c5ecd1a7d18a2c095450c0e8628ab818a"
    ),
    "pyproject.toml": (
        "29d7a25d530884a4a2dff3d8ca2d9878717a43a4dc3c2710fc5317f533a7be44"
    ),
    "src/epistemic_foundry/contracts/registry.py": (
        "5620dc497f0e140ff274c619ffd690e4c1646a71277d43935162886ed133df8e"
    ),
    "manifests/development_manifest.yaml": (
        "a0a0db29da459d29c655827eaa0f7253d1becc3e75106f369850335ac7b88345"
    ),
    "artifacts/authority_decisions/EF4-A05-C01-B04-SHARED-CONTRACT.human-decision.json": (
        "436a69bfebf374e78e3f52711c52f2f2c02cb429fb8c0a8a5e4988720cdca2d1"
    ),
    "artifacts/authority_decisions/HD-EF4-C01-SG003-20260728-001.human-decision.json": (
        "bcce9f20f59712c78032a846e1ac368e8d0cf27141731df31478a1f7e976d38e"
    ),
    "artifacts/work_packages/B02/report.json": (
        "98abe689dbfb9399d2f50f87a18376ca9a85ed4a50c938513778e312e3e67dad"
    ),
    "artifacts/work_packages/B03/report.json": (
        "baa07e997402a290f2602cea39a78a1acdeeb69dd7ea8c89331c84e78976338f"
    ),
    "artifacts/work_packages/C04/report.json": (
        "eca4fdd3f10537a2fb5c39643f4dee52bab9bcf5b95f9468ddcd470ffd98592f"
    ),
}

HISTORICAL_B04_HASHES = {
    "artifacts/work_packages/B04/report.json": (
        "3b239d90f30257ef79e95caedbeb5d2b020e34710b4ddac3d5ebb07e981d775a"
    ),
    "artifacts/work_packages/B04/build-smoke.json": (
        "e9184f3d59b1b7b1d90cfc5ff5b418038a1fb6058fab3b369b325488befc2591"
    ),
    "artifacts/work_packages/B04/reconciliation.json": (
        "73b9671d6622a42e892e4aab7f4b29b171d3da7b46f42bb818230cc22001e258"
    ),
    "artifacts/work_packages/B04/commands.jsonl": (
        "77d10bbf83fb9b734f9a5e6767e7c8a1579ca83964d7df36365006de85c80102"
    ),
    "artifacts/work_packages/B04/review.md": (
        "5c32fb9c7e811d23ee569bd3202a2176137202e073ef5d357fa72f3de33a819d"
    ),
}

DIST_ARTIFACTS = {
    "artifacts/work_packages/B04/attempts/0002/dist/epistemic_foundry-4.0.0-py3-none-any.whl": {
        "sha256": "ac6fc720b2df29ef8ebb73c429e6ef484e7dd844ed863e55e1d744a691a73756",
        "byte_size": 301117,
    },
    "artifacts/work_packages/B04/attempts/0002/dist/epistemic_foundry-4.0.0.tar.gz": {
        "sha256": "dc5a40c8e9a92f58219e3b031038b745a00c30ce381cf43478f591d3041464d1",
        "byte_size": 246149,
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"cannot read required JSON evidence {path}: {error}")
    if not isinstance(document, dict):
        raise SystemExit(f"required JSON evidence is not an object: {path}")
    return document


def numbered_generations(ralph_root: Path) -> list[str]:
    return sorted(
        path.name
        for path in (ralph_root / "generations").iterdir()
        if path.is_dir() and re.fullmatch(r"\d{6}-[0-9a-f]{8}", path.name)
    )


def evidence_ids(payloads: dict[str, Any]) -> list[str]:
    ledger = payloads.get("evidence_ledger.json")
    if not isinstance(ledger, dict) or not isinstance(ledger.get("entries"), list):
        raise SystemExit("RAH evidence ledger is not a valid object")
    return [
        str(entry.get("id"))
        for entry in ledger["entries"]
        if isinstance(entry, dict)
    ]


def assert_fixed_evidence() -> None:
    for relative, expected in {**STABLE_HASHES, **HISTORICAL_B04_HASHES}.items():
        path = ROOT / relative
        actual = sha256(path)
        if actual != expected:
            raise SystemExit(
                f"B04 fixed-evidence hash mismatch for {relative}: "
                f"{actual} != {expected}"
            )
    for relative, expected in DIST_ARTIFACTS.items():
        path = ROOT / relative
        actual = {"sha256": sha256(path), "byte_size": path.stat().st_size}
        if actual != expected:
            raise SystemExit(
                f"B04 distribution mismatch for {relative}: {actual} != {expected}"
            )

    verification = read_json(ATTEMPT / "b04-packaging-verification.json")
    if verification.get("status") != "PASS":
        raise SystemExit("B04 formal packaging verification is not PASS")
    canonical = verification.get("canonical_registry")
    if not isinstance(canonical, dict) or canonical.get("resource_count") != 125:
        raise SystemExit("B04 formal verification lacks the 125-resource registry")
    if canonical.get("schema_count") != 124 or canonical.get("duplicate_document_ids") != 0:
        raise SystemExit("B04 canonical schema/ID reconciliation is not clean")
    checks = verification.get("checks")
    if not isinstance(checks, dict):
        raise SystemExit("B04 formal verification has no checks object")
    installed = checks.get("installed_wheel")
    reproducibility = checks.get("two_build_reproducibility")
    if not isinstance(installed, dict) or not isinstance(reproducibility, dict):
        raise SystemExit("B04 installed/reproducibility evidence is missing")
    if not (
        installed.get("clean_venv_install") == "PASS"
        and installed.get("fallback_attempt_count") == 1
        and installed.get("fallback_success_count") == 0
        and installed.get("missing_packaged_resource_error_code")
        == "CANONICAL_REGISTRY_MISSING"
        and installed.get("tamper_error_code")
        == "CANONICAL_REGISTRY_HASH_MISMATCH"
        and all(value is True for value in reproducibility.values())
    ):
        raise SystemExit("B04 installed isolation or reproducibility evidence failed")

    review = (ATTEMPT / "review.md").read_text(encoding="utf-8")
    if "Status: `PASS`" not in review or "blocking findings: 0" not in review.lower():
        raise SystemExit("B04 review is not an unblocked PASS")
    if "not external actor-independent certification" not in review:
        raise SystemExit("B04 review omits the actor-independence limitation")
    for finding in ("B04-RF001", "B04-RF002", "B04-RF003", "B04-RF004"):
        if finding not in review:
            raise SystemExit(f"B04 review omits resolved finding {finding}")

    reconciliation = read_json(ATTEMPT / "phase-artifact-reconciliation.json")
    if reconciliation.get("status") != "PASS" or reconciliation.get("failures") != []:
        raise SystemExit("B04 phase reconciliation is not a clean PASS")
    if reconciliation.get("completion_ready") is not False:
        raise SystemExit("B04 phase reconciliation must keep completion_ready=false")

    dependency = read_json(ATTEMPT / "dependency-status.json")
    manifest = dependency.get("manifest")
    if not isinstance(manifest, dict):
        raise SystemExit("B04 dependency evidence has no manifest summary")
    if (
        dependency.get("status") != "PASS"
        or dependency.get("ready_packages_manifest_order") != ["D01", "G01", "A06"]
        or dependency.get("next_package") != "D01"
        or manifest.get("work_package_count") != 156
        or manifest.get("unique_work_package_count") != 156
        or manifest.get("unknown_dependency_count") != 0
        or manifest.get("cycle_count") != 0
        or manifest.get("topological_layer_count") != 42
        or manifest.get("maximum_layer_width") != 10
    ):
        raise SystemExit("B04 post-PASS 156-package DAG reconciliation failed")
    if dependency.get("completion_ready") is not False:
        raise SystemExit("post-B04 DAG must keep completion_ready=false")

    junit = ET.parse(ATTEMPT / "full-python-suite.junit.xml").getroot()
    suite = junit if junit.tag == "testsuite" else junit.find("testsuite")
    if suite is None:
        raise SystemExit("B04 JUnit has no testsuite")
    counts = tuple(suite.get(name) for name in ("tests", "failures", "errors", "skipped"))
    if counts != ("912", "0", "0", "0"):
        raise SystemExit(f"B04 full-suite JUnit is not 912/0/0/0: {counts}")

    historical = read_json(ROOT / "artifacts/work_packages/B04/report.json")
    if historical.get("status") != "SPEC_GAP":
        raise SystemExit("historical B04 SPEC_GAP report was overwritten")
    first_failure = read_json(
        ATTEMPT / "verification-runs/0001-sdist-reproducibility-fail.json"
    )
    if first_failure.get("status") != "FAIL":
        raise SystemExit("initial B04 resolving failure is not preserved")


def current_state() -> tuple[Path, str, dict[str, Any]]:
    ralph_root = ROOT / ".rah" / "ralph"
    current = state_store.read_current(ralph_root)
    if current is None:
        raise SystemExit("No committed RAH generation")
    generation, payloads = current
    verified = state_store.verify_current(ralph_root)
    if verified.get("generation") != generation:
        raise SystemExit("RAH generation verification disagrees with current pointer")
    loop = payloads.get("loop_state.json")
    if not isinstance(loop, dict):
        raise SystemExit("RAH loop state is not an object")
    readiness = loop.get("completion_readiness")
    if not isinstance(readiness, dict) or readiness.get("ready") is not False:
        raise SystemExit("B04 cannot seal an absent or completion-ready loop state")
    return ralph_root, generation, payloads


def verify_generation_store(expected_generation_count: int) -> dict[str, Any]:
    ralph_root, current, payloads = current_state()
    generations = numbered_generations(ralph_root)
    if len(generations) != expected_generation_count:
        raise SystemExit(
            f"expected {expected_generation_count} retained generations, "
            f"found {len(generations)}"
        )
    if generations[-1] != current:
        raise SystemExit("latest retained generation is not the current generation")
    verified_hashes = 0
    for generation in generations:
        generation_root = ralph_root / "generations" / generation
        manifest = read_json(generation_root / "generation-manifest.json")
        if manifest.get("generation") != generation:
            raise SystemExit(f"generation manifest ID mismatch: {generation}")
        files = manifest.get("files")
        if not isinstance(files, dict) or set(files) != set(state_store.GENERATION_FILES):
            raise SystemExit(f"generation manifest file set mismatch: {generation}")
        for name in state_store.GENERATION_FILES:
            actual = sha256(generation_root / name)
            if actual != files[name]:
                raise SystemExit(f"generation hash mismatch: {generation}/{name}")
            verified_hashes += 1
    current_manifest = read_json(
        ralph_root / "generations" / current / "generation-manifest.json"
    )
    flat_stamps = 0
    flat_matches = 0
    for name in state_store.GENERATION_FILES:
        flat = read_json(ralph_root / name)
        if flat.get("state_generation") == current:
            flat_stamps += 1
        stripped = {key: value for key, value in flat.items() if key != "state_generation"}
        authority = payloads[name]
        if isinstance(authority, dict):
            authority = {
                key: value for key, value in authority.items() if key != "state_generation"
            }
        if state_store._dump(stripped) == state_store._dump(authority):
            flat_matches += 1
    if flat_stamps != 6 or flat_matches != 6:
        raise SystemExit(
            f"flat snapshot verification failed: stamps={flat_stamps}, "
            f"matches={flat_matches}"
        )
    return {
        "generation": current,
        "retained_generations": generations,
        "retained_generation_manifest_count": len(generations),
        "generation_file_hashes_verified": verified_hashes,
        "flat_snapshot_stamps_verified": flat_stamps,
        "flat_snapshot_content_matches": flat_matches,
        "current_generation_manifest_sha256": sha256(
            ralph_root / "generations" / current / "generation-manifest.json"
        ),
        "current_generation_file_count": len(current_manifest["files"]),
        "evidence_ids": evidence_ids(payloads),
        "completion_ready": False,
    }


def invoke_ralph(summary: str) -> str:
    state_store.KEEP_GENERATIONS = 10_000
    saved_argv = sys.argv
    captured = io.StringIO()
    result = 1
    try:
        sys.argv = [
            "ralph_harness.py",
            str(ROOT),
            "--record-evidence",
            summary,
            "--no-increment",
            "--no-update-current-loop",
            "--json",
        ]
        with contextlib.redirect_stdout(captured):
            result = rh.main()
    finally:
        sys.argv = saved_argv
    if result != 0:
        raise SystemExit(
            f"RAH evidence append failed with exit {result}: {captured.getvalue()}"
        )
    _, generation, _ = current_state()
    return generation


def core_summary() -> str:
    return (
        "B04-0002 PASS: canonical registry packaging projects 124 schemas and "
        "one OpenAPI document into deterministic wheel/sdist resources with "
        "source bundle sha256:7dc06f09278471a136d2675801495bfe72efe7784a67fa040b77a07187dee8b0. "
        "Formal verification sha256:6f07659db311b9689e45b9bd3643dc5a0c148a152ce1d1ef6e43002df02e2739; "
        "full-suite JUnit sha256:6000a3ce26bff3ed54daa5defab3f1f4950f9ddc1b039242b8150dee073c33ac "
        "records 912 passed and zero failed/skipped. Installed-wheel-only load, "
        "complete-decoy no-fallback, missing/tamper fail-closed checks, two "
        "byte-reproducible clean builds, sdist-to-wheel parity, receipts, and "
        "actor-separated review pass. Historical B04 SPEC_GAP and the first "
        "resolving failure remain preserved. The 156-package DAG has zero "
        "unknown dependencies/cycles; READY order is D01, G01, A06; "
        "completion_ready=false."
    )


def run_core() -> dict[str, Any]:
    assert_fixed_evidence()
    ralph_root, parent, payloads = current_state()
    if parent != CORE_PARENT:
        raise SystemExit(f"Unexpected B04 core parent {parent}; expected {CORE_PARENT}")
    if evidence_ids(payloads) != [f"E{index:04d}" for index in range(1, 14)]:
        raise SystemExit("B04 core seal requires preserved E0001-E0013")
    before = numbered_generations(ralph_root)
    if len(before) != 12 or before[-1] != CORE_PARENT:
        raise SystemExit("B04 core seal requires all 12 prior generations")
    generation = invoke_ralph(core_summary())
    _, _, sealed = current_state()
    if evidence_ids(sealed) != [f"E{index:04d}" for index in range(1, 15)]:
        raise SystemExit("B04 core seal did not append exactly E0014")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("B04 core seal did not preserve every prior generation")
    verification = verify_generation_store(13)
    return {
        "mode": "core",
        "parent_generation": parent,
        "generation": generation,
        "evidence_id": CORE_EVIDENCE_ID,
        "state_verification": verification,
        "completion_ready": False,
    }


def run_final() -> dict[str, Any]:
    assert_fixed_evidence()
    ralph_root, parent, payloads = current_state()
    if not re.fullmatch(r"000013-[0-9a-f]{8}", parent):
        raise SystemExit(f"Unexpected B04 final parent generation: {parent}")
    if evidence_ids(payloads) != [f"E{index:04d}" for index in range(1, 15)]:
        raise SystemExit("B04 final seal requires preserved E0001-E0014")
    ledger = payloads["evidence_ledger.json"]
    if ledger["entries"][-1].get("summary") != core_summary():
        raise SystemExit("E0014 does not match the B04 core evidence summary")

    report = read_json(ATTEMPT / "report.json")
    rah_state = report.get("rah_state")
    if not isinstance(rah_state, dict):
        raise SystemExit("B04 report has no RAH closeout record")
    if report.get("status") != "PASS" or report.get("package_status") != "PASS":
        raise SystemExit("B04 report is not PASS")
    if report.get("completion_ready") is not False:
        raise SystemExit("B04 report must keep completion_ready=false")
    if rah_state.get("core_generation") != parent:
        raise SystemExit("B04 report core generation does not match RAH authority")
    if rah_state.get("core_evidence_id") != CORE_EVIDENCE_ID:
        raise SystemExit("B04 report does not bind E0014")
    if rah_state.get("final_closeout_evidence_id") != FINAL_EVIDENCE_ID:
        raise SystemExit("B04 report does not reserve E0015")

    commands = [
        json.loads(line)
        for line in (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    command_ids = [str(row.get("command_id")) for row in commands]
    if len(command_ids) != len(set(command_ids)):
        raise SystemExit("B04 commands.jsonl has duplicate command IDs")
    if command_ids[-3:] != [
        "B04-0002-C020",
        "B04-0002-C021",
        "B04-0002-C022",
    ]:
        raise SystemExit("B04 core seal/inspect/history commands are missing")

    closeout_hashes = {
        name: sha256(ATTEMPT / name)
        for name in (
            "report.json",
            "review.md",
            "commands.jsonl",
            "phase-artifact-reconciliation.json",
            "dependency-status.json",
            "b04-rah-seal.py",
        )
    }
    summary = (
        "B04-0002 closeout artifacts are hash-sealed after core RAH generation "
        f"{parent}: report sha256:{closeout_hashes['report.json']}; review "
        f"sha256:{closeout_hashes['review.md']}; commands sha256:"
        f"{closeout_hashes['commands.jsonl']}; phase reconciliation sha256:"
        f"{closeout_hashes['phase-artifact-reconciliation.json']}; dependency "
        f"status sha256:{closeout_hashes['dependency-status.json']}; preservation "
        f"wrapper sha256:{closeout_hashes['b04-rah-seal.py']}. B04=PASS; the "
        "156-package DAG is reconciled; D01 is next; all prior generations and "
        "SPEC_GAP history remain retained; completion_ready=false."
    )
    before = numbered_generations(ralph_root)
    generation = invoke_ralph(summary)
    _, _, sealed = current_state()
    if evidence_ids(sealed) != [f"E{index:04d}" for index in range(1, 16)]:
        raise SystemExit("B04 final seal did not append exactly E0015")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or after[-1] != generation:
        raise SystemExit("B04 final seal did not preserve every prior generation")
    verification = verify_generation_store(14)
    return {
        "mode": "final",
        "parent_generation": parent,
        "generation": generation,
        "evidence_id": FINAL_EVIDENCE_ID,
        "artifact_hashes": closeout_hashes,
        "state_verification": verification,
        "completion_ready": False,
    }


def run_verify() -> dict[str, Any]:
    assert_fixed_evidence()
    generations = numbered_generations(ROOT / ".rah" / "ralph")
    if len(generations) not in (12, 13, 14):
        raise SystemExit(f"unexpected retained generation count: {len(generations)}")
    return {
        "mode": "verify",
        "fixed_evidence": "PASS",
        "state_verification": verify_generation_store(len(generations)),
        "completion_ready": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("core", "final", "verify"))
    args = parser.parse_args()
    if args.mode == "core":
        result = run_core()
    elif args.mode == "final":
        result = run_final()
    else:
        result = run_verify()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
