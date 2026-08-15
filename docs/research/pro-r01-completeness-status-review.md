# R01 completeness and status projection review

Act as an independent, read-only contract reviewer for a bounded R01 repair.
Return only material blockers, or `NO_BLOCKER` with a short rationale.

Authority:

- R01 owns `python/epistemic_foundry/reasoning/induction/**` and must apply
  independence adjustment while retaining nulls, moderators, incomplete lanes,
  stale state, and unsearched scope.
- Canonical `schemas/evidence-pack.schema.json` requires exactly six boolean
  completeness fields, boolean `stale`, and array `unsearched_scopes`.
- R01 statuses are `COMPLETE`, `PARTIAL`, and `INSUFFICIENT`; incomplete/stale/
  unsearched/undetermined/no-findings conditions must not become `COMPLETE`.

Observed defects:

1. `synthesize` defaulted missing completeness to `{}`, iterated only present
   keys, coerced values with `bool()`, coerced `stale` with `bool()`, and could
   iterate a scalar unsearched-scope string. Empty/partial status inputs could
   therefore omit degradation and claim a stronger status.
2. Public `validate_synthesis` checked only the status vocabulary and self-hash.
   Rehashing could change `status`, completeness, degradation reasons, or raw
   finding count without preserving their semantic relation.

Bounded repair:

- `_pack_status_inputs` validates the exact six completeness fields and real
  booleans, real boolean stale, and a non-string/byte array of unique string
  unsearched scopes. The builder reads these once and reuses the normalized
  values for both degradation and output; no truthiness coercion remains.
- `_degradation_reasons` is a pure projection of completeness, stale,
  unsearched scopes, finding count, and heterogeneity classification.
- `validate_synthesis` applies the same status-input validation, validates the
  exact independence projection, requires direction-summary raw and adjusted
  totals to match it, recomputes degradation reasons, and derives the only
  permitted status (`INSUFFICIENT` for zero findings, otherwise `PARTIAL` when
  degradation exists, else `COMPLETE`).
- Recorded degradation reasons and unsearched scopes must be canonical sorted
  unique arrays.
- Regression source covers empty/partial/nonboolean inputs, scalar status
  inputs, rehashed COMPLETE laundering, empty completeness, and forged raw
  finding count.

No shared schema, manifest, workflow, upstream EvidencePack builder, or other
package changed. Review whether the repaired projection follows the supplied
authority and identify any material correctness, compatibility, or
overconstraint blocker.
