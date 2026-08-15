// H06 — hook-disabled and hosted-tool degraded-mode integration gate.
//
// H05 publishes what the plugin's observability registrations *could* observe if
// every declared host ran every declared hook.  A real host often does not: a
// user or policy turns hooks off, and hosted tools execute inside the host where
// a local hook never runs.  H06 is the gate that stands between those two facts
// and any claim of hook-verified provenance.
//
// Nothing here detects degradation.  Degradation is *declared* by the host, as a
// sealed H04 HostCapabilityReport plus the bounded tool-path sets that report was
// built from.  This module refuses to interpret an absent declaration as good
// news, and refuses every claim that outruns the declaration it was given.
//
// Four honesty rules drive every refusal below.
//
//   1. A gateway host the observability registrations claim to observe must have
//      a declared host state.  Silence is not evidence that hooks are enabled.
//   2. The degraded coverage report never claims more than the enabled set.
//      Every host/event pair whose observation is withdrawn is named, and a
//      caller presenting H05's full-coverage report while hooks are disabled is
//      refused rather than quietly re-scoped.
//   3. A hosted-tool action that bypasses local hooks can never carry
//      hook-verified provenance, and the actions it covers are published as an
//      explicit unverified list rather than omitted.
//   4. Coming back from degraded mode requires re-registration evidence that
//      H04's own hook-trust verifier accepts and that binds to the exact hook
//      bundle the new host report was probed with.  Re-enablement is never
//      assumed from a fresh report alone.
//
// The module owns no canonical or persistent state, holds no clock, and reads
// no environment: every timestamp arrives inside a caller-supplied host report,
// and every hash is re-derivable with the sealed gateway's canonical-JSON
// digest.  An ephemeral private binding keeps the complete canonical verified
// state attached to the exact gate context that exposed its compatibility
// snapshot.

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  CAPABILITY_STATES,
  HOST_CAPABILITY_MODES,
  validateHostCapabilityReport,
  verifyHookTrust,
} from "../../../../packages/plugin-host/src/capability-probe/capability-probe.mjs";
import {
  HOOK_COVERAGE,
  HOOK_EVENT_TYPES,
  HOOK_HOSTS,
  sha256HookJson,
} from "../../../../packages/plugin-host/src/hooks/gateway/hook-gateway.mjs";
import {
  coverageReport,
  DECLARING_SOURCES as OBSERVABILITY_DECLARING_SOURCES,
  loadObservability,
  observabilityReceipt,
} from "../v4_h05/index.mjs";

/** Repository root, resolved from this file rather than the process cwd. */
export const REPOSITORY_ROOT = fileURLToPath(new URL("../../../../", import.meta.url));

export const POLICY_PATH =
  "plugin_blueprint/epistemic-foundry/hooks/v4_h06/degraded-mode-policy.json";

/**
 * The declaring sources this gate binds: everything H05 already binds, plus the
 * degraded-mode policy that maps host reports onto the gateway host vocabulary.
 */
export const DECLARING_SOURCES = Object.freeze(
  [...OBSERVABILITY_DECLARING_SOURCES, POLICY_PATH].sort(),
);

/** Why an action carries no hook-verified provenance. */
export const UNVERIFIED_REASONS = Object.freeze({
  HOOKS_DISABLED:
    "the declared host state reports that hooks do not run for this gateway host, so no action on it carries hook-verified provenance however the workflow describes it",
  HOSTED_TOOL_BYPASS:
    "the action runs on a hosted tool path the host declares as bypassing local hooks, so a local hook can neither observe the action nor attest that it happened",
  UNOBSERVED_TOOL_PATH:
    "the host capability report lists this tool path among the bounded paths its probe never observed, so actions on it are unverified even while hooks are enabled",
});

