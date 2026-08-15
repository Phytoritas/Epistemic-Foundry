"""T01 authorization, workspace isolation, and confidentiality ordering."""

from __future__ import annotations

import pytest
from test_t01_shared_handlers import (
    WORKSPACE,
    build_service,
    call_arguments,
    fixture_auth,
    full_capabilities,
)

from epistemic_foundry.application.mcp_common import AUTHORIZATION_ORDER


def test_t01_authorization_order_is_frozen() -> None:
    assert AUTHORIZATION_ORDER == (
        "PROTOCOL_VALIDATION",
        "INPUT_SCHEMA_VALIDATION",
        "AUTHENTICATION",
        "WORKSPACE_ISOLATION",
        "CAPABILITY_AUTHORIZATION",
        "CONFIDENTIALITY_CONCEALMENT",
        "HANDLER_EXECUTION",
    )


def test_t01_authorization_unknown_tool_precedes_authentication() -> None:
    service, _read_port, _compiler, _store = build_service()
    envelope, is_error = service.call(
        "foundry.nope",
        {"workspace_id": WORKSPACE},
        fixture_auth(principal_id=None),
        request_id="R1",
    )

    assert is_error
    assert envelope["error_code"] == "UNKNOWN_TOOL"
    assert envelope["tool"] is None


def test_t01_authorization_input_validation_precedes_authentication() -> None:
    service, _read_port, _compiler, _store = build_service()
    envelope, is_error = service.call(
        "foundry.claim.get",
        {"workspace_id": WORKSPACE, "claim_id": ""},
        fixture_auth(principal_id=None),
        request_id="R1",
    )

    assert is_error
    assert envelope["error_code"] == "INVALID_INPUT"
    assert envelope["details"]["schema_errors"]


def test_t01_authorization_unauthenticated_precedes_existence() -> None:
    service, _read_port, _compiler, _store = build_service()
    envelope, is_error = service.call(
        "foundry.claim.get",
        {"workspace_id": WORKSPACE, "claim_id": "CLM-missing"},
        fixture_auth(principal_id=None),
        request_id="R1",
    )

    assert is_error
    assert envelope["error_code"] == "UNAUTHENTICATED"


def test_t01_authorization_workspace_isolation_precedes_capability() -> None:
    service, _read_port, _compiler, _store = build_service()
    envelope, is_error = service.call(
        "foundry.claim.get",
        {"workspace_id": "WS-other", "claim_id": "CLM-0001"},
        fixture_auth(capabilities=frozenset()),
        request_id="R1",
    )

    assert is_error
    assert envelope["error_code"] == "WORKSPACE_DENIED"


def test_t01_authorization_capability_denial_precedes_existence() -> None:
    service, read_port, _compiler, _store = build_service()
    read_port.records["read_claim"] = {
        "found": False,
        "state": "EMPTY_CONFIRMED",
        "data": None,
        "reason": None,
    }
    envelope, is_error = service.call(
        "foundry.claim.get",
        call_arguments("foundry.claim.get"),
        fixture_auth(capabilities=full_capabilities() - {"mcp.read.claim"}),
        request_id="R1",
    )

    assert is_error
    assert envelope["error_code"] == "UNAUTHORIZED"
    assert read_port.calls == []


def test_t01_authorization_concealment_answers_not_found() -> None:
    service, read_port, _compiler, _store = build_service()
    read_port.records["read_claim"] = {
        "found": False,
        "state": "EMPTY_CONFIRMED",
        "data": None,
        "reason": None,
    }

    envelope, is_error = service.call(
        "foundry.claim.get",
        call_arguments("foundry.claim.get"),
        fixture_auth(),
        request_id="R1",
    )

    assert is_error
    assert envelope["error_code"] == "NOT_FOUND"
    assert "authorized scope" in envelope["message"]


