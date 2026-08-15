// Stateless plugin-host MCP framing for the T01 read/planning surface.
//
// The adapter owns JSON-RPC shaping only.  Tool semantics live behind the
// injected handler port (the provider-neutral Python application layer); the
// descriptor table is the generated projection of the canonical catalog at
// contracts/mcp/t01/tool-catalog.yaml.  No session state survives a request
// and no SSE fallback exists (HD-EF4-T01-SG001-20260730-001).

import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const descriptorDocument = require("../generated/tool-descriptors.json");

export const JSONRPC_VERSION = "2.0";
export const PROTOCOL_VERSION = descriptorDocument.protocol_version;
export const HTTP_MCP_PATH = "/mcp";
export const JSONRPC_PARSE_ERROR = -32700;
export const JSONRPC_INVALID_REQUEST = -32600;
export const JSONRPC_METHOD_NOT_FOUND = -32601;
export const JSONRPC_INVALID_PARAMS = -32602;

const NUMERIC_ID_SOURCE = Symbol("epistemic-foundry.numeric-id-source");
const JSON_NUMBER_PATTERN =
  /^(-?)(0|[1-9]\d*)(?:\.(\d+))?(?:[eE]([+-]?)(\d+))?$/;

export function toolDescriptors() {
  return structuredClone(descriptorDocument.tools);
}

function attachNumericIdSource(value, source, requestId) {
  Object.defineProperty(value, NUMERIC_ID_SOURCE, {
    value: Object.freeze({ source, value: requestId }),
    enumerable: true,
  });
  return value;
}

function numericIdSource(value, requestId) {
  const metadata = value?.[NUMERIC_ID_SOURCE];
  return metadata !== undefined && Object.is(metadata.value, requestId)
    ? metadata.source
    : undefined;
}

/** Parse JSON while retaining the exact top-level numeric `id` token. */
export function parseJsonrpcMessage(text) {
  const numericIds = new WeakMap();
  const parsed = JSON.parse(text, function retainNumericId(key, value, context) {
    if (key === "id" && typeof value === "number") {
      if (typeof context?.source !== "string") {
        throw new TypeError("JSON.parse reviver context.source is required");
      }
      numericIds.set(this, { source: context.source, value });
    }
    return value;
  });
  if (typeof parsed === "object" && parsed !== null) {
    const metadata = numericIds.get(parsed);
    if (metadata !== undefined) {
      attachNumericIdSource(parsed, metadata.source, metadata.value);
    }
  }
  return parsed;
}

/** Serialize a response while emitting an exact retained numeric `id` token. */
export function stringifyJsonrpcMessage(value) {
  const metadata = value?.[NUMERIC_ID_SOURCE];
  if (metadata === undefined || !Object.is(value.id, metadata.value)) {
    return JSON.stringify(value);
  }
  if (typeof JSON.rawJSON !== "function") {
    throw new TypeError("JSON.rawJSON is required");
  }
  return JSON.stringify(value, function emitNumericId(key, current) {
    return key === "id" && this === value
      ? JSON.rawJSON(metadata.source)
      : current;
  });
}

function jsonrpcError(requestId, code, message, source) {
  const response = { jsonrpc: JSONRPC_VERSION };
  if (requestId !== undefined) response.id = requestId;
  response.error = { code, message };
  return source === undefined
    ? response
    : attachNumericIdSource(response, source, requestId);
}

function jsonrpcResult(requestId, result, source) {
  const response = { jsonrpc: JSONRPC_VERSION, id: requestId, result };
  return source === undefined
    ? response
    : attachNumericIdSource(response, source, requestId);
}

function initializeResult() {
  return {
    protocolVersion: PROTOCOL_VERSION,
    capabilities: { tools: { listChanged: false } },
    serverInfo: { name: "epistemic-foundry", title: "Epistemic Foundry" },
    instructions:
      "Stateless T01 surface: nine PURE_READ tools and four " +
      "DURABLE_PLAN_ARTIFACT tools; no execution-capable tool is exposed.",
  };
}

function isPlainObject(value) {
  return (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value) &&
    Object.getPrototypeOf(value) === Object.prototype
  );
}

function hasOnlyUnicodeScalars(value) {
  for (let index = 0; index < value.length; index += 1) {
    const code = value.charCodeAt(index);
    if (code >= 0xd800 && code <= 0xdbff) {
      if (index + 1 >= value.length) return false;
      const next = value.charCodeAt(index + 1);
      if (next < 0xdc00 || next > 0xdfff) return false;
      index += 1;
    } else if (code >= 0xdc00 && code <= 0xdfff) {
      return false;
    }
  }
  return true;
}

