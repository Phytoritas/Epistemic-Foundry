# ALTERNATE_LOCAL_DEFECT

## Repository authorization

`model_update` remains a **shared specification gap**. The canonical schema establishes only that the token is permitted in `trigger_type`; it does not assign:

* invalidating, stale-only, or future-only classification;
* default `required_actions`;
* default `priority`;
* affected artifact classes or Passport state;
* whether it means an evaluator update, provider/model-version change, prompt-model change, or another event class.

A schema enum is not authorization to invent those semantics. 

EF4-I38 governs corrections, retractions, parser fixes, policy/ontology changes, and new evidence. EF4-I56 separately makes **evaluator** updates future-only and forbids retroactive rewriting of completed judgments. Neither provision equates generic `model_update` with an evaluator update. Historical hashes and revisions are generally immutable, but the higher authority does not decide whether a `model_update` should create a new stale Passport revision or affect only future runs. 

Therefore W03 is **not authorized** to add `model_update` to `TRIGGER_TYPES`, `_DEFAULT_ACTIONS`, `_DEFAULT_PRIORITY`, `INVALIDATING_TRIGGERS`, or `VOIDING_TRIGGERS`. The missing shared decision belongs first in `MASTER_SPEC.md` under the A01 constitutional/specification owner; if the intended meaning is evaluator evolution, A05/A06 and the W05/S06 future-run boundary must explicitly classify it. C01 may then project that decision into canonical contracts, but cannot originate it. W03’s manifest explicitly requires `SPEC_GAP` on ambiguous shared semantics and limits its writes to `python/epistemic_foundry/reassessment/**`. 

## One independently repairable production defect

**Defect:** `apply_passport_states()` applies a merely shape-valid reassessment plan without verifying that it is the deterministic plan for its provenance graph.

**Causal path:**

1. `_validate_plan_shape()` verifies fields, enums, Passport-state completeness, timestamp, and the plan’s self-hash.
2. A caller can therefore construct and self-hash an internally well-formed but semantically forged plan—for example, a `new_document` plan that declares a reached Passport `INVALIDATED`.
3. `apply_passport_states()` currently calls only `_validate_plan_shape(plan).payload`, then increments the Passport revision and applies that forged state.
4. The adjacent `validate_plan()` already supplies the required authority check: it recomputes the plan with `assess_update()` against the bound graph and requires byte-for-byte identity. That check is bypassed at the mutation boundary.  

This violates the authorized graph-bound, transitive, replayable reassessment model. The canonical workflow requires impact to be derived from graph dependencies, preserves prior revisions, and applies staleness through append-only superseding state rather than caller-selected assertions.  

## Smallest production repair

**W03-owned path:** `python/epistemic_foundry/reassessment/contracts.py`

```diff
 def apply_passport_states(
     passports: Sequence[Mapping[str, object]],
     plan: Mapping[str, Any],
+    *,
+    graph: Sequence[Mapping[str, object]],
 ) -> list[dict[str, Any]]:
-    sealed = _validate_plan_shape(plan).payload
+    sealed = validate_plan(plan, graph=graph).payload
```

No other source hunk is authorized or necessary. This reuses the existing deterministic validator, retains historical Passport revisions, and leaves the dirty `span`/`decision` artifact classes and stricter seed validation untouched. It requires no manifest, schema, workflow, report, evidence-packet, or test edit. The path is consistent with the repository’s declared Python component root.  
