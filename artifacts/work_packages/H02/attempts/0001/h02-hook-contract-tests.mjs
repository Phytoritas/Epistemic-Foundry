import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const attemptDirectory = path.dirname(fileURLToPath(import.meta.url));
const repositoryRoot = path.resolve(attemptDirectory, "../../../../..");

const readJson = (relativePath) =>
  JSON.parse(fs.readFileSync(path.join(repositoryRoot, relativePath), "utf8"));

const sessionPath = "plugins/epistemic-foundry/hooks/session.json";
const promptPath = "plugins/epistemic-foundry/hooks/prompt.json";
const blueprintSessionPath =
  "plugin_blueprint/epistemic-foundry/hooks/session.json";
const blueprintPromptPath =
  "plugin_blueprint/epistemic-foundry/hooks/prompt.json";

const expectedSession = {
  hooks: {
    SessionStart: [
      {
        hooks: [
          {
            type: "command",
            command:
              'node "${PLUGIN_ROOT}/dist/hook-runner.mjs" session-start',
            timeout: 15,
            statusMessage:
              "(Epistemic Foundry) Probing capabilities and resuming FORGE",
          },
        ],
        matcher: "startup|resume|clear|compact",
      },
    ],
    PostCompact: [
      {
        hooks: [
          {
            type: "command",
            command:
              'node "${PLUGIN_ROOT}/dist/hook-runner.mjs" post-compact',
            timeout: 15,
            statusMessage:
              "(Epistemic Foundry) Rebuilding the Context Capsule",
          },
        ],
        matcher: "manual|auto",
      },
    ],
  },
};