def test_t01_authorization_malformed_ready_is_validated_before_concealment() -> None:
    service, read_port, _compiler, _store = build_service()
    read_port.records["read_claim"] = {
        "found": False,
        "state": "READY",
        "data": {"claim_id": "CLM-0001"},
        "reason": None,
    }

    envelope, is_error = service.call(
        "foundry.claim.get",
        call_arguments("foundry.claim.get"),
        fixture_auth(),
        request_id="R1",
    )

    assert is_error
    assert envelope["error_code"] == "INTERNAL"
    assert "READY requires found=True" in envelope["message"]


def test_t01_authorization_concealment_is_indistinguishable_from_absence() -> None:
    absent_service, absent_port, _compiler, _store = build_service()
    absent_port.records["read_passport"] = {
        "found": False,
        "state": "EMPTY_CONFIRMED",
        "data": None,
        "reason": None,
    }
    concealed_service, concealed_port, _c2, _s2 = build_service()
    concealed_port.records["read_passport"] = {
        "found": False,
        "state": "EMPTY_CONFIRMED",
        "data": None,
        "reason": None,
    }

    absent, _ = absent_service.call(
        "foundry.passport.get",
        call_arguments("foundry.passport.get"),
        fixture_auth(),
        request_id="R1",
    )
    concealed, _ = concealed_service.call(
        "foundry.passport.get",
        call_arguments("foundry.passport.get"),
        fixture_auth(),
        request_id="R1",
    )

    assert absent == concealed


@pytest.mark.parametrize(
    ("state", "reason"),
    [
        ("DEGRADED", "read replica lagging"),
        ("UNAVAILABLE", "read model offline"),
    ],
)
def test_t01_authorization_concealing_tools_report_nonabsence_states_honestly(
    state: str, reason: str
) -> None:
    service, read_port, _compiler, _store = build_service()
    read_port.records["read_claim"] = {
        "found": False,
        "state": state,
        "data": None,
        "reason": reason,
    }

    envelope, is_error = service.call(
        "foundry.claim.get",
        call_arguments("foundry.claim.get"),
        fixture_auth(),
        request_id="R1",
    )

    assert not is_error
    assert "error_code" not in envelope
    assert envelope["read_model_state"] == state
    assert envelope["data"] is None
    assert envelope["degradation_reason"] == reason


@pytest.mark.parametrize("tool", ["foundry.status", "foundry.health"])
def test_t01_authorization_non_concealing_tools_do_not_conceal(tool: str) -> None:
    service, read_port, _compiler, _store = build_service()
    operation = service.catalog.tools[tool].handler_operation
    read_port.records[operation] = {
        "found": False,
        "state": "UNAVAILABLE",
        "data": None,
        "reason": "probe failed",
    }

    envelope, is_error = service.call(
        tool, call_arguments(tool), fixture_auth(), request_id="R1"
    )

    assert not is_error
    assert envelope["read_model_state"] == "UNAVAILABLE"


def test_t01_authorization_planning_tools_enforce_the_same_boundary() -> None:
    service, _read_port, compiler, store = build_service()

    unauthenticated, _ = service.call(
        "foundry.search.plan",
        call_arguments("foundry.search.plan"),
        fixture_auth(principal_id=None),
        request_id="R1",
    )
    cross_workspace, _ = service.call(
        "foundry.search.plan",
        {**call_arguments("foundry.search.plan"), "workspace_id": "WS-other"},
        fixture_auth(),
        request_id="R2",
    )
    unauthorized, _ = service.call(
        "foundry.search.plan",
        call_arguments("foundry.search.plan"),
        fixture_auth(capabilities=full_capabilities() - {"mcp.plan.search"}),
        request_id="R3",
    )

    assert unauthenticated["error_code"] == "UNAUTHENTICATED"
    assert cross_workspace["error_code"] == "WORKSPACE_DENIED"
    assert unauthorized["error_code"] == "UNAUTHORIZED"
    assert compiler.calls == []
    assert store.put_count == 0
