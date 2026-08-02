"""approval_test — typed refusal flows for tools that require approval.

Approval verification sits inside CAPABILITY_AUTHORIZATION, after policy
evaluation and before lease issuance, so a refusal must leave no lease, no
intent, and no effect behind.
"""

from __future__ import annotations

import pytest
from harness import (
    APPROVER,
    PRINCIPAL,
    ApprovalRecord,
    call_arguments,
)

from epistemic_foundry.application.mcp_common import AuthContext
from epistemic_foundry.application.mcp_mutating import MUTATION_ERROR_MAPPING

HUMAN_REQUIRED_TOOLS = (
    "foundry.claim.promote",
    "foundry.validation.execute",
    "foundry.passport.publish",
    "foundry.skill.activate",
)
CONSENT_REQUIRED_TOOL = "foundry.memory.write"
POLICY_ONLY_TOOL = "foundry.session.transition"


def _record(catalog, tool: str, **overrides) -> ApprovalRecord:
    fields = {
        "approval_id": "approval-1",
        "approver_id": APPROVER,
        "operation": catalog.spec(tool).handler_operation,
    }
    fields.update(overrides)
    return ApprovalRecord(**fields)


def _assert_refused(harness, envelope, is_error: bool, code: str) -> None:
    assert is_error is True
    assert envelope["error_code"] == MUTATION_ERROR_MAPPING[code]
    assert envelope["details"]["mutation_error_code"] == code
    assert harness.leases.issued == []
    assert harness.intents.intents == []
    assert harness.receipts.receipts == []
    assert harness.executor.executions == []
    assert harness.executor.previews == []


@pytest.mark.parametrize("tool", HUMAN_REQUIRED_TOOLS)
def test_a_human_required_tool_refuses_without_approval(
    build_harness, tool: str
) -> None:
    harness = build_harness()

    envelope, is_error = harness.call(tool)

    _assert_refused(harness, envelope, is_error, "APPROVAL_REQUIRED")


def test_a_consent_required_tool_refuses_without_consent(build_harness) -> None:
    harness = build_harness()

    envelope, is_error = harness.call(CONSENT_REQUIRED_TOOL)

    _assert_refused(harness, envelope, is_error, "APPROVAL_REQUIRED")


def test_a_policy_conditional_tool_proceeds_without_approval(build_harness) -> None:
    harness = build_harness()

    envelope, is_error = harness.call(POLICY_ONLY_TOOL)

    assert is_error is False
    assert harness.approvals.calls == [("mutate_session_transition", ())]
    assert envelope["data"]["mutation"]["effect_status"] == "SUCCEEDED"


def test_an_unresolvable_approval_is_invalid_and_discloses_nothing(
    build_harness, catalog
) -> None:
    harness = build_harness()

    envelope, is_error = harness.call(
        HUMAN_REQUIRED_TOOLS[0], approval_record_ids=["approval-ghost"]
    )

    _assert_refused(harness, envelope, is_error, "APPROVAL_INVALID")
    # Concealment: the message must not reveal whether the record exists.
    assert "approval-ghost" not in envelope["message"]
    assert "not found" not in envelope["message"].lower()


def test_a_denied_approval_is_reported_as_denied(build_harness, catalog) -> None:
    tool = HUMAN_REQUIRED_TOOLS[1]
    harness = build_harness(approvals=[_record(catalog, tool, valid=False)])

    envelope, is_error = harness.call(tool, approval_record_ids=["approval-1"])

    _assert_refused(harness, envelope, is_error, "APPROVAL_DENIED")


def test_an_approval_bound_to_another_operation_is_invalid(
    build_harness, catalog
) -> None:
    tool = HUMAN_REQUIRED_TOOLS[2]
    harness = build_harness(
        approvals=[_record(catalog, tool, operation="mutate_session_transition")]
    )

    envelope, is_error = harness.call(tool, approval_record_ids=["approval-1"])

    _assert_refused(harness, envelope, is_error, "APPROVAL_INVALID")


def test_self_approval_is_refused_by_the_service_itself(build_harness, catalog) -> None:
    tool = HUMAN_REQUIRED_TOOLS[3]
    harness = build_harness(approvals=[_record(catalog, tool, approver_id=PRINCIPAL)])

    envelope, is_error = harness.call(tool, approval_record_ids=["approval-1"])

    _assert_refused(harness, envelope, is_error, "SELF_APPROVAL_FORBIDDEN")


