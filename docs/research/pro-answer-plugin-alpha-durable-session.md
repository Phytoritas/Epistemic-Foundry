**Decision: do not implement the durable session service against the current contracts.** The proposed architecture—immutable CAS payload → ordered ledger append → derived CAS snapshot/head → restart reconciliation—is sound, but only after one narrow canonical amendment lands. The exact blocker is the absence of a contract that simultaneously defines canonical session events, caller-stable idempotent/conditional E01 append semantics, the replay-complete F01 classification view, and artifact attachment reduction. Without that amendment, crash retry can duplicate or fork events, and deterministic F02 replay cannot be demonstrated.

## 1. Required authority amendment

Create one authority grant:

```text
authority_id: PLUGIN_ALPHA_SESSION_COMPOSITION_20260815
canonical_contract: ForgeSessionJournalCompositionV1
contract_owner: F02
qualified_release_status: SPEC_BUNDLE
```

It authorizes only these changes:

1. **F02** owns the session aggregate, canonical event payloads, reducer, repository interface, and implementation scope:

   ```text
   packages/foundry-kernel/src/forge/session/**
   ```

2. **E01** amends its own contract to provide:

   ```text
   append_once(
     stream_id,
     event_id,
     event_type,
     payload_digest,
     expected_stream_position,
     expected_last_event_id
   )
   ```

3. **F01** amends its own contract to provide a replay-complete read and, for session-scoped classifications, an atomic session-attachment intent.

4. The existing manifest authority adds F02’s missing write scope and dependency edges. F02 may implement the contract but may not accept its own evidence.

No D01 or D03 semantic amendment is required: their existing transaction, CAS, immutable-object, receipt, staging, and SAFE_MODE capabilities are sufficient.

The authority must explicitly prohibit:

```text
F02 self-acceptance
a second session state authority
unconditional E01 append
raw-cwd session identity
implicit recovery from a materialized snapshot when the ledger disagrees
PLUGIN_ALPHA status promotion
```

### Ownership amendment

Add only:

```yaml
F02:
  write_scope:
    - packages/foundry-kernel/src/forge/session/**
    - <canonical location of ForgeSessionJournalCompositionV1>
  depends_on:
    - D01
    - D03
    - E01
    - F01
    - F03
```

Add only missing dependencies if some are already present.

E01 retains ownership of its append contract. F01 retains ownership of classification reads and its outbox. The existing independent PLUGIN_ALPHA acceptance owner—not F02, E01, or F01 implementation authors—accepts the resulting evidence.

## 2. Single state authority

The sole semantic authority is:

```text
ordered E01 session stream
+ immutable D03 payloads referenced by that stream
```

Everything else is derived or operational:

```text
D01 session head          derived projection pointer
D03 session snapshot      derived projection payload
D01 mutation outbox       delivery and crash-recovery coordination
host-session lookup       derived index
SessionStart output       advisory host integration
```

The D01 head must never be used to overwrite, truncate, or synthesize ledger history. Reconciliation runs only in this direction:

```text
E01 + D03 → replay → D03 snapshot → D01 head
```

Never:

```text
D01 head → manufacture or repair E01 events
```

## 3. Exact canonical types

### `ForgeSessionMutationOutboxV1`

A revisioned D01 operational record:

```yaml
schema_id: ForgeSessionMutationOutboxV1
operation_id: <lowercase sha256>
session_id: <lowercase sha256>
workspace_id: <canonical workspace identity>
operation_kind: OPEN | TRANSITION | ATTACH_ARTIFACT
command_digest: <sha256>
event_id: <same value as operation_id>
event_type: <canonical event type>
event_payload_digest: <D03 digest>
expected_stream_position: <integer>
expected_last_event_id: <sha256 or null>
delivery_state: PREPARED | APPENDED | MATERIALIZED | REJECTED
ledger_position: <integer or null>
snapshot_digest: <D03 digest or null>
result_aggregate_hash: <sha256 or null>
failure_code: <canonical code or null>
record_revision: <D01 revision>
```

