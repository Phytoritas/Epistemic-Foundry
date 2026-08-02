"""FORGE transition authority, optimistic concurrency, and gate refusals."""

from __future__ import annotations

import pytest

from epistemic_foundry.domain.status import ForgePhase, GateStatus, WorkClass
from epistemic_foundry.foundry_kernel import ForgeKernel, RevisionConflict, TransitionRejected
from epistemic_foundry.foundry_kernel.gates import (
    GateEvaluation,
    GateSpec,
    WaiverRefused,
    all_passed,
    evaluate_gate,
    gate_decision,
)
from epistemic_foundry.foundry_kernel.transitions import allowed_targets, is_legal_transition
from epistemic_foundry.noetic_ledger import NoeticLedger

POLICY_HASH = "sha256:" + "a" * 64
CORPUS_HASH = "sha256:" + "b" * 64
GATE_INPUT_ARTIFACT_IDS = ("ART-GATE-INPUT-0001",)
GATE_VERSION = "4.0.0"


@pytest.fixture()
def kernel(tmp_path) -> ForgeKernel:
    return ForgeKernel(NoeticLedger(tmp_path / "ledger.jsonl"))


@pytest.fixture()
def session(kernel: ForgeKernel) -> dict:
    return kernel.open_session(
        workspace_id="WS-001",
        run_spec_id="RUN-0001",
        work_class=WorkClass.E3,
        policy_hash=POLICY_HASH,
        corpus_snapshot_hash=CORPUS_HASH,
    )


def _advance(kernel: ForgeKernel, state: dict, to_phase: ForgePhase, **kwargs) -> dict:
    request = kernel.build_request(
        state,
        to_phase=to_phase,
        actor_id="AG-Scout",
        actor_role="evidence_scout",
        reason=f"advance to {to_phase}",
        **{k: v for k, v in kwargs.items() if k != "gate_decisions"},
    )
    return kernel.apply_transition(state, request, gate_decisions=kwargs.get("gate_decisions", ()))


# -- lifecycle map ------------------------------------------------------


def test_interview_is_optional() -> None:
    assert is_legal_transition(ForgePhase.IDLE, ForgePhase.FRAME)
    assert is_legal_transition(ForgePhase.IDLE, ForgePhase.INTERVIEW)


def test_gate_may_send_work_back() -> None:
    targets = allowed_targets(ForgePhase.GATE)
    assert ForgePhase.OBSERVE in targets
    assert ForgePhase.REASON in targets


def test_frame_cannot_skip_observe() -> None:
    assert not is_legal_transition(ForgePhase.FRAME, ForgePhase.REASON)


# -- state machine ------------------------------------------------------


def test_open_session_starts_idle_at_revision_zero(session: dict) -> None:
    assert session["phase"] == "IDLE"
    assert session["revision"] == 0
    assert session["state_hash"].startswith("sha256:")


def test_transition_increments_revision_and_records_history(kernel: ForgeKernel, session: dict) -> None:
    framed = _advance(kernel, session, ForgePhase.FRAME)
    assert framed["phase"] == "F"
    assert framed["revision"] == 1
    assert framed["phase_history"][-1]["from"] == "IDLE"
    assert framed["phase_history"][-1]["to"] == "F"
    kernel.ledger.verify()


def test_rejected_transition_does_not_mutate_the_caller_state(kernel: ForgeKernel, session: dict) -> None:
    before = dict(session)
    with pytest.raises(TransitionRejected):
        _advance(kernel, session, ForgePhase.EXPORT)
    assert session == before


def test_stale_revision_is_a_conflict_not_a_retry(kernel: ForgeKernel, session: dict) -> None:
    """Two actors advancing from the same revision: the second must lose."""
    request_a = kernel.build_request(
        session,
        to_phase=ForgePhase.FRAME,
        actor_id="AG-A",
        actor_role="bounded_maker",
        reason="first writer",
    )
    request_b = kernel.build_request(
        session,
        to_phase=ForgePhase.FRAME,
        actor_id="AG-B",
        actor_role="bounded_maker",
        reason="second writer, same base revision",
    )
    advanced = kernel.apply_transition(session, request_a)
    with pytest.raises(RevisionConflict):
        kernel.apply_transition(advanced, request_b)


def test_illegal_edge_is_refused_even_with_receipts(kernel: ForgeKernel, session: dict) -> None:
    with pytest.raises(TransitionRejected) as excinfo:
        _advance(
            kernel,
            session,
            ForgePhase.REASON,
            artifact_receipt_ids=["AR-1", "AR-2"],
        )
    assert "illegal FORGE phase transition" in str(excinfo.value)


# -- promotion boundary -------------------------------------------------


def _reach_gate(kernel: ForgeKernel, session: dict) -> dict:
    state = _advance(kernel, session, ForgePhase.FRAME)
    state = _advance(kernel, state, ForgePhase.OBSERVE)
    state = _advance(kernel, state, ForgePhase.REASON)
    return _advance(kernel, state, ForgePhase.GATE)


def test_export_without_gate_evidence_is_refused(kernel: ForgeKernel, session: dict) -> None:
    gated = _reach_gate(kernel, session)
    with pytest.raises(TransitionRejected) as excinfo:
        _advance(kernel, gated, ForgePhase.EXPORT)
    assert "gate evidence" in str(excinfo.value)


