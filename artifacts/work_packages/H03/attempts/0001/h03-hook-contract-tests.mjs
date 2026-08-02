import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const attemptDirectory = path.dirname(fileURLToPath(import.meta.url));
const repositoryRoot = path.resolve(attemptDirectory, "../../../../..");

const readJson = (relativePath) =>
  JSON.parse(fs.readFileSync(path.join(repositoryRoot, relativePath), "utf8"));

const toolsPath = "plugins/epistemic-foundry/hooks/tools.json";
const delegationPath = "plugins/epistemic-foundry/hooks/delegation.json";
const blueprintToolsPath =
  "plugin_blueprint/epistemic-foundry/hooks/tools.json";
const blueprintDelegationPath =
  "plugin_blueprint/epistemic-foundry/hooks/delegation.json";

const expectedTools = {
  hooks: {
    PermissionRequest: [
      {
        hooks: [
          {
            type: "command",
            command:
              'node "${PLUGIN_ROOT}/dist/hook-runner.mjs" permission-request',
            timeout: 12,
            statusMessage:
              "(Epistemic Foundry) Checking authority and capability",
          },
        ],
        matcher: "Bash|apply_patch|mcp__.*",
      },
    ],
    PreToolUse: [
      {
        hooks: [
          {
            type: "command",
            command: 'node "${PLUGIN_ROOT}/dist/hook-runner.mjs" pre-tool-use',
            timeout: 12,
            statusMessage: "(Epistemic Foundry) Applying tool guardrails",
          },
        ],
        matcher: "Bash|apply_patch|Edit|Write|mcp__.*|Agent",
      },
    ],
    PostToolUse: [
      {
        hooks: [
          {
            type: "command",
            command: 'node "${PLUGIN_ROOT}/dist/hook-runner.mjs" post-tool-use',
            timeout: 15,
            statusMessage: "(Epistemic Foundry) Capturing effect receipts",
          },
        ],
        matcher: "Bash|apply_patch|Edit|Write|mcp__.*|Agent",
      },
    ],
  },
};

const expectedDelegation = {
  hooks: {
    SubagentStart: [
      {
        hooks: [
          {
            type: "command",
            command: 'node "${PLUGIN_ROOT}/dist/hook-runner.mjs" subagent-start',
            timeout: 8,
            statusMessage: "(Epistemic Foundry) Binding RoleSpec",
          },
        ],
        matcher: ".*",
      },
    ],
    SubagentStop: [
      {
        hooks: [
          {
            type: "command",
            command: 'node "${PLUGIN_ROOT}/dist/hook-runner.mjs" subagent-stop',
            timeout: 15,
            statusMessage: "(Epistemic Foundry) Validating ResultEnvelope",
          },
        ],
        matcher: ".*",
      },
    ],
  },
};

const clone = (value) => structuredClone(value);

const requireExactKeys = (value, expectedKeys, label) => {
  assert.equal(value !== null && typeof value === "object", true, `${label} object`);
  assert.deepEqual(Object.keys(value).sort(), [...expectedKeys].sort(), `${label} keys`);
};