function trimUnsignedDecimal(value) {
  let index = 0;
  while (index < value.length - 1 && value.charCodeAt(index) === 0x30) {
    index += 1;
  }
  return value.slice(index);
}

function compareUnsignedDecimals(left, right) {
  if (left.length !== right.length) return left.length < right.length ? -1 : 1;
  if (left === right) return 0;
  return left < right ? -1 : 1;
}

function addUnsignedDecimals(left, right) {
  let leftIndex = left.length - 1;
  let rightIndex = right.length - 1;
  let carry = 0;
  const result = [];
  while (leftIndex >= 0 || rightIndex >= 0 || carry !== 0) {
    const leftDigit = leftIndex >= 0 ? left.charCodeAt(leftIndex) - 0x30 : 0;
    const rightDigit = rightIndex >= 0 ? right.charCodeAt(rightIndex) - 0x30 : 0;
    const sum = leftDigit + rightDigit + carry;
    result.push(String(sum % 10));
    carry = Math.floor(sum / 10);
    leftIndex -= 1;
    rightIndex -= 1;
  }
  return result.reverse().join("");
}

function subtractUnsignedDecimals(left, right) {
  let leftIndex = left.length - 1;
  let rightIndex = right.length - 1;
  let borrow = 0;
  const result = [];
  while (leftIndex >= 0) {
    let digit = left.charCodeAt(leftIndex) - 0x30 - borrow;
    const subtrahend =
      rightIndex >= 0 ? right.charCodeAt(rightIndex) - 0x30 : 0;
    if (digit < subtrahend) {
      digit += 10;
      borrow = 1;
    } else {
      borrow = 0;
    }
    result.push(String(digit - subtrahend));
    leftIndex -= 1;
    rightIndex -= 1;
  }
  return trimUnsignedDecimal(result.reverse().join(""));
}

function normalizeJsonIntegerSource(source) {
  const match = JSON_NUMBER_PATTERN.exec(source);
  if (match === null) return null;

  const [, sign, integerDigits, fractionDigits = "", exponentSign = "", rawExponent = "0"] =
    match;
  const coefficient = trimUnsignedDecimal(`${integerDigits}${fractionDigits}`);
  if (coefficient === "0") return "0";

  const exponent = trimUnsignedDecimal(rawExponent);
  const fractionLength = String(fractionDigits.length);
  let powerIsNegative;
  let powerMagnitude;
  if (exponentSign === "-" && exponent !== "0") {
    powerIsNegative = true;
    powerMagnitude = addUnsignedDecimals(exponent, fractionLength);
  } else if (compareUnsignedDecimals(exponent, fractionLength) >= 0) {
    powerIsNegative = false;
    powerMagnitude = subtractUnsignedDecimals(exponent, fractionLength);
  } else {
    powerIsNegative = true;
    powerMagnitude = subtractUnsignedDecimals(fractionLength, exponent);
  }

  let significantEnd = coefficient.length;
  while (
    significantEnd > 0 &&
    coefficient.charCodeAt(significantEnd - 1) === 0x30
  ) {
    significantEnd -= 1;
  }
  const trailingZeroCount = coefficient.length - significantEnd;
  let exactTrailingZeros;
  if (powerIsNegative) {
    if (
      compareUnsignedDecimals(powerMagnitude, String(trailingZeroCount)) > 0
    ) {
      return null;
    }
    exactTrailingZeros = String(trailingZeroCount - Number(powerMagnitude));
  } else {
    exactTrailingZeros = addUnsignedDecimals(
      String(trailingZeroCount),
      powerMagnitude,
    );
  }

  const prefix = sign === "-" ? "-" : "";
  const significant = coefficient.slice(0, significantEnd);
  if (exactTrailingZeros === "0") return `${prefix}${significant}`;

  const exponentOverhead = String(exactTrailingZeros.length + 1);
  if (compareUnsignedDecimals(exactTrailingZeros, exponentOverhead) > 0) {
    return `${prefix}${significant}e${exactTrailingZeros}`;
  }
  return `${prefix}${significant}${"0".repeat(Number(exactTrailingZeros))}`;
}

function classifyRequestId(request) {
  if (!Object.hasOwn(request, "id")) return { kind: "absent" };
  const value = request.id;
  if (typeof value === "string") {
    return hasOnlyUnicodeScalars(value)
      ? { kind: "valid", value, correlation: JSON.stringify(value) }
      : { kind: "invalid" };
  }
  if (typeof value !== "number") return { kind: "invalid" };

  const source = numericIdSource(request, value);
  if (source !== undefined) {
    const correlation = normalizeJsonIntegerSource(source);
    return correlation === null
      ? { kind: "invalid" }
      : { kind: "valid", value, correlation, source };
  }
  if (!Number.isSafeInteger(value)) return { kind: "invalid" };
  return {
    kind: "valid",
    value,
    correlation: normalizeJsonIntegerSource(JSON.stringify(value)),
  };
}

