import { createHash } from "node:crypto";
import { types as utilTypes } from "node:util";

import {
  HOOK_EVENT_TYPES,
  canonicalizeHookJson,
  sha256HookJson,
} from "../hooks/gateway/hook-gateway.mjs";

export const CAPABILITY_STATES = Object.freeze([
  "SUPPORTED",
  "UNSUPPORTED",
  "UNKNOWN",
  "DISABLED",
  "ERROR",
]);
export const HOST_CAPABILITY_MODES = Object.freeze([
  "FULL",
  "DEGRADED",
  "READ_ONLY",
  "SAFE_MODE",
  "BLOCKED",
]);
export const PLUGIN_HEALTH_STATES = Object.freeze([
  "PASS",
  "DEGRADED",
  "FAIL",
  "SAFE_MODE",
]);

const CAPABILITY_STATE_SET = new Set(CAPABILITY_STATES);
const HOST_MODE_SET = new Set(HOST_CAPABILITY_MODES);
const HEALTH_STATE_SET = new Set(PLUGIN_HEALTH_STATES);
const HOOK_EVENT_SET = new Set(HOOK_EVENT_TYPES);
const HOST_SET = new Set([
  "codex_cli",
  "codex_desktop",
  "chatgpt_work",
  "claude_code",
  "other",
]);
const PROFILE_SET = new Set(["LITE", "RESEARCH", "TEAM", "REGULATED"]);
const HEALTH_CHECK_STATE_SET = new Set(["PASS", "WARN", "FAIL", "NOT_RUN"]);
const DEGRADED_MODE_SET = new Set(["DEGRADED", "READ_ONLY", "SAFE_MODE", "BLOCKED"]);
const SHA256_PATTERN = /^sha256:[0-9a-f]{64}$/u;
const CAPABILITY_NAME_PATTERN = /^[a-z][a-z0-9_]*$/u;
const RFC3339_PATTERN =
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/u;
const MODE_RANK = Object.freeze({
  FULL: 0,
  DEGRADED: 1,
  READ_ONLY: 2,
  SAFE_MODE: 3,
  BLOCKED: 4,
});
const CAPABILITY_STATE_RANK = Object.freeze({
  SUPPORTED: 0,
  UNKNOWN: 1,
  UNSUPPORTED: 2,
  DISABLED: 3,
  ERROR: 4,
});
const TRUST_RESULTS = new WeakSet();

const HOST_REPORT_KEYS = Object.freeze([
  "report_id",
  "host",
  "host_version",
  "plugin_version",
  "detected_at",
  "capabilities",
  "hook_events",
  "unobserved_tool_paths",
  "mode",
  "blockers",
  "report_hash",
]);
const HEALTH_REPORT_KEYS = Object.freeze([
  "health_id",
  "plugin_version",
  "host_capability_report_id",
  "profile",
  "overall",
  "checks",
  "generated_at",
  "report_hash",
]);

export class CapabilityProbeError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "CapabilityProbeError";
    this.code = code;
  }
}

const fail = (code, message) => {
  throw new CapabilityProbeError(code, message);
};

const hasOnlyUnicodeScalars = (value) => {
  for (let index = 0; index < value.length; index += 1) {
    const codeUnit = value.charCodeAt(index);
    if (codeUnit >= 0xd800 && codeUnit <= 0xdbff) {
      const next = value.charCodeAt(index + 1);
      if (!(next >= 0xdc00 && next <= 0xdfff)) return false;
      index += 1;
    } else if (codeUnit >= 0xdc00 && codeUnit <= 0xdfff) {
      return false;
    }
  }
  return true;
};

const requireString = (
  value,
  label,
  { allowEmpty = false, minLength = undefined, maxLength = undefined, code = "INVALID_INPUT" } = {},
) => {
  const length = typeof value === "string" ? [...value].length : undefined;
  if (
    typeof value !== "string" ||
    !hasOnlyUnicodeScalars(value) ||
    (!allowEmpty && length === 0) ||
    (minLength !== undefined && length < minLength) ||
    (maxLength !== undefined && length > maxLength)
  ) {
    fail(code, `${label} must be a canonical Unicode scalar string`);
  }
  return value;
};

const requireEnum = (value, values, label, code = "INVALID_INPUT") => {
  const candidate = requireString(value, label, { code });
  if (!values.has(candidate)) fail(code, `${label} is outside the canonical vocabulary`);
  return candidate;
};

