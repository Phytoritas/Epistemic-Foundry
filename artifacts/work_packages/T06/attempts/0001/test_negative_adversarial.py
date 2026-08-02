"""negative_and_adversarial_tests — every refusal fires for the stated reason.

The gate's whole value is in what it refuses to let an optional backend become.
Each test drives one declared refusal and asserts the exact finding code that
names it, so a future change that silences a guard or renames a code fails here
rather than shipping a lifecycle that served past its window, degraded to a wider
substitute, kept serving after disablement, or lost the runs it left in flight.

A T06 refusal is an ``IntegrationGateError``; a tampered record is a T05
integrity failure and refuses under ``AdapterGateError`` with its own code, and
that separation is asserted rather than smoothed over.  The adversarial cases at
the end prove the crash/resume boundary — a record that does not re-derive is
inert — and that no path down the chain lets a backend acquire authority.
"""

from __future__ import annotations

import copy

import pytest

from epistemic_foundry.adapters.v4_t05 import AdapterGateError
from epistemic_foundry.adapters.v4_t06 import (
    NATIVE_CORE_MEMBER_ID,
    STANDING_REVOKED,
    IntegrationGateError,
    assert_fallback_recorded,
    assert_may_serve,
    assert_not_serving_after_disable,
    assert_reverification_marked,
    backend_member,
    build_chain,
    declare_fallback_chain,
    disable_backend,
    native_core_member,
    open_qualification,
    requalify,
    require_instant,
    route_request,
    withdraw_qualification,
)
from fixtures import (
    AFTER_EXPIRY,
    EXPIRES_AT,
    ISSUED_AT,
    PRIMARY_CAPABILITIES,
    PRIMARY_MANIFEST_ID,
    REQUALIFIED_AT,
    REQUESTED_CAPABILITIES,
    WITHIN_WINDOW,
    binding,
    chain,
    fallback_chain,
    genesis,
    imported_run,
    members,
    rejecting_chain,
    second_binding,
    standby_binding,
    standby_chain,
)


def _refused(code: str, call) -> None:
    with pytest.raises(IntegrationGateError) as caught:
        call()
    assert caught.value.code == code, (
        f"expected {code}, got {caught.value.code}: {caught.value}"
    )


# --- time is the axis the whole package judges against --------------------


def test_a_naive_timestamp_cannot_be_compared() -> None:
    _refused(
        "TIMESTAMP_NOT_ABSOLUTE",
        lambda: require_instant("2026-08-02T00:00:00", "as_of"),
    )


def test_an_unparseable_timestamp_is_refused() -> None:
    _refused(
        "TIMESTAMP_NOT_ABSOLUTE",
        lambda: require_instant("not-an-instant", "as_of"),
    )


def test_a_window_that_does_not_open_before_it_closes_is_refused() -> None:
    _refused(
        "QUALIFICATION_WINDOW_INVALID",
        lambda: open_qualification(
            lifecycle_id="T06-LIFE-BAD",
            binding=binding(),
            issued_at=EXPIRES_AT,
            expires_at=ISSUED_AT,
        ),
    )


# --- the qualification lifecycle stays an unbroken line -------------------


def test_a_requalification_of_another_backend_is_refused() -> None:
    _refused(
        "BACKEND_IDENTITY_MISMATCH",
        lambda: requalify(
            previous=genesis(),
            binding=standby_binding(),
            issued_at=REQUALIFIED_AT,
            expires_at="2026-10-01T00:00:00+00:00",
        ),
    )


def test_a_requalification_that_is_not_a_new_record_is_refused() -> None:
    _refused(
        "QUALIFICATION_CHAIN_BROKEN",
        lambda: requalify(
            previous=genesis(),
            binding=binding(),
            issued_at=REQUALIFIED_AT,
            expires_at="2026-10-01T00:00:00+00:00",
        ),
    )


def test_a_requalification_issued_before_its_predecessor_is_refused() -> None:
    _refused(
        "QUALIFICATION_WINDOW_INVALID",
        lambda: requalify(
            previous=genesis(),
            binding=second_binding(),
            issued_at="2026-08-01T00:00:00+00:00",
            expires_at="2026-10-01T00:00:00+00:00",
        ),
    )


