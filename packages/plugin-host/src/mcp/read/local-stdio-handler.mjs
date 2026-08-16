import { types as utilTypes } from "node:util";

import {
  PluginPathResolutionError,
  resolvePluginPaths,
} from "../../paths/path-resolution.mjs";
import {
  LocalStdioBindingError,
  assertLocalStdioBindingRoots,
  loadLocalStdioBinding,
} from "./local-stdio-binding.mjs";
import { PROTOCOL_VERSION, toolDescriptors } from "./mcp-server.mjs";

export const UNBOUND_DIAGNOSTIC_WORKSPACE_ID = "WS-UNBOUND-DIAGNOSTIC";

const READ_MODEL_STATES = new Set([
  "READY",
  "EMPTY_CONFIRMED",
  "DEGRADED",
  "UNAVAILABLE",
]);
const DIAGNOSTIC_TOOLS = new Set(["foundry.status", "foundry.health"]);
const MAP_TOOL = "foundry.map.query";
const SESSION_TOOL = "foundry.session.get";
const TOOL_SPECS = new Map(toolDescriptors().map((descriptor) => [descriptor.name, descriptor]));
const FACTORY_FIELDS = new Set([
  "pluginRoot",
  "pluginData",
  "workspaceRoot",
  "buildWorkspaceMapSnapshot",
  "statusProjection",
  "healthProjection",
  "sessionReadPort",
  "clock",
]);
const SESSION_OUTCOME_FIELDS = new Set(["found", "state", "data", "reason"]);
const RFC3339_PATTERN =
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/u;

class LocalStdioHandlerError extends Error {
  constructor(errorCode, message, details = null) {
    super(message);
    this.name = "LocalStdioHandlerError";
    this.errorCode = errorCode;
    this.details = details;
  }
}

const fail = (errorCode, message, details = null) => {
  throw new LocalStdioHandlerError(errorCode, message, details);
};

const isPlainObject = (value) => {
  if (
    value === null ||
    typeof value !== "object" ||
    Array.isArray(value) ||
    utilTypes.isProxy(value)
  ) {
    return false;
  }
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
};

const readDataProperty = (record, key, errorCode = "INVALID_INPUT") => {
  const descriptor = Object.getOwnPropertyDescriptor(record, key);
  if (descriptor === undefined || !("value" in descriptor)) {
    fail(errorCode, `${key} must be an own data property`);
  }
  return descriptor.value;
};

const assertCanonicalJson = (
  value,
  errorCode = "INTERNAL",
  ancestors = new WeakSet(),
) => {
  if (value === null || typeof value === "boolean" || typeof value === "string") return;
  if (typeof value === "number") {
    if (!Number.isFinite(value) || Object.is(value, -0)) {
      fail(errorCode, "JSON value contains a noncanonical number");
    }
    return;
  }
  if (typeof value !== "object" || utilTypes.isProxy(value)) {
    fail(errorCode, "value is not canonical JSON");
  }
  if (ancestors.has(value)) {
    fail(errorCode, "JSON value contains a cycle");
  }
  ancestors.add(value);
  if (Array.isArray(value)) {
    if (Object.getPrototypeOf(value) !== Array.prototype) {
      fail(errorCode, "JSON array has a custom prototype");
    }
    const allowedKeys = new Set(["length"]);
    for (let index = 0; index < value.length; index += 1) {
      const key = String(index);
      allowedKeys.add(key);
      const descriptor = Object.getOwnPropertyDescriptor(value, key);
      if (descriptor === undefined || !("value" in descriptor)) {
        fail(errorCode, "JSON array contains an accessor or hole");
      }
      assertCanonicalJson(descriptor.value, errorCode, ancestors);
    }
    for (const key of Reflect.ownKeys(value)) {
      if (typeof key !== "string" || !allowedKeys.has(key)) {
        fail(errorCode, "JSON array contains an unexpected field");
      }
    }
  } else {
    if (!isPlainObject(value)) {
      fail(errorCode, "JSON object has a custom prototype");
    }
    for (const key of Reflect.ownKeys(value)) {
      if (typeof key !== "string") {
        fail(errorCode, "JSON object contains a symbol field");
      }
      const descriptor = Object.getOwnPropertyDescriptor(value, key);
      if (descriptor === undefined || !("value" in descriptor)) {
        fail(errorCode, "JSON object contains an accessor");
      }
      assertCanonicalJson(descriptor.value, errorCode, ancestors);
    }
  }
  ancestors.delete(value);
};

