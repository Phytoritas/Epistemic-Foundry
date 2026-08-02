"""T01 planning tools: receipt-bound, idempotent, non-executing artifacts."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import pytest
from test_t01_shared_handlers import (
    ROOT,
    build_service,
    call_arguments,
    fixture_auth,
)

from epistemic_foundry.application.mcp_common.contracts import (
    canonical_json_bytes,
    sha256_id,
)
from epistemic_foundry.application.mcp_common import PlanRejected

PLANNING_TOOLS = (
    "foundry.frame.compile",
    "foundry.search.plan",
    "foundry.parliament.plan",
    "foundry.validation.plan",
)


class RejectingCompiler:
    def compile(
        self, operation: str, workspace_id: str, arguments: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        raise PlanRejected("falsifier is missing", {"missing": ["falsifier"]})


class NonCanonicalCompiler:
    def compile(
        self, operation: str, workspace_id: str, arguments: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        return {"not_a_plan": True}


def test_t01_planning_artifacts_all_four_tools_bind_receipts() -> None:
    service, _read_port, compiler, store = build_service()
    auth = fixture_auth()

    for tool in PLANNING_TOOLS:
        envelope, is_error = service.call(
            tool, call_arguments(tool), auth, request_id=f"R-{tool}"
        )
        assert not is_error, (tool, envelope)
        assert envelope["read_model_state"] == "READY"
        assert len(envelope["receipts"]) == 1
        receipt = envelope["receipts"][0]
        assert receipt["sha256"] == sha256_id(canonical_json_bytes(envelope["data"]))
        assert receipt["artifact_id"].startswith("PLAN-")
        assert receipt["receipt_id"].startswith("AR-")

    assert store.put_count == 4
    assert len(store.entries) == 4
    assert [operation for operation, _ in compiler.calls] == [
        service.catalog.tools[tool].handler_operation for tool in PLANNING_TOOLS
    ]


def test_t01_planning_artifacts_match_canonical_examples() -> None:
    service, _read_port, _compiler, _store = build_service()
    fixtures = json.loads(
        (ROOT / "tests" / "fixtures" / "t01_mcp" / "fixtures.json").read_text(
            encoding="utf-8"
        )
    )

    for tool, example in fixtures["planning_examples"].items():
        envelope, is_error = service.call(
            tool, call_arguments(tool), fixture_auth(), request_id="R1"
        )
        assert not is_error
        expected = json.loads((ROOT / example).read_text(encoding="utf-8"))
        assert envelope["data"] == expected


def test_t01_planning_artifacts_idempotent_replay_returns_same_receipt() -> None:
    service, _read_port, compiler, store = build_service()
    auth = fixture_auth()
    arguments = call_arguments("foundry.search.plan")

    first, _ = service.call("foundry.search.plan", arguments, auth, request_id="R1")
    second, _ = service.call("foundry.search.plan", arguments, auth, request_id="R1")

    assert first == second
    assert store.put_count == 2
    assert len(store.entries) == 1
    assert len(compiler.calls) == 2


def test_t01_planning_artifacts_key_reuse_with_new_request_conflicts() -> None:
    service, _read_port, _compiler, store = build_service()
    auth = fixture_auth()
    arguments = call_arguments("foundry.search.plan")

    first, is_error = service.call(
        "foundry.search.plan", arguments, auth, request_id="R1"
    )
    changed = {**arguments, "request": {"work_class": "E3"}}
    conflict, conflict_is_error = service.call(
        "foundry.search.plan", changed, auth, request_id="R2"
    )

    assert not is_error
    assert conflict_is_error
    assert conflict["error_code"] == "IDEMPOTENCY_CONFLICT"
    assert conflict["retryable"] is False
    assert len(store.entries) == 1


def test_t01_planning_artifacts_domain_rejection_is_typed() -> None:
    service, _read_port, _compiler, store = build_service(compiler=RejectingCompiler())

    envelope, is_error = service.call(
        "foundry.frame.compile",
        call_arguments("foundry.frame.compile"),
        fixture_auth(),
        request_id="R1",
    )

    assert is_error
    assert envelope["error_code"] == "PLAN_COMPILATION_REJECTED"
    assert envelope["details"] == {"missing": ["falsifier"]}
    assert store.put_count == 0


def test_t01_planning_artifacts_non_canonical_artifact_never_persists() -> None:
    service, _read_port, _compiler, store = build_service(
        compiler=NonCanonicalCompiler()
    )

    envelope, is_error = service.call(
        "foundry.validation.plan",
        call_arguments("foundry.validation.plan"),
        fixture_auth(),
        request_id="R1",
    )

    assert is_error
    assert envelope["error_code"] == "PLAN_COMPILATION_REJECTED"
    assert "validation-plan" in envelope["message"]
    assert envelope["details"]["schema_errors"]
    assert store.put_count == 0
    assert store.entries == {}


@pytest.mark.parametrize("tool", PLANNING_TOOLS)
def test_t01_planning_artifacts_do_not_execute_or_touch_read_models(tool: str) -> None:
    service, read_port, _compiler, _store = build_service()

    envelope, is_error = service.call(
        tool, call_arguments(tool), fixture_auth(), request_id="R1"
    )

    assert not is_error
    assert read_port.calls == []
