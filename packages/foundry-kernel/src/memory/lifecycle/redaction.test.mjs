import assert from "node:assert/strict";
import test from "node:test";

import {
  MemoryLifecycleError,
  canonicalMemoryLifecycleJson,
  redactAndDeduplicateMemory,
  validateMemorySelection,
} from "./index.mjs";
import {
  directive,
  retrievalHit,
  sourceArtifact,
  textHash,
} from "./memory-lifecycle-test-support.mjs";

const errorCode = (code) => (error) =>
  error instanceof MemoryLifecycleError && error.code === code;

const redact = ({ hits, sources, directives, profile = null }) =>
  redactAndDeduplicateMemory({
    hits,
    source_artifacts: sources,
    redaction_directives: directives,
    required_redaction_profile: profile,
  });

test("redaction_test: exact byte-span redaction creates a new immutable derived artifact", () => {
  const source = sourceArtifact();
  const input = {
    hits: [retrievalHit(source)],
    sources: [source],
    directives: [directive(source)],
  };
  const before = structuredClone(input);
  const result = redact(input);
  assert.deepEqual(input, before);
  assert.equal(result.selected_hits[0].redacted, true);
  assert.equal(result.redacted_artifacts[0].content, "alpha [REDACTED] omega");
  assert.equal(result.redacted_artifacts[0].original_source_hash, source.source_hash);
  assert.notEqual(result.redacted_artifacts[0].redacted_content_hash, source.source_hash);
  assert.match(result.redacted_artifacts[0].artifact_id, /^MRA-[0-9a-f]{64}$/u);
  assert.equal(result.redaction_count, 1);
  assert.ok(Object.isFrozen(result));
  assert.deepEqual(validateMemorySelection(result), result);
});

test("redaction_test: duplicate source hashes select one representative without score amplification", () => {
  const source = sourceArtifact();
  const hits = [
    retrievalHit(source, { memory_id: "MEM-L03-003", score: 0.6 }),
    retrievalHit(source, { memory_id: "MEM-L03-002", score: 0.9 }),
    retrievalHit(source, { memory_id: "MEM-L03-001", score: 0.9 }),
  ];
  const result = redact({ hits, sources: [source], directives: [] });
  assert.deepEqual(result.selected_hits.map((hit) => hit.memory_id), ["MEM-L03-001"]);
  assert.equal(result.selected_hits[0].score, 0.9);
  assert.deepEqual(result.duplicate_exclusions, [
    {
      duplicate_memory_id: "MEM-L03-002",
      representative_memory_id: "MEM-L03-001",
      reason: "DUPLICATE_SOURCE_HASH",
      source_hash: source.source_hash,
    },
    {
      duplicate_memory_id: "MEM-L03-003",
      representative_memory_id: "MEM-L03-001",
      reason: "DUPLICATE_SOURCE_HASH",
      source_hash: source.source_hash,
    },
  ]);
});

test("redaction_test: hit and directive permutations produce the same selection hash", () => {
  const left = sourceArtifact("left secret tail");
  const right = sourceArtifact("right hidden tail");
  const hits = [
    retrievalHit(left, { memory_id: "MEM-L03-A", score: 0.75 }),
    retrievalHit(right, { memory_id: "MEM-L03-B", score: 1 }),
  ];
  const directives = [
    directive(left, { directive_id: "RED-L03-A", start_byte: 5, end_byte: 11 }),
    directive(right, { directive_id: "RED-L03-B", start_byte: 6, end_byte: 12 }),
  ];
  const first = redact({ hits, sources: [left, right], directives });
  const second = redact({
    hits: [...hits].reverse(),
    sources: [right, left],
    directives: [...directives].reverse(),
  });
  assert.deepEqual(second, first);
  assert.equal(second.selection_hash, first.selection_hash);
});

test("redaction_test: multiple non-overlapping spans are counted exactly", () => {
  const source = sourceArtifact("alpha secret and hidden omega");
  const result = redact({
    hits: [retrievalHit(source)],
    sources: [source],
    directives: [
      directive(source, { directive_id: "RED-L03-A", start_byte: 6, end_byte: 12, replacement: "X" }),
      directive(source, { directive_id: "RED-L03-B", start_byte: 17, end_byte: 23, replacement: "Y" }),
    ],
  });
  assert.equal(result.redaction_count, 2);
  assert.equal(result.redacted_artifacts[0].content, "alpha X and Y omega");
  assert.deepEqual(result.redacted_artifacts[0].directive_ids, ["RED-L03-A", "RED-L03-B"]);
});

