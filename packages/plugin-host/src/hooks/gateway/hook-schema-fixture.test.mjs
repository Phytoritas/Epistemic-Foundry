import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  HOOK_COVERAGE,
  HOOK_DECISIONS,
  HOOK_EVENT_TYPES,
  HOOK_HOSTS,
  HookGatewayError,
  canonicalizeHookJson,
  dispatchHookEvent,
  sha256HookJson,
  validateHookEventEnvelope,
} from "./hook-gateway.mjs";

const repositoryRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../../..");
const schema = JSON.parse(
  fs.readFileSync(path.join(repositoryRoot, "schemas", "hook-event-envelope.schema.json"), "utf8"),
);

const fixtureRequest = (raw_payload = { zeta: [3, { beta: true, alpha: "한글" }], alpha: null }) => ({
  event_id: "HEE-H01-FIXTURE-001",
  host: "codex",
  event_type: "PreToolUse",
  session_id: "FS-H01-001",
  tool_name: "shell_command",
  received_at: "2026-07-29T04:00:00.000Z",
  raw_payload,
  coverage: "OBSERVED",
});

const allowDecision = () => ({
  decision: "ALLOW",
  reasons: ["POLICY_SCOPE_PERMITTED"],
  action_intent_id: "AI-H01-001",
  effect_receipt_id: null,
});

const assertSchemaShape = (envelope) => {
  assert.deepEqual(Object.keys(envelope).sort(), [...schema.required].sort());
  assert.deepEqual(schema.properties.host.enum, [...HOOK_HOSTS]);
  assert.deepEqual(schema.properties.event_type.enum, [...HOOK_EVENT_TYPES]);
  assert.deepEqual(schema.properties.decision.enum, [...HOOK_DECISIONS]);
  assert.deepEqual(schema.properties.coverage.enum, [...HOOK_COVERAGE]);
  assert.match(envelope.raw_payload_hash, new RegExp(schema.properties.raw_payload_hash.pattern, "u"));
  assert.match(envelope.envelope_hash, new RegExp(schema.properties.envelope_hash.pattern, "u"));
  assert.equal(typeof envelope.normalized_payload, schema.properties.normalized_payload.type);
  assert.equal(schema.additionalProperties, false);
};

const expectCode = (code) => (error) => error instanceof HookGatewayError && error.code === code;

test("hook_schema_fixture_test: canonical schema vocabulary and deterministic fixture agree", async () => {
  const envelope = await dispatchHookEvent(fixtureRequest(), {
    decide: allowDecision,
    timeout_ms: 1_000,
  });

  assertSchemaShape(envelope);
  assert.deepEqual(validateHookEventEnvelope(envelope), envelope);
  assert.equal(
    canonicalizeHookJson(envelope.normalized_payload),
    '{"alpha":null,"zeta":[3,{"alpha":"한글","beta":true}]}',
  );
  assert.equal(
    envelope.raw_payload_hash,
    "sha256:6bcbb2809863ad7b57d804d004efea47dcb5f39f31dcc0297fec7d87fe1dc931",
  );
  assert.equal(
    envelope.envelope_hash,
    "sha256:f3c3e9ee377a78379b5ac074e5ecf70d58c7ad1a7a1efcc44d53848ccdb6817d",
  );
  assert.equal(Object.isFrozen(envelope), true);
  assert.equal(Object.isFrozen(envelope.normalized_payload), true);
  assert.equal(Object.isFrozen(envelope.normalized_payload.zeta), true);

  await assert.rejects(
    dispatchHookEvent({ ...fixtureRequest(), event_id: "😀😀" }, {
      decide: allowDecision,
      timeout_ms: 1_000,
    }),
    expectCode("INVALID_INPUT"),
  );
  const threeScalarIdentifier = await dispatchHookEvent(
    { ...fixtureRequest(), event_id: "😀😀😀" },
    { decide: allowDecision, timeout_ms: 1_000 },
  );
  assert.equal(threeScalarIdentifier.event_id, "😀😀😀");
});

