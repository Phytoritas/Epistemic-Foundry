# Decision

Your new census **changes the implementation priority, but it does not invalidate the pending A01 source-root freeze**.

The correct next step is still a contract-only A01 decision. Amend the pending product-owner request before approval so that the same `MASTER_SPEC.md` amendment freezes two independent facts:

1. `src/epistemic_foundry` is the sole shipped Python source root.
2. A code-backed business callable is **not** a bound workflow executor unless an explicit node-adapter binding connects it to the canonical invocation, output, authorization, effect, and replay contracts.

Do **not** move K03, implement an adapter, modify a workflow, or change the compiler while that decision is pending.

The present state is:

> **`SPEC_GAP`: the shared executor-shell contract and its implementation owner are not yet authoritatively assigned.**

The repository already requires missing or inconsistent shared semantics to stop as `SPEC_GAP`, and A01 is the package with authority over `MASTER_SPEC.md` and the repository constitution.  

---

## 1. Shared contract or per-node work?

It is a **shared-shell plus per-node-binding** architecture.

Neither extreme is correct:

* Reimplementing the complete K01 lifecycle independently in every package would duplicate security, replay, and effect semantics and would inevitably drift.
* A universal reflection-based wrapper that guesses how to call arbitrary business functions would silently decide domain semantics and would make a callable look bound when it is not.

The boundary should be divided as follows:

| Responsibility                                                                   | Authoritative owner after the freeze                              |
| -------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| Normative definition and ownership assignment                                    | **A01 / product owner**                                           |
| Shared scheduler-facing execution shell                                          | **W02**, after explicit A01 delegation                            |
| Compile-time binding validation and fail-closed census                           | **W01**                                                           |
| Per-node input mapping, business invocation, output mapping, and domain failures | The node’s original domain work package                           |
| ActionIntent, Attempt, idempotency, effect reconciliation                        | Existing **E02** authority                                        |
| Capability, lease, fencing, approval, and policy enforcement                     | Existing **E03** authority                                        |
| Semantic business implementation                                                 | The original domain work package; never W01 or W02 by implication |

This assignment is not currently derivable from the live manifest. W01 owns only the workflow compiler surface, while W02 owns the workflow runtime surface but is presently described as checkpoint, pause, resume, and cancellation. E02 and E03 separately own effects and capabilities. No one currently owns the complete composition boundary.  

Therefore:

* **W02 is the narrowest appropriate future owner** of the reusable runtime shell.
* **W01 is not the runtime owner.** It should verify that a binding exists and is internally consistent, then reject unbound nodes.
* **Domain packages own their adapters.** The shell must not decide that a `SourceSnapshot` comes from artifact A, that a proposal mapping requires option B, or that a domain exception means `PARTIAL`.
* **E02 and E03 remain authorities behind injected ports.** W02 must not recreate effect or lease logic.

Assigning W02 this broader runtime meaning is itself part of the A01 decision. Its current title and scope do not provide enough authority to infer the assignment locally.

A separate lower-authority A–Z planning document does describe an “Executor binding closure” stream, but that is evidence that the gap was anticipated, not live authority to reuse the E identifiers or alter current package ownership. 

---

## 2. Minimum reusable boundary

### First, freeze the meaning of `executor_ref`

The least ambiguous rule is:

> For a code-backed workflow node, `executor_ref` identifies the **scheduler-facing node-adapter entrypoint**, not an arbitrary business function.

A raw function such as:

```python
emit(snapshot, candidates) -> tuple[SourceSpan, ...]
```

is a business implementation. It may be excellent and fully tested, but it is not the callable named by a canonical node until a node adapter supplies the missing mapping and execution behavior.

The adapter may internally invoke one or more business functions. Their identities should be retained in a hash-sealed binding record rather than hidden inside the wrapper.

This means many current workflow references are best classified as **candidate business references that have not yet been bound**, even though they are currently written in the `executor_ref` field. Correcting that meaning will later require node-by-node workflow or binding changes. It should not be concealed by declaring the existing raw symbols executable.