test("redaction_test: overlapping spans fail closed", () => {
  const source = sourceArtifact();
  assert.throws(
    () => redact({
      hits: [retrievalHit(source)],
      sources: [source],
      directives: [
        directive(source, { directive_id: "RED-L03-A", start_byte: 6, end_byte: 12 }),
        directive(source, { directive_id: "RED-L03-B", start_byte: 10, end_byte: 14 }),
      ],
    }),
    errorCode("REDACTION_SPAN_OVERLAP"),
  );
});

test("redaction_test: out-of-range spans fail closed", () => {
  const source = sourceArtifact();
  assert.throws(
    () => redact({
      hits: [retrievalHit(source)],
      sources: [source],
      directives: [directive(source, { end_byte: 999 })],
    }),
    errorCode("REDACTION_SPAN_OUT_OF_RANGE"),
  );
});

test("redaction_test: byte spans cannot split UTF-8 code points", () => {
  const source = sourceArtifact("A한B");
  assert.throws(
    () => redact({
      hits: [retrievalHit(source)],
      sources: [source],
      directives: [directive(source, { start_byte: 2, end_byte: 4 })],
    }),
    errorCode("REDACTION_SPAN_SPLITS_UTF8"),
  );
  const valid = redact({
    hits: [retrievalHit(source)],
    sources: [source],
    directives: [directive(source, { start_byte: 1, end_byte: 4, replacement: "[K]" })],
  });
  assert.equal(valid.redacted_artifacts[0].content, "A[K]B");
});

test("redaction_test: stale source content cannot reuse a source hash", () => {
  const source = sourceArtifact();
  assert.throws(
    () => redact({
      hits: [retrievalHit(source)],
      sources: [{ source_hash: source.source_hash, content: "tampered" }],
      directives: [],
    }),
    errorCode("REDACTION_SOURCE_HASH_MISMATCH"),
  );
});

test("redaction_test: profile-only redaction fails closed without authoritative rules", () => {
  const source = sourceArtifact();
  assert.throws(
    () => redact({ hits: [retrievalHit(source)], sources: [source], directives: [], profile: "pii-strip" }),
    errorCode("REDACTION_PROFILE_UNRESOLVED"),
  );
});

test("redaction_test: missing, extra, and unused source bindings are rejected", () => {
  const source = sourceArtifact();
  const extra = sourceArtifact("extra content");
  assert.throws(
    () => redact({ hits: [retrievalHit(source)], sources: [], directives: [] }),
    errorCode("REDACTION_SOURCE_MISSING"),
  );
  assert.throws(
    () => redact({ hits: [retrievalHit(source)], sources: [source, extra], directives: [] }),
    errorCode("REDACTION_SOURCE_UNUSED"),
  );
  assert.throws(
    () => redact({
      hits: [retrievalHit(source)],
      sources: [source],
      directives: [directive(extra)],
    }),
    errorCode("REDACTION_DIRECTIVE_UNUSED"),
  );
});

test("redaction_test: no-op directives and duplicate IDs are rejected", () => {
  const source = sourceArtifact();
  assert.throws(
    () => redact({
      hits: [retrievalHit(source)],
      sources: [source],
      directives: [directive(source, { replacement: "secret" })],
    }),
    errorCode("REDACTION_NO_OP"),
  );
  assert.throws(
    () => redact({
      hits: [retrievalHit(source)],
      sources: [source],
      directives: [directive(source), directive(source)],
    }),
    errorCode("DUPLICATE_REDACTION_DIRECTIVE"),
  );
});

test("redaction_test: duplicate memory IDs and duplicate source artifacts are rejected", () => {
  const source = sourceArtifact();
  assert.throws(
    () => redact({ hits: [retrievalHit(source), retrievalHit(source)], sources: [source], directives: [] }),
    errorCode("DUPLICATE_MEMORY_ID"),
  );
  assert.throws(
    () => redact({ hits: [retrievalHit(source)], sources: [source, source], directives: [] }),
    errorCode("DUPLICATE_SOURCE_ARTIFACT"),
  );
});

test("redaction_test: already-redacted hits cannot be silently redacted again", () => {
  const source = sourceArtifact();
  assert.throws(
    () => redact({ hits: [retrievalHit(source, { redacted: true })], sources: [source], directives: [] }),
    errorCode("REDACTION_STAGE_ALREADY_APPLIED"),
  );
});

