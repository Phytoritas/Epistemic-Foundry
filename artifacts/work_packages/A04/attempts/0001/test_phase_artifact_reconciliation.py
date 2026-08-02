#!/usr/bin/env python3
"""A04 required check ``phase_artifact_reconciliation``.

A04 is the P00-A (Authority and architecture) integration checkpoint.  It owns
no source: it reconciles the *already sealed* evidence of A01 (authority chain,
repository constitution, status vocabulary), A02 (product invariants and
non-goals) and A03 (architecture decision records and the ADR-032/ADR-034
boundary map), and attests that the three bodies of evidence are present,
internally self-consistent, and cohere into one authority spine.

This harness is deterministic and fail-closed.  It reconciles four things:

1. **Sealed evidence integrity.**  For each of A01/A02/A03 the three manifest
   ``evidence_artifacts`` (``report.json``, ``commands.jsonl``, ``review.md``)
   exist and match a pinned SHA-256.  Any silent drift of the reconciled
   evidence fails the check.

2. **Per-package self-consistency.**  Each sealed ``report.json`` reports
   ``status == PASS``; every declared check has ``exit_code == 0`` and its
   ``commands.jsonl#<id>`` anchor resolves to a real command record in that
   package's ``commands.jsonl``; every declared ``output_artifact`` exists; and
   the authored authority/constitution/architecture documents named in
   ``changed_files`` are present on disk.

3. **Ledger evidence-id chain.**  The sealed attempt reports carry ledger
   ``core``/``final_closeout`` evidence ids.  The check asserts the A-phase
   chain is monotonic (A01 < A02 < A03), each closeout follows its core by one,
   and each dependent package pins its predecessor's *exact* ids: A02 and A03
   both cite A01's ``(E0249, E0250)``, and A03's regression baseline is the
   sealed ``A02-0001`` at ``(E0261, E0262)``.

4. **Dependency coherence.**  The manifest dependency structure of the phase is
   exactly A02→A01, A03→A01, and A04→{A02, A03}; the three authority domains
   (status/authority docs, product invariants, ADR boundary map) all exist and
   are non-empty, i.e. the phase is one coherent authority spine, not three
   unrelated artifacts.

A04 attests this pre-existing sealed evidence; it edits no source, schema, or
manifest, and weakens no check to reach GREEN.

Run as a pytest module::

    .venv/Scripts/python.exe -m pytest \
        artifacts/work_packages/A04/attempts/0001/test_phase_artifact_reconciliation.py \
        -p no:cacheprovider

Or standalone to emit deterministic JSON evidence::

    .venv/Scripts/python.exe \
        artifacts/work_packages/A04/attempts/0001/test_phase_artifact_reconciliation.py \
        --output artifacts/work_packages/A04/attempts/0001/phase-artifact-reconciliation.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[5]

MANIFEST = ROOT / "manifests/development_manifest.yaml"

#: The A-phase leaf packages this checkpoint reconciles, in dependency order.
PHASE_PACKAGES = ("A01", "A02", "A03")

#: Pinned SHA-256 of the three sealed manifest ``evidence_artifacts`` per
#: package.  These are the canonical, promoted evidence files.  Pinning makes
#: the reconciliation fail closed against any silent drift of the reconciled
#: evidence between now and seal time.
SEALED_EVIDENCE_SHA256 = {
    "artifacts/work_packages/A01/report.json":
        "892c5afcab7af0ad4c173c9abe64f80c70f6062f8ac585f3d333f72e51d78c31",
    "artifacts/work_packages/A01/commands.jsonl":
        "956d095cc4f90ab3a8bbeeabf390b1e19447f5f66c6c047435482da6f176ba8f",
    "artifacts/work_packages/A01/review.md":
        "9b359accbd9b4fc969581ca91a2f975052570a6dab3849517b85751cc7004aff",
    "artifacts/work_packages/A02/report.json":
        "ef8ea64be13746823a3c80474bc9d58ba06887c72763c518a7d51008df700e76",
    "artifacts/work_packages/A02/commands.jsonl":
        "4a07da65fc9e2dc8800d00b110fbc95fa9943a10f2af23bb32fef8d10572e4f2",
    "artifacts/work_packages/A02/review.md":
        "eecc2f33014dc81beecfc17c00854ad984652457cb40b9f59a1cc6b1a0407747",
    "artifacts/work_packages/A03/report.json":
        "23d1ab7df17afc2afb41ab989c4da2f2cf32f13872ad55dd692e4a89d31214ac",
    "artifacts/work_packages/A03/commands.jsonl":
        "9bd3c94da5886202f41abfdc1d46eecdce1db300867d87224a5be33b7921aabb",
    "artifacts/work_packages/A03/review.md":
        "e9d69c3dacac2c6274505bae05dcc71dbe23fe216a23159e78985b7824febdfd",
}

#: Expected ledger evidence-id chain, read from the sealed attempt reports.  The
#: check verifies these against the on-disk attempt reports; it does not invent
#: them.  (core, closeout) per package plus the cross references each dependent
#: package must pin.
EXPECTED_CHAIN = {
    "A01": ("E0249", "E0250"),
    "A02": ("E0261", "E0262"),
    "A03": ("E0277", "E0278"),
}

#: The manifest dependency structure of the A phase that A04 closes.
EXPECTED_DEPENDS_ON = {
    "A02": ["A01"],
    "A03": ["A01"],
    "A04": ["A02", "A03"],
}

#: One representative authored document from each package's write scope, proving
#: the three authority domains are physically present and non-empty.
DOMAIN_DOCUMENTS = {
    "A01_authority_and_status": ("CLAUDE.md", "docs/status_taxonomy.md"),
    "A02_product_invariants": ("manifests/product_invariants.yaml",),
    "A03_adr_boundary_map": ("docs/adr/README.md",),
}

EVIDENCE_ID = re.compile(r"^E(\d{4})$")


class ReconciliationError(AssertionError):
    """Fail-closed A-phase reconciliation violation."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReconciliationError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(rel: str) -> Any:
    path = ROOT / rel
    require(path.is_file(), f"required evidence missing: {rel}")
    return json.loads(path.read_text(encoding="utf-8"))


