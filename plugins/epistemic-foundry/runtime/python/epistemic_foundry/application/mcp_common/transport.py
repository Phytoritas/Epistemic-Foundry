"""Stateless JSON-RPC framing shared by the STDIO and Streamable HTTP transports.

Both transports call the same :class:`ToolService`; the framing layer owns
only protocol validation, request/response shaping, and authentication
extraction.  No session state survives a request (frozen by
HD-EF4-T01-SG001-20260730-001): ``initialize`` echoes constants, and every
``tools/call`` carries its complete context.
"""

from __future__ import annotations

import json
import math
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

_OMIT_REQUEST_ID = object()


class _JsonNumberLexeme:
    """A JSON number retained until the top-level request ID is validated."""

    __slots__ = ("text",)

    def __init__(self, text: str) -> None:
        self.text = text


def _reject_non_json_number(value: str) -> None:
    raise ValueError(f"non-JSON numeric constant: {value}")


def _has_only_unicode_scalars(value: str) -> bool:
    return not any(0xD800 <= ord(character) <= 0xDFFF for character in value)


def _compare_unsigned_decimal(left: str, right: str) -> int:
    left = left.lstrip("0") or "0"
    right = right.lstrip("0") or "0"
    if len(left) != len(right):
        return 1 if len(left) > len(right) else -1
    return (left > right) - (left < right)


def _add_unsigned_decimal(left: str, right: str) -> str:
    carry = 0
    result: list[str] = []
    left_index = len(left) - 1
    right_index = len(right) - 1
    while left_index >= 0 or right_index >= 0 or carry:
        total = carry
        if left_index >= 0:
            total += ord(left[left_index]) - ord("0")
            left_index -= 1
        if right_index >= 0:
            total += ord(right[right_index]) - ord("0")
            right_index -= 1
        carry, digit = divmod(total, 10)
        result.append(str(digit))
    return "".join(reversed(result))


def _subtract_unsigned_decimal(left: str, right: str) -> str:
    """Return ``left - right`` for unsigned decimals where left >= right."""

    borrow = 0
    result: list[str] = []
    right_index = len(right) - 1
    for left_index in range(len(left) - 1, -1, -1):
        digit = ord(left[left_index]) - ord("0") - borrow
        if right_index >= 0:
            digit -= ord(right[right_index]) - ord("0")
            right_index -= 1
        if digit < 0:
            digit += 10
            borrow = 1
        else:
            borrow = 0
        result.append(str(digit))
    return "".join(reversed(result)).lstrip("0") or "0"


def _signed_decimal(value: str) -> tuple[int, str]:
    negative = value.startswith("-")
    if value[:1] in {"+", "-"}:
        value = value[1:]
    digits = value.lstrip("0") or "0"
    if digits == "0":
        return 0, digits
    return (-1 if negative else 1), digits


def _compare_signed_decimal(
    left: tuple[int, str], right: tuple[int, str]
) -> int:
    left_sign, left_digits = left
    right_sign, right_digits = right
    if left_sign != right_sign:
        return (left_sign > right_sign) - (left_sign < right_sign)
    if left_sign == 0:
        return 0
    magnitude = _compare_unsigned_decimal(left_digits, right_digits)
    return magnitude if left_sign > 0 else -magnitude


def _nonnegative_decimal_difference(
    left: tuple[int, str], right_value: int
) -> str | None:
    right = _signed_decimal(str(right_value))
    if _compare_signed_decimal(left, right) < 0:
        return None
    left_sign, left_digits = left
    right_sign, right_digits = right
    if left_sign >= 0:
        if right_sign >= 0:
            return _subtract_unsigned_decimal(left_digits, right_digits)
        return _add_unsigned_decimal(left_digits, right_digits)
    return _subtract_unsigned_decimal(right_digits, left_digits)


def _int_to_decimal(value: int) -> str:
    if value == 0:
        return "0"
    negative = value < 0
    remaining = -value if negative else value
    chunks: list[int] = []
    while remaining:
        remaining, chunk = divmod(remaining, 1_000_000_000)
        chunks.append(chunk)
    text = str(chunks.pop()) + "".join(f"{chunk:09d}" for chunk in reversed(chunks))
    return f"-{text}" if negative else text


def _canonical_integer_lexeme(value: str) -> str | None:
    negative = value.startswith("-")
    unsigned = value[1:] if negative else value
    exponent_index = max(unsigned.find("e"), unsigned.find("E"))
    if exponent_index >= 0:
        mantissa = unsigned[:exponent_index]
        exponent_text = unsigned[exponent_index + 1 :]
    else:
        mantissa = unsigned
        exponent_text = "0"
    if "." in mantissa:
        whole, fraction = mantissa.split(".", 1)
    else:
        whole, fraction = mantissa, ""

    coefficient = (whole + fraction).lstrip("0")
    if not coefficient:
        return "0"

    fraction_length = len(fraction)
    trailing_zeros = len(coefficient) - len(coefficient.rstrip("0"))
    canonical_exponent = _nonnegative_decimal_difference(
        _signed_decimal(exponent_text), fraction_length - trailing_zeros
    )
    if canonical_exponent is None:
        return None
    canonical = coefficient.rstrip("0")
    sign = "-" if negative else ""
    if canonical_exponent == "0":
        return f"{sign}{canonical}"
    plain_is_shorter_or_equal = _compare_unsigned_decimal(
        canonical_exponent, str(1 + len(canonical_exponent))
    ) <= 0
    if plain_is_shorter_or_equal:
        return f"{sign}{canonical}{'0' * int(canonical_exponent)}"
    return f"{sign}{canonical}e{canonical_exponent}"


