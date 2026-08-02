"""T01 error envelope and JSON-RPC protocol error contract."""

from __future__ import annotations

import json

from test_t01_shared_handlers import (
    WORKSPACE,
    build_service,
    call_arguments,
    fixture_auth,
    full_capabilities,
    jsonrpc_call,
)

from epistemic_foundry.application.mcp_common import (
    ERROR_CODES,
    handle_http_post,
    handle_jsonrpc,
)


def test_t01_error_contract_code_vocabulary_is_frozen() -> None:
    assert ERROR_CODES == (
        "INVALID_REQUEST",
        "UNKNOWN_TOOL",
        "INVALID_INPUT",
        "UNAUTHENTICATED",
        "WORKSPACE_DENIED",
        "UNAUTHORIZED",
        "NOT_FOUND",
        "IDEMPOTENCY_CONFLICT",
        "PLAN_COMPILATION_REJECTED",
        "INTERNAL",
    )


def test_t01_error_contract_every_error_envelope_is_schema_valid() -> None:
    service, read_port, _compiler, _store = build_service()
    read_port.records["read_claim"] = {"found": False, "state": "READY", "data": None}
    catalog = service.catalog

    cases = [
        ("foundry.nope", {"workspace_id": WORKSPACE}, fixture_auth(), "UNKNOWN_TOOL"),
        (
            "foundry.claim.get",
            {"workspace_id": WORKSPACE},
            fixture_auth(),
            "INVALID_INPUT",
        ),
        (
            "foundry.claim.get",
            call_arguments("foundry.claim.get"),
            fixture_auth(principal_id=None),
            "UNAUTHENTICATED",
        ),
        (
            "foundry.claim.get",
            {**call_arguments("foundry.claim.get"), "workspace_id": "WS-x"},
            fixture_auth(),
            "WORKSPACE_DENIED",
        ),
        (
            "foundry.claim.get",
            call_arguments("foundry.claim.get"),
            fixture_auth(capabilities=full_capabilities() - {"mcp.read.claim"}),
            "UNAUTHORIZED",
        ),
        (
            "foundry.claim.get",
            call_arguments("foundry.claim.get"),
            fixture_auth(),
            "NOT_FOUND",
        ),
    ]
    for tool, arguments, auth, expected in cases:
        envelope, is_error = service.call(tool, arguments, auth, request_id="R1")
        assert is_error
        assert envelope["error_code"] == expected
        catalog.validate_error_envelope(envelope)
        assert envelope["retryable"] is (expected == "INTERNAL")


def test_t01_error_contract_jsonrpc_protocol_errors_are_typed() -> None:
    service, _read_port, _compiler, _store = build_service()
    auth = fixture_auth()

    not_object = handle_jsonrpc(service, ["nope"], auth)
    bad_version = handle_jsonrpc(
        service, {"jsonrpc": "1.0", "id": 1, "method": "x"}, auth
    )
    unknown_method = handle_jsonrpc(
        service, {"jsonrpc": "2.0", "id": 2, "method": "resources/list"}, auth
    )
    missing_name = handle_jsonrpc(
        service, {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {}}, auth
    )
    notification = handle_jsonrpc(
        service, {"jsonrpc": "2.0", "method": "notifications/initialized"}, auth
    )

    assert not_object["error"]["code"] == -32600
    assert bad_version["error"]["code"] == -32600
    assert unknown_method["error"]["code"] == -32601
    assert missing_name["error"]["code"] == -32602
    assert notification is None


def test_t01_error_contract_http_transport_maps_protocol_failures() -> None:
    service, _read_port, _compiler, _store = build_service()
    auth = fixture_auth()

    wrong_path = handle_http_post(
        service,
        path="/rpc",
        body=b"{}",
        headers={"content-type": "application/json"},
        auth_provider=lambda _meta: auth,
    )
    wrong_type = handle_http_post(
        service,
        path="/mcp",
        body=b"{}",
        headers={"content-type": "text/plain"},
        auth_provider=lambda _meta: auth,
    )
    bad_json = handle_http_post(
        service,
        path="/mcp",
        body=b"{nope",
        headers={"content-type": "application/json"},
        auth_provider=lambda _meta: auth,
    )
    notification = handle_http_post(
        service,
        path="/mcp",
        body=json.dumps(
            {"jsonrpc": "2.0", "method": "notifications/initialized"}
        ).encode("utf-8"),
        headers={"content-type": "application/json"},
        auth_provider=lambda _meta: auth,
    )

    assert wrong_path[0] == 404
    assert wrong_type[0] == 415
    assert bad_json[0] == 400
    assert json.loads(bad_json[2])["error"]["code"] == -32700
    assert notification[0] == 202
    assert notification[2] == b""


def test_t01_error_contract_tool_errors_ride_inside_jsonrpc_results() -> None:
    service, _read_port, _compiler, _store = build_service()
    request = jsonrpc_call("foundry.claim.get", {"workspace_id": WORKSPACE}, "R-err")

    response = handle_jsonrpc(service, request, fixture_auth())

    assert "error" not in response
    assert response["result"]["isError"] is True
    envelope = response["result"]["structuredContent"]
    assert envelope["error_code"] == "INVALID_INPUT"
    service.catalog.validate_error_envelope(envelope)
