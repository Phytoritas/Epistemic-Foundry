# R01 completeness/status blocker-fix follow-up

Review only the delta addressing your prior blocker. Return material blockers,
or `NO_BLOCKER` with a short rationale.

Applied correction:

- EvidencePack input `unsearched_scopes` still must be a non-string/byte
  sequence, but every item need only be a string, exactly as the canonical
  schema states. Empty strings and duplicates are accepted at this input
  boundary.
- `synthesize` publishes `sorted(set(unsearched_scopes))`; any nonempty source
  sequence still contributes `unsearched_scopes_present` degradation.
- `validate_synthesis` accepts string items through the same shape reader, then
  requires the recorded synthesis projection itself to equal
  `sorted(set(recorded_items))`.
- Regression source includes duplicate and empty strings and expects the
  sorted-unique output projection.

One independent compatibility refinement was also applied: direction-level
adjusted weights and the aggregate are each sealed after 10-decimal rounding,
so the validator binds their totals using `math.isclose(rel_tol=0,
abs_tol=1e-9)` rather than exact equality. Raw finding counts remain exact.
With seven canonical directions, this tolerance covers only accumulated final
decimal-place rounding and does not permit a material count/weight mismatch.

All other completeness, stale, degradation, independence, and status
re-derivation behavior from the prior review is unchanged. Is the prior blocker
closed, and does either delta introduce a material new blocker?
