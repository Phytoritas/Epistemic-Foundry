#!/usr/bin/env node
// Packaged Epistemic Foundry MCP surface.
//
// The canonical T01 catalog of thirteen tools is advertised in full, because
// that catalog is the single source of the MCP wire literals and an agent must
// be able to tell "this operation does not exist" from "it exists but is not
// bound here".  A tool this payload cannot serve returns a canonical result
// envelope with `read_model_state: UNAVAILABLE` and a reason, never a silent
// success and never a made-up error code.
//
// Status and health are observed entirely in Node. The workspace-map handler
// is conditionally bound only for an explicitly configured local principal,
// workspace, and capability set. This MCP server never starts Python;
// Python-dependent schema, ledger, and retrieval commands remain CLI-only.

import { createRequire } from "node:module";

import {
  BOUND_TOOL_NAMES,
  createHealthProjection,
  createStatusProjection,
  observeMapQueryBinding,
  observePluginPayload,
  UNBOUND_REASON,
} from "./runtime-observation.mjs";

const require = createRequire(import.meta.url);
const descriptorDocument = require("./tool-descriptors.json");

const JSONRPC_VERSION = "2.0";
const PROTOCOL_VERSION = descriptorDocument.protocol_version;
const MAX_JSON_FRAME_BYTES = 1024 * 1024;
const FRAME_TOO_LARGE_MESSAGE = "request line exceeds the 1 MiB limit";
const INTERNAL_TOOL_ERROR_MESSAGE = "internal tool error";
const INTERNAL_SERVER_ERROR_MESSAGE = "internal server error";
const MAP_BUILD_UNAVAILABLE_REASON =
  "the bundled workspace-map producer could not build the requested snapshot";

/** Every name the canonical catalog declares. */
const CATALOG_TOOLS = new Set(descriptorDocument.tools.map((tool) => tool.name));

function jsonValuesEqual(left, right) {
  const pending = [[left, right]];
  while (pending.length > 0) {
    const [currentLeft, currentRight] = pending.pop();
    if (currentLeft === currentRight) continue;
    if (
      currentLeft === null ||
      currentRight === null ||
      typeof currentLeft !== "object" ||
      typeof currentRight !== "object"
    ) {
      return false;
    }
    const leftIsArray = Array.isArray(currentLeft);
    if (leftIsArray !== Array.isArray(currentRight)) return false;
    if (leftIsArray) {
      if (currentLeft.length !== currentRight.length) return false;
      for (let index = 0; index < currentLeft.length; index += 1) {
        pending.push([currentLeft[index], currentRight[index]]);
      }
      continue;
    }
    const leftKeys = Object.keys(currentLeft);
    const rightKeys = Object.keys(currentRight);
    if (leftKeys.length !== rightKeys.length) return false;
    for (const key of leftKeys) {
      if (!Object.hasOwn(currentRight, key)) return false;
      pending.push([currentLeft[key], currentRight[key]]);
    }
  }
  return true;
}

/**
 * Validate arguments against the tool's own declared input schema.
 *
 * A malformed request is not an availability fact.  Without this, asking for a
 * claim with no `claim_id` reports "no claim store is bound", which tells the
 * caller something true about the package and nothing about their mistake.
 *
 * This is a bounded structural check over the shapes the canonical inputs
 * actually use — required keys, declared types, string bounds, integer
 * ranges, enums, and closed objects. It is not a general JSON Schema engine,
 * and it refuses rather than guesses when it meets a construct it does not
 * model.
 */
