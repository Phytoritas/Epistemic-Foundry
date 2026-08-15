# Epistemic Foundry O01 scope-binding authority decision

You are an advisory reviewer. The local repository remains the authority, and your answer must not invent a missing shared contract.

## Objective

Determine whether the attached higher-authority Epistemic Foundry sources already define a unique, implementable relationship between:

- `QueryPlan.scope_partitions`, and
- each executed `SearchLaneReceipt.scope_filter`.

The current O01 implementation now binds every receipt to the exact QueryPlan identity/hash and the exact canonical query text for its lane. It still cannot determine whether a receipt scope must be:

1. exactly one declared partition;
2. a schema-valid subset/refinement of one partition;
3. a union of declared partitions; or
4. another explicitly derivable projection.

That missing relationship blocks truthful `executed_scope_ids`, unsearched-scope accounting, absence claims, and downstream O04/P/R work.

## Authority order

Use only the attached sources, in repository authority order:

1. `MASTER_SPEC.md`
2. `manifests/development_manifest.yaml`
3. `workflows/evidence_retrieval.workflow.yaml`
4. applicable schemas
5. current O01/O04 source

Historical reports, tests, comments, and plausible design preferences cannot create authority that these sources do not contain.

## Required analysis

Trace the exact data path from QueryPlan construction through lane execution, receipt sealing/reconciliation, completeness, and absence claims. Check:

- partition identity and completeness;
- lane-to-partition cardinality;
- temporal and external-novelty extension behavior;
- subset, union, overlap, and refinement semantics;
- replay/idempotency implications;
- whether `ScopeVector` supplies a canonical equality or containment relation;
- whether any proposed rule would silently narrow or broaden searched scope.

## Required output

Return exactly one top-level verdict:

- `AUTHORIZED`: the higher authority already implies one unique rule; or
- `SPEC_GAP`: more than one materially different rule remains compatible with the authority.

If `AUTHORIZED`, provide:

1. the exact deterministic rule in implementation-ready terms;
2. direct file/section locators supporting every part of the rule;
3. the smallest package/contract changes required, in dependency order;
4. compatibility and replay consequences;
5. one adversarial counterexample each for off-plan scope, partial scope, overlapping scope, and false absence.

If `SPEC_GAP`, provide:

1. the smallest unresolved human decision;
2. the mutually exclusive viable choices still allowed by authority;
3. the downstream behavior each choice changes;
4. the canonical owner paths that must record the decision before O01 code can proceed.

Do not produce a compromise design, convenience wrapper, evidence packet, approval record, or PASS claim. Distinguish direct authority from your own inference.
