# A06-0003 constitutional re-audit review

Package recommendation: `PASS`

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_REVIEW`

## Why this attempt exists

A05 split the three commit-phase nodes out of `nodes.py` into `promotion.py`
and `reconciliation.py` so the commit path could invoke a Foundry Kernel
lease-protected transaction through an injected port. That change made three
assertions in the A06-0002 verifier false:

- every executable node reference begins with `...evolution_authority.nodes:`
- the literal `PromotionCommitter` appears in `nodes.py`
- the literal `decide_promotion(request)` appears in `nodes.py`

Running the A06-0002 verifier against current source therefore reports
`f005_status: FAIL` with the three commit-phase nodes listed as unbound.

## What was actually re-audited

`A06-F005` states that the bounded promotion helper is present but not bound to
the canonical evolution workflow. That is a statement about reachability, not
about which module holds the binding. The A06-0002 verifier encoded one
implementation shape as a proxy for it, and the proxy expired.

The A06-0003 verifier re-derives the finding directly:

- the A05 package, not one module, is the authority boundary;
- each executor reference is resolved the way the runtime resolves it,
  including generated gate executors published through the entrypoint table;
- the resolved callable's defining module must be inside the A05 package, so a
  module in the package cannot launder a callable imported from elsewhere;
- the commit path must actually invoke `decide_promotion` and
  `validate_promotion_decision_semantics`, and must refuse without a trusted
  commit port;
- the executable node count must still be 21.

## Adversarial checks performed

A verifier that only passes proves nothing, so it was driven against mutated
workflows:

| Mutation | Result |
|---|---|
| commit node retargeted outside the A05 package | `FAIL` (unbound) |
| commit node aliased to a foreign callable inside the package | `FAIL` (unresolved) |
| one gate node removed | `FAIL` (count 20) |
| unmodified current source | `PASS` |

## Scope

This attempt re-audits `A06-F005` only. `F001`-`F004` and the schema-meta audit
were re-executed from the A06-0002 verifier against current source and all
returned `PASS`; none of them touch the promotion runtime binding.

No source outside `artifacts/work_packages/A06/attempts/0003/` was modified by
this attempt.
