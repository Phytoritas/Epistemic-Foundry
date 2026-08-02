import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  CapabilityProbeError,
  hashHookDefinitionBytes,
  probeHostCapabilities,
  validateHostCapabilityReport,
  verifyHookTrust,
} from "../../../packages/plugin-host/src/capability-probe/capability-probe.mjs";

const repositoryRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const hookDirectory = path.join(repositoryRoot, "plugins", "epistemic-foundry", "hooks");
const hookNames = ["delegation.json", "prompt.json", "session.json", "tools.json"];
const declaredEvents = [
  "SessionStart",
  "UserPromptSubmit",
  "PermissionRequest",
  "PreToolUse",
  "PostToolUse",
  "SubagentStart",
  "SubagentStop",
  "PostCompact",
];

const definitions = () => hookNames.map((hookId) => ({
  hookId,
  observedHash: hashHookDefinitionBytes(fs.readFileSync(path.join(hookDirectory, hookId))),
}));

const trustedHooks = () => {
  const hookDefinitions = definitions();
  return verifyHookTrust({
    hookDefinitions,
    trustedHookHashes: hookDefinitions.map((entry) => entry.observedHash),
    hooksEnabled: true,
  });
};

const baseRequest = (overrides = {}) => ({
  reportId: "HCR-H04-001",
  host: "codex_cli",
  hostVersion: "2026.07",
  pluginVersion: "4.0.0",
  detectedAt: "2026-07-29T06:00:00.000Z",
  requiredCapabilities: ["artifact_hashing", "local_state"],
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
      behavior: "Require kernel receipts for hosted tools.",
    },
  ],
  observations: {
    artifact_hashing: { state: "SUPPORTED", evidence: "SHA-256 probe passed.", limitations: [] },
    local_state: { state: "SUPPORTED", evidence: "State probe passed.", limitations: [] },
    plugin_hooks: { state: "SUPPORTED", evidence: "Declared hooks were observed.", limitations: [] },
    hosted_tool_hooks: {
      state: "UNSUPPORTED",
      evidence: "Hosted search bypasses local hooks.",
      limitations: ["kernel receipts required"],
    },
  },
  hookTrust: trustedHooks(),
  declaredHookEvents: declaredEvents,
  observedHookEvents: declaredEvents,
  knownToolPaths: ["local_shell", "hosted_search"],
  observedToolPaths: ["local_shell"],
  ...overrides,
});

const expectCode = (code) => (error) =>
  error instanceof CapabilityProbeError && error.code === code;

test("hook_feature_probe_test: report is schema-shaped, hash-bound, and explicit about unobserved paths", () => {
  const report = probeHostCapabilities(baseRequest());
  const schema = JSON.parse(
    fs.readFileSync(path.join(repositoryRoot, "schemas", "host-capability-report.schema.json"), "utf8"),
  );

  assert.deepEqual(Object.keys(report).sort(), [...schema.required].sort());
  assert.equal(report.mode, "DEGRADED");
  assert.deepEqual(report.hook_events, declaredEvents);
  assert.deepEqual(report.unobserved_tool_paths, ["hosted_search"]);
  assert.equal(report.capabilities.plugin_hooks.state, "SUPPORTED");
  assert.equal(report.capabilities.hosted_tool_hooks.state, "UNSUPPORTED");
  assert.match(report.report_hash, /^sha256:[0-9a-f]{64}$/u);
  assert.deepEqual(validateHostCapabilityReport(report), report);
  assert.equal(Object.isFrozen(report), true);
  assert.equal(Object.isFrozen(report.capabilities), true);
});

test("hook_feature_probe_test: declaration order cannot change trust or report hashes", () => {
  const firstDefinitions = definitions();
  const secondDefinitions = [...firstDefinitions].reverse();
  const firstTrust = verifyHookTrust({
    hookDefinitions: firstDefinitions,
    trustedHookHashes: firstDefinitions.map((entry) => entry.observedHash),
    hooksEnabled: true,
  });
  const secondTrust = verifyHookTrust({
    hookDefinitions: secondDefinitions,
    trustedHookHashes: secondDefinitions.map((entry) => entry.observedHash).reverse(),
    hooksEnabled: true,
  });
  assert.equal(firstTrust.observedHash, secondTrust.observedHash);

  const first = probeHostCapabilities(baseRequest({ hookTrust: firstTrust }));
  const second = probeHostCapabilities(baseRequest({
    hookTrust: secondTrust,
    requiredCapabilities: ["local_state", "artifact_hashing"],
    optionalCapabilities: ["hosted_tool_hooks", "plugin_hooks"],
    declaredHookEvents: [...declaredEvents].reverse(),
    observedHookEvents: [...declaredEvents].reverse(),
    knownToolPaths: ["hosted_search", "local_shell"],
  }));
  assert.equal(first.report_hash, second.report_hash);
});

