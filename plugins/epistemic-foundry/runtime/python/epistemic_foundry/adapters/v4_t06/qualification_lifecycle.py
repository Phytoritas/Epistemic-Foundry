"""The qualification lifecycle a backend serves under (T06).

Contract sources: `schemas/backend-adapter-qualification.schema.json` by way of
T05's `qualification_statuses`, and `shinka_adapter.backend`'s usable-verdict
set.  Neither vocabulary is restated here; the serving set is the intersection
of the two, computed on every call.

T05 answers "is this backend qualified?" once.  That answer has no duration, no
predecessor and no way to be taken back, and all three are what an integration
gate needs:

* *A verdict alone is not permission to serve.*  A qualification is opened with
  a validity window and can be withdrawn.  `assert_may_serve` decides against a
  caller-supplied instant and refuses naming the standing it found, so "the
  backend refused" and "the backend's qualification expired at 03:00" are the
  same event rather than two unrelated stories.
* *Requalification is a continuation, not a new fact.*  Each record after the
  first names the qualification it replaces and the sealed T05 binding hash of
  that predecessor.  A record that claims a later position without naming what
  came before it is a qualification appearing from nowhere, and is refused.
* *The head is the only record that serves.*  An earlier record in a verified
  chain is `replaced`; presenting it as current is refused under the same code
  as an expired one, because both are requests to serve under a qualification
  that is not the standing one.

Nothing here qualifies a backend — `qualify_backend_adapter` does, and its
record is carried in whole.  Every identifier and instant is supplied by the
caller, so a chain re-derives byte for byte on replay.
"""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from ...shinka_adapter.backend import USABLE_QUALIFICATION_STATUSES
from ..v4_t05 import assert_hash_rederives, qualification_statuses
from ..v4_t05.findings import (
    require_identifier,
    require_mapping,
    seal,
)
from .findings import _fail, require_instant

#: What a qualification record's standing can be at a given instant.  These are
#: this package's own words: no canonical schema declares a lifecycle for a
#: backend qualification, and borrowing another artifact's enum would assert a
#: shared contract that does not exist.  The names carry a `STANDING_` prefix so
#: that re-exporting them cannot put a canonical enum value into an `__all__`
#: list, which is a wire literal like any other.
STANDING_SERVING = "serving"
STANDING_REPLACED = "replaced"
STANDING_NOT_YET_ISSUED = "not_yet_issued"
STANDING_EXPIRED = "expired"
STANDING_REVOKED = "revoked"
STANDING_DEACTIVATED = "deactivated"
STANDING_STATUS_NOT_USABLE = "status_not_usable"

#: Ordered strongest-refusal-first; `standing` reports the first that holds.
STANDINGS: tuple[str, ...] = (
    STANDING_REVOKED,
    STANDING_DEACTIVATED,
    STANDING_REPLACED,
    STANDING_NOT_YET_ISSUED,
    STANDING_EXPIRED,
    STANDING_STATUS_NOT_USABLE,
    STANDING_SERVING,
)

#: The two ways a live qualification stops being one.  A revocation is a
#: judgement about the qualification; a deactivation is an operational decision
#: about the backend.  They are kept apart so a record says which happened.
WITHDRAWAL_KINDS: tuple[str, ...] = (STANDING_REVOKED, STANDING_DEACTIVATED)

#: The T05 binding fields a lifecycle record carries forward.
BINDING_FIELDS: tuple[str, ...] = (
    "backend_manifest_id",
    "binding_hash",
    "binding_id",
    "qualification",
)


def usable_statuses() -> tuple[str, ...]:
    """The verdicts that permit serving, composed from both owning modules.

    The schema declares the vocabulary and the shinka adapter declares which of
    it permits use.  Intersecting them on every call means a verdict dropped
    from either side stops permitting service here without this module being
    edited — and if the two stop overlapping at all, nothing serves.
    """
    declared = qualification_statuses()
    undeclared = sorted(set(USABLE_QUALIFICATION_STATUSES) - set(declared))
    if undeclared:
        _fail(
            "QUALIFICATION_NOT_SERVING",
            "the usable verdict set names verdicts the schema does not declare",
            {"declared": list(declared), "undeclared": undeclared},
        )
    usable = tuple(
        status for status in declared if status in USABLE_QUALIFICATION_STATUSES
    )
    if not usable:
        _fail(
            "QUALIFICATION_NOT_SERVING",
            "no declared verdict permits serving",
            {"declared": list(declared)},
        )
    return usable