const requireHash = (value, label, code = "INVALID_INPUT") => {
  const candidate = requireString(value, label, { code });
  if (!SHA256_PATTERN.test(candidate)) fail(code, `${label} must be a canonical SHA-256 value`);
  return candidate;
};

const requireDateTime = (value, label, code = "INVALID_INPUT") => {
  const candidate = requireString(value, label, { code });
  if (!RFC3339_PATTERN.test(candidate) || Number.isNaN(Date.parse(candidate))) {
    fail(code, `${label} must be an RFC 3339 date-time`);
  }
  return candidate;
};

const requirePlainDataObject = (
  value,
  label,
  { allowedKeys = undefined, requiredKeys = undefined, code = "INVALID_INPUT" } = {},
) => {
  if (
    value === null ||
    typeof value !== "object" ||
    Array.isArray(value) ||
    utilTypes.isProxy(value)
  ) {
    fail(code, `${label} must be a non-proxy plain data object`);
  }
  const prototype = Object.getPrototypeOf(value);
  if (prototype !== Object.prototype && prototype !== null) {
    fail(code, `${label} must be a plain data object`);
  }

  const allowed = allowedKeys === undefined ? null : new Set(allowedKeys);
  for (const key of Reflect.ownKeys(value)) {
    if (typeof key !== "string" || (allowed !== null && !allowed.has(key))) {
      fail(code, `${label} contains an unsupported field`);
    }
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (
      descriptor === undefined ||
      !descriptor.enumerable ||
      !Object.hasOwn(descriptor, "value")
    ) {
      fail(code, `${label}.${String(key)} must be an enumerable data property`);
    }
  }

  if (requiredKeys !== undefined) {
    for (const key of requiredKeys) {
      if (!Object.hasOwn(value, key)) fail(code, `${label}.${key} is required`);
    }
  }
  return value;
};

const readDataProperty = (record, key) => Object.getOwnPropertyDescriptor(record, key).value;

const readDenseArray = (value, label, code = "INVALID_INPUT") => {
  if (!Array.isArray(value) || utilTypes.isProxy(value)) {
    fail(code, `${label} must be a non-proxy dense array`);
  }
  for (const key of Reflect.ownKeys(value)) {
    if (key === "length") continue;
    if (typeof key !== "string" || !/^(0|[1-9][0-9]*)$/u.test(key)) {
      fail(code, `${label} contains a non-element property`);
    }
    const index = Number(key);
    if (!Number.isSafeInteger(index) || index < 0 || index >= value.length) {
      fail(code, `${label} contains a non-canonical index`);
    }
  }
  const entries = new Array(value.length);
  for (let index = 0; index < value.length; index += 1) {
    const descriptor = Object.getOwnPropertyDescriptor(value, String(index));
    if (
      descriptor === undefined ||
      !descriptor.enumerable ||
      !Object.hasOwn(descriptor, "value")
    ) {
      fail(code, `${label} must not be sparse or accessor-backed`);
    }
    entries[index] = descriptor.value;
  }
  return entries;
};

const requireStringArray = (
  value,
  label,
  { allowEmpty = true, itemValidator = requireString, code = "INVALID_INPUT" } = {},
) => {
  const entries = readDenseArray(value, label, code).map((entry, index) =>
    itemValidator(entry, `${label}[${index}]`, code),
  );
  if (!allowEmpty && entries.length === 0) fail(code, `${label} must not be empty`);
  if (new Set(entries).size !== entries.length) fail(code, `${label} must contain unique values`);
  return entries;
};

const requireCapabilityName = (value, label, code = "INVALID_INPUT") => {
  const candidate = requireString(value, label, { code });
  if (!CAPABILITY_NAME_PATTERN.test(candidate)) {
    fail(code, `${label} must use canonical snake_case capability vocabulary`);
  }
  return candidate;
};

const deepFreeze = (value) => {
  if (value === null || typeof value !== "object" || utilTypes.isProxy(value)) return value;
  for (const key of Reflect.ownKeys(value)) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (descriptor !== undefined && Object.hasOwn(descriptor, "value")) {
      deepFreeze(descriptor.value);
    }
  }
  return Object.freeze(value);
};

const sortedUnique = (values) => [...new Set(values)].sort();

const requireCanonicalSorted = (values, label, comparator = undefined, code = "INVALID_INPUT") => {
  const expected = [...values].sort(comparator);
  if (canonicalizeHookJson(values) !== canonicalizeHookJson(expected)) {
    fail(code, `${label} must use canonical ordering`);
  }
  return values;
};