Invariants:

```text
operation_id uniquely identifies one canonical command
same operation_id + same command_digest = idempotent retry
same operation_id + different command_digest = integrity failure
at most one nonterminal mutation per session
delivery_state is operational, not semantic authority
```

### `ForgeSessionHeadV1`

A revisioned D01 projection pointer:

```yaml
schema_id: ForgeSessionHeadV1
session_id: <sha256>
workspace_id: <canonical workspace identity>
stream_id: <canonical E01 stream id>
stream_position: <integer>
last_event_id: <sha256>
fsm_revision: <integer>
fsm_state_hash: <sha256>
aggregate_hash: <sha256>
snapshot_digest: <D03 digest>
record_revision: <D01 revision>
```

It contains no independently editable session state.

### `ForgeSessionSnapshotV1`

An immutable D03 projection artifact:

```yaml
schema_id: ForgeSessionSnapshotV1
session_id: <sha256>
workspace_id: <canonical workspace identity>
stream_position: <integer>
last_event_id: <sha256>
fsm_revision: <integer>
fsm_state: <canonical F02 ForgeSessionState>
fsm_state_hash: <sha256>
attachments:
  - attachment_id: <sha256>
    role: <canonical role>
    artifact_manifest_digest: <sha256>
    producer_receipt_digest: <sha256>
aggregate_hash: <sha256>
reducer_profile_id: ForgeSessionAggregateReducerV1
```

`attachments` is sorted by `attachment_id`. `aggregate_hash` is calculated over the canonical snapshot body with the `aggregate_hash` field omitted.

`stream_position` advances for every session event. `fsm_revision` advances only for an F02 transition. Artifact attachment must not manufacture an F02 revision.

### `ClassificationReplayViewV1`

F01 must expose this exact replay-facing view:

```yaml
schema_id: ClassificationReplayViewV1
classification_record_id: <id>
classification_record_revision: <integer>
classification_payload_digest: <sha256>
identity_context: <stored canonical identity context>
identity_context_hash: <sha256>
artifact_manifest_digest: <sha256>
commit_receipt_digest: <sha256>
```

The session service stores the canonicalized view in D03 and records its digest in the transition event. Later replay resolves that immutable digest; it does not depend on a future “current” F01 read.

## 4. Canonical session identity

For a Codex-bound session:

```text
binding_body =
  JCS({
    "host_kind": "codex",
    "host_session_id": <SessionStart session_id>,
    "workspace_id": <canonical workspace_id>
  })

session_id =
  lowercase_sha256(
    UTF8("forge.session.binding.v1") || 0x00 || binding_body
  )
```

Rules:

* `cwd` is input to the canonical workspace resolver; it is not itself `workspace_id`.
* `source`—`startup`, `resume`, `clear`, or `compact`—does not participate in identity.
* The same Codex session in different canonical workspaces produces different Foundry sessions.
* `resume`, `clear`, and `compact` do not append another open event if the binding already exists.
* Failure to resolve canonical `workspace_id` is `WORKSPACE_ID_UNRESOLVED`; no session is opened.

## 5. Exact event and append contract

E01 must expose conditional, idempotent append:

```text
append_once(
  stream_id,
  event_id,
  event_type,
  payload_digest,
  expected_stream_position,
  expected_last_event_id
)
```

Required behavior:

```text
stream head matches expectation:
  append exactly once and return ledger_position

event_id already exists with identical event tuple:
  return the existing ledger_position

event_id already exists with different type, payload, or stream:
  enter SAFE_MODE

stream head does not match expectation and event_id is absent:
  reject with STALE_SESSION_HEAD; append nothing
```

This call executes in E01’s own D01 transaction. It must never be invoked inside another D01 transaction.

### `ForgeSessionOpenedV1`