const cloneCanonicalJson = (value) => {
  assertCanonicalJson(value);
  return structuredClone(value);
};

const actualJsonType = (value) => {
  if (value === null) return "null";
  if (Array.isArray(value)) return "array";
  if (Number.isInteger(value)) return "integer";
  return typeof value;
};

const validateArguments = (spec, candidate) => {
  if (!isPlainObject(candidate)) {
    fail("INVALID_INPUT", "tool arguments must be a plain object");
  }
  const schema = spec.inputSchema;
  const properties = schema.properties ?? {};
  for (const key of Reflect.ownKeys(candidate)) {
    if (typeof key !== "string" || !Object.hasOwn(properties, key)) {
      fail("INVALID_INPUT", "tool arguments contain an unexpected field");
    }
  }
  for (const required of schema.required ?? []) {
    if (!Object.hasOwn(candidate, required)) {
      fail("INVALID_INPUT", `missing required argument: ${required}`);
    }
  }

  const validated = {};
  for (const key of Object.keys(properties)) {
    if (!Object.hasOwn(candidate, key)) continue;
    const value = readDataProperty(candidate, key);
    assertCanonicalJson(value, "INVALID_INPUT");
    const rule = properties[key];
    if (rule.type !== undefined) {
      const acceptedTypes = Array.isArray(rule.type) ? rule.type : [rule.type];
      const actualType = actualJsonType(value);
      if (
        !acceptedTypes.includes(actualType) &&
        !(actualType === "integer" && acceptedTypes.includes("number"))
      ) {
        fail("INVALID_INPUT", `${key} has the wrong JSON type`);
      }
    }
    if (typeof value === "string") {
      if (rule.minLength !== undefined && value.length < rule.minLength) {
        fail("INVALID_INPUT", `${key} is shorter than the canonical minimum`);
      }
      if (rule.maxLength !== undefined && value.length > rule.maxLength) {
        fail("INVALID_INPUT", `${key} exceeds the canonical maximum`);
      }
      if (rule.pattern !== undefined && !new RegExp(rule.pattern, "u").test(value)) {
        fail("INVALID_INPUT", `${key} does not match the canonical pattern`);
      }
    }
    if (typeof value === "number") {
      if (rule.minimum !== undefined && value < rule.minimum) {
        fail("INVALID_INPUT", `${key} is below the canonical minimum`);
      }
      if (rule.maximum !== undefined && value > rule.maximum) {
        fail("INVALID_INPUT", `${key} exceeds the canonical maximum`);
      }
    }
    if (Array.isArray(rule.enum) && !rule.enum.includes(value)) {
      fail("INVALID_INPUT", `${key} is not a canonical enum value`);
    }
    validated[key] = cloneCanonicalJson(value);
  }
  return Object.freeze(validated);
};

const normalizeClockValue = (value) => {
  const candidate = value instanceof Date ? value.toISOString() : value;
  if (
    typeof candidate !== "string" ||
    !RFC3339_PATTERN.test(candidate) ||
    !Number.isFinite(Date.parse(candidate))
  ) {
    fail("INTERNAL", "local stdio clock returned an invalid timestamp");
  }
  return candidate;
};

const resultEnvelope = ({
  spec,
  requestId,
  workspaceId,
  state,
  data,
  degradationReason,
  generatedAt,
}) => ({
  protocol_version: PROTOCOL_VERSION,
  tool: spec.name,
  request_id: requestId,
  workspace_id: workspaceId,
  read_model_state: state,
  data,
  data_schema_refs: [...(spec.annotations.dataSchemaRefs ?? [])],
  receipts: [],
  degradation_reason: degradationReason,
  generated_at: generatedAt,
});

const errorEnvelope = (spec, requestId, errorCode, message, details = null) => ({
  protocol_version: PROTOCOL_VERSION,
  tool: spec?.name ?? null,
  request_id: typeof requestId === "string" ? requestId : null,
  error_code: errorCode,
  message,
  retryable: errorCode === "INTERNAL",
  details,
});

const failure = (spec, requestId, errorCode, message, details = null) => ({
  envelope: errorEnvelope(spec, requestId, errorCode, message, details),
  isError: true,
});

