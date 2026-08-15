"""tool_receipt_test — outputs are hashed and every run is accounted for.

Exit criteria under test: "tool outputs hashed" and "timeouts/cancellation/
quotas enforced".  A receipt is only worth as much as the bytes it can
re-derive, so the hash is recomputed rather than trusted; and an invocation
that was cancelled, throttled or timed out still owes an EffectReceipt whose
status follows what was observed instead of what was hoped for.
"""

from __future__ import annotations

import hashlib
from typing import Any

import pytest

from .contracts import (
    OBSERVATION_STATUS,
    REQUIRED_BOUNDED_DIMENSIONS,
    Denial,
    _hash_excluding,
    GateStatus,
    Observation,
    SandboxGateError,
    authorize_invocation,
    build_effect_receipt,
    consume,
    effect_statuses,
    evaluate_deadline,
    evaluate_tool_gate,
    open_ledger,
    reconcile_invocation,
    remaining,
    seal_adapter,
    seal_quota_envelope,
    seal_tool_output,
    verify_tool_output,
)
from .test_sandbox_escape import (
    NOW,
    POLICY_HASH,
    ROOT,
    envelope,
    holdout,
    lease,
    manifest,
    request,
)

PAYLOAD = b'{"result":42}'
STARTED = "2026-08-01T12:00:00Z"
FINISHED = "2026-08-01T12:00:05Z"


def ledger(**overrides: Any):
    return open_ledger(
        ROOT,
        adapter=overrides.pop("adapter", None) or seal_adapter(ROOT, manifest()),
        budget=overrides.pop("budget", None)
        or seal_quota_envelope(ROOT, envelope(**overrides)),
    )


def output(payload: bytes = PAYLOAD, **overrides: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "actor_id": "tool-runner",
        "actor_type": "tool",
        "artifact_id": "ART-1",
        "created_at": FINISHED,
        "intent_id": "INT-1",
        "locator": "artifacts/tool/ART-1.json",
        "media_type": "application/json",
        "receipt_id": "AREC-1",
        "truncated": False,
    }
    fields.update(overrides)
    return seal_tool_output(ROOT, payload=payload, **fields)


def effect(**overrides: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "error_artifact_ids": [],
        "external_operation_id": "EXT-1",
        "finished_at": FINISHED,
        "idempotency_key": "IDEM-1",
        "intent_id": "INT-1",
        "outcome": reconcile_invocation(
            ROOT, observation=Observation.COMPLETED.value, stop_reason=None
        ),
        "output_receipts": [output()],
        "receipt_id": "EREC-1",
        "run_id": "RUN-1",
        "started_at": STARTED,
    }
    fields.update(overrides)
    return build_effect_receipt(ROOT, **fields)


def test_an_output_hash_is_the_hash_of_the_bytes_that_were_captured() -> None:
    receipt = output()

    assert receipt["content_hash"] == "sha256:" + hashlib.sha256(PAYLOAD).hexdigest()
    assert receipt["byte_size"] == len(PAYLOAD)
    assert verify_tool_output(receipt, PAYLOAD)["artifact_id"] == "ART-1"


def test_an_empty_output_is_still_hashed() -> None:
    receipt = output(b"")

    assert receipt["byte_size"] == 0
    assert receipt["content_hash"] == "sha256:" + hashlib.sha256(b"").hexdigest()


def test_a_truncated_capture_hashes_what_it_captured_and_says_so() -> None:
    receipt = output(b"partial", truncated=True)

    completeness = next(
        entry
        for entry in receipt["validation_results"]
        if entry["check"] == "capture_completeness"
    )
    assert completeness["status"] == "FAIL"
    assert verify_tool_output(receipt, b"partial")["byte_size"] == 7


def test_a_receipt_hash_excludes_itself_and_is_recomputable() -> None:
    first = output()
    second = output()

    assert first == second
    assert first["receipt_hash"].startswith("sha256:")


def test_different_bytes_do_not_verify_against_the_same_receipt() -> None:
    with pytest.raises(SandboxGateError) as caught:
        verify_tool_output(output(), b'{"result":43}')

    assert caught.value.code == "OUTPUT_HASH_MISMATCH"


