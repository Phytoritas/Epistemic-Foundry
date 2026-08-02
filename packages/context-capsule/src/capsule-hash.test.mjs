import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  CONTEXT_CAPSULE_SCHEMA_ID,
  CONTEXT_CAPSULE_SCHEMA_SHA256,
  ContextCapsuleError,
  assembleContextCapsule,
  canonicalizeContextCapsuleJson,
  computeContextCapsuleHash,
  verifyContextCapsuleIntegrity,
} from "./index.mjs";

const HASH_A = `sha256:${"a".repeat(64)}`;
const HASH_B = `sha256:${"b".repeat(64)}`;
const HASH_C = `sha256:${"c".repeat(64)}`;

const snapshot = (overrides = {}) => ({
  capsule_id: "CAP-J03-0001",
  session_id: "SESSION-J03-0001",
  phase: "O",
  purpose: "resume the Observe phase from canonical state",
  run_spec_hash: HASH_A,
  policy_hash: HASH_B,
  artifact_selections: [
    {
      artifact_id: "ART-beta",
      disposition: "INCLUDE",
      source_hash: HASH_C,
      summary: "One counterevidence lane remains unresolved.",
    },
    { artifact_id: "ART-omega", disposition: "EXCLUDE" },
    {
      artifact_id: "ART-alpha",
      disposition: "INCLUDE",
      source_hash: HASH_A,
      summary: "The scoped claim and falsifier are recorded.",
    },
  ],
  open_blockers: ["counterevidence lane unresolved"],
  allowed_capabilities: ["retrieval_read", "artifact_read"],
  token_budget: 8000,
  created_at: "2026-07-30T00:00:00Z",
  expires_at: "2026-07-31T00:00:00Z",
  ...overrides,
});

const expectCode = (code) => (error) => error instanceof ContextCapsuleError && error.code === code;

test("capsule_hash_test: canonical snapshot yields a deterministic immutable capsule", () => {
  const input = snapshot();
  const before = structuredClone(input);
  const first = assembleContextCapsule(input);
  const second = assembleContextCapsule(structuredClone(input));
  assert.deepEqual(first, second);
  assert.deepEqual(input, before);
  assert.equal(Object.isFrozen(first), true);
  assert.equal(Object.isFrozen(first.summaries), true);
  assert.equal(Object.isFrozen(first.summaries[0]), true);
  assert.deepEqual(first.artifact_ids, ["ART-alpha", "ART-beta"]);
  assert.deepEqual(first.excluded_artifact_ids, ["ART-omega"]);
  assert.deepEqual(first.allowed_capabilities, ["artifact_read", "retrieval_read"]);
  assert.match(first.capsule_hash, /^sha256:[0-9a-f]{64}$/u);
});

test("capsule_hash_test: set-like input ordering cannot change capsule bytes or hash", () => {
  const first = assembleContextCapsule(snapshot());
  const reordered = assembleContextCapsule(
    snapshot({
      artifact_selections: [...snapshot().artifact_selections].reverse(),
      allowed_capabilities: ["artifact_read", "retrieval_read"],
    }),
  );
  assert.equal(canonicalizeContextCapsuleJson(first), canonicalizeContextCapsuleJson(reordered));
  assert.equal(first.capsule_hash, reordered.capsule_hash);
});

test("capsule_hash_test: capsule and summary hashes bind exact canonical content", () => {
  const capsule = assembleContextCapsule(snapshot());
  const preimage = { ...capsule };
  delete preimage.capsule_hash;
  assert.equal(capsule.capsule_hash, computeContextCapsuleHash(preimage));
  for (const summary of capsule.summaries) {
    const expected = `sha256:${createHash("sha256")
      .update(JSON.stringify(summary.summary), "utf8")
      .digest("hex")}`;
    assert.equal(summary.summary_hash, expected);
  }
  assert.deepEqual(verifyContextCapsuleIntegrity(capsule), capsule);
});

test("capsule_hash_test: emitted capsule validates against the canonical Draft 2020-12 schema", () => {
  const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
  const capsule = assembleContextCapsule(snapshot());
  const script = `
import json
import pathlib
import sys
from jsonschema import Draft202012Validator, FormatChecker

schema = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
instance = json.loads(sys.argv[2])
Draft202012Validator.check_schema(schema)
errors = sorted(
    Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(instance),
    key=lambda error: list(error.absolute_path),
)
if errors:
    raise SystemExit("; ".join(error.message for error in errors))
print(schema["$id"])
`;
  const result = spawnSync(
    "uv",
    [
      "run",
      "--locked",
      "python",
      "-",
      path.join(repoRoot, "schemas", "context-capsule.schema.json"),
      JSON.stringify(capsule),
    ],
    { cwd: repoRoot, encoding: "utf8", input: script },
  );
  assert.equal(result.status, 0, `schema validation failed\n${result.stdout}\n${result.stderr}`);
  assert.equal(result.stdout.trim(), CONTEXT_CAPSULE_SCHEMA_ID);
  assert.match(CONTEXT_CAPSULE_SCHEMA_SHA256, /^sha256:[0-9a-f]{64}$/u);
});

