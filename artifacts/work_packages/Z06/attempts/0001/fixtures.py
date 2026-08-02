"""Shared fixtures for the Z06 terminal release composition suite.

Nothing here hand-writes a canonical receipt.  The synthetic builders feed the
terminal gate the shape it composes: the release-provenance inputs the sealed
Z02/B05 surface accepts (with the ``clean_extraction`` build check present), a
declared bundle manifest whose extraction is byte-identical, maturity sources that
sit exactly at the acceptance-matrix floor, and the expected composed-package set.
The loaders read the *actually-sealed* artifacts — the frozen Z05 zero-trust
release report and the thirteen sealed ``*06`` reports — so the provenance suite
reconciles what the sealed owners really emit rather than what the test author
guessed.  The floor and the passing status token are read through the composed Z05
surface, so a raised floor or a reshaped status ladder fails at the assertion
rather than letting a test exercise the wrong value.
"""

from __future__ import annotations

import json
from typing import Any

from epistemic_foundry.contracts import repo_root
from epistemic_foundry.domain.hashing import sha256_of_payload

from v4_z05.zero_trust_release import reconciled_status_token, release_level_floor

# --- values read through the composed Z05 surface ------------------------------
PASS_STATUS = reconciled_status_token()
FLOOR = release_level_floor()

# --- the sealed packages this terminal gate composes ---------------------------
Z05_REPORT = "artifacts/work_packages/Z05/attempts/0001/report.json"
COMPOSED_06_PACKAGE_IDS = (
    "B06",
    "C06",
    "F06",
    "G06",
    "K06",
    "N06",
    "P06",
    "Q06",
    "S06",
    "T06",
    "V06",
    "W06",
    "Y06",
)
EXPECTED_PACKAGE_IDS = ("Z05", *COMPOSED_06_PACKAGE_IDS)

# --- the build-provenance checks the sealed release-provenance surface requires -
REQUIRED_BUILD_CHECK_IDS = (
    "reproducible_build",
    "sbom_generated",
    "manifest_complete",
    "clean_extraction",
)

STAMP = "2026-08-02T00:00:00+00:00"


def _digest(seed: str) -> str:
    return "sha256:" + (seed * 64)[:64]


def build_checks(status: str = "PASS", **per_check: str) -> list[dict[str, Any]]:
    """The four required build checks, each satisfying the provenance gate."""
    return [
        {
            "check_id": check_id,
            "status": per_check.get(check_id, status),
            "details": f"{check_id} evidence collected",
            "remediation": [],
        }
        for check_id in REQUIRED_BUILD_CHECK_IDS
    ]


def provenance_inputs(**overrides: Any) -> dict[str, Any]:
    """Release-provenance inputs the sealed surface accepts, unsigned by default."""
    inputs: dict[str, Any] = {
        "plugin_id": "epistemic-foundry",
        "version": "4.0.0",
        "source_revision": "0f1e2d3c4b5a69788796a5b4c3d2e1f00f1e2d3c",
        "source_hash": _digest("a"),
        "bundle_hash": _digest("b"),
        "sbom_hash": _digest("c"),
        "manifest_hash": _digest("d"),
        "builder_identity": "foundry-ci",
        "builder_environment_hash": _digest("e"),
        "checks": build_checks(),
        "created_at": STAMP,
    }
    inputs.update(overrides)
    return inputs


def bundle_members(**overrides: Any) -> list[dict[str, Any]]:
    """A declared bundle manifest with safe, relative member paths."""
    return [
        {"path": "epistemic_foundry/__init__.py", "digest": _digest("1")},
        {"path": "MASTER_SPEC.md", "digest": _digest("2")},
        {"path": "manifests/acceptance_matrix.yaml", "digest": _digest("3")},
    ]