```yaml
schema_id: ForgeSessionOpenedV1
session_id: <sha256>
workspace_id: <canonical workspace_id>
host_binding:
  host_kind: codex
  host_session_id: <host session id>
initial_fsm_state: <canonical F02 initial state>
initial_fsm_state_hash: <sha256>
reducer_profile_id: ForgeSessionAggregateReducerV1
```

Hook `source`, invocation surface, process ID, and timestamps belong in an invocation receipt, not in this semantic event payload. Otherwise the same open operation retried through CLI instead of the hook could produce a different payload under the same identity.

Open uses:

```text
expected_stream_position = 0
expected_last_event_id = null
```

### `ForgeSessionTransitionAppliedV1`

```yaml
schema_id: ForgeSessionTransitionAppliedV1
session_id: <sha256>
transition_input_digest: <D03 digest>
admission_receipt_digest: <D03 digest>
classification_replay_view_digests:
  - <D03 digest>
pre_fsm_revision: <integer>
pre_fsm_state_hash: <sha256>
post_fsm_revision: <integer>
post_fsm_state_hash: <sha256>
pre_aggregate_hash: <sha256>
post_aggregate_hash: <sha256>
```

The reducer must recompute the post-state from the pre-state, transition input, replay views, and F03 admission receipt. The recorded post hashes are assertions to verify, not state to trust.

### `ForgeSessionArtifactAttachedV1`

```yaml
schema_id: ForgeSessionArtifactAttachedV1
session_id: <sha256>
attachment_id: <sha256>
role: <canonical artifact role>
artifact_manifest_digest: <sha256>
producer_receipt_digest: <sha256>
pre_aggregate_hash: <sha256>
post_aggregate_hash: <sha256>
fsm_revision: <unchanged F02 revision>
```

For F01-produced artifacts, F01’s durable commit transaction must also emit:

```yaml
schema_id: SessionArtifactAttachmentIntentV1
intent_id: <sha256>
session_id: <sha256>
role: <canonical role>
artifact_manifest_digest: <sha256>
producer_receipt_digest: <sha256>
```

This intent is delivered through the session mutation path. The session association must be supplied to F01’s commit command; it must not be inferred from `cwd`, the latest session, or a singleton process variable.

## 6. Idempotency keys

All mutation operations use:

```text
operation_id =
  lowercase_sha256(
    UTF8("forge.session.operation.v1") || 0x00 ||
    JCS({
      "session_id": session_id,
      "operation_kind": operation_kind,
      "expected_stream_position": expected_stream_position,
      "expected_last_event_id": expected_last_event_id,
      "command_digest": command_digest
    })
  )

event_id = operation_id
```

For open, `command_digest` is the digest of `ForgeSessionOpenedV1`.

For transition, it covers at least:

```text
transition_input_digest
admission_receipt_digest
classification_replay_view_digests
```

For attachment, it covers:

```text
attachment_id
role
artifact_manifest_digest
producer_receipt_digest
```

A stale command is not silently rebased. It is rejected, reconciled, and re-admitted as a new operation against the new stream head.

## 7. Exact transaction and outbox sequence

For every mutation:

1. **Reconcile first.** Resolve any nonterminal outbox record for the session. Refuse mutation if D01 is in SAFE_MODE.

2. **Resolve inputs.** For transitions, resolve F03 admission and the exact F01 replay views. For attachment, resolve the artifact manifest and producer receipt.

3. **Build canonical event payload.** Calculate `command_digest`, `operation_id`, `event_id`, and the expected stream head.

4. **Write event payload to D03.** This is idempotent. A crash here may leave an unreferenced CAS object, but it creates no session effect.

5. **D01 transaction A — prepare.**

   ```text
   insert ForgeSessionMutationOutboxV1(PREPARED)
   assert expected ForgeSessionHeadV1 record revision
   assert no other nonterminal operation for this session
   ```

   Do not call E01 within this transaction.

6. **E01 append outside all caller D01 transactions.**

   ```text
   E01.append_once(...)
   ```