/** Every way this gate refuses, and why that refusal exists. */
export const FINDING_CODES = Object.freeze({
  CAPABILITY_STATE_UNDECLARED:
    "the policy named a host capability state the sealed capability probe does not declare, so a mistyped state would silently decide whether hooks count as enabled",
  COVERAGE_RANK_AMBIGUOUS:
    "the observability coverage rank does not order the gateway coverage vocabulary into one least, one intermediate and one greatest disposition, so a degraded disposition cannot be derived rather than invented",
  COVERAGE_UNDECLARED:
    "a coverage disposition offered by a claim or a workflow step is not the vocabulary the sealed hook gateway declares, so it would be compared against nothing",
  DECLARATION_NONCANONICAL:
    "a declared list is not in canonical form (sorted, unique, exactly the declared fields), so two equal declarations could produce different receipts",
  DECLARATION_UNREADABLE:
    "a runtime declaration, claim, step or recovery record is not the exact object this gate requires, so the gate would be reasoning about a shape nobody agreed on",
  DEGRADATION_UNDECLARED:
    "a host report claims a full operating mode while a capability it declares is outside the enabled set, so the report asserts undegraded operation it cannot support",
  DEGRADED_OVERCLAIMED:
    "a coverage claim or workflow step asserted more observation than the enabled host set supports, which would let a disabled hook or a bypassed hosted tool be read as verified",
  DEGRADED_UNDERSTATED:
    "a coverage claim asserted less observation than the enabled host set supports, which hides observation that actually happens and makes the degraded report unfalsifiable",
  ENABLED_STATE_SET_VACUOUS:
    "the policy's enabled capability states are empty or cover the whole capability vocabulary, so hook availability would be decided by a test that can never fail",
  EVENT_TYPE_UNDECLARED:
    "a workflow step named an event type the sealed hook gateway does not declare, so it claims provenance for an event that cannot arrive",
  HOOK_CAPABILITY_ABSENT:
    "the declared host state carries no observation of the hook capability the policy names, so whether hooks run on that host is unknown and must not be assumed",
  HOSTED_TOOL_ACTIONS_UNNAMED:
    "a host declares its hosted-tool capability as not enabled while naming no hosted tool path, so the bypassed actions would be degraded silently instead of listed",
  HOSTED_TOOL_OBSERVATION_CONTRADICTED:
    "a tool path is declared as bypassing local hooks while the same host report lists it as observed, so the two halves of the declaration cannot both be true",
  HOSTED_TOOL_PROVENANCE_CLAIMED:
    "a workflow step claimed hook-verified provenance for an action on a tool path this gate holds as unverified, which is the exact claim hosted-tool bypass makes impossible",
  HOST_BINDING_INCOMPLETE:
    "the policy host bindings do not reach every host the sealed hook gateway declares, so some gateway host could never be described by any host capability report",
  HOST_BINDING_UNDECLARED:
    "a host capability report names a host the policy binds to no gateway host, so its degradation could not be attributed to any observability claim",
  HOST_STATE_DUPLICATED:
    "two declared host states bind to the same gateway host, so that host's hook availability would have two answers and no single owner",
  HOST_STATE_MISSING:
    "a gateway host the observability registrations claim to observe has no declared host state, and an absent declaration is not evidence that hooks are enabled",
  HOST_UNDECLARED:
    "a policy binding, workflow step or recovery record named a host the sealed hook gateway does not declare, so it refers to a host that can deliver no events",
  MODE_PARTITION_INCOMPLETE:
    "the full and degraded mode sets are not an exact partition of the capability probe mode vocabulary, so a new host mode would be classified by nobody",
  MODE_UNDECLARED:
    "the policy named an operating mode the sealed capability probe does not declare, so a mistyped mode would silently escape the degraded-mode classification",
  POLICY_UNREADABLE:
    "the degraded-mode policy could not be read as the object this gate requires, so the binding between host reports and gateway hosts is unavailable",
  RECEIPT_REJECTED:
    "a prior degraded-mode receipt did not re-derive its own hash or belongs to another policy, so what it claims about earlier hook availability is not evidence",
  RECOVERY_COVERAGE_UNRESTORED:
    "a recovery presented a host report whose hook capability is still outside the enabled set, so re-enabled coverage would be claimed while the host still cannot deliver events",
  RECOVERY_EVIDENCE_MISMATCHED:
    "the re-registration evidence binds a different hook bundle than the one the new host report was probed with, so the approved hooks and the running hooks are not the same hooks",
  RECOVERY_EVIDENCE_MISSING:
    "a host moved from hook-disabled to hook-enabled without re-registration evidence that the sealed hook-trust verifier accepts, so recovery would be assumed rather than shown",
  RECOVERY_HOST_NOT_DISABLED:
    "recovery was offered for a gateway host the prior receipt does not hold as hook-disabled, so the transition it claims to complete never started",
  RECOVERY_RETRUST_REQUIRED:
    "the re-registration evidence contains an active hook hash outside the approved trust set, so re-enabling hooks would inherit trust that was never granted",
  RECOVERY_UNCHANGED_REPORT:
    "recovery re-presented the same host capability report the disabled state was derived from, so nothing was re-probed and the transition rests on the old evidence",
  REPORT_REJECTED:
    "a declared host capability report did not survive revalidation by the sealed capability probe, so it is not evidence of any host state and must not be gated on",
  TOOL_PATH_UNDECLARED:
    "a tool path was used outside the bounded tool-path set its host declares, so the gate would be judging provenance for an action nobody scoped",
});

export class DegradedModeError extends Error {
  constructor(code, message, context = {}) {
    super(message);
    this.name = "DegradedModeError";
    this.code = code;
    this.context = context;
  }
}

const fail = (code, message, context = {}) => {
  throw new DegradedModeError(code, message, context);
};

const POLICY_FIELDS = Object.freeze([
  "degraded_modes",
  "enabled_capability_states",
  "full_modes",
  "hook_capability_name",
  "host_bindings",
  "hosted_tool_capability_name",
  "policy_id",
  "policy_version",
]);
const BINDING_FIELDS = Object.freeze(["capability_report_host", "gateway_host"]);
const HOST_STATE_FIELDS = Object.freeze([
  "capability_report",
  "hosted_tool_paths",
  "tool_paths",
]);
const CLAIM_FIELDS = Object.freeze(["coverage_by_event_type", "not_observed"]);
const STEP_FIELDS = Object.freeze([
  "claimed_coverage",
  "event_type",
  "gateway_host",
  "step_id",
  "tool_path",
]);
const RECOVERY_FIELDS = Object.freeze([
  "gateway_host",
  "hook_definitions",
  "hooks_enabled",
  "trusted_hook_hashes",
]);
const RECEIPT_FIELDS = Object.freeze([
  "capability_vocabulary",
  "coverage_by_event_type",
  "declaring_sources",
  "full_coverage_by_event_type",
  "gateway_vocabulary",
  "hook_disabled_hosts",
  "hook_enabled_hosts",
  "host_states",
  "not_observed",
  "observability_receipt_hash",
  "observed_pair_count",
  "policy_id",
  "policy_version",
  "receipt_hash",
  "receipt_id",
  "recoveries",
  "unverified_actions",
  "withdrawn_pairs",
]);

const CAPABILITY_STATE_SET = new Set(CAPABILITY_STATES);
const MODE_SET = new Set(HOST_CAPABILITY_MODES);
const HOST_SET = new Set(HOOK_HOSTS);
const EVENT_TYPE_SET = new Set(HOOK_EVENT_TYPES);
const COVERAGE_SET = new Set(HOOK_COVERAGE);

// Public values are compatibility snapshots.  Only this module-private state is
// authoritative, and the WeakMap key brands the exact object returned by
// openDegradedGate rather than any forged or cloned lookalike.
const VERIFIED_GATE_STATE_BY_CONTEXT = new WeakMap();

const requireVerifiedGateState = (gate, context = {}) => {
  const state = VERIFIED_GATE_STATE_BY_CONTEXT.get(gate);
  if (state === undefined) {
    fail(
      "DECLARATION_UNREADABLE",
      "the gate context was not returned by this openDegradedGate instance",
      context,
    );
  }
  return state;
};

const isPlainObject = (value) =>
  value !== null && typeof value === "object" && !Array.isArray(value);

const deepFreeze = (value) => {
  if (value === null || typeof value !== "object") return value;
  for (const key of Reflect.ownKeys(value)) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (descriptor !== undefined && Object.hasOwn(descriptor, "value")) {
      deepFreeze(descriptor.value);
    }
  }
  return Object.freeze(value);
};