function validateArguments(tool, args) {
  const descriptor = descriptorDocument.tools.find((entry) => entry.name === tool);
  const schema = descriptor?.inputSchema;
  if (schema === undefined) {
    return { message: `${tool} declares no input schema`, ok: false };
  }
  if (args === null || typeof args !== "object" || Array.isArray(args)) {
    return { message: "arguments must be a JSON object", ok: false };
  }
  const properties = schema.properties ?? {};
  if (schema.additionalProperties === false) {
    const unknown = Object.keys(args).filter((key) => properties[key] === undefined);
    if (unknown.length > 0) {
      return { message: `unknown argument(s): ${unknown.sort().join(", ")}`, ok: false };
    }
  }
  for (const key of schema.required ?? []) {
    if (args[key] === undefined) {
      return { message: `${key} is required`, ok: false };
    }
  }
  for (const [key, value] of Object.entries(args)) {
    const rule = properties[key];
    if (rule === undefined) continue;
    if (rule.type !== undefined) {
      const types = Array.isArray(rule.type) ? rule.type : [rule.type];
      const actual =
        value === null
          ? "null"
          : Array.isArray(value)
            ? "array"
            : Number.isInteger(value)
              ? "integer"
              : typeof value;
      const accepted =
        types.includes(actual) ||
        (actual === "integer" && types.includes("number"));
      if (!accepted) {
        return { message: `${key} must be ${types.join(" or ")}`, ok: false };
      }
    }
    if (typeof value === "string") {
      if (rule.minLength !== undefined && value.length < rule.minLength) {
        return { message: `${key} must be at least ${rule.minLength} character(s)`, ok: false };
      }
      if (rule.maxLength !== undefined && value.length > rule.maxLength) {
        return { message: `${key} must be at most ${rule.maxLength} character(s)`, ok: false };
      }
      if (rule.pattern !== undefined && !new RegExp(rule.pattern, "u").test(value)) {
        return { message: `${key} does not match ${rule.pattern}`, ok: false };
      }
    }
    if (typeof value === "number") {
      if (rule.minimum !== undefined && value < rule.minimum) {
        return { message: `${key} must be at least ${rule.minimum}`, ok: false };
      }
      if (rule.maximum !== undefined && value > rule.maximum) {
        return { message: `${key} must be at most ${rule.maximum}`, ok: false };
      }
    }
    if (
      Array.isArray(rule.enum) &&
      !rule.enum.some((candidate) => jsonValuesEqual(candidate, value))
    ) {
      return { message: `${key} must be one of ${rule.enum.join(", ")}`, ok: false };
    }
  }
  return { ok: true };
}

function response(id, result) {
  return { jsonrpc: JSONRPC_VERSION, id, result };
}

function error(id, code, message) {
  const payload = { jsonrpc: JSONRPC_VERSION };
  if (id !== undefined) payload.id = id;
  payload.error = { code, message };
  return payload;
}

function classifyRequestId(request) {
  if (!Object.hasOwn(request, "id")) return { kind: "absent" };
  const value = request.id;
  if (typeof value === "string") {
    return { kind: "valid", value, correlation: JSON.stringify(value) };
  }
  if (typeof value === "number" && Number.isSafeInteger(value)) {
    return { kind: "valid", value, correlation: JSON.stringify(value) };
  }
  return { kind: "invalid" };
}

function toolResult(payload, isError = false) {
  return {
    content: [{ type: "text", text: JSON.stringify(payload) }],
    structuredContent: payload,
    isError,
  };
}

/** The canonical data schema refs a tool declares, for a non-null result. */
function dataSchemaRefs(tool) {
  const descriptor = descriptorDocument.tools.find((entry) => entry.name === tool);
  return descriptor?.annotations?.dataSchemaRefs ?? [];
}

/**
 * Build one canonical `foundry-mcp-tool-result` envelope.
 *
 * Every field the schema requires is present and no field it forbids is
 * added, so a caller that validates against the sealed contract accepts this
 * payload.  `data_schema_refs` is empty whenever `data` is null: claiming a
 * schema for absent data would describe something that was never returned.
 */
function resultEnvelope(
  tool,
  requestId,
  workspaceId,
  state,
  data,
  degradationReason = null,
  generatedAt = new Date().toISOString(),
) {
  return {
    data,
    data_schema_refs: data === null ? [] : dataSchemaRefs(tool),
    degradation_reason: degradationReason,
    generated_at: generatedAt,
    protocol_version: PROTOCOL_VERSION,
    read_model_state: state,
    receipts: [],
    request_id: requestId,
    tool,
    workspace_id: workspaceId,
  };
}

