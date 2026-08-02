# E01 append-only Noetic Ledger and reducer review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_ADVERSARIAL_REVIEW`

Final verdict: `PASS`

blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_PASS`

The product owner requires serial primary-session execution without Fleet or
subagents and explicitly authorizes the independent-review artifacts. This is a
procedurally separate adversarial review of the final E01 bytes. It is not
external actor-independent certification.

## Authority and reviewed boundary

- `MASTER_SPEC.md`, `MASTER_EXECUTION_PROMPT.md`, `AGENTS.md`, and E01 in
  `manifests/development_manifest.yaml`;
- invariants `EF4-I01` (Kernel authority) and `EF4-I16` (event-sourced state);
- canonical `schemas/event-record.schema.json` —
  `sha256:538cf66a8d006aa6895dc52fc0761747c9b18bba7ea857eda4f8385364880588`;
- dependency reports C04
  (`sha256:eca4fdd3f10537a2fb5c39643f4dee52bab9bcf5b95f9468ddcd470ffd98592f`)
  and D04
  (`sha256:b47c194e230f4b08ab96b6153e9fc0e170eafb1054318cfaedd8e1ddeb4c5fde`);
- unchanged dependency implementations: D01 SQLite store
  (`sha256:6619dccb72f40e92fdaae3d023a2d6591f8d63bdfe789ba5c36b53ce7dbe1380`)
  and D03 artifact store
  (`sha256:75e69756d30ab5b5112fd908f3fec312660f30e603fe1201566db2ad263c8c8e`);
- final E01 files:
  - `packages/foundry-kernel/src/ledger/noetic-ledger.mjs` —
    `sha256:58ea9dc0d52d9c20720b33970ee3b8d8d05703ba7dd0fb4f51a483d9f505f1ed`;
  - `packages/foundry-kernel/src/ledger/ledger-test-support.mjs` —
    `sha256:4954d4dd7bc985136d744f0689b91316419fb376e842dba2a428c66c9813d6e9`;
  - `packages/foundry-kernel/src/ledger/ledger-hash-chain.test.mjs` —
    `sha256:e478e71b48d74a139a10023033b3fd2d73fcbdf92660feeb920a6c3953e4eb82`;
  - `packages/foundry-kernel/src/ledger/reducer-replay.test.mjs` —
    `sha256:a1f9848e08c1231de29ada86236b6a1ffef19d867ce412d16737a8ce44222029`.

E01 owns only `packages/foundry-kernel/src/ledger/**` and
`artifacts/work_packages/E01/**`. No schema, D01 state-store, D03 artifact-store,
manifest, or other package implementation was changed to make E01 pass.

## Adversarial findings

1. **Ledger authority and atomicity — PASS.** Immutable events are D01
   revision-zero records and the per-run ordered stream is a revisioned D01
   record. Event creation and stream CAS execute in one `BEGIN IMMEDIATE`
   transaction. Fault injection makes stream CAS fail after event creation and
   proves rollback leaves neither an orphan immutable event nor a changed tail.
   Concurrent writers serialize into one contiguous chain.
2. **Ordering and reconciliation — PASS.** Sequence is ledger-owned, starts at
   one per run, and must be contiguous. Reads reconcile stream revision,
   event count, event IDs, immutable event revisions, run identity, previous
   hashes, and the tail ID/hash. Gaps, reorder, cross-run substitution, missing
   records, direct revision mutation, and coherently revised streams that name a
   missing event fail closed.
3. **Hash-chain integrity — PASS.** `payload_hash` binds the exact D03 bytes and
   `event_hash` binds deterministic canonical JSON excluding only
   `event_hash`. Hash fields require explicit canonical strings, so hostile
   coercion hooks do not execute. Event tampering and payload-byte changes are
   rejected. `verifyRun()` re-resolves every artifact and reconciles all hashes.
4. **Idempotency and global event identity — PASS.** Retrying the exact append
   intent returns the existing immutable event. Reusing an event ID with any
   changed intent or payload hash is a conflict. An existing event must also be
   present at its exact sequence in its run stream; otherwise it is rejected as
   orphaned rather than silently repaired.
5. **Canonical EventRecord conformance — PASS.** Emitted events validate against
   the Draft 2020-12 authority. Inputs reject extra fields, accessors, Proxies,
   invalid timestamps, non-semantic versions, non-scalar Unicode, and
   noncanonical hashes. The runtime does not extend or weaken the schema.
6. **Deterministic rebuild — PASS.** Replay starts from an explicit canonical
   initial state and consumes the verified ordered events and exact payload
   bytes. Two isolated passes must produce identical canonical state at every
   event boundary. Async reducers, input mutation, malformed payload JSON,
   non-JSON output, hidden array properties, and nondeterministic results fail
   closed. Reopening both durable stores reproduces the same state and hash.
7. **Authority separation — PASS.** The ledger stores events and derives state;
   it does not implement effect success, capabilities, approvals, promotion, or
   policy authority. Those remain downstream E02/E03 and later package
   responsibilities. The artifact adapter is provider-neutral and no
   repository-root or current-working-directory fallback exists.
8. **Regression and repeatability — PASS for E01.** The final targeted gate is
   21/21 and ten independent repeats are 210/210. The full Python suite is
   913/913. Repository-wide Node discovery is 170 passed with only the existing
   out-of-scope `S04-TM004` stale manifest-hash failure. Structure, package
   boundaries, lock/toolchain, CI matrix, cache policy, ten CI mutation tests,
   strict UTF-8, and `git diff --check` pass. The existing double-build staged
   `scripts/` omission remains outside E01.

## Assurance limitations

- The supplied reducer is an in-process trusted deterministic function. E01
  freezes and isolates its inputs, denies async results, and detects divergent
  state across two passes, but it does not sandbox or prove the absence of
  external side effects. Reducer qualification and effect authority remain
  separate contracts.
- Event and payload hashes provide integrity and ordering, not signatures,
  non-repudiation, or an external transparency log. Actor authentication and
  capability authorization are downstream responsibilities.
- E01 qualifies the local D01 SQLite/D03 artifact adapters used by the tests; it
  does not claim distributed consensus, PostgreSQL ledger concurrency, remote
  object-store availability, or production throughput.
- The repository-wide Node residual is `S04-TM004`: expected manifest hash
  `456330ae...` versus actual `a0a0db29...`. E01 has no S04 write authority.
- `scripts/build/double_build.py` still omits `scripts/` from its staged source.
  This is the preserved B02/B04 build-integration residual, outside E01.

## Decision

E01 satisfies its exact package contract. Event ordering and the hash chain are
verified, state is deterministically rebuildable from the append-only stream,
and all identified integrity failures fail closed. The overall Foundry objective
remains active and `completion_ready=false`.
