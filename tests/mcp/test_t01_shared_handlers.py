"""T01 shared-handler contract: one handler set behind every transport."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from io import StringIO
from pathlib import Path
from typing import Any

import pytest

from epistemic_foundry.application.mcp_common import (
    PROTOCOL_VERSION,
    AuthContext,
    IdempotencyConflict,
    ReadOutcome,
    StoredPlanArtifact,
    ToolService,
    handle_http_post,
    handle_jsonrpc,
    load_catalog,
    serve_stdio,
)
from epistemic_foundry.application.mcp_common.contracts import (
    canonical_json_bytes,
    sha256_id,
)
from epistemic_foundry.application.mcp_planning import build_planning_registry
from epistemic_foundry.application.mcp_read import build_read_registry

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = json.loads(
    (ROOT / "tests" / "fixtures" / "t01_mcp" / "fixtures.json").read_text(
        encoding="utf-8"
    )
)
FIXED_NOW = "2026-07-31T00:00:00Z"
WORKSPACE = FIXTURES["auth"]["workspace_id"]


class FixtureReadModelPort:
    """Deterministic read-model provider with a mutation-detection snapshot."""

    def __init__(self, records: Mapping[str, Any] | None = None) -> None:
        self.records = copy.deepcopy(
            dict(records if records is not None else FIXTURES["read_records"])
        )
        self.calls: list[tuple[str, str]] = []

    def snapshot(self) -> dict[str, Any]:
        return copy.deepcopy(self.records)

    def fetch(
        self, operation: str, workspace_id: str, arguments: Mapping[str, Any]
    ) -> ReadOutcome:
        self.calls.append((operation, workspace_id))
        record = self.records.get(operation)
        if record is None:
            return ReadOutcome(found=False, state="READY", data=None)
        if record.get("raise"):
            raise RuntimeError(str(record["raise"]))
        return ReadOutcome(
            found=bool(record.get("found", True)),
            state=str(record["state"]),
            data=copy.deepcopy(record.get("data")),
            reason=record.get("reason"),
        )


class FixturePlanCompiler:
    """Returns canonical repository examples; records every invocation."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        catalog = load_catalog(ROOT)
        self._by_operation = {
            catalog.tools[name].handler_operation: ROOT / relative
            for name, relative in FIXTURES["planning_examples"].items()
        }

    def compile(
        self, operation: str, workspace_id: str, arguments: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        self.calls.append((operation, workspace_id))
        return json.loads(self._by_operation[operation].read_text(encoding="utf-8"))


class InMemoryPlanArtifactStore:
    """Append-only idempotent store; every put is observable."""

    def __init__(self) -> None:
        self.entries: dict[tuple[str, str], dict[str, Any]] = {}
        self.put_count = 0

    def put(
        self,
        *,
        workspace_id: str,
        kind: str,
        content: bytes,
        idempotency_key: str,
        request_fingerprint: str,
    ) -> StoredPlanArtifact:
        self.put_count += 1
        key = (workspace_id, idempotency_key)
        digest = sha256_id(content)
        existing = self.entries.get(key)
        if existing is not None:
            if existing["request_fingerprint"] != request_fingerprint:
                raise IdempotencyConflict(idempotency_key)
            return StoredPlanArtifact(
                artifact_id=existing["artifact_id"],
                receipt_id=existing["receipt_id"],
                sha256=existing["sha256"],
                created=False,
            )
        entry = {
            "artifact_id": f"PLAN-{digest[7:23]}",
            "receipt_id": f"AR-{digest[7:23]}",
            "sha256": digest,
            "kind": kind,
            "request_fingerprint": request_fingerprint,
        }
        self.entries[key] = entry
        return StoredPlanArtifact(
            artifact_id=entry["artifact_id"],
            receipt_id=entry["receipt_id"],
            sha256=entry["sha256"],
            created=True,
        )


def full_capabilities() -> frozenset[str]:
    catalog = load_catalog(ROOT)
    return frozenset(spec.capability for spec in catalog.tools.values())


def fixture_auth(**overrides: Any) -> AuthContext:
    values: dict[str, Any] = {
        "principal_id": FIXTURES["auth"]["principal_id"],
        "workspace_id": WORKSPACE,
        "capabilities": full_capabilities(),
    }
    values.update(overrides)
    return AuthContext(**values)


def build_service(
    *,
    read_port: FixtureReadModelPort | None = None,
    compiler: FixturePlanCompiler | None = None,
    store: InMemoryPlanArtifactStore | None = None,
) -> tuple[
    ToolService, FixtureReadModelPort, FixturePlanCompiler, InMemoryPlanArtifactStore
]:
    catalog = load_catalog(ROOT)
    read_port = read_port if read_port is not None else FixtureReadModelPort()
    compiler = compiler if compiler is not None else FixturePlanCompiler()
    store = store if store is not None else InMemoryPlanArtifactStore()
    handlers: dict[str, Any] = {}
    handlers.update(build_read_registry(catalog, read_port))
    handlers.update(build_planning_registry(catalog, compiler, store))
    service = ToolService(catalog, handlers, clock=lambda: FIXED_NOW)
    return service, read_port, compiler, store


def call_arguments(tool: str) -> dict[str, Any]:
    base: dict[str, Any] = {"workspace_id": WORKSPACE}
    extra: dict[str, dict[str, Any]] = {
        "foundry.session.get": {"session_id": "FS-0001"},
        "foundry.artifact.get": {"artifact_id": "ART-0001"},
        "foundry.claim.get": {"claim_id": "CLM-0001"},
        "foundry.atlas.query": {"subject_id": "INS-1", "view": "coverage"},
        "foundry.passport.get": {"passport_id": "HP-0001"},
        "foundry.replay.diff": {"run_id": "RUN-2", "baseline_run_id": "RUN-1"},
        "foundry.frame.compile": {
            "insight_id": "INS-1",
            "idempotency_key": "IDEM-frame-1",
            "proposal": {"statement": "bounded relation"},
        },
        "foundry.search.plan": {
            "insight_id": "INS-1",
            "idempotency_key": "IDEM-search-1",
            "request": {"work_class": "E2"},
        },
        "foundry.parliament.plan": {
            "subject_id": "INS-1",
            "idempotency_key": "IDEM-parliament-1",
            "request": {"stage": "deliberation"},
        },
        "foundry.validation.plan": {
            "target_id": "VT-1",
            "idempotency_key": "IDEM-validation-1",
            "request": {"stage": "S3"},
        },
    }
    return {**base, **extra.get(tool, {})}


def jsonrpc_call(
    tool: str, arguments: Mapping[str, Any], request_id: str
) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {"name": tool, "arguments": dict(arguments)},
    }