const normalizeObservation = (candidate, label, code = "INVALID_INPUT") => {
  const record = requirePlainDataObject(candidate, label, {
    allowedKeys: ["state", "evidence", "observedHash", "limitations"],
    requiredKeys: ["state", "evidence"],
    code,
  });
  const normalized = {
    state: requireEnum(
      readDataProperty(record, "state"),
      CAPABILITY_STATE_SET,
      `${label}.state`,
      code,
    ),
    evidence: requireString(readDataProperty(record, "evidence"), `${label}.evidence`, { code }),
    limitations: Object.hasOwn(record, "limitations")
      ? sortedUnique(
        requireStringArray(readDataProperty(record, "limitations"), `${label}.limitations`, { code }),
      )
      : [],
  };
  if (Object.hasOwn(record, "observedHash")) {
    normalized.observed_hash = requireHash(
      readDataProperty(record, "observedHash"),
      `${label}.observedHash`,
      code,
    );
  }
  return normalized;
};

const normalizeReportCapability = (candidate, label, code) => {
  const record = requirePlainDataObject(candidate, label, {
    allowedKeys: ["state", "evidence", "observed_hash", "limitations"],
    requiredKeys: ["state", "evidence"],
    code,
  });
  const normalized = {
    state: requireEnum(readDataProperty(record, "state"), CAPABILITY_STATE_SET, `${label}.state`, code),
    evidence: requireString(readDataProperty(record, "evidence"), `${label}.evidence`, { code }),
  };
  if (Object.hasOwn(record, "observed_hash")) {
    normalized.observed_hash = requireHash(
      readDataProperty(record, "observed_hash"),
      `${label}.observed_hash`,
      code,
    );
  }
  if (Object.hasOwn(record, "limitations")) {
    const limitations = requireStringArray(
      readDataProperty(record, "limitations"),
      `${label}.limitations`,
      { code },
    );
    requireCanonicalSorted(limitations, `${label}.limitations`, undefined, code);
    normalized.limitations = limitations;
  }
  return normalized;
};

const selectMode = (left, right) => (MODE_RANK[right] > MODE_RANK[left] ? right : left);
const selectCapabilityState = (left, right) =>
  CAPABILITY_STATE_RANK[right] > CAPABILITY_STATE_RANK[left] ? right : left;
const compareCanonicalStrings = (left, right) => (left < right ? -1 : left > right ? 1 : 0);

/** Hash the exact installed hook-definition bytes. Text normalization is not applied. */
export const hashHookDefinitionBytes = (bytes) => {
  if (!(bytes instanceof Uint8Array) || utilTypes.isProxy(bytes)) {
    fail("INVALID_INPUT", "hook definition bytes must be a non-proxy Uint8Array");
  }
  return `sha256:${createHash("sha256").update(bytes).digest("hex")}`;
};

/**
 * Compare all active hook hashes with the exact hashes stored in
 * PluginInstallState.trusted_hook_hashes. A changed active hook is never
 * inherited into the trusted set and always requires a new approval action.
 */