def evidence_number(evidence_id: str, where: str) -> int:
    match = EVIDENCE_ID.match(evidence_id)
    require(match is not None, f"{where}: malformed evidence id {evidence_id!r}")
    return int(match.group(1))


def manifest_packages() -> dict[str, dict[str, Any]]:
    require(MANIFEST.is_file(), "manifests/development_manifest.yaml missing")
    doc = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    packages = {wp["id"]: wp for wp in doc.get("work_packages", [])}
    for wp_id in (*PHASE_PACKAGES, "A04"):
        require(wp_id in packages, f"manifest missing work package {wp_id}")
    return packages


def reconcile_sealed_evidence(packages: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Integrity + self-consistency of each sealed A01/A02/A03 evidence set."""
    per_package: dict[str, Any] = {}
    for wp_id in PHASE_PACKAGES:
        manifest_wp = packages[wp_id]
        evidence_artifacts = list(manifest_wp.get("evidence_artifacts", []))
        require(
            len(evidence_artifacts) == 3,
            f"{wp_id}: expected 3 manifest evidence_artifacts, got {evidence_artifacts}",
        )
        # 1. Sealed evidence integrity: exist and match pinned SHA-256.
        for rel in evidence_artifacts:
            path = ROOT / rel
            require(path.is_file(), f"{wp_id}: sealed evidence missing: {rel}")
            require(
                rel in SEALED_EVIDENCE_SHA256,
                f"{wp_id}: no pinned hash for evidence artifact {rel}",
            )
            actual = sha256(path)
            require(
                actual == SEALED_EVIDENCE_SHA256[rel],
                f"{wp_id}: sealed evidence drift at {rel}: "
                f"expected {SEALED_EVIDENCE_SHA256[rel]}, got {actual}",
            )

        report = load_json(f"artifacts/work_packages/{wp_id}/report.json")
        require(
            report.get("work_package_id") == wp_id,
            f"{wp_id}: report work_package_id mismatch",
        )
        require(report.get("status") == "PASS", f"{wp_id}: sealed status not PASS")

        # 2. Every declared check succeeded and its commands.jsonl anchor exists.
        commands_text = (
            ROOT / f"artifacts/work_packages/{wp_id}/commands.jsonl"
        ).read_text(encoding="utf-8")
        checks = report.get("checks", [])
        require(bool(checks), f"{wp_id}: report declares no checks")
        for check in checks:
            require(
                check.get("exit_code") == 0,
                f"{wp_id}: check {check.get('command')!r} exit_code != 0",
            )
            anchor = check.get("artifact", "")
            require(
                "#" in anchor,
                f"{wp_id}: check {check.get('command')!r} has no commands anchor",
            )
            command_id = anchor.rsplit("#", 1)[1]
            require(
                f'"{command_id}"' in commands_text,
                f"{wp_id}: command id {command_id} not found in commands.jsonl",
            )

        # 2b. Declared output artifacts and authored documents exist.
        for rel in report.get("output_artifacts", []):
            require((ROOT / rel).is_file(), f"{wp_id}: output artifact missing: {rel}")
        authored_docs = [
            rel
            for rel in report.get("changed_files", [])
            if not rel.startswith("artifacts/work_packages/")
        ]
        require(bool(authored_docs), f"{wp_id}: report changed no authority documents")
        for rel in authored_docs:
            require((ROOT / rel).is_file(), f"{wp_id}: authored document missing: {rel}")

        per_package[wp_id] = {
            "status": "PASS",
            "evidence_artifacts": sorted(evidence_artifacts),
            "checks_passed": len(checks),
            "authored_documents": sorted(authored_docs),
        }
    return per_package


def reconcile_ledger_chain() -> dict[str, Any]:
    """Monotonic, correctly cross-referenced A-phase ledger evidence chain."""
    attempts = {
        wp_id: load_json(
            f"artifacts/work_packages/{wp_id}/attempts/0001/report.json"
        )
        for wp_id in PHASE_PACKAGES
    }
    chain: dict[str, Any] = {}
    previous_core = -1
    for wp_id in PHASE_PACKAGES:
        rah = attempts[wp_id].get("rah_state", {})
        core = rah.get("core_evidence_id")
        closeout = rah.get("final_closeout_evidence_id")
        require(
            (core, closeout) == EXPECTED_CHAIN[wp_id],
            f"{wp_id}: ledger ids {(core, closeout)} != expected "
            f"{EXPECTED_CHAIN[wp_id]}",
        )
        core_n = evidence_number(core, f"{wp_id}.core")
        closeout_n = evidence_number(closeout, f"{wp_id}.closeout")
        require(
            closeout_n == core_n + 1,
            f"{wp_id}: closeout {closeout} does not follow core {core} by one",
        )
        require(
            core_n > previous_core,
            f"{wp_id}: ledger core {core} not monotonic after {previous_core}",
        )
        require(
            attempts[wp_id].get("status") == "PASS",
            f"{wp_id}: sealed attempt status not PASS",
        )
        previous_core = core_n
        chain[wp_id] = {"core": core, "closeout": closeout}

    # A02 and A03 must both pin A01's exact sealed ids as their dependency.
    for dependent in ("A02", "A03"):
        dep = (
            attempts[dependent]
            .get("dependency_state", {})
            .get("dependencies", {})
            .get("A01", {})
        )
        require(
            (dep.get("core_evidence_id"), dep.get("final_closeout_evidence_id"))
            == EXPECTED_CHAIN["A01"],
            f"{dependent}: A01 dependency ids "
            f"{(dep.get('core_evidence_id'), dep.get('final_closeout_evidence_id'))} "
            f"!= sealed A01 {EXPECTED_CHAIN['A01']}",
        )
        require(dep.get("status") == "PASS", f"{dependent}: A01 dependency not PASS")

    # A03's regression baseline is the sealed A02-0001 at its exact ids.
    baseline = (
        attempts["A03"].get("dependency_state", {}).get("regression_baseline", {})
    )
    require(
        baseline.get("attempt_id") == "A02-0001",
        f"A03: regression baseline {baseline.get('attempt_id')} != A02-0001",
    )
    require(
        (baseline.get("core_evidence_id"), baseline.get("final_closeout_evidence_id"))
        == EXPECTED_CHAIN["A02"],
        "A03: regression baseline ids do not match sealed A02",
    )
    return chain


def reconcile_dependencies(packages: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Manifest dependency structure of the phase and domain-document presence."""
    depends_on: dict[str, list[str]] = {}
    for wp_id, expected in EXPECTED_DEPENDS_ON.items():
        actual = list(packages[wp_id].get("depends_on", []))
        require(
            actual == expected,
            f"{wp_id}: depends_on {actual} != expected {expected}",
        )
        depends_on[wp_id] = actual

    domains: dict[str, list[str]] = {}
    for domain, docs in DOMAIN_DOCUMENTS.items():
        for rel in docs:
            path = ROOT / rel
            require(path.is_file(), f"{domain}: document missing: {rel}")
            require(path.stat().st_size > 0, f"{domain}: document empty: {rel}")
        domains[domain] = list(docs)
    return {"depends_on": depends_on, "domain_documents": domains}


def build_evidence() -> dict[str, Any]:
    packages = manifest_packages()
    per_package = reconcile_sealed_evidence(packages)
    chain = reconcile_ledger_chain()
    dependencies = reconcile_dependencies(packages)
    return {
        "schema_version": 1,
        "work_package_id": "A04",
        "attempt_id": "A04-0001",
        "check": "phase_artifact_reconciliation",
        "phase": "P00-A",
        "status": "PASS",
        "reconciled_packages": list(PHASE_PACKAGES),
        "sealed_evidence": per_package,
        "ledger_chain": chain,
        "ledger_chain_monotonic": True,
        "dependencies": dependencies["depends_on"],
        "domain_documents": dependencies["domain_documents"],
        "authority_spine_coheres": True,
        "attests_pre_sealed_evidence_only": True,
        "edits_source_schema_or_manifest": False,
    }


# --------------------------------------------------------------------------- #
# pytest surface
# --------------------------------------------------------------------------- #
def test_sealed_evidence_present_and_consistent() -> None:
    evidence = build_evidence()
    assert evidence["status"] == "PASS"
    for wp_id in PHASE_PACKAGES:
        entry = evidence["sealed_evidence"][wp_id]
        assert entry["status"] == "PASS"
        assert entry["checks_passed"] >= 1
        assert entry["authored_documents"]


def test_ledger_chain_monotonic_and_cross_referenced() -> None:
    evidence = build_evidence()
    chain = evidence["ledger_chain"]
    cores = [int(chain[wp]["core"][1:]) for wp in PHASE_PACKAGES]
    assert cores == sorted(cores)
    assert cores[0] < cores[1] < cores[2]
    assert evidence["ledger_chain_monotonic"] is True


def test_phase_dependency_structure() -> None:
    depends_on = build_evidence()["dependencies"]
    assert depends_on["A02"] == ["A01"]
    assert depends_on["A03"] == ["A01"]
    assert depends_on["A04"] == ["A02", "A03"]


def test_authority_spine_coheres() -> None:
    evidence = build_evidence()
    assert evidence["authority_spine_coheres"] is True
    assert set(evidence["domain_documents"]) == set(DOMAIN_DOCUMENTS)


def test_reconciliation_fails_closed_on_drift() -> None:
    # A missing evidence file must raise, proving the check is fail-closed.
    import copy

    saved = dict(SEALED_EVIDENCE_SHA256)
    try:
        SEALED_EVIDENCE_SHA256["artifacts/work_packages/A01/report.json"] = "0" * 64
        raised = False
        try:
            build_evidence()
        except ReconciliationError:
            raised = True
        assert raised, "drifted sealed evidence must fail the reconciliation"
    finally:
        SEALED_EVIDENCE_SHA256.clear()
        SEALED_EVIDENCE_SHA256.update(saved)
        del copy


# --------------------------------------------------------------------------- #
# standalone evidence emitter
# --------------------------------------------------------------------------- #
def main() -> int:
    parser = argparse.ArgumentParser(description="A04 phase_artifact_reconciliation")
    parser.add_argument(
        "--output", type=Path, help="Write deterministic JSON evidence to this path"
    )
    args = parser.parse_args()
    try:
        evidence = build_evidence()
    except ReconciliationError as exc:
        print(f"A04_PHASE_ARTIFACT_RECONCILIATION_FAIL: {exc}", file=sys.stderr)
        return 1
    rendered = json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = args.output if args.output.is_absolute() else ROOT / args.output
        output = output.resolve()
        require(output.is_relative_to(ROOT.resolve()), "output must stay inside repo")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8", newline="\n")
        print(
            "A04_PHASE_ARTIFACT_RECONCILIATION_PASS: wrote "
            f"{output.relative_to(ROOT.resolve()).as_posix()}"
        )
    else:
        sys.stdout.write(rendered)
        print("A04_PHASE_ARTIFACT_RECONCILIATION_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