const expectedPrompt = {
  hooks: {
    UserPromptSubmit: [
      {
        hooks: [
          {
            type: "command",
            command:
              'node "${PLUGIN_ROOT}/dist/hook-runner.mjs" user-prompt-submit',
            timeout: 8,
            statusMessage:
              "(Epistemic Foundry) Classifying research intent",
          },
        ],
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
  assert.doesNotMatch(
    candidate.command,
    /(?:^|\s)(?:transition|promote|approve|commit|write-state|set-phase)(?:\s|$)/u,
    `${label} has no direct authority command`,
  );
};

const validateSession = (candidate) => {
  requireExactKeys(candidate, ["hooks"], "session bundle");
  requireExactKeys(candidate.hooks, ["SessionStart", "PostCompact"], "session events");
  assert.equal(candidate.hooks.SessionStart.length, 1, "one SessionStart route");
  assert.equal(candidate.hooks.PostCompact.length, 1, "one PostCompact route");

  const startRoute = candidate.hooks.SessionStart[0];
  requireExactKeys(startRoute, ["hooks", "matcher"], "SessionStart route");
  assert.equal(startRoute.matcher, "startup|resume|clear|compact");
  assert.equal(startRoute.hooks.length, 1, "one SessionStart command");
  validateCommand(
    startRoute.hooks[0],
    expectedSession.hooks.SessionStart[0].hooks[0],
    15,
    "SessionStart command",
  );

  const compactRoute = candidate.hooks.PostCompact[0];
  requireExactKeys(compactRoute, ["hooks", "matcher"], "PostCompact route");
  assert.equal(compactRoute.matcher, "manual|auto");
  assert.equal(compactRoute.hooks.length, 1, "one PostCompact command");
  validateCommand(
    compactRoute.hooks[0],
    expectedSession.hooks.PostCompact[0].hooks[0],
    15,
    "PostCompact command",
  );
  return true;
};

const validatePrompt = (candidate) => {
  requireExactKeys(candidate, ["hooks"], "prompt bundle");
  requireExactKeys(candidate.hooks, ["UserPromptSubmit"], "prompt events");
  assert.equal(candidate.hooks.UserPromptSubmit.length, 1, "one prompt route");
  const route = candidate.hooks.UserPromptSubmit[0];
  requireExactKeys(route, ["hooks"], "prompt route");
  assert.equal(route.hooks.length, 1, "one prompt command");
  validateCommand(
    route.hooks[0],
    expectedPrompt.hooks.UserPromptSubmit[0].hooks[0],
    8,
    "UserPromptSubmit command",
  );

  const serialized = JSON.stringify(candidate);
  for (const forbidden of [
    '"decision"',
    '"action_intent_id"',
    '"effect_receipt_id"',
    '"phase"',
    '"revision"',
    '"state"',
  ]) {
    assert.equal(serialized.includes(forbidden), false, `prompt excludes ${forbidden}`);
  }
  return true;
};

test("session_hook_test: canonical session lifecycle routes are exact and bounded", () => {
  const observed = readJson(sessionPath);
  assert.deepEqual(observed, expectedSession);
  assert.equal(validateSession(observed), true);
});

test("session_hook_test: installed declaration is byte-equivalent to the authority blueprint", () => {
  const installed = fs.readFileSync(path.join(repositoryRoot, sessionPath));
  const blueprint = fs.readFileSync(path.join(repositoryRoot, blueprintSessionPath));
  assert.deepEqual(installed, blueprint);
});

test("session_hook_test: timeout expansion and extra lifecycle work fail closed", () => {
  const timeoutExpansion = clone(expectedSession);
  timeoutExpansion.hooks.SessionStart[0].hooks[0].timeout = 16;
  assert.throws(() => validateSession(timeoutExpansion));

  const extraEvent = clone(expectedSession);
  extraEvent.hooks.SessionEnd = clone(extraEvent.hooks.SessionStart);
  assert.throws(() => validateSession(extraEvent));

  const directTransition = clone(expectedSession);
  directTransition.hooks.SessionStart[0].hooks[0].command =
    'node "${PLUGIN_ROOT}/dist/hook-runner.mjs" transition set-phase';
  assert.throws(() => validateSession(directTransition));
});

test("session_hook_test: current package shell does not prematurely claim hook runtime integration", () => {
  const manifest = readJson("plugins/epistemic-foundry/.codex-plugin/plugin.json");
  assert.equal(Object.hasOwn(manifest, "hooks"), false);
  assert.deepEqual(manifest.interface.capabilities, []);
  assert.equal(
    fs.existsSync(path.join(repositoryRoot, "plugins/epistemic-foundry/dist/hook-runner.mjs")),
    false,
  );
});

test("prompt_hook_test: prompt intake is one bounded classification request", () => {
  const observed = readJson(promptPath);
  assert.deepEqual(observed, expectedPrompt);
  assert.equal(validatePrompt(observed), true);
});

test("prompt_hook_test: installed declaration is byte-equivalent to the authority blueprint", () => {
  const installed = fs.readFileSync(path.join(repositoryRoot, promptPath));
  const blueprint = fs.readFileSync(path.join(repositoryRoot, blueprintPromptPath));
  assert.deepEqual(installed, blueprint);
});

test("prompt_hook_test: direct state mutation and authority fields fail closed", () => {
  const directCommit = clone(expectedPrompt);
  directCommit.hooks.UserPromptSubmit[0].hooks[0].command =
    'node "${PLUGIN_ROOT}/dist/hook-runner.mjs" commit set-phase';
  assert.throws(() => validatePrompt(directCommit));

  const authorityField = clone(expectedPrompt);
  authorityField.hooks.UserPromptSubmit[0].decision = "ALLOW";
  assert.throws(() => validatePrompt(authorityField));

  const timeoutExpansion = clone(expectedPrompt);
  timeoutExpansion.hooks.UserPromptSubmit[0].hooks[0].timeout = 9;
  assert.throws(() => validatePrompt(timeoutExpansion));
});

test("prompt_hook_test: prompt declaration cannot register tool, completion, or delegation events", () => {
  for (const eventName of ["PreToolUse", "Stop", "SubagentStart"]) {
    const mutation = clone(expectedPrompt);
    mutation.hooks[eventName] = clone(mutation.hooks.UserPromptSubmit);
    assert.throws(() => validatePrompt(mutation));
  }
});
