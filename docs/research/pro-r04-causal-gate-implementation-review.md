# R04 causal gate implementation review

Review the implemented R04-local repair against your immediately preceding `AUTHORIZED_LOCAL_REPAIR` answer and repository authority. Return `NO_BLOCKER` or only material correctness, authority, compatibility, or adversarial-input blockers. Ignore style and do not ask to run tests.

Implemented production behavior in `python/epistemic_foundry/reasoning/causal/contracts.py`:

1. Primitive-first recursive JSON detachment now protects `seal_mechanism_graph`, graph validation inside `evaluate_causal_gate`, `mode_verdicts`, all three identifier arrays, scalar call arguments, and `validate_causal_gate`. It rejects cycles, byte-like/non-JSON values, non-finite numbers, non-string or duplicate projected keys; primitive subclasses use base values before Mapping/Sequence classification.
2. Duplicate edge IDs remain rejected.
3. `adjustment_set`, `conditioned_on`, and `unmeasured_confounders` must be JSON arrays of nonblank strings. Scalar strings, mappings, bytes, nested arrays, and non-string members fail closed before assessment. Duplicates normalize only after validation.
4. Adjustment/conditioning/unmeasured identifiers must resolve to graph nodes. Unmeasured IDs must name confounder-role nodes, and one confounder cannot be both adjusted and unmeasured.
5. Until `MECHANISM_GRAPH_LAG_SEMANTICS` is frozen, every causal/inhibitory edge lag is `UNKNOWN` except literal `simultaneous`, which is `SIMULTANEOUS`. No raw lag can yield `ESTABLISHED`; standalone gate validation also rejects a rehashed `ESTABLISHED` state with `TIME_ORDER_UNQUALIFIED`. The raw lag remains in the graph. Thus R04 cannot emit `IDENTIFIED` merely from arbitrary lag text.
6. Each collider/confounding/time-order assessment now carries exact `mechanism_graph_id` and `mechanism_graph_hash`. The gate also publishes `mechanism_graph_hash`.
7. Assessment validators enforce exact nested field sets, graph binding, exact booleans/vocabularies, sorted unique ID arrays, and internal state/open-list/satisfied consistency.
8. Mode verdicts require exact outer fields and closed mode-specific details: R01 causal identification is exactly `NOT_ASSESSED` with canonical synthesis status; R02 status is a canonical `TraceStatus`; R03 selection must be null and standing conflict count an exact non-negative int. No coercion remains.
9. The validator requires exactly one sorted verdict per mode, recomputes the causal ceiling/reasons, re-derives identification from assessment failures/assumptions/ceiling, and rejects mismatches. The existing deterministic gate-ID preimage is factored into one helper and re-derived; it includes assessments, graph hash, status, subject, and creation time. Gate hash remains final.

Regression source now covers scalar/mapping/bytes/nested identifier inputs, unknown/non-confounder IDs, adjusted+unmeasured conflict, arbitrary lag strings including `P1D`/garbage, duplicate top-level Mapping items at sealer/builder/validator boundaries, coerced/negative conflict counts, rehashed mode ceiling, rehashed satisfied assessment, graph-hash binding, and forged established time order. Existing expectations that arbitrary `P1D` proved time order were replaced with fail-closed `NOT_IDENTIFIED` expectations; the causal ceiling remains independently reported.

The validator proves closed shape and internal derivation relative to the bound graph hash; it does not claim a self-hash is external authority or invent the missing positive lag grammar. No schema, manifest, R01/R02/R03 source, or package outside R04 was changed.

Check especially for a path that could still raise `identification_status` or `identification_ceiling`, hide a failed assessment, reinterpret caller data, or masquerade under the old gate identity. Distinguish the intentionally retained positive-lag `SPEC_GAP` from a repairable current implementation defect.