def test_t01_shared_handlers_catalog_is_exactly_thirteen() -> None:
    catalog = load_catalog(ROOT)
    reads = [s for s in catalog.tools.values() if s.side_effect_class == "PURE_READ"]
    plans = [
        s
        for s in catalog.tools.values()
        if s.side_effect_class == "DURABLE_PLAN_ARTIFACT"
    ]

    assert len(catalog.tool_names) == 13
    assert len(reads) == 9
    assert len(plans) == 4
    assert len(set(catalog.tool_names)) == 13


def test_t01_shared_handlers_read_states_are_honest() -> None:
    service, _read_port, _compiler, _store = build_service()
    auth = fixture_auth()

    ready, is_error = service.call(
        "foundry.status", call_arguments("foundry.status"), auth, request_id="R1"
    )
    degraded, _ = service.call(
        "foundry.health", call_arguments("foundry.health"), auth, request_id="R2"
    )
    empty, _ = service.call(
        "foundry.atlas.query",
        call_arguments("foundry.atlas.query"),
        auth,
        request_id="R3",
    )

    assert not is_error
    assert ready["read_model_state"] == "READY"
    assert ready["data"]["kernel_state"] == "IDLE"
    assert degraded["read_model_state"] == "DEGRADED"
    assert degraded["degradation_reason"] == "postgres_store probe failed"
    assert empty["read_model_state"] == "EMPTY_CONFIRMED"
    assert empty["data"] is None
    assert empty["degradation_reason"] is None


def test_t01_shared_handlers_provider_failure_is_unavailable_never_empty() -> None:
    read_port = FixtureReadModelPort()
    read_port.records["read_status"] = {"raise": "backend down"}
    service, _read_port, _compiler, _store = build_service(read_port=read_port)

    envelope, is_error = service.call(
        "foundry.status",
        call_arguments("foundry.status"),
        fixture_auth(),
        request_id="R1",
    )

    assert not is_error
    assert envelope["read_model_state"] == "UNAVAILABLE"
    assert envelope["read_model_state"] != "EMPTY_CONFIRMED"
    assert envelope["data"] is None
    assert "RuntimeError" in envelope["degradation_reason"]