def bundle_extraction(*, tamper: bool = False) -> list[dict[str, Any]]:
    """The byte-identical extraction of :func:`bundle_members`.

    Each extracted member's content hash equals the digest the manifest declares,
    so the extraction is clean; ``tamper`` flips one member's hash for the
    adversarial case.
    """
    extraction = [
        {"path": member["path"], "content_hash": member["digest"]}
        for member in bundle_members()
    ]
    if tamper:
        extraction[0]["content_hash"] = _digest("f")
    return extraction


def clean_extraction_inputs(**overrides: Any) -> dict[str, Any]:
    """The smallest clean-extraction manifest ``require_clean_extraction`` accepts."""
    inputs: dict[str, Any] = {
        "bundle_id": "BUNDLE-Z06-0001",
        "provenance_inputs": provenance_inputs(),
        "members": bundle_members(),
        "extracted": bundle_extraction(),
    }
    inputs.update(overrides)
    return inputs


def maturity_source(**overrides: Any) -> dict[str, Any]:
    """A single source sitting exactly at the acceptance-matrix floor."""
    source: dict[str, Any] = {
        "source_id": "MASTER_SPEC.md#2",
        "release_level": FLOOR,
        "completion_ready": False,
        "claims": [
            "this bundle specifies the v4 target architecture and contracts",
            "reference plugin executables remain fail-closed stubs",
        ],
    }
    source.update(overrides)
    return source


def maturity_sources() -> list[dict[str, Any]]:
    """A small honest set of maturity sources at the floor."""
    return [
        maturity_source(),
        maturity_source(
            source_id="manifests/acceptance_matrix.yaml",
            claims=["a specification file is not execution evidence"],
        ),
    ]


def accounting_packages() -> list[dict[str, Any]]:
    """Synthetic sealed-PASS package receipts covering the expected composition."""
    return [
        {
            "package_id": package_id,
            "status": PASS_STATUS,
            "completion_ready": False,
            "report_hash": _digest(package_id[0].lower()),
            "conditionals": [],
        }
        for package_id in EXPECTED_PACKAGE_IDS
    ]


def z05_facts(**overrides: Any) -> dict[str, Any]:
    """A synthetic frozen-Z05 report facts mapping the terminal gate composes."""
    facts: dict[str, Any] = {
        "work_package_id": "Z05",
        "status": PASS_STATUS,
        "completion_ready": False,
    }
    facts.update(overrides)
    return facts


def seal_kwargs(**overrides: Any) -> dict[str, Any]:
    """The smallest whole terminal-release manifest ``seal_truthful_release`` takes."""
    kwargs: dict[str, Any] = {
        "release_id": "REL-Z06-0001",
        "z05": z05_facts(),
        "clean_extraction_inputs": clean_extraction_inputs(),
        "maturity_sources": maturity_sources(),
        "expected_package_ids": list(EXPECTED_PACKAGE_IDS),
        "accounting_packages": accounting_packages(),
    }
    kwargs.update(overrides)
    return kwargs


# --- loaders over the actually-sealed artifacts --------------------------------


def _load_report(package_id: str) -> dict[str, Any]:
    path = (
        repo_root() / f"artifacts/work_packages/{package_id}/attempts/0001/report.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


def load_sealed_z05() -> dict[str, Any]:
    """The sealed Z05 zero-trust release facts, read from its frozen report."""
    report = _load_report("Z05")
    return {
        "work_package_id": report["work_package_id"],
        "status": report["status"],
        "completion_ready": report["completion_ready"],
    }


def load_sealed_accounting() -> list[dict[str, Any]]:
    """The real sealed Z05 + thirteen ``*06`` package receipts, read from disk."""
    packages: list[dict[str, Any]] = []
    for package_id in EXPECTED_PACKAGE_IDS:
        report = _load_report(package_id)
        packages.append(
            {
                "package_id": report["work_package_id"],
                "status": report["status"],
                "completion_ready": report["completion_ready"],
                "report_hash": sha256_of_payload(report),
                "conditionals": [],
            }
        )
    return packages