def test_a_tampered_receipt_is_refused() -> None:
    receipt = output()
    receipt["locator"] = "artifacts/tool/other.json"

    with pytest.raises(SandboxGateError) as caught:
        verify_tool_output(receipt, PAYLOAD)

    assert caught.value.code == "RECEIPT_HASH_MISMATCH"


def test_a_restated_byte_size_is_refused_even_when_it_is_resealed() -> None:
    """Re-sealing a forged size hides the tamper from the self-hash, so the
    size is re-derived from the bytes as well."""

    receipt = output()
    receipt["byte_size"] = 1
    receipt["receipt_hash"] = _hash_excluding(receipt, "receipt_hash")

    with pytest.raises(SandboxGateError) as caught:
        verify_tool_output(receipt, PAYLOAD)

    assert caught.value.code == "OUTPUT_SIZE_MISMATCH"
    assert caught.value.context == {"declared": 1, "derived": len(PAYLOAD)}


def test_an_output_that_was_never_captured_as_bytes_is_refused() -> None:
    with pytest.raises(SandboxGateError) as caught:
        output(payload='{"result":42}')  # type: ignore[arg-type]

    assert caught.value.code == "OUTPUT_UNHASHED"


def test_an_unmetered_envelope_cannot_open_a_ledger() -> None:
    with pytest.raises(SandboxGateError) as caught:
        ledger(enforcement="UNMETERED")

    assert caught.value.code == Denial.QUOTA_UNBOUNDED.value


def test_an_estimate_is_too_weak_for_bounded_compute() -> None:
    with pytest.raises(SandboxGateError) as caught:
        ledger(enforcement="SOFT_ESTIMATE")

    assert caught.value.code == Denial.QUOTA_UNBOUNDED.value
    assert caught.value.context["required"] == "HARD_METERED"


def test_high_risk_requires_preallocation() -> None:
    with pytest.raises(SandboxGateError) as caught:
        open_ledger(
            ROOT,
            adapter=seal_adapter(ROOT, manifest(safety_class="high_risk")),
            budget=seal_quota_envelope(ROOT, envelope(enforcement="HARD_METERED")),
        )

    assert caught.value.code == Denial.QUOTA_UNBOUNDED.value


def test_a_read_only_adapter_may_run_on_an_estimate() -> None:
    opened = open_ledger(
        ROOT,
        adapter=seal_adapter(ROOT, manifest(safety_class="read_only")),
        budget=seal_quota_envelope(ROOT, envelope(enforcement="SOFT_ESTIMATE")),
    )

    assert opened.enforcement == "SOFT_ESTIMATE"


@pytest.mark.parametrize("dimension", REQUIRED_BOUNDED_DIMENSIONS)
def test_a_mandatory_ceiling_may_not_be_null(dimension: str) -> None:
    with pytest.raises(SandboxGateError) as caught:
        ledger(hard_limits={dimension: None})

    assert caught.value.code == Denial.QUOTA_UNBOUNDED.value
    assert caught.value.context["unbounded"] == [dimension]


def test_an_adapter_that_may_reach_the_network_must_bound_what_it_sends() -> None:
    with pytest.raises(SandboxGateError) as caught:
        ledger(hard_limits={"network_bytes": None})

    assert caught.value.context["unbounded"] == ["network_bytes"]


def test_an_offline_adapter_needs_no_network_ceiling() -> None:
    opened = open_ledger(
        ROOT,
        adapter=seal_adapter(ROOT, manifest(network_policy="disabled")),
        budget=seal_quota_envelope(ROOT, envelope(hard_limits={"network_bytes": None})),
    )

    assert opened.limits["network_bytes"] is None


def test_consumption_is_charged_and_what_is_left_is_reported() -> None:
    outcome = consume(ROOT, ledger(), "calls", 3)

    assert outcome.breach is None
    assert remaining(outcome.ledger, "calls") == 1
    assert remaining(outcome.ledger, "tokens") is None