def _binding_facts(binding: Mapping[str, Any]) -> dict[str, Any]:
    """Read the sealed T05 binding, re-deriving both digests on the way in.

    The digest checks are T05's, and their refusals are left to raise as
    themselves: an edited binding is a T05 integrity failure, not a T06
    lifecycle one, and relabelling it would hide which record was tampered.
    """
    record = dict(require_mapping(binding, "binding"))
    missing = [field for field in BINDING_FIELDS if field not in record]
    if missing:
        _fail(
            "QUALIFICATION_CHAIN_BROKEN",
            "the binding is missing fields a lifecycle record carries forward",
            {"missing": missing},
        )
    assert_hash_rederives(record, "binding_hash", "binding")
    qualification = dict(require_mapping(record["qualification"], "qualification"))
    assert_hash_rederives(qualification, "qualification_hash", "qualification")
    return {
        "backend_manifest_id": require_identifier(
            record["backend_manifest_id"], "backend_manifest_id"
        ),
        "binding_hash": require_identifier(record["binding_hash"], "binding_hash"),
        "binding_id": require_identifier(record["binding_id"], "binding_id"),
        "qualification_hash": require_identifier(
            qualification["qualification_hash"], "qualification_hash"
        ),
        "qualification_id": require_identifier(
            qualification.get("qualification_id"), "qualification_id"
        ),
        "status": require_identifier(qualification.get("status"), "status"),
    }


def _lifecycle_record(
    *,
    lifecycle_id: str,
    binding: Mapping[str, Any],
    issued_at: str,
    expires_at: str,
    sequence: int,
    previous_qualification_id: str | None,
    previous_binding_hash: str | None,
) -> dict[str, Any]:
    facts = _binding_facts(binding)
    opened = require_instant(issued_at, "issued_at")
    closed = require_instant(expires_at, "expires_at")
    if opened >= closed:
        _fail(
            "QUALIFICATION_WINDOW_INVALID",
            "a validity window must open strictly before it closes",
            {"expires_at": expires_at, "issued_at": issued_at},
        )
    return seal(
        {
            "backend_manifest_id": facts["backend_manifest_id"],
            "binding_hash": facts["binding_hash"],
            "binding_id": facts["binding_id"],
            "expires_at": require_identifier(expires_at, "expires_at"),
            "issued_at": require_identifier(issued_at, "issued_at"),
            "lifecycle_id": require_identifier(lifecycle_id, "lifecycle_id"),
            "previous_binding_hash": previous_binding_hash,
            "previous_qualification_id": previous_qualification_id,
            "qualification_hash": facts["qualification_hash"],
            "qualification_id": facts["qualification_id"],
            "sequence": sequence,
            "status": facts["status"],
            "withdrawal": None,
        },
        "record_hash",
    )


def open_qualification(
    *,
    lifecycle_id: str,
    binding: Mapping[str, Any],
    issued_at: str,
    expires_at: str,
) -> dict[str, Any]:
    """Open a lifecycle at its first qualification.

    Separate from `requalify` on purpose.  If one function took an optional
    predecessor, every requalification could omit it and become a first
    qualification by accident, which is precisely the chain break this package
    is meant to catch.
    """
    return _lifecycle_record(
        lifecycle_id=lifecycle_id,
        binding=binding,
        issued_at=issued_at,
        expires_at=expires_at,
        sequence=1,
        previous_qualification_id=None,
        previous_binding_hash=None,
    )


