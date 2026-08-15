# R02 intervention scope-boundary review

Act as an independent, read-only contract reviewer for one bounded Epistemic
Foundry R02 change. Return only material blockers, or `NO_BLOCKER` with one
short rationale. Do not invent a shared contract beyond the supplied authority.

Authority:

- R02 owns `python/epistemic_foundry/reasoning/deduction/**`.
- Its exit criteria are “premises source-bound or assumptions” and “scope
  widening rejected.”
- `schemas/scope-vector.schema.json` requires
  `intervention_or_exposure` to be null or a fixed nine-field object:
  `name`, `category`, `min_value`, `max_value`, `unit`, `duration`,
  `frequency`, `rate`, and `route_or_delivery`.
- `name` is a non-empty string; min/max are number-or-null; rate is
  string/number/null; the remaining attributes are string-or-null.
- Existing R02 scope semantics allow a conclusion if it lies within at least
  one transitive premise scope. Null premise values are unconstrained; a
  conclusion may narrow but may not drop or alter a constrained value.

Observed defect:

`_validate_scope` included `intervention_or_exposure` in the exact top-level
field set but never validated it. `scope_widening` checked all scalar, set, and
map fields except this one. A premise constrained to nitrogen could therefore
produce a conclusion with no intervention or a phosphorus intervention
without `SCOPE_WIDENED`.

Bounded repair:

1. Validate the exact nine-field intervention shape and JSON-schema value
   types at the existing R02 scope normalization boundary.
2. Add `_intervention_within(conclusion, premise)`:
   - constrained categorical/text/rate/name attributes must remain equal;
   - a constrained minimum may only increase;
   - a constrained maximum may only decrease;
   - unconstrained null premise attributes may be narrowed by the conclusion.
3. If at least one premise has an intervention, reject a null conclusion as
   `DROPPED_BOUNDARY`; reject a non-null conclusion not within any constrained
   premise as `UNCOVERED_VALUE`. Existing deterministic finding sorting and
   final `SCOPE_WIDENED` behavior remain unchanged.
4. Regression source covers dropped intervention, changed intervention,
   allowed numeric range narrowing, and the engine-level refusal.

No schema, workflow, manifest, or other package was changed. Review whether
this matches the frozen schema and existing R02 narrowing semantics, and name
any material correctness or compatibility blocker in this exact repair.
