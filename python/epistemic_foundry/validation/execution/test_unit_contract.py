"""unit_and_contract_tests — what an authorized validation run actually gets.

The contract of this component is that a run which was approved, leased,
recorded and captured completely produces a receipt that says exactly what
happened and a record that says exactly why it was allowed to.  These tests
walk that path forward: an intent that derives both of its hashes, an
environment that satisfies the target's own reproducibility contract, a capture
that carries every channel, a reconciliation whose arithmetic closes, and a gate
that separates a run which failed from a run which misbehaved.

There is no clock and no randomness anywhere in the path: every id, instant,
seed and token is supplied by the caller.
"""

from __future__ import annotations

from .contracts import (
    AUTHORIZATION_CRITERIA,
    CHANNEL_CLASS,
    EXECUTION_CRITERIA,
    authorize_execution,
    build_action_intent,
    build_effect_receipt,
    build_run_capture,
    capture_channels,
    digest,
    digest_bytes,
    hash_excluding,
    reconcile_effects,
    seal_capture_channel,
    seal_execution_record,
    seal_run_environment,
    verify_action_intent,
    verify_capture_channel,
    verify_effect_receipt,
)
from .fixtures import (
    ARTIFACT_HASH,
    CAPTURE_ID,
    CHANNEL_PAYLOADS,
    EXPECTED_EFFECTS,
    FINISHED_AT,
    IDEMPOTENCY_KEY,
    INTENT_ID,
    RECONCILIATION_ID,
    RECORD_ID,
    ROOT,
    RUN_ID,
    SEALED_AT,
    STARTED_AT,
    STDOUT_PAYLOAD,
    action_intent,
    arguments,
    authorization_arguments,
    capture_arguments,
    channel_receipt,
    channels,
    environment_arguments,
    intent_arguments,
    receipt_arguments,
    reconciliation,
    run_capture,
    run_environment,
)


def authorized() -> dict:
    return authorize_execution(ROOT, **authorization_arguments())


def test_intent_derives_both_hashes_from_what_it_publishes() -> None:
    intent = action_intent()
    assert intent["intent_hash"] == hash_excluding(intent, "intent_hash")
    assert intent["arguments_hash"] == digest(arguments())
    verification = verify_action_intent(ROOT, intent, arguments())
    assert verification["intent_hash_matches"] is True
    assert verification["arguments_hash_matches"] is True


def test_intent_builder_does_not_mutate_caller_inputs() -> None:
    supplied = intent_arguments()
    before = digest(supplied)
    build_action_intent(ROOT, **supplied)
    assert digest(supplied) == before


def test_intent_sorts_every_derived_list() -> None:
    intent = action_intent(
        required_capabilities=["sandbox_execute", "object_store_read"],
        approval_record_ids=["APPROVAL-V03-2", "APPROVAL-V03-1"],
    )
    assert intent["required_capabilities"] == sorted(intent["required_capabilities"])
    assert intent["approval_record_ids"] == sorted(intent["approval_record_ids"])


def test_environment_records_seeds_artifacts_and_image() -> None:
    environment = run_environment()
    assert environment["seeds"] == {"numpy_global": 20260801, "target_stream": 4242}
    assert ARTIFACT_HASH in environment["artifact_hashes"]
    assert environment["artifact_hashes"] == sorted(environment["artifact_hashes"])
    assert environment["container_digest"] is not None
    assert environment["environment_capture"]["interpreter"] == "CPython 3.12.7"
    assert environment["environment_hash"] == hash_excluding(
        environment, "environment_hash"
    )


def test_environment_may_record_more_than_the_contract_demands() -> None:
    """Recording beyond the contract is always allowed; recording less is not."""

    relaxed = run_environment(
        reproducibility_contract={
            "container_digest_required": False,
            "environment_capture": False,
            "seed_control": False,
        }
    )
    assert relaxed["seeds"]
    assert relaxed["container_digest"] is not None
    assert relaxed["environment_capture"]


def test_capture_channel_is_addressed_by_the_bytes_it_captured() -> None:
    receipt = channel_receipt("stdout")
    assert receipt["content_hash"] == digest_bytes(STDOUT_PAYLOAD)
    assert receipt["byte_size"] == len(STDOUT_PAYLOAD)
    assert receipt["receipt_hash"] == hash_excluding(receipt, "receipt_hash")
    verification = verify_capture_channel(ROOT, receipt, STDOUT_PAYLOAD)
    assert verification["content_hash_matches"] is True
    assert verification["receipt_hash_matches"] is True
    assert verification["size_matches"] is True


