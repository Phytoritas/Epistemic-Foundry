"""Stateless JSON-RPC framing shared by the STDIO and Streamable HTTP transports.

Both transports call the same :class:`ToolService`; the framing layer owns
only protocol validation, request/response shaping, and authentication
extraction.  No session state survives a request (frozen by
HD-EF4-T01-SG001-20260730-001): ``initialize`` echoes constants, and every
``tools/call`` carries its complete context.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any, TextIO

from .contracts import PROTOCOL_VERSION, AuthContext, ToolCatalog, ToolService

JSONRPC_VERSION = "2.0"
HTTP_MCP_PATH = "/mcp"
JSONRPC_PARSE_ERROR = -32700
JSONRPC_INVALID_REQUEST = -32600
JSONRPC_METHOD_NOT_FOUND = -32601
JSONRPC_INVALID_PARAMS = -32602

AuthProvider = Callable[[Mapping[str, Any]], AuthContext]


def _jsonrpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": JSONRPC_VERSION,
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def _initialize_result() -> dict[str, Any]:
    return {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {"name": "epistemic-foundry", "title": "Epistemic Foundry"},
        "instructions": (
            "Stateless T01 surface: nine PURE_READ tools and four "
            "DURABLE_PLAN_ARTIFACT tools; no execution-capable tool is exposed."
        ),
    }


def tool_descriptors(catalog: ToolCatalog) -> list[dict[str, Any]]:
    """Descriptor projection derived from the canonical catalog only."""

    return [
        {
            "name": spec.name,
            "title": spec.title,
            "inputSchema": catalog.input_schema(spec.name),
            "annotations": {
                "sideEffectClass": spec.side_effect_class,
                "capability": spec.capability,
                "dataSchemaRefs": list(spec.data_schema_refs),
                "readOnlyHint": spec.side_effect_class == "PURE_READ",
            },
        }
        for spec in catalog.tools.values()
    ]


def handle_jsonrpc(
    service: ToolService,
    request: Any,
    auth: AuthContext,
) -> dict[str, Any] | None:
    """Handle one JSON-RPC request object; returns the response object."""

    if not isinstance(request, Mapping):
        return _jsonrpc_error(
            None, JSONRPC_INVALID_REQUEST, "request must be an object"
        )
    request_id = request.get("id")
    if (
        request.get("jsonrpc") != JSONRPC_VERSION
        or not isinstance(request.get("method"), str)
        or isinstance(request_id, (list, dict, bool))
    ):
        return _jsonrpc_error(
            request_id if isinstance(request_id, (str, int, float)) else None,
            JSONRPC_INVALID_REQUEST,
            "request is not a JSON-RPC 2.0 call",
        )
    method = str(request["method"])
    if request_id is None:
        # Notifications receive no response; the stateless surface keeps none.
        return None
    if method == "initialize":
        return {
            "jsonrpc": JSONRPC_VERSION,
            "id": request_id,
            "result": _initialize_result(),
        }
    if method == "tools/list":
        return {
            "jsonrpc": JSONRPC_VERSION,
            "id": request_id,
            "result": {"tools": tool_descriptors(service.catalog)},
        }
    if method == "tools/call":
        params = request.get("params")
        if not isinstance(params, Mapping) or not isinstance(params.get("name"), str):
            return _jsonrpc_error(
                request_id, JSONRPC_INVALID_PARAMS, "params.name is required"
            )
        arguments = params.get("arguments", {})
        envelope, is_error = service.call(
            str(params["name"]),
            arguments,
            auth,
            request_id=str(request_id),
        )
        return {
            "jsonrpc": JSONRPC_VERSION,
            "id": request_id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            envelope, ensure_ascii=False, sort_keys=True
                        ),
                    }
                ],
                "structuredContent": envelope,
                "isError": is_error,
            },
        }
    return _jsonrpc_error(
        request_id, JSONRPC_METHOD_NOT_FOUND, f"unknown method: {method}"
    )


def serve_stdio(
    service: ToolService,
    stdin: TextIO,
    stdout: TextIO,
    auth_provider: AuthProvider,
) -> int:
    """Line-delimited stateless STDIO loop; one JSON-RPC message per line."""

    handled = 0
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            response: dict[str, Any] | None = _jsonrpc_error(
                None, JSONRPC_PARSE_ERROR, "request line is not valid JSON"
            )
        else:
            response = handle_jsonrpc(
                service, request, auth_provider({"transport": "stdio"})
            )
        if response is not None:
            stdout.write(
                json.dumps(response, ensure_ascii=False, sort_keys=True) + "\n"
            )
            stdout.flush()
            handled += 1
    return handled


def handle_http_post(
    service: ToolService,
    *,
    path: str,
    body: bytes,
    headers: Mapping[str, str],
    auth_provider: AuthProvider,
) -> tuple[int, dict[str, str], bytes]:
    """One stateless Streamable HTTP POST /mcp exchange; no SSE fallback."""

    response_headers = {"content-type": "application/json"}
    if path != HTTP_MCP_PATH:
        return 404, response_headers, b'{"error":"unknown path"}'
    content_type = headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type != "application/json":
        return (
            415,
            response_headers,
            b'{"error":"content-type must be application/json"}',
        )
    try:
        request = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = _jsonrpc_error(None, JSONRPC_PARSE_ERROR, "body is not valid JSON")
        return (
            400,
            response_headers,
            json.dumps(payload, sort_keys=True).encode("utf-8"),
        )
    response = handle_jsonrpc(
        service, request, auth_provider({"transport": "http", "headers": dict(headers)})
    )
    if response is None:
        return 202, response_headers, b""
    return (
        200,
        response_headers,
        json.dumps(response, ensure_ascii=False, sort_keys=True).encode("utf-8"),
    )
