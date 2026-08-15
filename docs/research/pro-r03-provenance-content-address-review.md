# R03 provenance and content-address review

Act as an independent, read-only contract reviewer for a bounded R03 change.
Return material blockers only, or `NO_BLOCKER` with a short rationale.

Authority and current local contract:

- R03 owns `python/epistemic_foundry/reasoning/aporia/**` and must classify
  condition differences while preserving competing explanations; it may not
  adjudicate a winner.
- `build_aporia_record` publishes sorted observation IDs, classified conflicts,
  canonical explanations, kind counts, deterministic status, `aporia_id`, and
  `aporia_hash`. There is no shared AporiaRecord schema outside this R03-owned
  contract.
- A conflict ID is already derived from its sorted observation pair. Aporia ID
  was derived from conflicts, explanations, subject, and timestamp, but omitted
  the examined observation set.

Observed validator gaps:

- Rehashing could remove observation IDs referenced by conflicts, replace
  conflict IDs/endpoints/directions, insert noncanonical explanations, or
  replace `aporia_id` while still passing the public validator.
- Two no-conflict records for the same subject/timestamp but different examined
  observation sets produced the same `aporia_id`.

Bounded repair:

1. Share `_conflict_id(left_id, right_id)` between builder and validator.
2. Validate recorded observation IDs as canonical sorted unique strings.
3. For each conflict, require distinct sorted endpoints resolving to recorded
   observations, exact conflict ID, canonical genuinely conflicting directions,
   canonical differing-condition projection, and the existing type/condition
   consistency that is provable from the published record.
4. Re-run existing `_validate_explanation` on every recorded explanation and
   require equality with its canonical normalized projection before kind-count
   reconciliation.
5. Share `_aporia_id(payload)` between builder and validator and add
   `observation_ids` to its preimage. This intentionally changes newly built IDs
   so the examined set is content-addressed; there is no migration or persisted
   production store in this reference-blueprint package.
6. Keep the prior deterministic `OPEN`/`NO_CONFLICT` status binding and final
   self-hash check.

Regression source covers different observation sets receiving different IDs,
rehashed observation removal, forged conflict ID, forged Aporia ID, and prior
status cases. No shared schema, manifest, workflow, or other package changed.

Review whether each invariant is supported by the published fields and R03
authority, and whether changing the local `aporia_id` preimage creates a
material compatibility or migration blocker in this repository state.