const readText = (root, relative) => {
  try {
    return readFileSync(join(root, relative), "utf8");
  } catch (error) {
    fail("POLICY_UNREADABLE", `cannot read ${relative}: ${error.message}`, { path: relative });
    return "";
  }
};

const readJson = (root, relative) => {
  const text = readText(root, relative);
  try {
    return JSON.parse(text);
  } catch (error) {
    fail("POLICY_UNREADABLE", `${relative} is not JSON: ${error.message}`, { path: relative });
    return undefined;
  }
};

const requireFields = (value, fields, label, code) => {
  if (!isPlainObject(value)) fail(code, `${label} must be an object`, { label });
  const actual = Object.keys(value).sort();
  const expected = [...fields].sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) {
    fail(code, `${label} must declare exactly ${expected.join(", ")}`, {
      actual,
      expected,
      label,
    });
  }
  return value;
};

const requireCanonicalStrings = (value, label) => {
  if (!Array.isArray(value) || value.some((entry) => typeof entry !== "string")) {
    fail("DECLARATION_NONCANONICAL", `${label} must be an array of strings`, { label });
  }
  const sorted = [...value].sort();
  if (value.some((entry, index) => entry !== sorted[index])) {
    fail("DECLARATION_NONCANONICAL", `${label} must be sorted`, { label, value: [...value] });
  }
  if (new Set(value).size !== value.length) {
    fail("DECLARATION_NONCANONICAL", `${label} must not repeat an entry`, {
      label,
      value: [...value],
    });
  }
  return Object.freeze([...value]);
};

const requireMembers = (values, allowed, code, label) => {
  for (const value of values) {
    if (!allowed.has(value)) {
      fail(code, `${label} names "${value}", which its declaring source does not declare`, {
        declared: [...allowed].sort(),
        label,
        value,
      });
    }
  }
  return values;
};

const requireNonEmptyString = (value, label, code) => {
  if (typeof value !== "string" || value.length === 0) {
    fail(code, `${label} must be a non-empty string`, { label });
  }
  return value;
};

/**
 * Read and cross-check the degraded-mode policy.
 *
 * The policy declares no vocabulary of its own: the capability states it treats
 * as enabled must be states the sealed capability probe declares, the full and
 * degraded operating modes must partition that probe's mode vocabulary, and the
 * host bindings must reach every host the sealed hook gateway declares.  What
 * the policy adds is the binding between a host report and a gateway host, which
 * cannot be derived from either vocabulary and so is declared and checked.
 */
export const loadDegradedModePolicy = ({ root = REPOSITORY_ROOT } = {}) => {
  const declared = requireFields(
    readJson(root, POLICY_PATH),
    POLICY_FIELDS,
    "degraded-mode policy",
    "POLICY_UNREADABLE",
  );

  const enabledStates = requireCanonicalStrings(
    declared.enabled_capability_states,
    "enabled_capability_states",
  );
  requireMembers(
    enabledStates,
    CAPABILITY_STATE_SET,
    "CAPABILITY_STATE_UNDECLARED",
    "enabled_capability_states",
  );
  if (enabledStates.length === 0 || enabledStates.length === CAPABILITY_STATES.length) {
    fail(
      "ENABLED_STATE_SET_VACUOUS",
      "enabled_capability_states must be a non-empty proper subset of the capability vocabulary",
      { declared: [...CAPABILITY_STATES], enabled: [...enabledStates] },
    );
  }

  const fullModes = requireCanonicalStrings(declared.full_modes, "full_modes");
  const degradedModes = requireCanonicalStrings(declared.degraded_modes, "degraded_modes");
  requireMembers(fullModes, MODE_SET, "MODE_UNDECLARED", "full_modes");
  requireMembers(degradedModes, MODE_SET, "MODE_UNDECLARED", "degraded_modes");
  const union = [...new Set([...fullModes, ...degradedModes])].sort();
  const modeVocabulary = [...HOST_CAPABILITY_MODES].sort();
  if (
    union.length !== fullModes.length + degradedModes.length ||
    union.length !== modeVocabulary.length ||
    union.some((entry, index) => entry !== modeVocabulary[index])
  ) {
    fail(
      "MODE_PARTITION_INCOMPLETE",
      "full_modes and degraded_modes must partition the capability probe mode vocabulary",
      { degraded: [...degradedModes], full: [...fullModes], vocabulary: modeVocabulary },
    );
  }

  if (!Array.isArray(declared.host_bindings) || declared.host_bindings.length === 0) {
    fail("POLICY_UNREADABLE", "host_bindings must be a non-empty array", {
      path: POLICY_PATH,
    });
  }
  const bindings = new Map();
  const reportHosts = [];
  for (const row of declared.host_bindings) {
    requireFields(row, BINDING_FIELDS, "host_bindings[]", "POLICY_UNREADABLE");
    const reportHost = requireNonEmptyString(
      row.capability_report_host,
      "host_bindings[].capability_report_host",
      "POLICY_UNREADABLE",
    );
    const gatewayHost = requireNonEmptyString(
      row.gateway_host,
      "host_bindings[].gateway_host",
      "POLICY_UNREADABLE",
    );
    requireMembers([gatewayHost], HOST_SET, "HOST_UNDECLARED", "host_bindings[].gateway_host");
    reportHosts.push(reportHost);
    bindings.set(reportHost, gatewayHost);
  }
  requireCanonicalStrings(reportHosts, "host_bindings[].capability_report_host");
  const reached = new Set(bindings.values());
  const unreached = HOOK_HOSTS.filter((host) => !reached.has(host));
  if (unreached.length > 0) {
    fail("HOST_BINDING_INCOMPLETE", "no host binding reaches every declared gateway host", {
      unreached,
    });
  }

  const hookCapability = requireNonEmptyString(
    declared.hook_capability_name,
    "hook_capability_name",
    "POLICY_UNREADABLE",
  );
  const hostedToolCapability = requireNonEmptyString(
    declared.hosted_tool_capability_name,
    "hosted_tool_capability_name",
    "POLICY_UNREADABLE",
  );
  if (hookCapability === hostedToolCapability) {
    fail(
      "POLICY_UNREADABLE",
      "hook_capability_name and hosted_tool_capability_name must be different capabilities",
      { capability: hookCapability },
    );
  }

  return Object.freeze({
    bindings: Object.freeze(new Map(bindings)),
    declared: deepFreeze(declared),
    degradedModes: new Set(degradedModes),
    enabledStates: new Set(enabledStates),
    fullModes: new Set(fullModes),
    hookCapabilityName: hookCapability,
    hostedToolCapabilityName: hostedToolCapability,
    policyId: requireNonEmptyString(declared.policy_id, "policy_id", "POLICY_UNREADABLE"),
    policyVersion: requireNonEmptyString(
      declared.policy_version,
      "policy_version",
      "POLICY_UNREADABLE",
    ),
    root,
  });
};

