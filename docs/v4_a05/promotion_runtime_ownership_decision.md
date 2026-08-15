# A05 promotion runtime ownership decision

## Status

`RATIFIED`

This record freezes who may execute the promotion commit chain. It does not
claim that the runtime is implemented, qualified, or exercised.

## Decision

A05 keeps executable ownership of the 23-node `evolution_promotion` chain and
declares a provider-neutral commit port. E05 owns the concrete adapter that
composes E02 effects, E03 capability leases, and the Foundry Kernel
lease-protected transaction.

Foundry Kernel and Noetic Ledger remain the sole authorities for capability
leases, fencing, persisted compare-and-swap, ledger events, effect receipts,
and replay.

## Why the direct-dependency option was rejected

Adding `A05 -> E03` or `A05 -> E04` creates a static cycle:

```text
A05 -> E04 -> E01 -> C04 -> C03 -> C02 -> C01 -> A05
```

Dependency inversion removes the cycle without weakening authority: A05 depends
only on its own port declaration, and E05 depends on A05 plus the effect and
capability packages it composes.

## Ratified authority changes

- `MASTER_SPEC.md` now records `C01` as depending on `A04, A05`, resolving the
  prior disagreement with the development manifest.
- `MASTER_SPEC.md` and the manifest now record `E05` as depending on
  `A05, A06, C05, E02, E03, E04`.
- The manifest adds `packages/foundry-kernel/src/integrations/evolution-promotion/**`
  to E05 write scope.
- The manifest adds the existing `nodes.py` and `registry.py` promotion
  entrypoints to A05 write scope, because the canonical workflow already binds
  them.

## Port contract

A05 declares exactly three closed operations:

```text
acquire_commit_lease(request)  -> lease reference
commit_promotion(request)      -> COMMITTED | EXISTING | OUTCOME_UNKNOWN
reconcile_promotion(identity)  -> resolved outcome | still unknown
```

A05 decides sequencing, required gate evidence, expected revisions, request
identity, idempotency, and G14 eligibility. A05 never decides that a supplied
lease is authoritative, never implements fencing or CAS, never fabricates a
receipt, and never falls back to an in-memory committer.

## Commit lifecycle

```text
sealed ActionIntent
-> registered/started Attempt
-> short-lived promotion:commit lease
-> Kernel lease-protected transaction
-> COMMITTED or EXISTING result
-> EffectReceipt recording/reconciliation
-> artifact/event/lease-use reconciliation
-> G14
```

A resolving `EffectReceipt` is recorded after the attempted effect, not required
before the compare-and-swap. An interrupted dispatch yields `OUTCOME_UNKNOWN`,
which may never become success and may never trigger a blind second commit.

## Remaining canonical-contract dependency

The commit operation still needs one C01-owned strict schema binding the
invocation identity and the Kernel result disposition, plus versioned
`NodeInvocation` and `ResultEnvelope` references to it.

A drafted schema and example are staged, unregistered, at
`docs/v4_a05/proposed_contracts/`. They are deliberately **not** in `schemas/`
or `examples/`, because the canonical inventory is frozen at 127/127 and every
prior count change required an explicit product-owner decision
(`EF4-A05-C01-B04-SHARED-CONTRACT` R71/R99, `HD-EF4-K01-SG001-20260730-001`,
`HD-EF4-O02-SG001-20260731-001`). Registering them without that decision would
break `tools/validate_spec_bundle.py` and bypass the C01 authority path.

Until that decision exists, `cas.validate_commit_operation` enforces the
binding structurally inside A05 and the entrypoints fail closed rather than
claiming a canonical contract already governs the operation.

The shared promotion contract has a second, independent blocker. The current
`PromotionDecision` requires G14 and its resolving receipts before the commit
that creates them. The recommended repair, not yet ratified by C01/C03, is a
14+1 proof split using existing record types: G00-G13 authorize CAS through the existing `ActionIntent` and
lease, the transaction creates the immutable commit set, and reconciliation
alone emits G14. No new pre-commit authority artifact is added. Until C01 and
C03 version that schema/runtime split and bind the authorization-dispatch hash
in the result contract, `commit_outcome` and `commit_promotion_atomically`
return `SPEC_GAP` before resolving or calling a commit port. Lease acquisition
remains independently available.

## Implemented in this change

- `models.py`: immutable request/outcome models and the `COMMITTED`,
  `EXISTING`, `OUTCOME_UNKNOWN` vocabulary.
- `cas.py`: the `PromotionCommitPort` protocol, `require_commit_port`
  fail-closed binding check, and outcome-to-request binding checks.
- `promotion.py`: lease acquisition and atomic-commit orchestration.
- `reconciliation.py`: unknown-outcome resolution and G14 completion.
- `errors.py`: single re-exported typed failure surface.
- `nodes.py`: the three commit nodes now delegate to those modules, so exactly
  one implementation exists per canonical node.
