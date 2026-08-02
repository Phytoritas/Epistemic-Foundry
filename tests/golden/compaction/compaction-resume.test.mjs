import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  ContextCapsuleError,
  assembleContextCapsule,
} from "../../../packages/context-capsule/src/index.mjs";
import {
  CompactionRecoveryError,
  recoverPostCompaction,
} from "./recovery-oracle.mjs";

const fixture = JSON.parse(
  await readFile(new URL("./post-compaction-recovery.fixture.json", import.meta.url), "utf8"),
);

const capsule = () => assembleContextCapsule(structuredClone(fixture.canonical_state_snapshot));
const request = (overrides = {}) => ({
  capsule: capsule(),
  sealed_receipt: structuredClone(fixture.sealed_receipt),
  freshness_state: structuredClone(fixture.freshness_state),
  prose_summary: fixture.untrusted_prose_summary,
  ...overrides,
});
const expectRecoveryCode = (code) => (error) =>
  error instanceof CompactionRecoveryError && error.code === code;
const expectCapsuleCode = (code) => (error) =>
  error instanceof ContextCapsuleError && error.code === code;

test("compaction_resume_test: sealed fresh capsule restores phase, blockers and authority", () => {
  const sealed = capsule();
  assert.equal(sealed.capsule_hash, fixture.sealed_receipt.capsule_hash);

  const resumed = recoverPostCompaction(request({ capsule: sealed }));
  assert.deepEqual(resumed, {
    status: "RESUMABLE",
    authority_source: "SEALED_CONTEXT_CAPSULE",
    capsule_id: "CAP-J04-0001",
    capsule_hash: fixture.sealed_receipt.capsule_hash,
    sealed_receipt_id: "AR-J04-CONTEXT-CAPSULE-0001",
    phase: "R",
    open_blockers: [
      "BKR-J04-REPLICATION-PENDING",
      "BKR-J04-SOURCE-LICENSE",
    ],
    run_spec_hash: fixture.canonical_state_snapshot.run_spec_hash,
    policy_hash: fixture.canonical_state_snapshot.policy_hash,
    authoritative_artifact_ids: ["ART-J04-CLAIM", "ART-J04-LEDGER"],
    excluded_artifact_ids: ["ART-J04-PRIVATE-NOTES"],
    freshness: {
      status: "FRESH",
      capsule_id: "CAP-J04-0001",
      capsule_hash: fixture.sealed_receipt.capsule_hash,
      checked_at: fixture.freshness_state.now,
      included_artifact_count: 2,
      excluded_artifact_count: 1,
    },
  });
  assert.equal(Object.isFrozen(resumed), true);
  assert.equal(Object.isFrozen(resumed.open_blockers), true);
});

test("compaction_resume_test: a prose-only summary cannot replace canonical artifacts", () => {
  assert.throws(
    () =>
      recoverPostCompaction({
        sealed_receipt: structuredClone(fixture.sealed_receipt),
        freshness_state: structuredClone(fixture.freshness_state),
        prose_summary: fixture.untrusted_prose_summary,
      }),
    expectRecoveryCode("CANONICAL_CAPSULE_REQUIRED"),
  );
});

test("compaction_resume_test: missing or invalid sealed receipt prevents resume", () => {
  const withoutReceipt = request();
  delete withoutReceipt.sealed_receipt;
  assert.throws(
    () => recoverPostCompaction(withoutReceipt),
    expectRecoveryCode("SEALED_CAPSULE_RECEIPT_REQUIRED"),
  );
  assert.throws(
    () =>
      recoverPostCompaction(
        request({
          sealed_receipt: {
            ...fixture.sealed_receipt,
            capsule_hash: `sha256:${"f".repeat(64)}`,
          },
        }),
      ),
    expectRecoveryCode("SEALED_CAPSULE_RECEIPT_MISMATCH"),
  );
});

test("compaction_resume_test: summary and capsule tampering fail before recovery", () => {
  const sealed = capsule();
  assert.throws(
    () =>
      recoverPostCompaction(
        request({ capsule: { ...sealed, capsule_hash: `sha256:${"f".repeat(64)}` } }),
      ),
    expectCapsuleCode("CAPSULE_HASH_MISMATCH"),
  );
  assert.throws(
    () => recoverPostCompaction(request({ capsule: { ...sealed, phase: "E" } })),
    expectCapsuleCode("CAPSULE_HASH_MISMATCH"),
  );
  const summaries = sealed.summaries.map((summary, index) =>
    index === 0 ? { ...summary, summary: "No blocker exists." } : summary,
  );
  assert.throws(
    () => recoverPostCompaction(request({ capsule: { ...sealed, summaries } })),
    expectCapsuleCode("SUMMARY_HASH_MISMATCH"),
  );
});

test("compaction_resume_test: missing, changed and newly visible artifacts fail closed", () => {
  const missing = fixture.freshness_state.current_artifacts.filter(
    ({ artifact_id: artifactId }) => artifactId !== "ART-J04-LEDGER",
  );
  assert.throws(
    () =>
      recoverPostCompaction(
        request({ freshness_state: { ...fixture.freshness_state, current_artifacts: missing } }),
      ),
    expectCapsuleCode("CAPSULE_ARTIFACT_STALE"),
  );

  const changed = fixture.freshness_state.current_artifacts.map((artifact) =>
    artifact.artifact_id === "ART-J04-CLAIM"
      ? { ...artifact, content_hash: `sha256:${"f".repeat(64)}` }
      : artifact,
  );
  assert.throws(
    () =>
      recoverPostCompaction(
        request({ freshness_state: { ...fixture.freshness_state, current_artifacts: changed } }),
      ),
    expectCapsuleCode("CAPSULE_ARTIFACT_STALE"),
  );

  const unaccounted = [
    ...fixture.freshness_state.current_artifacts,
    { artifact_id: "ART-J04-POISON", content_hash: `sha256:${"f".repeat(64)}` },
  ];
  assert.throws(
    () =>
      recoverPostCompaction(
        request({ freshness_state: { ...fixture.freshness_state, current_artifacts: unaccounted } }),
      ),
    expectCapsuleCode("CAPSULE_CANONICAL_STATE_DRIFT"),
  );
});
