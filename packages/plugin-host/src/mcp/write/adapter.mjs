// Composed T01 + T02 MCP adapter framing.
//
// Everything that can be reused from the sealed T01 module is reused: request
// validation, id handling, and JSON-RPC error shaping all come from
// `handleJsonrpc` there.  This module overrides only the two payloads that
// genuinely differ on the composed surface (`initialize` instructions and the
// `tools/list` table) and adds the mutating `isError` rule.  The HTTP and
// STDIO shells are restated because the sealed module's shells are bound to
// its own `handleJsonrpc`; they carry no contract of their own.

import {
  HTTP_MCP_PATH,
  JSONRPC_PARSE_ERROR,
  JSONRPC_INVALID_REQUEST,
  JSONRPC_VERSION,
  handleJsonrpc as handleReadJsonrpc,
  parseJsonrpcMessage,
  stringifyJsonrpcMessage,
} from "../read/mcp-server.mjs";
import {
  GLOBAL_EXACT_COUNT,
  PROTOCOL_VERSION,
  isMutatingTool,
  mergedToolDescriptors,
} from "./catalog-set.mjs";

export { HTTP_MCP_PATH, JSONRPC_VERSION, PROTOCOL_VERSION };

const COMPOSED_INSTRUCTIONS =
  "Composed stateless surface: the sealed read and planning tools plus eleven " +
  "MUTATING_EFFECT tools. Every mutating call requires dry_run, " +
  "expected_revision, and an idempotency key, and answers with an " +
  "ActionIntent, a CapabilityLease id, and an EffectReceipt. An unresolved " +
  "effect answers UNKNOWN with reconciliation_required and must never be " +
  "read as either success or as proof that nothing happened.";

/**
 * Whether a completed mutating call may be presented to the model as success.
 *
 * Only a committed effect, or a dry run that intentionally executed nothing,
 * is a success. FAILED, ROLLED_BACK, and UNKNOWN are not, so none of them is
 * ever framed as a successful tool call.
 */
export function isSuccessfulMutation(envelope) {
  const mutation = envelope?.data?.mutation;
  if (mutation === undefined || mutation === null) {
    return false;
  }
  if (mutation.effect_status === "SUCCEEDED") {
    return true;
  }
  return mutation.effect_status === "NOT_EXECUTED" && mutation.dry_run === true;
}

/** Wrap a handler port so mutating outcomes carry an honest `isError`. */
export function composedHandlerPort(handlerPort) {
  return {
    async call(toolName, args, requestId) {
      const outcome = await handlerPort.call(toolName, args, requestId);
      if (outcome.isError || !isMutatingTool(toolName)) {
        return outcome;
      }
      return { envelope: outcome.envelope, isError: !isSuccessfulMutation(outcome.envelope) };
    },
  };
}

/** Handle one JSON-RPC request against the composed surface. */
export async function handleJsonrpc(request, handlerPort) {
  const response = await handleReadJsonrpc(request, composedHandlerPort(handlerPort));
  if (response === null || response.result === undefined) {
    return response;
  }
  if (request.method === "tools/list") {
    return {
      ...response,
      result: { tools: mergedToolDescriptors() },
    };
  }
  if (request.method === "initialize") {
    return {
      ...response,
      result: { ...response.result, instructions: COMPOSED_INSTRUCTIONS },
    };
  }
  return response;
}

function jsonrpcError(requestId, code, message) {
  const response = { jsonrpc: JSONRPC_VERSION };
  if (requestId !== undefined) response.id = requestId;
  response.error = { code, message };
  return response;
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
  return { status: 200, headers: responseHeaders, body: stringifyJsonrpcMessage(response) };
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

/** The composed tools/list cardinality, asserted by the catalog set. */
export function composedToolCount() {
  return GLOBAL_EXACT_COUNT;
}