def test_export_with_failing_gate_is_refused(kernel: ForgeKernel, session: dict) -> None:
    gated = _reach_gate(kernel, session)
    failing = gate_decision(
        evaluate_gate(GateSpec("evidence_grounding", ("evidence_ids",)), {}),
        run_id="RUN-0001",
        policy_version="4.0.0",
        inputs={},
        gate_version=GATE_VERSION,
        input_artifact_ids=GATE_INPUT_ARTIFACT_IDS,
        policy_bundle_hash=POLICY_HASH,
        blocker_ids=(),
    )
    assert failing["status"] == "FAIL"
    with pytest.raises(TransitionRejected) as excinfo:
        _advance(
            kernel,
            gated,
            ForgePhase.EXPORT,
            gate_result_ids=[failing["gate_id"]],
            gate_decisions=[failing],
        )
    assert "unsatisfied gate" in str(excinfo.value)


def test_export_succeeds_only_with_a_resolving_passing_gate(kernel: ForgeKernel, session: dict) -> None:
    gated = _reach_gate(kernel, session)
    passing = gate_decision(
        evaluate_gate(GateSpec("evidence_grounding", ("evidence_ids",)), {"evidence_ids": ["EV-1"]}),
        run_id="RUN-0001",
        policy_version="4.0.0",
        inputs={"evidence_ids": ["EV-1"]},
        gate_version=GATE_VERSION,
        input_artifact_ids=GATE_INPUT_ARTIFACT_IDS,
        policy_bundle_hash=POLICY_HASH,
        blocker_ids=(),
    )
    assert passing["status"] == "PASS"
    exported = _advance(
        kernel,
        gated,
        ForgePhase.EXPORT,
        gate_result_ids=[passing["gate_id"]],
        gate_decisions=[passing],
    )
    assert exported["phase"] == "E"
    kernel.ledger.verify()


def test_unresolved_gate_ids_are_refused(kernel: ForgeKernel, session: dict) -> None:
    """Claiming a gate id without supplying that decision must not promote."""
    gated = _reach_gate(kernel, session)
    passing = gate_decision(
        evaluate_gate(GateSpec("other_gate", ()), {}),
        run_id="RUN-0001",
        policy_version="4.0.0",
        inputs={},
        gate_version=GATE_VERSION,
        input_artifact_ids=GATE_INPUT_ARTIFACT_IDS,
        policy_bundle_hash=POLICY_HASH,
        blocker_ids=(),
    )
    with pytest.raises(TransitionRejected) as excinfo:
        _advance(
            kernel,
            gated,
            ForgePhase.EXPORT,
            gate_result_ids=["GD-does-not-exist"],
            gate_decisions=[passing],
        )
    assert "do not resolve" in str(excinfo.value)


# -- gate semantics -----------------------------------------------------


def test_empty_evidence_list_fails_the_gate() -> None:
    evaluation = evaluate_gate(GateSpec("grounding", ("evidence_ids",)), {"evidence_ids": []})
    assert evaluation.status is GateStatus.FAIL


def test_non_waivable_gate_refuses_a_waiver() -> None:
    evaluation = evaluate_gate(GateSpec("grounding", ("evidence_ids",)), {})
    with pytest.raises(WaiverRefused):
        gate_decision(
            evaluation,
            run_id="RUN-0001",
            policy_version="4.0.0",
            inputs={},
            gate_version=GATE_VERSION,
            input_artifact_ids=GATE_INPUT_ARTIFACT_IDS,
            policy_bundle_hash=POLICY_HASH,
            blocker_ids=(),
            waiver_authority="HUMAN-1",
            waiver_reason="deadline",
        )


def test_waivable_gate_requires_authority_and_reason() -> None:
    evaluation = evaluate_gate(GateSpec("style", ("x",), non_waivable=False), {})
    with pytest.raises(ValueError):
        gate_decision(
            evaluation,
            run_id="RUN-0001",
            policy_version="4.0.0",
            inputs={},
            gate_version=GATE_VERSION,
            input_artifact_ids=GATE_INPUT_ARTIFACT_IDS,
            policy_bundle_hash=POLICY_HASH,
            blocker_ids=(),
            waiver_authority="HUMAN-1",
        )


def test_gate_decisions_are_deterministic_for_equal_inputs() -> None:
    spec = GateSpec("grounding", ("evidence_ids",))
    inputs = {"evidence_ids": ["EV-1"]}
    first = gate_decision(
        evaluate_gate(spec, inputs),
        run_id="RUN-0001",
        policy_version="4.0.0",
        inputs=inputs,
        gate_version=GATE_VERSION,
        input_artifact_ids=GATE_INPUT_ARTIFACT_IDS,
        policy_bundle_hash=POLICY_HASH,
        blocker_ids=(),
        gate_id="GD-DETERMINISTIC-0001",
        evaluated_at="2026-07-27T00:00:00+00:00",
    )
    second = gate_decision(
        evaluate_gate(spec, {"evidence_ids": ["EV-1"]}),
        run_id="RUN-0001",
        policy_version="4.0.0",
        inputs={"evidence_ids": ["EV-1"]},
        gate_version=GATE_VERSION,
        input_artifact_ids=GATE_INPUT_ARTIFACT_IDS,
        policy_bundle_hash=POLICY_HASH,
        blocker_ids=(),
        gate_id="GD-DETERMINISTIC-0001",
        evaluated_at="2026-07-27T00:00:00+00:00",
    )
    assert first["input_hash"] == second["input_hash"]
    assert first["decision_hash"] == second["decision_hash"]
    assert first["evaluated_at"] == first["created_at"]
    assert first == second


def test_fail_and_block_are_never_absorbed() -> None:
    blocked = {"status": "BLOCK", "name": "leakage"}
    assert all_passed([{"status": "PASS"}, {"status": "WAIVE"}]) is True
    assert all_passed([{"status": "PASS"}, blocked]) is False
    assert all_passed([{"status": "FAIL"}]) is False


def test_gate_evaluation_defaults_to_non_waivable() -> None:
    assert GateEvaluation(name="g", status=GateStatus.PASS).non_waivable is True