test("hook_schema_fixture_test: object insertion order cannot change hashes", async () => {
  const first = fixtureRequest({ z: 1, a: { d: 4, c: 3 } });
  const second = fixtureRequest({ a: { c: 3, d: 4 }, z: 1 });
  const left = await dispatchHookEvent(first, { decide: allowDecision, timeout_ms: 1_000 });
  const right = await dispatchHookEvent(second, { decide: allowDecision, timeout_ms: 1_000 });

  assert.equal(left.raw_payload_hash, right.raw_payload_hash);
  assert.equal(left.envelope_hash, right.envelope_hash);
  assert.equal(canonicalizeHookJson(left), canonicalizeHookJson(right));
});

test("hook_schema_fixture_test: the decision callback receives only an immutable canonical view", async () => {
  let observed;
  const envelope = await dispatchHookEvent(fixtureRequest(), {
    timeout_ms: 1_000,
    decide(input, signal) {
      observed = input;
      assert.equal(signal.aborted, false);
      assert.deepEqual(Object.keys(input), [
        "coverage",
        "event_id",
        "event_type",
        "host",
        "normalized_payload",
        "raw_payload_hash",
        "received_at",
        "session_id",
        "tool_name",
      ]);
      assert.equal(Object.isFrozen(input), true);
      assert.equal(Object.isFrozen(input.normalized_payload), true);
      assert.throws(() => {
        input.normalized_payload.alpha = "mutated";
      }, TypeError);
      return allowDecision();
    },
  });

  assert.notEqual(observed.normalized_payload, fixtureRequest().raw_payload);
  assert.equal(envelope.normalized_payload.alpha, null);
});

test("hook_schema_fixture_test: invalid callback output becomes an explicit schema-valid error", async () => {
  const envelope = await dispatchHookEvent(fixtureRequest(), {
    timeout_ms: 1_000,
    decide: () => ({
      decision: "ALLOW",
      reasons: [],
      action_intent_id: null,
      effect_receipt_id: null,
      hidden_authority: true,
    }),
  });

  assertSchemaShape(envelope);
  assert.equal(envelope.decision, "ERROR");
  assert.deepEqual(envelope.reasons, ["HOOK_DECISION_INVALID"]);
  assert.equal(envelope.action_intent_id, null);
  assert.equal(envelope.effect_receipt_id, null);
});

test("hook_schema_fixture_test: hostile or non-JSON payloads fail closed before decision", async () => {
  const cycle = {};
  cycle.self = cycle;
  const sparse = [];
  sparse.length = 1;
  let getterRan = false;
  const accessor = {};
  Object.defineProperty(accessor, "secret", {
    enumerable: true,
    get() {
      getterRan = true;
      return "do not read";
    },
  });
  let proxyTrapRan = false;
  const proxy = new Proxy({}, {
    ownKeys() {
      proxyTrapRan = true;
      return [];
    },
  });
  const symbolProperty = { safe: true };
  symbolProperty[Symbol("hidden")] = true;

  const invalidPayloads = [
    cycle,
    sparse,
    accessor,
    proxy,
    { value: undefined },
    { value: 1n },
    { value: Number.NaN },
    { value: Number.POSITIVE_INFINITY },
    { value: -0 },
    { value: "\ud800" },
    symbolProperty,
    Object.create({ inherited: true }),
  ];
  for (const rawPayload of invalidPayloads) {
    let called = false;
    await assert.rejects(
      dispatchHookEvent(fixtureRequest(rawPayload), {
        timeout_ms: 1_000,
        decide() {
          called = true;
          return allowDecision();
        },
      }),
      expectCode("NON_CANONICAL_JSON"),
    );
    assert.equal(called, false);
  }
  assert.equal(getterRan, false);
  assert.equal(proxyTrapRan, false);
});

test("hook_schema_fixture_test: envelope integrity rejects tampering", async () => {
  const envelope = await dispatchHookEvent(fixtureRequest(), {
    decide: allowDecision,
    timeout_ms: 1_000,
  });
  assert.throws(
    () => validateHookEventEnvelope({ ...envelope, decision: "BLOCK" }),
    expectCode("HOOK_ENVELOPE_HASH_MISMATCH"),
  );
  assert.throws(
    () => validateHookEventEnvelope({ ...envelope, raw_payload_hash: `sha256:${"A".repeat(64)}` }),
    expectCode("HOOK_ENVELOPE_INVALID"),
  );
  assert.match(sha256HookJson({ stable: true }), /^sha256:[0-9a-f]{64}$/u);
});
