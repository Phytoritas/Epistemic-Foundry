# R05 crossover-report re-derivation review

Act as an independent, read-only contract reviewer for one bounded Epistemic
Foundry R05 change. Return only material blockers, or `NO_BLOCKER` with one
short rationale.

Authority and existing interfaces:

- R05 owns `src/epistemic_foundry/reasoning/v4_r05/**` and may compose existing
  C05/I05/Evolution Chamber contracts; it must not let evolution self-authorize
  a crossover.
- `schemas/crossover-compatibility-report.schema.json` fixes the exact report
  shape: two-or-more string candidate IDs, four typed compatibility axes,
  conflicts, required repairs, derived decision, report ID, and SHA-256 hash.
- The existing public `build_crossover_report` deterministically derives
  `decision` from the four axes, requires a named repair for repairable axes,
  computes `report_hash`, and validates the canonical schema.
- The existing `crossover_permitted` only returns whether
  `report["decision"] == "ALLOW"`; it is not itself a report validator.

Observed defect:

`apply_typed_crossover` previously converted the supplied report to a dict,
checked that its candidate IDs covered both parents, then called only
`crossover_permitted`. A caller could supply a partial or rehashed forged
`decision="ALLOW"` without a canonical four-axis assessment and splice parents
whose scope, measurement, causal assumptions, or units were incompatible.

Bounded repair in R05:

1. `_validated_compatibility_report` snapshots the input mapping.
2. It calls the existing canonical schema validator for
   `crossover-compatibility-report`.
3. It calls existing `build_crossover_report` with every supplied canonical
   field and the exact report ID.
4. It requires the rebuilt report to equal the supplied report exactly,
   thereby binding axis-derived decision and self-hash. Builder semantic
   refusal is mapped to local `CROSSOVER_REPORT_MISMATCH`.
5. `apply_typed_crossover` consumes only this rebuilt report, validates actual
   string candidate IDs, retains its exact parent binding, then keeps the
   existing unconditional-ALLOW and mechanism-agreement checks.

No shared schema, builder, manifest, workflow, or artifact was changed.
Review whether this is the correct R05-local composition of the existing
canonical report contract, and identify any material correctness,
compatibility, or authority-boundary blocker.
