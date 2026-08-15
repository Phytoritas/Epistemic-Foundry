# SPEC_GAP

The higher authority requires searched scope, unsearched scope, and absence claims to be explicit, but it does **not** define a unique relation

[
B(\texttt{QueryPlan.scope_partitions},\ \texttt{lane},\ \texttt{SearchLaneReceipt.scope_filter})
]

that determines when a receipt has executed a planned partition. More than one materially different rule remains compatible with the attached sources. Under the governing authority rule, missing shared semantics must therefore remain `SPEC_GAP`. 

## Direct authority trace

### 1. QueryPlan construction

The workflow compiles one immutable, class-bound QueryPlan. Its acceptance checks bind request/classification revisions, the E0–E5 lane floor, canonical lane order, and `plan_hash`; they do not specify partition identity, disjointness, exhaustiveness, or a receipt-binding relation. 

The QueryPlan schema defines `scope_partitions` only as:

```text
array<ScopeVector>
```

It provides no `minItems`, `uniqueItems`, partition identifier, partition hash, parent relation, or coverage operator. Thus empty, duplicate, overlapping, and merely adjacent ScopeVectors are not distinguished by this field’s contract. 

### 2. ScopeVector semantics

`ScopeVector` is a closed record of boundary-condition fields. It defines valid shapes for population, setting, geography, temporal scale, inclusion/exclusion criteria, conditions, and domain extensions, but it defines no:

```text
scope_id
scope_hash
parent_scope_id
relation_to_parent
subset operator
union operator
overlap operator
normalization version
```

Its string-valued temporal and geographic fields also carry no range algebra, while list-valued criteria and condition values have no declared set-order or duplicate semantics. The schema therefore supports structural validation, not canonical equality, containment, intersection, or union.  

### 3. Lane execution

The workflow declares one execution node for each selected lane and sends `scope_filter` as part of the provider-request binding. It does not declare fan-out over `scope_partitions`, one receipt per partition, one aggregate receipt per lane, or a partition-to-filter derivation function. 

This is especially material for the two extension-like lanes:

* the temporal lane seals “a versioned date and correction filter”;
* the external-novelty lane seals “external scope and stop rule.”

Neither clause says whether that added filter must equal a declared partition, refine one, union several, or extend beyond all of them.  

### 4. SearchLaneReceipt sealing

Each receipt binds one `query_plan_id`, one `plan_hash`, one lane, and one `scope_filter`. For an execution receipt, `scope_filter` must merely be a schema-valid ScopeVector; for an `UNSEARCHED` sentinel it must be `null`. There is no field recording which plan partition or partitions the filter represents, nor the relation used to derive it.  

Consequently, binding the exact plan hash and exact query text proves:

> this search says it belongs to this plan and query,

but not:

> this search executed exactly this planned scope.

A schema-valid off-plan, narrowed, broadened, overlapping, or aggregated ScopeVector can still satisfy the two individual schemas.

### 5. Receipt reconciliation

The workflow requires all eleven lanes to be reconciled. Unselected lanes have exactly one sentinel, while selected lanes have “execution receipts”; no partition-level receipt cardinality is fixed. The declared count of eleven is a **lane reconciliation count**, not a lane-by-partition execution count.  

Therefore none of the following can be derived canonically:

```text
executed_scope_ids
unsearched_scope_ids
fully covered partition
partially covered partition
overlap counted once or repeatedly
one receipt satisfying multiple partitions
multiple refinements jointly satisfying one partition
```

### 6. Completeness and absence claims

The certificate node is supposed to report executed and unsearched regions, limit claim ceilings to executed scope, and reproduce a stable certificate hash on replay. 

O04 then trusts the recomputed certificate’s `executed_scope_ids` and `unsearched_scope_ids`:

* a scope-bounded claim is allowed when the supplied `scope_id` occurs in `executed_scope_ids`;
* a full-scope claim is forbidden only when `unsearched_scope_ids` remains nonempty. 

That makes the missing O01 relation causally decisive:

```text
undefined plan→receipt scope relation
→ undefined executed_scope_ids
→ undefined unsearched_scope_ids
→ unstable PARTIAL/PASS classification
→ potentially false scope-bounded or full-scope absence claim
→ unsound O04/P/R downstream use
```