def _materialize_json_numbers(value: Any) -> Any:
    if isinstance(value, _JsonNumberLexeme):
        if any(marker in value.text for marker in (".", "e", "E")):
            return float(value.text)
        return int(value.text)
    if isinstance(value, list):
        return [_materialize_json_numbers(item) for item in value]
    if isinstance(value, dict):
        return {key: _materialize_json_numbers(item) for key, item in value.items()}
    return value


def _decode_jsonrpc_request(value: str) -> Any:
    parsed = json.loads(
        value,
        parse_int=_JsonNumberLexeme,
        parse_float=_JsonNumberLexeme,
        parse_constant=_reject_non_json_number,
    )
    if isinstance(parsed, dict) and isinstance(parsed.get("id"), _JsonNumberLexeme):
        return {
            key: item if key == "id" else _materialize_json_numbers(item)
            for key, item in parsed.items()
        }
    return _materialize_json_numbers(parsed)


def _validated_request_id(value: Any) -> tuple[bool, str | None]:
    if type(value) is str:
        if not _has_only_unicode_scalars(value):
            return False, None
        return True, json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, _JsonNumberLexeme):
        canonical = _canonical_integer_lexeme(value.text)
        return canonical is not None, canonical
    if type(value) is int:
        return True, _canonical_integer_lexeme(_int_to_decimal(value))
    if type(value) is float and math.isfinite(value) and value.is_integer():
        return True, _canonical_integer_lexeme(_int_to_decimal(int(value)))
    return False, None


def _encode_jsonrpc_response(response: Mapping[str, Any]) -> str:
    fields: list[str] = []
    for key in sorted(response):
        value = response[key]
        if key == "id" and isinstance(value, _JsonNumberLexeme):
            encoded_value = value.text
        elif key == "id" and type(value) is int:
            encoded_value = _int_to_decimal(value)
        else:
            encoded_value = json.dumps(value, ensure_ascii=False, sort_keys=True)
        fields.append(f"{json.dumps(key)}: {encoded_value}")
    return "{" + ", ".join(fields) + "}"


def _jsonrpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    response = {
        "jsonrpc": JSONRPC_VERSION,
        "error": {"code": code, "message": message},
    }
    if request_id is not _OMIT_REQUEST_ID:
        response["id"] = request_id
    return response


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
            _OMIT_REQUEST_ID, JSONRPC_INVALID_REQUEST, "request must be an object"
        )
    has_request_id = "id" in request
    request_id = request.get("id") if has_request_id else _OMIT_REQUEST_ID
    if has_request_id:
        request_id_is_valid, correlation_id = _validated_request_id(request_id)
        if not request_id_is_valid:
            return _jsonrpc_error(
                _OMIT_REQUEST_ID,
                JSONRPC_INVALID_REQUEST,
                "request is not a JSON-RPC 2.0 call",
            )
    else:
        correlation_id = None
    if (
        request.get("jsonrpc") != JSONRPC_VERSION
        or not isinstance(request.get("method"), str)
    ):
        return _jsonrpc_error(
            request_id,
            JSONRPC_INVALID_REQUEST,
            "request is not a JSON-RPC 2.0 call",
        )
    if not has_request_id:
        if "params" in request and not isinstance(
            request["params"], (Mapping, list)
        ):
            return _jsonrpc_error(
                _OMIT_REQUEST_ID,
                JSONRPC_INVALID_REQUEST,
                "request params must be an object or array",
            )
        # Structurally valid notifications receive no response or correlation.
        return None
    method = str(request["method"])
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
            request_id=correlation_id,
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
            request = _decode_jsonrpc_request(line)
        except (json.JSONDecodeError, ValueError):
            response: dict[str, Any] | None = _jsonrpc_error(
                _OMIT_REQUEST_ID,
                JSONRPC_PARSE_ERROR,
                "request line is not valid JSON",
            )
        else:
            response = handle_jsonrpc(
                service, request, auth_provider({"transport": "stdio"})
            )
        if response is not None:
            stdout.write(_encode_jsonrpc_response(response) + "\n")
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
        request = _decode_jsonrpc_request(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        payload = _jsonrpc_error(
            _OMIT_REQUEST_ID, JSONRPC_PARSE_ERROR, "body is not valid JSON"
        )
        return (
            400,
            response_headers,
            _encode_jsonrpc_response(payload).encode("utf-8"),
        )
    response = handle_jsonrpc(
        service, request, auth_provider({"transport": "http", "headers": dict(headers)})
    )
    if response is None:
        return 202, response_headers, b""
    return (
        200,
        response_headers,
        _encode_jsonrpc_response(response).encode("utf-8"),
    )