def test_an_unknown_dimension_cannot_be_charged() -> None:
    with pytest.raises(SandboxGateError) as caught:
        consume(ROOT, ledger(), "vibes", 1)

    assert caught.value.code == "DIMENSION_UNKNOWN"


@pytest.mark.parametrize("amount", [-1, True, 1.5])
def test_an_invalid_amount_cannot_be_charged(amount: object) -> None:
    with pytest.raises(SandboxGateError) as caught:
        consume(ROOT, ledger(), "calls", amount)  # type: ignore[arg-type]

    assert caught.value.code == "INPUT_INVALID"


def test_a_breach_under_cancel_denies_and_charges_nothing() -> None:
    outcome = consume(ROOT, ledger(breach_policy="CANCEL"), "calls", 5)

    assert outcome.stopped is True
    assert outcome.breach["action"] == "DENIED"
    assert outcome.breach["code"] == Denial.QUOTA_EXHAUSTED.value
    assert outcome.ledger.consumed["calls"] == 0


def test_a_breach_under_escalation_stops_the_invocation() -> None:
    outcome = consume(ROOT, ledger(breach_policy="PAUSE_AND_ESCALATE"), "calls", 5)

    assert outcome.stopped is True
    assert outcome.breach["action"] == "ESCALATED"


def test_a_breach_under_mark_partial_clamps_to_the_ceiling() -> None:
    outcome = consume(ROOT, ledger(breach_policy="MARK_PARTIAL"), "calls", 5)

    assert outcome.stopped is False
    assert outcome.breach["action"] == "TRUNCATED"
    assert outcome.ledger.consumed["calls"] == 4
    assert remaining(outcome.ledger, "calls") == 0


def test_a_breach_under_warn_records_it_and_continues() -> None:
    outcome = consume(ROOT, ledger(breach_policy="WARN"), "calls", 5)

    assert outcome.stopped is False
    assert outcome.breach["action"] == "WARNED"


def test_an_unlimited_dimension_never_breaches() -> None:
    outcome = consume(ROOT, ledger(), "tokens", 10_000_000)

    assert outcome.breach is None


def test_a_deadline_has_a_verdict_in_both_directions() -> None:
    within = evaluate_deadline(ledger(), 30)
    exceeded = evaluate_deadline(ledger(), 31)

    assert within["exceeded"] is False and within["code"] is None
    assert exceeded["exceeded"] is True
    assert exceeded["code"] == Denial.DEADLINE_EXCEEDED.value


@pytest.mark.parametrize("elapsed", [-1, True, 2.5])
def test_an_invalid_elapsed_time_is_refused(elapsed: object) -> None:
    with pytest.raises(SandboxGateError) as caught:
        evaluate_deadline(ledger(), elapsed)  # type: ignore[arg-type]

    assert caught.value.code == "INPUT_INVALID"


def test_the_observation_table_covers_the_whole_effect_vocabulary() -> None:
    mapped = {status for status, _ in OBSERVATION_STATUS.values()}

    assert mapped == set(effect_statuses(ROOT))


def test_a_proven_non_start_is_not_executed_and_needs_no_reconciliation() -> None:
    outcome = reconcile_invocation(
        ROOT,
        observation=Observation.NOT_STARTED.value,
        stop_reason=Denial.QUOTA_EXHAUSTED.value,
    )

    assert outcome["status"] == "NOT_EXECUTED"
    assert outcome["reconciliation_required"] is False


def test_an_interrupted_run_is_unknown_and_must_reconcile() -> None:
    outcome = reconcile_invocation(
        ROOT,
        observation=Observation.STARTED.value,
        stop_reason=Denial.DEADLINE_EXCEEDED.value,
    )

    assert outcome["status"] == "UNKNOWN"
    assert outcome["reconciliation_required"] is True


def test_a_stopped_invocation_cannot_also_have_completed() -> None:
    with pytest.raises(SandboxGateError) as caught:
        reconcile_invocation(
            ROOT,
            observation=Observation.COMPLETED.value,
            stop_reason=Denial.DEADLINE_EXCEEDED.value,
        )

    assert caught.value.code == "OBSERVATION_INCONSISTENT"