export const verifyHookTrust = (candidate) => {
  const request = requirePlainDataObject(candidate, "hook trust request", {
    allowedKeys: ["hookDefinitions", "trustedHookHashes", "hooksEnabled"],
    requiredKeys: ["hookDefinitions", "trustedHookHashes", "hooksEnabled"],
  });
  const definitions = readDenseArray(
    readDataProperty(request, "hookDefinitions"),
    "hookDefinitions",
  ).map((entry, index) => {
    const record = requirePlainDataObject(entry, `hookDefinitions[${index}]`, {
      allowedKeys: ["hookId", "observedHash"],
      requiredKeys: ["hookId", "observedHash"],
    });
    return {
      hookId: requireString(readDataProperty(record, "hookId"), `hookDefinitions[${index}].hookId`),
      observedHash: requireHash(
        readDataProperty(record, "observedHash"),
        `hookDefinitions[${index}].observedHash`,
      ),
    };
  });
  definitions.sort((left, right) => compareCanonicalStrings(left.hookId, right.hookId));
  if (new Set(definitions.map((entry) => entry.hookId)).size !== definitions.length) {
    fail("INVALID_INPUT", "hookDefinitions must have unique hookId values");
  }
  if (new Set(definitions.map((entry) => entry.observedHash)).size !== definitions.length) {
    fail(
      "INVALID_INPUT",
      "hookDefinitions must bind each active hookId to a distinct observedHash",
    );
  }

  const trustedHookHashes = requireStringArray(
    readDataProperty(request, "trustedHookHashes"),
    "trustedHookHashes",
    { itemValidator: requireHash },
  ).sort();
  const hooksEnabled = readDataProperty(request, "hooksEnabled");
  if (typeof hooksEnabled !== "boolean") fail("INVALID_INPUT", "hooksEnabled must be boolean");

  const trusted = new Set(trustedHookHashes);
  const currentHashes = new Set(definitions.map((entry) => entry.observedHash));
  const changedHooks = definitions
    .filter((entry) => !trusted.has(entry.observedHash))
    .map((entry) => entry.hookId);
  const staleTrustedHashes = trustedHookHashes.filter((hash) => !currentHashes.has(hash));
  const retrustRequired = changedHooks.length > 0 || staleTrustedHashes.length > 0;
  const bundleHash = sha256HookJson({
    hooks: definitions.map((entry) => ({
      hook_id: entry.hookId,
      observed_hash: entry.observedHash,
    })),
  });

  let state;
  let evidence;
  const limitations = [];
  if (!hooksEnabled) {
    state = "DISABLED";
    evidence = "Hook execution is explicitly disabled by the observed host configuration.";
    limitations.push("HOOKS_DISABLED");
  } else if (definitions.length === 0) {
    state = "UNSUPPORTED";
    evidence = "No active hook definitions were observed.";
    limitations.push("NO_ACTIVE_HOOK_DEFINITIONS");
  } else if (retrustRequired) {
    state = "UNKNOWN";
    evidence = "The active hook hash set differs from the approved trust set.";
  } else {
    state = "SUPPORTED";
    evidence = "Every active hook hash exactly matches the approved trust set.";
  }
  if (retrustRequired) limitations.push("HOOK_RETRUST_REQUIRED");
  limitations.push(...changedHooks.map((hookId) => `UNTRUSTED_ACTIVE_HOOK:${hookId}`));
  limitations.push(...staleTrustedHashes.map((hash) => `STALE_TRUSTED_HOOK_HASH:${hash}`));

  const result = deepFreeze({
    state,
    evidence,
    observedHash: bundleHash,
    limitations: sortedUnique(limitations),
    currentHookHashes: [...currentHashes].sort(),
    trustedHookHashes,
    changedHooks,
    staleTrustedHashes,
    retrustRequired,
    hooksEnabled,
  });
  TRUST_RESULTS.add(result);
  return result;
};

const normalizeDegradedModes = (candidate, capabilities) => {
  const entries = readDenseArray(candidate, "degradedModes");
  const mappings = new Map();
  for (let index = 0; index < entries.length; index += 1) {
    const record = requirePlainDataObject(entries[index], `degradedModes[${index}]`, {
      allowedKeys: ["missingCapability", "mode", "behavior"],
      requiredKeys: ["missingCapability", "mode", "behavior"],
    });
    const missingCapability = requireCapabilityName(
      readDataProperty(record, "missingCapability"),
      `degradedModes[${index}].missingCapability`,
    );
    if (!capabilities.has(missingCapability)) {
      fail("INVALID_INPUT", "degradedModes may reference only declared capabilities");
    }
    if (mappings.has(missingCapability)) {
      fail("INVALID_INPUT", "degradedModes must have at most one mapping per capability");
    }
    mappings.set(missingCapability, {
      mode: requireEnum(
        readDataProperty(record, "mode"),
        DEGRADED_MODE_SET,
        `degradedModes[${index}].mode`,
      ),
      behavior: requireString(
        readDataProperty(record, "behavior"),
        `degradedModes[${index}].behavior`,
      ),
    });
  }
  return mappings;
};

const normalizeObservedCapabilities = (candidate, declaredCapabilities) => {
  const record = requirePlainDataObject(candidate, "observations");
  const observed = new Map();
  for (const key of Reflect.ownKeys(record)) {
    if (typeof key !== "string") fail("INVALID_INPUT", "observations contains a symbol key");
    requireCapabilityName(key, `observations.${key}`);
    if (!declaredCapabilities.has(key)) {
      fail("UNDECLARED_CAPABILITY", `observation ${key} is not declared by the capability manifest`);
    }
    observed.set(
      key,
      normalizeObservation(readDataProperty(record, key), `observations.${key}`),
    );
  }
  return observed;
};

const eventOrder = (left, right) => HOOK_EVENT_TYPES.indexOf(left) - HOOK_EVENT_TYPES.indexOf(right);

/**
 * Produce a canonical HostCapabilityReport from bounded observations. Missing
 * observations become UNKNOWN, profile names confer no capability, and a
 * verifier-issued hook trust result constrains the plugin_hooks claim.
 */
