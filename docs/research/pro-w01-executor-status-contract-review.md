# W01 executor-status and unknown-executor contract review

Continue as an advisory reviewer for Epistemic Foundry v4. Determine whether
the current W01 compiler change can be completed locally or exposes a shared
contract gap. Return exactly one of `AUTHORIZED_LOCAL_REPAIR`, `SPEC_GAP`, or
`NO_BLOCKER`, followed by only material findings and the smallest truthful
next change. Do not ask to run tests.

## Authority

- W01 is “Workflow compiler and NodeContract validator”, depends on current
  D04/E04/F04/N04 PASS packages, and solely owns
  `packages/foundry-kernel/src/workflows/compiler/**`.
- Exit criteria require DAG/resource-edge validation and unknown executors
  blocked.
- Canonical `schemas/node-contract.schema.json` defines optional
  `executor_status` with enum `executor_bound | executor_unbound`. Its
  description says bound asserts a live reference checked by the
  executor-resolution gate; unbound declares specified-but-unbuilt; absent is
  unverified; a workflow with `missing_node_policy: FAIL` is unsatisfiable
  while a needed node is unbound.

## Current source delta

The dirty W01 compiler now derives all schema property names separately from
the required field list, validates optional `executor_status` against the
schema enum, and accepts bound, unbound, or absent values. Before passing nodes
to the sealed scheduler it projects only `vocabulary.required_fields`, because
the scheduler contract does not own the optional field.

Consequently these three workflows currently compile to the same
`scheduler_plan_sha256` and final `compiled_sha256`, and compiled output retains
no status/census:

```text
executor_status absent
executor_status executor_bound
executor_status executor_unbound
```

Current regression source explicitly expects all three to compile.

The compiler's “unknown executor” checks otherwise validate only the closed
`executor_type` enum and executor-ref syntax. It receives no executor registry,
callable resolver, release identity, or resolution receipt. Repository tests
outside W01 currently report a zero-node `executor_status` declaration census,
and canonical workflows contain known syntactically valid refs whose symbols
do not exist.

A second current delta changes unordered overlapping writers so a shared
`quota:*` resource no longer masquerades as serialization; only a shared
`exclusive:*` resource or dependency ancestry satisfies the compiler. This is
independent of executor resolution.

## Decision requested

1. Is silently dropping `executor_status` from the compiled identity a W01-local
   correctness defect even if actual callable resolution is owned elsewhere?
2. May W01 locally include a deterministic status census/projection in the
   compiled artifact and fail closed on `executor_unbound` under the frozen
   `missing_node_policy: FAIL`, or would that invent execution/release
   semantics?
3. Does truthful enforcement of `executor_bound` require a missing shared
   executor-registry/resolver/receipt binding outside W01, making full
   “unknown executor blocked” completion a `SPEC_GAP`?
4. Is the `exclusive:*` resource repair independently authorized by W01's
   resource-edge exit criterion?

Do not invent a registry, rewrite canonical workflows, or claim a syntactically
valid executor ref is live.
