# PLUGIN_ALPHA durable FORGE session composition gap

Status: `APPROVED_FOR_IMPLEMENTATION`

Approved freeze: `DURABLE_FORGE_V1`  
Approved by: repository owner, 2026-08-15

This decision record is not a release claim and does not mark any acceptance
gate as passing. It records the authority decisions needed before the installed
plugin may own a durable FORGE session path.

## What is already authorized

The existing F01 outbox pattern may be reused to compose D01 SQLite, D03 CAS,
E01 Noetic Ledger, F02 deterministic reduction, and F03 transition admission.
The materialized session record remains a reducer projection; the append-only
ledger remains the replay authority.

The implementation sequence must be:

1. one D01 transaction performs the idempotency probe, deterministic reduction,
   session-record CAS, and creation of an unpublished outbox record;
2. outside that transaction, the exact payload is registered in D03 and the
   exact event is appended through E01;
3. a second D01 transaction marks the outbox published with the resolving
   hashes;
4. restart reconciliation repeats steps 2–3 with the same immutable IDs;
5. restore reads F01's stored classification identity context, replays the
   session events through F02, and refuses a stored/replayed state-hash
   mismatch.

This uses D01 `revisioned_records`; it adds no SQLite table or schema version.

## Gap 1 — artifact retention has no owner

F02 `reduceForgeTransition` preserves `ForgeSessionState.artifact_ids` and has
no canonical operation that adds newly accepted artifacts. F03, however,
rejects a phase artifact that is not already retained in that array. An
adapter-side mutation would become a second FSM authority and would silently
invent state-hash semantics.

Required decision: the F02/F03 authority owner must define one deterministic,
receipt-bound artifact-retention transition or reducer input. It must state
which admitted receipt bindings may add which artifact IDs, when the state
hash changes, how replay reconstructs the same set, and how return-edge
staleness interacts with retention. Until then, the product must not claim a
multi-phase durable FORGE session.

## Gap 2 — F04 does not yet own session composition

The current manifest assigns D01, D03, E01, F02, and F03 only their leaf
directories. X01 owns the Codex adapter and plugin payload, but the
constitution forbids a host adapter from owning canonical Kernel state.

The closed A01–Z06 package grammar does not permit a new `D07`. F04 already
depends on F02 and F03 and transitively reaches D01, D03, E01, and F01. It is
also the existing F-phase end-to-end integration checkpoint.

Required decision: add
`packages/foundry-kernel/src/forge/session/**` to F04's write scope and state
that F04 owns durable session composition and restore. F04 may define private
D01 record projections and composition code; it may not create a second
ledger, FSM, CAS, or public wire schema.

## Gap 3 — E01 append lacks an expected-head condition

E01 makes an `event_id` idempotent, but a new event is appended to the current
tail without comparing the caller's expected stream position or tail event.
A session transition reduced against one head must not be silently appended
after a foreign or concurrent event.

Required decision: E01 must expose a conditional idempotent append that binds
the immutable event intent to the expected stream position and expected tail
event hash or ID. Matching existing event intent returns the existing event;
a stale head with no matching event appends nothing; a reused event ID with a
different intent enters the existing integrity-failure path.

## Gap 4 — F01 public reads omit replay identity

F01 already persists `identity_context`, but its public classification read
omits that context while F02 replay requires it. Copying the context into a
session record would duplicate classification authority.

Required decision: F01 must expose a replay-complete, immutable read projection
containing the stored classification and its exact `identity_context`, bound
to the existing classification artifact and receipt. Session replay resolves
that F01 projection; it never reconstructs or edits the context locally.

## Gap 5 — installed consumers have no lawful Kernel session surface

`@epistemic-foundry/foundry-kernel` declares no package exports, and the current
plugin adapter has no trusted injected session port. Adding F04 implementation
files without deciding the callable boundary would leave durable composition
unreachable or encourage a host-side second implementation.

Required decision: F04 must export one narrow Kernel session composition port,
or an existing integration owner must inject that exact port into the plugin.
The adapter may call it; it may not recreate FSM, ledger, CAS, outbox, replay or
authorization semantics.

## Gap 6 — the acceptance owner has not assigned durable-session evidence

The current `PLUGIN_ALPHA` list names fifteen gates but no separate durable
session gate. The closest gate is `sqlite_wal_crash_recovery`, while the scope
text also promises working FORGE state and recovery.

Required decision: make durable open/transition/restart/reconcile/replay part of
`sqlite_wal_crash_recovery`, or add a sixteenth named gate and update every
fifteen-gate statement. The smaller compatible choice is to bind it explicitly
to `sqlite_wal_crash_recovery`.

## Approved product-owner freeze — `DURABLE_FORGE_V1`

The following decision is approved for implementation. It changes
no existing canonical schema bytes, D01 schema version, historical state hash,
event hash or current unconditional E01 caller.

1. F03 issues a versioned `ForgeTransitionAdmission` whose used receipt
   bindings determine an exact append-only `artifact_retention` set. Extra
   receipts unused by the transition are rejected.
2. F02 keeps the current reducer unchanged and adds an admitted reducer. It
   preserves existing artifact order, appends only newly admitted IDs in
   canonical order, never deletes IDs on return, and records staleness only in
   the existing phase projection. Its transition hash binds the admission and
   retained-ID delta.
3. E01 keeps `append()` and adds a conditional sibling operation. A matching
   existing immutable event is idempotent; an absent event with a stale expected
   head returns `STALE_LEDGER_HEAD` without a write; an event-ID intent conflict
   keeps the existing integrity-conflict behavior.
4. F01 keeps existing reads and adds an immutable replay projection containing
   the stored classification and exact `identity_context`, cross-bound to its
   D03 manifest, artifact receipt and published ledger event.
5. F04 owns `packages/foundry-kernel/src/forge/session/**`, including `OPEN` and
   `TRANSITION` event payloads, private D01 `.v1` records, published/pending
   projections, outbox reconciliation and replay. An unpublished candidate is
   never returned as canonical session state.
6. A stale ledger head moves the outbox to `CONFLICTED` and preserves the last
   published projection. Rebase requires a new request/idempotency intent.
   Session `OPEN` is also a ledger event.
7. The installed adapter consumes only the exported/injected F04 port. The
   independent Python FSM and host adapters are not session authorities.
8. Durable-session acceptance is part of `sqlite_wal_crash_recovery`, covering
   crash windows, duplicate retry, stale head, restart reconciliation, OPEN
   replay and stored-versus-replayed state-hash mismatch.

The approval also adds `packages/foundry-kernel/src/forge/session/**` and its
durable criteria to F04's manifest write scope. This approval does not pass the
durable-session acceptance gate; only executed, independently reviewed results
may do that.

## Work that is not blocked

- make the plugin payload trackable and reproducible from a clean clone;
- keep the PLUGIN_ALPHA-critical CLI/MCP path in the existing canonical Node
  Kernel, remove runtime PATH probing, and keep Python-only auxiliary commands
  optional behind an exact absolute interpreter path;
- keep `status`, `health`, and `map.query` honest;
- bind D01/D03 component health after the Kernel bundle exists;
- keep `claim.get`, `atlas.query`, `passport.get`, and `replay.diff`
  `UNAVAILABLE` with exact reasons until their authoritative producers exist;
- implement installed-copy CLI/MCP/hook lifecycle automation without claiming
  that the durable-session gate passed.