@pytest.mark.parametrize(
    ("observation", "stop_reason", "code"),
    [
        ("TIMED_OUT", None, "OBSERVATION_INVALID"),
        (Observation.STARTED.value, "gave_up", "STOP_REASON_INVALID"),
    ],
)
def test_a_non_canonical_outcome_is_refused(
    observation: str, stop_reason: str | None, code: str
) -> None:
    with pytest.raises(SandboxGateError) as caught:
        reconcile_invocation(ROOT, observation=observation, stop_reason=stop_reason)

    assert caught.value.code == code


def test_a_completed_invocation_records_its_hashed_output() -> None:
    receipt = effect()

    assert receipt["status"] == "SUCCEEDED"
    assert receipt["result_artifact_ids"] == ["ART-1"]
    assert receipt["observed_state_hash"].startswith("sha256:")
    assert set(receipt) == {
        "error_artifact_ids",
        "external_operation_id",
        "finished_at",
        "idempotency_key",
        "intent_id",
        "observed_state_hash",
        "receipt_hash",
        "receipt_id",
        "reconciliation_required",
        "result_artifact_ids",
        "run_id",
        "started_at",
        "status",
    }


def test_a_success_with_nothing_hashed_is_refused() -> None:
    with pytest.raises(SandboxGateError) as caught:
        effect(output_receipts=[])

    assert caught.value.code == "RESULT_UNRECORDED"


def test_a_failure_that_records_no_reason_is_refused() -> None:
    with pytest.raises(SandboxGateError) as caught:
        effect(
            outcome=reconcile_invocation(
                ROOT, observation=Observation.FAILED.value, stop_reason=None
            ),
            output_receipts=[],
        )

    assert caught.value.code == "ERROR_UNRECORDED"


def test_a_run_that_never_started_has_no_external_effect() -> None:
    with pytest.raises(SandboxGateError) as caught:
        effect(
            outcome=reconcile_invocation(
                ROOT,
                observation=Observation.NOT_STARTED.value,
                stop_reason=Denial.QUOTA_EXHAUSTED.value,
            ),
            output_receipts=[],
        )

    assert caught.value.code == "OBSERVATION_INCONSISTENT"


def test_a_cancelled_run_still_owes_a_receipt() -> None:
    receipt = effect(
        external_operation_id=None,
        outcome=reconcile_invocation(
            ROOT,
            observation=Observation.NOT_STARTED.value,
            stop_reason=Denial.QUOTA_EXHAUSTED.value,
        ),
        output_receipts=[],
    )

    assert receipt["status"] == "NOT_EXECUTED"
    assert receipt["result_artifact_ids"] == []
    assert receipt["reconciliation_required"] is False


def test_a_timed_out_run_is_unknown_until_it_reconciles() -> None:
    receipt = effect(
        outcome=reconcile_invocation(
            ROOT,
            observation=Observation.STARTED.value,
            stop_reason=Denial.DEADLINE_EXCEEDED.value,
        ),
        output_receipts=[],
    )

    assert receipt["status"] == "UNKNOWN"
    assert receipt["reconciliation_required"] is True


def test_an_unhashed_output_cannot_become_evidence() -> None:
    receipt = output()
    receipt["content_hash"] = "not-a-digest"

    with pytest.raises(SandboxGateError) as caught:
        effect(output_receipts=[receipt])

    assert caught.value.code == "OUTPUT_UNHASHED"


def test_a_tampered_output_cannot_become_evidence() -> None:
    receipt = output()
    receipt["artifact_id"] = "ART-2"

    with pytest.raises(SandboxGateError) as caught:
        effect(output_receipts=[receipt])

    assert caught.value.code == "RECEIPT_HASH_MISMATCH"


def test_an_invocation_cannot_finish_before_it_started() -> None:
    with pytest.raises(SandboxGateError) as caught:
        effect(started_at=FINISHED, finished_at=STARTED)

    assert caught.value.code == "INPUT_INVALID"