const outcome = (envelope) => ({ envelope, isError: false });

const safeRuntimeCode = (value) =>
  typeof value === "string" && /^[A-Z][A-Z0-9_]{1,127}$/u.test(value)
    ? value
    : null;

const g03Details = (error) => {
  const code = safeRuntimeCode(error?.code);
  return code === null ? null : { g03_code: code };
};

const bindingDetails = (error) => {
  const code = safeRuntimeCode(error?.code);
  return code === null ? null : { binding_code: code };
};

const isBoundaryChanged = (error) =>
  error instanceof PluginPathResolutionError && error.code === "BOUNDARY_ROOT_CHANGED";

const unavailable = (spec, requestId, workspaceId, generatedAt) =>
  outcome(
    resultEnvelope({
      spec,
      requestId,
      workspaceId,
      state: "UNAVAILABLE",
      data: null,
      degradationReason: `${spec.name} is not bound in LOCAL_STDIO_READ_V1`,
      generatedAt,
    }),
  );

const providerErrorCode = (error) => {
  if (
    error === null ||
    (typeof error !== "object" && typeof error !== "function") ||
    utilTypes.isProxy(error)
  ) {
    return null;
  }
  const descriptor = Object.getOwnPropertyDescriptor(error, "code");
  return descriptor !== undefined &&
    "value" in descriptor &&
    typeof descriptor.value === "string"
    ? descriptor.value
    : null;
};

const normalizeSessionOutcome = (candidate) => {
  if (!isPlainObject(candidate)) {
    fail("INTERNAL", "session read provider returned a noncanonical outcome");
  }
  for (const key of Reflect.ownKeys(candidate)) {
    if (typeof key !== "string" || !SESSION_OUTCOME_FIELDS.has(key)) {
      fail("INTERNAL", "session read outcome contains an unexpected field");
    }
  }
  for (const key of SESSION_OUTCOME_FIELDS) {
    if (!Object.hasOwn(candidate, key)) {
      fail("INTERNAL", `session read outcome is missing ${key}`);
    }
  }

  const found = readDataProperty(candidate, "found", "INTERNAL");
  const state = readDataProperty(candidate, "state", "INTERNAL");
  const data = readDataProperty(candidate, "data", "INTERNAL");
  const reason = readDataProperty(candidate, "reason", "INTERNAL");
  if (typeof found !== "boolean") {
    fail("INTERNAL", "session read outcome found must be boolean");
  }
  if (typeof state !== "string" || !READ_MODEL_STATES.has(state)) {
    fail("INTERNAL", "session read outcome state is not canonical");
  }
  if (data !== null && !isPlainObject(data)) {
    fail("INTERNAL", "session read outcome data must be an object or null");
  }
  if (reason !== null && typeof reason !== "string") {
    fail("INTERNAL", "session read outcome reason must be a string or null");
  }
  if (state === "READY" && (!found || data === null)) {
    fail("INTERNAL", "READY requires found data");
  }
  if (
    state === "EMPTY_CONFIRMED" &&
    (found || data !== null || reason !== null)
  ) {
    fail("INTERNAL", "EMPTY_CONFIRMED requires an absent null result");
  }
  if (state === "DEGRADED" && (reason === null || reason.length === 0)) {
    fail("INTERNAL", "DEGRADED requires a non-empty reason");
  }
  return Object.freeze({
    found,
    state,
    data: data === null ? null : cloneCanonicalJson(data),
    reason,
  });
};