### The shared shell

Conceptually, the shell performs:

```text
canonical NodeInvocation
+ compiled NodeContract
+ exact NodeExecutorBinding
+ kernel-owned ports
→ declared business output
+ only the execution sidecars explicitly required by contract
```

Its minimum responsibilities are:

1. Validate the invocation against the exact canonical invocation schema without silently normalizing unknown fields.
2. Resolve the exact workflow version, node ID, compiled NodeContract, and contract hash.
3. Resolve one exact node binding; no node-name heuristics, wildcard matching, or signature guessing.
4. Verify the binding’s workflow, node, schema, adapter, and implementation identities before business code is called.
5. Resolve immutable input artifacts through injected read ports and verify their content hashes, roles, and the invocation’s `input_hash`.
6. Enforce declared read scope, write scope, policy checks, capabilities, approvals, lease, fencing, cancellation, and deadline through the appropriate kernel-owned ports.
7. Perform the generic idempotency and replay protocol through E02-owned ports.
8. Invoke the per-node adapter exactly once on a new attempt.
9. Validate the serialized business result against the node’s exact `output_schema_ref`.
10. Persist declared outputs through injected artifact/state ports, where the node contract requires persistence.
11. Seal and reconcile only the effects declared by the NodeContract.
12. Return typed failures with enough state to distinguish:

    * business code not started;
    * effect may be uncertain;
    * effect confirmed;
    * replayed prior result.
13. On canonical replay, return the prior bound result without a second business invocation.

The compiler currently validates the syntactic form of an entrypoint reference but does not establish these behavioral properties. 

### The per-node adapter

The original domain package remains responsible for:

* mapping artifact roles to domain arguments;
* decoding canonical data into `SourceSnapshot`, `SpanCandidate`, proposal mappings, or other domain objects;
* selecting the exact business function and fixed options;
* enforcing domain invariants that are stronger than JSON Schema;
* converting the domain result into the node’s declared business output;
* declaring domain-specific artifact roles and semantic identifiers;
* mapping domain errors into the already-authorized failure vocabulary;
* constructing domain effect payloads for the shared shell to seal and reconcile.

The adapter must not:

* authorize itself;
* mint capabilities or leases;
* select a different NodeContract;
* bypass idempotency;
* write outside the declared scope;
* turn an unvalidated business return value directly into a success envelope.

### Minimum binding identity

The minimum conceptual binding record is:

```yaml
workflow_id: ...
workflow_version: ...
node_id: ...
node_contract_hash: ...

adapter_ref: package.module:symbol
adapter_revision_or_digest: ...

business_refs:
  - package.module:symbol
business_revision_or_digests:
  - ...

input_schema_ref: ...
input_schema_hash: ...
output_schema_ref: ...
output_schema_hash: ...

binding_hash: ...
```

Do not duplicate capabilities, read scopes, write scopes, expected effects, or required policy checks in this record. Those remain authoritative in the NodeContract. Duplicating them would create two policy sources that could diverge.

A schema or manifest representation for this record must be delegated later. Creating one now would exceed A01’s current write scope.

### K01 is a reference oracle, not a universal template

K01 demonstrates that a real node boundary must behaviorally bind:

* invocation identity;
* input hashes;
* immutable artifacts;
* authority and lease decisions;
* effects and replay;
* the declared output.

Its package contract explicitly requires registry, ledger, lease, compare-and-swap, and receipt effects to reconcile without reimplementing the underlying D/E primitives. 

But the K01 return shape must **not** be generalized to every node.

For example, `compile_query_plan` declares `schemas/query-plan.schema.json` as its node output, while retrieval lanes declare `schemas/result-envelope.schema.json`. The retrieval workflow also explicitly distinguishes the business output from a telemetry-sidecar `ResultEnvelope`. 

Therefore the frozen rule must be:

> `output_schema_ref` is authoritative for the node’s business result. A `ResultEnvelope` is produced only when it is the declared output or when the workflow explicitly defines it as a separate execution sidecar. An envelope never substitutes for the business artifact.

This is why “accepts `NodeInvocation` and returns `ResultEnvelope`” cannot be the universal static signature test.

---

## 3. How to classify the current 29 callables

Your static `0/29` result and the K01 behavioral result should not be collapsed into one number.

A Python signature is only a diagnostic. It cannot prove:

* exact node-ID binding;
* input-hash integrity;
* authorization;
* declared schema output;
* idempotency;
* effect reconciliation;
* no-second-call replay.

Conversely, a factory, callable object, or dependency-injected service may satisfy the runtime contract without having a simple annotation of `NodeInvocation -> ResultEnvelope`.

The truthful current behavioral census is therefore:

| State                                                           |   Count |
| --------------------------------------------------------------- | ------: |
| Module absent                                                   |     224 |
| Module exists but named symbol absent                           |      12 |
| Callable exists, but only business-callable or binding-unproven |      28 |
| Behaviorally demonstrated bound node                            |       1 |
| **Total Python refs**                                           | **265** |

That gives K01 credit for what it actually demonstrates without treating the other 28 callables as missing business implementations.

The following classifications should fall directly out of the frozen contract:

```text
epistemic_foundry.ingest.registry:register_document
  → BOUND
    because installed-runtime, invocation, output, effects, and replay
    behavior are demonstrated

epistemic_foundry.ingest.spans:emit
  → BUSINESS_CALLABLE_ONLY
  + TRANSITION_ONLY_SOURCE
    because the producer exists and is tested, but is neither shipped nor
    node-adapted

epistemic_foundry.retrieval.planning:compile_query_plan
  → BUSINESS_CALLABLE_ONLY
  + TRANSITION_ONLY_SOURCE
    for the same reason

epistemic_foundry.retrieval.lanes:lexical
  → BUSINESS_CALLABLE_ONLY or BINDING_UNPROVEN
    even if it imports from src

epistemic_foundry.validation.reconcile:evidence
  → MISSING_SYMBOL
```

Your correction is therefore accepted: the `python/`-only real-symbol count is four, `validation.reconcile:evidence` belongs to the missing-symbol class, and the missing-symbol total is twelve.

Do not “repair” that last reference with:

```python
evidence = reconcile_evidence
```

unless `reconcile_evidence` has separately been shown to satisfy the node-adapter contract. Aliasing a business function can improve symbol resolution while leaving executability unchanged.

---

## 4. Does this change the tree-migration priority?

Yes, but only at the implementation level.

The source-root freeze remains first because it answers repository authority and makes later ownership non-circular. It should still be approved.

What changes is the claim made about its value:

> Draining `python/` into `src` is necessary for shipment and duplicate elimination, but it is not sufficient for workflow binding.

The two dimensions are orthogonal:

| Source state | Binding state              | Consequence                                   |
| ------------ | -------------------------- | --------------------------------------------- |
| Unshipped    | Bound adapter exists       | Still not runnable from the installed product |
| Shipped      | Raw business callable only | Importable, but not a node executor           |
| Unshipped    | Raw business callable only | Both migration and binding are missing        |
| Shipped      | Behaviorally bound adapter | Executable candidate                          |

Moving all 1.2 MB into `src` without adding node bindings would make more modules importable but could leave the number of executable nodes unchanged.

Accordingly, correct the pending owner request now:

* The source-root resolution remains constitutional and necessary.
* Bulk tree drainage is **not the primary workflow-capability unlock**.
* After contracts are frozen, a complete vertical node binding is more informative than a large path-only migration.
* K03 should not be used to discover the shared contract by implementation. That would combine source migration, adapter design, workflow semantics, and evidence continuation in one package.

This is a reprioritization, not a reversal of the previous root decision.

---

## 5. The single bounded next step

## Amend the pending A01 approval request