O04 cannot repair this by checking membership more strictly, because it does not own the meaning by which those identifiers entered the certificate.

## Smallest unresolved human decision

Freeze one **O01 scope-binding model** answering this single normative question:

> For every selected lane and execution receipt, what exact deterministic relation must hold between `scope_filter` and the QueryPlan’s declared `scope_partitions`, and how does that relation determine stable executed and unsearched scope identities?

That decision necessarily includes four inseparable parameters:

1. the canonical identity of each declared partition;
2. the permitted relation between a receipt filter and its source partition or partitions;
3. receipt cardinality per lane and per scope;
4. the coverage-closure rule used to derive `executed_scope_ids`, `unsearched_scope_ids`, `PARTIAL`, and full-scope eligibility.

Without all four, the selected relation cannot be implemented or replayed.

## Mutually exclusive choices still allowed by current authority

| Choice                               | What one receipt means                                                                                                   | Effect on completeness and absence claims                                                                                                                                                          |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Exact-one partition**              | `scope_filter` must canonically equal exactly one declared partition.                                                    | A partition becomes executed only through an exact match. A lane is complete only when every required partition has a qualifying receipt. Refinements, unions, and extensions are off-plan.        |
| **Refinement of one partition**      | `scope_filter` must be canonically contained within one identified parent partition.                                     | The refinement itself may support a scope-bounded claim. The parent remains partly unsearched unless a declared closure rule proves that all refinements cover it.                                 |
| **Union of declared partitions**     | One receipt identifies a nonempty partition set and its filter equals their canonical union.                             | One execution may close several partitions. Overlap must be deduplicated, and false broadening must be rejected. Empty results could support an absence claim over the union only under this rule. |
| **Explicit lane-derived projection** | `scope_filter` is produced by a versioned lane-specific derivation from named source partitions and other sealed inputs. | Temporal or external-novelty scope may narrow or extend the base plan. Base-partition completeness and derived-extension completeness must be accounted for separately.                            |

All four are consistent with the present statement that the filter is sealed and claims are bounded to reconciled executed scope. None is selected by the current authority.

## Replay and idempotency consequence

The existing hashes protect record bytes, not unstated interpretation. Two software versions could receive byte-identical QueryPlan and SearchLaneReceipt records yet map the same `scope_filter` to different `executed_scope_ids` under different implicit rules. They would then emit different completeness certificates despite the workflow requiring certificate-hash stability under replay. 

A relation version or equivalent canonical binding must therefore participate in the hashed authority surface. Merely adding another local comparison inside O01 would make code version, rather than the canonical contract, the hidden source of scope truth.

## Canonical owner paths required before O01 proceeds

The decision must be recorded in dependency order:

1. **Higher authority and ownership**

   * `MASTER_SPEC.md`: freeze the selected relation at product-contract level.
   * `manifests/development_manifest.yaml`: assign exact write authority for the affected canonical schemas.

2. **Canonical schemas**

   * `schemas/query-plan.schema.json`: partition identity and plan-side partition constraints.
   * `schemas/search-lane-receipt.schema.json`: source-partition binding and the selected relation.
   * `schemas/scope-vector.schema.json`: only if the selected rule requires canonical containment, union, normalization, or refinement semantics intrinsic to ScopeVector.

3. **Execution workflow**

   * `workflows/evidence_retrieval.workflow.yaml`: receipt cardinality, partition fan-out or aggregation, coverage closure, and temporal/external-novelty behavior.

4. **Runtime implementation**

   * `python/epistemic_foundry/retrieval/planning/**`: implement the frozen relation and derive stable executed/unsearched scope identities.

The current manifest gives O01 authority only over the planning runtime and gives O02 authority over `workflows/evidence_retrieval.workflow.yaml`.  The current canonical-schema authority entry does not include `query-plan.schema.json`, `search-lane-receipt.schema.json`, or `scope-vector.schema.json` in its exact enumerated write scope, so that scope cannot be silently presumed; it requires an explicit manifest-level owner correction. 

O04 must remain a downstream consumer. Its existing path may verify the finally resolved certificate, but it must not choose or infer the missing plan-to-receipt scope algebra.
