# Epistemic Foundry v4 — the executor adapter boundary

Follow-up in the same conversation. Your last answer resolved the two-tree
split: `src` survives, `python/` is transition-only, and the first step is an
A01 contract freeze in `MASTER_SPEC.md` with no code moved. I wrote that up as
an approval request for the product owner and it is waiting on them.

While it waits, I went back to a number in my own census that I had reported
but not investigated: **224 of 265 Python executor refs resolve in neither
tree**. I assumed those were simply unimplemented. That assumption was wrong in
a way that changes what "unimplemented" means here.

## What I found

First, my earlier census was module-level only. Re-running it with AST symbol
resolution:

| | src only | both | python only | neither |
|---|---:|---:|---:|---:|
| module exists | 24 | 12 | 5 | 224 |
| symbol exists | 24 | 1 | 4 | 236 |

So the honest figure is 236 refs with no symbol anywhere, and only 29 refs that
resolve to a real callable.

Then I checked whether those 29 actually satisfy their declared node contract.
Every workflow node declares `input_schema_ref: schemas/node-invocation.schema.json`
and an `output_schema_ref`. I compared each resolvable callable's real signature
against that declaration.

**0 of 29 match.**

Representative examples:

```text
epistemic_foundry.governance.evolution_authority.nodes:gate_g08_adaptive_statistics
  node declares: node-invocation.schema.json -> gate-decision.schema.json
  actual:        (_payload: Mapping[str, Any]) -> dict[str, Any]

epistemic_foundry.ingest.spans:emit
  node declares: node-invocation.schema.json -> result-envelope.schema.json
  actual:        (snapshot: SourceSnapshot, candidates: Sequence[SpanCandidate])
                 -> tuple[SourceSpan, ...]

epistemic_foundry.retrieval.planning:compile_query_plan
  node declares: node-invocation.schema.json -> result-envelope.schema.json
  actual:        (proposal: Mapping[str, object], *, selected_optional_lanes=...,
                 ...) -> SealedArtifact
```

Repository-wide, exactly one production module both accepts a validated
`NodeInvocation` and returns a `ResultEnvelope`:
`src/epistemic_foundry/ingest/registry/service.py`, K01's `register_document`.
It validates the invocation against the canonical schema, checks
`node_id`, binds `input_hash` to the sealed request hash, resolves input
artifacts through injected ports, and returns a receipt-bound envelope. There is
also an existing `resolve_node_executor(node_id)` in
`governance/evolution_authority/nodes.py`, but it only maps a node ID to a
business function — it does not parse invocations or build envelopes.

The workflow compiler confirms the gap from the other side: it validates
`executor_ref` string shape only. It never imports the module, checks the
callable exists, or checks its signature.

## Why this reframes the problem

I had been treating "236 unimplemented refs" as 236 missing business
implementations. But many of those business functions exist — they are just not
shaped like node executors. K03's `emit` is a real, tested span producer.
O01's `compile_query_plan` is a real, tested plan compiler. Neither is bound to
its node, and moving files between trees would not bind them.

So the missing thing is not (only) implementations. It is the **executor
adapter boundary**: the layer that turns a canonical `NodeInvocation` into a
call on a business function and turns the result into a `ResultEnvelope` with
its receipts. K01 built one, by hand, for exactly one node.

That also means my previous framing of the tree migration was incomplete. Even
after `python/` is fully drained into `src`, the workflow layer stays unbound,
because path is not the binding problem.

## The question

**Given this, what is the correct next bounded step, and does it change the
priority of the tree migration?**

Specifically:

1. Is the executor adapter boundary a real missing shared contract that should
   be specified once and reused, or is it deliberately per-node work that each
   package owns (as K01 did)? If it should be shared, who owns it — is there an
   existing package whose scope covers it, or is that itself a `SPEC_GAP`?

2. If a shared adapter contract is right, what is its minimum shape? K01's
   version couples invocation validation, artifact resolution through injected
   ports, authorization/lease checks, idempotency lookup, effect emission, and
   envelope construction. Which of those belong in a reusable boundary and which
   must stay per-node? I want the boundary to be genuinely reusable, not a
   framework that quietly decides domain semantics.

3. Does this change the order relative to the tree migration? My reading is that
   the A01 contract freeze is still correct and still first, because it costs
   nothing and unblocks ownership. But if the adapter boundary is the real
   blocker, then draining 1.2 MB between trees may be lower value than I told
   the owner, and I would rather correct that now than after they approve.

4. What is the single bounded step? If it is "bind one more node end to end as a
   second reference implementation", name which node and why that one. If it is
   "specify the boundary first", name the owner and the artifact.

Constraints unchanged: no embedding models, no network dependencies, no external
services, local determinism is hard. Name one step, not a roadmap. State the
observable outcome that proves it worked and the one that proves it only
appeared to work. If it requires a shared-contract change outside one write
scope, say so — that is a `SPEC_GAP` I stop on rather than improvise.

One correction to my earlier message, for the record: I told you five refs were
`python`-only. Four of those have real symbols; the fifth
(`validation.reconcile:evidence`) names a symbol that exists in neither tree.
And the missing-symbol count I gave you as 8 is actually 12.
