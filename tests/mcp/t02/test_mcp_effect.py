"""mcp_effect_test — no mutation without a lease, and every effect reconciles.

Exit criteria under test (manifests/development_manifest.yaml, T02):
  * "no mutation without lease"
  * "effects reconcile"
"""

from __future__ import annotations

import pytest

from epistemic_foundry.application.mcp_mutating import (
    DRY_RUN_OPERATION_ID,
    UNOBSERVED_OPERATION_ID,
    EffectOutcome,
    is_unresolved,
    outstanding_receipts,
    reconcile,
    reconciliation_report,
    semantic_fingerprint,
)
from epistemic_foundry.application.mcp_common import AuthContext
from harness import (
    APPROVER,
    PRINCIPAL,
    TARGET,
    WORKSPACE,
    ApprovalRecord,
    FakeExecutor,
    FakeLeaseIssuer,
    call_arguments,
)

POLICY_ONLY_TOOL = "foundry.session.transition"
NO_REVISION_TOOL = "foundry.corpus.register"
APPROVED_TOOL = "foundry.claim.promote"


def _approval(catalog, tool: str, identifier: str = "approval-1") -> ApprovalRecord:
    return ApprovalRecord(
        approval_id=identifier,
        approver_id=APPROVER,
        operation=catalog.spec(tool).handler_operation,
    )


def test_a_committed_effect_binds_intent_lease_and_receipt(build_harness) -> None:
    harness = build_harness()

    envelope, is_error = harness.call(POLICY_ONLY_TOOL)

    assert is_error is False
    mutation = envelope["data"]["mutation"]
    assert mutation["effect_status"] == "SUCCEEDED"
    assert mutation["committed"] is True
    assert mutation["new_revision"] == "rev-2"
    assert mutation["reconciliation_required"] is False
    assert mutation["action_intent_id"] == harness.intents.intents[0]["intent_id"]
    assert mutation["capability_lease_id"] == harness.leases.issued[0].lease_id
    assert mutation["effect_receipt_id"] == harness.receipts.receipts[0]["receipt_id"]
    assert envelope["receipts"][0]["artifact_id"] == mutation["action_intent_id"]


def test_the_lease_is_issued_before_the_effect_and_revalidated(build_harness) -> None:
    harness = build_harness()

    harness.call(POLICY_ONLY_TOOL)

    assert len(harness.leases.issued) == 1
    assert harness.leases.revalidations == 1
    lease = harness.leases.issued[0]
    assert lease.resource_scopes == (f"{WORKSPACE}:{TARGET}",)
    assert lease.capabilities == (harness.catalog.spec(POLICY_ONLY_TOOL).capability,)


def test_no_effect_is_attempted_when_the_lease_scope_is_wrong(build_harness) -> None:
    harness = build_harness(leases=FakeLeaseIssuer(scope_override="other-ws:other"))

    envelope, is_error = harness.call(POLICY_ONLY_TOOL)

    assert is_error is True
    assert envelope["details"]["mutation_error_code"] == "LEASE_INVALID"
    assert harness.executor.executions == []
    assert harness.intents.intents == []
    assert harness.receipts.receipts == []


def test_no_effect_is_attempted_when_the_lease_is_revoked(build_harness) -> None:
    harness = build_harness(leases=FakeLeaseIssuer(revoke_before_effect=True))

    envelope, is_error = harness.call(POLICY_ONLY_TOOL)

    assert is_error is True
    assert envelope["details"]["mutation_error_code"] == "LEASE_INVALID"
    assert harness.executor.executions == []
    # The intent is durable evidence that the attempt was admitted and stopped.
    assert len(harness.intents.intents) == 1
    assert harness.receipts.receipts == []


def test_a_policy_that_denies_the_capability_blocks_the_effect(build_harness) -> None:
    harness = build_harness(grant_capability=False)

    envelope, is_error = harness.call(POLICY_ONLY_TOOL)

    assert is_error is True
    assert envelope["details"]["mutation_error_code"] == "LEASE_DENIED"
    assert harness.leases.issued == []
    assert harness.executor.executions == []


def test_a_lease_that_drops_its_approval_binding_blocks_the_effect(
    build_harness, catalog
) -> None:
    harness = build_harness(
        approvals=[_approval(catalog, APPROVED_TOOL)],
        leases=FakeLeaseIssuer(drop_approval_binding=True),
    )

    envelope, is_error = harness.call(APPROVED_TOOL, approval_record_ids=["approval-1"])

    assert is_error is True
    assert envelope["details"]["mutation_error_code"] == "LEASE_INVALID"
    assert harness.executor.executions == []


