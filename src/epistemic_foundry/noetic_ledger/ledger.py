"""Append-only, hash-chained event log.

Contract source: `schemas/event-record.schema.json`. Each appended record is
validated before it lands, its `previous_event_hash` must equal the digest of
the current tail, and `sequence` must be exactly `tail + 1`. A gap or a
mismatch is an integrity failure, not a recoverable warning: the whole value of
the chain is that a rewritten past cannot pass `verify()`.

Storage is a JSON Lines file. One record per line keeps append O(1) and lets a
truncated write be detected as a malformed final line instead of corrupting
earlier history.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterator

from ..contracts import ContractViolation, validate_artifact
from ..domain.hashing import hash_excluding, sha256_of_payload
from ..domain.ids import new_id
from ..domain.time import utc_now_iso

LEDGER_SCHEMA = "event-record"
LEDGER_SCHEMA_VERSION = "4.0.0"


class LedgerIntegrityError(RuntimeError):
    """The stored chain does not satisfy the append-only hash contract."""


class NoeticLedger:
    """Hash-chained event store backed by a JSONL file."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    # -- reading ---------------------------------------------------------

    def __iter__(self) -> Iterator[dict[str, Any]]:
        return self.events()

    def events(self) -> Iterator[dict[str, Any]]:
        """Yield stored events in append order."""
        if not self._path.is_file():
            return iter(())
        return self._read_events()

    def _read_events(self) -> Iterator[dict[str, Any]]:
        with self._path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    record = json.loads(stripped)
                except json.JSONDecodeError as exc:
                    raise LedgerIntegrityError(
                        f"{self._path}: line {line_number} is not valid JSON: {exc}"
                    ) from exc
                if not isinstance(record, dict):
                    raise LedgerIntegrityError(
                        f"{self._path}: line {line_number} is not a JSON object"
                    )
                yield record

    def tail(self) -> dict[str, Any] | None:
        """Last appended event, or None for an empty ledger."""
        last: dict[str, Any] | None = None
        for record in self.events():
            last = record
        return last

    def length(self) -> int:
        return sum(1 for _ in self.events())

    # -- writing ---------------------------------------------------------

    def append(
        self,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        actor_id: str,
        run_id: str,
        payload: Any,
        payload_artifact_id: str | None = None,
        occurred_at: str | None = None,
    ) -> dict[str, Any]:
        """Append one event and return the stored record.

        The caller supplies the payload; the ledger owns sequence numbering,
        chaining, and digests so no component can mint a record that skips the
        chain.
        """
        tail = self.tail()
        if tail is None:
            sequence = 1
            previous_hash = None
        else:
            sequence = int(tail["sequence"]) + 1
            previous_hash = tail["event_hash"]

        record: dict[str, Any] = {
            "event_id": new_id("EVT"),
            "run_id": run_id,
            "sequence": sequence,
            "event_type": event_type,
            "aggregate_type": aggregate_type,
            "aggregate_id": aggregate_id,
            "actor_id": actor_id,
            "payload_artifact_id": payload_artifact_id or new_id("ART"),
            "payload_hash": sha256_of_payload(payload),
            "previous_event_hash": previous_hash,
            "occurred_at": occurred_at or utc_now_iso(),
            "schema_version": LEDGER_SCHEMA_VERSION,
        }
        record["event_hash"] = hash_excluding(record, "event_hash")
        validate_artifact(LEDGER_SCHEMA, record)
        self._append_line(record)
        return record

    def _append_line(self, record: dict[str, Any]) -> None:
        line = json.dumps(record, sort_keys=True, ensure_ascii=False, allow_nan=False)
        with self._path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    # -- verification ----------------------------------------------------

    def verify(self) -> None:
        """Replay the chain; raise `LedgerIntegrityError` on the first break."""
        expected_sequence = 1
        previous_hash: str | None = None
        for record in self.events():
            validate_artifact(LEDGER_SCHEMA, record)
            if int(record["sequence"]) != expected_sequence:
                raise LedgerIntegrityError(
                    f"sequence gap: expected {expected_sequence}, found {record['sequence']}"
                )
            if record["previous_event_hash"] != previous_hash:
                raise LedgerIntegrityError(
                    f"chain break at sequence {record['sequence']}: "
                    f"previous_event_hash {record['previous_event_hash']!r} != {previous_hash!r}"
                )
            recomputed = hash_excluding(record, "event_hash")
            if recomputed != record["event_hash"]:
                raise LedgerIntegrityError(
                    f"tampered event at sequence {record['sequence']}: "
                    f"event_hash {record['event_hash']} != recomputed {recomputed}"
                )
            previous_hash = record["event_hash"]
            expected_sequence += 1

    def is_intact(self) -> bool:
        """Non-raising verification for status surfaces."""
        try:
            self.verify()
        except (LedgerIntegrityError, ContractViolation, OSError):
            return False
        return True
