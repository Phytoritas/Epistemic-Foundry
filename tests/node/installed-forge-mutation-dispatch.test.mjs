import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import {
  InstalledForgeMutationDispatchError,
  createInstalledForgeMutationDispatch,
  installedForgeMutationToolNames,
} from "../../packages/foundry-kernel/src/forge/session/installed-forge-mutation-dispatch.mjs";
import {
  mutatingToolDescriptors,
} from "../../packages/plugin-host/src/mcp/write/catalog-set.mjs";

const HASH_A = `sha256:${"a".repeat(64)}`;
const GENERATED_AT = "2026-08-17T08:00:00.000Z";
const INSTALLED_MCP_SOURCE = fs.readFileSync(
  new URL("../../plugins/epistemic-foundry/src/mcp-server.mjs", import.meta.url),
  "utf8",
);
const T02_DESCRIPTORS = mutatingToolDescriptors();

function oneDescriptor(predicate, label) {
  const matches = T02_DESCRIPTORS.filter(predicate);
  assert.equal(matches.length, 1, `${label} must resolve exactly one T02 descriptor`);
  return matches[0];
}

const classificationDescriptor = oneDescriptor(
  (descriptor) => descriptor.annotations.capability === "mcp.write.classification",
  "classification route",
);
const sessionDescriptors = T02_DESCRIPTORS.filter(
  (descriptor) => descriptor.annotations.capability === "mcp.write.session",
);
assert.equal(sessionDescriptors.length, 2);
const openDescriptor = oneDescriptor(
  (descriptor) =>
    descriptor.annotations.capability === "mcp.write.session" &&
    descriptor.inputSchema.properties.expected_revision.type === "null",
  "session OPEN route",
);
const transitionDescriptor = oneDescriptor(
  (descriptor) =>
    descriptor.annotations.capability === "mcp.write.session" &&
    descriptor.inputSchema.properties.expected_revision.type === "string",
  "session transition route",
);
const ROUTE_NAMES = Object.freeze({
  classificationToolName: classificationDescriptor.name,
  openToolName: openDescriptor.name,
  transitionToolName: transitionDescriptor.name,
});

const auth = Object.freeze({
  principal_id: "AG-TEST",
  workspace_id: "WS-TEST",
});

const transitionArguments = Object.freeze({
  workspace_id: "WS-TEST",
  dry_run: true,
  expected_revision: "7",
  idempotency_key: "transition-idem-1",
  approval_record_ids: Object.freeze([]),
  target_ref: "SESSION-TEST",
  arguments: Object.freeze({
    session_id: "SESSION-TEST",
    to_phase: "FRAME",
    transition_request_artifact_id: "FTR-TEST",
  }),
});

const openArguments = Object.freeze({
  workspace_id: "WS-TEST",
  dry_run: true,
  expected_revision: null,
  idempotency_key: "open-idem-0001",
  approval_record_ids: Object.freeze([]),
  target_ref: "SESSION-TEST",
  arguments: Object.freeze({
    session_id: "SESSION-TEST",
    classification_id: "EWC-TEST",
    corpus_snapshot_hash: HASH_A,
    actor: Object.freeze({
      actor_id: "AG-TEST",
      actor_type: "agent",
      role: "tester",
    }),
    requested_at: GENERATED_AT,
  }),
});

const context = (validatedArguments) => Object.freeze({
  auth,
  validatedArguments,
  requestId: "REQ-MCP-1",
  generatedAt: GENERATED_AT,
});

const worker = (calls, result = Object.freeze({ ok: true })) => Object.freeze({
  execute(request) {
    calls.push(request);
    return result;
  },
});

function assertDispatchError(error, code) {
  assert.equal(error instanceof InstalledForgeMutationDispatchError, true);
  assert.equal(error.code, code);
  return true;
}

function dispatchFor(runtime) {
  return createInstalledForgeMutationDispatch(runtime, ROUTE_NAMES);
}

test("Forge route names are derived from the canonical T02 descriptor projection", () => {
  assert.deepEqual(installedForgeMutationToolNames(ROUTE_NAMES), [
    classificationDescriptor.name,
    openDescriptor.name,
    transitionDescriptor.name,
  ]);
});

test("the public installed write surface cannot activate before every T02 runtime is backed", () => {
  const installed = new Set(installedForgeMutationToolNames(ROUTE_NAMES));
  const canonical = new Set(T02_DESCRIPTORS.map(({ name }) => name));
  const writeSurfaceActive = INSTALLED_MCP_SOURCE.includes(
    "./plugin-host/mcp/write/adapter.mjs",
  );

  assert.equal(canonical.size, 11);
  assert.equal(installed.size, 3);
  for (const name of installed) assert.equal(canonical.has(name), true, name);

  if (writeSurfaceActive) {
    assert.deepEqual(
      [...installed].sort(),
      [...canonical].sort(),
      "installed MCP write framing may activate only when every canonical T02 tool has a runtime route",
    );
  } else {
    assert.equal(installed.size < canonical.size, true);
  }
});