def test_a_verified_approval_binds_the_lease_and_the_intent(
    build_harness, catalog
) -> None:
    tool = HUMAN_REQUIRED_TOOLS[0]
    harness = build_harness(approvals=[_record(catalog, tool)])

    envelope, is_error = harness.call(tool, approval_record_ids=["approval-1"])

    assert is_error is False
    assert harness.leases.issued[0].approval_ids == ("approval-1",)
    assert harness.intents.intents[0]["approval_record_ids"] == ["approval-1"]
    assert envelope["data"]["mutation"]["capability_lease_id"] == "lease-1"


def test_approval_verification_runs_after_policy_and_before_the_lease(
    build_harness, catalog
) -> None:
    tool = HUMAN_REQUIRED_TOOLS[0]
    harness = build_harness()

    harness.call(tool)

    # Policy ran first and set the requirement; with no evidence declared the
    # refusal is immediate, so the resolver is never consulted and no lease is
    # ever issued.
    assert harness.policy.calls == [catalog.spec(tool).handler_operation]
    assert harness.approvals.calls == []
    assert harness.leases.issued == []


def test_a_dry_run_still_requires_approval(build_harness) -> None:
    harness = build_harness()

    envelope, is_error = harness.call(HUMAN_REQUIRED_TOOLS[0], dry_run=True)

    _assert_refused(harness, envelope, is_error, "APPROVAL_REQUIRED")


def test_a_missing_capability_is_refused_before_policy(build_harness, catalog) -> None:
    tool = HUMAN_REQUIRED_TOOLS[0]
    harness = build_harness(approvals=[_record(catalog, tool)])
    unprivileged = AuthContext(
        capabilities=frozenset(),
        principal_id=PRINCIPAL,
        workspace_id="ws-t02",
    )

    envelope, is_error = harness.call(
        tool, approval_record_ids=["approval-1"], auth=unprivileged
    )

    assert is_error is True
    assert envelope["error_code"] == "UNAUTHORIZED"
    assert envelope["details"] is None
    assert harness.policy.calls == []
    assert harness.approvals.calls == []


def test_every_refusal_maps_onto_the_sealed_error_enum(build_harness, catalog) -> None:
    tool = HUMAN_REQUIRED_TOOLS[0]
    harness = build_harness()

    envelope, _ = harness.call(tool)

    catalog.validate_error_envelope(envelope)
    assert envelope["retryable"] is False
    assert envelope["tool"] == tool


def test_duplicate_approval_ids_violate_the_shared_input_schema(
    build_harness, catalog
) -> None:
    harness = build_harness(approvals=[_record(catalog, HUMAN_REQUIRED_TOOLS[0])])
    arguments = call_arguments(
        catalog,
        HUMAN_REQUIRED_TOOLS[0],
        approval_record_ids=["approval-1", "approval-1"],
    )

    envelope, is_error = harness.service.call(
        HUMAN_REQUIRED_TOOLS[0],
        arguments,
        harness.auth(HUMAN_REQUIRED_TOOLS[0]),
        request_id="req-dup",
    )

    assert is_error is True
    assert envelope["error_code"] == "INVALID_INPUT"
    assert harness.policy.calls == []


def test_an_oversized_idempotency_key_violates_the_shared_input_schema(
    build_harness, catalog
) -> None:
    harness = build_harness()
    arguments = call_arguments(catalog, POLICY_ONLY_TOOL, idempotency_key="k" * 201)

    envelope, is_error = harness.service.call(
        POLICY_ONLY_TOOL,
        arguments,
        harness.auth(POLICY_ONLY_TOOL),
        request_id="req-long",
    )

    assert is_error is True
    assert envelope["error_code"] == "INVALID_INPUT"
    assert harness.policy.calls == []


def test_a_client_supplied_lease_or_receipt_is_rejected(build_harness, catalog) -> None:
    harness = build_harness()

    for forged in ("capability_lease", "effect_receipt", "capability_lease_id"):
        arguments = call_arguments(catalog, POLICY_ONLY_TOOL)
        arguments[forged] = "forged"

        envelope, is_error = harness.service.call(
            POLICY_ONLY_TOOL,
            arguments,
            harness.auth(POLICY_ONLY_TOOL),
            request_id="req-forged",
        )

        assert is_error is True, forged
        assert envelope["error_code"] == "INVALID_INPUT", forged
        assert harness.leases.issued == []