/**
 * The coverage dispositions, ordered by the rank H05's registration set already
 * declares.  H06 restates no disposition name: the least-ranked disposition is
 * the one that claims nothing, the greatest is the one that claims every host,
 * and the single intermediate disposition is what partial observation degrades
 * to.  A rank that cannot be read that way is refused rather than guessed at.
 */
export const deriveCoverageOrder = (observability) => {
  const rank = observability.declaration.coverage_rank;
  const ordered = [...HOOK_COVERAGE].sort((left, right) => rank[left] - rank[right]);
  const ranks = ordered.map((disposition) => rank[disposition]);
  if (
    ordered.length !== 3 ||
    new Set(ranks).size !== ranks.length ||
    ranks.some((value) => !Number.isSafeInteger(value))
  ) {
    fail(
      "COVERAGE_RANK_AMBIGUOUS",
      "the coverage rank must order the gateway vocabulary into three distinct ranks",
      { ordered, ranks },
    );
  }
  return Object.freeze({
    greatest: ordered[2],
    intermediate: ordered[1],
    least: ordered[0],
    rank: Object.freeze({ ...rank }),
  });
};

const compareCoverage = (order, declared, derived, context) => {
  const declaredRank = order.rank[declared];
  const derivedRank = order.rank[derived];
  if (declaredRank > derivedRank) {
    fail("DEGRADED_OVERCLAIMED", `${context.label} claims ${declared} but only ${derived} holds`, {
      ...context,
      declared,
      derived,
    });
  }
  if (declaredRank < derivedRank) {
    fail("DEGRADED_UNDERSTATED", `${context.label} claims ${declared} while ${derived} holds`, {
      ...context,
      declared,
      derived,
    });
  }
};

const normalizeHostState = (policy, candidate) => {
  requireFields(candidate, HOST_STATE_FIELDS, "host state", "DECLARATION_UNREADABLE");
  let report;
  try {
    report = validateHostCapabilityReport(candidate.capability_report);
  } catch (error) {
    fail("REPORT_REJECTED", "a declared host capability report did not survive revalidation", {
      probe_code: error.code ?? null,
    });
  }

  const gatewayHost = policy.bindings.get(report.host);
  if (gatewayHost === undefined) {
    fail("HOST_BINDING_UNDECLARED", `no policy binding names host report host ${report.host}`, {
      capability_report_host: report.host,
      declared: [...policy.bindings.keys()].sort(),
    });
  }

  const toolPaths = requireCanonicalStrings(candidate.tool_paths, "host state.tool_paths");
  const hostedToolPaths = requireCanonicalStrings(
    candidate.hosted_tool_paths,
    "host state.hosted_tool_paths",
  );
  const toolPathSet = new Set(toolPaths);
  requireMembers(
    hostedToolPaths,
    toolPathSet,
    "TOOL_PATH_UNDECLARED",
    `${gatewayHost}.hosted_tool_paths`,
  );
  requireMembers(
    report.unobserved_tool_paths,
    toolPathSet,
    "TOOL_PATH_UNDECLARED",
    `${gatewayHost}.capability_report.unobserved_tool_paths`,
  );

  const hookCapability = report.capabilities[policy.hookCapabilityName];
  if (hookCapability === undefined) {
    fail(
      "HOOK_CAPABILITY_ABSENT",
      `${gatewayHost} declares no observation of ${policy.hookCapabilityName}`,
      { capability: policy.hookCapabilityName, gateway_host: gatewayHost },
    );
  }
  const hostedCapability = report.capabilities[policy.hostedToolCapabilityName] ?? null;
  const hooksEnabled = policy.enabledStates.has(hookCapability.state);
  const hostedToolsEnabled =
    hostedCapability === null ? null : policy.enabledStates.has(hostedCapability.state);

  if (policy.fullModes.has(report.mode)) {
    for (const name of Object.keys(report.capabilities).sort()) {
      if (!policy.enabledStates.has(report.capabilities[name].state)) {
        fail(
          "DEGRADATION_UNDECLARED",
          `${gatewayHost} reports mode ${report.mode} while ${name} is ${report.capabilities[name].state}`,
          {
            capability: name,
            gateway_host: gatewayHost,
            mode: report.mode,
            state: report.capabilities[name].state,
          },
        );
      }
    }
  }

  const unobserved = new Set(report.unobserved_tool_paths);
  for (const toolPath of hostedToolPaths) {
    if (!unobserved.has(toolPath)) {
      fail(
        "HOSTED_TOOL_OBSERVATION_CONTRADICTED",
        `${gatewayHost} declares ${toolPath} as bypassing local hooks while reporting it observed`,
        { gateway_host: gatewayHost, tool_path: toolPath },
      );
    }
  }
  if (hostedToolsEnabled === false && hostedToolPaths.length === 0) {
    fail(
      "HOSTED_TOOL_ACTIONS_UNNAMED",
      `${gatewayHost} declares ${policy.hostedToolCapabilityName} as ${hostedCapability.state} while naming no hosted tool path`,
      { gateway_host: gatewayHost, state: hostedCapability.state },
    );
  }

  const reasons = new Map();
  const addReason = (toolPath, reason) => {
    if (!reasons.has(toolPath)) reasons.set(toolPath, new Set());
    reasons.get(toolPath).add(reason);
  };
  if (!hooksEnabled) for (const toolPath of toolPaths) addReason(toolPath, "HOOKS_DISABLED");
  for (const toolPath of hostedToolPaths) addReason(toolPath, "HOSTED_TOOL_BYPASS");
  for (const toolPath of report.unobserved_tool_paths) {
    addReason(toolPath, "UNOBSERVED_TOOL_PATH");
  }

  return deepFreeze({
    gatewayHost,
    hookCapability,
    hooksEnabled,
    hostedCapability,
    hostedToolPaths: [...hostedToolPaths],
    hostedToolsEnabled,
    report,
    toolPaths: [...toolPaths],
    unverified: [...reasons.keys()].sort().map((toolPath) => ({
      gateway_host: gatewayHost,
      reasons: [...reasons.get(toolPath)].sort(),
      tool_path: toolPath,
    })),
  });
};

