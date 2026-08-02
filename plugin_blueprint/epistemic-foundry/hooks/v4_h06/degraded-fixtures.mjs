// Test scaffolding: declared host states and a staged repository root.
//
// Every host state this gate reasons about is a real H04 HostCapabilityReport
// produced by the sealed capability probe, not a hand-written object, so a test
// can only express degradation the probe itself can express.  Where a hostile
// case needs a report the probe would never emit, `forgeReport` rebuilds the
// canonical hash as well, because a forgery that fails validation would prove
// nothing about the gate's own cross-checks.
//
// The staged root is H05's staged root plus this package's policy: the hostile
// policy cases mutate a copy, never the repository.

import { cpSync, mkdirSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";

import {
  probeHostCapabilities,
  verifyHookTrust,
} from "../../../../packages/plugin-host/src/capability-probe/capability-probe.mjs";
import { sha256HookJson } from "../../../../packages/plugin-host/src/hooks/gateway/hook-gateway.mjs";
import { REGISTRATIONS_PATH } from "../v4_h05/index.mjs";
import {
  readStagedJson,
  stageRoot as stageObservabilityRoot,
  writeStagedJson,
} from "../v4_h05/observability-fixtures.mjs";
import { POLICY_PATH, REPOSITORY_ROOT } from "./index.mjs";

export const APPROVED_HOOK_HASH = `sha256:${"a".repeat(64)}`;
export const CHANGED_HOOK_HASH = `sha256:${"b".repeat(64)}`;
export const OTHER_HOOK_HASH = `sha256:${"c".repeat(64)}`;

/** The bounded hook-event scope every fixture host declares. */
export const DECLARED_HOOK_EVENTS = Object.freeze(["PostToolUse", "PreToolUse", "Stop"]);

/** Stage a root carrying H05's declaring sources and this package's policy. */
export const stageRoot = (t) => {
  const root = stageObservabilityRoot(t);
  const target = join(root, POLICY_PATH);
  mkdirSync(dirname(target), { recursive: true });
  cpSync(join(REPOSITORY_ROOT, POLICY_PATH), target);
  return root;
};

/** Stage a root whose degraded-mode policy has been mutated in one way. */
export const stagePolicy = (t, mutate) => {
  const root = stageRoot(t);
  const policy = readStagedJson(root, POLICY_PATH);
  mutate(policy, root);
  writeStagedJson(root, POLICY_PATH, policy);
  return root;
};

/** Stage a root whose H05 observability registration set has been mutated. */
export const stageObservability = (t, mutate) => {
  const root = stageRoot(t);
  const declaration = readStagedJson(root, REGISTRATIONS_PATH);
  mutate(declaration, root);
  writeStagedJson(root, REGISTRATIONS_PATH, declaration);
  return root;
};

/** Stage a root whose degraded-mode policy file has been removed. */
export const stageWithoutPolicy = (t) => {
  const root = stageRoot(t);
  rmSync(join(root, POLICY_PATH), { force: true });
  return root;
};

/** Run `run` and return the refusal it raises, or fail loudly if it does not. */
export const refusal = (run) => {
  try {
    run();
  } catch (error) {
    return error;
  }
  throw new Error("expected a refusal, but the call succeeded");
};

/** Hook-trust evidence in the exact shape the sealed capability probe requires. */
export const hookTrust = ({
  hooksEnabled = true,
  observedHash = APPROVED_HOOK_HASH,
  trustedHookHashes = [APPROVED_HOOK_HASH],
} = {}) =>
  verifyHookTrust({
    hookDefinitions: [{ hookId: "hooks.json", observedHash }],
    hooksEnabled,
    trustedHookHashes,
  });

/** Re-registration evidence in the shape a recovery record carries. */
export const recoveryEvidence = ({
  gatewayHost = "codex",
  hooksEnabled = true,
  observedHash = APPROVED_HOOK_HASH,
  trustedHookHashes = [APPROVED_HOOK_HASH],
} = {}) => ({
  gateway_host: gatewayHost,
  hook_definitions: [{ hookId: "hooks.json", observedHash }],
  hooks_enabled: hooksEnabled,
  trusted_hook_hashes: trustedHookHashes,
});

/** One HostCapabilityReport, produced by the sealed probe rather than by hand. */
export const capabilityReport = ({
  detectedAt = "2026-08-02T07:00:00.000Z",
  host = "codex_cli",
  hooksEnabled = true,
  knownToolPaths = ["local_shell"],
  observedHookEvents = DECLARED_HOOK_EVENTS,
  observedToolPaths = undefined,
  reportId = "HCR-H06-CODEX-0001",
  trust = undefined,
} = {}) =>
  probeHostCapabilities({
    declaredHookEvents: [...DECLARED_HOOK_EVENTS],
    degradedModes: [
      {
        missingCapability: "plugin_hooks",
        mode: "DEGRADED",
        behavior: "Require explicit kernel receipts instead of hook observation.",
      },
      {
        missingCapability: "hosted_tool_hooks",
        mode: "DEGRADED",
        behavior: "Treat hosted tool actions as unverified and name them.",
      },
      {
        missingCapability: "local_state",
        mode: "READ_ONLY",
        behavior: "Deny writes until local state integrity is re-established.",
      },
    ],
    detectedAt,
    host,
    hostVersion: "2026.08",
    hookTrust: trust ?? hookTrust({ hooksEnabled }),
    knownToolPaths: [...knownToolPaths],
    observations: {
      hosted_tool_hooks: {
        state: "SUPPORTED",
        evidence: "The hosted tool probe returned every declared hosted path.",
      },
      local_state: {
        state: "SUPPORTED",
        evidence: "The local state integrity probe passed.",
      },
      plugin_hooks: {
        state: "SUPPORTED",
        evidence: "The local hook probe returned every declared event.",
      },
    },
    observedHookEvents: [...observedHookEvents],
    observedToolPaths: [...(observedToolPaths ?? knownToolPaths)],
    optionalCapabilities: ["plugin_hooks", "hosted_tool_hooks"],
    pluginVersion: "4.0.0",
    reportId,
    requiredCapabilities: ["local_state"],
  });

/** A declared host state in the exact shape `openDegradedGate` requires. */
export const hostState = ({ hostedToolPaths = [], report, toolPaths }) => ({
  capability_report: report,
  hosted_tool_paths: [...hostedToolPaths].sort(),
  tool_paths: [...toolPaths].sort(),
});

/** A fully hook-enabled codex host with no bypassed tool path. */
export const enabledCodexState = (overrides = {}) =>
  hostState({
    report: capabilityReport({ knownToolPaths: ["local_shell", "repo_write"], ...overrides }),
    toolPaths: ["local_shell", "repo_write"],
  });

/** A fully hook-enabled claude host with no bypassed tool path. */
export const enabledClaudeState = (overrides = {}) =>
  hostState({
    report: capabilityReport({
      host: "claude_code",
      knownToolPaths: ["local_shell"],
      reportId: "HCR-H06-CLAUDE-0001",
      ...overrides,
    }),
    toolPaths: ["local_shell"],
  });

/** A codex host whose hooks the host configuration has turned off. */
export const disabledCodexState = (overrides = {}) =>
  hostState({
    report: capabilityReport({
      hooksEnabled: false,
      knownToolPaths: ["local_shell", "repo_write"],
      reportId: "HCR-H06-CODEX-DISABLED-0001",
      ...overrides,
    }),
    toolPaths: ["local_shell", "repo_write"],
  });

/** A claude host whose hooks the host configuration has turned off. */
export const disabledClaudeState = (overrides = {}) =>
  hostState({
    report: capabilityReport({
      hooksEnabled: false,
      host: "claude_code",
      knownToolPaths: ["local_shell"],
      reportId: "HCR-H06-CLAUDE-DISABLED-0001",
      ...overrides,
    }),
    toolPaths: ["local_shell"],
  });

/** A second codex-bound host state, used where two states collide. */
export const desktopCodexState = (overrides = {}) =>
  hostState({
    report: capabilityReport({
      host: "codex_desktop",
      knownToolPaths: ["local_shell", "repo_write"],
      reportId: "HCR-H06-CODEX-DESKTOP-0001",
      ...overrides,
    }),
    toolPaths: ["local_shell", "repo_write"],
  });

/** A codex host whose hosted search tool bypasses every local hook. */
export const hostedBypassCodexState = (overrides = {}) =>
  hostState({
    hostedToolPaths: ["hosted_search"],
    report: capabilityReport({
      knownToolPaths: ["hosted_search", "local_shell"],
      observedToolPaths: ["local_shell"],
      reportId: "HCR-H06-CODEX-HOSTED-0001",
      ...overrides,
    }),
    toolPaths: ["hosted_search", "local_shell"],
  });

/** The re-probed codex host a recovery presents. */
export const recoveredCodexState = (overrides = {}) =>
  hostState({
    report: capabilityReport({
      detectedAt: "2026-08-02T09:00:00.000Z",
      knownToolPaths: ["local_shell", "repo_write"],
      reportId: "HCR-H06-CODEX-RECOVERED-0001",
      ...overrides,
    }),
    toolPaths: ["local_shell", "repo_write"],
  });

/**
 * Rebuild a host capability report with one field changed and a hash that
 * matches, so the gate's own cross-checks are what refuse it.
 */
export const forgeReport = (report, mutate) => {
  const draft = JSON.parse(JSON.stringify(report));
  delete draft.report_hash;
  mutate(draft);
  return { ...draft, report_hash: sha256HookJson(draft) };
};

/** Rebuild a degraded-mode receipt with one field changed and a matching hash. */
export const forgeReceipt = (receipt, mutate) => {
  const draft = JSON.parse(JSON.stringify(receipt));
  delete draft.receipt_hash;
  delete draft.receipt_id;
  mutate(draft);
  const hash = sha256HookJson(draft);
  return {
    receipt_id: `EFH06-DEGRADED-MODE-${hash.slice("sha256:".length, "sha256:".length + 16)}`,
    ...draft,
    receipt_hash: hash,
  };
};

/** A workflow step in the exact shape `assertStepProvenance` requires. */
export const workflowStep = (overrides = {}) => ({
  claimed_coverage: "OBSERVED",
  event_type: "PreToolUse",
  gateway_host: "codex",
  step_id: "STEP-H06-0001",
  tool_path: "local_shell",
  ...overrides,
});