def test_a_revision_conflict_blocks_the_effect(build_harness) -> None:
    harness = build_harness(revisions={(WORKSPACE, TARGET): "rev-9"})

    envelope, is_error = harness.call(POLICY_ONLY_TOOL, expected_revision="rev-1")

    assert is_error is True
    assert envelope["error_code"] == "INVALID_REQUEST"
    assert envelope["details"]["mutation_error_code"] == "REVISION_CONFLICT"
    assert harness.executor.executions == []
    assert len(harness.intents.intents) == 1


def test_a_tool_without_expected_revision_ignores_target_drift(build_harness) -> None:
    harness = build_harness(revisions={(WORKSPACE, TARGET): "rev-9"})

    envelope, is_error = harness.call(NO_REVISION_TOOL)

    assert is_error is False
    assert envelope["data"]["mutation"]["expected_revision"] is None
    assert envelope["data"]["mutation"]["observed_revision"] == "rev-9"
    assert harness.executor.executions == ["mutate_corpus_register"]


def test_a_dry_run_records_evidence_and_executes_nothing(build_harness) -> None:
    harness = build_harness()

    envelope, is_error = harness.call(POLICY_ONLY_TOOL, dry_run=True)

    mutation = envelope["data"]["mutation"]
    assert is_error is False
    assert mutation["dry_run"] is True
    assert mutation["effect_status"] == "NOT_EXECUTED"
    assert mutation["committed"] is False
    assert mutation["new_revision"] is None
    assert mutation["reconciliation_required"] is False
    assert harness.executor.executions == []
    assert harness.executor.previews == ["mutate_session_transition"]
    # Durable proof that admission succeeded and the effect was declined.
    assert len(harness.intents.intents) == 1
    receipt = harness.receipts.receipts[0]
    assert receipt["status"] == "NOT_EXECUTED"
    assert receipt["external_operation_id"] == DRY_RUN_OPERATION_ID
    schema = harness.catalog.input_schema(POLICY_ONLY_TOOL)
    assert envelope["data"]["preview"] == {
        "would_change": sorted(schema["properties"]["arguments"]["properties"])
    }


def test_a_dry_run_key_cannot_be_reused_for_a_live_commit(
    build_harness, catalog
) -> None:
    harness = build_harness()
    auth = harness.auth(POLICY_ONLY_TOOL)

    dry = semantic_fingerprint(
        arguments=call_arguments(catalog, POLICY_ONLY_TOOL, dry_run=True),
        auth=auth,
        tool=POLICY_ONLY_TOOL,
    )
    live = semantic_fingerprint(
        arguments=call_arguments(catalog, POLICY_ONLY_TOOL, dry_run=False),
        auth=auth,
        tool=POLICY_ONLY_TOOL,
    )

    assert dry != live

    harness.call(POLICY_ONLY_TOOL, dry_run=True, idempotency_key="shared")
    envelope, is_error = harness.call(
        POLICY_ONLY_TOOL, dry_run=False, idempotency_key="shared"
    )

    assert is_error is True
    assert envelope["error_code"] == "IDEMPOTENCY_CONFLICT"
    assert harness.executor.executions == []


def test_supplying_approvals_after_a_refusal_is_not_an_idempotency_conflict(
    build_harness, catalog
) -> None:
    harness = build_harness(approvals=[_approval(catalog, APPROVED_TOOL)])

    refused, refused_is_error = harness.call(APPROVED_TOOL, idempotency_key="shared")
    accepted, accepted_is_error = harness.call(
        APPROVED_TOOL, idempotency_key="shared", approval_record_ids=["approval-1"]
    )

    assert refused_is_error is True
    assert refused["details"]["mutation_error_code"] == "APPROVAL_REQUIRED"
    assert accepted_is_error is False
    assert accepted["data"]["mutation"]["effect_status"] == "SUCCEEDED"


def test_replaying_a_committed_key_returns_the_stored_receipt(build_harness) -> None:
    harness = build_harness()

    first, _ = harness.call(POLICY_ONLY_TOOL, idempotency_key="once")
    second, is_error = harness.call(POLICY_ONLY_TOOL, idempotency_key="once")

    assert is_error is False
    assert harness.executor.executions == ["mutate_session_transition"]
    assert len(harness.receipts.receipts) == 1
    assert (
        second["data"]["mutation"]["effect_receipt_id"]
        == first["data"]["mutation"]["effect_receipt_id"]
    )