def test_truncated_capture_is_sealed_as_what_was_actually_captured() -> None:
    partial = STDOUT_PAYLOAD[:5]
    receipt = seal_capture_channel(
        ROOT,
        receipt_id="AR-V03-stdout-partial",
        artifact_id="ART-V03-stdout-partial",
        action_intent_id=INTENT_ID,
        channel="stdout",
        payload=partial,
        media_type="text/plain",
        locator="object_store/validation_runs/partial",
        actor_id="svc-validation-runner",
        actor_type="service",
        created_at=FINISHED_AT,
        truncated=True,
    )
    assert receipt["content_hash"] == digest_bytes(partial)
    statuses = {
        entry["check"]: entry["status"] for entry in receipt["validation_results"]
    }
    assert statuses["content_hash_matches_payload"] == "PASS"
    assert statuses["capture_complete"] == "FAIL"


def test_capture_carries_every_channel_and_flags_truncation() -> None:
    capture = run_capture()
    assert sorted(capture["channel_hashes"]) == sorted(capture_channels(ROOT))
    assert capture["truncated_channels"] == []
    assert capture["effect_status"] == "SUCCEEDED"
    assert capture["exit_code"] == 0
    assert capture["resource_usage"]["wall_seconds"] == 1800
    for name, payload in CHANNEL_PAYLOADS.items():
        assert capture["channel_hashes"][name] == digest_bytes(payload)
    assert capture["capture_hash"] == hash_excluding(capture, "capture_hash")


def test_authorization_names_every_criterion_it_satisfied() -> None:
    decision = authorized()
    assert decision["allowed"] is True
    assert decision["denial_codes"] == []
    assert decision["criteria_satisfied"] == sorted(AUTHORIZATION_CRITERIA)
    assert decision["decision_hash"] == hash_excluding(decision, "decision_hash")


def test_lease_scope_wildcard_covers_what_it_prefixes() -> None:
    decision = authorize_execution(
        ROOT,
        **authorization_arguments(
            write_scopes=[
                "object_store/validation_runs/VRUN-V03-1",
                "object_store/validation_runs/VRUN-V03-1/analysis",
            ],
            scope_fencing_heads={},
        ),
    )
    assert decision["allowed"] is True


def test_reconciliation_arithmetic_closes_exactly() -> None:
    record = reconcile_effects(
        ROOT,
        reconciliation_id=RECONCILIATION_ID,
        expected_effects=["a", "b", "c"],
        observed_effects=["b", "c", "d"],
        status="SUCCEEDED",
    )
    counts = record["counts"]
    assert counts["expected"] == counts["matched"] + counts["missing"]
    assert counts["observed"] == counts["matched"] + counts["unexpected"]
    assert record["matched_effects"] == ["b", "c"]
    assert record["missing_effects"] == ["a"]
    assert record["unexpected_effects"] == ["d"]
    assert record["incident_raised"] is True
    assert record["reconciliation_required"] is True


def test_exact_reconciliation_needs_no_follow_up() -> None:
    record = reconciliation()
    assert record["incident_raised"] is False
    assert record["reconciliation_required"] is False
    assert record["matched_effects"] == sorted(EXPECTED_EFFECTS)


def test_receipt_takes_status_and_key_from_what_it_reports_on() -> None:
    receipt = build_effect_receipt(ROOT, **receipt_arguments())
    assert receipt["status"] == "SUCCEEDED"
    assert receipt["idempotency_key"] == IDEMPOTENCY_KEY
    assert receipt["intent_id"] == INTENT_ID
    assert receipt["run_id"] == RUN_ID
    assert receipt["reconciliation_required"] is False
    assert receipt["observed_state_hash"] is not None
    verification = verify_effect_receipt(ROOT, receipt, action_intent())
    assert verification["receipt_hash_matches"] is True
    assert verification["intent_bound"] is True
    assert verification["resolves"] is True


def test_receipt_partitions_channels_by_their_declared_class() -> None:
    receipt = build_effect_receipt(ROOT, **receipt_arguments())
    capture = run_capture()
    for name, artifact in capture["channel_receipt_ids"].items():
        partition = (
            receipt["result_artifact_ids"]
            if CHANNEL_CLASS[name] == "result"
            else receipt["error_artifact_ids"]
        )
        assert artifact in partition
    assert not set(receipt["result_artifact_ids"]) & set(receipt["error_artifact_ids"])