def requalify(
    *,
    previous: Mapping[str, Any],
    binding: Mapping[str, Any],
    issued_at: str,
    expires_at: str,
) -> dict[str, Any]:
    """Extend a lifecycle with a new qualification of the same backend.

    The predecessor is required, re-derived, and named in the new record by
    both its qualification id and the sealed T05 binding hash behind it.  The
    binding hash is used rather than the predecessor's own record hash because
    a withdrawal rewrites the head record, and a chain whose links broke every
    time a qualification was revoked would be unverifiable exactly when it
    mattered most.
    """
    earlier = dict(require_mapping(previous, "previous"))
    assert_hash_rederives(earlier, "record_hash", "previous")
    facts = _binding_facts(binding)
    if facts["backend_manifest_id"] != earlier.get("backend_manifest_id"):
        _fail(
            "BACKEND_IDENTITY_MISMATCH",
            "a requalification must describe the backend it continues",
            {
                "backend_manifest_id": facts["backend_manifest_id"],
                "previous_backend_manifest_id": earlier.get("backend_manifest_id"),
            },
        )
    if facts["qualification_id"] == earlier.get("qualification_id"):
        _fail(
            "QUALIFICATION_CHAIN_BROKEN",
            "a requalification must be a distinct qualification record",
            {"qualification_id": facts["qualification_id"]},
        )
    later = require_instant(issued_at, "issued_at")
    if later < require_instant(earlier.get("issued_at"), "previous.issued_at"):
        _fail(
            "QUALIFICATION_WINDOW_INVALID",
            "a requalification cannot be issued before the record it replaces",
            {"issued_at": issued_at, "previous_issued_at": earlier.get("issued_at")},
        )
    sequence = earlier.get("sequence")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
        _fail(
            "QUALIFICATION_CHAIN_BROKEN",
            "the predecessor does not declare a usable chain position",
            {"sequence": sequence},
        )
    return _lifecycle_record(
        lifecycle_id=require_identifier(earlier.get("lifecycle_id"), "lifecycle_id"),
        binding=binding,
        issued_at=issued_at,
        expires_at=expires_at,
        sequence=int(sequence) + 1,
        previous_qualification_id=require_identifier(
            earlier.get("qualification_id"), "previous.qualification_id"
        ),
        previous_binding_hash=require_identifier(
            earlier.get("binding_hash"), "previous.binding_hash"
        ),
    )


def withdraw_qualification(
    *,
    withdrawal_id: str,
    record: Mapping[str, Any],
    kind: str,
    at: str,
    reason: str,
) -> dict[str, Any]:
    """Take back a qualification, as a revocation or as a deactivation.

    The withdrawal is written into the record and resealed rather than kept in
    a side list, so a reader holding the record cannot miss it.
    """
    current = dict(require_mapping(record, "record"))
    assert_hash_rederives(current, "record_hash", "record")
    if kind not in WITHDRAWAL_KINDS:
        _fail(
            "QUALIFICATION_NOT_SERVING",
            "a withdrawal must say which kind of withdrawal it is",
            {"declared": list(WITHDRAWAL_KINDS), "kind": kind},
        )
    if current.get("withdrawal") is not None:
        _fail(
            "QUALIFICATION_NOT_SERVING",
            "the qualification has already been withdrawn",
            {"qualification_id": current.get("qualification_id")},
        )
    moment = require_instant(at, "at")
    if moment < require_instant(current.get("issued_at"), "issued_at"):
        _fail(
            "QUALIFICATION_WINDOW_INVALID",
            "a qualification cannot be withdrawn before it was issued",
            {"at": at, "issued_at": current.get("issued_at")},
        )
    withdrawal = {
        "at": require_identifier(at, "at"),
        "kind": kind,
        "reason": require_identifier(reason, "reason"),
        "withdrawal_id": require_identifier(withdrawal_id, "withdrawal_id"),
    }
    return seal({**current, "withdrawal": withdrawal}, "record_hash")


