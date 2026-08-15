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
// Python is never started for initialize, ping, or tools/list.  It runs at
// most once per tool call, and this adapter never reimplements schema, ledger,
// or index semantics that Python already owns.

import { createInterface } from "node:readline";
import { createRequire } from "node:module";
import { createHash } from "node:crypto";
import { readFileSync, realpathSync } from "node:fs";
import { isAbsolute } from "node:path";

import {
  readRuntimeManifest,
  resolveInterpreter,
  runBundledJson,
} from "./python-runtime.mjs";

const require = createRequire(import.meta.url);
const descriptorDocument = require("./tool-descriptors.json");

const JSONRPC_VERSION = "2.0";
const PROTOCOL_VERSION = descriptorDocument.protocol_version;

/** Every name the canonical catalog declares. */
const CATALOG_TOOLS = new Set(descriptorDocument.tools.map((tool) => tool.name));

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
      (actual === "integer" && types.includes("number")) ||
      (actual === "object" && types.includes("object"));
    if (!accepted) {
      return { message: `${key} must be ${types.join(" or ")}`, ok: false };
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
      if (Array.isArray(rule.enum) && !rule.enum.includes(value)) {
        return { message: `${key} must be one of ${rule.enum.join(", ")}`, ok: false };
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
  }
  return { ok: true };
}

/** Lanes this release actually executes. The rest return UNSEARCHED. */
const SERVED_LANES = Object.freeze(["lexical", "citation", "entity_variable"]);

/**
 * Tools this payload can actually answer, and how.
 *
 * Everything else in the canonical catalog is advertised and returns
 * UNAVAILABLE with the reason recorded here, so the gap between the contract
 * and this package is visible rather than implied.
 */
const UNBOUND_REASON = Object.freeze({
  "foundry.artifact.get":
    "no artifact store is bound in this package; artifact read models are not built",
  "foundry.atlas.query":
    "no coverage atlas is bound in this package",
  "foundry.claim.get":
    "no claim store is bound in this package; claims require the promotion path",
  "foundry.frame.compile":
    "plan compilation requires the durable plan-artifact store, which is not bound in this package",
  "foundry.parliament.plan":
    "plan compilation requires the durable plan-artifact store, which is not bound in this package",
  "foundry.passport.get":
    "no hypothesis passport store is bound in this package",
  "foundry.replay.diff":
    "no run store is bound in this package, so runs cannot be compared",
  "foundry.search.plan":
    "plan compilation requires the durable plan-artifact store, which is not bound in this package",
  "foundry.session.get":
    "no FORGE session store is bound in this package; the payload holds no session state",
  "foundry.validation.plan":
    "plan compilation requires the durable plan-artifact store, which is not bound in this package",
});

/**
 * The directory tree this server may touch.
 *
 * An MCP caller is not necessarily the user: a tool call can originate from
 * text a model read somewhere.  Handing a caller-chosen path straight to a
 * command that writes files would let injected text overwrite anything the
 * process can reach, so every path argument is confined to one explicitly
 * configured root.  Absent configuration, path-taking tools refuse rather than
 * defaulting to the current directory, which would be whatever the host
 * happened to start in.
 */