/**
 * Build one canonical `foundry-mcp-tool-error` envelope.
 *
 * `errorCode` must come from the sealed enum; a runtime-specific reason goes
 * in `details`, which is exactly where the T02 contract puts codes the
 * top-level vocabulary does not name.
 */
function errorEnvelope(tool, requestId, errorCode, message, details = null) {
  return {
    details,
    error_code: errorCode,
    message,
    protocol_version: PROTOCOL_VERSION,
    request_id: requestId,
    // Only an internal fault is worth retrying; a malformed request or an
    // unknown name will fail identically every time.
    retryable: errorCode === "INTERNAL",
    tool,
  };
}

function failure(tool, requestId, errorCode, message, details = null) {
  return toolResult(errorEnvelope(tool, requestId, errorCode, message, details), true);
}

/** An advertised tool this package does not bind. */
function unavailable(tool, requestId, workspaceId, reason) {
  return toolResult(
    resultEnvelope(tool, requestId, workspaceId, "UNAVAILABLE", null, reason),
  );
}

/**
 * `foundry.status` — the one tool that must answer even when nothing works.
 *
 * The shared projection observes installed bytes and explicit configuration
 * without starting the optional Python runtime.
 */
function statusTool(requestId, workspaceId) {
  const projection = createStatusProjection();
  return toolResult(
    resultEnvelope(
      "foundry.status",
      requestId,
      workspaceId,
      projection.state,
      projection.data,
      projection.degradationReason,
    ),
  );
}

/**
 * `foundry.health` — component readiness, observed rather than asserted.
 */
function healthTool(requestId, workspaceId) {
  const projection = createHealthProjection();
  return toolResult(
    resultEnvelope(
      "foundry.health",
      requestId,
      workspaceId,
      projection.state,
      projection.data,
      projection.degradationReason,
    ),
  );
}

/**
 * `foundry.map.query` — on-demand use of the bundled repository map producer.
 *
 * All principal, workspace, and capability checks precede the lazy import, so
 * neither a configured path nor a caller-supplied workspace grants access by
 * itself. The returned snapshot is never cached, persisted, or truncated.
 */
async function mapQueryTool(requestId, workspaceId, args) {
  const binding = observeMapQueryBinding({ requestedWorkspaceId: workspaceId });
  if (!binding.ok) {
    return unavailable(
      "foundry.map.query",
      requestId,
      workspaceId,
      binding.reason,
    );
  }

  const generatedAt = new Date().toISOString();
  const limit = args.limit ?? 50;
  const query = args.query ?? null;
  try {
    const { buildRepositoryWorkspaceMapSnapshot } = await import(
      "./workspace-map/snapshot/index.mjs"
    );
    const snapshot = await buildRepositoryWorkspaceMapSnapshot({
      generatedAt,
      mapId: `MAP-${workspaceId}`.slice(0, 128),
      query,
      workspaceId,
      workspaceRoot: binding.workspace.root,
    });
    if (snapshot.nodes.length > limit) {
      return toolResult(
        resultEnvelope(
          "foundry.map.query",
          requestId,
          workspaceId,
          "DEGRADED",
          snapshot,
          `the workspace map contains ${snapshot.nodes.length} nodes, more than the requested limit of ${limit}; the full map is returned rather than a silently narrowed one`,
          generatedAt,
        ),
      );
    }
    return toolResult(
      resultEnvelope(
        "foundry.map.query",
        requestId,
        workspaceId,
        "READY",
        snapshot,
        null,
        generatedAt,
      ),
    );
  } catch {
    return unavailable(
      "foundry.map.query",
      requestId,
      workspaceId,
      MAP_BUILD_UNAVAILABLE_REASON,
    );
  }
}