const sessionRead = async ({
  spec,
  args,
  requestId,
  generatedAt,
  binding,
  resolution,
  sessionReadPort,
  sessionFetch,
}) => {
  let candidate;
  let providerFailed = false;
  let providerFailure;
  try {
    candidate = await sessionFetch.call(
      sessionReadPort,
      "read_session",
      binding.workspace_id,
      args,
    );
  } catch (error) {
    providerFailed = true;
    providerFailure = error;
  }

  try {
    assertLocalStdioBindingRoots(binding, resolution);
  } catch (error) {
    return failure(
      spec,
      requestId,
      "WORKSPACE_DENIED",
      "the authenticated workspace boundary changed during the request",
      error instanceof PluginPathResolutionError
        ? g03Details(error)
        : error instanceof LocalStdioBindingError
          ? bindingDetails(error)
          : null,
    );
  }

  if (providerFailed) {
    const code = providerErrorCode(providerFailure);
    if (code === "READ_MODEL_INPUT_INVALID") {
      return failure(
        spec,
        requestId,
        "INVALID_INPUT",
        "the session read provider rejected the canonical input",
      );
    }
    if (code === "READ_MODEL_NOT_FOUND") {
      return failure(
        spec,
        requestId,
        "NOT_FOUND",
        "the resource does not exist in the authorized scope",
      );
    }
    return outcome(
      resultEnvelope({
        spec,
        requestId,
        workspaceId: binding.workspace_id,
        state: "UNAVAILABLE",
        data: null,
        degradationReason: "the session read provider is unavailable",
        generatedAt,
      }),
    );
  }

  let normalized;
  try {
    normalized = normalizeSessionOutcome(candidate);
  } catch (error) {
    if (error instanceof LocalStdioHandlerError) {
      return failure(spec, requestId, error.errorCode, error.message, error.details);
    }
    return failure(
      spec,
      requestId,
      "INTERNAL",
      "session read provider returned an invalid outcome",
    );
  }
  if (!normalized.found && normalized.state === "EMPTY_CONFIRMED") {
    return failure(
      spec,
      requestId,
      "NOT_FOUND",
      "the resource does not exist in the authorized scope",
    );
  }
  return outcome(
    resultEnvelope({
      spec,
      requestId,
      workspaceId: binding.workspace_id,
      state: normalized.state,
      data: normalized.data,
      degradationReason: normalized.reason,
      generatedAt,
    }),
  );
};

const normalizeProjection = (candidate) => {
  if (!isPlainObject(candidate)) {
    fail("INTERNAL", "diagnostic projection must be a plain object");
  }
  const state = readDataProperty(candidate, "state", "INTERNAL");
  const data = readDataProperty(candidate, "data", "INTERNAL");
  const degradationReason = readDataProperty(
    candidate,
    "degradationReason",
    "INTERNAL",
  );
  if (!READ_MODEL_STATES.has(state)) {
    fail("INTERNAL", "diagnostic projection returned an unknown state");
  }
  if (data !== null && !isPlainObject(data)) {
    fail("INTERNAL", "diagnostic projection data must be an object or null");
  }
  if (
    degradationReason !== null &&
    (typeof degradationReason !== "string" || degradationReason.length === 0)
  ) {
    fail("INTERNAL", "diagnostic projection returned an invalid reason");
  }
  if (state === "DEGRADED" && degradationReason === null) {
    fail("INTERNAL", "a degraded diagnostic projection requires a reason");
  }
  return {
    state,
    data: data === null ? null : cloneCanonicalJson(data),
    degradationReason,
  };
};

const diagnostic = async ({
  spec,
  projection,
  args,
  requestId,
  workspaceId,
  generatedAt,
  binding,
  resolution,
  unbound,
}) => {
  let projected;
  if (unbound) {
    projected = {
      state: "DEGRADED",
      data: {
        diagnostic: spec.name,
        local_stdio_binding: "UNBOUND",
      },
      degradationReason: "local stdio binding is unavailable",
    };
  } else {
    try {
      projected = normalizeProjection(
        await projection(
          Object.freeze({
            arguments: args,
            generatedAt,
            principalId: binding.principal_id,
            principalType: binding.principal_type,
            workspaceId,
            workspaceRoot: resolution.workspaceRoot,
            unbound: false,
          }),
        ),
      );
    } catch {
      projected = {
        state: "DEGRADED",
        data: {
          diagnostic: spec.name,
          local_stdio_binding: "AVAILABLE",
        },
        degradationReason: "the Node-local diagnostic projection is degraded",
      };
    }
  }

  if (spec.name === "foundry.health" && args.include_components === false) {
    if (projected.data !== null && Object.hasOwn(projected.data, "components")) {
      const { components: _components, ...withoutComponents } = projected.data;
      projected.data = withoutComponents;
    }
  }
  if (!unbound) {
    try {
      assertLocalStdioBindingRoots(binding, resolution);
    } catch (error) {
      return failure(
        spec,
        requestId,
        "WORKSPACE_DENIED",
        "the authenticated workspace boundary changed during the request",
        error instanceof PluginPathResolutionError
          ? g03Details(error)
          : error instanceof LocalStdioBindingError
            ? bindingDetails(error)
            : null,
      );
    }
  }
  return outcome(
    resultEnvelope({
      spec,
      requestId,
      workspaceId,
      state: unbound ? "DEGRADED" : projected.state,
      data: projected.data,
      degradationReason: unbound
        ? "local stdio binding is unavailable"
        : projected.degradationReason,
      generatedAt,
    }),
  );
};