export const probeHostCapabilities = (candidate) => {
  const request = requirePlainDataObject(candidate, "capability probe request", {
    allowedKeys: [
      "reportId",
      "host",
      "hostVersion",
      "pluginVersion",
      "detectedAt",
      "requiredCapabilities",
      "optionalCapabilities",
      "degradedModes",
      "observations",
      "hookTrust",
      "declaredHookEvents",
      "observedHookEvents",
      "knownToolPaths",
      "observedToolPaths",
    ],
    requiredKeys: [
      "reportId",
      "host",
      "hostVersion",
      "pluginVersion",
      "detectedAt",
      "requiredCapabilities",
      "optionalCapabilities",
      "degradedModes",
      "observations",
      "hookTrust",
      "declaredHookEvents",
      "observedHookEvents",
      "knownToolPaths",
      "observedToolPaths",
    ],
  });

  const requiredCapabilities = requireStringArray(
    readDataProperty(request, "requiredCapabilities"),
    "requiredCapabilities",
    { allowEmpty: false, itemValidator: requireCapabilityName },
  );
  const optionalCapabilities = requireStringArray(
    readDataProperty(request, "optionalCapabilities"),
    "optionalCapabilities",
    { itemValidator: requireCapabilityName },
  );
  const declaredNames = new Set([...requiredCapabilities, ...optionalCapabilities]);
  if (declaredNames.size !== requiredCapabilities.length + optionalCapabilities.length) {
    fail("INVALID_INPUT", "requiredCapabilities and optionalCapabilities must be disjoint");
  }
  if (!declaredNames.has("plugin_hooks")) {
    fail("INVALID_INPUT", "the H04 hook probe requires the declared plugin_hooks capability");
  }

  const hookTrust = readDataProperty(request, "hookTrust");
  if (!TRUST_RESULTS.has(hookTrust)) {
    fail("UNVERIFIED_HOOK_TRUST", "hookTrust must be issued by verifyHookTrust");
  }
  const degradedModes = normalizeDegradedModes(
    readDataProperty(request, "degradedModes"),
    declaredNames,
  );
  const observations = normalizeObservedCapabilities(
    readDataProperty(request, "observations"),
    declaredNames,
  );

  const declaredHookEvents = requireStringArray(
    readDataProperty(request, "declaredHookEvents"),
    "declaredHookEvents",
    { itemValidator: (value, label, code) => requireEnum(value, HOOK_EVENT_SET, label, code) },
  ).sort(eventOrder);
  const observedHookEvents = requireStringArray(
    readDataProperty(request, "observedHookEvents"),
    "observedHookEvents",
    { itemValidator: (value, label, code) => requireEnum(value, HOOK_EVENT_SET, label, code) },
  ).sort(eventOrder);
  const declaredEventSet = new Set(declaredHookEvents);
  for (const event of observedHookEvents) {
    if (!declaredEventSet.has(event)) {
      fail("UNDECLARED_HOOK_EVENT", "observedHookEvents contains an undeclared event");
    }
  }
  const observedEventSet = new Set(observedHookEvents);
  const missingHookEvents = declaredHookEvents.filter((event) => !observedEventSet.has(event));

  const knownToolPaths = requireStringArray(
    readDataProperty(request, "knownToolPaths"),
    "knownToolPaths",
  ).sort();
  const observedToolPaths = requireStringArray(
    readDataProperty(request, "observedToolPaths"),
    "observedToolPaths",
  ).sort();
  const knownToolPathSet = new Set(knownToolPaths);
  for (const toolPath of observedToolPaths) {
    if (!knownToolPathSet.has(toolPath)) {
      fail("UNDECLARED_TOOL_PATH", "observedToolPaths contains a path outside the bounded probe set");
    }
  }
  const observedToolPathSet = new Set(observedToolPaths);
  const unobservedToolPaths = knownToolPaths.filter((path) => !observedToolPathSet.has(path));

  const capabilities = new Map();
  for (const name of [...declaredNames].sort()) {
    const observation = observations.get(name) ?? {
      state: "UNKNOWN",
      evidence: "No bounded capability observation was recorded.",
      limitations: ["CAPABILITY_OBSERVATION_MISSING"],
    };
    capabilities.set(name, { ...observation, limitations: [...observation.limitations] });
  }

  const pluginHooks = capabilities.get("plugin_hooks");
  if (hookTrust.state !== "SUPPORTED") {
    const priorState = pluginHooks.state;
    pluginHooks.state = selectCapabilityState(pluginHooks.state, hookTrust.state);
    if (pluginHooks.state !== priorState) pluginHooks.evidence = hookTrust.evidence;
  }
  pluginHooks.observed_hash = hookTrust.observedHash;
  pluginHooks.limitations.push(...hookTrust.limitations);

  if (declaredHookEvents.length === 0) {
    if (pluginHooks.state === "SUPPORTED") {
      pluginHooks.state = "UNKNOWN";
      pluginHooks.evidence = "The bounded hook event coverage scope is empty.";
    }
    pluginHooks.limitations.push("HOOK_EVENT_COVERAGE_SCOPE_EMPTY");
  }

  if (knownToolPaths.length === 0) {
    const coverageName = declaredNames.has("hosted_tool_hooks")
      ? "hosted_tool_hooks"
      : "plugin_hooks";
    const coverageCapability = capabilities.get(coverageName);
    if (coverageCapability.state === "SUPPORTED") {
      coverageCapability.state = "UNKNOWN";
      coverageCapability.evidence = "The bounded tool-path coverage scope is empty.";
    }
    coverageCapability.limitations.push("TOOL_COVERAGE_SCOPE_EMPTY");
  }

  if (missingHookEvents.length > 0) {
    if (pluginHooks.state === "SUPPORTED") {
      pluginHooks.state = "UNKNOWN";
      pluginHooks.evidence = "Declared hook event coverage is incomplete.";
    }
    pluginHooks.limitations.push(
      ...missingHookEvents.map((event) => `UNOBSERVED_HOOK_EVENT:${event}`),
    );
  }

  if (unobservedToolPaths.length > 0) {
    const coverageName = declaredNames.has("hosted_tool_hooks")
      ? "hosted_tool_hooks"
      : "plugin_hooks";
    const coverageCapability = capabilities.get(coverageName);
    if (coverageCapability.state === "SUPPORTED") {
      coverageCapability.state = "UNKNOWN";
      coverageCapability.evidence = "One or more bounded tool paths are not hook-observable.";
    }
    coverageCapability.limitations.push(
      ...unobservedToolPaths.map((toolPath) => `UNOBSERVED_TOOL_PATH:${toolPath}`),
    );
  }

  let mode = "FULL";
  const blockers = [];
  for (const name of [...declaredNames].sort()) {
    const capability = capabilities.get(name);
    capability.limitations = sortedUnique(capability.limitations);
    if (capability.state === "SUPPORTED") continue;
    const degradedMode = degradedModes.get(name);
    if (degradedMode === undefined) {
      mode = "BLOCKED";
      capability.limitations.push("DEGRADED_MODE_CONTRACT_MISSING");
      capability.limitations = sortedUnique(capability.limitations);
      blockers.push(`DEGRADED_MODE_UNDECLARED:${name}`);
      continue;
    }
    mode = selectMode(mode, degradedMode.mode);
    capability.limitations.push(`DEGRADED_BEHAVIOR:${degradedMode.behavior}`);
    capability.limitations = sortedUnique(capability.limitations);
    if (degradedMode.mode === "BLOCKED") blockers.push(`CAPABILITY_BLOCKED:${name}`);
  }

  const capabilityObject = {};
  for (const name of [...capabilities.keys()].sort()) {
    capabilityObject[name] = capabilities.get(name);
  }
  const preimage = {
    report_id: requireString(readDataProperty(request, "reportId"), "reportId", {
      minLength: 3,
      maxLength: 128,
    }),
    host: requireEnum(readDataProperty(request, "host"), HOST_SET, "host"),
    host_version: requireString(readDataProperty(request, "hostVersion"), "hostVersion", {
      allowEmpty: true,
    }),
    plugin_version: requireString(readDataProperty(request, "pluginVersion"), "pluginVersion", {
      allowEmpty: true,
    }),
    detected_at: requireDateTime(readDataProperty(request, "detectedAt"), "detectedAt"),
    capabilities: capabilityObject,
    hook_events: observedHookEvents,
    unobserved_tool_paths: unobservedToolPaths,
    mode,
    blockers: sortedUnique(blockers),
  };
  return validateHostCapabilityReport({
    ...preimage,
    report_hash: sha256HookJson(preimage),
  });
};

