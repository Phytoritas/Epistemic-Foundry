# T02 MCP Mutating Tool Architecture

Status: `ADOPTED DESIGN CONTRACT — v1.1`

Work package: `T02`. The v1.0 baseline was authorized by
`HD-EF4-T02-SCOPE-20260801-001`; the v1.1 FORGE additions are authorized by
`MASTER_SPEC.md` section “T02 additive FORGE public mutation contract”.

This contract records the architecture the T02 implementation must follow. It
was produced by a persistent ChatGPT Pro reasoning session on 2026-08-01 and
then verified locally against this repository. Pro's reasoning is advisory;
every claim below marked `verified` was checked against repository state, and
one Pro assumption was found wrong and corrected.

## 1. Catalog composition

- `contracts/mcp/t02/tool-catalog.yaml` declares the eleven mutating tool names
  exactly once and carries its own exact-11 test. The original nine remain in
  their original order; `foundry.work.classify` and `foundry.session.open` are
  appended.
- `contracts/mcp/t01/tool-catalog.yaml` and its generated descriptor
  projection stay byte-for-byte unchanged; the sealed exact-13 tests keep
  passing.
- `contracts/mcp/catalog-set.yaml` owns membership, order, and counts only. It
  contains no MCP tool-name literal.
- `tools/list` composition concatenates the two generated descriptor
  projections in catalog-set order and asserts 13 + 11 = 24 with globally
  unique names. No combined catalog YAML or combined descriptor JSON is
  generated: a generated file must never become a second declaring source.

Verified: the EF4-I22 guard in `tests/test_wire_literal_discipline.py` scans
only `src/epistemic_foundry/**/*.py`, so a contracts-directory catalog is a
declaring source per the invariant's own registry model rather than a second
copy. Verified: the sealed T01 `tools/list` test binds the T01 catalog
specifically, so a higher composition layer may expose 24 without weakening it.

### 1.1 FORGE classify and OPEN additions

`foundry.work.classify` and `foundry.session.open` are separate
`MUTATING_EFFECT` operations. A composite is forbidden: F01 classification and
F04 OPEN use different durable idempotency records, outboxes, ledger events,
retry outcomes, and reconciliation paths, so a classification that commits
before an OPEN conflict cannot be represented by one truthful effect status.

`foundry.work.classify` maps directly to the existing F01 classification input,
uses `mcp.write.classification`, and binds the successful MutationResult
`new_revision` to the immutable classification ID. A live success keeps
`preview` null rather than overloading the dry-run preview channel. `target_ref`
equals the F01 `request_id`.

`foundry.session.open` uses `mcp.write.session`. Its public arguments contain
`session_id`, `classification_id`, `corpus_snapshot_hash`, `actor`, and
`requested_at`. The trusted worker obtains `workspace_id` and
`idempotency_key` from the common mutation envelope; reads the sealed F01
replay projection to derive `request_id`, `run_spec_id`, and `policy_hash`; and
reads the current E01 ledger head immediately before calling F04. `target_ref`
equals `session_id`. Caller-supplied copies of those authoritative values are
neither required nor accepted.

Both tools are `medium` risk, `POLICY_CONDITIONAL`, and require the common
outer `expected_revision` to be null. Dry-run records the existing
`NOT_EXECUTED` intent/receipt path and makes no F01 or F04 effect call. F01
human override remains unexposed. On success, classification reports
`observed_revision: null` and `new_revision: classification_id`; OPEN reports
`observed_revision: null` and the published F04 session projection's
`state.revision`, rendered as a decimal string, as `new_revision`.

## 2. Layering and write scope

A Node-only implementation is rejected: it would have to duplicate the shared
Python envelope semantics, make Node authoritative for policy, leases,
receipts, and reconciliation, or hide domain logic under the Node write
directory. The mutation lifecycle stays provider-neutral in Python; Node stays
a thin adapter.

