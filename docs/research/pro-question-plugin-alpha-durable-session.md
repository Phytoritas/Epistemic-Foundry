# PLUGIN_ALPHA durable session architecture decision

Act as an advisory architecture reviewer. Do not ask for more context. Give a
single decisive design or identify the exact shared contract that makes it
unsafe to implement.

Target: implement `docs/decisions/20260815-plugin-alpha-goal.md` while the
qualified release status remains `SPEC_BUNDLE`.

Existing canonical components:

- D01 `SQLiteStateStore`: WAL, transactions, immutable and revisioned records,
  compare-and-swap, SAFE_MODE. Nested transactions are denied.
- D03 `ContentAddressedArtifactStore`: immutable artifacts, manifests and
  receipts, private staging and rename.
- E01 `NoeticLedger`: CAS-backed payloads plus append-only event/run-stream
  records in D01. `append()` opens its own D01 transaction. `rebuild()` runs a
  supplied reducer twice and compares canonical traces.
- F01 classification committer: durable classification record plus CAS
  artifact/receipt and ledger outbox. Its public read result omits the stored
  `identity_context`, even though F02 replay requires it.
- F02 FSM: canonical `ForgeSessionState`, deterministic transition/replay,
  revision and state hash.
- F03 admission: resolves immutable receipts and returns a deterministic
  transition admission.

Missing:

- no production durable session repository/service;
- no canonical session-open event payload;
- no manifest owner for `packages/foundry-kernel/src/forge/session/**`;
- no public classification read that returns the identity context needed by
  replay;
- no reducer/effect that attaches newly produced artifacts to a session;
- plugin currently has only an observation-only SessionStart hook and direct
  Node MCP; `foundry.session.get` is UNAVAILABLE.

Official Codex hook facts: SessionStart provides `session_id`, `cwd`, and
`source`; plugin commands receive `PLUGIN_ROOT` and `PLUGIN_DATA`; hooks can be
disabled.

Questions:

1. Can a PLUGIN_ALPHA session service be implemented safely using the existing
   contracts, with CAS payload write -> durable ledger append -> materialized
   session CAS -> reconciliation on restart? Or is a new canonical event or
   composition contract required first?
2. If implementation is authorized, freeze the exact record types, event
   payloads, transaction/outbox sequence, idempotency keys, crash states, and
   replay comparison. Avoid a second state authority.
3. If a new contract is unavoidable, name the smallest exact authority
   amendment and owner. Do not hand-wave “add a service.”
4. Decide whether SessionStart should open/resume the Foundry session keyed by
   host session ID and workspace, while CLI/MCP share that repository and
   hook-disabled mode keeps explicit CLI open/resume available.
5. Decide the pathless runtime strategy: remove Python from the critical
   PLUGIN_ALPHA path and keep it optional behind an absolute interpreter path,
   require an absolute host interpreter for all operations, or bundle Python.

Return a concise architecture decision, implementation order, and exact
fail-closed boundaries. Do not claim any gate passed.
