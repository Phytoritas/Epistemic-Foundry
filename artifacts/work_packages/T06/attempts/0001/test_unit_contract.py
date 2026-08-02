"""unit_and_contract_tests — the gate behaves the way T06 claims it behaves.

A qualification is opened with a window and a predecessor-free head; a
requalification continues the same lifecycle one position deeper; a chain
verifies end to end; a standing is decided against a caller-supplied instant and
names why it is not serving; a declared fallback chain ends in the always-present
core; a routed request steps down the chain only for a standing reason and
records every step; and disabling a backend both withdraws its head qualification
and marks the runs it left in flight.  None of these reads a clock, so every
record re-derives across runs.
"""

from __future__ import annotations

from epistemic_foundry.adapters.v4_t06 import (
    NATIVE_CORE_MEMBER_ID,
    STANDING_DEACTIVATED,
    STANDING_EXPIRED,
    STANDING_REPLACED,
    STANDING_REVOKED,
    STANDING_SERVING,
    STANDING_STATUS_NOT_USABLE,
    assert_fallback_recorded,
    assert_may_serve,
    assert_not_serving_after_disable,
    assert_reverification_marked,
    build_chain,
    disable_backend,
    open_qualification,
    requalify,
    route_request,
    standing,
    usable_statuses,
    withdraw_qualification,
)
from fixtures import (
    AFTER_EXPIRY,
    AFTER_STANDBY_EXPIRY,
    EXPIRES_AT,
    ISSUED_AT,
    PRIMARY_MANIFEST_ID,
    REQUALIFIED_AT,
    REQUESTED_CAPABILITIES,
    WITHIN_WINDOW,
    binding,
    chain,
    fallback_chain,
    genesis,
    imported_run,
    requalified,
    requalified_chain,
    rejecting_chain,
    second_binding,
)


# --- qualification lifecycle ---------------------------------------------


def test_the_opened_head_carries_a_window_and_no_predecessor() -> None:
    record = open_qualification(
        lifecycle_id="T06-LIFE-1",
        binding=binding(),
        issued_at=ISSUED_AT,
        expires_at=EXPIRES_AT,
    )

    assert record["sequence"] == 1
    assert record["previous_qualification_id"] is None
    assert record["previous_binding_hash"] is None
    assert record["withdrawal"] is None
    assert record["status"] in usable_statuses()


def test_a_requalification_continues_the_line_one_position_deeper() -> None:
    first = genesis()
    later = requalify(
        previous=first,
        binding=second_binding(),
        issued_at=REQUALIFIED_AT,
        expires_at="2026-10-01T00:00:00+00:00",
    )

    assert later["sequence"] == first["sequence"] + 1
    assert later["lifecycle_id"] == first["lifecycle_id"]
    assert later["previous_qualification_id"] == first["qualification_id"]
    assert later["previous_binding_hash"] == first["binding_hash"]


def test_a_chain_verifies_end_to_end_and_reports_its_head() -> None:
    built = requalified_chain()

    assert built["length"] == 2
    assert built["head_qualification_id"] == requalified()["qualification_id"]
    assert built["backend_manifest_id"] == PRIMARY_MANIFEST_ID


def test_the_head_is_serving_inside_its_window() -> None:
    assert standing(chain=chain(), as_of=WITHIN_WINDOW) == STANDING_SERVING


def test_the_head_is_expired_after_its_window_closes() -> None:
    assert standing(chain=chain(), as_of=AFTER_EXPIRY) == STANDING_EXPIRED


def test_a_superseded_qualification_reads_as_replaced() -> None:
    built = requalified_chain()
    superseded = genesis()["qualification_id"]

    reported = standing(chain=built, as_of=WITHIN_WINDOW, qualification_id=superseded)

    assert reported == STANDING_REPLACED


def test_a_status_that_never_permitted_serving_reads_as_not_usable() -> None:
    assert (
        standing(chain=rejecting_chain(), as_of=WITHIN_WINDOW)
        == STANDING_STATUS_NOT_USABLE
    )


def test_a_permit_names_the_head_it_authorized() -> None:
    permit = assert_may_serve(permit_id="PERMIT-1", chain=chain(), as_of=WITHIN_WINDOW)

    assert permit["standing"] == STANDING_SERVING
    assert permit["backend_manifest_id"] == PRIMARY_MANIFEST_ID
    assert permit["qualification_id"] == genesis()["qualification_id"]


def test_a_withdrawal_is_written_into_the_record_and_changes_its_standing() -> None:
    revoked = withdraw_qualification(
        withdrawal_id="WD-1",
        record=genesis(),
        kind=STANDING_REVOKED,
        at=WITHIN_WINDOW,
        reason="policy revocation",
    )
    revoked_chain = build_chain(chain_id="T06-CHAIN-1", records=[revoked])

    assert revoked["withdrawal"]["kind"] == STANDING_REVOKED
    assert standing(chain=revoked_chain, as_of=WITHIN_WINDOW) == STANDING_REVOKED


