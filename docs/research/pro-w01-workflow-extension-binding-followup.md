# W01 workflow extension binding follow-up

Review one additional current-source fact after the executor-status decision.
Return `AUTHORIZED_LOCAL_REPAIR`, `SPEC_GAP`, or `NO_BLOCKER` with only the
smallest truthful action. Do not ask to run tests.

The W01 compiler checks that a workflow contains its 12 common required
top-level keys but neither rejects nor binds any additional top-level field.
Its `compiled_sha256` covers only this projection:

```text
kind
node_count
resource_edges
scheduler_plan_sha256
topological_order
version
workflow_id
```

Therefore changing or deleting an extra top-level contract does not change the
compiled identity. This is not only a hypothetical unknown field. Canonical
`workflows/evidence_retrieval.workflow.yaml` currently contains
`retrieval_candidate_contract`, which binds business/output schemas, provider
request fields, snapshot mismatch behavior, silent fallback, non-vector
origins, and the vector-only ceiling. No other canonical workflow top-level
extension is currently present.

W01 owns only `packages/foundry-kernel/src/workflows/compiler/**`; there is no
canonical workflow-document JSON Schema or extension registry in its inputs.

Decide:

1. Is silently compiling the evidence-retrieval workflow while dropping this
   contract from `compiled_sha256` a material W01 integrity defect?
2. Can W01 safely bind the recursively canonicalized extension as an opaque
   field without claiming to validate its semantics, or would that make
   unrecognized caller fields part of canonical execution identity?
3. Must a shared authority first define the exact allowed workflow extension
   fields/schema and their scheduler/runtime ownership?

Do not delete the canonical retrieval contract, silently allow arbitrary
extensions, or invent its runtime semantics.
