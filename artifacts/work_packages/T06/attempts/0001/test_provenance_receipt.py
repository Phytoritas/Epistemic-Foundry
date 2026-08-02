"""provenance_and_receipt_audit — every gate decision is a self-proving receipt.

The gate settles no external effect of its own, so what it must prove is that
each record it emits re-derives byte for byte from its own published fields and
that replaying the same identified call reproduces the identical receipt.  The
hash covers the record; the disablement carries the marks it made; the permit,
the routing and the audits each re-derive their own digest; and no call mutates
the binding, chain or import it was handed.  There is no clock and no random draw
on any of these paths, so determinism is a property of the modules rather than of
the machine they ran on.
"""

from __future__ import annotations

import copy

from epistemic_foundry.adapters.v4_t06 import (
    assert_fallback_recorded,
    assert_may_serve,
    assert_not_serving_after_disable,
    assert_reverification_marked,
    disable_backend,
    open_qualification,
    route_request,
)
from epistemic_foundry.domain.hashing import hash_excluding
from fixtures import (
    AFTER_EXPIRY,
    EXPIRES_AT,
    ISSUED_AT,
    REQUESTED_CAPABILITIES,
    WITHIN_WINDOW,
    binding,
    chain,
    fallback_chain,
    imported_run,
)


def test_the_record_hash_covers_the_opened_qualification() -> None:
    record = open_qualification(
        lifecycle_id="T06-LIFE-1",
        binding=binding(),
        issued_at=ISSUED_AT,
        expires_at=EXPIRES_AT,
    )

    assert record["record_hash"] == hash_excluding(record, "record_hash")


def test_the_chain_hash_covers_the_verified_chain() -> None:
    built = chain()

    assert built["chain_hash"] == hash_excluding(built, "chain_hash")


def test_the_permit_hash_covers_the_permit() -> None:
    permit = assert_may_serve(permit_id="PERMIT-1", chain=chain(), as_of=WITHIN_WINDOW)

    assert permit["permit_hash"] == hash_excluding(permit, "permit_hash")


def test_the_routing_hash_covers_the_routing() -> None:
    routed = route_request(
        request_id="REQ-1",
        fallback_chain=fallback_chain(),
        requested_capabilities=list(REQUESTED_CAPABILITIES),
        as_of=AFTER_EXPIRY,
    )

    assert routed["routing_hash"] == hash_excluding(routed, "routing_hash")


def test_the_disablement_hash_covers_the_disablement_and_its_marks() -> None:
    disablement = disable_backend(
        disablement_id="DIS-1",
        chain=chain(),
        disabled_at=WITHIN_WINDOW,
        reason="operational stand-down",
        in_flight_imports=[imported_run()],
    )

    assert disablement["disablement_hash"] == hash_excluding(
        disablement, "disablement_hash"
    )
    assert disablement["reverification_marks"][0]["import_id"] == "IMP-T06-1"


def test_the_fallback_audit_hash_covers_the_audit() -> None:
    routed = route_request(
        request_id="REQ-2",
        fallback_chain=fallback_chain(),
        requested_capabilities=list(REQUESTED_CAPABILITIES),
        as_of=AFTER_EXPIRY,
    )
    audit = assert_fallback_recorded(
        audit_id="AUD-1", routing=routed, fallback_chain=fallback_chain()
    )

    assert audit["audit_hash"] == hash_excluding(audit, "audit_hash")


def test_a_permit_replays_byte_for_byte() -> None:
    first = assert_may_serve(permit_id="PERMIT-1", chain=chain(), as_of=WITHIN_WINDOW)
    second = assert_may_serve(permit_id="PERMIT-1", chain=chain(), as_of=WITHIN_WINDOW)

    assert first == second
    assert first["permit_hash"] == second["permit_hash"]


def test_a_routing_replays_byte_for_byte() -> None:
    first = route_request(
        request_id="REQ-1",
        fallback_chain=fallback_chain(),
        requested_capabilities=list(REQUESTED_CAPABILITIES),
        as_of=AFTER_EXPIRY,
    )
    second = route_request(
        request_id="REQ-1",
        fallback_chain=fallback_chain(),
        requested_capabilities=list(REQUESTED_CAPABILITIES),
        as_of=AFTER_EXPIRY,
    )

    assert first == second
    assert first["routing_hash"] == second["routing_hash"]


def test_a_disablement_replays_byte_for_byte() -> None:
    first = disable_backend(
        disablement_id="DIS-1",
        chain=chain(),
        disabled_at=WITHIN_WINDOW,
        reason="operational stand-down",
        in_flight_imports=[imported_run()],
    )
    second = disable_backend(
        disablement_id="DIS-1",
        chain=chain(),
        disabled_at=WITHIN_WINDOW,
        reason="operational stand-down",
        in_flight_imports=[imported_run()],
    )

    assert first == second
    assert first["disablement_hash"] == second["disablement_hash"]


def test_the_after_disable_audit_re_derives_and_names_its_routing() -> None:
    disablement = disable_backend(
        disablement_id="DIS-2",
        chain=chain(),
        disabled_at=WITHIN_WINDOW,
        reason="operational stand-down",
    )
    earlier = route_request(
        request_id="REQ-3",
        fallback_chain=fallback_chain(),
        requested_capabilities=list(REQUESTED_CAPABILITIES),
        as_of=ISSUED_AT,
    )
    audit = assert_not_serving_after_disable(disablement=disablement, routing=earlier)

    assert audit["audit_hash"] == hash_excluding(audit, "audit_hash")
    assert audit["routing_hash"] == earlier["routing_hash"]


def test_the_reverification_audit_re_derives_its_own_digest() -> None:
    disablement = disable_backend(
        disablement_id="DIS-3",
        chain=chain(),
        disabled_at=WITHIN_WINDOW,
        reason="operational stand-down",
        in_flight_imports=[imported_run()],
    )
    audit = assert_reverification_marked(
        disablement=disablement, imports=[imported_run()]
    )

    assert audit["audit_hash"] == hash_excluding(audit, "audit_hash")


def test_opening_a_qualification_never_mutates_its_binding() -> None:
    supplied = binding()
    before = copy.deepcopy(supplied)

    open_qualification(
        lifecycle_id="T06-LIFE-1",
        binding=supplied,
        issued_at=ISSUED_AT,
        expires_at=EXPIRES_AT,
    )

    assert supplied == before


def test_disabling_never_mutates_the_import_it_marks() -> None:
    supplied = imported_run()
    before = copy.deepcopy(supplied)

    disable_backend(
        disablement_id="DIS-4",
        chain=chain(),
        disabled_at=WITHIN_WINDOW,
        reason="operational stand-down",
        in_flight_imports=[supplied],
    )

    assert supplied == before


def test_a_permit_never_mutates_the_chain_it_was_given() -> None:
    supplied = chain()
    before = copy.deepcopy(supplied)

    assert_may_serve(permit_id="PERMIT-1", chain=supplied, as_of=WITHIN_WINDOW)

    assert supplied == before