const hostStateInput = (state) => ({
  capability_report: state.report,
  hosted_tool_paths: [...state.hostedToolPaths],
  tool_paths: [...state.toolPaths],
});

const canonicalPolicyCopy = (policy) =>
  Object.freeze({
    bindings: new Map(policy.bindings),
    declared: deepFreeze({
      ...policy.declared,
      degraded_modes: [...policy.declared.degraded_modes],
      enabled_capability_states: [...policy.declared.enabled_capability_states],
      full_modes: [...policy.declared.full_modes],
      host_bindings: policy.declared.host_bindings.map((binding) => ({ ...binding })),
    }),
    degradedModes: new Set(policy.degradedModes),
    enabledStates: new Set(policy.enabledStates),
    fullModes: new Set(policy.fullModes),
    hookCapabilityName: policy.hookCapabilityName,
    hostedToolCapabilityName: policy.hostedToolCapabilityName,
    policyId: policy.policyId,
    policyVersion: policy.policyVersion,
    root: policy.root,
  });

const verifyRecovery = (policy, states, prior, candidate) => {
  requireFields(candidate, RECOVERY_FIELDS, "recovery", "DECLARATION_UNREADABLE");
  const gatewayHost = requireNonEmptyString(
    candidate.gateway_host,
    "recovery.gateway_host",
    "DECLARATION_UNREADABLE",
  );
  requireMembers([gatewayHost], HOST_SET, "HOST_UNDECLARED", "recovery.gateway_host");
  if (prior === null || !prior.hook_disabled_hosts.includes(gatewayHost)) {
    fail("RECOVERY_HOST_NOT_DISABLED", `no prior receipt holds ${gatewayHost} as hook-disabled`, {
      gateway_host: gatewayHost,
      prior_hook_disabled_hosts: prior === null ? null : [...prior.hook_disabled_hosts],
    });
  }

  const state = states.get(gatewayHost);
  if (state === undefined) {
    fail("HOST_STATE_MISSING", `recovery names ${gatewayHost}, which declares no host state`, {
      gateway_host: gatewayHost,
    });
  }
  if (!state.hooksEnabled) {
    fail(
      "RECOVERY_COVERAGE_UNRESTORED",
      `${gatewayHost} still reports ${state.hookCapability.state} for ${policy.hookCapabilityName}`,
      { gateway_host: gatewayHost, state: state.hookCapability.state },
    );
  }

  const priorState = prior.host_states.find((row) => row.gateway_host === gatewayHost) ?? null;
  if (
    priorState !== null &&
    (priorState.capability_report_id === state.report.report_id ||
      priorState.capability_report_hash === state.report.report_hash)
  ) {
    fail(
      "RECOVERY_UNCHANGED_REPORT",
      `${gatewayHost} re-presented the host report the disabled state was derived from`,
      { gateway_host: gatewayHost, report_id: state.report.report_id },
    );
  }

  let trust;
  try {
    trust = verifyHookTrust({
      hookDefinitions: candidate.hook_definitions,
      trustedHookHashes: candidate.trusted_hook_hashes,
      hooksEnabled: candidate.hooks_enabled,
    });
  } catch (error) {
    fail("RECOVERY_EVIDENCE_MISSING", "the re-registration evidence was not verifiable", {
      gateway_host: gatewayHost,
      probe_code: error.code ?? null,
    });
  }
  if (!trust.hooksEnabled) {
    fail("RECOVERY_EVIDENCE_MISSING", `${gatewayHost} re-registered with hooks still disabled`, {
      gateway_host: gatewayHost,
    });
  }
  if (trust.retrustRequired) {
    fail("RECOVERY_RETRUST_REQUIRED", `${gatewayHost} re-registered outside the approved trust set`, {
      changed_hooks: [...trust.changedHooks],
      gateway_host: gatewayHost,
      stale_trusted_hashes: [...trust.staleTrustedHashes],
    });
  }
  if (!policy.enabledStates.has(trust.state)) {
    fail("RECOVERY_EVIDENCE_MISSING", `${gatewayHost} re-registration evidence is ${trust.state}`, {
      gateway_host: gatewayHost,
      state: trust.state,
    });
  }

  const observedHash = state.hookCapability.observed_hash;
  if (observedHash === undefined || observedHash !== trust.observedHash) {
    fail(
      "RECOVERY_EVIDENCE_MISMATCHED",
      `${gatewayHost} re-registered a hook bundle the new host report was not probed with`,
      {
        evidence_hash: trust.observedHash,
        gateway_host: gatewayHost,
        report_hook_hash: observedHash ?? null,
      },
    );
  }

  return {
    evidence_hash: sha256HookJson({
      current_hook_hashes: [...trust.currentHookHashes],
      hooks_enabled: trust.hooksEnabled,
      trusted_hook_hashes: [...trust.trustedHookHashes],
    }),
    from_report_id: priorState === null ? null : priorState.capability_report_id,
    gateway_host: gatewayHost,
    hook_bundle_hash: trust.observedHash,
    to_report_id: state.report.report_id,
  };
};

/**
 * Open the degraded-mode gate over one declared host state per gateway host.
 *
 * `priorReceipt` is how a transition is judged.  Without it the gate describes
 * the present only; with it, every gateway host the prior receipt recorded as
 * hook-disabled and this state reports as enabled must carry re-registration
 * evidence in `recoveries`, or the gate refuses to publish the re-enablement.
 */