def test_a_head_record_presented_as_a_first_position_chain_is_refused() -> None:
    later = requalify(
        previous=genesis(),
        binding=second_binding(),
        issued_at=REQUALIFIED_AT,
        expires_at="2026-10-01T00:00:00+00:00",
    )
    _refused(
        "QUALIFICATION_CHAIN_BROKEN",
        lambda: build_chain(chain_id="T06-CHAIN-BAD", records=[later]),
    )


# --- serving is decided against an instant, never assumed -----------------


def test_serving_under_an_expired_qualification_is_refused() -> None:
    _refused(
        "QUALIFICATION_NOT_SERVING",
        lambda: assert_may_serve(
            permit_id="PERMIT-BAD", chain=chain(), as_of=AFTER_EXPIRY
        ),
    )


def test_serving_under_a_non_usable_verdict_is_refused() -> None:
    _refused(
        "QUALIFICATION_NOT_SERVING",
        lambda: assert_may_serve(
            permit_id="PERMIT-BAD", chain=rejecting_chain(), as_of=WITHIN_WINDOW
        ),
    )


def test_withdrawing_an_already_withdrawn_qualification_is_refused() -> None:
    once = withdraw_qualification(
        withdrawal_id="WD-1",
        record=genesis(),
        kind=STANDING_REVOKED,
        at=WITHIN_WINDOW,
        reason="policy revocation",
    )
    _refused(
        "QUALIFICATION_NOT_SERVING",
        lambda: withdraw_qualification(
            withdrawal_id="WD-2",
            record=once,
            kind=STANDING_REVOKED,
            at=WITHIN_WINDOW,
            reason="again",
        ),
    )


# --- a fallback may only ever narrow -------------------------------------


def test_an_unqualified_fallback_member_is_refused() -> None:
    _refused(
        "FALLBACK_MEMBER_UNQUALIFIED",
        lambda: backend_member(
            member_id="rejected-backend",
            chain=rejecting_chain(),
            capabilities=list(PRIMARY_CAPABILITIES),
        ),
    )


def test_a_chain_that_does_not_end_in_the_core_is_refused() -> None:
    without_core = members()[:2]
    _refused(
        "FALLBACK_CHAIN_MALFORMED",
        lambda: declare_fallback_chain(chain_id="T06-FALL-BAD", members=without_core),
    )


def test_a_core_that_is_not_the_terminal_member_is_refused() -> None:
    primary, standby, core = members()
    _refused(
        "FALLBACK_CHAIN_MALFORMED",
        lambda: declare_fallback_chain(
            chain_id="T06-FALL-BAD", members=[primary, core, standby]
        ),
    )


def test_a_member_that_appears_twice_is_refused() -> None:
    primary, standby, core = members()
    _refused(
        "FALLBACK_CHAIN_MALFORMED",
        lambda: declare_fallback_chain(
            chain_id="T06-FALL-BAD", members=[primary, primary, core]
        ),
    )


def test_a_fallback_member_that_widens_the_primary_is_refused() -> None:
    widened_standby = backend_member(
        member_id="standby-backend",
        chain=standby_chain(),
        capabilities=["candidate-search", "network-egress"],
    )
    primary, _standby, core = members()
    _refused(
        "FALLBACK_CAPABILITY_WIDENED",
        lambda: declare_fallback_chain(
            chain_id="T06-FALL-BAD", members=[primary, widened_standby, core]
        ),
    )


def test_routing_a_member_that_widens_the_request_is_refused() -> None:
    # The request asks for less than the primary holds, so serving it from the
    # primary would hand back more reach than was asked for.
    _refused(
        "FALLBACK_CAPABILITY_WIDENED",
        lambda: route_request(
            request_id="REQ-BAD",
            fallback_chain=fallback_chain(),
            requested_capabilities=["candidate-search"],
            as_of=WITHIN_WINDOW,
        ),
    )


