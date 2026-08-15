"""T01 read tools are side-effect free: no writes, receipts, or state drift."""

from __future__ import annotations

from test_t01_shared_handlers import (
    build_service,
    call_arguments,
    fixture_auth,
)


def read_tool_names(service) -> list[str]:
    return [
        name
        for name, spec in service.catalog.tools.items()
        if spec.side_effect_class == "PURE_READ"
    ]


def test_t01_read_side_effects_no_store_writes_and_no_provider_mutation() -> None:
    service, read_port, compiler, store = build_service()
    auth = fixture_auth()
    before = read_port.snapshot()

    for index, tool in enumerate(read_tool_names(service)):
        envelope, is_error = service.call(
            tool, call_arguments(tool), auth, request_id=f"R{index}"
        )
        assert not is_error, (tool, envelope)

    assert read_port.snapshot() == before
    assert store.put_count == 0
    assert store.entries == {}
    assert compiler.calls == []


def test_t01_read_side_effects_envelopes_carry_no_receipts() -> None:
    service, _read_port, _compiler, _store = build_service()
    auth = fixture_auth()

    for tool in read_tool_names(service):
        envelope, is_error = service.call(
            tool, call_arguments(tool), auth, request_id="R1"
        )
        assert not is_error
        assert envelope["receipts"] == []


def test_t01_read_side_effects_result_mutation_cannot_reach_the_provider() -> None:
    service, read_port, _compiler, _store = build_service()
    before = read_port.snapshot()

    envelope, _ = service.call(
        "foundry.status",
        call_arguments("foundry.status"),
        fixture_auth(),
        request_id="R1",
    )
    envelope["data"]["kernel_state"] = "TAMPERED"
    envelope["data"]["capability_labels"]["mcp_read_tools"] = "TAMPERED"

    fresh, _ = service.call(
        "foundry.status",
        call_arguments("foundry.status"),
        fixture_auth(),
        request_id="R2",
    )

    assert read_port.snapshot() == before
    assert fresh["data"]["kernel_state"] == "IDLE"


def test_t01_read_side_effects_failed_calls_also_leave_no_trace() -> None:
    service, read_port, compiler, store = build_service()
    read_port.records["read_claim"] = {
        "found": False,
        "state": "EMPTY_CONFIRMED",
        "data": None,
        "reason": None,
    }
    before = read_port.snapshot()

    for auth, request in (
        (fixture_auth(principal_id=None), call_arguments("foundry.claim.get")),
        (
            fixture_auth(),
            {**call_arguments("foundry.claim.get"), "workspace_id": "WS-x"},
        ),
        (fixture_auth(), call_arguments("foundry.claim.get")),
    ):
        envelope, is_error = service.call(
            "foundry.claim.get", request, auth, request_id="R1"
        )
        assert is_error

    assert read_port.snapshot() == before
    assert store.put_count == 0
    assert compiler.calls == []