export const validateHostCapabilityReport = (candidate) => {
  const code = "HOST_CAPABILITY_REPORT_INVALID";
  const record = requirePlainDataObject(candidate, "HostCapabilityReport", {
    allowedKeys: HOST_REPORT_KEYS,
    requiredKeys: HOST_REPORT_KEYS,
    code,
  });
  const rawCapabilities = requirePlainDataObject(
    readDataProperty(record, "capabilities"),
    "HostCapabilityReport.capabilities",
    { code },
  );
  const capabilityNames = Reflect.ownKeys(rawCapabilities);
  if (capabilityNames.length === 0 || capabilityNames.some((key) => typeof key !== "string")) {
    fail(code, "HostCapabilityReport.capabilities must contain named entries");
  }
  const capabilities = {};
  for (const name of capabilityNames.sort()) {
    requireCapabilityName(name, `HostCapabilityReport.capabilities.${name}`, code);
    capabilities[name] = normalizeReportCapability(
      readDataProperty(rawCapabilities, name),
      `HostCapabilityReport.capabilities.${name}`,
      code,
    );
  }
  const hookEvents = requireStringArray(
    readDataProperty(record, "hook_events"),
    "HostCapabilityReport.hook_events",
    { code, itemValidator: (value, label) => requireEnum(value, HOOK_EVENT_SET, label, code) },
  );
  requireCanonicalSorted(hookEvents, "HostCapabilityReport.hook_events", eventOrder, code);
  const unobservedToolPaths = requireStringArray(
    readDataProperty(record, "unobserved_tool_paths"),
    "HostCapabilityReport.unobserved_tool_paths",
    { code },
  );
  requireCanonicalSorted(unobservedToolPaths, "HostCapabilityReport.unobserved_tool_paths", undefined, code);
  const blockers = requireStringArray(
    readDataProperty(record, "blockers"),
    "HostCapabilityReport.blockers",
    { code },
  );
  requireCanonicalSorted(blockers, "HostCapabilityReport.blockers", undefined, code);

  const preimage = {
    report_id: requireString(readDataProperty(record, "report_id"), "report_id", {
      minLength: 3,
      maxLength: 128,
      code,
    }),
    host: requireEnum(readDataProperty(record, "host"), HOST_SET, "host", code),
    host_version: requireString(readDataProperty(record, "host_version"), "host_version", {
      allowEmpty: true,
      code,
    }),
    plugin_version: requireString(readDataProperty(record, "plugin_version"), "plugin_version", {
      allowEmpty: true,
      code,
    }),
    detected_at: requireDateTime(readDataProperty(record, "detected_at"), "detected_at", code),
    capabilities,
    hook_events: hookEvents,
    unobserved_tool_paths: unobservedToolPaths,
    mode: requireEnum(readDataProperty(record, "mode"), HOST_MODE_SET, "mode", code),
    blockers,
  };
  const observedHash = requireHash(readDataProperty(record, "report_hash"), "report_hash", code);
  if (observedHash !== sha256HookJson(preimage)) {
    fail("HOST_CAPABILITY_REPORT_HASH_MISMATCH", "HostCapabilityReport hash does not match");
  }
  if (
    preimage.mode === "FULL" &&
    (blockers.length > 0 || Object.values(capabilities).some(({ state }) => state !== "SUPPORTED"))
  ) {
    fail(code, "HostCapabilityReport mode FULL requires supported capabilities and no blockers");
  }
  return deepFreeze({ ...preimage, report_hash: observedHash });
};

