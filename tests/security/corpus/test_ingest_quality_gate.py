from __future__ import annotations

import pytest

from epistemic_foundry.release import (
    SourceAccessDenied,
    build_source_integrity_report,
    export_permitted,
)
from epistemic_foundry.release.integrity import require_export_permitted


CONTENT_HASH = "sha256:" + "a" * 64


def check(
    check_id: str,
    status: str,
    details: str,
    evidence_id: str,
) -> dict[str, object]:
    return {
        "check_id": check_id,
        "status": status,
        "details": details,
        "evidence_artifact_ids": [evidence_id],
    }


def report(checks: list[dict[str, object]]) -> dict[str, object]:
    return build_source_integrity_report(
        document_id="DOC-K04-001",
        content_hash=CONTENT_HASH,
        checks=checks,
        policy_version="4.0.0-k04.1",
        report_id="SIR-K04-001",
        evaluated_at="2026-07-31T00:00:00.000Z",
    )


def test_active_content_is_quarantined_and_cannot_be_extracted_or_exported() -> None:
    integrity = report(
        [
            check(
                "active_content_inventory",
                "PASS",
                "Embedded script and launch-action inventory retained.",
                "ART-K04-ACTIVE-INVENTORY",
            ),
            check(
                "malware_scan",
                "FAIL",
                "Executable active content violates the ingest policy.",
                "ART-K04-MALWARE-SCAN",
            ),
            check(
                "prompt_injection_scan",
                "WARN",
                "Instruction-like spans retained as untrusted data.",
                "ART-K04-INJECTION-SCAN",
            ),
        ]
    )

    assert integrity["overall_status"] == "QUARANTINE"
    assert integrity["trusted_for_extraction"] is False
    assert export_permitted(integrity, licence="CC0", verbatim=False) is False
    assert export_permitted(integrity, licence="CC-BY", verbatim=True) is False
    with pytest.raises(SourceAccessDenied):
        require_export_permitted(integrity, licence="CC0", verbatim=False)


@pytest.mark.parametrize("check_id", ["provenance_verified", "tamper_evident"])
def test_identity_or_tamper_failure_is_quarantined(check_id: str) -> None:
    integrity = report(
        [
            check(
                check_id,
                "FAIL",
                "The retained bytes cannot be bound to the declared source identity.",
                f"ART-K04-{check_id.upper()}",
            )
        ]
    )

    assert integrity["overall_status"] == "QUARANTINE"
    assert integrity["trusted_for_extraction"] is False


def test_malformed_passive_parser_output_fails_closed_without_becoming_trusted() -> None:
    integrity = report(
        [
            check(
                "parser_structure_valid",
                "FAIL",
                "The retained parser output is malformed.",
                "ART-K04-PARSER-FAILURE",
            )
        ]
    )

    assert integrity["overall_status"] == "FAIL"
    assert integrity["trusted_for_extraction"] is False
    assert export_permitted(integrity, licence="CC0", verbatim=False) is False


def test_unchecked_content_never_defaults_to_pass() -> None:
    with pytest.raises(SourceAccessDenied, match="not trusted by default"):
        report([])


def test_extraction_permission_does_not_upgrade_restricted_export() -> None:
    integrity = report(
        [
            check(
                "source_integrity",
                "PASS",
                "Immutable bytes and provenance verified.",
                "ART-K04-INTEGRITY-PASS",
            )
        ]
    )

    assert integrity["overall_status"] == "PASS"
    assert integrity["trusted_for_extraction"] is True
    assert export_permitted(integrity, licence="all-rights-reserved", verbatim=False) is True
    assert export_permitted(integrity, licence="all-rights-reserved", verbatim=True) is False
    with pytest.raises(SourceAccessDenied, match="all-rights-reserved"):
        require_export_permitted(
            integrity,
            licence="all-rights-reserved",
            verbatim=True,
        )
