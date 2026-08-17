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

test("installed Forge mutation dispatch owns exactly the three durable FORGE routes", () => {
  assert.deepEqual(installedForgeMutationToolNames(), [
    "foundry.work.classify",
    "foundry.session.open",
    "foundry.session.transition",
  ]);
});

test("the public installed write surface cannot activate before every T02 runtime is backed", () => {
  const installed = new Set(installedForgeMutationToolNames());
  const canonical = new Set(mutatingToolDescriptors().map(({ name }) => name));
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
  const dispatch = createInstalledForgeMutationDispatch({
    classificationWorker: null,
    openWorker: null,
    transitionWorker: worker(calls),
  });

  const result = dispatch.execute(
    "foundry.session.transition",
    context(transitionArguments),
  );

  assert.deepEqual(result, { ok: true });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].tool_name, "foundry.session.transition");
  assert.equal(calls[0].handler_operation, "mutate_session_transition");
  assert.equal(calls[0].capability, "mcp.write.session");
  assert.equal(calls[0].expected_revision_required, true);
  assert.deepEqual(calls[0].validated_arguments, transitionArguments);
  assert.deepEqual(calls[0].auth, auth);
});

test("session OPEN is independently routed and never falls back to transition", () => {
  const openCalls = [];
  const transitionCalls = [];
  const dispatch = createInstalledForgeMutationDispatch({
    classificationWorker: null,
    openWorker: worker(openCalls),
    transitionWorker: worker(transitionCalls),
  });

  dispatch.execute("foundry.session.open", context(openArguments));

  assert.equal(openCalls.length, 1);
  assert.equal(transitionCalls.length, 0);
  assert.equal(openCalls[0].tool_name, "foundry.session.open");
  assert.equal(openCalls[0].handler_operation, "mutate_session_open");
  assert.equal(openCalls[0].expected_revision_required, false);
});

test("an omitted route worker is explicit UNAVAILABLE rather than a sibling fallback", () => {
  const transitionCalls = [];
  const dispatch = createInstalledForgeMutationDispatch({
    classificationWorker: null,
    openWorker: null,
    transitionWorker: worker(transitionCalls),
  });

  assert.throws(
    () => dispatch.execute("foundry.session.open", context(openArguments)),
    (error) => assertDispatchError(error, "INSTALLED_FORGE_MUTATION_UNAVAILABLE"),
  );
  assert.equal(transitionCalls.length, 0);
});

test("T02 tools without a canonical installed runtime remain explicit UNAVAILABLE", () => {
  const dispatch = createInstalledForgeMutationDispatch({
    classificationWorker: null,
    openWorker: null,
    transitionWorker: null,
  });

  const unbacked = mutatingToolDescriptors()
    .map(({ name }) => name)
    .filter((name) => !installedForgeMutationToolNames().includes(name));
  assert.equal(unbacked.length, 8);

  for (const toolName of unbacked) {
    assert.throws(
      () => dispatch.execute(toolName, null),
      (error) => assertDispatchError(error, "INSTALLED_FORGE_MUTATION_UNAVAILABLE"),
      toolName,
    );
  }
});

test("runtime and dispatch contexts reject proxies and noncanonical fields", () => {
  assert.throws(
    () => createInstalledForgeMutationDispatch(new Proxy({}, {})),
    (error) => assertDispatchError(error, "INSTALLED_FORGE_MUTATION_INPUT_INVALID"),
  );

  const dispatch = createInstalledForgeMutationDispatch({
    classificationWorker: null,
    openWorker: null,
    transitionWorker: worker([]),
  });
  assert.throws(
    () => dispatch.execute(
      "foundry.session.transition",
      { ...context(transitionArguments), extra: true },
    ),
    (error) => assertDispatchError(error, "INSTALLED_FORGE_MUTATION_INPUT_INVALID"),
  );
});

test("prototype-looking tool names cannot escape the closed route table", () => {
  const dispatch = createInstalledForgeMutationDispatch({
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
  const dispatch = createInstalledForgeMutationDispatch({
    classificationWorker: null,
    openWorker: null,
    transitionWorker: Object.freeze({
      execute() {
        return Promise.resolve({ ok: true });
      },
    }),
  });

  assert.throws(
    () => dispatch.execute("foundry.session.transition", context(transitionArguments)),
    (error) => assertDispatchError(error, "INSTALLED_FORGE_MUTATION_RUNTIME_INVALID"),
  );
});