const healthOverallForMode = (mode) => {
  if (mode === "FULL") return "PASS";
  if (mode === "SAFE_MODE") return "SAFE_MODE";
  if (mode === "BLOCKED") return "FAIL";
  return "DEGRADED";
};

/** Build the canonical health projection without advertising unavailable features. */
export const buildPluginHealthReport = (candidate) => {
  const request = requirePlainDataObject(candidate, "plugin health request", {
    allowedKeys: ["healthId", "profile", "generatedAt", "capabilityReport"],
    requiredKeys: ["healthId", "profile", "generatedAt", "capabilityReport"],
  });
  const capabilityReport = validateHostCapabilityReport(
    readDataProperty(request, "capabilityReport"),
  );
  const checks = [];
  for (const name of Object.keys(capabilityReport.capabilities).sort()) {
    const capability = capabilityReport.capabilities[name];
    const status = capability.state === "SUPPORTED"
      ? "PASS"
      : capabilityReport.mode === "BLOCKED" ||
          capabilityReport.mode === "SAFE_MODE" ||
          capability.state === "ERROR"
        ? "FAIL"
        : "WARN";
    checks.push({
      check_id: `capability.${name}`,
      status,
      details: `${name}=${capability.state}: ${capability.evidence}`,
      remediation: capability.state === "SUPPORTED"
        ? []
        : capability.limitations ?? ["Consult the capability manifest before continuing."],
    });
  }
  if (capabilityReport.unobserved_tool_paths.length > 0) {
    checks.push({
      check_id: "hooks.coverage",
      status: "WARN",
      details: `Unobserved tool paths: ${capabilityReport.unobserved_tool_paths.join(", ")}`,
      remediation: ["Use explicit skill/CLI and kernel gates for unobserved paths."],
    });
  }
  const pluginHooks = capabilityReport.capabilities.plugin_hooks;
  if (pluginHooks?.limitations?.includes("HOOK_RETRUST_REQUIRED")) {
    checks.push({
      check_id: "hooks.trust",
      status: "WARN",
      details: "Changed active hook definitions are not trusted.",
      remediation: ["Approve the exact current hook hashes before enabling hook enforcement."],
    });
  }
  checks.sort((left, right) => compareCanonicalStrings(left.check_id, right.check_id));

  const preimage = {
    health_id: requireString(readDataProperty(request, "healthId"), "healthId", {
      minLength: 3,
      maxLength: 128,
    }),
    plugin_version: capabilityReport.plugin_version,
    host_capability_report_id: capabilityReport.report_id,
    profile: requireEnum(readDataProperty(request, "profile"), PROFILE_SET, "profile"),
    overall: healthOverallForMode(capabilityReport.mode),
    checks,
    generated_at: requireDateTime(readDataProperty(request, "generatedAt"), "generatedAt"),
  };
  return validatePluginHealthReport({
    ...preimage,
    report_hash: sha256HookJson(preimage),
  });
};

