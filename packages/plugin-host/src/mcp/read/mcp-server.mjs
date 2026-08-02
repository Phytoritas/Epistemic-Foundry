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

export function toolDescriptors() {
  return structuredClone(descriptorDocument.tools);
}

function jsonrpcError(requestId, code, message) {
  return { jsonrpc: JSONRPC_VERSION, id: requestId, error: { code, message } };
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

/**
 * Handle one JSON-RPC request against the injected handler port.
 *
 * The handler port mirrors the shared Python ToolService:
 * `call(toolName, argumentsObject, requestId)` returning
 * `{ envelope, isError }`.  Notifications receive `null`.
 */
export async function handleJsonrpc(request, handlerPort) {
  if (!isPlainObject(request)) {
    return jsonrpcError(null, JSONRPC_INVALID_REQUEST, "request must be an object");
  }
  const requestId = Object.hasOwn(request, "id") ? request.id : undefined;
  const idIsInvalid =
    typeof requestId === "boolean" ||
    Array.isArray(requestId) ||
    isPlainObject(requestId);
  if (request.jsonrpc !== JSONRPC_VERSION || typeof request.method !== "string" || idIsInvalid) {
    const reportable =
      typeof requestId === "string" || typeof requestId === "number" ? requestId : null;
    return jsonrpcError(
      reportable,
      JSONRPC_INVALID_REQUEST,
      "request is not a JSON-RPC 2.0 call",
    );
  }
  if (requestId === undefined || requestId === null) {
    return null;
  }
  if (request.method === "initialize") {
    return { jsonrpc: JSONRPC_VERSION, id: requestId, result: initializeResult() };
  }
  if (request.method === "tools/list") {
    return {
      jsonrpc: JSONRPC_VERSION,
      id: requestId,
      result: { tools: toolDescriptors() },
    };
  }
  if (request.method === "tools/call") {
    const params = request.params;
    if (!isPlainObject(params) || typeof params.name !== "string") {
      return jsonrpcError(requestId, JSONRPC_INVALID_PARAMS, "params.name is required");
    }
    const args = Object.hasOwn(params, "arguments") ? params.arguments : {};
    const { envelope, isError } = await handlerPort.call(
      params.name,
      args,
      String(requestId),
    );
    return {
      jsonrpc: JSONRPC_VERSION,
      id: requestId,
      result: {
        content: [{ type: "text", text: JSON.stringify(envelope) }],
        structuredContent: envelope,
        isError: Boolean(isError),
      },
    };
  }
  return jsonrpcError(
    requestId,
    JSONRPC_METHOD_NOT_FOUND,
    `unknown method: ${request.method}`,
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
    request = JSON.parse(body);
  } catch {
    return {
      status: 400,
      headers: responseHeaders,
      body: JSON.stringify(
        jsonrpcError(null, JSONRPC_PARSE_ERROR, "body is not valid JSON"),
      ),
    };
  }
  const response = await handleJsonrpc(request, handlerPort);
  if (response === null) {
    return { status: 202, headers: responseHeaders, body: "" };
  }
  return { status: 200, headers: responseHeaders, body: JSON.stringify(response) };
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
      response = await handleJsonrpc(JSON.parse(line), handlerPort);
    } catch (error) {
      response =
        error instanceof SyntaxError
          ? jsonrpcError(null, JSONRPC_PARSE_ERROR, "request line is not valid JSON")
          : jsonrpcError(null, JSONRPC_INVALID_REQUEST, "request handling failed");
    }
    if (response !== null) {
      write(`${JSON.stringify(response)}\n`);
      handled += 1;
    }
  }
  return handled;
}