def _check_link(
    position: int, earlier: Mapping[str, Any], later: Mapping[str, Any]
) -> None:
    if later.get("previous_qualification_id") != earlier.get("qualification_id"):
        _fail(
            "QUALIFICATION_CHAIN_BROKEN",
            f"records[{position}] does not name the qualification it replaces",
            {
                "expected": earlier.get("qualification_id"),
                "named": later.get("previous_qualification_id"),
                "position": position,
            },
        )
    if later.get("previous_binding_hash") != earlier.get("binding_hash"):
        _fail(
            "QUALIFICATION_CHAIN_BROKEN",
            f"records[{position}] does not name the binding it continues",
            {
                "expected": earlier.get("binding_hash"),
                "named": later.get("previous_binding_hash"),
                "position": position,
            },
        )


def build_chain(
    *, chain_id: str, records: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Verify a qualification history end to end and seal it as one record.

    Every position is checked rather than only the head: a chain is evidence
    that the current qualification descends from an unbroken line, and a break
    three records back is exactly the kind of gap a head-only check would pass.
    """
    if isinstance(records, (str, bytes)) or not isinstance(records, (list, tuple)):
        _fail(
            "QUALIFICATION_CHAIN_BROKEN",
            "records must be an array of qualification records",
            {"chain_id": chain_id},
        )
    verified: list[dict[str, Any]] = []
    for position, entry in enumerate(records):
        current = dict(require_mapping(entry, f"records[{position}]"))
        assert_hash_rederives(current, "record_hash", f"records[{position}]")
        if current.get("sequence") != position + 1:
            _fail(
                "QUALIFICATION_CHAIN_BROKEN",
                f"records[{position}] declares a position it does not occupy",
                {"declared": current.get("sequence"), "position": position + 1},
            )
        if position == 0:
            if (
                current.get("previous_qualification_id") is not None
                or current.get("previous_binding_hash") is not None
            ):
                _fail(
                    "QUALIFICATION_CHAIN_BROKEN",
                    "the first record names a predecessor the chain does not hold",
                    {"named": current.get("previous_qualification_id")},
                )
        else:
            if current.get("previous_qualification_id") is None:
                _fail(
                    "QUALIFICATION_CHAIN_BROKEN",
                    f"records[{position}] continues a chain it does not name",
                    {"position": position},
                )
            _check_link(position, verified[-1], current)
            if current.get("lifecycle_id") != verified[0].get("lifecycle_id"):
                _fail(
                    "QUALIFICATION_CHAIN_BROKEN",
                    f"records[{position}] belongs to another lifecycle",
                    {
                        "lifecycle_id": current.get("lifecycle_id"),
                        "position": position,
                    },
                )
            if current.get("backend_manifest_id") != verified[0].get(
                "backend_manifest_id"
            ):
                _fail(
                    "BACKEND_IDENTITY_MISMATCH",
                    f"records[{position}] describes another backend",
                    {
                        "backend_manifest_id": current.get("backend_manifest_id"),
                        "position": position,
                    },
                )
        verified.append(current)
    if not verified:
        _fail(
            "QUALIFICATION_CHAIN_BROKEN",
            "a qualification chain must hold at least one record",
            {"chain_id": chain_id},
        )
    head = verified[-1]
    return seal(
        {
            "backend_manifest_id": head["backend_manifest_id"],
            "chain_id": require_identifier(chain_id, "chain_id"),
            "head_qualification_id": head["qualification_id"],
            "length": len(verified),
            "lifecycle_id": head["lifecycle_id"],
            "records": verified,
        },
        "chain_hash",
    )


def verified_chain(chain: Mapping[str, Any]) -> dict[str, Any]:
    """Re-derive a chain's digest and prove it still holds its own records.

    A digest alone does not make a chain: a hand-built envelope with no
    `records` re-derives perfectly and answers every question with a KeyError,
    so the shape is checked wherever a chain is read.  The copy returned is
    detached, so a chain embedded in a fallback declaration cannot be changed
    afterwards through the mapping the caller still holds.
    """
    value = dict(require_mapping(chain, "chain"))
    assert_hash_rederives(value, "chain_hash", "chain")
    records = value.get("records")
    if not isinstance(records, list) or not records:
        _fail(
            "QUALIFICATION_CHAIN_BROKEN",
            "the chain holds no qualification records",
            {"chain_id": value.get("chain_id")},
        )
    rebuilt = build_chain(
        chain_id=require_identifier(value.get("chain_id"), "chain_id"),
        records=records,
    )
    if rebuilt != value:
        _fail(
            "QUALIFICATION_CHAIN_BROKEN",
            "the supplied chain is not the exact canonical record chain",
            {
                "chain_id": value.get("chain_id"),
                "recorded_chain_hash": value.get("chain_hash"),
                "rebuilt_chain_hash": rebuilt.get("chain_hash"),
            },
        )
    return json.loads(json.dumps(rebuilt))


def _record_standing(record: Mapping[str, Any], as_of: str) -> str:
    observed = require_instant(as_of, "as_of")
    issued = require_instant(record.get("issued_at"), "issued_at")
    if observed < issued:
        return STANDING_NOT_YET_ISSUED
    withdrawal = record.get("withdrawal")
    if withdrawal is not None:
        withdrawal_record = dict(require_mapping(withdrawal, "withdrawal"))
        kind = withdrawal_record.get("kind")
        if kind not in WITHDRAWAL_KINDS:
            _fail(
                "QUALIFICATION_NOT_SERVING",
                "the withdrawal does not say which kind of withdrawal it is",
                {"kind": kind},
            )
        effective = require_instant(withdrawal_record.get("at"), "withdrawal.at")
        if observed >= effective:
            return str(kind)
    if observed >= require_instant(record.get("expires_at"), "expires_at"):
        return STANDING_EXPIRED
    if record.get("status") not in usable_statuses():
        return STANDING_STATUS_NOT_USABLE
    return STANDING_SERVING


def standing(
    *, chain: Mapping[str, Any], as_of: str, qualification_id: str | None = None
) -> str:
    """The standing of one qualification in a verified chain at an instant.

    Any record other than the head is `replaced` whatever its own window says:
    a superseded qualification does not become servable again by outliving the
    one that replaced it.
    """
    verified = verified_chain(chain)
    records = verified["records"]
    head = records[-1]
    if qualification_id is None:
        return _record_standing(head, as_of)
    wanted = require_identifier(qualification_id, "qualification_id")
    known = [record for record in records if record["qualification_id"] == wanted]
    if not known:
        _fail(
            "QUALIFICATION_CHAIN_BROKEN",
            "the chain holds no such qualification",
            {"chain_id": verified["chain_id"], "qualification_id": wanted},
        )
    if wanted != head["qualification_id"]:
        return STANDING_REPLACED
    return _record_standing(head, as_of)


def assert_may_serve(
    *,
    permit_id: str,
    chain: Mapping[str, Any],
    as_of: str,
    qualification_id: str | None = None,
) -> dict[str, Any]:
    """Permit this backend to serve at this instant, or refuse naming why not.

    The refusal carries both the standing and the schema verdict, so a caller
    handling it can tell "the qualification lapsed" from "this backend was
    never qualified" without inspecting the chain itself.
    """
    verified = verified_chain(chain)
    found = standing(chain=verified, as_of=as_of, qualification_id=qualification_id)
    head = verified["records"][-1]
    if found != STANDING_SERVING:
        _fail(
            "QUALIFICATION_NOT_SERVING",
            f"the qualification is {found} at {as_of}",
            {
                "as_of": as_of,
                "backend_manifest_id": verified["backend_manifest_id"],
                "qualification_id": qualification_id or head["qualification_id"],
                "standing": found,
                "status": head["status"],
            },
        )
    return seal(
        {
            "as_of": require_identifier(as_of, "as_of"),
            "backend_manifest_id": verified["backend_manifest_id"],
            "binding_hash": head["binding_hash"],
            "chain_hash": verified["chain_hash"],
            "chain_id": verified["chain_id"],
            "expires_at": head["expires_at"],
            "permit_id": require_identifier(permit_id, "permit_id"),
            "qualification_id": head["qualification_id"],
            "standing": found,
            "status": head["status"],
        },
        "permit_hash",
    )