def test_a_reused_key_with_a_different_request_is_a_conflict(build_harness) -> None:
    harness = build_harness()

    harness.call(POLICY_ONLY_TOOL, idempotency_key="once")
    envelope, is_error = harness.call(
        POLICY_ONLY_TOOL, idempotency_key="once", target_ref="target-beta"
    )

    assert is_error is True
    assert envelope["error_code"] == "IDEMPOTENCY_CONFLICT"
    assert harness.executor.executions == ["mutate_session_transition"]


def test_an_unresolved_effect_is_unknown_and_never_claims_failure(
    build_harness,
) -> None:
    harness = build_harness(
        executor=FakeExecutor(
            outcome=EffectOutcome(
                external_operation_id="op-remote",
                observed_state_hash="sha256:" + "0" * 64,
                status="UNKNOWN",
            )
        )
    )

    envelope, is_error = harness.call(POLICY_ONLY_TOOL)

    mutation = envelope["data"]["mutation"]
    # An unresolved effect is a result envelope, not an INTERNAL error.
    assert is_error is False
    assert "error_code" not in envelope
    assert mutation["effect_status"] == "UNKNOWN"
    assert mutation["committed"] is None
    assert mutation["reconciliation_required"] is True
    assert envelope["read_model_state"] == "DEGRADED"


def test_a_crash_between_intent_and_receipt_replays_as_unknown(build_harness) -> None:
    harness = build_harness()
    fingerprint = semantic_fingerprint(
        arguments=call_arguments(
            harness.catalog, POLICY_ONLY_TOOL, idempotency_key="crashed"
        ),
        auth=harness.auth(POLICY_ONLY_TOOL),
        tool=POLICY_ONLY_TOOL,
    )
    harness.idempotency.seed(
        "crashed", fingerprint, intent_id="intent-orphan", receipt_id=None
    )

    envelope, is_error = harness.call(POLICY_ONLY_TOOL, idempotency_key="crashed")

    mutation = envelope["data"]["mutation"]
    assert is_error is False
    assert mutation["effect_status"] == "UNKNOWN"
    assert mutation["committed"] is None
    assert mutation["reconciliation_required"] is True
    # The effect is never re-attempted while the outcome is unknown.
    assert harness.executor.executions == []
    assert (
        harness.receipts.receipts[0]["external_operation_id"] == UNOBSERVED_OPERATION_ID
    )


def test_a_reservation_without_an_intent_may_safely_continue(build_harness) -> None:
    harness = build_harness()
    fingerprint = semantic_fingerprint(
        arguments=call_arguments(
            harness.catalog, POLICY_ONLY_TOOL, idempotency_key="stub"
        ),
        auth=harness.auth(POLICY_ONLY_TOOL),
        tool=POLICY_ONLY_TOOL,
    )
    harness.idempotency.seed("stub", fingerprint, intent_id=None, receipt_id=None)

    envelope, is_error = harness.call(POLICY_ONLY_TOOL, idempotency_key="stub")

    assert is_error is False
    assert envelope["data"]["mutation"]["effect_status"] == "SUCCEEDED"
    assert harness.executor.executions == ["mutate_session_transition"]


class _Probe:
    def __init__(self, outcome: EffectOutcome | None) -> None:
        self.outcome = outcome
        self.calls: list[str] = []

    def observe(self, *, operation, external_operation_id, intent):
        self.calls.append(external_operation_id)
        return self.outcome


def test_reconciliation_closes_an_unknown_receipt(build_harness) -> None:
    harness = build_harness(
        executor=FakeExecutor(
            outcome=EffectOutcome(
                external_operation_id="op-remote",
                observed_state_hash="sha256:" + "0" * 64,
                status="UNKNOWN",
            )
        )
    )
    harness.call(POLICY_ONLY_TOOL)
    unresolved = harness.receipts.receipts[0]
    probe = _Probe(
        EffectOutcome(
            external_operation_id="op-remote",
            new_revision="rev-2",
            observed_state_hash="sha256:" + "1" * 64,
            status="SUCCEEDED",
        )
    )

    resolved = reconcile(
        intent=harness.intents.intents[0],
        probe=probe,
        receipts=harness.receipts,
        unresolved=unresolved,
    )

    assert probe.calls == ["op-remote"]
    assert resolved["status"] == "SUCCEEDED"
    assert resolved["reconciliation_required"] is False
    assert resolved["reconciles_receipt_id"] == unresolved["receipt_id"]
    assert is_unresolved(unresolved) is True
    assert is_unresolved(resolved) is False
    report = reconciliation_report(
        intents=harness.intents.intents, receipts=harness.receipts.receipts
    )
    assert report["reconciled"] is True
    assert report["unresolved_intent_ids"] == []