def test_auditing_a_routing_against_the_wrong_chain_is_refused() -> None:
    routed = route_request(
        request_id="REQ-6",
        fallback_chain=fallback_chain(),
        requested_capabilities=list(REQUESTED_CAPABILITIES),
        as_of=AFTER_EXPIRY,
    )
    _refused(
        "FALLBACK_UNRECORDED",
        lambda: assert_fallback_recorded(
            audit_id="AUD-BAD",
            routing=routed,
            fallback_chain=fallback_chain(chain_id="T06-FALL-OTHER"),
        ),
    )


# --- disablement reaches backwards, and must not miss a run ---------------


def test_a_disablement_that_left_an_import_unmarked_is_refused() -> None:
    disablement = disable_backend(
        disablement_id="DIS-4",
        chain=chain(),
        disabled_at=WITHIN_WINDOW,
        reason="operational stand-down",
    )
    _refused(
        "REVERIFICATION_UNMARKED",
        lambda: assert_reverification_marked(
            disablement=disablement, imports=[imported_run()]
        ),
    )


def test_a_disabled_backend_that_kept_serving_afterwards_is_refused() -> None:
    disablement = disable_backend(
        disablement_id="DIS-5",
        chain=chain(),
        disabled_at=ISSUED_AT,
        reason="operational stand-down",
    )
    served_after = route_request(
        request_id="REQ-7",
        fallback_chain=fallback_chain(),
        requested_capabilities=list(REQUESTED_CAPABILITIES),
        as_of=WITHIN_WINDOW,
    )
    _refused(
        "DISABLED_BACKEND_STILL_SERVING",
        lambda: assert_not_serving_after_disable(
            disablement=disablement, routing=served_after
        ),
    )


# --- adversarial: crash/resume integrity and the authority boundary -------


def test_a_tampered_chain_record_refuses_under_the_sealed_t05_gate() -> None:
    # A record edited in flight and replayed must not be trusted; the T05
    # digest gate — not a T06 lifecycle code — is what names the corruption.
    corrupt = chain()
    corrupt["records"][0]["status"] = "forged-verdict"
    with pytest.raises(AdapterGateError) as caught:
        assert_may_serve(permit_id="PERMIT-X", chain=corrupt, as_of=WITHIN_WINDOW)
    assert caught.value.code == "RECORD_HASH_MISMATCH"


def test_the_two_gates_do_not_catch_each_other() -> None:
    assert not issubclass(IntegrationGateError, AdapterGateError)
    assert not issubclass(AdapterGateError, IntegrationGateError)


def test_the_terminal_core_can_carry_no_backend_and_no_capability() -> None:
    # The one member that must always be reachable is inert by construction, so
    # reaching it can never be a widening or an acquisition of authority.
    core = native_core_member()

    assert core["member_id"] == NATIVE_CORE_MEMBER_ID
    assert core["runs_backend"] is False
    assert core["backend_manifest_id"] is None
    assert core["capabilities"] == []
    assert core["qualification_chain"] is None


def test_no_routed_record_carries_evaluator_or_promotion_authority() -> None:
    # T06 gates; it never scores, promotes or evaluates.  A routing or permit
    # record that grew such a field would be exactly the leakage the gate bars.
    forbidden = {
        "score",
        "fitness",
        "reward",
        "promoted",
        "promotion",
        "evaluator_verdict",
        "holdout",
    }
    routed = route_request(
        request_id="REQ-8",
        fallback_chain=fallback_chain(),
        requested_capabilities=list(REQUESTED_CAPABILITIES),
        as_of=WITHIN_WINDOW,
    )
    permit = assert_may_serve(permit_id="PERMIT-Y", chain=chain(), as_of=WITHIN_WINDOW)

    assert set(routed) & forbidden == set()
    assert set(permit) & forbidden == set()
    assert routed["selected_backend_manifest_id"] == PRIMARY_MANIFEST_ID


def test_routing_never_mutates_the_declared_chain_it_was_given() -> None:
    declared = fallback_chain()
    before = copy.deepcopy(declared)

    route_request(
        request_id="REQ-9",
        fallback_chain=declared,
        requested_capabilities=list(REQUESTED_CAPABILITIES),
        as_of=AFTER_EXPIRY,
    )

    assert declared == before
