# R04 causal gate bounded gap review

Review the current R04 implementation against repository authority and identify the smallest remaining package-local repair, if any. Return exactly one of `NO_BLOCKER`, `AUTHORIZED_LOCAL_REPAIR`, or `SPEC_GAP`, followed only by material findings. Ignore style and do not ask to run tests.

Authority:

- `MASTER_SPEC.md`: R04 is “R-phase causal identification and ArgumentGraph gate”.
- `manifests/development_manifest.yaml`: R04 depends on R02 and R03; sole write scope is `python/epistemic_foundry/reasoning/causal/**`; exit criteria require collider/confounder/time-order assessment and separation of inference modes.
- `schemas/mechanism-graph.schema.json` gives `lag` only `type:string,minLength:1`; it does not define a duration grammar.

Current implementation:

- Validates exact MechanismGraph/node/edge field sets, node identities/roles, edge endpoints/relation/sign/nonblank lag, graph hash, and nonempty nodes/edges.
- The latest local change rejects duplicate edge IDs before assessments, preventing a later edge from hiding an earlier unknown time-order result.
- Confounding is derived from declared confounder-role nodes plus `adjustment_set` and `unmeasured_confounders`.
- Collider assessment derives converging causal/inhibitory parents and rejects conditioning on a collider.
- Time order treats `unknown`, `simultaneous`, `none`, and `not_reported` as non-establishing; every other nonblank lag currently counts as established.
- Exactly one separate INDuctive, DEDUCTIVE, and ABDUCTIVE mode verdict is required. Modes can lower but never raise the causal ceiling.
- The gate derives identification, rejects a stronger declared status, self-hashes the result, and validates top-level gate consistency.

Please decide, against the frozen sources rather than preferred design:

1. Is duplicate-edge rejection sufficient for the current bounded defect, or do scalar-string/bytes/mapping containers in `adjustment_set`, `conditioned_on`, or `unmeasured_confounders`, non-string members, and unknown unmeasured IDs create a package-local wrong-accept path?
2. May R04 truthfully treat every non-placeholder arbitrary lag string as established temporal order, or does the schema’s missing lag grammar make stricter parsing a `SPEC_GAP` rather than a local invention?
3. Are the current graph/gate one-pass mapping reads, caller-owned nested aliases, rehashable `gate_id`, shallow mode/assessment validation, or primitive subclass coercions material to the R04 exit criteria?
4. If a local repair is authorized, give the smallest exact production behavior and error semantics that close it without changing schemas, manifests, R02/R03, or shared contracts. Preserve the already-correct duplicate-edge change.

Do not call a stronger future runtime or scientific-identification design necessary unless a concrete current input can cross the gate incorrectly. Distinguish self-hash integrity from authority, but keep the answer bounded to R04.
