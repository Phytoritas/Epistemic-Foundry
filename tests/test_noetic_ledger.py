"""Append-only hash chain and receipt contracts."""

from __future__ import annotations

import json

import pytest

from epistemic_foundry.contracts import ContractViolation
from epistemic_foundry.noetic_ledger import (
    LedgerIntegrityError,
    NoeticLedger,
    build_artifact_receipt,
    build_effect_receipt,
)


def _append(ledger: NoeticLedger, event_type: str, payload: dict) -> dict:
    return ledger.append(
        event_type=event_type,
        aggregate_type="session",
        aggregate_id="FS-001",
        actor_id="ACTOR-test",
        run_id="RUN-0001",
        payload=payload,
    )


def test_empty_ledger_is_intact_and_has_no_tail(tmp_path) -> None:
    ledger = NoeticLedger(tmp_path / "ledger.jsonl")
    assert ledger.tail() is None
    assert ledger.length() == 0
    ledger.verify()


def test_chain_links_sequence_and_previous_hash(tmp_path) -> None:
    ledger = NoeticLedger(tmp_path / "ledger.jsonl")
    first = _append(ledger, "session.created", {"n": 1})
    second = _append(ledger, "session.advanced", {"n": 2})

    assert first["sequence"] == 1
    assert first["previous_event_hash"] is None
    assert second["sequence"] == 2
    assert second["previous_event_hash"] == first["event_hash"]
    ledger.verify()


def test_equal_payloads_hash_equally_and_differing_payloads_do_not(tmp_path) -> None:
    ledger = NoeticLedger(tmp_path / "ledger.jsonl")
    a = _append(ledger, "e", {"alpha": 1, "beta": 2})
    b = _append(ledger, "e", {"beta": 2, "alpha": 1})  # key order must not matter
    c = _append(ledger, "e", {"alpha": 1, "beta": 3})

    assert a["payload_hash"] == b["payload_hash"]
    assert a["payload_hash"] != c["payload_hash"]


def test_tampered_payload_hash_fails_verification(tmp_path) -> None:
    """Editing a stored record must break replay, not pass silently."""
    path = tmp_path / "ledger.jsonl"
    ledger = NoeticLedger(path)
    _append(ledger, "session.created", {"n": 1})
    _append(ledger, "session.advanced", {"n": 2})

    lines = path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[0])
    record["payload_hash"] = "sha256:" + "0" * 64
    lines[0] = json.dumps(record, sort_keys=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(LedgerIntegrityError) as excinfo:
        ledger.verify()
    assert "tampered" in str(excinfo.value)
    assert ledger.is_intact() is False


def test_removed_event_breaks_the_chain(tmp_path) -> None:
    path = tmp_path / "ledger.jsonl"
    ledger = NoeticLedger(path)
    _append(ledger, "a", {"n": 1})
    _append(ledger, "b", {"n": 2})
    _append(ledger, "c", {"n": 3})

    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join([lines[0], lines[2]]) + "\n", encoding="utf-8")

    with pytest.raises(LedgerIntegrityError):
        ledger.verify()


def test_reordered_events_break_the_chain(tmp_path) -> None:
    path = tmp_path / "ledger.jsonl"
    ledger = NoeticLedger(path)
    _append(ledger, "a", {"n": 1})
    _append(ledger, "b", {"n": 2})

    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join(reversed(lines)) + "\n", encoding="utf-8")

    with pytest.raises(LedgerIntegrityError):
        ledger.verify()


def test_artifact_receipt_without_validation_records_not_run(tmp_path) -> None:
    """An unverified artifact must read as unverified, never as PASS."""
    receipt = build_artifact_receipt(
        artifact_id="ART-0001",
        payload={"claim": "x"},
        locator=str(tmp_path / "artifact.json"),
        media_type="application/json",
        actor_id="ACTOR-test",
    )
    assert receipt["validation_results"] == [
        {
            "check": "schema_validation",
            "status": "NOT_RUN",
            "details": "no validation was executed for this artifact",
        }
    ]
    assert receipt["content_hash"].startswith("sha256:")
    assert receipt["byte_size"] > 0


def test_effect_receipt_forces_reconciliation_on_unknown() -> None:
    unknown = build_effect_receipt(
        intent_id="AI-1",
        run_id="RUN-1",
        status="UNKNOWN",
        idempotency_key="key-0001",
        started_at="2026-07-27T00:00:00+00:00",
    )
    succeeded = build_effect_receipt(
        intent_id="AI-1",
        run_id="RUN-1",
        status="SUCCEEDED",
        idempotency_key="key-0002",
        started_at="2026-07-27T00:00:00+00:00",
    )
    assert unknown["reconciliation_required"] is True
    assert succeeded["reconciliation_required"] is False


def test_effect_receipt_rejects_an_unknown_status() -> None:
    with pytest.raises(ContractViolation):
        build_effect_receipt(
            intent_id="AI-1",
            run_id="RUN-1",
            status="MOSTLY_FINE",  # type: ignore[arg-type]
            idempotency_key="key-0003",
            started_at="2026-07-27T00:00:00+00:00",
        )