test("session transition is converted by the canonical worker request factory", () => {
  const calls = [];
  const dispatch = dispatchFor({
    classificationWorker: null,
    openWorker: null,
    transitionWorker: worker(calls),
  });

  const result = dispatch.execute(
    transitionDescriptor.name,
    context(transitionArguments),
  );

  assert.deepEqual(result, { ok: true });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].tool_name, transitionDescriptor.name);
  assert.equal(calls[0].handler_operation, "mutate_session_transition");
  assert.equal(calls[0].capability, "mcp.write.session");
  assert.equal(calls[0].expected_revision_required, true);
  assert.deepEqual(calls[0].validated_arguments, transitionArguments);
  assert.deepEqual(calls[0].auth, auth);
});

test("session OPEN is independently routed and never falls back to transition", () => {
  const openCalls = [];
  const transitionCalls = [];
  const dispatch = dispatchFor({
    classificationWorker: null,
    openWorker: worker(openCalls),
    transitionWorker: worker(transitionCalls),
  });

  dispatch.execute(openDescriptor.name, context(openArguments));

  assert.equal(openCalls.length, 1);
  assert.equal(transitionCalls.length, 0);
  assert.equal(openCalls[0].tool_name, openDescriptor.name);
  assert.equal(openCalls[0].handler_operation, "mutate_session_open");
  assert.equal(openCalls[0].expected_revision_required, false);
});

test("an omitted route worker is explicit UNAVAILABLE rather than a sibling fallback", () => {
  const transitionCalls = [];
  const dispatch = dispatchFor({
    classificationWorker: null,
    openWorker: null,
    transitionWorker: worker(transitionCalls),
  });

  assert.throws(
    () => dispatch.execute(openDescriptor.name, context(openArguments)),
    (error) => assertDispatchError(error, "INSTALLED_FORGE_MUTATION_UNAVAILABLE"),
  );
  assert.equal(transitionCalls.length, 0);
});

test("T02 tools without a canonical installed runtime remain explicit UNAVAILABLE", () => {
  const dispatch = dispatchFor({
    classificationWorker: null,
    openWorker: null,
    transitionWorker: null,
  });

  const installedNames = new Set(installedForgeMutationToolNames(ROUTE_NAMES));
  const unbacked = T02_DESCRIPTORS
    .map(({ name }) => name)
    .filter((name) => !installedNames.has(name));
  assert.equal(unbacked.length, 8);

  for (const toolName of unbacked) {
    assert.throws(
      () => dispatch.execute(toolName, null),
      (error) => assertDispatchError(error, "INSTALLED_FORGE_MUTATION_UNAVAILABLE"),
      toolName,
    );
  }
});

test("catalog route misbinding fails before a worker can execute", () => {
  const calls = [];
  const misbound = Object.freeze({
    ...ROUTE_NAMES,
    openToolName: transitionDescriptor.name,
    transitionToolName: openDescriptor.name,
  });
  const dispatch = createInstalledForgeMutationDispatch(
    {
      classificationWorker: null,
      openWorker: worker(calls),
      transitionWorker: worker(calls),
    },
    misbound,
  );

  assert.throws(
    () => dispatch.execute(transitionDescriptor.name, context(openArguments)),
    (error) => assertDispatchError(error, "INSTALLED_FORGE_MUTATION_BINDING_INVALID"),
  );
  assert.equal(calls.length, 0);
});

test("runtime, route names, and dispatch contexts reject proxies or noncanonical fields", () => {
  assert.throws(
    () => createInstalledForgeMutationDispatch(new Proxy({}, {}), ROUTE_NAMES),
    (error) => assertDispatchError(error, "INSTALLED_FORGE_MUTATION_INPUT_INVALID"),
  );
  assert.throws(
    () => createInstalledForgeMutationDispatch({}, new Proxy(ROUTE_NAMES, {})),
    (error) => assertDispatchError(error, "INSTALLED_FORGE_MUTATION_INPUT_INVALID"),
  );

  const dispatch = dispatchFor({
    classificationWorker: null,
    openWorker: null,
    transitionWorker: worker([]),
  });
  assert.throws(
    () => dispatch.execute(
      transitionDescriptor.name,
      { ...context(transitionArguments), extra: true },
    ),
    (error) => assertDispatchError(error, "INSTALLED_FORGE_MUTATION_INPUT_INVALID"),
  );
});

test("prototype-looking tool names cannot escape the closed route table", () => {
  const dispatch = dispatchFor({
    classificationWorker: null,
    openWorker: null,
    transitionWorker: null,
  });
  for (const toolName of ["__proto__", "constructor", "toString"]) {
    assert.throws(
      () => dispatch.execute(toolName, null),
      (error) => assertDispatchError(error, "INSTALLED_FORGE_MUTATION_UNAVAILABLE"),
      toolName,
    );
  }
});

test("mutation workers are a synchronous port", () => {
  const dispatch = dispatchFor({
    classificationWorker: null,
    openWorker: null,
    transitionWorker: Object.freeze({
      execute() {
        return Promise.resolve({ ok: true });
      },
    }),
  });

  assert.throws(
    () => dispatch.execute(transitionDescriptor.name, context(transitionArguments)),
    (error) => assertDispatchError(error, "INSTALLED_FORGE_MUTATION_RUNTIME_INVALID"),
  );
});