export const openDegradedGate = ({
  root = REPOSITORY_ROOT,
  policy = loadDegradedModePolicy({ root }),
  observability = loadObservability({ root }),
  hostStates,
  priorReceipt = null,
  recoveries = [],
} = {}) => {
  if (!Array.isArray(hostStates)) {
    fail("DECLARATION_UNREADABLE", "hostStates must be an array of declared host states");
  }
  if (!Array.isArray(recoveries)) {
    fail("DECLARATION_UNREADABLE", "recoveries must be an array of recovery records");
  }

  const prior = priorReceipt === null ? null : validateDegradedModeReceipt(priorReceipt);
  if (prior !== null && prior.policy_id !== policy.policyId) {
    fail("RECEIPT_REJECTED", "the prior receipt was issued under a different degraded-mode policy", {
      policy_id: policy.policyId,
      prior_policy_id: prior.policy_id,
    });
  }

  const states = new Map();
  for (const candidate of hostStates) {
    const state = normalizeHostState(policy, candidate);
    if (states.has(state.gatewayHost)) {
      fail("HOST_STATE_DUPLICATED", `${state.gatewayHost} is declared by two host states`, {
        gateway_host: state.gatewayHost,
      });
    }
    states.set(state.gatewayHost, state);
  }
  for (const host of observability.observedHosts) {
    if (!states.has(host)) {
      fail("HOST_STATE_MISSING", `${host} is claimed as observed but declares no host state`, {
        declared: [...states.keys()].sort(),
        gateway_host: host,
      });
    }
  }

  const verified = [];
  const recoveredHosts = new Set();
  for (const candidate of recoveries) {
    const record = verifyRecovery(policy, states, prior, candidate);
    if (recoveredHosts.has(record.gateway_host)) {
      fail("HOST_STATE_DUPLICATED", `${record.gateway_host} carries two recovery records`, {
        gateway_host: record.gateway_host,
      });
    }
    recoveredHosts.add(record.gateway_host);
    verified.push(record);
  }
  if (prior !== null) {
    for (const host of prior.hook_disabled_hosts) {
      const state = states.get(host);
      if (state !== undefined && state.hooksEnabled && !recoveredHosts.has(host)) {
        fail(
          "RECOVERY_EVIDENCE_MISSING",
          `${host} moved from hook-disabled to hook-enabled without re-registration evidence`,
          { gateway_host: host },
        );
      }
    }
  }
  verified.sort((left, right) => (left.gateway_host < right.gateway_host ? -1 : 1));

  const enabledHosts = HOOK_HOSTS.filter((host) => states.get(host)?.hooksEnabled === true).sort();
  const disabledHosts = HOOK_HOSTS.filter(
    (host) => states.has(host) && !states.get(host).hooksEnabled,
  ).sort();
  const unverifiedActions = [...states.keys()]
    .sort()
    .flatMap((host) => states.get(host).unverified)
    .sort((left, right) =>
      left.gateway_host === right.gateway_host
        ? left.tool_path < right.tool_path
          ? -1
          : 1
        : left.gateway_host < right.gateway_host
          ? -1
          : 1,
    );

  const verifiedState = Object.freeze({
    coverageOrder: deriveCoverageOrder(observability),
    disabledHosts: Object.freeze([...disabledHosts]),
    enabledHosts: Object.freeze([...enabledHosts]),
    fullReport: deepFreeze(coverageReport(observability)),
    hostStates: new Map(states),
    observability,
    policy: canonicalPolicyCopy(policy),
    priorReceipt: prior,
    recoveries: deepFreeze(verified),
    root,
    unverifiedActions: deepFreeze(unverifiedActions),
  });
  const result = Object.freeze({
    coverageOrder: verifiedState.coverageOrder,
    disabledHosts: Object.freeze([...verifiedState.disabledHosts]),
    enabledHosts: Object.freeze([...verifiedState.enabledHosts]),
    fullReport: deepFreeze(coverageReport(verifiedState.observability)),
    // Compatibility snapshot only. Map mutations cannot change the private
    // verified state used by authoritative derivations.
    hostStates: Object.freeze(new Map(verifiedState.hostStates)),
    observability: verifiedState.observability,
    policy: canonicalPolicyCopy(verifiedState.policy),
    priorReceipt: verifiedState.priorReceipt,
    recoveries: verifiedState.recoveries,
    root: verifiedState.root,
    unverifiedActions: verifiedState.unverifiedActions,
  });
  VERIFIED_GATE_STATE_BY_CONTEXT.set(result, verifiedState);
  return result;
};

/**
 * The degraded coverage report.
 *
 * It is H05's report projected through the enabled host set: every host/event
 * pair that only a hook-disabled host observed is withdrawn, named in
 * `withdrawn_pairs`, and added to `not_observed`.  The derived disposition is
 * checked against H05's own disposition for the same event type, so this report
 * can only ever say the same or less — never more.
 */
export const degradedCoverageReport = (gate) => {
  const state = requireVerifiedGateState(gate);
  const order = state.coverageOrder;
  const enabled = new Set(state.enabledHosts);
  const withdrawn = [];
  const notObserved = [...state.fullReport.not_observed];

  const eventTypes = state.fullReport.event_types.map((row) => {
    const observed = row.hosts_observed.filter((host) => enabled.has(host)).sort();
    const withdrawnHosts = row.hosts_observed.filter((host) => !enabled.has(host)).sort();
    for (const host of withdrawnHosts) {
      withdrawn.push(`${host}:${row.event_type}`);
      notObserved.push(`${host}:${row.event_type}`);
    }
    const coverage =
      observed.length === 0
        ? order.least
        : observed.length === HOOK_HOSTS.length
          ? order.greatest
          : order.intermediate;
    if (order.rank[coverage] > order.rank[row.coverage]) {
      fail("DEGRADED_OVERCLAIMED", `the degraded report exceeds H05 for ${row.event_type}`, {
        declared: coverage,
        derived: row.coverage,
        event_type: row.event_type,
      });
    }
    return {
      coverage,
      event_type: row.event_type,
      hosts_observed: observed,
      hosts_unobserved: [...row.hosts_unobserved, ...withdrawnHosts].sort(),
      hosts_withdrawn: withdrawnHosts,
      in_evolution_surface: row.in_evolution_surface,
    };
  });

  return deepFreeze({
    coverage_by_event_type: Object.fromEntries(
      eventTypes.map((row) => [row.event_type, row.coverage]),
    ),
    event_types: eventTypes,
    full_coverage_by_event_type: { ...state.fullReport.coverage_by_event_type },
    hook_disabled_hosts: [...state.disabledHosts],
    hook_enabled_hosts: [...state.enabledHosts],
    not_observed: [...new Set(notObserved)].sort(),
    observed_pair_count: eventTypes.reduce((total, row) => total + row.hosts_observed.length, 0),
    unverified_actions: state.unverifiedActions.map((row) => ({
      gateway_host: row.gateway_host,
      reasons: [...row.reasons],
      tool_path: row.tool_path,
    })),
    withdrawn_pairs: withdrawn.sort(),
  });
};

