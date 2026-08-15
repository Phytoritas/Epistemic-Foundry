// Read-only observations shared by the payload CLI and MCP server.
//
// Status and health are a Node-owned PLUGIN_ALPHA critical surface. They read
// only installed payload bytes and explicit environment configuration; they
// never start the optional bundled Python runtime and never infer a workspace
// or caller authority from cwd, PATH, or a repository checkout.

import { createHash } from "node:crypto";
import { readFileSync, realpathSync, statSync } from "node:fs";
import { isAbsolute, join, relative, resolve } from "node:path";

import {
  pluginRoot,
  readRuntimeManifest,
  RUNTIME_ERRORS,
} from "./python-runtime.mjs";

const ALWAYS_BOUND_TOOL_NAMES = Object.freeze([
  "foundry.status",
  "foundry.health",
]);

// These reasons are part of the candidate's truthful availability surface.
// In particular, read-model bindings remain unavailable until their
// authoritative stores, projections, and authorization paths are composed.
const ALWAYS_UNBOUND_REASON = Object.freeze({
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

export const SERVED_RETRIEVAL_LANES = Object.freeze([
  "lexical",
  "citation",
  "entity_variable",
]);

const QUALIFIED_STATUS = "SPEC_BUNDLE";
const IMPLEMENTATION_TARGET = "PLUGIN_ALPHA";
const IMPLEMENTATION_TARGET_STATUS = "INCOMPLETE";
const WORKFLOW_EXECUTION_REASON =
  "workflow execution, promotion, and evidence recomputation are not bound in this package";
const WORKSPACE_CONFIGURATION_REQUIREMENT =
  "EFOUNDRY_WORKSPACE_ID and an absolute EFOUNDRY_WORKSPACE_ROOT are both required for workspace mapping; paths alone do not establish caller authority.";
const MCP_AUTHORIZATION_CONFIGURATION_REQUIREMENT =
  "EFOUNDRY_PRINCIPAL_ID and JSON-array EFOUNDRY_MCP_CAPABILITIES are required for the local MCP binding; environment configuration is not proof of authority.";
const MCP_AUTHORIZATION_CONFIGURATION_NOTICE =
  "the local principal and capability values are configured but have not been independently authenticated; environment configuration is not proof of authority";
const MAP_READ_CAPABILITY = "mcp.read.map";
const MAX_PRINCIPAL_ID_LENGTH = 128;
const EMPTY_CAPABILITIES = Object.freeze([]);

const NODE_ONLY_CLI_COMMANDS = Object.freeze([
  "status",
  "health",
  "--runtime-info",
]);
const PYTHON_DEPENDENT_CLI_COMMANDS = Object.freeze([
  "schemas",
  "validate",
  "ledger verify",
  "retrieve build",
  "retrieve query",
]);

const sha256 = (bytes) =>
  `sha256:${createHash("sha256").update(bytes).digest("hex")}`;

function readBytes(path) {
  try {
    return { bytes: readFileSync(path), ok: true };
  } catch {
    return { message: "the requested payload file is missing or unreadable", ok: false };
  }
}

function readJson(path) {
  const read = readBytes(path);
  if (!read.ok) return { ...read, present: false };
  try {
    return {
      bytes: read.bytes,
      data: JSON.parse(read.bytes.toString("utf8")),
      ok: true,
      present: true,
    };
  } catch (cause) {
    return {
      bytes: read.bytes,
      message: `the JSON document is unreadable: ${cause.message}`,
      ok: false,
      present: true,
    };
  }
}

function observePluginIdentity(root) {
  const manifest = readJson(join(root, ".codex-plugin", "plugin.json"));
  const inventory = readBytes(join(root, "skills", "skill-inventory.json"));
  const pluginName = manifest.ok && typeof manifest.data?.name === "string"
    ? manifest.data.name
    : null;
  const pluginVersion = manifest.ok && typeof manifest.data?.version === "string"
    ? manifest.data.version
    : null;
  const ready =
    manifest.ok && pluginName !== null && pluginVersion !== null && inventory.ok;
  return {
    manifest_present: manifest.present,
    plugin_manifest_sha256: manifest.ok ? sha256(manifest.bytes) : null,
    plugin_name: pluginName,
    plugin_version: pluginVersion,
    skill_inventory_sha256: inventory.ok ? sha256(inventory.bytes) : null,
    status: ready ? "READY" : "UNAVAILABLE",
    ...(ready
      ? {}
      : {
          message:
            manifest.message ??
            (pluginName === null || pluginVersion === null
              ? "the plugin identity manifest does not contain a string name and version"
              : "the packaged skill inventory is missing or unreadable"),
        }),
  };
}

function observePayloadManifest(root) {
  const payloadRoot = join(root, "dist");
  const manifest = readJson(join(payloadRoot, "payload-manifest.json"));
  if (!manifest.ok) {
    return {
      manifest_present: manifest.present,
      manifest_sha256: manifest.present ? sha256(manifest.bytes) : null,
      status: "UNAVAILABLE",
      message: manifest.message,
    };
  }
  const files = manifest.data?.files;
  if (files === null || typeof files !== "object" || Array.isArray(files)) {
    return {
      manifest_present: true,
      manifest_sha256: sha256(manifest.bytes),
      status: "UNAVAILABLE",
      message: "the payload manifest does not contain a files object",
    };
  }
  if (Object.keys(files).length === 0) {
    return {
      manifest_present: true,
      manifest_sha256: sha256(manifest.bytes),
      status: "UNAVAILABLE",
      message: "the payload manifest records no files",
    };
  }

  const damaged = [];
  let checkedFileCount = 0;
  for (const [relativePath, expected] of Object.entries(files)) {
    const absolutePath = resolve(payloadRoot, relativePath);
    const confinedPath = relative(payloadRoot, absolutePath);
    if (
      relativePath.length === 0 ||
      confinedPath === ".." ||
      confinedPath.startsWith(`..${process.platform === "win32" ? "\\" : "/"}`) ||
      isAbsolute(confinedPath)
    ) {
      damaged.push(`${relativePath}: path escapes the payload root`);
      continue;
    }
    if (typeof expected !== "string" || !/^sha256:[0-9a-f]{64}$/u.test(expected)) {
      damaged.push(`${relativePath}: malformed digest`);
      continue;
    }
    const file = readBytes(absolutePath);
    if (!file.ok) {
      damaged.push(`${relativePath}: missing`);
      continue;
    }
    checkedFileCount += 1;
    if (sha256(file.bytes) !== expected) damaged.push(`${relativePath}: content differs`);
  }

  const ready = damaged.length === 0;
  return {
    descriptor_source: manifest.data.descriptor_source ?? null,
    file_count: Object.keys(files).length,
    integrity: ready
      ? { checked_file_count: checkedFileCount, status: "READY" }
      : { checked_file_count: checkedFileCount, damaged, status: "UNAVAILABLE" },
    manifest_present: true,
    manifest_sha256: sha256(manifest.bytes),
    source: manifest.data.source ?? null,
    status: ready ? "READY" : "UNAVAILABLE",
    ...(ready
      ? {}
      : { message: `the installed payload differs from its manifest: ${damaged.join("; ")}` }),
  };
}

export function observePluginPayload({ root = pluginRoot(import.meta.url) } = {}) {
  const identity = observePluginIdentity(root);
  const payloadManifest = observePayloadManifest(root);
  const ready = identity.status === "READY" && payloadManifest.status === "READY";
  return {
    ...identity,
    payload_manifest: payloadManifest,
    status: ready ? "READY" : "UNAVAILABLE",
    ...(ready
      ? {}
      : {
          message:
            identity.message ?? payloadManifest.message ?? "the plugin payload is unavailable",
        }),
  };
}

function observePythonRuntime(root) {
  const manifestPath = join(root, "runtime", "runtime-manifest.json");
  const manifestBytes = readBytes(manifestPath);
  const manifestRead = readRuntimeManifest(root);
  if (!manifestRead.ok) {
    return {
      error_code: manifestRead.error_code,
      integrity: {
        error_code: manifestRead.error_code,
        message: manifestRead.message,
        status: "UNAVAILABLE",
      },
      manifest_present: manifestBytes.ok,
      manifest_sha256: manifestBytes.ok ? sha256(manifestBytes.bytes) : null,
      message: manifestRead.message,
      status: "UNAVAILABLE",
    };
  }
  if (
    manifestRead.manifest === null ||
    typeof manifestRead.manifest !== "object" ||
    Array.isArray(manifestRead.manifest)
  ) {
    const message = "the runtime manifest root must be a JSON object";
    return {
      error_code: RUNTIME_ERRORS.RUNTIME_INTEGRITY_FAILED,
      integrity: {
        error_code: RUNTIME_ERRORS.RUNTIME_INTEGRITY_FAILED,
        message,
        status: "UNAVAILABLE",
      },
      manifest_present: true,
      manifest_sha256: manifestBytes.ok ? sha256(manifestBytes.bytes) : null,
      message,
      status: "UNAVAILABLE",
    };
  }

  // Status, health, and SessionStart stay lightweight and Node-local. The full
  // closed-tree hash is checked by resolveInterpreter immediately before an
  // auxiliary Python command, not on every diagnostic observation.
  return {
    canonicality_claim: manifestRead.manifest.canonicality_claim ?? null,
    closure_sha256: manifestRead.manifest.closure_sha256 ?? null,
    file_count: manifestRead.manifest.file_count ?? null,
    integrity: {
      message:
        "the full runtime closure is verified immediately before auxiliary execution",
      status: "NOT_RUN",
    },
    manifest_present: true,
    manifest_sha256: manifestBytes.ok ? sha256(manifestBytes.bytes) : null,
    python_requirement: manifestRead.manifest.python_requirement ?? null,
    required_third_party: manifestRead.manifest.required_third_party ?? [],
    schema: manifestRead.manifest.schema ?? null,
    scope: manifestRead.manifest.scope ?? null,
    served_retrieval_lanes: manifestRead.manifest.served_retrieval_lanes ?? [],
    source_commit: manifestRead.manifest.source_commit ?? null,
    source_root: manifestRead.manifest.source_root ?? null,
    status: "CONFIGURED_UNVERIFIED",
  };
}

function observeOptionalInterpreter(env = process.env) {
  const configured = env.EFOUNDRY_PYTHON;
  if (typeof configured !== "string" || configured.length === 0) {
    return {
      configured: false,
      error_code: RUNTIME_ERRORS.PYTHON_INTERPRETER_NOT_FOUND,
      execution_probe: "NOT_RUN",
      message:
        "EFOUNDRY_PYTHON is not set; optional Python-dependent commands are unavailable",
      status: "UNAVAILABLE",
    };
  }
  if (!isAbsolute(configured)) {
    return {
      configured: true,
      error_code: RUNTIME_ERRORS.PYTHON_INTERPRETER_NOT_FOUND,
      execution_probe: "NOT_RUN",
      message: "the configured EFOUNDRY_PYTHON value is not an absolute path",
      status: "UNAVAILABLE",
    };
  }
  try {
    if (!statSync(configured).isFile()) {
      throw new Error("the configured path is not a regular file");
    }
  } catch {
    return {
      configured: true,
      error_code: RUNTIME_ERRORS.PYTHON_INTERPRETER_NOT_FOUND,
      execution_probe: "NOT_RUN",
      message: "the configured EFOUNDRY_PYTHON path is not an available regular file",
      status: "UNAVAILABLE",
    };
  }
  return {
    command: configured,
    configured: true,
    execution_probe: "NOT_RUN",
    message:
      "EFOUNDRY_PYTHON is an absolute regular file, but Python 3.12+ and " +
      "dependency compatibility are checked only when an auxiliary command runs",
    status: "CONFIGURED_UNVERIFIED",
  };
}

export function observeWorkspaceRoot(env = process.env) {
  const workspaceId = env.EFOUNDRY_WORKSPACE_ID;
  const configuredRoot = env.EFOUNDRY_WORKSPACE_ROOT;
  if (
    typeof workspaceId !== "string" ||
    workspaceId.length < 3 ||
    workspaceId.length > 128
  ) {
    return {
      message:
        "EFOUNDRY_WORKSPACE_ID must be a string from 3 to 128 characters. " +
        WORKSPACE_CONFIGURATION_REQUIREMENT,
      ok: false,
      path_tools_available: false,
      requirement: WORKSPACE_CONFIGURATION_REQUIREMENT,
      status: "UNCONFIGURED",
      workspace_id: null,
    };
  }
  if (typeof configuredRoot !== "string" || configuredRoot.length === 0) {
    return {
      message:
        "EFOUNDRY_WORKSPACE_ROOT is not configured, so no path may be read or " +
        `written. ${WORKSPACE_CONFIGURATION_REQUIREMENT}`,
      ok: false,
      path_tools_available: false,
      requirement: WORKSPACE_CONFIGURATION_REQUIREMENT,
      status: "UNCONFIGURED",
      workspace_id: workspaceId,
    };
  }
  if (!isAbsolute(configuredRoot)) {
    return {
      message:
        "EFOUNDRY_WORKSPACE_ROOT must be an absolute path. " +
        WORKSPACE_CONFIGURATION_REQUIREMENT,
      ok: false,
      path_tools_available: false,
      requirement: WORKSPACE_CONFIGURATION_REQUIREMENT,
      status: "UNCONFIGURED",
      workspace_id: workspaceId,
    };
  }
  try {
    return {
      ok: true,
      requirement: WORKSPACE_CONFIGURATION_REQUIREMENT,
      root: realpathSync(configuredRoot),
      status: "CONFIGURED",
      workspace_id: workspaceId,
    };
  } catch {
    return {
      message:
        "the configured EFOUNDRY_WORKSPACE_ROOT is unavailable. " +
        WORKSPACE_CONFIGURATION_REQUIREMENT,
      ok: false,
      path_tools_available: false,
      requirement: WORKSPACE_CONFIGURATION_REQUIREMENT,
      status: "UNCONFIGURED",
      workspace_id: workspaceId,
    };
  }
}

function parseMcpCapabilities(value) {
  if (typeof value !== "string" || value.length === 0) {
    return {
      capabilities: EMPTY_CAPABILITIES,
      message:
        "EFOUNDRY_MCP_CAPABILITIES must be a JSON array of unique non-empty strings. " +
        MCP_AUTHORIZATION_CONFIGURATION_REQUIREMENT,
      ok: false,
    };
  }
  let parsed;
  try {
    parsed = JSON.parse(value);
  } catch {
    return {
      capabilities: EMPTY_CAPABILITIES,
      message:
        "EFOUNDRY_MCP_CAPABILITIES is not valid JSON. " +
        MCP_AUTHORIZATION_CONFIGURATION_REQUIREMENT,
      ok: false,
    };
  }
  if (
    !Array.isArray(parsed) ||
    parsed.some(
      (capability) =>
        typeof capability !== "string" || capability.trim().length === 0,
    ) ||
    new Set(parsed).size !== parsed.length
  ) {
    return {
      capabilities: EMPTY_CAPABILITIES,
      message:
        "EFOUNDRY_MCP_CAPABILITIES must be a JSON array of unique non-empty strings. " +
        MCP_AUTHORIZATION_CONFIGURATION_REQUIREMENT,
      ok: false,
    };
  }
  return { capabilities: Object.freeze([...parsed]), ok: true };
}

/**
 * Observe the local MCP identity/capability configuration without treating it
 * as authentication evidence or granting authority from paths.
 */
export function observeMcpAuthorization(env = process.env) {
  const principalId = env.EFOUNDRY_PRINCIPAL_ID;
  const principalConfigured =
    typeof principalId === "string" &&
    principalId.trim().length > 0 &&
    principalId.length <= MAX_PRINCIPAL_ID_LENGTH;
  const capabilityConfiguration = parseMcpCapabilities(
    env.EFOUNDRY_MCP_CAPABILITIES,
  );
  const ok = principalConfigured && capabilityConfiguration.ok;
  const message = !principalConfigured
    ? `EFOUNDRY_PRINCIPAL_ID must be a non-empty string of at most ${MAX_PRINCIPAL_ID_LENGTH} characters. ${MCP_AUTHORIZATION_CONFIGURATION_REQUIREMENT}`
    : !capabilityConfiguration.ok
      ? capabilityConfiguration.message
      : MCP_AUTHORIZATION_CONFIGURATION_NOTICE;
  return Object.freeze({
    capabilities: capabilityConfiguration.capabilities,
    capabilities_configured: capabilityConfiguration.ok,
    map_read_capability_configured:
      capabilityConfiguration.ok &&
      capabilityConfiguration.capabilities.includes(MAP_READ_CAPABILITY),
    message,
    ok,
    principal_configured: principalConfigured,
    principal_id: principalConfigured ? principalId : null,
    requirement: MCP_AUTHORIZATION_CONFIGURATION_REQUIREMENT,
    status: ok ? "CONFIGURED" : "UNCONFIGURED",
  });
}

/**
 * Observe whether this process may bind one map query. The successful state is
 * deliberately CONFIGURED_UNVERIFIED: only the subsequent producer call can
 * observe whether a snapshot is actually available.
 */
export function observeMapQueryBinding({
  authorization,
  env = process.env,
  requestedWorkspaceId,
  workspace,
} = {}) {
  const observedAuthorization = authorization ?? observeMcpAuthorization(env);
  const observedWorkspace = workspace ?? observeWorkspaceRoot(env);
  let reason = null;
  if (!observedAuthorization.principal_configured) {
    reason = observedAuthorization.message;
  } else if (!observedWorkspace.ok) {
    reason = observedWorkspace.message;
  } else if (
    requestedWorkspaceId !== undefined &&
    requestedWorkspaceId !== observedWorkspace.workspace_id
  ) {
    reason =
      "requested workspace_id does not exactly match EFOUNDRY_WORKSPACE_ID";
  } else if (!observedAuthorization.capabilities_configured) {
    reason = observedAuthorization.message;
  } else if (!observedAuthorization.map_read_capability_configured) {
    reason =
      "EFOUNDRY_MCP_CAPABILITIES does not include mcp.read.map; environment paths alone do not establish caller authority";
  }
  return Object.freeze({
    authorization: observedAuthorization,
    ok: reason === null,
    reason: reason ?? MCP_AUTHORIZATION_CONFIGURATION_NOTICE,
    status: reason === null ? "CONFIGURED_UNVERIFIED" : "UNAVAILABLE",
    workspace: observedWorkspace,
  });
}

function toolAvailability({ authorization, workspace } = {}) {
  const mapQuery = observeMapQueryBinding({ authorization, workspace });
  const bound = [...ALWAYS_BOUND_TOOL_NAMES];
  const unbound = { ...ALWAYS_UNBOUND_REASON };
  if (mapQuery.ok) {
    bound.push("foundry.map.query");
  } else {
    unbound["foundry.map.query"] = mapQuery.reason;
  }
  return Object.freeze({
    bound: Object.freeze(bound),
    map_query: mapQuery,
    unbound: Object.freeze(unbound),
  });
}

const DEFAULT_TOOL_AVAILABILITY = toolAvailability();

export const BOUND_TOOL_NAMES = DEFAULT_TOOL_AVAILABILITY.bound;
export const UNBOUND_REASON = DEFAULT_TOOL_AVAILABILITY.unbound;

export function observeRuntime({
  env = process.env,
  root = pluginRoot(import.meta.url),
} = {}) {
  return {
    interpreter: observeOptionalInterpreter(env),
    mcp_authorization: observeMcpAuthorization(env),
    node_runtime: {
      executable: process.execPath,
      status: "READY",
      version: process.version,
    },
    payload: observePluginPayload({ root }),
    python_runtime: observePythonRuntime(root),
    workspace: observeWorkspaceRoot(env),
  };
}

function publicWorkspace(workspace) {
  return {
    requirement: workspace.requirement,
    status: workspace.status,
    ...(typeof workspace.path_tools_available === "boolean"
      ? { path_tools_available: workspace.path_tools_available }
      : {}),
    ...(typeof workspace.message === "string"
      ? { message: workspace.message }
      : {}),
  };
}

function publicMcpAuthorization(authorization) {
  return {
    capabilities_configured: authorization.capabilities_configured,
    map_read_capability_configured:
      authorization.map_read_capability_configured,
    message: authorization.message,
    principal_configured: authorization.principal_configured,
    requirement: authorization.requirement,
    status: authorization.status,
  };
}

function publicInterpreter(interpreter) {
  return {
    configured: interpreter.configured,
    execution_probe: interpreter.execution_probe,
    status: interpreter.status,
    ...(typeof interpreter.error_code === "string"
      ? { error_code: interpreter.error_code }
      : {}),
    ...(typeof interpreter.message === "string"
      ? { message: interpreter.message }
      : {}),
  };
}

function publicNodeRuntime(nodeRuntime) {
  return {
    status: nodeRuntime.status,
    version: nodeRuntime.version,
  };
}

function optionalPythonReady(observation) {
  return (
    observation.interpreter.status === "READY" &&
    observation.python_runtime.status === "READY"
  );
}

function statusDegradationReason(availability) {
  return (
    `PLUGIN_ALPHA implementation is incomplete; exactly ${availability.bound.length} ` +
    `MCP tools are configured as bound (${availability.bound.join(", ")}), while ` +
    "durable FORGE session state and workflow execution are unavailable"
  );
}

function candidateSurfaces(observation, availability) {
  const pythonState = optionalPythonReady(observation)
    ? "READY"
    : observation.interpreter.status === "CONFIGURED_UNVERIFIED" &&
        observation.python_runtime.status === "CONFIGURED_UNVERIFIED"
      ? "CONFIGURED_UNVERIFIED"
      : "UNAVAILABLE";
  const unavailableTools = Object.keys(availability.unbound).sort();
  return {
    cli: {
      node_bound: [...NODE_ONLY_CLI_COMMANDS],
      python_dependent: [...PYTHON_DEPENDENT_CLI_COMMANDS],
      python_dependent_state: pythonState,
    },
    mcp: {
      bound: [...availability.bound],
      bound_count: availability.bound.length,
      unavailable: unavailableTools,
      unavailable_count: unavailableTools.length,
    },
  };
}

export function createStatusProjection({ observation = observeRuntime() } = {}) {
  const availability = toolAvailability({
    authorization: observation.mcp_authorization,
    workspace: observation.workspace,
  });
  const surfaces = candidateSurfaces(observation, availability);
  const runtimeLanes = Array.isArray(observation.python_runtime.served_retrieval_lanes)
    ? observation.python_runtime.served_retrieval_lanes
    : [];
  return {
    data: {
      bound_tool_count: availability.bound.length,
      bound_tools: [...availability.bound],
      candidate_surfaces: surfaces,
      current_qualified_status: QUALIFIED_STATUS,
      full_v4_operational: false,
      implementation_target: IMPLEMENTATION_TARGET,
      implementation_target_status: IMPLEMENTATION_TARGET_STATUS,
      interpreter: publicInterpreter(observation.interpreter),
      mcp_authorization: publicMcpAuthorization(
        availability.map_query.authorization,
      ),
      node_runtime: publicNodeRuntime(observation.node_runtime),
      overall_state: "DEGRADED",
      payload: observation.payload,
      plugin_version: observation.payload.plugin_version,
      qualified_status: QUALIFIED_STATUS,
      release_level: QUALIFIED_STATUS,
      retrieval_lanes: {
        cli_served: optionalPythonReady(observation) ? runtimeLanes : [],
        manifest_declared: runtimeLanes,
        note:
          "retrieval lanes execute only through the optional bundled Python CLI; " +
          "the other eight canonical lanes are declared and return UNSEARCHED",
      },
      runtime: observation.python_runtime,
      runtime_status: "PARTIAL_IMPLEMENTATION",
      unavailable_tool_reasons: { ...availability.unbound },
      unbound_tool_count: Object.keys(availability.unbound).length,
      unbound_tools: Object.keys(availability.unbound).sort(),
      version: observation.payload.plugin_version,
      workspace: publicWorkspace(observation.workspace),
      mcp_authorization_configuration_requirement:
        MCP_AUTHORIZATION_CONFIGURATION_REQUIREMENT,
      workspace_configuration_requirement: WORKSPACE_CONFIGURATION_REQUIREMENT,
    },
    degradationReason: statusDegradationReason(availability),
    state: "DEGRADED",
  };
}

export function createHealthProjection({ observation = observeRuntime() } = {}) {
  const availability = toolAvailability({
    authorization: observation.mcp_authorization,
    workspace: observation.workspace,
  });
  const pythonReady = optionalPythonReady(observation);
  const pythonReason =
    observation.interpreter.status !== "READY"
      ? observation.interpreter.message
      : observation.python_runtime.message;
  return {
    data: {
      components: [
        {
          component: "plugin_payload",
          plugin_version: observation.payload.plugin_version,
          state: observation.payload.status,
          ...(observation.payload.status === "READY"
            ? {}
            : { reason: observation.payload.message }),
        },
        {
          component: "node_runtime",
          state: "READY",
          version: observation.node_runtime.version,
        },
        {
          component: "python_runtime",
          execution_probe: observation.interpreter.execution_probe,
          interpreter_state: observation.interpreter.status,
          optional: true,
          runtime_manifest_state: observation.python_runtime.status,
          state: pythonReady ? "READY" : "UNAVAILABLE",
          ...(pythonReady ? {} : { reason: pythonReason }),
        },
        {
          component: "workspace_map",
          reason: availability.map_query.reason,
          state: availability.map_query.status,
        },
        {
          component: "workflow_execution",
          reason: WORKFLOW_EXECUTION_REASON,
          state: "UNAVAILABLE",
        },
      ],
      current_qualified_status: QUALIFIED_STATUS,
      full_v4_operational: false,
      implementation_target: IMPLEMENTATION_TARGET,
      implementation_target_status: IMPLEMENTATION_TARGET_STATUS,
      overall_state: "DEGRADED",
      qualified_status: QUALIFIED_STATUS,
    },
    degradationReason: statusDegradationReason(availability),
    state: "DEGRADED",
  };
}
