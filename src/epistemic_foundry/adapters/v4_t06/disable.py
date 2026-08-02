"""Disabling a backend, and what that does to work already in flight (T06).

Disabling is the one operation in this package that reaches backwards.  Turning
a backend off stops the next request, but the runs already imported from it
were accepted on the strength of a qualification that no longer stands, and
they do not stop being wrong just because nothing new arrives.  So a
disablement is not a flag: it is a record that does three things at once.

* *It deactivates the qualification.*  The chain head is withdrawn through the
  lifecycle module, so every later `assert_may_serve` refuses on its own and
  no separate "is it disabled?" check has to be remembered at each call site.
* *It marks the in-flight imports.*  Each imported run is re-derived through
  T05's own digest check and then carried into the record as requiring
  re-verification.  Marking is explicit rather than implied by the disablement's
  existence, so an import that was never handed to this function is visibly
  absent instead of quietly assumed covered.
* *It stays checkable afterwards.*  `assert_not_serving_after_disable` reads a
  routing record produced at or after the disablement and refuses if the
  disabled backend still served it.  That is the failure a disablement is
  supposed to prevent, so it is a refusal rather than a note.

Nothing here re-verifies anything.  Re-verification is somebody else's work;
this module records that it is owed.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..v4_t05 import assert_hash_rederives
from ..v4_t05.findings import (
    require_identifier,
    require_mapping,
    seal,
)
from .findings import _fail, require_instant
from .qualification_lifecycle import (
    STANDING_DEACTIVATED,
    build_chain,
    verified_chain,
    withdraw_qualification,
)


def _import_mark(entry: object, position: int) -> dict[str, Any]:
    """Re-derive one T05 import envelope and reduce it to what a mark needs.

    Both digests are checked through T05's helper, and the refusal is left to
    raise as itself: an edited import envelope is an integrity failure at the
    import boundary, not a disablement failure, and the record that was
    tampered with should be the one the error names.
    """
    envelope = dict(require_mapping(entry, f"in_flight_imports[{position}]"))
    assert_hash_rederives(envelope, "import_hash", f"in_flight_imports[{position}]")
    record = dict(
        require_mapping(
            envelope.get("imported_run"), f"in_flight_imports[{position}].imported_run"
        )
    )
    assert_hash_rederives(
        record, "record_hash", f"in_flight_imports[{position}].imported_run"
    )
    return {
        "import_hash": require_identifier(envelope["import_hash"], "import_hash"),
        "import_id": require_identifier(record.get("import_id"), "import_id"),
        "record_hash": require_identifier(record["record_hash"], "record_hash"),
        "requires_reverification": True,
        "target_session_id": require_identifier(
            record.get("target_session_id"), "target_session_id"
        ),
    }


def disable_backend(
    *,
    disablement_id: str,
    chain: Mapping[str, Any],
    disabled_at: str,
    reason: str,
    in_flight_imports: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Disable a backend and mark everything it left in flight.

    The returned record carries the rebuilt qualification chain, so the caller
    that disables a backend holds, in one value, both the proof that it can no
    longer serve and the list of imports whose standing it just changed.
    """
    verified = verified_chain(chain)
    require_instant(disabled_at, "disabled_at")
    if isinstance(in_flight_imports, (str, bytes)) or not isinstance(
        in_flight_imports, (list, tuple)
    ):
        _fail(
            "REVERIFICATION_UNMARKED",
            "in_flight_imports must be an array of imported-run envelopes",
            {"disablement_id": disablement_id},
        )
    marks = [
        _import_mark(entry, position)
        for position, entry in enumerate(in_flight_imports)
    ]
    identifiers = [mark["import_id"] for mark in marks]
    repeated = sorted({name for name in identifiers if identifiers.count(name) > 1})
    if repeated:
        _fail(
            "REVERIFICATION_UNMARKED",
            "an imported run was presented more than once",
            {"repeated": repeated},
        )
    deactivated = withdraw_qualification(
        withdrawal_id=require_identifier(disablement_id, "disablement_id"),
        record=verified["records"][-1],
        kind=STANDING_DEACTIVATED,
        at=disabled_at,
        reason=reason,
    )
    rebuilt = build_chain(
        chain_id=verified["chain_id"],
        records=[*verified["records"][:-1], deactivated],
    )
    return seal(
        {
            "backend_manifest_id": verified["backend_manifest_id"],
            "disabled_at": require_identifier(disabled_at, "disabled_at"),
            "disabled_chain": rebuilt,
            "disablement_id": require_identifier(disablement_id, "disablement_id"),
            "reason": require_identifier(reason, "reason"),
            "reverification_marks": sorted(marks, key=lambda mark: mark["import_id"]),
            "serving_permitted": False,
        },
        "disablement_hash",
    )


