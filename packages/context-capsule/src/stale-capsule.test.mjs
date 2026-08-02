import assert from "node:assert/strict";
import test from "node:test";

import {
  ContextCapsuleError,
  assembleContextCapsule,
  requireFreshContextCapsule,
} from "./index.mjs";

const HASH_A = `sha256:${"a".repeat(64)}`;
const HASH_B = `sha256:${"b".repeat(64)}`;
const HASH_C = `sha256:${"c".repeat(64)}`;

const capsule = (overrides = {}) =>
  assembleContextCapsule({
    capsule_id: "CAP-J03-STALE-0001",
    session_id: "SESSION-J03-STALE-0001",
    phase: "R",
    purpose: "resume reasoning from current canonical artifacts",
    run_spec_hash: HASH_A,
    policy_hash: HASH_B,
    artifact_selections: [
      {
        artifact_id: "ART-alpha",
        disposition: "INCLUDE",
        source_hash: HASH_A,
        summary: "Canonical claim and falsifier.",
      },
      {
        artifact_id: "ART-beta",
        disposition: "INCLUDE",
        source_hash: HASH_B,
        summary: "Current counterevidence and method boundary.",
      },
      { artifact_id: "ART-private", disposition: "EXCLUDE" },
    ],
    open_blockers: ["replication pending"],
    allowed_capabilities: ["artifact_read"],
    token_budget: 4096,
    created_at: "2026-07-30T00:00:00Z",
    expires_at: "2026-07-31T00:00:00Z",
    ...overrides,
  });

const state = (overrides = {}) => ({
  session_id: "SESSION-J03-STALE-0001",
  phase: "R",
  run_spec_hash: HASH_A,
  policy_hash: HASH_B,
  current_artifacts: [
    { artifact_id: "ART-beta", content_hash: HASH_B },
    { artifact_id: "ART-private", content_hash: HASH_C },
    { artifact_id: "ART-alpha", content_hash: HASH_A },
  ],
  now: "2026-07-30T12:00:00Z",
  ...overrides,
});

const expectCode = (code) => (error) => error instanceof ContextCapsuleError && error.code === code;

test("stale_capsule_test: intact capsule matching current canonical state is fresh", () => {
  const result = requireFreshContextCapsule(capsule(), state());
  assert.deepEqual(result, {
    status: "FRESH",
    capsule_id: "CAP-J03-STALE-0001",
    capsule_hash: capsule().capsule_hash,
    checked_at: "2026-07-30T12:00:00Z",
    included_artifact_count: 2,
    excluded_artifact_count: 1,
  });
  assert.equal(Object.isFrozen(result), true);
});

test("stale_capsule_test: missing expiry and expired capsule fail closed", () => {
  assert.throws(
    () => requireFreshContextCapsule(capsule({ expires_at: null }), state()),
    expectCode("CAPSULE_FRESHNESS_UNDECLARED"),
  );
  assert.throws(
    () => requireFreshContextCapsule(capsule(), state({ now: "2026-07-31T00:00:00Z" })),
    expectCode("CAPSULE_EXPIRED"),
  );
});

test("stale_capsule_test: future-created capsule is not yet valid", () => {
  assert.throws(
    () => requireFreshContextCapsule(capsule(), state({ now: "2026-07-29T23:59:59Z" })),
    expectCode("CAPSULE_NOT_YET_VALID"),
  );
});

test("stale_capsule_test: session and phase drift require reconstruction", () => {
  assert.throws(
    () => requireFreshContextCapsule(capsule(), state({ session_id: "SESSION-OTHER" })),
    expectCode("CAPSULE_SESSION_DRIFT"),
  );
  assert.throws(
    () => requireFreshContextCapsule(capsule(), state({ phase: "G" })),
    expectCode("CAPSULE_PHASE_DRIFT"),
  );
});

test("stale_capsule_test: RunSpec and policy drift require reconstruction", () => {
  assert.throws(
    () => requireFreshContextCapsule(capsule(), state({ run_spec_hash: HASH_C })),
    expectCode("CAPSULE_RUN_SPEC_DRIFT"),
  );
  assert.throws(
    () => requireFreshContextCapsule(capsule(), state({ policy_hash: HASH_C })),
    expectCode("CAPSULE_POLICY_DRIFT"),
  );
});

test("stale_capsule_test: changed or missing included artifacts are stale", () => {
  const changed = state().current_artifacts.map((artifact) =>
    artifact.artifact_id === "ART-alpha" ? { ...artifact, content_hash: HASH_C } : artifact,
  );
  assert.throws(
    () => requireFreshContextCapsule(capsule(), state({ current_artifacts: changed })),
    (error) =>
      expectCode("CAPSULE_ARTIFACT_STALE")(error) &&
      error.details.artifact_ids[0] === "ART-alpha",
  );
  const missing = state().current_artifacts.filter((artifact) => artifact.artifact_id !== "ART-beta");
  assert.throws(
    () => requireFreshContextCapsule(capsule(), state({ current_artifacts: missing })),
    (error) =>
      expectCode("CAPSULE_ARTIFACT_STALE")(error) && error.details.artifact_ids[0] === "ART-beta",
  );
});

test("stale_capsule_test: newly visible artifact cannot be silently omitted", () => {
  const current = [
    ...state().current_artifacts,
    { artifact_id: "ART-new", content_hash: HASH_C },
  ];
  assert.throws(
    () => requireFreshContextCapsule(capsule(), state({ current_artifacts: current })),
    (error) =>
      expectCode("CAPSULE_CANONICAL_STATE_DRIFT")(error) &&
      error.details.artifact_ids[0] === "ART-new",
  );
});

test("stale_capsule_test: excluded artifact absence does not resurrect it", () => {
  const current = state().current_artifacts.filter(
    (artifact) => artifact.artifact_id !== "ART-private",
  );
  const result = requireFreshContextCapsule(capsule(), state({ current_artifacts: current }));
  assert.equal(result.status, "FRESH");
  assert.equal(result.excluded_artifact_count, 1);
});

test("stale_capsule_test: capsule tamper is rejected before freshness decisions", () => {
  const sealed = capsule();
  assert.throws(
    () => requireFreshContextCapsule({ ...sealed, token_budget: 1 }, state()),
    expectCode("CAPSULE_HASH_MISMATCH"),
  );
});

test("stale_capsule_test: hostile current-state input fails closed", () => {
  assert.throws(
    () => requireFreshContextCapsule(capsule(), new Proxy(state(), {})),
    expectCode("INVALID_INPUT"),
  );
  const duplicate = [
    ...state().current_artifacts,
    { artifact_id: "ART-alpha", content_hash: HASH_A },
  ];
  assert.throws(
    () => requireFreshContextCapsule(capsule(), state({ current_artifacts: duplicate })),
    expectCode("DUPLICATE_VALUE"),
  );
});