- `registry.py`: the runtime-binding check now enforces the A05 *package* as
  the authority boundary instead of a single module, while still refusing any
  executor outside A05.
- `workflows/evolution_promotion.workflow.yaml`: the three commit-phase nodes
  point at the new A05 entrypoints; all 23 nodes and gate order are unchanged.
- `models.py`: the exact dispatch hash covers both the sealed invocation and
  the derived PromotionDecision, ready for the C01/C03 result binding.
- `nodes.py`: G12 and approval resolution now refuse missing independence
  context instead of treating an incomplete context as evidence.

## Deterministic promotion authority stays in A05

The commit node does not accept a `PromotionDecision`. It calls
`derive_promotion_decision`, which runs `decide_promotion` over the sealed
`PromotionRequest` and then `validate_promotion_decision_semantics` against the
candidate's real `current_level`.

This matters because a supplied decision is only self-consistent: the canonical
schema constrains `granted_level` against the `promotion_ceiling` and
`hard_gate_status` *inside the same document*, and `current_level` does not
appear in it at all. Nothing in the document says where its ceiling came from,
and its self-hash is computed over whatever was supplied. Accepting one would
have made hard gates, the replication ceiling, and the rank rules advisory.

A caller may still pass `promotion_decision` as a cross-check; a mismatch with
the derived verdict refuses the commit rather than preferring either value.

## Request identity and retry stability

The canonical request hash is derived from the projected invocation binding
with its own field excluded, never copied from node input. The charter requires
that hash to cover the entire canonical request because idempotent replay
compares exactly that value: the same key with a different request must
conflict rather than return a prior result. A hash the caller merely asserts
could not do that, since one value could be attached to two different
operations and each half would still look internally consistent. A caller may
restate the derived hash; asserting a different one is refused.

Each commit result likewise carries its own digest, including an unresolved
one, so a result edited between the adapter and A05 cannot read as the
adapter's answer.

The shared authority mints a random `decision_id` per call. A05 normalizes it
to an identifier derived from the sealed idempotency key and reseals the
decision hash before any external record exists. Without this, a retry whose
Kernel result is `EXISTING` would compare a freshly minted identifier against
the one already committed, disagree, and reject its own successful
transaction. The verdict itself is still entirely the shared authority's; only
the identifier is made reproducible.

## Known follow-on work owned elsewhere

### A06-F005 was broken by this change and has been re-audited

The A06-0002 verifier proved `A06-F005` by asserting an implementation shape:
one module prefix `...evolution_authority.nodes:`, plus the literal strings
`PromotionCommitter` and `decide_promotion(request)` in `nodes.py`. Splitting
the commit-phase nodes into `promotion.py` and `reconciliation.py` made all
three assertions false while the finding itself stayed closed.

`artifacts/work_packages/A06/attempts/0003/` re-derives the finding from what
it actually claims: the bounded promotion helper must be bound to the canonical
workflow. That verifier checks the A05 package as the authority boundary,
resolves each executor the way the runtime does, requires the resolved
callable's defining module to be inside the package, and requires the commit
path to invoke both `decide_promotion` and
`validate_promotion_decision_semantics`.

It reports `PASS`, and it was driven against mutated workflows to confirm it
still refuses: retargeting a node outside the package, aliasing a node to a
foreign callable inside the package, and dropping a gate node all produce
`FAIL`. `F001`-`F004` and the schema-meta audit were re-executed from the
A06-0002 verifier against current source and still pass.

A06-0001 and A06-0002 are preserved unchanged as immutable history.

### Other follow-on

- `PromotionCommitter` remains live in C03-owned `governance/promotion.py`. It
  is *not* re-exported from either `governance/__init__.py` or the A05 package,
  but it is still imported directly by `tests/test_integration_forge_cycle.py`,
  the A05 legacy cases, and C04's verifier. Removing or shimming it requires
  C03 ownership; A05 cannot do it. Two commit implementations must not coexist
  past E05.
- How a node payload reaches these executors is still unspecified.
  `node-invocation.schema.json` is closed with twelve fields and no payload
  container, yet the commit path needs the operation, port binding, sealed
  `PromotionRequest`, and receipts. The chain is therefore not yet executable
  through the declared canonical invocation contract; E05 needs that binding
  resolved together with the C01 transport schema.
- The Kernel has no canonical record-type/value contract yet for candidate,
  PromotionDecision, or Passport revisions; the Passport document revision
  also has no ratified mapping to the state-store revision. E05 must consume a
  C01/C05-owned decision here rather than invent storage keys.
- `commitWithLease()` now exposes its authoritative lease-use and EventRecord
  IDs and hashes, so E05 does not need to duplicate E03's internal identity or
  ledger rules. This closes only the proof-exposure gap, not the shared storage
  and transport contracts above.