def test_caller_supplied_result_artifacts_join_the_captured_ones() -> None:
    receipt = build_effect_receipt(
        ROOT, **receipt_arguments(result_artifact_ids=["ART-V03-storage-series"])
    )
    assert "ART-V03-storage-series" in receipt["result_artifact_ids"]
    assert receipt["result_artifact_ids"] == sorted(receipt["result_artifact_ids"])


def test_interrupted_run_stays_unresolved_and_demands_reconciliation() -> None:
    capture = run_capture(observation="timed_out", exit_code=None)
    assert capture["effect_status"] == "UNKNOWN"
    receipt = build_effect_receipt(
        ROOT,
        **receipt_arguments(
            capture=capture,
            reconciliation=reconciliation(status="UNKNOWN"),
        ),
    )
    assert receipt["status"] == "UNKNOWN"
    assert receipt["reconciliation_required"] is True
    assert verify_effect_receipt(ROOT, receipt, action_intent())["resolves"] is False


def test_run_that_never_started_observes_no_state() -> None:
    capture = run_capture(
        observation="not_started",
        exit_code=None,
        channels=channels(),
    )
    assert capture["effect_status"] == "NOT_EXECUTED"
    receipt = build_effect_receipt(
        ROOT,
        **receipt_arguments(
            capture=capture,
            reconciliation=reconcile_effects(
                ROOT,
                reconciliation_id=RECONCILIATION_ID,
                expected_effects=list(EXPECTED_EFFECTS),
                observed_effects=[],
                status="NOT_EXECUTED",
            ),
        ),
    )
    assert receipt["status"] == "NOT_EXECUTED"
    assert receipt["observed_state_hash"] is None
    assert receipt["reconciliation_required"] is True


def sealed(**overrides: object) -> dict:
    decision = overrides.pop("authorization", None) or authorized()
    parts = {
        "capture": run_capture(),
        "environment": run_environment(),
        "receipt": build_effect_receipt(ROOT, **receipt_arguments()),
        "reconciliation": reconciliation(),
    }
    parts.update(overrides)  # type: ignore[arg-type]
    return seal_execution_record(
        ROOT,
        record_id=RECORD_ID,
        sealed_at=SEALED_AT,
        authorization=decision,
        **parts,  # type: ignore[arg-type]
    )


def test_clean_run_passes_the_execution_gate() -> None:
    record = sealed()
    assert record["gate"] == "PASS"
    assert record["criteria_satisfied"] == sorted(EXECUTION_CRITERIA)
    assert record["record_hash"] == hash_excluding(record, "record_hash")
    assert record["detail"] == {}


def test_target_that_fails_cleanly_is_a_result_not_a_broken_gate() -> None:
    capture = run_capture(observation="failed", exit_code=1)
    failed = reconciliation(status="FAILED")
    receipt = build_effect_receipt(
        ROOT, **receipt_arguments(capture=capture, reconciliation=failed)
    )
    record = sealed(capture=capture, reconciliation=failed, receipt=receipt)
    assert record["gate"] == "FAILED_RUN"
    assert record["criteria_satisfied"] == sorted(EXECUTION_CRITERIA)


def test_unexpected_effect_raises_an_incident_over_a_green_exit() -> None:
    unexpected = reconciliation(
        observed_effects=[*EXPECTED_EFFECTS, "object_store_write_outside_run"]
    )
    receipt = build_effect_receipt(ROOT, **receipt_arguments(reconciliation=unexpected))
    record = sealed(reconciliation=unexpected, receipt=receipt)
    assert record["gate"] == "INCIDENT"
    assert "effects_reconciled" not in record["criteria_satisfied"]
    assert record["detail"]["reconciliation"]["unexpected"] == [
        "object_store_write_outside_run"
    ]


def test_capture_binds_the_run_and_intent_it_belongs_to() -> None:
    capture = build_run_capture(ROOT, **capture_arguments())
    assert capture["run_id"] == RUN_ID
    assert capture["intent_id"] == INTENT_ID
    assert capture["capture_id"] == CAPTURE_ID


def test_environment_builder_accepts_only_declared_network_policies() -> None:
    environment = seal_run_environment(
        ROOT, **environment_arguments(network_policy="disabled")
    )
    assert environment["network_policy"] == "disabled"
    assert environment["recorded_at"].endswith("Z")
    assert environment["run_id"] == RUN_ID
    assert STARTED_AT > environment["recorded_at"]
