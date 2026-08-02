# R06-0001 independent contract review

- Author: a bounded implementation agent dispatched in parallel under
  the product owner's explicit aggressive-parallel-agent authorization.
  Reviewer: this sealing session, which did not author the subject code
  and reviewed it independently against the authority chain. The author
  and the reviewer are distinct actors, so actor-independence HOLDS;
  external actor-independent (provider-independent) certification does
  NOT hold. Verdict: PASS, blocking_finding_count=0.
- Verification basis: static reading of
  src/epistemic_foundry/reasoning/v4_r06/gate.py and the modules it
  composes (reasoning.v4_r05.operators, evolution_chamber.crossover,
  intake.v4_i05, contracts, domain.hashing) and the canonical
  mechanism-graph / scope-vector / measurement-compatibility-report /
  crossover-compatibility-report schemas, plus inspection-only
  execution: the R06 targeted suite (52 tests: 8 schema-and-type, 11
  unit-and-contract, 25 negative-and-adversarial, 8
  provenance-and-receipt) and check_packaging.py pass. No FORGE state
  was mutated by the review.
- Per-exit-criterion: (1) all governing schemas, authority boundaries
  and failure states implemented exactly - PASS; the identification
  ladder, comparability/construct vocabularies, four crossover axes and
  allow decision are read from the canonical schemas via _vocab() and
  each artifact is validated and re-hashed, never restated. (2) happy /
  negative / crash-resume(=replay determinism) / adversarial coverage -
  PASS; all twenty-four finding codes have a driving negative and the
  module self-guards that the documented set matches. (3) no candidate,
  model, prompt, backend or hook acquires evaluator, holdout or promotion
  authority - PASS. (4) all effects resolve to immutable, re-derivable
  receipts - PASS.
- Evolution-integrity: PASS. This is an integration gate that composes
  the sealed axis owners rather than re-deriving them: causal
  identification is R04's pinned mechanism-graph verdict, measurement
  comparability is a self-hash-verified report bound to both parents,
  scope is compared field by field over the two ScopeVectors, and the
  Chamber's CrossoverCompatibilityReport is re-derived and cross-checked
  rather than trusted. The report-axis-mismatch check runs FIRST in
  _decide, so a report that overclaims a compatible axis is refused
  (REPORT_AXIS_MISMATCH) before the axis is judged - this is the
  anti-leakage boundary the gate exists to hold. A cross-kind splice
  (PARENT_KIND_MISMATCH) and every incompatible/unassessed causal,
  measurement, scope and unit axis are refused. The four axes stay
  SEPARATE dimensions and are never collapsed into one score; nothing
  scores, selects, promotes or evaluates. Promotion authority is
  contained: test_the_gate_decision_never_consults_a_promotion_field
  flips the measurement report's promotion_ceiling and the decision is
  unchanged, and an allow additionally requires the Chamber's own
  unconditional ALLOW (CROSSOVER_NOT_PERMITTED otherwise). EF4-I22 is
  honored: _vocab() reads every enum token from the canonical schema and
  fails closed on a reshape.
- Findings (all non-blocking): F1 - EF4-I22 is honored positionally
  (_vocab() derives tokens from schema order and guards each length), so
  correctness depends on the schema-and-type suite asserting each token
  against the canonical schema text; that suite exists and passes (8
  tests), so the invariant is guarded rather than assumed; recorded as a
  design note. F2 - the unassessed sentinels 'unknown' (derived axis) and
  'UNKNOWN' (a measurement report's status/construct) are held as string
  literals rather than read positionally from the schema; they are the
  generic 'axis never examined' marker and any real schema token still
  routes through the report-axis-mismatch and per-axis refusals, so this
  is a legibility note, not a correctness gap. F3 - _decide judges report
  faithfulness before axis compatibility; this ordering is deliberate
  (leakage is the higher-severity failure) and is recorded so the
  precedence is explicit. F4 - report.json/commands.jsonl are
  materialized by this build/seal step (the sealing session's emission
  responsibility), now satisfied.
- Residual limitations: R06 gates typed crossovers and records an
  auditable safety receipt only. It does not score, select, promote or
  evaluate any candidate; it makes no DSSAT or plant-model numerical
  parity claim; promotion remains a governance decision outside this
  module; and this review is not external actor-independent
  certification.