7. **D01 transaction B — acknowledge append.**

   ```text
   PREPARED → APPENDED
   store ledger_position
   ```

8. **Replay the authoritative stream.** Resolve every D03 payload and run the aggregate reducer through E01’s double-rebuild mechanism.

9. **Write `ForgeSessionSnapshotV1` to D03.**

10. **D01 transaction C — materialize atomically.**

    ```text
    CAS ForgeSessionHeadV1 from the expected prior pointer
    APPENDED → MATERIALIZED
    store snapshot_digest and result_aggregate_hash
    ```

11. Return the result derived from the ledger position and snapshot digest.

No E01 append occurs inside transactions A, B, or C, so D01’s nested-transaction prohibition is respected.

## 8. Crash states and restart action

| Observed state                          | Semantic result       | Restart action                         |
| --------------------------------------- | --------------------- | -------------------------------------- |
| Event payload exists; no outbox         | No session effect     | Reuse or eventually collect the orphan |
| Outbox `PREPARED`; event absent         | No session effect yet | Retry `append_once`                    |
| Outbox `PREPARED`; event present        | Event committed       | Record `APPENDED`, replay              |
| Outbox `APPENDED`; snapshot absent      | Event committed       | Replay and write snapshot              |
| Snapshot exists; head is behind         | Event committed       | CAS the derived head                   |
| Head matches; outbox not final          | Event committed       | Mark `MATERIALIZED`                    |
| Append rejected as stale                | No event appended     | Mark `REJECTED`; caller must re-admit  |
| Same `event_id`, different payload/type | Integrity conflict    | SAFE_MODE                              |
| Projection ahead of ledger              | Authority conflict    | SAFE_MODE                              |
| Same stream position, different hash    | Authority conflict    | SAFE_MODE                              |

There is no “roll back” after an E01 event has committed. Recovery completes materialization from the authoritative stream.

## 9. Replay comparison

The canonical trace entry is:

```yaml
stream_position: <integer>
event_id: <sha256>
event_type: <canonical type>
payload_digest: <sha256>
pre_aggregate_hash: <sha256 or null>
post_aggregate_hash: <sha256>
post_fsm_revision: <integer>
post_fsm_state_hash: <sha256>
```

`E01.rebuild()` runs `ForgeSessionAggregateReducerV1` twice. The JCS-encoded trace arrays must be byte-identical.

The final replay result is compared with `ForgeSessionHeadV1` on:

```text
stream_position
last_event_id
fsm_revision
fsm_state_hash
aggregate_hash
snapshot_digest
```

Automatic repair is allowed only when the materialized projection is absent or a strict, valid prefix of the authoritative stream.

The following enter SAFE_MODE:

```text
double-rebuild trace mismatch
unknown session event type
missing or invalid D03 event payload
missing classification replay view
invalid F03 admission receipt
event sequence gap
pre-state or predecessor mismatch
projection ahead of stream
same-position hash disagreement
event-id collision with nonidentical content
```

## 10. SessionStart, CLI, and MCP

**Yes:** `SessionStart` should call the same `open_or_resume()` operation used by CLI and MCP, keyed by canonical `workspace_id` plus the host `session_id`.

`SessionStart` provides `session_id`, `cwd`, and `source`; plugin hook commands receive `PLUGIN_ROOT` and writable `PLUGIN_DATA`. Hooks can also be disabled, and plugin hooks may be skipped until trusted. Therefore, the hook cannot be the only lifecycle entrance. ([OpenAI Developers][1])

Rules:

* Use `PLUGIN_DATA` for D01, D03, ledger, outbox, and session projections.

* Treat `PLUGIN_ROOT` as executable/resource input only.

* `startup`, `resume`, `clear`, and `compact` all perform the same idempotent open-or-resume lookup.

* A hook failure must not create an in-memory or temporary session.

* The hook may warn and let Codex continue, but all Foundry operations requiring a session return `FOUNDRY_SESSION_UNAVAILABLE`.

