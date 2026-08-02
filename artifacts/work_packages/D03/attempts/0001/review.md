# D03-0001 independent review of bounded-agent work

- Author: the bounded implementation agent that wrote
  packages/foundry-kernel/src/artifacts. Reviewer: this seal-prep
  session, a distinct actor that did not author the store. The author
  never approves its own work, so actor_independence HOLDS for this
  review; external actor-independent certification does NOT, and no such
  claim is made. D03 is risk_class=medium; the store was still attacked on
  its content-addressing, receipt-resolution, and fail-closed contracts
  rather than skimmed.
- Immutable content-hash addressing. Object bytes are written once under
  their sha256 digest and never overwritten. The same bytes always yield
  the same content_hash and storage_uri, an identical registration and
  receipt replay is idempotent (EXISTING, not a second write), one object
  can back several artifacts and receipts, distinct byte sequences never
  alias to one address, and empty bytes still have a real address. An
  artifact ID cannot be rebound to different bytes (ARTIFACT_ID_CONFLICT),
  a receipt ID cannot be rebound (ARTIFACT_RECEIPT_ID_CONFLICT), and
  immutable manifest metadata cannot be overwritten
  (ARTIFACT_IMMUTABLE_CONFLICT).
- Receipt resolution. resolveReceipt returns the exact addressed bytes,
  the schema_ref, the creating actor, and the resolving manifest; returned
  buffers are copies, so mutating them does not corrupt the store. The
  manifest and receipt validate against the canonical Draft 2020-12
  artifact-manifest and artifact-receipt schemas.
- Integrity failures fail closed. Content tamper (ARTIFACT_HASH_MISMATCH),
  non-canonical manifest or receipt bytes, orphaned receipts without
  content or manifest (ARTIFACT_ORPHAN_RECEIPT), receipts or manifests
  copied under the wrong key (ARTIFACT_RECEIPT_KEY_MISMATCH,
  ARTIFACT_MANIFEST_KEY_MISMATCH), hard-linked or relabelled records,
  linked roots, replaced roots, and unknown tree entries each enter a
  read-only SAFE_MODE that denies every mutation path. The public surface
  exposes no deletion or overwrite operation.
- Concurrency-robustness fix preserved fail-closed behavior. A benign
  Windows .staging/.mutation-lock inode handoff is re-observed within a
  bounded retry budget (STAGING_HANDOFF_RETRY_LIMIT=8) instead of
  fail-closing, so a single injected EPERM handoff still opens ACTIVE; a
  persistent EPERM denial is injected nine times, exhausts the budget, and
  still fails closed to SAFE_MODE with
  ARTIFACT_STORE_STRUCTURE_INVALID / cause EPERM. Concurrent identical and
  distinct worker-thread publishers converge, and a reader/writer overlap
  never observes a broken tree.
- Dependency and checks: the store builds on the sealed D01 SQLite WAL
  canonical store (D01-0001 PASS) and adds no new production dependency.
  Ruff lint and format, the two required checks (artifact_hash_test 21/21,
  orphan_receipt_test 19/19), targeted 40/40, full Python 1261/1261, full
  Node 1253/1253 across 111 files, and git diff --check all pass with zero
  failures.
- Residual limitations: the store is append-only with no garbage
  collection or deletion of unreferenced objects, and backup, corruption,
  and recovery lifecycle beyond fail-closed SAFE_MODE entry belong to the
  later D04 gate. Verdict: PASS on the exact D03 package contract.
