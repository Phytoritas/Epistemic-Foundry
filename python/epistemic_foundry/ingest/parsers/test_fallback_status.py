from __future__ import annotations

import hashlib
import json

import pytest

from .adapters import (
    PARSER_ADAPTER_VERSION,
    ArtifactEnvelope,
    FallbackDisposition,
    ParserContractError,
    ParserPin,
    ParserRole,
    ParserStatus,
    adapt_docling_artifact,
    adapt_fallback_artifact,
    blocked_attempt,
    resolve_fallback,
)


def digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def pin(role: ParserRole) -> ParserPin:
    values = {
        ParserRole.DOCLING_LAYOUT: ("docling", "2.41.0"),
        ParserRole.GROBID_STRUCTURE: ("grobid", "0.8.2"),
        ParserRole.FALLBACK: ("pypdf-fallback", "5.9.0"),
    }
    parser_id, version = values[role]
    return ParserPin(
        parser_id=parser_id,
        role=role,
        exact_version=version,
        executable_digest=digest(f"{parser_id}-{version}".encode()),
        adapter_version=PARSER_ADAPTER_VERSION,
        profile_hash=digest(f"{parser_id}-profile".encode()),
    )


def payload(parser_pin: ParserPin, *, text: str = "Fallback source text") -> bytes:
    value = {
        "parser_version": parser_pin.exact_version,
        "profile_hash": parser_pin.profile_hash,
        "elements": [
            {
                "logical_address": "body/section[0]/paragraph[0]",
                "kind": "PARAGRAPH",
                "text": text,
                "page": 1,
                "bbox": [10, 10, 300, 40],
                "char_start": 0,
                "char_end": len(text),
                "reading_order": 0,
                "links": [],
                "row_headers": [],
                "column_headers": [],
                "confidence": 0.75,
            }
        ],
    }
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def envelope(parser_pin: ParserPin, *, malformed: bool = False) -> ArtifactEnvelope:
    output = b"{" if malformed else payload(parser_pin)
    return ArtifactEnvelope(
        artifact_id=f"ART-{parser_pin.role.value}",
        source_artifact_id="ART-SOURCE-0001",
        media_type="application/json",
        content_hash=digest(output),
        payload=output,
    )


def primary_success():
    parser_pin = pin(ParserRole.DOCLING_LAYOUT)
    return adapt_docling_artifact(parser_pin, envelope(parser_pin))


def primary_failure():
    parser_pin = pin(ParserRole.DOCLING_LAYOUT)
    return adapt_docling_artifact(parser_pin, envelope(parser_pin, malformed=True))


def fallback_success():
    parser_pin = pin(ParserRole.FALLBACK)
    return adapt_fallback_artifact(parser_pin, envelope(parser_pin))


def fallback_failure():
    parser_pin = pin(ParserRole.FALLBACK)
    return adapt_fallback_artifact(parser_pin, envelope(parser_pin, malformed=True))


def test_fallback_status_test_primary_success_does_not_use_fallback() -> None:
    primary = primary_success()
    result = resolve_fallback(primary)

    assert result.disposition is FallbackDisposition.NOT_REQUIRED
    assert result.terminal_status is ParserStatus.PASS
    assert result.primary is primary
    assert result.fallback is None
    assert result.selected_stream is primary.stream


def test_fallback_status_test_successful_primary_cannot_be_silently_replaced() -> None:
    with pytest.raises(ParserContractError) as raised:
        resolve_fallback(primary_success(), fallback_success())

    assert raised.value.code == "FALLBACK_NOT_ALLOWED"


def test_fallback_status_test_failed_primary_without_fallback_remains_failed() -> None:
    primary = primary_failure()
    result = resolve_fallback(primary)

    assert result.disposition is FallbackDisposition.PRIMARY_FAILED_NO_FALLBACK
    assert result.terminal_status is ParserStatus.FAIL
    assert result.primary.error_code == "PARSER_OUTPUT_MALFORMED"
    assert result.selected_stream is None


def test_fallback_status_test_blocked_primary_without_fallback_remains_blocked() -> None:
    primary = blocked_attempt(
        pin(ParserRole.GROBID_STRUCTURE),
        "GROBID_BACKEND_UNAVAILABLE",
        "the pinned GROBID backend is unavailable",
    )
    result = resolve_fallback(primary)

    assert result.disposition is FallbackDisposition.PRIMARY_BLOCKED_NO_FALLBACK
    assert result.terminal_status is ParserStatus.BLOCKED
    assert result.primary.error_code == "GROBID_BACKEND_UNAVAILABLE"