async function callTool(name, args, requestId) {
  // Unknown tool first: a name that does not exist cannot have its arguments
  // validated against a schema it does not have.
  if (!CATALOG_TOOLS.has(name)) {
    return failure(
      null,
      requestId,
      "UNKNOWN_TOOL",
      `no tool named ${String(name)} exists in the canonical catalog`,
    );
  }
  // Then input validity, before any availability answer: a malformed request
  // must not be reported as a fact about what this package binds.
  const valid = validateArguments(name, args);
  if (!valid.ok) {
    return failure(name, requestId, "INVALID_INPUT", valid.message);
  }
  const workspaceId = args.workspace_id;
  const unboundReason = UNBOUND_REASON[name];
  if (unboundReason !== undefined) {
    return unavailable(name, requestId, workspaceId, unboundReason);
  }
  if (name === "foundry.status") {
    return statusTool(requestId, workspaceId);
  }
  if (name === "foundry.health") {
    return healthTool(requestId, workspaceId);
  }
  if (name === "foundry.map.query") {
    return mapQueryTool(requestId, workspaceId, args);
  }
  return failure(
    name,
    requestId,
    "INTERNAL",
    INTERNAL_TOOL_ERROR_MESSAGE,
  );
}

function initializeInstructions() {
  const mapReason = UNBOUND_REASON["foundry.map.query"];
  const mapBinding = mapReason === undefined
    ? "foundry.map.query is conditionally bound only for the exact configured " +
      "workspace; environment configuration is not proof of authority. "
    : `foundry.map.query is UNAVAILABLE: ${mapReason}. `;
  return (
    `The canonical ${descriptorDocument.tools.length}-tool catalog. Exactly ` +
    `${BOUND_TOOL_NAMES.length} tools are configured as bound in this process: ` +
    `${BOUND_TOOL_NAMES.join(", ")}. The remaining ` +
    `${descriptorDocument.tools.length - BOUND_TOOL_NAMES.length} tools return ` +
    "UNAVAILABLE with the reason they are unbound. Status and health are " +
    "Node-only and do not require Python. Retrieval lanes, schema validation, " +
    "and ledger verification run through the optional bundled Python CLI rather " +
    `than this surface. ${mapBinding}Workflow execution, promotion, and evidence ` +
    "recomputation are not part of this package."
  );
}

async function handleRequest(request) {
  if (request === null || typeof request !== "object" || Array.isArray(request)) {
    return error(undefined, -32600, "request must be an object");
  }
  const requestId = classifyRequestId(request);
  if (
    request.jsonrpc !== JSONRPC_VERSION ||
    typeof request.method !== "string" ||
    requestId.kind === "invalid"
  ) {
    return error(
      requestId.kind === "valid" ? requestId.value : undefined,
      -32600,
      "invalid JSON-RPC request",
    );
  }
  if (requestId.kind === "absent") return null;
  if (request.method === "initialize") {
    return response(requestId.value, {
      protocolVersion: PROTOCOL_VERSION,
      capabilities: { tools: { listChanged: false } },
      serverInfo: {
        name: "epistemic-foundry",
        title: "Epistemic Foundry",
        version: observePluginPayload().plugin_version ?? "unknown",
      },
      instructions: initializeInstructions(),
    });
  }
  if (request.method === "tools/list") {
    return response(requestId.value, { tools: descriptorDocument.tools });
  }
  if (request.method === "ping") {
    return response(requestId.value, {});
  }
  if (request.method === "tools/call") {
    const params = request.params;
    if (params === null || typeof params !== "object" || Array.isArray(params)) {
      return error(requestId.value, -32602, "params must be an object");
    }
    // A fault inside a tool is a tool outcome, not a malformed request, so it
    // is reported in the canonical error envelope rather than as a JSON-RPC
    // protocol error.
    let outcome;
    try {
      outcome = await callTool(
        params.name,
        params.arguments ?? {},
        requestId.correlation,
      );
    } catch {
      outcome = failure(
        typeof params.name === "string" && CATALOG_TOOLS.has(params.name)
          ? params.name
          : null,
        requestId.correlation,
        "INTERNAL",
        INTERNAL_TOOL_ERROR_MESSAGE,
      );
    }
    return response(requestId.value, outcome);
  }
  return error(requestId.value, -32601, `unknown method: ${request.method}`);
}

