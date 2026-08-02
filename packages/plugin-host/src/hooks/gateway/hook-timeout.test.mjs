import assert from "node:assert/strict";
import test from "node:test";
import { setTimeout as delay } from "node:timers/promises";

import {
  HookGatewayError,
  canonicalizeHookJson,
  dispatchHookEvent,
  validateHookEventEnvelope,
} from "./hook-gateway.mjs";

const request = () => ({
  event_id: "HEE-H01-TIMEOUT-001",
  host: "claude",
  event_type: "PermissionRequest",
  session_id: "FS-H01-002",
  tool_name: "filesystem_write",
  received_at: "2026-07-29T04:01:00.000Z",
  raw_payload: { path: "workspace/output.json", operation: "write" },
  coverage: "PARTIAL",
});

const validDecision = () => ({
  decision: "BLOCK",
  reasons: ["CAPABILITY_NOT_PROVEN"],
  action_intent_id: null,
  effect_receipt_id: null,
});

const expectCode = (code) => (error) => error instanceof HookGatewayError && error.code === code;

test("hook_timeout_test: a non-settling decision returns a bounded fail-closed envelope", async () => {
  const started = Date.now();
  let signal;
  const envelope = await dispatchHookEvent(request(), {
    timeout_ms: 20,
    decide(_input, observedSignal) {
      signal = observedSignal;
      return new Promise(() => {});
    },
  });
  const elapsedMs = Date.now() - started;

  assert.equal(envelope.decision, "ERROR");
  assert.deepEqual(envelope.reasons, ["HOOK_DECISION_TIMEOUT"]);
  assert.equal(envelope.action_intent_id, null);
  assert.equal(envelope.effect_receipt_id, null);
  assert.equal(envelope.coverage, "PARTIAL");
  assert.equal(signal.aborted, true);
  assert.equal(elapsedMs >= 10, true, `timeout returned too early: ${elapsedMs}ms`);
  assert.equal(elapsedMs < 2_000, true, `timeout was not bounded: ${elapsedMs}ms`);
  assert.deepEqual(validateHookEventEnvelope(envelope), envelope);
});

test("hook_timeout_test: late completion cannot mutate the sealed timeout result", async () => {
  let resolveDecision;
  const pending = new Promise((resolve) => {
    resolveDecision = resolve;
  });
  const envelope = await dispatchHookEvent(request(), {
    timeout_ms: 15,
    decide: () => pending,
  });
  const before = canonicalizeHookJson(envelope);

  resolveDecision(validDecision());
  await delay(30);

  assert.equal(canonicalizeHookJson(envelope), before);
  assert.equal(envelope.decision, "ERROR");
  assert.equal(Object.isFrozen(envelope), true);
  assert.equal(Object.isFrozen(envelope.reasons), true);
});

test("hook_timeout_test: callback rejection is explicit and does not leak its message", async () => {
  const secret = "sensitive-callback-detail";
  const envelope = await dispatchHookEvent(request(), {
    timeout_ms: 1_000,
    decide: () => Promise.reject(new Error(secret)),
  });

  assert.equal(envelope.decision, "ERROR");
  assert.deepEqual(envelope.reasons, ["HOOK_DECISION_CALLBACK_ERROR"]);
  assert.equal(canonicalizeHookJson(envelope).includes(secret), false);
  assert.deepEqual(validateHookEventEnvelope(envelope), envelope);
});

test("hook_timeout_test: a fast canonical decision wins without timeout rewriting", async () => {
  let signal;
  const envelope = await dispatchHookEvent(request(), {
    timeout_ms: 1_000,
    decide: async (_input, observedSignal) => {
      signal = observedSignal;
      await Promise.resolve();
      return validDecision();
    },
  });

  assert.equal(envelope.decision, "BLOCK");
  assert.deepEqual(envelope.reasons, ["CAPABILITY_NOT_PROVEN"]);
  assert.equal(signal.aborted, false);
});

test("hook_timeout_test: timeout bounds are validated before callback invocation", async () => {
  for (const timeout_ms of [0, -1, 1.5, Number.NaN, Number.POSITIVE_INFINITY, 2_147_483_648]) {
    let called = false;
    await assert.rejects(
      dispatchHookEvent(request(), {
        timeout_ms,
        decide() {
          called = true;
          return validDecision();
        },
      }),
      expectCode("INVALID_INPUT"),
    );
    assert.equal(called, false);
  }
});
