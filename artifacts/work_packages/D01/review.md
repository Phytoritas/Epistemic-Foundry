# D01 SQLite WAL local canonical store review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_ADVERSARIAL_REVIEW`

Final verdict: `PASS`

blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_PASS`

The product owner requires serial primary-session execution without Fleet or
subagents and explicitly approves all independent reviews. Accordingly, this
review is a separate adversarial pass in the primary session. Earlier
actor-separated read-only reviewer runs supplied concrete attacks and HIGH
findings; those findings were reproduced and closed. The final source hashes
were then re-read and attacked in a separate primary-session pass. This is not
external actor-independent certification and no such claim is made.

## Authority and final reviewed bytes

- `MASTER_SPEC.md`, `AGENTS.md`, `MASTER_EXECUTION_PROMPT.md`, and D01 in
  `manifests/development_manifest.yaml`;
- dependency evidence for B04-0002 and C04-0001;
- `sqlite-state-store.mjs` —
  `sha256:6619dccb72f40e92fdaae3d023a2d6591f8d63bdfe789ba5c36b53ce7dbe1380`;
- `sqlite-wal.test.mjs` —
  `sha256:e9d17526d229edf4e9369cfffd1834bdb9ff761a264f4aa4605edc3d8f3d2bfc`;
- `concurrent-revision.test.mjs` —
  `sha256:3df6754b227d32fdfad8c6bc4e7352634fc847bad8ffbe3ffceb030441688bbb`;
- `integrity-safe-mode.test.mjs` —
  `sha256:9b6d31b8fb45b17183d3d8a9fe9a3d72d70e047a17f01fd31b2ea516407ac37f`.

## Resolved blocking findings

1. **D01-RF001 — structural schema integrity.** A database with a plausible
   table name but missing composite primary key, wrong column constraints, or
   duplicate rows could previously look healthy. The store now verifies the
   exact table SQL/fingerprint, `STRICT` mode, columns, primary-key order, and
   revision/JSON constraints before use. Eight schema-drift attacks and the
   duplicate-row attack enter `SAFE_MODE`.
2. **D01-RF002 — persisted JSON semantic validity.** SQLite accepts JSON
   spellings such as `1e400` that JavaScript decodes to a non-finite number.
   Persisted values are now decoded and revalidated against the canonical JSON
   value contract; invalid persisted JSON fails closed.
3. **D01-RF003 — uncertain transaction outcome.** If both the transaction
   operation and rollback fail, the store no longer reports an ordinary
   callback failure. It enters `SAFE_MODE` with
   `SQLITE_TRANSACTION_OUTCOME_UNCERTAIN` and denies reuse.
4. **D01-RF004 — escaped async transaction continuation.** A callback that
   returned a Promise could continue after rollback and write through the
   still-live handle. Async/thenable callbacks are denied, rollback is
   confirmed, and that store handle is revoked into `SAFE_MODE`; pre-await and
   post-await writes both remain absent.
5. **D01-RF005 — runtime schema-version mutation.** An already-open store did
   not detect external `schema_version` drift on every read/integrity/mutation
   path. The version and complete persistent state are now revalidated, with a
   second validation after `BEGIN IMMEDIATE` for mutations.
6. **D01-RF006 — cross-realm and subclass rejected Promises.** Denied Promise
   results from another realm or a Promise subclass could remain unobserved
   and terminate Node under strict unhandled-rejection policy. The store now
   attaches an intrinsic rejection observer without executing hostile
   `then`, `constructor`, or `Symbol.species` hooks, while preserving rollback
   and handle revocation.
7. **D01-RF007 — non-extensible rejected Promises.** `preventExtensions`,
   `seal`, and `freeze` blocked an own-property observer shim and left the
   rejected Promise unhandled. Trusted local Promises are now observed
   directly with captured intrinsics; hostile constructor chains use a
   bounded, restored shadow only when safe. Strict-process probes survive all
   three forms.

## Final findings

1. **WAL and durability — PASS.** The database uses SQLite WAL, committed
   revisioned records survive reopen, and callback failure rolls back every
   partial write.
2. **Atomic revision CAS — PASS.** Two worker-thread writers using the same
   expected revision produce exactly one update and one typed stale no-op.
   One hundred independent contention repetitions passed; revision exhaustion
   also fails without changing the record.
3. **Concurrent initialization — PASS.** Two first-open workers converge on a
   single canonical WAL schema. One hundred repetitions passed.
4. **Integrity and `SAFE_MODE` — PASS.** Physical corruption, schema drift,
   invalid persisted JSON, runtime JSON/revision corruption, and runtime
   schema-version drift all fail closed. Every mutation path is denied after
   `SAFE_MODE` entry.
5. **Hostile JavaScript values — PASS.** Proxies, accessors, cycles,
   non-plain objects, lossy values, inherited serialization hooks, and
   Promise/thenable callbacks are rejected without granting execution or
   partial state.
6. **Promise lifecycle — PASS.** A strict clean process survives rejected
   local, cross-realm, subclass, `preventExtensions`, sealed, and frozen
   Promises. Hostile hook calls are zero, Promise primordials are restored,
   the transaction row is absent, and the store is revoked.
7. **Regression and packaging — PASS for D01.** D01 records 37/37 tests and
   83.46% line, 76.05% branch, and 95.00% function coverage. The foundry
   kernel/security set records 72/72. Python records 912/912. Structure,
   package boundary, lock, CI-matrix, cache-policy, package dry-run, UTF-8,
   and whitespace checks pass.

## Preserved non-D01 integration failures and limitations

- The repository-wide Node set records 103 passed and one failure in
  `S04-TM004`: the stored expected hash for
  `manifests/development_manifest.yaml` is stale. D01 neither owns nor changed
  that S04 traceability binding.
- `scripts/build/double_build.py` fails because its staged source omits the
  `scripts/` package required by the build hook. This predates D01 and lies
  outside `packages/foundry-kernel/src/state/sqlite/**`.
- WAL busy retry is exercised indirectly by concurrent opens but has no
  deterministic retry-count/deadline assertion.
- `checkIntegrity()` has an ordinary linearization point: an external writer
  may change metadata immediately after its validation statement; the next
  store operation detects the drift. D04 owns broader recovery lifecycle.

## Decision

D01 passes its exact package contract. Transactions, WAL persistence,
compare-and-swap revision semantics, corruption detection, and fail-closed
`SAFE_MODE` behavior are implemented and adversarially exercised. No
non-waivable D01 finding remains. The overall Foundry objective is not
complete and `completion_ready` remains false.