function workspaceRoot() {
  const configured = process.env.EFOUNDRY_WORKSPACE_ROOT;
  if (typeof configured !== "string" || configured.length === 0) {
    return {
      message:
        "EFOUNDRY_WORKSPACE_ROOT is not configured, so no path may be read or " +
        "written. Set it to the directory this server may use.",
      ok: false,
    };
  }
  if (!isAbsolute(configured)) {
    return { message: "EFOUNDRY_WORKSPACE_ROOT must be an absolute path", ok: false };
  }
  try {
    return { ok: true, root: realpathSync(configured) };
  } catch {
    return {
      message: `EFOUNDRY_WORKSPACE_ROOT does not exist: ${configured}`,
      ok: false,
    };
  }
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

/** Read a packaged payload file, returning null rather than throwing. */
function readPayloadFile(relativePath) {
  try {
    return readFileSync(new URL(relativePath, new URL("../", import.meta.url)));
  } catch {
    return null;
  }
}

/** Facts this Node process owns outright: its own installed identity. */
function observePayload() {
  const manifestBytes = readPayloadFile(".codex-plugin/plugin.json");
  const inventoryBytes = readPayloadFile("skills/skill-inventory.json");
  let manifest = null;
  try {
    manifest = manifestBytes === null ? null : JSON.parse(manifestBytes.toString("utf8"));
  } catch {
    manifest = null;
  }
  return {
    manifest_present: manifestBytes !== null,
    plugin_name: manifest?.name ?? null,
    plugin_version: manifest?.version ?? null,
    skill_inventory_sha256:
      inventoryBytes === null
        ? null
        : `sha256:${createHash("sha256").update(inventoryBytes).digest("hex")}`,
  };
}

function toolResult(payload, isError = false) {
  return {
    content: [{ type: "text", text: JSON.stringify(payload) }],
    structuredContent: payload,
    isError,
  };
}

/**
 * Whether path-taking tools can run at all.
 *
 * Reported by `status` so a caller learns the configuration is missing before
 * a tool call fails, rather than after.
 */
function workspaceState() {
  const workspace = workspaceRoot();
  return workspace.ok
    ? { root: workspace.root, status: "CONFIGURED" }
    : {
        message: workspace.message,
        path_tools_available: false,
        status: "UNCONFIGURED",
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
) {
  return {
    data,
    data_schema_refs: data === null ? [] : dataSchemaRefs(tool),
    degradation_reason: degradationReason,
    generated_at: new Date().toISOString(),
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
 * It reports the payload, the runtime binding, and the capability set, so a
 * caller learns why a capability is absent instead of inferring it from a
 * missing tool.
 */
function statusTool(requestId, workspaceId) {
  const payload = observePayload();
  const manifestRead = readRuntimeManifest();
  const interpreter = resolveInterpreter();

  const runtime = manifestRead.ok
    ? {
        closure_sha256: manifestRead.manifest.closure_sha256 ?? null,
        file_count: manifestRead.manifest.file_count ?? null,
        scope: manifestRead.manifest.scope ?? null,
        source_commit: manifestRead.manifest.source_commit ?? null,
        source_root: manifestRead.manifest.source_root ?? null,
        status: "PRESENT",
      }
    : {
        error_code: manifestRead.error_code,
        message: manifestRead.message,
        status: "MISSING",
      };

  const bound = descriptorDocument.tools
    .map((tool) => tool.name)
    .filter((name) => UNBOUND_REASON[name] === undefined);
  const unbound = Object.keys(UNBOUND_REASON).sort();
  // `foundry.map.query` is served by the bundled JavaScript producer, so it
  // survives an unusable Python runtime; reporting it as unbound there would
  // understate what the package can still answer.
  const withoutPython = ["foundry.status", "foundry.map.query"];
  const unboundWithoutPython = descriptorDocument.tools
    .map((tool) => tool.name)
    .filter((name) => !withoutPython.includes(name));

  if (!interpreter.ok) {
    return toolResult(
      resultEnvelope(
        "foundry.status",
        requestId,
        workspaceId,
        "DEGRADED",
        {
          bound_tools: withoutPython,
          full_v4_operational: false,
          interpreter: {
            error_code: interpreter.error_code,
            message: interpreter.message,
            status: "UNAVAILABLE",
          },
          payload,
          retrieval_lanes: { cli_served: [] },
          runtime,
          unbound_tools: unboundWithoutPython,
          workspace: workspaceState(),
        },
        interpreter.message,
      ),
    );
  }

  const probe = runBundledJson(["status"]);
  if (!probe.ok || probe.status !== 0) {
    const reason = probe.ok ? probe.stderr.trim() : probe.message;
    return toolResult(
      resultEnvelope(
        "foundry.status",
        requestId,
        workspaceId,
        "DEGRADED",
        {
          bound_tools: withoutPython,
          full_v4_operational: false,
          interpreter: { command: interpreter.command, status: "READY" },
          payload,
          retrieval_lanes: { cli_served: [] },
          runtime,
          unbound_tools: unboundWithoutPython,
          workspace: workspaceState(),
        },
        reason === "" ? "the bundled runtime did not answer" : reason,
      ),
    );
  }

  return toolResult(
    resultEnvelope("foundry.status", requestId, workspaceId, "READY", {
      bound_tools: bound,
      canonical_schemas_loaded: probe.data.canonical_schemas_loaded ?? null,
      full_v4_operational: false,
      interpreter: { command: interpreter.command, status: "READY" },
      payload,
      retrieval_lanes: {
        cli_served: SERVED_LANES,
        note:
          "retrieval lanes are executed through the bundled CLI; the other " +
          "eight canonical lanes are declared and return UNSEARCHED",
      },
      runtime,
      unbound_tools: unbound,
      workspace: workspaceState(),
    }),
  );
}

/**
 * `foundry.health` — component readiness, observed rather than asserted.
 *
 * The bundled runtime reports which components it implements; this adds what
 * only the Node side knows, namely whether the interpreter and payload are
 * usable at all.
 */
function healthTool(requestId, workspaceId) {
  const interpreter = resolveInterpreter();
  if (!interpreter.ok) {
    return toolResult(
      resultEnvelope(
        "foundry.health",
        requestId,
        workspaceId,
        "DEGRADED",
        {
          components: [
            { component: "python_runtime", state: "UNAVAILABLE" },
            { component: "plugin_payload", state: "READY" },
          ],
        },
        interpreter.message,
      ),
    );
  }
  const probe = runBundledJson(["status"]);
  if (!probe.ok || probe.status !== 0) {
    return toolResult(
      resultEnvelope(
        "foundry.health",
        requestId,
        workspaceId,
        "DEGRADED",
        {
          components: [
            { component: "python_runtime", state: "DEGRADED" },
            { component: "plugin_payload", state: "READY" },
          ],
        },
        probe.ok ? "the bundled runtime returned a failure" : probe.message,
      ),
    );
  }
  const implemented = Array.isArray(probe.data.implemented)
    ? probe.data.implemented
    : [];
  return toolResult(
    resultEnvelope(
      "foundry.health",
      requestId,
      workspaceId,
      "DEGRADED",
      {
        components: [
          { component: "python_runtime", state: "READY" },
          { component: "plugin_payload", state: "READY" },
          {
            component: "canonical_registry",
            // Observed from the runtime probe, not assumed: a registry that
            // loaded no schemas is not ready.
            observed_schema_count: probe.data.canonical_schemas_loaded ?? null,
            state:
              typeof probe.data.canonical_schemas_loaded === "number" &&
              probe.data.canonical_schemas_loaded > 0
                ? "READY"
                : "UNAVAILABLE",
          },
          {
            component: "workspace_map",
            state: workspaceRoot().ok ? "READY" : "UNAVAILABLE",
          },
          { component: "workflow_execution", state: "UNAVAILABLE" },
        ],
        implemented_modules: implemented,
      },
      "workflow execution, promotion, and evidence recomputation are not bound in this package",
    ),
  );
}

/**
 * `foundry.map.query` — the bundled workspace-map producer.
 *
 * The map is computed from the configured workspace root by the same source
 * the repository uses; this adapter only supplies the roots and forwards the
 * snapshot.
 */
async function mapQueryTool(requestId, workspaceId, args) {
  const workspace = workspaceRoot();
  if (!workspace.ok) {
    return toolResult(
      resultEnvelope(
        "foundry.map.query",
        requestId,
        workspaceId,
        "UNAVAILABLE",
        null,
        workspace.message,
      ),
    );
  }
  // The canonical input allows an absent or null query.  The bundled producer
  // models a null query in its ranking stage but its snapshot assembler still
  // requires a string, so an unfocused map cannot be built here.  That is
  // reported as a bounded gap rather than answered with a substituted term the
  // caller never asked for.
  const requested = args.query;
  if (typeof requested !== "string" || requested.trim().length === 0) {
    return toolResult(
      resultEnvelope(
        "foundry.map.query",
        requestId,
        workspaceId,
        "UNAVAILABLE",
        null,
        "the bundled workspace-map producer requires a non-empty query; an unfocused map is not built by this package",
      ),
    );
  }
  const query = requested;
  const limit = typeof args.limit === "number" ? args.limit : null;
  try {
    const { buildRepositoryWorkspaceMapSnapshot } = await import(
      "./workspace-map/snapshot/index.mjs"
    );
    const snapshot = await buildRepositoryWorkspaceMapSnapshot({
      generatedAt: new Date().toISOString(),
      // The map ID is bounded independently of the workspace ID, which the
      // canonical snapshot schema caps at 128 characters.
      mapId: `MAP-${workspaceId}`.slice(0, 128),
      query,
      workspaceId,
      workspaceRoot: workspace.root,
    });
    if (limit === null || snapshot.nodes.length <= limit) {
      return toolResult(
        resultEnvelope("foundry.map.query", requestId, workspaceId, "READY", snapshot),
      );
    }
    // Truncation is disclosed rather than applied silently: a map that
    // quietly drops nodes still claims to cover the whole workspace.
    return toolResult(
      resultEnvelope(
        "foundry.map.query",
        requestId,
        workspaceId,
        "DEGRADED",
        snapshot,
        `the workspace map contains ${snapshot.nodes.length} nodes, more than the requested limit of ${limit}; the full map is returned rather than a silently narrowed one`,
      ),
    );
  } catch (cause) {
    return toolResult(
      resultEnvelope(
        "foundry.map.query",
        requestId,
        workspaceId,
        "UNAVAILABLE",
        null,
        `the workspace map could not be built: ${cause.message}`,
      ),
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
    `${name} is declared bound but has no handler`,
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
        version: observePayload().plugin_version ?? "unknown",
      },
      instructions:
        "The canonical thirteen-tool catalog. foundry.status, foundry.health, " +
        "and foundry.map.query are bound in this package; every other tool " +
        "returns UNAVAILABLE with the reason it is unbound. Retrieval lanes, " +
        "schema validation, and ledger verification run through the bundled " +
        "CLI rather than this surface. foundry.map.query requires " +
        "EFOUNDRY_WORKSPACE_ROOT. Workflow execution, promotion, and evidence " +
        "recomputation are not part of this package.",
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
    } catch (cause) {
      outcome = failure(
        typeof params.name === "string" && CATALOG_TOOLS.has(params.name)
          ? params.name
          : null,
        requestId.correlation,
        "INTERNAL",
        `the tool failed unexpectedly: ${cause.message}`,
      );
    }
    return response(requestId.value, outcome);
  }
  return error(requestId.value, -32601, `unknown method: ${request.method}`);
}

// Every tool must be either bound to a handler or explicitly declared unbound.
// A name in neither set would be advertised with no defined behaviour, which is
// exactly the silent gap this payload exists to avoid.
const BOUND_TOOLS = new Set([
  "foundry.status",
  "foundry.health",
  "foundry.map.query",
]);
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

// This file is a process entry point: `.mcp.json` starts it directly over
// stdio, and nothing else imports it.
const lines = createInterface({ input: process.stdin, crlfDelay: Infinity });
for await (const line of lines) {
  if (line.trim() === "") continue;
  // Parse and dispatch stay separate so an internal fault is never reported
  // as a client parse error.
  let request;
  try {
    request = JSON.parse(line);
  } catch {
    process.stdout.write(
      `${JSON.stringify(error(undefined, -32700, "request line is not valid JSON"))}\n`,
    );
    continue;
  }
  let payload;
  try {
    payload = await handleRequest(request);
  } catch (cause) {
    const id = Object.hasOwn(request ?? {}, "id") ? request.id : undefined;
    payload = error(id, -32603, `internal server error: ${cause.message}`);
  }
  if (payload !== null) process.stdout.write(`${JSON.stringify(payload)}\n`);
}