const mapQuery = async ({
  spec,
  args,
  requestId,
  generatedAt,
  binding,
  resolution,
  buildWorkspaceMapSnapshot,
}) => {
  let snapshot;
  let nodeCount;
  try {
    snapshot = await buildWorkspaceMapSnapshot({
      workspaceRoot: resolution.workspaceRoot,
      workspaceId: binding.workspace_id,
      query: args.query ?? null,
      generatedAt,
      mapId: `MAP-${binding.workspace_id}`.slice(0, 128),
    });
    assertCanonicalJson(snapshot);
    if (!isPlainObject(snapshot)) {
      fail("INTERNAL", "workspace map producer returned a non-object snapshot");
    }
    if (readDataProperty(snapshot, "workspace_id", "INTERNAL") !== binding.workspace_id) {
      fail("INTERNAL", "workspace map producer returned a different workspace");
    }
    const nodes = readDataProperty(snapshot, "nodes", "INTERNAL");
    if (!Array.isArray(nodes)) {
      fail("INTERNAL", "workspace map producer returned invalid nodes");
    }
    nodeCount = nodes.length;
    assertLocalStdioBindingRoots(binding, resolution);
  } catch (error) {
    if (isBoundaryChanged(error)) {
      return failure(
        spec,
        requestId,
        "WORKSPACE_DENIED",
        "a resolved local stdio boundary changed during the request",
        g03Details(error),
      );
    }
    if (error instanceof LocalStdioBindingError) {
      return failure(
        spec,
        requestId,
        "WORKSPACE_DENIED",
        "the authenticated workspace boundary changed during the request",
        bindingDetails(error),
      );
    }
    const code = safeRuntimeCode(error?.code);
    return failure(
      spec,
      requestId,
      "INTERNAL",
      "workspace map scan failed",
      code === null ? null : { map_code: code },
    );
  }

  const limit = args.limit ?? 50;
  const overLimit = nodeCount > limit;
  return outcome(
    resultEnvelope({
      spec,
      requestId,
      workspaceId: binding.workspace_id,
      state: overLimit ? "DEGRADED" : "READY",
      data: cloneCanonicalJson(snapshot),
      degradationReason: overLimit
        ? `the workspace map contains more than the requested limit of ${limit}; the full snapshot is returned`
        : null,
      generatedAt,
    }),
  );
};

/**
 * Create the existing T01 handlerPort shape for one installed local stdio cell.
 *
 * The three paths are location selectors. Authority is loaded from the G03
 * PLUGIN_DATA boundary on every `call`.
 */
