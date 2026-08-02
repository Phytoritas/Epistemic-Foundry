import assert from "node:assert/strict";
import test from "node:test";

import {
  CapabilityProbeError,
  buildPluginHealthReport,
  probeHostCapabilities,
  validatePluginHealthReport,
  verifyHookTrust,
} from "../../../packages/plugin-host/src/capability-probe/capability-probe.mjs";

const HASH_A = `sha256:${"a".repeat(64)}`;

const trust = (overrides = {}) => verifyHookTrust({
  hookDefinitions: [{ hookId: "hooks.json", observedHash: HASH_A }],
  trustedHookHashes: [HASH_A],
  hooksEnabled: true,
  ...overrides,
});

const request = (overrides = {}) => ({
  reportId: "HCR-H04-MODE-001",
  host: "codex_desktop",
  hostVersion: "2026.07",
  pluginVersion: "4.0.0",
  detectedAt: "2026-07-29T06:10:00.000Z",
  requiredCapabilities: ["local_state"],
  optionalCapabilities: ["plugin_hooks", "hosted_tool_hooks"],
  degradedModes: [
    {
      missingCapability: "plugin_hooks",
      mode: "DEGRADED",
      behavior: "Use explicit CLI and kernel gates.",
    },
    {
      missingCapability: "hosted_tool_hooks",
      mode: "DEGRADED",
      behavior: "Require kernel receipts for hosted paths.",
    },
  ],
  observations: {
    local_state: { state: "SUPPORTED", evidence: "State integrity probe passed." },
    plugin_hooks: { state: "SUPPORTED", evidence: "Hook probe passed." },
    hosted_tool_hooks: { state: "SUPPORTED", evidence: "Hosted hook probe passed." },
  },
  hookTrust: trust(),
  declaredHookEvents: ["SessionStart", "PreToolUse", "PostToolUse"],
  observedHookEvents: ["SessionStart", "PreToolUse", "PostToolUse"],
  knownToolPaths: ["local_shell", "hosted_search"],
  observedToolPaths: ["local_shell", "hosted_search"],
  ...overrides,
});

const health = (capabilityReport) => buildPluginHealthReport({
  healthId: "PHR-H04-001",
  profile: "LITE",
  generatedAt: "2026-07-29T06:11:00.000Z",
  capabilityReport,
});

const expectCode = (code) => (error) =>
  error instanceof CapabilityProbeError && error.code === code;

test("hook_degraded_mode_test: complete observed support is FULL and health PASS", () => {
  const report = probeHostCapabilities(request());
  const pluginHealth = health(report);

  assert.equal(report.mode, "FULL");
  assert.deepEqual(report.blockers, []);
  assert.equal(pluginHealth.overall, "PASS");
  assert.equal(pluginHealth.checks.every((check) => check.status === "PASS"), true);
  assert.deepEqual(validatePluginHealthReport(pluginHealth), pluginHealth);
});

test("hook_degraded_mode_test: unavailable optional hooks select the declared DEGRADED behavior", () => {
  const report = probeHostCapabilities(request({
    observations: {
      ...request().observations,
      hosted_tool_hooks: {
        state: "UNSUPPORTED",
        evidence: "Hosted tool hooks are unavailable.",
      },
    },
    observedToolPaths: ["local_shell"],
  }));
  const pluginHealth = health(report);

  assert.equal(report.mode, "DEGRADED");
  assert.deepEqual(report.unobserved_tool_paths, ["hosted_search"]);
  assert.equal(pluginHealth.overall, "DEGRADED");
  assert.equal(pluginHealth.checks.some((check) => check.check_id === "hooks.coverage"), true);
  assert.equal(
    report.capabilities.hosted_tool_hooks.limitations.includes(
      "DEGRADED_BEHAVIOR:Require kernel receipts for hosted paths.",
    ),
    true,
  );
});

