# U05-0001 independent contract review

- Author: a bounded implementation agent that wrote the Evolution
  Chamber console under src/epistemic_foundry/console/v4_u05.
  Reviewer: an independent contract-reviewer session that did not
  author the subject code and reviewed it adversarially against the
  authority chain. Actor-independence between author and reviewer
  HOLDS; external actor-independent (provider-independent) certification
  does NOT hold. Mode: INDEPENDENT_REVIEW_OF_BOUNDED_AGENT_WORK.
  Verdict: PASS, blocking_finding_count=0.
- Verification basis: static reading of the subject plus the composed
  surfaces (cartography.v4_m05 mapper, the contracts registry, the
  challenge-genome/challenge-result/candidate-lineage/pareto-front-
  snapshot/epistemic-niche schemas, domain.hashing), plus
  inspection-only execution: the four U05 required suites (48 tests),
  the repository wire-literal-discipline gate, packaging-discovery, and
  ruff lint/format all pass over the final bytes. No FORGE state was
  mutated by the review.
- Per-exit-criterion: (1) all governing v4 schemas, authority
  boundaries and failure states implemented exactly - PASS: every input
  is validated against its canonical schema, each sealed hash is
  re-derived, and each FINDING_CODE names an exact refusal; (2) happy /
  negative / crash-resume / adversarial coverage - PASS: every finding
  code is driven by a negative, a persisted view re-derives its identity
  after reload, and a tampered view and an authority grab are refused;
  (3) no candidate, model, prompt, backend or hook acquires evaluator,
  holdout or promotion authority - PASS: any authority_request is
  refused before a surface is touched and the two authority markers are
  invariant; (4) all completion and external effects resolve to
  immutable receipts - PASS: view_id and view_hash are a pure function
  of the record's own content, so equal inputs are byte-equal.
- Evolution-integrity: PASS. The console reads sealed state only: it
  invents nothing (every candidate id, niche, outcome and severity is
  read from the sealed artifact or, for the ordered buckets, from the
  canonical schema, never named as a literal - EF4-I22, enforced by the
  wire-literal gate over the whole console tree), it never scores,
  selects, promotes or exposes a holdout, and a candidate-generating
  role (ef-hypothesis-mutator, ef-challenge-evolver) may READ but is
  granted nothing. No overclaim.
- Findings (all non-blocking): F1 - src/epistemic_foundry/console/
  __init__.py is a namespace marker one level above the v4_u05 write
  glob; it carries no logic and is the mandatory first marker of the new
  console tree, proven a wheel prerequisite by check_packaging.py.
  Recorded as a scope-precision note; ratified as a packaging
  prerequisite. F2 - report.json/commands.jsonl are materialized by the
  seal step (the primary session's emission responsibility). F3 -
  crash/resume maps to persisted-view re-derivation for this pure
  module; informational.
- Residual limitations: U05 projects sealed state read-only. It does not
  score, select, promote or evaluate any candidate; it exposes no
  holdout; it makes no DSSAT or plant-model numerical parity claim;
  promotion remains a governance decision outside this console; and this
  review is not external actor-independent certification.