def _verified_disablement(disablement: Mapping[str, Any]) -> dict[str, Any]:
    value = dict(require_mapping(disablement, "disablement"))
    assert_hash_rederives(value, "disablement_hash", "disablement")
    if value.get("serving_permitted") is not False:
        _fail(
            "DISABLED_BACKEND_STILL_SERVING",
            "the disablement record does not record itself as non-serving",
            {"disablement_id": value.get("disablement_id")},
        )
    return value


def assert_reverification_marked(
    *, disablement: Mapping[str, Any], imports: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Refuse a disablement that left an in-flight import unmarked.

    `imports` is the set the caller believes was in flight.  The check is one
    way on purpose: a disablement holding a mark for an import nobody claims is
    harmless, while an import nobody marked keeps being read as if the backend
    behind it were still qualified.
    """
    verified = _verified_disablement(disablement)
    marks = verified.get("reverification_marks")
    if not isinstance(marks, list):
        _fail(
            "REVERIFICATION_UNMARKED",
            "the disablement carries no re-verification marks",
            {"disablement_id": verified.get("disablement_id")},
        )
    marked: set[str] = set()
    for position, mark in enumerate(marks):  # type: ignore[arg-type]
        entry = dict(require_mapping(mark, f"reverification_marks[{position}]"))
        if entry.get("requires_reverification") is not True:
            _fail(
                "REVERIFICATION_UNMARKED",
                f"reverification_marks[{position}] does not require re-verification",
                {"disablement_id": verified.get("disablement_id")},
            )
        marked.add(
            require_identifier(
                entry.get("import_id"), f"reverification_marks[{position}].import_id"
            )
        )
    if isinstance(imports, (str, bytes)) or not isinstance(imports, (list, tuple)):
        _fail(
            "REVERIFICATION_UNMARKED",
            "imports must be an array of imported-run envelopes",
            {"disablement_id": verified.get("disablement_id")},
        )
    claimed = [
        _import_mark(entry, position)["import_id"]
        for position, entry in enumerate(imports)
    ]
    unmarked = sorted(set(claimed) - marked)
    if unmarked:
        _fail(
            "REVERIFICATION_UNMARKED",
            "an in-flight imported run was not marked for re-verification",
            {
                "disablement_id": verified.get("disablement_id"),
                "marked": sorted(marked),
                "unmarked": unmarked,
            },
        )
    return seal(
        {
            "backend_manifest_id": verified["backend_manifest_id"],
            "disablement_hash": verified["disablement_hash"],
            "disablement_id": verified["disablement_id"],
            "marked_import_ids": sorted(marked),
            "serving_permitted": False,
        },
        "audit_hash",
    )


def assert_not_serving_after_disable(
    *, disablement: Mapping[str, Any], routing: Mapping[str, Any]
) -> dict[str, Any]:
    """Refuse a routing that let the disabled backend serve after the fact.

    Routings decided strictly before the disablement are left alone: they were
    correct when they were made, and rewriting their standing after the event
    would make the record say something the operator could not have known.
    """
    verified = _verified_disablement(disablement)
    record = dict(require_mapping(routing, "routing"))
    assert_hash_rederives(record, "routing_hash", "routing")
    decided = require_instant(record.get("as_of"), "routing.as_of")
    disabled = require_instant(verified.get("disabled_at"), "disabled_at")
    served = record.get("selected_backend_manifest_id")
    if decided >= disabled and served == verified["backend_manifest_id"]:
        _fail(
            "DISABLED_BACKEND_STILL_SERVING",
            "the disabled backend served a request decided after its disablement",
            {
                "as_of": record.get("as_of"),
                "backend_manifest_id": served,
                "disabled_at": verified.get("disabled_at"),
                "request_id": record.get("request_id"),
            },
        )
    return seal(
        {
            "as_of": require_identifier(record.get("as_of"), "as_of"),
            "backend_manifest_id": verified["backend_manifest_id"],
            "decided_before_disablement": decided < disabled,
            "disablement_id": verified["disablement_id"],
            "request_id": require_identifier(record.get("request_id"), "request_id"),
            "routing_hash": record["routing_hash"],
            "selected_backend_manifest_id": served,
        },
        "audit_hash",
    )