test("redaction_test: selection hash and derived content hash detect tampering", () => {
  const source = sourceArtifact();
  const result = redact({ hits: [retrievalHit(source)], sources: [source], directives: [directive(source)] });
  const selectionTamper = structuredClone(result);
  selectionTamper.selection_hash = textHash("wrong");
  assert.throws(() => validateMemorySelection(selectionTamper), errorCode("MEMORY_SELECTION_HASH_MISMATCH"));
  const contentTamper = structuredClone(result);
  contentTamper.redacted_artifacts[0].content = "leaked";
  assert.throws(() => validateMemorySelection(contentTamper), errorCode("REDACTED_ARTIFACT_HASH_MISMATCH"));
});

test("redaction_test: empty hit input has an explicit deterministic empty selection", () => {
  const result = redact({ hits: [], sources: [], directives: [] });
  assert.deepEqual(result.selected_hits, []);
  assert.deepEqual(result.redacted_artifacts, []);
  assert.deepEqual(result.duplicate_exclusions, []);
  assert.equal(result.redaction_count, 0);
  assert.deepEqual(validateMemorySelection(result), result);
});

test("redaction_test: accessors, proxies, and extra fields fail closed", () => {
  const source = sourceArtifact();
  const accessor = retrievalHit(source);
  Object.defineProperty(accessor, "score", { enumerable: true, get: () => 1 });
  assert.throws(
    () => redact({ hits: [accessor], sources: [source], directives: [] }),
    errorCode("MEMORY_REDACTION_INPUT_INVALID"),
  );
  assert.throws(
    () => redact(new Proxy({
      hits: [retrievalHit(source)],
      source_artifacts: [source],
      redaction_directives: [],
      required_redaction_profile: null,
    }, {})),
    errorCode("MEMORY_REDACTION_INPUT_INVALID"),
  );
  assert.throws(
    () => redactAndDeduplicateMemory({
      hits: [retrievalHit(source)],
      source_artifacts: [source],
      redaction_directives: [],
      required_redaction_profile: null,
      fallback: true,
    }),
    errorCode("MEMORY_REDACTION_INPUT_INVALID"),
  );
});

test("redaction_test: directive IDs use canonical ID ordering independent of span order", () => {
  const source = sourceArtifact("alpha secret and hidden omega");
  const result = redact({
    hits: [retrievalHit(source)],
    sources: [source],
    directives: [
      directive(source, {
        directive_id: "RED-L03-Z",
        start_byte: 6,
        end_byte: 12,
        replacement: "X",
      }),
      directive(source, {
        directive_id: "RED-L03-A",
        start_byte: 17,
        end_byte: 23,
        replacement: "Y",
      }),
    ],
  });
  assert.equal(result.redacted_artifacts[0].content, "alpha X and Y omega");
  assert.deepEqual(result.redacted_artifacts[0].directive_ids, ["RED-L03-A", "RED-L03-Z"]);
  assert.deepEqual(validateMemorySelection(result), result);
});

test("redaction_test: replay validation rejects accessor-backed selected hits", () => {
  const source = sourceArtifact();
  const result = structuredClone(redact({
    hits: [retrievalHit(source)],
    sources: [source],
    directives: [],
  }));
  Object.defineProperty(result.selected_hits[0], "score", {
    enumerable: true,
    get: () => 1,
  });
  assert.throws(() => validateMemorySelection(result), errorCode("MEMORY_REDACTION_INPUT_INVALID"));
});

test("redaction_test: a self-rehashed duplicate exclusion cannot forge its representative", () => {
  const source = sourceArtifact();
  const result = structuredClone(redact({
    hits: [
      retrievalHit(source, { memory_id: "MEM-L03-REP", score: 1 }),
      retrievalHit(source, { memory_id: "MEM-L03-DUP", score: 0.5 }),
    ],
    sources: [source],
    directives: [],
  }));
  result.duplicate_exclusions[0].representative_memory_id = "MEM-L03-FORGED";
  const preimage = { ...result };
  delete preimage.selection_hash;
  result.selection_hash = textHash(canonicalMemoryLifecycleJson(preimage));
  assert.throws(() => validateMemorySelection(result), errorCode("MEMORY_SELECTION_INVALID"));
});