test("hook_feature_probe_test: changed active hook bytes require exact re-trust", () => {
  const current = definitions();
  const priorHashes = current.map((entry) => entry.observedHash);
  current[0] = {
    ...current[0],
    observedHash: hashHookDefinitionBytes(Buffer.from('{"changed":true}\n', "utf8")),
  };
  const trust = verifyHookTrust({
    hookDefinitions: current,
    trustedHookHashes: priorHashes,
    hooksEnabled: true,
  });

  assert.equal(trust.retrustRequired, true);
  assert.deepEqual(trust.changedHooks, ["delegation.json"]);
  assert.equal(trust.state, "UNKNOWN");
  assert.equal(trust.limitations.includes("HOOK_RETRUST_REQUIRED"), true);

  const report = probeHostCapabilities(baseRequest({ hookTrust: trust }));
  assert.equal(report.capabilities.plugin_hooks.state, "UNKNOWN");
  assert.equal(report.capabilities.plugin_hooks.limitations.includes("HOOK_RETRUST_REQUIRED"), true);
  assert.equal(report.mode, "DEGRADED");
});

test("hook_feature_probe_test: removed hook hashes also invalidate prior trust", () => {
  const current = definitions();
  const removed = current.pop();
  const trust = verifyHookTrust({
    hookDefinitions: current,
    trustedHookHashes: [...current.map((entry) => entry.observedHash), removed.observedHash],
    hooksEnabled: true,
  });

  assert.equal(trust.state, "UNKNOWN");
  assert.equal(trust.retrustRequired, true);
  assert.deepEqual(trust.staleTrustedHashes, [removed.observedHash]);
  assert.equal(trust.limitations.includes("HOOK_RETRUST_REQUIRED"), true);
});

test("hook_feature_probe_test: removing every formerly trusted hook remains explicit", () => {
  const priorHashes = definitions().map((entry) => entry.observedHash);
  const trust = verifyHookTrust({
    hookDefinitions: [],
    trustedHookHashes: priorHashes,
    hooksEnabled: true,
  });

  assert.equal(trust.state, "UNSUPPORTED");
  assert.equal(trust.retrustRequired, true);
  assert.equal(trust.limitations.includes("NO_ACTIVE_HOOK_DEFINITIONS"), true);
  assert.equal(trust.limitations.includes("HOOK_RETRUST_REQUIRED"), true);
});

test("hook_feature_probe_test: a hook observation error cannot be weakened by trust state", () => {
  const current = definitions();
  const trust = verifyHookTrust({
    hookDefinitions: current,
    trustedHookHashes: current.slice(1).map((entry) => entry.observedHash),
    hooksEnabled: true,
  });
  const observations = {
    ...baseRequest().observations,
    plugin_hooks: {
      state: "ERROR",
      evidence: "The bounded hook execution probe crashed.",
      limitations: ["HOOK_EXECUTION_PROBE_ERROR"],
    },
  };
  const report = probeHostCapabilities(baseRequest({
    hookTrust: trust,
    observations,
    observedHookEvents: declaredEvents.slice(1),
  }));

  assert.equal(report.capabilities.plugin_hooks.state, "ERROR");
  assert.equal(
    report.capabilities.plugin_hooks.evidence,
    "The bounded hook execution probe crashed.",
  );
  assert.equal(report.capabilities.plugin_hooks.limitations.includes("HOOK_RETRUST_REQUIRED"), true);
  assert.equal(
    report.capabilities.plugin_hooks.limitations.includes("UNOBSERVED_HOOK_EVENT:SessionStart"),
    true,
  );
  assert.equal(report.mode, "DEGRADED");
});