def test_fallback_status_test_fallback_use_retains_primary_failure() -> None:
    primary = primary_failure()
    fallback = fallback_success()
    result = resolve_fallback(primary, fallback)

    assert result.disposition is FallbackDisposition.FALLBACK_USED
    assert result.terminal_status is ParserStatus.PARTIAL
    assert result.primary is primary
    assert result.primary.error_code == "PARSER_OUTPUT_MALFORMED"
    assert result.fallback is fallback
    assert result.selected_stream is fallback.stream


def test_fallback_status_test_fallback_use_retains_primary_blocker() -> None:
    primary = blocked_attempt(
        pin(ParserRole.GROBID_STRUCTURE),
        "GROBID_CREDENTIAL_UNAVAILABLE",
        "the required backend credential is unavailable",
    )
    fallback = fallback_success()
    result = resolve_fallback(primary, fallback)

    assert result.disposition is FallbackDisposition.FALLBACK_USED
    assert result.terminal_status is ParserStatus.PARTIAL
    assert result.primary.status is ParserStatus.BLOCKED
    assert result.primary.error_code == "GROBID_CREDENTIAL_UNAVAILABLE"


def test_fallback_status_test_failed_fallback_retains_both_errors() -> None:
    primary = primary_failure()
    fallback = fallback_failure()
    result = resolve_fallback(primary, fallback)

    assert result.disposition is FallbackDisposition.FALLBACK_FAILED
    assert result.terminal_status is ParserStatus.FAIL
    assert result.primary.error_code == "PARSER_OUTPUT_MALFORMED"
    assert result.fallback is not None
    assert result.fallback.error_code == "PARSER_OUTPUT_MALFORMED"
    assert result.selected_stream is None


def test_fallback_status_test_blocked_fallback_is_visible() -> None:
    fallback = blocked_attempt(
        pin(ParserRole.FALLBACK),
        "FALLBACK_BACKEND_UNAVAILABLE",
        "the pinned fallback backend is unavailable",
    )
    result = resolve_fallback(primary_failure(), fallback)

    assert result.disposition is FallbackDisposition.FALLBACK_BLOCKED
    assert result.terminal_status is ParserStatus.BLOCKED
    assert result.fallback is fallback
    assert result.selected_stream is None


def test_fallback_status_test_non_fallback_role_is_rejected() -> None:
    wrong_role = primary_failure()
    with pytest.raises(ParserContractError) as raised:
        resolve_fallback(primary_failure(), wrong_role)

    assert raised.value.code == "FALLBACK_ROLE_MISMATCH"


def test_fallback_status_test_fallback_cannot_be_primary() -> None:
    with pytest.raises(ParserContractError) as raised:
        resolve_fallback(fallback_success())

    assert raised.value.code == "FALLBACK_PRIMARY_INVALID"


def test_fallback_status_test_resolution_hash_is_replay_stable() -> None:
    first = resolve_fallback(primary_failure(), fallback_success())
    second = resolve_fallback(primary_failure(), fallback_success())

    assert first.resolution_hash == second.resolution_hash
    assert first.projection() == second.projection()


def test_fallback_status_test_invalid_blocked_code_is_rejected() -> None:
    with pytest.raises(ParserContractError) as raised:
        blocked_attempt(
            pin(ParserRole.GROBID_STRUCTURE),
            "backend unavailable",
            "the backend is unavailable",
        )

    assert raised.value.code == "PARSER_ATTEMPT_INVALID"


def test_fallback_status_test_missing_locator_never_becomes_success() -> None:
    parser_pin = pin(ParserRole.FALLBACK)
    value = json.loads(payload(parser_pin))
    value["elements"][0].update(
        {"page": None, "bbox": None, "char_start": None, "char_end": None}
    )
    output = json.dumps(value, sort_keys=True).encode()
    invalid = ArtifactEnvelope(
        artifact_id="ART-FALLBACK",
        source_artifact_id="ART-SOURCE-0001",
        media_type="application/json",
        content_hash=digest(output),
        payload=output,
    )

    attempt = adapt_fallback_artifact(parser_pin, invalid)
    result = resolve_fallback(primary_failure(), attempt)

    assert attempt.status is ParserStatus.FAIL
    assert attempt.error_code == "PARSER_PROVENANCE_MISSING"
    assert result.disposition is FallbackDisposition.FALLBACK_FAILED
    assert result.terminal_status is ParserStatus.FAIL
