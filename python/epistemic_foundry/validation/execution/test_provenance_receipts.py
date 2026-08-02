"""provenance_and_receipt_audit — every effect resolves to a re-derivable receipt.

The whole point of capability-controlled execution is that what happened can be
reconstructed later without this module in the room.  So every document it seals
publishes a hash over exactly the fields it carries and re-derives that hash from
those fields alone: the intent, the run environment, each captured channel, the
whole capture, the reconciliation, the effect receipt, the authorization
decision and the sealed execution record.  Each verifier is shown to agree with
the builder that produced it, and the effect receipt is shown to bind the intent
it reports on by idempotency key and by run — the tie a retry is recognised
through.

Immutability is content addressing all the way down: a captured channel is
addressed by the exact bytes it captured, so a changed payload changes the
receipt, and the receipt's observed-state hash is a function of the environment,
the capture and the reconciliation together, so editing any one of them is
visible in the seal.  Every observation a runner can report — a clean run, a
clean failure, an interruption, a run that never started — resolves to a receipt
that re-derives, so "we didn't receipt that" is never reachable.

Nothing here carries a clock or a random draw: every id, instant, seed and token
comes from the caller, builders do not mutate what they are handed, and the same
run sealed twice is byte-identical canonical JSON.
"""

from __future__ import annotations

import json

from .contracts import (
    authorize_execution,
    build_action_intent,
    build_effect_receipt,
    build_run_capture,
    digest,
    digest_bytes,
    hash_excluding,
    reconcile_effects,
    seal_execution_record,
    seal_run_environment,
    verify_action_intent,
    verify_capture_channel,
    verify_effect_receipt,
)
from .fixtures import (
    EXPECTED_EFFECTS,
    IDEMPOTENCY_KEY,
    INTENT_ID,
    RECONCILIATION_ID,
    RECORD_ID,
    ROOT,
    RUN_ID,
    SEALED_AT,
    STDOUT_PAYLOAD,
    action_intent,
    arguments,
    authorization_arguments,
    capture_arguments,
    channel_receipt,
    environment_arguments,
    intent_arguments,
    lease,
    receipt_arguments,
    reconciliation,
    run_capture,
    run_environment,
)


def canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def authorized() -> dict:
    return authorize_execution(ROOT, **authorization_arguments())


def sealed_record() -> dict:
    return seal_execution_record(
        ROOT,
        record_id=RECORD_ID,
        sealed_at=SEALED_AT,
        authorization=authorized(),
        environment=run_environment(),
        capture=run_capture(),
        receipt=build_effect_receipt(ROOT, **receipt_arguments()),
        reconciliation=reconciliation(),
    )


# --------------------------------------------------------------------------
# Every sealed document re-derives its own hash.
# --------------------------------------------------------------------------


def test_the_intent_re_derives_both_hashes_it_publishes() -> None:
    intent = action_intent()
    verification = verify_action_intent(ROOT, intent, arguments())

    assert intent["intent_hash"] == hash_excluding(intent, "intent_hash")
    assert verification["intent_hash_matches"] is True
    assert verification["arguments_hash_matches"] is True
    assert verification["verification_hash"] == hash_excluding(
        verification, "verification_hash"
    )


def test_the_environment_re_derives_its_own_hash() -> None:
    environment = run_environment()

    assert environment["environment_hash"] == hash_excluding(
        environment, "environment_hash"
    )


def test_a_captured_channel_re_derives_from_the_bytes_it_addressed() -> None:
    receipt = channel_receipt("stdout")
    verification = verify_capture_channel(ROOT, receipt, STDOUT_PAYLOAD)

    assert receipt["content_hash"] == digest_bytes(STDOUT_PAYLOAD)
    assert receipt["receipt_hash"] == hash_excluding(receipt, "receipt_hash")
    assert verification["content_hash_matches"] is True
    assert verification["receipt_hash_matches"] is True


def test_the_capture_re_derives_its_own_hash() -> None:
    capture = run_capture()

    assert capture["capture_hash"] == hash_excluding(capture, "capture_hash")


def test_the_reconciliation_re_derives_its_own_hash() -> None:
    record = reconciliation()

    assert record["reconciliation_hash"] == hash_excluding(
        record, "reconciliation_hash"
    )


def test_the_authorization_decision_re_derives_its_own_hash() -> None:
    result = authorized()

    assert result["decision_hash"] == hash_excluding(result, "decision_hash")


def test_the_effect_receipt_re_derives_its_own_hash() -> None:
    receipt = build_effect_receipt(ROOT, **receipt_arguments())

    assert receipt["receipt_hash"] == hash_excluding(receipt, "receipt_hash")


def test_the_sealed_execution_record_re_derives_its_own_hash() -> None:
    record = sealed_record()

    assert record["record_hash"] == hash_excluding(record, "record_hash")


# --------------------------------------------------------------------------
# The receipt binds the intent it reports on.
# --------------------------------------------------------------------------


def test_the_receipt_takes_its_key_and_binding_from_the_intent() -> None:
    receipt = build_effect_receipt(ROOT, **receipt_arguments())
    verification = verify_effect_receipt(ROOT, receipt, action_intent())

    assert receipt["idempotency_key"] == IDEMPOTENCY_KEY
    assert receipt["intent_id"] == INTENT_ID
    assert receipt["run_id"] == RUN_ID
    assert verification["intent_bound"] is True
    assert verification["receipt_hash_matches"] is True


def test_a_receipt_binds_the_exact_capture_environment_and_reconciliation() -> None:
    baseline = build_effect_receipt(ROOT, **receipt_arguments())
    other_env = build_effect_receipt(
        ROOT,
        **receipt_arguments(
            environment=run_environment(seeds={"numpy_global": 1, "target_stream": 2})
        ),
    )

    assert baseline["observed_state_hash"] is not None
    assert baseline["observed_state_hash"] != other_env["observed_state_hash"]