test("hook_feature_probe_test: disabled changed hooks retain re-trust debt", () => {
  const hookDefinitions = definitions();
  const priorHashes = hookDefinitions.map((entry) => entry.observedHash);
  hookDefinitions[0] = {
    ...hookDefinitions[0],
    observedHash: hashHookDefinitionBytes(Buffer.from('{"disabled-change":true}\n', "utf8")),
  };
  const trust = verifyHookTrust({
    hookDefinitions,
    trustedHookHashes: priorHashes,
    hooksEnabled: false,
  });
  const report = probeHostCapabilities(baseRequest({
    hookTrust: trust,
    knownToolPaths: ["local_shell"],
    observedToolPaths: ["local_shell"],
    observations: {
      ...baseRequest().observations,
      hosted_tool_hooks: { state: "SUPPORTED", evidence: "Hosted hook probe passed.", limitations: [] },
    },
  }));

  assert.equal(report.capabilities.plugin_hooks.state, "DISABLED");
  assert.equal(report.capabilities.plugin_hooks.limitations.includes("HOOKS_DISABLED"), true);
  assert.equal(report.capabilities.plugin_hooks.limitations.includes("HOOK_RETRUST_REQUIRED"), true);
  assert.equal(
    report.capabilities.plugin_hooks.limitations.includes("UNTRUSTED_ACTIVE_HOOK:delegation.json"),
    true,
  );
  assert.equal(report.mode, "DEGRADED");
});

test("hook_feature_probe_test: duplicate active hook hashes fail closed", () => {
  assert.throws(
    () => verifyHookTrust({
      hookDefinitions: [
        { hookId: "first.json", observedHash: definitions()[0].observedHash },
        { hookId: "second.json", observedHash: definitions()[0].observedHash },
      ],
      trustedHookHashes: [definitions()[0].observedHash],
      hooksEnabled: true,
    }),
    expectCode("INVALID_INPUT"),
  );
});

test("hook_feature_probe_test: missing observations fail closed to UNKNOWN rather than optimistic support", () => {
  const observations = { ...baseRequest().observations };
  delete observations.hosted_tool_hooks;
  const report = probeHostCapabilities(baseRequest({ observations }));

  assert.equal(report.capabilities.hosted_tool_hooks.state, "UNKNOWN");
  assert.equal(
    report.capabilities.hosted_tool_hooks.limitations.includes("CAPABILITY_OBSERVATION_MISSING"),
    true,
  );
  assert.notEqual(report.mode, "FULL");
});

test("hook_feature_probe_test: empty event and tool scopes never prove FULL coverage", () => {
  const report = probeHostCapabilities(baseRequest({
    declaredHookEvents: [],
    observedHookEvents: [],
    knownToolPaths: [],
    observedToolPaths: [],
    observations: {
      ...baseRequest().observations,
      hosted_tool_hooks: { state: "SUPPORTED", evidence: "No bounded path was tested.", limitations: [] },
    },
  }));

  assert.equal(report.mode, "DEGRADED");
  assert.equal(report.capabilities.plugin_hooks.state, "UNKNOWN");
  assert.equal(
    report.capabilities.plugin_hooks.limitations.includes("HOOK_EVENT_COVERAGE_SCOPE_EMPTY"),
    true,
  );
  assert.equal(report.capabilities.hosted_tool_hooks.state, "UNKNOWN");
  assert.equal(
    report.capabilities.hosted_tool_hooks.limitations.includes("TOOL_COVERAGE_SCOPE_EMPTY"),
    true,
  );
});

test("hook_feature_probe_test: unsupported claims, forged trust, and hostile inputs fail closed", () => {
  assert.throws(
    () => probeHostCapabilities(baseRequest({ hookTrust: { state: "SUPPORTED" } })),
    expectCode("UNVERIFIED_HOOK_TRUST"),
  );
  assert.throws(
    () => probeHostCapabilities(baseRequest({
      observations: {
        ...baseRequest().observations,
        plugin_hooks: { state: "SUPPORTED", evidence: "" },
      },
    })),
    expectCode("INVALID_INPUT"),
  );
  assert.throws(
    () => probeHostCapabilities(baseRequest({
      observations: {
        ...baseRequest().observations,
        invented_feature: { state: "SUPPORTED", evidence: "Profile name says so." },
      },
    })),
    expectCode("UNDECLARED_CAPABILITY"),
  );

  let getterRan = false;
  const hostile = baseRequest();
  Object.defineProperty(hostile, "host", {
    enumerable: true,
    get() {
      getterRan = true;
      return "codex_cli";
    },
  });
  assert.throws(() => probeHostCapabilities(hostile), expectCode("INVALID_INPUT"));
  assert.equal(getterRan, false);
});