def test_a_probe_that_cannot_observe_leaves_the_obligation_open(build_harness) -> None:
    harness = build_harness(
        executor=FakeExecutor(
            outcome=EffectOutcome(
                external_operation_id="op-remote",
                observed_state_hash="sha256:" + "0" * 64,
                status="UNKNOWN",
            )
        )
    )
    harness.call(POLICY_ONLY_TOOL)
    unresolved = harness.receipts.receipts[0]

    still = reconcile(
        intent=harness.intents.intents[0],
        probe=_Probe(None),
        receipts=harness.receipts,
        unresolved=unresolved,
    )

    assert still is unresolved
    assert len(harness.receipts.receipts) == 1
    report = reconciliation_report(
        intents=harness.intents.intents, receipts=harness.receipts.receipts
    )
    assert report["reconciled"] is False
    assert report["unresolved_intent_ids"] == [harness.intents.intents[0]["intent_id"]]
    assert outstanding_receipts(harness.receipts.receipts) == (unresolved,)


def test_a_probe_may_not_report_a_non_terminal_status(build_harness) -> None:
    harness = build_harness(
        executor=FakeExecutor(
            outcome=EffectOutcome(
                external_operation_id="op-remote",
                observed_state_hash="sha256:" + "0" * 64,
                status="UNKNOWN",
            )
        )
    )
    harness.call(POLICY_ONLY_TOOL)

    with pytest.raises(Exception) as caught:
        reconcile(
            intent=harness.intents.intents[0],
            probe=_Probe(
                EffectOutcome(
                    external_operation_id="op-remote",
                    observed_state_hash="sha256:" + "0" * 64,
                    status="UNKNOWN",
                )
            ),
            receipts=harness.receipts,
            unresolved=harness.receipts.receipts[0],
        )

    assert "terminal status" in str(caught.value)


def test_a_reconciliation_report_flags_an_intent_with_no_receipt() -> None:
    report = reconciliation_report(
        intents=[{"intent_id": "intent-1"}, {"intent_id": "intent-2"}],
        receipts=[{"intent_id": "intent-1", "status": "SUCCEEDED"}],
    )

    assert report["reconciled"] is False
    assert report["intents_missing_receipts"] == ["intent-2"]
    assert report["report_hash"].startswith("sha256:")


def test_a_reconciliation_report_flags_an_orphaned_receipt() -> None:
    report = reconciliation_report(
        intents=[{"intent_id": "intent-1"}],
        receipts=[
            {"intent_id": "intent-1", "status": "SUCCEEDED"},
            {"intent_id": "intent-ghost", "status": "SUCCEEDED"},
        ],
    )

    assert report["reconciled"] is False
    assert report["orphaned_receipt_intent_ids"] == ["intent-ghost"]


def test_cross_workspace_access_is_denied_before_any_authority_work(
    build_harness, catalog
) -> None:
    harness = build_harness()
    foreign = AuthContext(
        capabilities=frozenset({catalog.spec(POLICY_ONLY_TOOL).capability}),
        principal_id=PRINCIPAL,
        workspace_id="ws-other",
    )

    envelope, is_error = harness.call(POLICY_ONLY_TOOL, auth=foreign)

    assert is_error is True
    assert envelope["error_code"] == "WORKSPACE_DENIED"
    assert harness.policy.calls == []
    assert harness.leases.issued == []


def test_an_unauthenticated_call_never_reaches_policy(build_harness) -> None:
    harness = build_harness()
    anonymous = AuthContext(
        capabilities=frozenset(), principal_id=None, workspace_id=WORKSPACE
    )

    envelope, is_error = harness.call(POLICY_ONLY_TOOL, auth=anonymous)

    assert is_error is True
    assert envelope["error_code"] == "UNAUTHENTICATED"
    assert harness.policy.calls == []


def test_every_mutating_tool_completes_the_lifecycle(build_harness, catalog) -> None:
    for tool in catalog.tool_names:
        spec = catalog.spec(tool)
        approvals = (
            [_approval(catalog, tool)]
            if spec.approval_class in {"HUMAN_REQUIRED", "CONSENT_REQUIRED"}
            else []
        )
        harness = build_harness(approvals=approvals)

        envelope, is_error = harness.call(
            tool, approval_record_ids=[record.approval_id for record in approvals]
        )

        assert is_error is False, tool
        assert envelope["data"]["mutation"]["effect_status"] == "SUCCEEDED", tool
        assert harness.executor.executions == [spec.handler_operation], tool
        assert len(harness.receipts.receipts) == 1, tool