/**
 * Handle one JSON-RPC request against the injected handler port.
 *
 * The handler port mirrors the shared Python ToolService:
 * `call(toolName, argumentsObject, requestId)` returning
 * `{ envelope, isError }`. Notifications are not dispatched.
 */
export async function handleJsonrpc(request, handlerPort) {
  if (!isPlainObject(request)) {
    return jsonrpcError(undefined, JSONRPC_INVALID_REQUEST, "request must be an object");
  }
  const requestId = classifyRequestId(request);
  if (
    request.jsonrpc !== JSONRPC_VERSION ||
    typeof request.method !== "string" ||
    requestId.kind === "invalid"
  ) {
    const reportable = requestId.kind === "valid" ? requestId.value : undefined;
    return jsonrpcError(
      reportable,
      JSONRPC_INVALID_REQUEST,
      "request is not a JSON-RPC 2.0 call",
      requestId.kind === "valid" ? requestId.source : undefined,
    );
  }
  if (requestId.kind === "absent") {
    if (
      Object.hasOwn(request, "params") &&
      !isPlainObject(request.params) &&
      !Array.isArray(request.params)
    ) {
      return jsonrpcError(
        undefined,
        JSONRPC_INVALID_REQUEST,
        "request params must be an object or array",
      );
    }
    return null;
  }
  if (request.method === "initialize") {
    return jsonrpcResult(requestId.value, initializeResult(), requestId.source);
  }
  if (request.method === "tools/list") {
    return jsonrpcResult(
      requestId.value,
      { tools: toolDescriptors() },
      requestId.source,
    );
  }
  if (request.method === "tools/call") {
    const params = request.params;
    if (!isPlainObject(params) || typeof params.name !== "string") {
      return jsonrpcError(
        requestId.value,
        JSONRPC_INVALID_PARAMS,
        "params.name is required",
        requestId.source,
      );
    }
    const args = Object.hasOwn(params, "arguments") ? params.arguments : {};
    const { envelope, isError } = await handlerPort.call(
      params.name,
      args,
      requestId.correlation,
    );
    return jsonrpcResult(
      requestId.value,
      {
        content: [{ type: "text", text: JSON.stringify(envelope) }],
        structuredContent: envelope,
        isError: Boolean(isError),
      },
      requestId.source,
    );
  }
  return jsonrpcError(
    requestId.value,
    JSONRPC_METHOD_NOT_FOUND,
    `unknown method: ${request.method}`,
    requestId.source,
  );
}

/** One stateless Streamable HTTP POST /mcp exchange; no SSE fallback. */
export async function handleHttpPost({ path, body, headers, handlerPort }) {
  const responseHeaders = { "content-type": "application/json" };
  if (path !== HTTP_MCP_PATH) {
    return { status: 404, headers: responseHeaders, body: '{"error":"unknown path"}' };
  }
  const contentType = String(headers?.["content-type"] ?? "")
    .split(";")[0]
    .trim()
    .toLowerCase();
  if (contentType !== "application/json") {
    return {
      status: 415,
      headers: responseHeaders,
      body: '{"error":"content-type must be application/json"}',
    };
  }
  let request;
  try {
    request = parseJsonrpcMessage(body);
  } catch {
    return {
      status: 400,
      headers: responseHeaders,
      body: stringifyJsonrpcMessage(
        jsonrpcError(undefined, JSONRPC_PARSE_ERROR, "body is not valid JSON"),
      ),
    };
  }
  const response = await handleJsonrpc(request, handlerPort);
  if (response === null) {
    return { status: 202, headers: responseHeaders, body: "" };
  }
  return {
    status: 200,
    headers: responseHeaders,
    body: stringifyJsonrpcMessage(response),
  };
}

/** Line-delimited stateless STDIO loop over async line iterables. */
export async function serveStdio(lines, write, handlerPort) {
  let handled = 0;
  for await (const rawLine of lines) {
    const line = String(rawLine).trim();
    if (line === "") {
      continue;
    }
    let response;
    try {
      response = await handleJsonrpc(parseJsonrpcMessage(line), handlerPort);
    } catch (error) {
      response =
        error instanceof SyntaxError
          ? jsonrpcError(undefined, JSONRPC_PARSE_ERROR, "request line is not valid JSON")
          : jsonrpcError(undefined, JSONRPC_INVALID_REQUEST, "request handling failed");
    }
    if (response !== null) {
      write(`${stringifyJsonrpcMessage(response)}\n`);
      handled += 1;
    }
  }
  return handled;
}