def _pick(overrides: dict[str, Any], key: str, default: Any) -> Any:
    """An override of ``[]`` means an empty list, not "use the default"."""

    value = overrides.pop(key, None)
    return default if value is None else value


def gate(**overrides: Any) -> dict[str, Any]:
    opened = _pick(overrides, "ledger", None) or ledger()
    return evaluate_tool_gate(
        ROOT,
        decision=_pick(
            overrides,
            "decision",
            None,
        )
        or authorize_invocation(
            ROOT,
            adapter=seal_adapter(ROOT, manifest()),
            lease=lease(),
            holdout=holdout(),
            request=request(),
            now=NOW,
            policy_hash=POLICY_HASH,
            scope_fencing_heads={"workspace": 7},
        ),
        ledger=opened,
        deadline=_pick(overrides, "deadline", None) or evaluate_deadline(opened, 5),
        output_receipts=_pick(overrides, "output_receipts", [output()]),
        effect_receipt=_pick(overrides, "effect_receipt", None) or effect(),
        declared_status=overrides.pop("declared_status", GateStatus.PASS.value),
    )


def test_a_clean_run_passes_every_criterion() -> None:
    report = gate()

    assert report["status"] == GateStatus.PASS.value
    assert report["failed_criteria"] == []
    assert all(report["checks"].values())
    assert report["report_hash"].startswith("sha256:")


def test_a_timed_out_run_that_reconciled_is_conditional_not_pass() -> None:
    opened = ledger()
    receipt = effect(
        outcome=reconcile_invocation(
            ROOT,
            observation=Observation.STARTED.value,
            stop_reason=Denial.DEADLINE_EXCEEDED.value,
        ),
        output_receipts=[],
    )
    report = gate(
        ledger=opened,
        deadline=evaluate_deadline(opened, 31),
        effect_receipt=receipt,
        output_receipts=[],
        declared_status=GateStatus.CONDITIONAL.value,
    )

    assert report["status"] == GateStatus.CONDITIONAL.value
    assert report["failed_criteria"] == ["deadline_enforced"]


def test_a_pass_declared_over_a_timeout_is_an_overclaim() -> None:
    opened = ledger()
    with pytest.raises(SandboxGateError) as caught:
        gate(
            ledger=opened,
            deadline=evaluate_deadline(opened, 31),
            effect_receipt=effect(
                outcome=reconcile_invocation(
                    ROOT,
                    observation=Observation.STARTED.value,
                    stop_reason=Denial.DEADLINE_EXCEEDED.value,
                ),
                output_receipts=[],
            ),
            output_receipts=[],
        )

    assert caught.value.code == "GATE_OVERCLAIM"
    assert caught.value.context["derived"] == GateStatus.CONDITIONAL.value


def test_a_success_claimed_past_its_own_deadline_does_not_reconcile() -> None:
    opened = ledger()
    report = gate(
        ledger=opened,
        deadline=evaluate_deadline(opened, 31),
        declared_status=GateStatus.FAIL.value,
    )

    assert report["status"] == GateStatus.FAIL.value
    assert report["failed_criteria"] == ["deadline_enforced", "effects_reconciled"]


def test_a_receipt_whose_results_do_not_match_the_outputs_fails() -> None:
    report = gate(
        output_receipts=[output(artifact_id="ART-2", receipt_id="AREC-2")],
        effect_receipt=effect(),
        declared_status=GateStatus.FAIL.value,
    )

    assert report["status"] == GateStatus.FAIL.value
    assert "outputs_hashed" in report["failed_criteria"]


def test_a_tampered_effect_receipt_stops_the_gate() -> None:
    receipt = effect()
    receipt["status"] = "SUCCEEDED "

    with pytest.raises(SandboxGateError) as caught:
        gate(effect_receipt=receipt)

    assert caught.value.code == "RECEIPT_HASH_MISMATCH"


def test_a_non_canonical_declared_status_is_refused() -> None:
    with pytest.raises(SandboxGateError) as caught:
        gate(declared_status="MOSTLY_PASS")

    assert caught.value.code == "INPUT_INVALID"


def test_the_gate_report_is_deterministic() -> None:
    assert gate() == gate()
