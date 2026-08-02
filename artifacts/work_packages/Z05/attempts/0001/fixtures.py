"""Shared fixtures for the Z05 zero-trust release composition suite.

Nothing here hand-writes a canonical receipt.  The synthetic builders feed the
gate the shape it composes: a passing final reconciliation, the release-provenance
inputs the sealed Z02/B05 surface accepts, a lens audit whose family arithmetic
closes, and the real sealed finding-code vocabularies imported from S05, T05 and
Y05.  The loaders read the actually-sealed artifacts — the Z04 reconciliation
report and the 288-lens audit result — so the provenance suite composes what the
sealed owners really emit rather than what the test author guessed.  The canonical
passing status token is read from the module (which reads it from the attestation
schema), so a reshaped schema fails at the assertion rather than letting a test
exercise the wrong token.
"""

from __future__ import annotations

import json
from typing import Any

from epistemic_foundry.adapters.v4_t05 import FINDING_CODES as T05_FINDING_CODES
from epistemic_foundry.contracts import repo_root
from epistemic_foundry.operations.v4_y05 import FINDING_CODES as Y05_FINDING_CODES
from epistemic_foundry.security.v4_s05 import FINDING_CODES as S05_FINDING_CODES

from v4_z05.zero_trust_release import reconciled_status_token

# --- the canonical passing status token, read through the module ---------------
PASS_STATUS = reconciled_status_token()

# --- sealed artifact paths this release composes by citation -------------------
Z04_REPORT = "artifacts/work_packages/Z04/attempts/0001/report.json"
LENS_AUDIT = "reports/288_lens_evolution_audit_results.json"

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


def reconciliation(**overrides: Any) -> dict[str, Any]:
    """A passing final reconciliation that does not claim completion."""
    facts: dict[str, Any] = {
        "status": PASS_STATUS,
        "completion_ready": False,
        "contract_status": "CONFORMANT",
        "package_status": PASS_STATUS,
    }
    facts.update(overrides)
    return facts


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


def lens_audit(
    *,
    families: int = 2,
    conditional: int = 3,
    failing: int = 0,
    fail_status: str = "FAIL",
    audit_id: str = "EF4-288-LENS-FIXTURE",
) -> dict[str, Any]:
    """A lens audit whose family/lens arithmetic closes.

    Twelve lenses per family, ``conditional`` of them owned-and-conditional and
    ``failing`` of them a hard failure; the rest pass.  The summary is built to
    partition the generated results exactly.
    """
    total = families * 12
    results: list[dict[str, Any]] = []
    for index in range(total):
        if index < failing:
            status = fail_status
        elif index < failing + conditional:
            status = "CONDITIONAL"
        else:
            status = PASS_STATUS
        results.append(
            {
                "lens_id": f"L{index:03d}",
                "status": status,
                "finding": "generated fixture lens",
            }
        )
    summary: dict[str, int] = {}
    for row in results:
        summary[row["status"]] = summary.get(row["status"], 0) + 1
    return {
        "audit_id": audit_id,
        "families": families,
        "total": total,
        "summary": summary,
        "results": results,
    }


def sealed_surfaces() -> dict[str, list[str]]:
    """The real sealed S05, T05 and Y05 identity vocabularies."""
    return {
        "security_v4_s05": sorted(S05_FINDING_CODES),
        "adapters_v4_t05": sorted(T05_FINDING_CODES),
        "operations_v4_y05": sorted(Y05_FINDING_CODES),
    }


def clean_authority_claims() -> list[dict[str, Any]]:
    """Authority claims that capture nothing the release must protect."""
    return [
        {
            "capability_id": "foundry:read",
            "holder_id": "CAND-1",
            "holder_is_search_space": True,
        }
    ]


def release_kwargs(**overrides: Any) -> dict[str, Any]:
    """The smallest whole-release manifest ``seal_zero_trust_release`` accepts."""
    kwargs: dict[str, Any] = {
        "release_id": "REL-Z05-0001",
        "reconciliation": reconciliation(),
        "provenance_inputs": provenance_inputs(),
        "audit": lens_audit(),
        "surfaces": sealed_surfaces(),
        "authority_claims": clean_authority_claims(),
    }
    kwargs.update(overrides)
    return kwargs


# --- loaders over the actually-sealed artifacts --------------------------------


def load_final_reconciliation() -> dict[str, Any]:
    """The sealed Z04 final-release reconciliation facts, read from its report."""
    report = json.loads((repo_root() / Z04_REPORT).read_text(encoding="utf-8"))
    return {
        "status": report["status"],
        "completion_ready": report["completion_ready"],
        "contract_status": report["contract_status"],
        "package_status": report["package_status"],
    }


def load_lens_audit_document() -> dict[str, Any]:
    """The sealed 288-lens evolution audit result, read from reports/."""
    return json.loads((repo_root() / LENS_AUDIT).read_text(encoding="utf-8"))