**Decision owner:** A01 product owner / architecture authority
**Normative artifact:** `MASTER_SPEC.md`
**Implementation files changed:** none
**Schemas changed:** none
**Workflows changed:** none
**Manifest changed:** none
**Source moved:** none

Add a section such as **“Code-backed node executor binding authority”** containing these exact decisions:

```text
1. Source reachability and node-executor binding are independent maturity
   dimensions.

2. A module or callable resolving successfully does not establish a bound
   workflow node.

3. For code-backed nodes, executor_ref identifies the scheduler-facing
   node-adapter entrypoint. Raw scientific or domain functions are business
   implementations and are retained as separately bound implementation
   identities.

4. One shared workflow-runtime shell owns invocation validation, exact
   NodeContract and binding resolution, immutable input/hash verification,
   scope enforcement, cancellation/deadline enforcement, generic
   idempotency/replay coordination, output-schema validation, effect
   reconciliation, and execution-sidecar construction.

5. W02 owns that shared runtime shell after explicit delegation. W01 owns
   compile-time binding validation and fail-closed rejection, not domain
   invocation semantics.

6. The original domain work package owns each node adapter, business argument
   mapping, business-result serialization, domain invariants, and domain
   failure mapping.

7. E02 remains the ActionIntent, Attempt, EffectReceipt, idempotency, and
   reconciliation authority. E03 remains the capability, lease, fencing,
   approval, and policy authority. The workflow shell consumes those
   authorities through ports and does not reimplement them.

8. output_schema_ref is authoritative for the node business output.
   ResultEnvelope is required only where declared as the output or explicitly
   specified as a separate execution sidecar.

9. Static signature compatibility, import success, symbol aliases, node-ID
   dispatch tables, wildcard wrappers, sys.path modification, and plausible
   dictionaries cannot establish BOUND.

10. BOUND requires clean installed-runtime resolution, an exact hash-sealed
    node binding, successful canonical invocation, exact output-schema
    validation, fail-closed negative cases, declared-effect reconciliation,
    and no-second-business-call replay where replay applies.

11. Until the shared shell owner and binding representation are delegated,
    implementation returns SPEC_GAP rather than inventing a local adapter
    convention.
```

The A01 amendment should delegate the later machine-readable binding representation but should not create it. If the pending request has already been sealed, record this as an append-only A01 successor request rather than editing prior evidence.

---

## Observable proof

The step worked only if all of the following are observed:

1. `git diff --name-only` contains only:

   * `MASTER_SPEC.md`;
   * already-authorized append-only A01 successor evidence, if required.

2. An independent reviewer can derive, without inspecting K01 implementation details:

   ```text
   shared_shell_owner = W02
   compile_time_binding_verifier = W01
   per_node_adapter_owner = original_domain_package
   effect_authority = E02
   capability_authority = E03
   callable_present != BOUND
   output_schema_ref = authoritative business output
   universal_ResultEnvelope = false
   ambiguous_binding = SPEC_GAP
   ```

3. The reviewer classifies K01, K03, O01, and `validation.reconcile:evidence` exactly as shown above.

4. The census remains:

   ```text
   224 module missing
   12 symbol missing
   28 callable present but binding unproven
   1 behaviorally bound
   ```

   No count improvement is expected from a contract-only step.

5. Existing unbound nodes continue to fail closed.

### It only appeared to work if

* the resolved-callable count increases;
* `python/` is added to `PYTHONPATH`;
* files are copied or moved into `src`;
* the compiler accepts a callable because it takes a mapping, `*args`, or `**kwargs`;
* `resolve_node_executor(node_id)` directly dispatches to raw business functions;
* one generic wrapper fabricates valid-looking envelopes for many nodes;
* every business result is forced into `ResultEnvelope`;
* `evidence` is aliased to `reconcile_evidence` to turn the census green;
* an old sealed A01 report is rewritten;
* any schema, workflow, manifest, or runtime implementation changes in this step.

Those outcomes would improve appearance or importability without establishing the missing executor boundary.