// Every tool must be either bound to a handler or explicitly declared unbound.
// A name in neither set would be advertised with no defined behaviour, which is
// exactly the silent gap this payload exists to avoid.
const BOUND_TOOLS = new Set(BOUND_TOOL_NAMES);
const unclassified = descriptorDocument.tools
  .map((tool) => tool.name)
  .filter((name) => !BOUND_TOOLS.has(name) && UNBOUND_REASON[name] === undefined);
const orphanReasons = Object.keys(UNBOUND_REASON).filter(
  (name) => !CATALOG_TOOLS.has(name),
);
if (unclassified.length > 0 || orphanReasons.length > 0) {
  process.stderr.write(
    `${JSON.stringify({
      error_code: "TOOL_SURFACE_MISMATCH",
      orphan_reasons: orphanReasons,
      unclassified,
    })}\n`,
  );
  process.exit(1);
}

async function dispatchLine(line) {
  if (line.trim() === "") return;
  // Parse and dispatch stay separate so an internal fault is never reported
  // as a client parse error.
  let request;
  try {
    request = JSON.parse(line);
  } catch {
    process.stdout.write(
      `${JSON.stringify(error(undefined, -32700, "request line is not valid JSON"))}\n`,
    );
    return;
  }
  let payload;
  try {
    payload = await handleRequest(request);
  } catch {
    const id = Object.hasOwn(request ?? {}, "id") ? request.id : undefined;
    payload = error(id, -32603, INTERNAL_SERVER_ERROR_MESSAGE);
  }
  if (payload !== null) process.stdout.write(`${JSON.stringify(payload)}\n`);
}

function rejectOversizedFrame() {
  process.stdout.write(
    `${JSON.stringify(error(undefined, -32700, FRAME_TOO_LARGE_MESSAGE))}\n`,
  );
}

// This file is a process entry point: `.mcp.json` starts it directly over
// stdio, and nothing else imports it. One extra byte permits an exactly 1 MiB
// frame followed by the CR in a CRLF delimiter without treating the delimiter
// as frame content. Bytes beyond this fixed buffer are discarded until LF.
const frame = Buffer.alloc(MAX_JSON_FRAME_BYTES + 1);
let frameLength = 0;
let frameTooLarge = false;

for await (const rawChunk of process.stdin) {
  const chunk = Buffer.isBuffer(rawChunk)
    ? rawChunk
    : Buffer.from(rawChunk, "utf8");
  let offset = 0;

  while (offset < chunk.length) {
    const newline = chunk.indexOf(0x0a, offset);
    const segmentEnd = newline === -1 ? chunk.length : newline;
    const segmentLength = segmentEnd - offset;

    if (!frameTooLarge && segmentLength > 0) {
      const remaining = frame.length - frameLength;
      if (segmentLength > remaining) {
        frameTooLarge = true;
        rejectOversizedFrame();
      } else {
        chunk.copy(frame, frameLength, offset, segmentEnd);
        frameLength += segmentLength;
        if (
          frameLength > MAX_JSON_FRAME_BYTES &&
          frame[frameLength - 1] !== 0x0d
        ) {
          frameTooLarge = true;
          rejectOversizedFrame();
        }
      }
    }

    if (newline === -1) break;

    if (!frameTooLarge) {
      const lineLength =
        frameLength > 0 && frame[frameLength - 1] === 0x0d
          ? frameLength - 1
          : frameLength;
      await dispatchLine(frame.subarray(0, lineLength).toString("utf8"));
    }
    frameLength = 0;
    frameTooLarge = false;
    offset = newline + 1;
  }
}

// Match readline's handling of a final unterminated line while retaining the
// same frame bound. An oversized frame was already rejected when it crossed
// the limit and needs no second response at EOF.
if (!frameTooLarge && frameLength > 0) {
  const lineLength =
    frame[frameLength - 1] === 0x0d ? frameLength - 1 : frameLength;
  await dispatchLine(frame.subarray(0, lineLength).toString("utf8"));
}