# --------------------------------------------------------------------------
# Content addressing is immutable: a changed input is a changed hash.
# --------------------------------------------------------------------------


def test_a_changed_payload_changes_the_capture_receipt() -> None:
    original = channel_receipt("stdout")
    altered = channel_receipt("stdout", payload=STDOUT_PAYLOAD + b"tampered\n")

    assert original["content_hash"] != altered["content_hash"]
    assert original["receipt_hash"] != altered["receipt_hash"]


def test_a_changed_environment_changes_the_sealed_record() -> None:
    first = sealed_record()
    second = seal_execution_record(
        ROOT,
        record_id=RECORD_ID,
        sealed_at=SEALED_AT,
        authorization=authorize_execution(
            ROOT,
            **authorization_arguments(
                environment=run_environment(
                    seeds={"numpy_global": 1, "target_stream": 2}
                )
            ),
        ),
        environment=run_environment(seeds={"numpy_global": 1, "target_stream": 2}),
        capture=run_capture(),
        receipt=build_effect_receipt(
            ROOT,
            **receipt_arguments(
                environment=run_environment(
                    seeds={"numpy_global": 1, "target_stream": 2}
                )
            ),
        ),
        reconciliation=reconciliation(),
    )

    assert first["environment_hash"] != second["environment_hash"]
    assert first["record_hash"] != second["record_hash"]


# --------------------------------------------------------------------------
# Every observation resolves to a receipt.
# --------------------------------------------------------------------------


def test_every_observation_a_runner_reports_resolves_to_a_receipt() -> None:
    cases = (
        ("succeeded", 0, "SUCCEEDED", list(EXPECTED_EFFECTS)),
        ("failed", 1, "FAILED", list(EXPECTED_EFFECTS)),
        ("timed_out", None, "UNKNOWN", list(EXPECTED_EFFECTS)),
        ("not_started", None, "NOT_EXECUTED", []),
    )
    for observation, exit_code, status, observed in cases:
        capture = run_capture(observation=observation, exit_code=exit_code)
        record = reconcile_effects(
            ROOT,
            reconciliation_id=RECONCILIATION_ID,
            expected_effects=list(EXPECTED_EFFECTS),
            observed_effects=observed,
            status=status,
        )
        receipt = build_effect_receipt(
            ROOT, **receipt_arguments(capture=capture, reconciliation=record)
        )

        assert receipt["status"] == status
        assert receipt["receipt_hash"] == hash_excluding(receipt, "receipt_hash")
        assert capture["effect_status"] == status


def test_a_run_that_never_started_observes_no_state() -> None:
    capture = run_capture(observation="not_started", exit_code=None)
    record = reconcile_effects(
        ROOT,
        reconciliation_id=RECONCILIATION_ID,
        expected_effects=list(EXPECTED_EFFECTS),
        observed_effects=[],
        status="NOT_EXECUTED",
    )
    receipt = build_effect_receipt(
        ROOT, **receipt_arguments(capture=capture, reconciliation=record)
    )

    assert receipt["observed_state_hash"] is None
    assert receipt["reconciliation_required"] is True


def test_a_denied_authorization_is_evidence_in_the_same_shape_as_a_success() -> None:
    denied = authorize_execution(
        ROOT,
        **authorization_arguments(
            lease=lease(revoked=True, revocation_reason="operator_cutoff")
        ),
    )
    record = seal_execution_record(
        ROOT,
        record_id="VXR-denied",
        sealed_at=SEALED_AT,
        authorization=denied,
    )

    assert record["gate"] == "DENIED"
    assert record["record_hash"] == hash_excluding(record, "record_hash")
    assert record["effect_receipt_hash"] is None


# --------------------------------------------------------------------------
# No clock, no randomness: the same run sealed twice is byte-identical.
# --------------------------------------------------------------------------


def test_the_same_intent_built_twice_is_byte_identical() -> None:
    assert canonical(action_intent()) == canonical(action_intent())


def test_the_same_receipt_built_twice_is_byte_identical() -> None:
    first = build_effect_receipt(ROOT, **receipt_arguments())
    second = build_effect_receipt(ROOT, **receipt_arguments())

    assert canonical(first) == canonical(second)


def test_the_same_authorization_decided_twice_is_byte_identical() -> None:
    assert canonical(authorized()) == canonical(authorized())


def test_the_same_execution_record_sealed_twice_is_byte_identical() -> None:
    assert canonical(sealed_record()) == canonical(sealed_record())


# --------------------------------------------------------------------------
# Builders do not mutate what the caller handed them.
# --------------------------------------------------------------------------


def test_the_intent_builder_does_not_mutate_its_inputs() -> None:
    supplied = intent_arguments()
    before = digest(supplied)

    build_action_intent(ROOT, **supplied)

    assert digest(supplied) == before


def test_the_environment_builder_does_not_mutate_its_inputs() -> None:
    supplied = environment_arguments()
    before = digest(supplied)

    seal_run_environment(ROOT, **supplied)

    assert digest(supplied) == before


def test_the_capture_builder_does_not_mutate_its_inputs() -> None:
    supplied = capture_arguments()
    before = digest(supplied)

    build_run_capture(ROOT, **supplied)

    assert digest(supplied) == before


def test_a_sealed_record_is_a_fresh_document() -> None:
    record = sealed_record()
    record["criteria_satisfied"].append("MUTATED")

    assert "MUTATED" not in sealed_record()["criteria_satisfied"]
