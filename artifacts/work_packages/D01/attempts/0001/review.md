# D01-0001 independent review of bounded-agent work

- Author: the bounded implementation agent that wrote
  packages/foundry-kernel/src/state/sqlite. Reviewer: this seal-prep
  session, a distinct actor that did not author the store. The author
  never approves its own work, so actor_independence HOLDS for this
  review; external actor-independent certification does NOT, and no such
  claim is made. D01 is risk_class=critical, so the store was attacked
  thoroughly rather than skimmed.
- WAL durability and transactions. The store opens the database in
  SQLite WAL journal mode through node:sqlite DatabaseSync and commits
  every revisioned record inside a BEGIN IMMEDIATE transaction.
  Committed state survives a close and reopen, and a transaction whose
  callback throws rolls back every partial write; when both the
  operation and its rollback fail the store refuses to report an
  ordinary failure and enters SAFE_MODE with an uncertain-outcome code.
- Compare-and-swap revisions. State advances only when the caller's
  expected revision matches the persisted revision. Two worker-thread
  writers that present the same expected revision produce exactly one
  update and one typed stale no-op; the stale writer never overwrites
  the record it did not observe. One hundred contention repetitions and
  one hundred concurrent first-open repetitions converge deterministically,
  and revision exhaustion is refused without changing the record. A
  stale compare-and-swap fails as data, not as a silent last-writer-wins
  overwrite.
- Integrity failure enters SAFE_MODE. Physical corruption, structural
  schema drift, invalid persisted JSON, and runtime revision or
  schema-version drift each fail closed. Once SAFE_MODE is entered the
  store is read-only and every mutation path is denied; hostile
  JavaScript values and Promise/thenable transaction callbacks are
  rejected without granting execution or leaving partial state. The
  failure mode is refusal, never a best-effort write.
- No new production dependency: the store uses the runtime's built-in
  node:sqlite. Ruff lint and format, the two required checks
  (sqlite_wal_test 19/19, concurrent_revision_test 2/2), the extra
  integrity-safe-mode coverage 16/16, targeted 37/37, full Python
  1261/1261, full Node 1253/1253 across 111 files, and git diff --check
  all pass with zero failures.
- Residual limitations: WAL busy retry is exercised indirectly by
  concurrent opens but has no deterministic retry-count assertion, and
  checkIntegrity() has an ordinary linearization point that the next
  store operation detects. Broader recovery lifecycle belongs to a later
  package. Verdict: PASS on the exact D01 package contract.