export const validatePluginHealthReport = (candidate) => {
  const code = "PLUGIN_HEALTH_REPORT_INVALID";
  const record = requirePlainDataObject(candidate, "PluginHealthReport", {
    allowedKeys: HEALTH_REPORT_KEYS,
    requiredKeys: HEALTH_REPORT_KEYS,
    code,
  });
  const rawChecks = readDenseArray(readDataProperty(record, "checks"), "PluginHealthReport.checks", code);
  if (rawChecks.length === 0) fail(code, "PluginHealthReport.checks must not be empty");
  const checks = rawChecks.map((candidateCheck, index) => {
    const check = requirePlainDataObject(candidateCheck, `PluginHealthReport.checks[${index}]`, {
      allowedKeys: ["check_id", "status", "details", "remediation"],
      requiredKeys: ["check_id", "status", "details", "remediation"],
      code,
    });
    const remediation = requireStringArray(
      readDataProperty(check, "remediation"),
      `PluginHealthReport.checks[${index}].remediation`,
      { code },
    );
    return {
      check_id: requireString(
        readDataProperty(check, "check_id"),
        `PluginHealthReport.checks[${index}].check_id`,
        { code },
      ),
      status: requireEnum(
        readDataProperty(check, "status"),
        HEALTH_CHECK_STATE_SET,
        `PluginHealthReport.checks[${index}].status`,
        code,
      ),
      details: requireString(
        readDataProperty(check, "details"),
        `PluginHealthReport.checks[${index}].details`,
        { code },
      ),
      remediation,
    };
  });
  if (new Set(checks.map((check) => check.check_id)).size !== checks.length) {
    fail(code, "PluginHealthReport.checks must have unique check_id values");
  }
  requireCanonicalSorted(
    checks.map((check) => check.check_id),
    "PluginHealthReport.checks",
    undefined,
    code,
  );

  const preimage = {
    health_id: requireString(readDataProperty(record, "health_id"), "health_id", {
      minLength: 3,
      maxLength: 128,
      code,
    }),
    plugin_version: requireString(readDataProperty(record, "plugin_version"), "plugin_version", {
      allowEmpty: true,
      code,
    }),
    host_capability_report_id: requireString(
      readDataProperty(record, "host_capability_report_id"),
      "host_capability_report_id",
      { minLength: 3, maxLength: 128, code },
    ),
    profile: requireEnum(readDataProperty(record, "profile"), PROFILE_SET, "profile", code),
    overall: requireEnum(readDataProperty(record, "overall"), HEALTH_STATE_SET, "overall", code),
    checks,
    generated_at: requireDateTime(readDataProperty(record, "generated_at"), "generated_at", code),
  };
  const observedHash = requireHash(readDataProperty(record, "report_hash"), "report_hash", code);
  if (observedHash !== sha256HookJson(preimage)) {
    fail("PLUGIN_HEALTH_REPORT_HASH_MISMATCH", "PluginHealthReport hash does not match");
  }
  return deepFreeze({ ...preimage, report_hash: observedHash });
};