# --- declared fallback and routing ---------------------------------------


def test_a_declared_chain_ends_in_the_always_present_core() -> None:
    declared = fallback_chain()

    assert declared["length"] == 3
    assert declared["terminal_member_id"] == NATIVE_CORE_MEMBER_ID
    assert declared["members"][-1]["runs_backend"] is False
    assert declared["members"][-1]["backend_manifest_id"] is None


def test_a_serving_primary_is_selected_with_no_step_down() -> None:
    routed = route_request(
        request_id="REQ-1",
        fallback_chain=fallback_chain(),
        requested_capabilities=list(REQUESTED_CAPABILITIES),
        as_of=WITHIN_WINDOW,
    )

    assert routed["served_by_backend"] is True
    assert routed["selected_backend_manifest_id"] == PRIMARY_MANIFEST_ID
    assert routed["fallback_events"] == []
    assert routed["capabilities_withheld"] == []


def test_an_expired_primary_steps_down_to_the_qualified_standby() -> None:
    routed = route_request(
        request_id="REQ-2",
        fallback_chain=fallback_chain(),
        requested_capabilities=list(REQUESTED_CAPABILITIES),
        as_of=AFTER_EXPIRY,
    )

    assert routed["served_by_backend"] is True
    assert routed["selected_member_id"] == "standby-backend"
    assert len(routed["fallback_events"]) == 1
    assert routed["fallback_events"][0]["from_member_id"] == "primary-backend"
    assert routed["fallback_events"][0]["to_member_id"] == "standby-backend"
    assert routed["capabilities_withheld"] == ["genome-mutation"]


def test_every_backend_expired_falls_through_to_the_inert_core() -> None:
    routed = route_request(
        request_id="REQ-3",
        fallback_chain=fallback_chain(),
        requested_capabilities=list(REQUESTED_CAPABILITIES),
        as_of=AFTER_STANDBY_EXPIRY,
    )

    assert routed["served_by_backend"] is False
    assert routed["selected_member_id"] == NATIVE_CORE_MEMBER_ID
    assert len(routed["fallback_events"]) == 2
    assert routed["capabilities_withheld"] == sorted(REQUESTED_CAPABILITIES)


def test_the_audit_accounts_for_every_member_that_was_passed() -> None:
    routed = route_request(
        request_id="REQ-4",
        fallback_chain=fallback_chain(),
        requested_capabilities=list(REQUESTED_CAPABILITIES),
        as_of=AFTER_EXPIRY,
    )

    audit = assert_fallback_recorded(
        audit_id="AUD-1", routing=routed, fallback_chain=fallback_chain()
    )

    assert audit["recorded_steps"] == 1
    assert audit["skipped_member_ids"] == ["primary-backend"]
    assert audit["selected_member_id"] == "standby-backend"


# --- disablement reaching backwards --------------------------------------


def test_disabling_withdraws_the_head_and_marks_the_in_flight_import() -> None:
    disablement = disable_backend(
        disablement_id="DIS-1",
        chain=chain(),
        disabled_at=WITHIN_WINDOW,
        reason="operational stand-down",
        in_flight_imports=[imported_run()],
    )

    assert disablement["serving_permitted"] is False
    assert len(disablement["reverification_marks"]) == 1
    assert disablement["reverification_marks"][0]["requires_reverification"] is True
    assert (
        standing(chain=disablement["disabled_chain"], as_of=WITHIN_WINDOW)
        == STANDING_DEACTIVATED
    )


def test_a_disablement_that_marked_every_import_passes_the_audit() -> None:
    disablement = disable_backend(
        disablement_id="DIS-2",
        chain=chain(),
        disabled_at=WITHIN_WINDOW,
        reason="operational stand-down",
        in_flight_imports=[imported_run()],
    )

    audit = assert_reverification_marked(
        disablement=disablement, imports=[imported_run()]
    )

    assert audit["serving_permitted"] is False
    assert audit["marked_import_ids"] == ["IMP-T06-1"]


def test_a_routing_decided_before_the_disablement_is_left_alone() -> None:
    disablement = disable_backend(
        disablement_id="DIS-3",
        chain=chain(),
        disabled_at=WITHIN_WINDOW,
        reason="operational stand-down",
    )
    earlier = route_request(
        request_id="REQ-5",
        fallback_chain=fallback_chain(),
        requested_capabilities=list(REQUESTED_CAPABILITIES),
        as_of=ISSUED_AT,
    )

    audit = assert_not_serving_after_disable(disablement=disablement, routing=earlier)

    assert audit["decided_before_disablement"] is True
    assert audit["selected_backend_manifest_id"] == PRIMARY_MANIFEST_ID