/** The explicit list of actions no local hook can attest, never an omission. */
export const unverifiedActions = (gate) => {
  const state = requireVerifiedGateState(gate);
  return deepFreeze(
    state.unverifiedActions.map((row) => ({
      gateway_host: row.gateway_host,
      reasons: [...row.reasons],
      tool_path: row.tool_path,
    })),
  );
};

/**
 * Verify an externally supplied coverage claim against the degraded report.
 *
 * H05's own full-coverage report is a valid claim only while every host it
 * counts is hook-enabled; presenting it under degradation is `DEGRADED_OVERCLAIMED`
 * because it omits the withdrawn pairs, or claims a disposition the enabled set
 * no longer supports.
 */
export const assertDegradedCoverageClaim = (gate, claim) => {
  const state = requireVerifiedGateState(gate);
  requireFields(claim, CLAIM_FIELDS, "coverage claim", "DECLARATION_UNREADABLE");
  const derived = degradedCoverageReport(gate);
  const claimed = claim.coverage_by_event_type;
  requireFields(
    claimed,
    HOOK_EVENT_TYPES,
    "coverage claim.coverage_by_event_type",
    "DECLARATION_UNREADABLE",
  );
  for (const eventType of HOOK_EVENT_TYPES) {
    if (!COVERAGE_SET.has(claimed[eventType])) {
      fail("COVERAGE_UNDECLARED", `the claim for ${eventType} is outside the gateway vocabulary`, {
        coverage: claimed[eventType],
        event_type: eventType,
      });
    }
    compareCoverage(
      state.coverageOrder,
      claimed[eventType],
      derived.coverage_by_event_type[eventType],
      { event_type: eventType, label: `degraded coverage claim for ${eventType}` },
    );
  }

  const claimedMissing = requireCanonicalStrings(claim.not_observed, "coverage claim.not_observed");
  const derivedMissing = new Set(derived.not_observed);
  const omitted = [...derivedMissing].filter((pair) => !claimedMissing.includes(pair)).sort();
  if (omitted.length > 0) {
    fail("DEGRADED_OVERCLAIMED", "the claim omits host/event pairs the enabled set cannot observe", {
      omitted,
      withdrawn: [...derived.withdrawn_pairs],
    });
  }
  const invented = claimedMissing.filter((pair) => !derivedMissing.has(pair)).sort();
  if (invented.length > 0) {
    fail("DEGRADED_UNDERSTATED", "the claim lists observed host/event pairs as unobserved", {
      invented,
    });
  }
  return derived;
};

/**
 * Judge one workflow step's provenance claim.
 *
 * A step claiming any disposition above the least-ranked one is claiming that a
 * hook observed its action.  That claim is refused when the action runs on an
 * unverified tool path — the hosted-tool bypass case — and refused when the
 * host/event pair is not observed by the enabled set — the hook-disabled case.
 * A step claiming the least-ranked disposition is always honest and is returned
 * with the reasons its action is unverified attached.
 */
export const assertStepProvenance = (gate, step) => {
  const state = requireVerifiedGateState(gate);
  requireFields(step, STEP_FIELDS, "workflow step", "DECLARATION_UNREADABLE");
  const stepId = requireNonEmptyString(step.step_id, "workflow step.step_id", "DECLARATION_UNREADABLE");
  const gatewayHost = step.gateway_host;
  requireMembers([gatewayHost], HOST_SET, "HOST_UNDECLARED", `${stepId}.gateway_host`);
  if (!EVENT_TYPE_SET.has(step.event_type)) {
    fail("EVENT_TYPE_UNDECLARED", `${stepId} names event type ${step.event_type}`, {
      event_type: step.event_type,
      step_id: stepId,
    });
  }
  if (!COVERAGE_SET.has(step.claimed_coverage)) {
    fail("COVERAGE_UNDECLARED", `${stepId} claims coverage outside the gateway vocabulary`, {
      coverage: step.claimed_coverage,
      step_id: stepId,
    });
  }

  const hostState = state.hostStates.get(gatewayHost) ?? null;
  const toolPath = step.tool_path;
  if (toolPath !== null) {
    if (
      typeof toolPath !== "string" ||
      hostState === null ||
      !hostState.toolPaths.includes(toolPath)
    ) {
      fail("TOOL_PATH_UNDECLARED", `${stepId} names a tool path ${gatewayHost} does not declare`, {
        declared: hostState === null ? [] : [...hostState.toolPaths],
        gateway_host: gatewayHost,
        step_id: stepId,
        tool_path: toolPath,
      });
    }
  }

  const unverified =
    hostState === null || toolPath === null
      ? null
      : (hostState.unverified.find((row) => row.tool_path === toolPath) ?? null);
  const reasons = unverified === null ? [] : [...unverified.reasons];
  const asserted =
    state.coverageOrder.rank[step.claimed_coverage] >
    state.coverageOrder.rank[state.coverageOrder.least];

  if (asserted && reasons.length > 0) {
    fail(
      "HOSTED_TOOL_PROVENANCE_CLAIMED",
      `${stepId} claims ${step.claimed_coverage} for an action no local hook can attest`,
      {
        gateway_host: gatewayHost,
        reasons,
        step_id: stepId,
        tool_path: toolPath,
      },
    );
  }

  const report = degradedCoverageReport(gate);
  const row = report.event_types.find((entry) => entry.event_type === step.event_type);
  const observed = row.hosts_observed.includes(gatewayHost);
  if (asserted && !observed) {
    fail(
      "DEGRADED_OVERCLAIMED",
      `${stepId} claims ${step.claimed_coverage} for ${gatewayHost}:${step.event_type}, which the enabled set does not observe`,
      {
        event_type: step.event_type,
        gateway_host: gatewayHost,
        hosts_observed: [...row.hosts_observed],
        step_id: stepId,
      },
    );
  }

  return deepFreeze({
    claimed_coverage: step.claimed_coverage,
    event_type: step.event_type,
    gateway_host: gatewayHost,
    hook_verified: observed && reasons.length === 0,
    step_id: stepId,
    tool_path: toolPath,
    unverified_reasons: reasons,
  });
};