const validateCommand = (candidate, expected, maximumTimeout, label) => {
  requireExactKeys(candidate, ["type", "command", "timeout", "statusMessage"], label);
  assert.equal(candidate.type, "command", `${label} type`);
  assert.equal(candidate.command, expected.command, `${label} command`);
  assert.equal(Number.isSafeInteger(candidate.timeout), true, `${label} integer timeout`);
  assert.equal(candidate.timeout > 0, true, `${label} positive timeout`);
  assert.equal(candidate.timeout <= maximumTimeout, true, `${label} bounded timeout`);
  assert.equal(candidate.timeout, expected.timeout, `${label} canonical timeout`);
  assert.equal(candidate.statusMessage, expected.statusMessage, `${label} status message`);
  assert.match(candidate.command, /^node "\$\{PLUGIN_ROOT\}\//u, `${label} plugin-root path`);
};

const validateTools = (candidate) => {
  requireExactKeys(candidate, ["hooks"], "tool bundle");
  requireExactKeys(
    candidate.hooks,
    ["PermissionRequest", "PreToolUse", "PostToolUse"],
    "tool events",
  );
  const eventContract = {
    PermissionRequest: {
      matcher: "Bash|apply_patch|mcp__.*",
      timeout: 12,
    },
    PreToolUse: {
      matcher: "Bash|apply_patch|Edit|Write|mcp__.*|Agent",
      timeout: 12,
    },
    PostToolUse: {
      matcher: "Bash|apply_patch|Edit|Write|mcp__.*|Agent",
      timeout: 15,
    },
  };
  for (const [eventName, contract] of Object.entries(eventContract)) {
    assert.equal(candidate.hooks[eventName].length, 1, `one ${eventName} route`);
    const route = candidate.hooks[eventName][0];
    requireExactKeys(route, ["hooks", "matcher"], `${eventName} route`);
    assert.equal(route.matcher, contract.matcher, `${eventName} matcher`);
    assert.equal(route.hooks.length, 1, `one ${eventName} command`);
    validateCommand(
      route.hooks[0],
      expectedTools.hooks[eventName][0].hooks[0],
      contract.timeout,
      `${eventName} command`,
    );
  }
  assert.equal(
    candidate.hooks.PreToolUse[0].matcher,
    candidate.hooks.PostToolUse[0].matcher,
    "observed mutating tools have matching pre/post coverage",
  );
  return true;
};

const validateDelegation = (candidate) => {
  requireExactKeys(candidate, ["hooks"], "delegation bundle");
  requireExactKeys(candidate.hooks, ["SubagentStart", "SubagentStop"], "delegation events");
  const eventContract = {
    SubagentStart: { timeout: 8 },
    SubagentStop: { timeout: 15 },
  };
  for (const [eventName, contract] of Object.entries(eventContract)) {
    assert.equal(candidate.hooks[eventName].length, 1, `one ${eventName} route`);
    const route = candidate.hooks[eventName][0];
    requireExactKeys(route, ["hooks", "matcher"], `${eventName} route`);
    assert.equal(route.matcher, ".*", `${eventName} observes every subagent identity`);
    assert.equal(route.hooks.length, 1, `one ${eventName} command`);
    validateCommand(
      route.hooks[0],
      expectedDelegation.hooks[eventName][0].hooks[0],
      contract.timeout,
      `${eventName} command`,
    );
  }
  assert.match(
    candidate.hooks.SubagentStart[0].hooks[0].statusMessage,
    /RoleSpec/u,
    "start binds RoleSpec",
  );
  assert.match(
    candidate.hooks.SubagentStop[0].hooks[0].statusMessage,
    /ResultEnvelope/u,
    "stop validates ResultEnvelope",
  );
  return true;
};

test("tool_hook_policy_test: canonical permission, pre-tool, and receipt routes are exact", () => {
  const observed = readJson(toolsPath);
  assert.deepEqual(observed, expectedTools);
  assert.equal(validateTools(observed), true);
});

test("tool_hook_policy_test: installed tool declaration is byte-equivalent to the authority blueprint", () => {
  const installed = fs.readFileSync(path.join(repositoryRoot, toolsPath));
  const blueprint = fs.readFileSync(path.join(repositoryRoot, blueprintToolsPath));
  assert.deepEqual(installed, blueprint);
});

test("tool_hook_policy_test: missing policy or receipt coverage fails closed", () => {
  for (const eventName of ["PermissionRequest", "PreToolUse", "PostToolUse"]) {
    const mutation = clone(expectedTools);
    delete mutation.hooks[eventName];
    assert.throws(() => validateTools(mutation));
  }

  const asymmetricCoverage = clone(expectedTools);
  asymmetricCoverage.hooks.PostToolUse[0].matcher = "Bash";
  assert.throws(() => validateTools(asymmetricCoverage));
});

test("tool_hook_policy_test: timeout expansion, direct allow, and extra events fail closed", () => {
  const timeoutExpansion = clone(expectedTools);
  timeoutExpansion.hooks.PreToolUse[0].hooks[0].timeout = 13;
  assert.throws(() => validateTools(timeoutExpansion));

  const directAllow = clone(expectedTools);
  directAllow.hooks.PermissionRequest[0].hooks[0].command =
    'node "${PLUGIN_ROOT}/dist/hook-runner.mjs" allow';
  assert.throws(() => validateTools(directAllow));

  const extraEvent = clone(expectedTools);
  extraEvent.hooks.Stop = clone(extraEvent.hooks.PostToolUse);
  assert.throws(() => validateTools(extraEvent));
});

test("subagent_result_gate_test: canonical start and stop bindings cover every subagent", () => {
  const observed = readJson(delegationPath);
  assert.deepEqual(observed, expectedDelegation);
  assert.equal(validateDelegation(observed), true);
});

test("subagent_result_gate_test: installed delegation declaration is byte-equivalent to the authority blueprint", () => {
  const installed = fs.readFileSync(path.join(repositoryRoot, delegationPath));
  const blueprint = fs.readFileSync(path.join(repositoryRoot, blueprintDelegationPath));
  assert.deepEqual(installed, blueprint);
});

test("subagent_result_gate_test: missing start or stop coverage and partial matchers fail closed", () => {
  for (const eventName of ["SubagentStart", "SubagentStop"]) {
    const mutation = clone(expectedDelegation);
    delete mutation.hooks[eventName];
    assert.throws(() => validateDelegation(mutation));
  }

  const partialMatcher = clone(expectedDelegation);
  partialMatcher.hooks.SubagentStop[0].matcher = "reviewer";
  assert.throws(() => validateDelegation(partialMatcher));
});

test("subagent_result_gate_test: handler substitution and premature runtime claims fail closed", () => {
  const bypass = clone(expectedDelegation);
  bypass.hooks.SubagentStop[0].hooks[0].command =
    'node "${PLUGIN_ROOT}/dist/hook-runner.mjs" accept-partial-result';
  assert.throws(() => validateDelegation(bypass));

  const manifest = readJson("plugins/epistemic-foundry/.codex-plugin/plugin.json");
  assert.equal(Object.hasOwn(manifest, "hooks"), false);
  assert.deepEqual(manifest.interface.capabilities, []);
  assert.equal(
    fs.existsSync(path.join(repositoryRoot, "plugins/epistemic-foundry/dist/hook-runner.mjs")),
    false,
  );
});