test("capsule_hash_test: every included artifact requires one bound nonblank summary", () => {
  const missingSummary = snapshot().artifact_selections.map((selection) =>
    selection.artifact_id === "ART-alpha"
      ? { artifact_id: selection.artifact_id, disposition: "INCLUDE", source_hash: HASH_A }
      : selection,
  );
  assert.throws(
    () => assembleContextCapsule(snapshot({ artifact_selections: missingSummary })),
    expectCode("UNBOUND_INCLUDED_ARTIFACT"),
  );
  const blankSummary = snapshot().artifact_selections.map((selection) =>
    selection.artifact_id === "ART-alpha" ? { ...selection, summary: "   " } : selection,
  );
  assert.throws(
    () => assembleContextCapsule(snapshot({ artifact_selections: blankSummary })),
    expectCode("EMPTY_SUMMARY"),
  );
});

test("capsule_hash_test: exclusions are explicit and cannot smuggle content", () => {
  const capsule = assembleContextCapsule(snapshot());
  assert.deepEqual(capsule.excluded_artifact_ids, ["ART-omega"]);
  const selections = snapshot().artifact_selections.map((selection) =>
    selection.artifact_id === "ART-omega"
      ? { ...selection, summary: "secret excluded bytes", source_hash: HASH_C }
      : selection,
  );
  assert.throws(
    () => assembleContextCapsule(snapshot({ artifact_selections: selections })),
    expectCode("EXCLUDED_ARTIFACT_CONTENT_DENIED"),
  );
});

test("capsule_hash_test: duplicate or conflicting dispositions fail closed", () => {
  const duplicate = [
    ...snapshot().artifact_selections,
    { artifact_id: "ART-alpha", disposition: "EXCLUDE" },
  ];
  assert.throws(
    () => assembleContextCapsule(snapshot({ artifact_selections: duplicate })),
    expectCode("ARTIFACT_DISPOSITION_CONFLICT"),
  );
  const capsule = assembleContextCapsule(snapshot());
  const overlap = {
    ...capsule,
    excluded_artifact_ids: ["ART-alpha", "ART-omega"],
  };
  assert.throws(
    () => verifyContextCapsuleIntegrity(overlap),
    expectCode("ARTIFACT_DISPOSITION_CONFLICT"),
  );
});

test("capsule_hash_test: prose-only, purposeless, invalid-hash and invalid-phase input is refused", () => {
  assert.throws(
    () =>
      assembleContextCapsule(
        snapshot({ artifact_selections: [{ artifact_id: "ART-omega", disposition: "EXCLUDE" }] }),
      ),
    expectCode("CANONICAL_ARTIFACT_REQUIRED"),
  );
  assert.throws(() => assembleContextCapsule(snapshot({ purpose: " " })), expectCode("EMPTY_PURPOSE"));
  assert.throws(
    () => assembleContextCapsule(snapshot({ policy_hash: "sha256:not-a-hash" })),
    expectCode("INVALID_HASH"),
  );
  assert.throws(() => assembleContextCapsule(snapshot({ phase: "OBSERVE" })), expectCode("INVALID_PHASE"));
});

test("capsule_hash_test: capsule or summary tamper is detected before reuse", () => {
  const capsule = assembleContextCapsule(snapshot());
  assert.throws(
    () => verifyContextCapsuleIntegrity({ ...capsule, purpose: "tampered" }),
    expectCode("CAPSULE_HASH_MISMATCH"),
  );
  const summaries = capsule.summaries.map((summary, index) =>
    index === 0 ? { ...summary, summary: "tampered" } : summary,
  );
  assert.throws(
    () => verifyContextCapsuleIntegrity({ ...capsule, summaries }),
    expectCode("SUMMARY_HASH_MISMATCH"),
  );
});

test("capsule_hash_test: hostile and noncanonical object input fails without invoking accessors", () => {
  let getterCalls = 0;
  const accessor = snapshot();
  Object.defineProperty(accessor, "purpose", {
    enumerable: true,
    get() {
      getterCalls += 1;
      return "stolen authority";
    },
  });
  assert.throws(() => assembleContextCapsule(accessor), expectCode("ACCESSOR_FIELD_DENIED"));
  assert.equal(getterCalls, 0);
  assert.throws(() => assembleContextCapsule(new Proxy(snapshot(), {})), expectCode("INVALID_INPUT"));
  const sparse = snapshot();
  sparse.artifact_selections = new Array(2);
  sparse.artifact_selections[1] = snapshot().artifact_selections[0];
  assert.throws(() => assembleContextCapsule(sparse), expectCode("INVALID_INPUT"));
  assert.throws(
    () => assembleContextCapsule({ ...snapshot(), previous_capsule: {} }),
    expectCode("UNEXPECTED_FIELD"),
  );
});

test("capsule_hash_test: null expiry is recordable but an inverted window is not", () => {
  const undated = assembleContextCapsule(snapshot({ expires_at: null }));
  assert.equal(undated.expires_at, null);
  assert.throws(
    () => assembleContextCapsule(snapshot({ expires_at: "2026-07-29T00:00:00Z" })),
    expectCode("INVALID_FRESHNESS_WINDOW"),
  );
});