export function createLocalStdioHandlerPort(options) {
  if (!isPlainObject(options)) {
    throw new TypeError("local stdio handler options must be a plain object");
  }
  for (const key of Reflect.ownKeys(options)) {
    if (typeof key !== "string" || !FACTORY_FIELDS.has(key)) {
      throw new TypeError("local stdio handler options contain an unexpected field");
    }
  }
  const pluginRoot = readDataProperty(options, "pluginRoot", "INTERNAL");
  const pluginData = readDataProperty(options, "pluginData", "INTERNAL");
  const workspaceRoot = readDataProperty(options, "workspaceRoot", "INTERNAL");
  const buildWorkspaceMapSnapshot = readDataProperty(
    options,
    "buildWorkspaceMapSnapshot",
    "INTERNAL",
  );
  const statusProjection = readDataProperty(options, "statusProjection", "INTERNAL");
  const healthProjection = readDataProperty(options, "healthProjection", "INTERNAL");
  const sessionReadPort = Object.hasOwn(options, "sessionReadPort")
    ? readDataProperty(options, "sessionReadPort", "INTERNAL")
    : null;
  let sessionFetch = null;
  if (sessionReadPort !== null) {
    if (!isPlainObject(sessionReadPort)) {
      throw new TypeError("sessionReadPort must be null or a trusted plain object");
    }
    sessionFetch = readDataProperty(sessionReadPort, "fetch", "INTERNAL");
    if (typeof sessionFetch !== "function") {
      throw new TypeError("sessionReadPort.fetch must be a function");
    }
  }
  const clock = Object.hasOwn(options, "clock")
    ? readDataProperty(options, "clock", "INTERNAL")
    : () => new Date().toISOString();
  if (
    typeof buildWorkspaceMapSnapshot !== "function" ||
    typeof statusProjection !== "function" ||
    typeof healthProjection !== "function" ||
    typeof clock !== "function"
  ) {
    throw new TypeError("local stdio runtime ports must be functions");
  }

  return Object.freeze({
    async call(toolName, args, requestId) {
      const spec = typeof toolName === "string" ? TOOL_SPECS.get(toolName) : undefined;
      if (spec === undefined) {
        return failure(
          null,
          requestId,
          "UNKNOWN_TOOL",
          "the canonical T01 catalog contains no such tool",
        );
      }

      let validated;
      try {
        validated = validateArguments(spec, args);
      } catch (error) {
        if (error instanceof LocalStdioHandlerError) {
          return failure(spec, requestId, error.errorCode, error.message, error.details);
        }
        return failure(spec, requestId, "INVALID_INPUT", "tool arguments are invalid");
      }

      let generatedAt;
      try {
        generatedAt = normalizeClockValue(clock());
      } catch {
        return failure(spec, requestId, "INTERNAL", "local stdio clock failed");
      }

      let resolution;
      let binding;
      try {
        resolution = resolvePluginPaths({ pluginRoot, pluginData, workspaceRoot });
        binding = loadLocalStdioBinding({ resolution, now: generatedAt });
      } catch (error) {
        if (isBoundaryChanged(error)) {
          return failure(
            spec,
            requestId,
            "WORKSPACE_DENIED",
            "a resolved local stdio boundary changed during the request",
            g03Details(error),
          );
        }
        if (DIAGNOSTIC_TOOLS.has(spec.name)) {
          return diagnostic({
            spec,
            projection: spec.name === "foundry.status" ? statusProjection : healthProjection,
            args: validated,
            requestId,
            workspaceId: UNBOUND_DIAGNOSTIC_WORKSPACE_ID,
            generatedAt,
            binding: null,
            resolution: null,
            unbound: true,
          });
        }
        return failure(
          spec,
          requestId,
          "UNAUTHENTICATED",
          "local stdio binding authentication failed",
          error instanceof PluginPathResolutionError
            ? g03Details(error)
            : error instanceof LocalStdioBindingError
              ? bindingDetails(error)
              : null,
        );
      }

      if (validated.workspace_id !== binding.workspace_id) {
        return failure(
          spec,
          requestId,
          "WORKSPACE_DENIED",
          "the requested workspace does not match the authenticated binding",
        );
      }
      if (spec.annotations.sideEffectClass === "DURABLE_PLAN_ARTIFACT") {
        // LocalStdioBinding deliberately cannot express mcp.plan.* authority.
        // These catalog entries stay advertised but do not reach a handler.
        return unavailable(spec, requestId, binding.workspace_id, generatedAt);
      }
      const requiredCapability = spec.annotations.capability;
      if (!binding.capabilities.includes(requiredCapability)) {
        return failure(
          spec,
          requestId,
          "UNAUTHORIZED",
          `principal lacks required capability ${requiredCapability}`,
        );
      }

      if (spec.name === "foundry.status" || spec.name === "foundry.health") {
        return diagnostic({
          spec,
          projection: spec.name === "foundry.status" ? statusProjection : healthProjection,
          args: validated,
          requestId,
          workspaceId: binding.workspace_id,
          generatedAt,
          binding,
          resolution,
          unbound: false,
        });
      }
      if (spec.name === MAP_TOOL) {
        return mapQuery({
          spec,
          args: validated,
          requestId,
          generatedAt,
          binding,
          resolution,
          buildWorkspaceMapSnapshot,
        });
      }
      if (spec.name === SESSION_TOOL && sessionFetch !== null) {
        return sessionRead({
          spec,
          args: validated,
          requestId,
          generatedAt,
          binding,
          resolution,
          sessionReadPort,
          sessionFetch,
        });
      }
      return unavailable(spec, requestId, binding.workspace_id, generatedAt);
    },
  });
}