* Hook-disabled mode must retain:

  ```text
  efoundry session open --workspace <path> --host codex --host-session-id <id>
  efoundry session resume --session-id <session_id>
  ```

* CLI, MCP, and hook code must invoke one repository/service implementation. None may maintain its own session cache as authority.

* Do not advertise `foundry.session.get` until it reads this repository and returns the canonical head/snapshot result.

## 11. Pathless runtime decision

**Bundle Python.**

The qualified PLUGIN_ALPHA path must execute a plugin-bundled interpreter by an absolute path derived from `PLUGIN_ROOT`, for example:

```text
<absolute PLUGIN_ROOT>/runtime/python/<platform>/python[.exe]
```

Rules:

```text
no PATH lookup
no bare python/python3/py
no editable installation
no PYTHONPATH
no fallback to repository source
no silent fallback to a host interpreter
```

Node entrypoints may launch the bundled interpreter, but they must not reimplement D01/D03/E01/F01/F02/F03 semantics.

An explicit external absolute interpreter may remain a developer-only override, but results produced through it do not count as PLUGIN_ALPHA release evidence unless separately authorized. Missing, unsupported, or integrity-invalid bundled Python produces:

```text
BUNDLED_RUNTIME_UNAVAILABLE
BUNDLED_RUNTIME_INTEGRITY_FAILED
```

and no session mutation occurs.

Removing Python from the critical path would require a second Node implementation of the canonical state, ledger, admission, and replay semantics. Requiring an arbitrary host Python would weaken installed reproducibility. Bundling preserves one semantic implementation and satisfies the pathless constraint.

## Implementation order

1. **Land `PLUGIN_ALPHA_SESSION_COMPOSITION_20260815`.** Assign F02 session-contract and implementation scope; preserve independent acceptance.

2. **Amend E01 first.** Implement and test `append_once` with event-id idempotency and expected-head rejection. Do not start the session repository before this exists.

3. **Amend F01.** Add `ClassificationReplayViewV1` and atomic `SessionArtifactAttachmentIntentV1` emission for session-scoped commits.

4. **Freeze F02 schemas and reducer.** Add the three event payloads, aggregate snapshot, head, outbox, canonical hashes, and double-rebuild trace.

5. **Implement the shared repository.** Put it only under:

   ```text
   packages/foundry-kernel/src/forge/session/**
   ```

   Implement prepare, append, replay, materialize, reconciliation, and SAFE_MODE behavior.

6. **Add restart reconciliation.** Reconcile all nonterminal outbox rows and verify every materialized head before accepting writes.

7. **Integrate the hook and explicit CLI.** Both call the same `open_or_resume()` service; hook-disabled operation remains complete.

8. **Point MCP session reads at the same repository.** Do not introduce MCP-local state or advertise unavailable session operations.

9. **Switch the critical launcher to bundled Python.** Use only the absolute plugin-local interpreter and `PLUGIN_DATA` persistence root.

10. **Produce executable evidence without changing release status.** The qualified status remains `SPEC_BUNDLE`; this decision passes no PLUGIN_ALPHA gate.

## Exact fail-closed boundaries

No session mutation is permitted when any of these holds:

```text
ForgeSessionJournalCompositionV1 not authorized
E01 append_once unavailable
canonical workspace_id unresolved
D01 SAFE_MODE active
another session mutation cannot be reconciled
expected stream head is stale
event payload or receipt is missing/corrupt
F01 identity_context replay view unavailable
F03 admission unresolved or invalid
artifact has no canonical session attachment intent
reducer traces differ
projection conflicts with authoritative replay
bundled interpreter unavailable or integrity-invalid
```

A disabled or failed hook does not block ordinary Codex use, but it leaves Foundry session-dependent operations unavailable until explicit CLI open/resume succeeds. No ephemeral fallback, “latest session,” raw-cwd identity, or snapshot-as-authority path is permitted.

[1]: https://developers.openai.com/codex/hooks "Hooks | ChatGPT Learn"