Corrected against Pro's assumption: the T01 MCP application root is
`src/epistemic_foundry/application/`, not a top-level `application/`. The new
package is therefore `src/epistemic_foundry/application/mcp_mutating/`.

Exact authorized extension (see the scope decision):

```text
contracts/mcp/catalog-set.yaml
contracts/mcp/t02/**
src/epistemic_foundry/application/mcp_mutating/**
tests/mcp/t02/**
tests/test_wire_literal_discipline.py   # registry addition only
```

The existing manifest grant already covers `packages/plugin-host/src/mcp/write/**`.

## 3. Request and result protocol

Every mutating tool input carries a required `mutation` block:

```text
dry_run              required boolean, never an omitted default
expected_revision    required, nullable; update-like tools require non-null
idempotency_key      required opaque bounded string
approval_record_ids  required unique array, may be empty
```

A client may never supply a `CapabilityLease` or an `EffectReceipt`: those are
server-created authority and evidence artifacts. `--json` is a CLI
presentation flag and is not an MCP input.

The semantic idempotency fingerprint covers protocol version, tool name,
principal, workspace, run, node, target ref, canonical business arguments,
`dry_run`, and `expected_revision`. `approval_record_ids` are authorization
evidence, not effect-defining arguments, so adding valid approval evidence
after an `APPROVAL_REQUIRED` response is not a conflict. Because `dry_run` is
in the fingerprint, a dry-run key can never later be reused for a live commit.

The result envelope's `data` carries a required `mutation` payload:

```text
action_intent_id, capability_lease_id, effect_receipt_id, dry_run,
effect_status, committed, expected_revision, observed_revision,
new_revision, reconciliation_required
```

with these exact combinations:

| `effect_status` | `committed` | `new_revision` | `reconciliation_required` |
| --- | --- | --- | --- |
| `SUCCEEDED` | `true` | non-null | `false` |
| `NOT_EXECUTED` | `false` | `null` | `false` |
| `FAILED` | `false` only with affirmative proof of no commit | `null` | `false` |
| `ROLLED_BACK` | `false` | `null` or current | `false` |
| `UNKNOWN` | `null` | `null` | `true` |

`committed` is therefore `boolean | null`. `UNKNOWN` must never be rendered as
`committed=false`: that would falsely claim the effect did not happen.
`capability_lease_id` exposes an identifier only, never bearer material.

Verified: the sealed result envelope's `data` and the error envelope's
`details` are both `object | null`, so both extensions compose without
touching the sealed schemas.

## 4. Dry-run semantics

A dry run records the `ActionIntent` and a `NOT_EXECUTED` `EffectReceipt`. It
does not return an unrecorded would-be intent. The dry-run path passes the
same protocol, schema, authentication, workspace, policy, approval, and lease
checks, verifies `expected_revision` where the tool requires it non-null,
persists the intent, performs preview only, makes zero target-effect calls,
and persists a receipt with
`status=NOT_EXECUTED`, `reconciliation_required=false`, and a canonical
synthetic non-effect `external_operation_id`.

This is the safer choice because it leaves durable proof that the request met
the same admission logic, that the effect was intentionally not executed, and
that the idempotency key has a known outcome — so replay can distinguish a
dry run from crash ambiguity.

## 5. Approval placement and typed errors

Approval verification sits inside `CAPABILITY_AUTHORIZATION`, after policy
evaluation and before lease issuance. The frozen order gains no new top-level
stage:

```text
CAPABILITY_AUTHORIZATION
  1 derive canonical target and exact resource scope
  2 construct the stable ActionIntent candidate identity
  3 evaluate policy and risk
  4 determine approval requirements
  5 resolve and verify ApprovalRecords
  6 reject self-approval
  7 issue or validate the exact-scope CapabilityLease
HANDLER_EXECUTION
  1 resolve or reserve idempotency
  2 create-or-load the deterministic ActionIntent and CAS-bind it
  3 revalidate lease expiry, revocation, scope, policy hash, fence
  4 enforce expected revision / CAS
  5 atomically persist and bind the durable Attempt
  6 execute the effect once, or finish the already-computed dry-run preview
  7 persist the EffectReceipt against that exact Attempt
  8 CAS-bind the receipt and reconcile when necessary
```