/**
 * Re-open the gate with one gateway host recovered.
 *
 * The recovery runs through the same path a caller would take by hand: the prior
 * receipt is the transition's starting point, the new host state is the re-probed
 * report, and the evidence is verified by H04's own hook-trust verifier.  This
 * helper adds no authority; it only removes the temptation to rebuild the gate
 * without the receipt that makes the transition checkable.
 */
export const recoverHookHost = (gate, options) => {
  const state = requireVerifiedGateState(gate);
  const { hostState, recovery } = options ?? {};
  requireFields(recovery, RECOVERY_FIELDS, "recovery", "DECLARATION_UNREADABLE");
  const retained = [...state.hostStates.keys()]
    .filter((host) => host !== recovery.gateway_host)
    .sort()
    .map((host) => hostStateInput(state.hostStates.get(host)));
  return openDegradedGate({
    hostStates: [...retained, hostState],
    observability: state.observability,
    policy: state.policy,
    priorReceipt: degradedModeReceipt(gate),
    recoveries: [recovery],
    root: state.root,
  });
};

/**
 * An immutable receipt for the degraded-mode gate: which hosts were declared,
 * which of them run hooks, which observability claims were withdrawn, which
 * actions are unverified, what recovery evidence was accepted, and the hash of
 * exactly those fields.  Every declaring source is bound by the sealed gateway's
 * canonical-JSON digest of its UTF-8 text, and the H05 receipt it degrades is
 * bound by hash rather than restated.
 */
export const degradedModeReceipt = (gate) => {
  const state = requireVerifiedGateState(gate);
  const report = degradedCoverageReport(gate);
  const preimage = {
    capability_vocabulary: {
      capability_states: [...CAPABILITY_STATES],
      host_capability_modes: [...HOST_CAPABILITY_MODES],
    },
    coverage_by_event_type: { ...report.coverage_by_event_type },
    declaring_sources: [...DECLARING_SOURCES]
      .sort()
      .map((path) => ({ path, text_hash: sha256HookJson(readText(state.root, path)) })),
    full_coverage_by_event_type: { ...report.full_coverage_by_event_type },
    gateway_vocabulary: {
      coverage: [...HOOK_COVERAGE],
      event_types: [...HOOK_EVENT_TYPES],
      hosts: [...HOOK_HOSTS],
    },
    hook_disabled_hosts: [...report.hook_disabled_hosts],
    hook_enabled_hosts: [...report.hook_enabled_hosts],
    host_states: [...state.hostStates.keys()].sort().map((host) => {
      const hostState = state.hostStates.get(host);
      return {
        capability_report_host: hostState.report.host,
        capability_report_hash: hostState.report.report_hash,
        capability_report_id: hostState.report.report_id,
        gateway_host: host,
        hook_capability_state: hostState.hookCapability.state,
        hooks_enabled: hostState.hooksEnabled,
        hosted_tool_capability_state:
          hostState.hostedCapability === null ? null : hostState.hostedCapability.state,
        hosted_tool_paths: [...hostState.hostedToolPaths],
        mode: hostState.report.mode,
        tool_paths: [...hostState.toolPaths],
      };
    }),
    not_observed: [...report.not_observed],
    observability_receipt_hash: observabilityReceipt(state.observability).receipt_hash,
    observed_pair_count: report.observed_pair_count,
    policy_id: state.policy.policyId,
    policy_version: state.policy.policyVersion,
    recoveries: state.recoveries.map((row) => ({ ...row })),
    unverified_actions: report.unverified_actions.map((row) => ({
      gateway_host: row.gateway_host,
      reasons: [...row.reasons],
      tool_path: row.tool_path,
    })),
    withdrawn_pairs: [...report.withdrawn_pairs],
  };
  const receiptHash = sha256HookJson(preimage);
  return deepFreeze({
    receipt_id: `EFH06-DEGRADED-MODE-${receiptHash.slice("sha256:".length, "sha256:".length + 16)}`,
    ...preimage,
    receipt_hash: receiptHash,
  });
};

/**
 * Revalidate a degraded-mode receipt as evidence of an earlier host state.
 *
 * A transition back to hook-enabled is judged against this receipt, so a receipt
 * that does not re-derive its own hash is refused before it can be used to claim
 * that a host was never disabled in the first place.
 */
export const validateDegradedModeReceipt = (candidate) => {
  requireFields(candidate, RECEIPT_FIELDS, "degraded-mode receipt", "RECEIPT_REJECTED");
  const { receipt_hash: observedHash, receipt_id: receiptId, ...preimage } = candidate;
  let expected;
  try {
    expected = sha256HookJson(preimage);
  } catch (error) {
    fail("RECEIPT_REJECTED", "the receipt preimage is not canonical JSON", {
      gateway_code: error.code ?? null,
    });
  }
  if (observedHash !== expected) {
    fail("RECEIPT_REJECTED", "the receipt does not re-derive its own hash", {
      expected,
      observed: observedHash,
    });
  }
  const expectedId = `EFH06-DEGRADED-MODE-${expected.slice("sha256:".length, "sha256:".length + 16)}`;
  if (receiptId !== expectedId) {
    fail("RECEIPT_REJECTED", "the receipt identifier is not derived from its hash", {
      expected: expectedId,
      observed: receiptId,
    });
  }
  return deepFreeze(JSON.parse(JSON.stringify(candidate)));
};