test("hook_degraded_mode_test: a required capability without a fallback is BLOCKED", () => {
  const report = probeHostCapabilities(request({
    observations: {
      ...request().observations,
      local_state: { state: "ERROR", evidence: "State integrity probe failed." },
    },
  }));
  const pluginHealth = health(report);

  assert.equal(report.mode, "BLOCKED");
  assert.deepEqual(report.blockers, ["DEGRADED_MODE_UNDECLARED:local_state"]);
  assert.equal(pluginHealth.overall, "FAIL");
  assert.equal(
    pluginHealth.checks.find((check) => check.check_id === "capability.local_state").status,
    "FAIL",
  );
});

test("hook_degraded_mode_test: explicit READ_ONLY and SAFE_MODE mappings use the strongest mode", () => {
  const report = probeHostCapabilities(request({
    degradedModes: [
      ...request().degradedModes,
      {
        missingCapability: "local_state",
        mode: "SAFE_MODE",
        behavior: "Allow only doctor, export, and recovery.",
      },
    ],
    observations: {
      local_state: { state: "ERROR", evidence: "State integrity is uncertain." },
      plugin_hooks: { state: "DISABLED", evidence: "Host policy disabled hooks." },
      hosted_tool_hooks: { state: "SUPPORTED", evidence: "Hosted hook probe passed." },
    },
  }));

  assert.equal(report.mode, "SAFE_MODE");
  assert.equal(health(report).overall, "SAFE_MODE");

  const readOnly = probeHostCapabilities(request({
    degradedModes: [
      {
        missingCapability: "local_state",
        mode: "READ_ONLY",
        behavior: "Deny writes and side effects.",
      },
      ...request().degradedModes,
    ],
    observations: {
      ...request().observations,
      local_state: { state: "UNSUPPORTED", evidence: "Writable state is unavailable." },
    },
  }));
  assert.equal(readOnly.mode, "READ_ONLY");
  assert.equal(health(readOnly).overall, "DEGRADED");
});

test("hook_degraded_mode_test: incomplete event coverage cannot remain FULL", () => {
  const report = probeHostCapabilities(request({
    observedHookEvents: ["SessionStart", "PostToolUse"],
  }));

  assert.equal(report.mode, "DEGRADED");
  assert.equal(report.capabilities.plugin_hooks.state, "UNKNOWN");
  assert.equal(
    report.capabilities.plugin_hooks.limitations.includes("UNOBSERVED_HOOK_EVENT:PreToolUse"),
    true,
  );
});

test("hook_degraded_mode_test: re-trust debt is visible in health and cannot be masked by FULL", () => {
  const changedTrust = trust({
    hookDefinitions: [{ hookId: "hooks.json", observedHash: `sha256:${"b".repeat(64)}` }],
  });
  const report = probeHostCapabilities(request({ hookTrust: changedTrust }));
  const pluginHealth = health(report);

  assert.equal(report.mode, "DEGRADED");
  assert.equal(report.capabilities.plugin_hooks.state, "UNKNOWN");
  assert.equal(pluginHealth.overall, "DEGRADED");
  assert.equal(pluginHealth.checks.some((check) => check.check_id === "hooks.trust"), true);
});

test("hook_degraded_mode_test: undeclared fallback and report tampering fail closed", () => {
  assert.throws(
    () => probeHostCapabilities(request({
      degradedModes: [
        ...request().degradedModes,
        { missingCapability: "invented", mode: "DEGRADED", behavior: "Guess." },
      ],
    })),
    expectCode("INVALID_INPUT"),
  );

  const report = probeHostCapabilities(request());
  const pluginHealth = health(report);
  assert.throws(
    () => validatePluginHealthReport({ ...pluginHealth, overall: "DEGRADED" }),
    expectCode("PLUGIN_HEALTH_REPORT_HASH_MISMATCH"),
  );
  assert.equal(Object.isFrozen(pluginHealth), true);
  assert.equal(Object.isFrozen(pluginHealth.checks), true);
});