Only the transaction that first creates the Attempt may call the live effect
executor. An ActionIntent without an Attempt is `NOT_STARTED` and remains safe
to retry. An Attempt without a receipt is `RECONCILING`: ordinary replay must
not execute again or fabricate an `UNKNOWN` receipt while the first caller may
still be running. It returns the retryable `EFFECT_RECONCILING` mutation error
until a receipt tail exists. The receipt store returns the append-only current
tail for the Attempt, allowing replay to adopt a receipt persisted just before
a crash.

A lease is never issued before required approvals pass; its scope covers the
exact workspace and target rather than the tool class; its expiry is no later
than the earliest applicable approval expiry or the policy maximum; and its
fencing token is revalidated immediately before the effect.

The sealed T01 top-level `error_code` enum is not extended and no parallel
same-version error envelope is created. Instead a closed mutation subcode
rides in `details`:

| `details.mutation_error_code` | top-level `error_code` |
| --- | --- |
| `APPROVAL_REQUIRED` | `UNAUTHORIZED` |
| `APPROVAL_DENIED` | `UNAUTHORIZED` |
| `APPROVAL_INVALID` | `UNAUTHORIZED` |
| `SELF_APPROVAL_FORBIDDEN` | `UNAUTHORIZED` |
| `LEASE_DENIED` | `UNAUTHORIZED` |
| `LEASE_INVALID` | `UNAUTHORIZED` |
| `REVISION_CONFLICT` | `INVALID_REQUEST` |
| `EFFECT_RECONCILING` | `INTERNAL` |
| `RECONCILIATION_FAILED` | `INTERNAL` |

Key/fingerprint mismatch uses the existing top-level `IDEMPOTENCY_CONFLICT`.
An unresolved external effect is not `INTERNAL`: it returns a result envelope
with `effect_status=UNKNOWN` and `reconciliation_required=true`.
`RECONCILIATION_FAILED` is reserved for failure of the reconciliation
mechanism itself. Inaccessible approval records must not be disclosed through
`NOT_FOUND` when that would leak their existence.

## 6. Module layout

```text
contracts/mcp/catalog-set.yaml
contracts/mcp/t02/tool-catalog.yaml
contracts/mcp/t02/schemas/common-mutation-input.schema.json
contracts/mcp/t02/schemas/mutation-result.schema.json
contracts/mcp/t02/schemas/mutation-error-details.schema.json
contracts/mcp/t02/schemas/tools/<tool>.input.schema.json      (11)
src/epistemic_foundry/application/mcp_mutating/__init__.py
src/epistemic_foundry/application/mcp_mutating/ports.py
src/epistemic_foundry/application/mcp_mutating/service.py
src/epistemic_foundry/application/mcp_mutating/handler_factory.py
src/epistemic_foundry/application/mcp_mutating/reconciliation.py
packages/plugin-host/src/mcp/write/generated/t02-tool-descriptors.json
packages/plugin-host/src/mcp/write/catalog-set.mjs
packages/plugin-host/src/mcp/write/adapter.mjs
tests/mcp/t02/test_tool_catalog.py
tests/mcp/t02/test_tools_list.py
tests/mcp/t02/test_mcp_effect.py
tests/mcp/t02/test_approval.py
```

The Node adapter is `.mjs` rather than `.ts` to match the existing
plugin-host modules in this repository.

## 7. Open items to resolve during implementation

- `ApprovalRecord.subject_id` is a free-form non-empty string (verified), so
  it can bind a pre-persistence intent-candidate id without inventing a
  mutable draft `ActionIntent`.
- The reconciliation contract for how a later receipt resolves an immutable
  `UNKNOWN` receipt must reuse the existing kernel semantics rather than
  introducing a second reconciliation model.