@pytest.mark.parametrize(
    ("record", "expected_message"),
    [
        (
            {"found": True, "state": "READY", "data": None},
            "READY requires a data payload",
        ),
        (
            {"found": True, "state": "EMPTY_CONFIRMED", "data": {"x": 1}},
            "EMPTY_CONFIRMED cannot carry a data payload",
        ),
        (
            {"found": True, "state": "EMPTY_CONFIRMED", "data": None, "reason": "late"},
            "EMPTY_CONFIRMED cannot carry a degradation reason",
        ),
    ],
)
def test_t01_shared_handlers_dishonest_provider_states_fail_closed(
    record: dict[str, Any], expected_message: str
) -> None:
    read_port = FixtureReadModelPort()
    read_port.records["read_status"] = record
    service, _read_port, _compiler, _store = build_service(read_port=read_port)

    envelope, is_error = service.call(
        "foundry.status",
        call_arguments("foundry.status"),
        fixture_auth(),
        request_id="R1",
    )

    assert is_error
    assert envelope["error_code"] == "INTERNAL"
    assert expected_message in envelope["message"]


def test_t01_shared_handlers_stdio_and_http_share_exact_envelopes() -> None:
    service, _read_port, _compiler, _store = build_service()
    auth = fixture_auth()
    request = jsonrpc_call("foundry.status", call_arguments("foundry.status"), "R-1")

    stdin = StringIO(json.dumps(request) + "\n")
    stdout = StringIO()
    handled = serve_stdio(service, stdin, stdout, lambda _meta: auth)
    stdio_response = json.loads(stdout.getvalue().strip())

    status, headers, body = handle_http_post(
        service,
        path="/mcp",
        body=json.dumps(request).encode("utf-8"),
        headers={"content-type": "application/json"},
        auth_provider=lambda _meta: auth,
    )
    http_response = json.loads(body.decode("utf-8"))

    assert handled == 1
    assert status == 200
    assert headers["content-type"] == "application/json"
    assert stdio_response == http_response
    assert (
        stdio_response["result"]["structuredContent"]["protocol_version"]
        == PROTOCOL_VERSION
    )
    assert stdio_response["result"]["isError"] is False


def test_t01_shared_handlers_initialize_and_tools_list_are_stateless_constants() -> (
    None
):
    service, _read_port, _compiler, _store = build_service()
    auth = fixture_auth()

    first = handle_jsonrpc(
        service, {"jsonrpc": "2.0", "id": 1, "method": "initialize"}, auth
    )
    listed = handle_jsonrpc(
        service, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, auth
    )
    second = handle_jsonrpc(
        service, {"jsonrpc": "2.0", "id": 1, "method": "initialize"}, auth
    )

    assert first == second
    assert first["result"]["protocolVersion"] == PROTOCOL_VERSION
    tools = listed["result"]["tools"]
    assert [row["name"] for row in tools] == list(load_catalog(ROOT).tool_names)
    assert all(
        row["annotations"]["readOnlyHint"]
        == (row["annotations"]["sideEffectClass"] == "PURE_READ")
        for row in tools
    )


def test_t01_shared_handlers_repeated_calls_are_stateless_and_identical() -> None:
    service, read_port, _compiler, _store = build_service()
    auth = fixture_auth()
    arguments = call_arguments("foundry.claim.get")

    first, _ = service.call("foundry.claim.get", arguments, auth, request_id="R1")
    second, _ = service.call("foundry.claim.get", arguments, auth, request_id="R1")

    assert first == second
    assert read_port.calls == [("read_claim", WORKSPACE), ("read_claim", WORKSPACE)]
    assert canonical_json_bytes(first) == canonical_json_bytes(second)


def test_t01_shared_handlers_every_tool_produces_a_schema_valid_envelope() -> None:
    service, _read_port, _compiler, _store = build_service()
    catalog = service.catalog
    auth = fixture_auth()

    for tool in catalog.tool_names:
        envelope, is_error = service.call(
            tool, call_arguments(tool), auth, request_id=f"R-{tool}"
        )
        assert not is_error, (tool, envelope)
        catalog.validate_result_envelope(envelope)
        assert envelope["tool"] == tool
        assert envelope["workspace_id"] == WORKSPACE
        assert envelope["generated_at"] == FIXED_NOW


def test_t01_shared_handlers_generated_descriptors_match_the_catalog() -> None:
    from epistemic_foundry.application.mcp_common.transport import tool_descriptors

    generated = json.loads(
        (
            ROOT
            / "packages"
            / "plugin-host"
            / "src"
            / "mcp"
            / "generated"
            / "tool-descriptors.json"
        ).read_text(encoding="utf-8")
    )
    catalog = load_catalog(ROOT)
    expected = {
        "generated_from": "contracts/mcp/t01/tool-catalog.yaml",
        "protocol_version": PROTOCOL_VERSION,
        "tools": tool_descriptors(catalog),
    }

    assert generated == expected
