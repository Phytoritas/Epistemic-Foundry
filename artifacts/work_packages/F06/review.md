# F06 package review record

Standing verdict: `PASS` (from attempt `0001`).

This file is the package-level projection the manifest requires. The
attempt review below, at `attempts/0001/review.md`, is the primary record.

---

# F06-0001 independent contract review

- Author: a bounded implementation agent dispatched in parallel under
  the product owner's explicit aggressive-parallel-agent authorization.
  Reviewer: this sealing session, which did not author the subject code
  and reviewed it independently against the authority chain. The author
  and the reviewer are distinct actors, so actor-independence HOLDS;
  external actor-independent (provider-independent) certification does
  NOT hold. Verdict: PASS, blocking_finding_count=0.
- Verification basis: static reading of
  src/epistemic_foundry/evolution/v4_f06/gate.py and the modules it
  composes (evolution.v4_f05, intake.v4_i05, reasoning.v4_r05, contracts,
  domain.hashing) and the canonical forge-session-state / replay-report /
  evolution-stop-certificate schemas, plus inspection-only execution: the
  F06 targeted suite (51 tests: 7 schema-and-type, 11 unit-and-contract,
  24 negative-and-adversarial, 9 provenance-and-receipt) and
  check_packaging.py pass. No FORGE state was mutated by the review.
- Per-exit-criterion: (1) all governing schemas, authority boundaries
  and failure states implemented exactly - PASS; the handoff phase, the
  replay vocabulary and the stop-reason vocabulary are read from the
  canonical schemas and the composed F05 machine via _vocab() and the
  re-exports, the forge session and replay report are validated against
  their schemas before use, and the fifteen finding codes are guarded for
  membership by _fail. (2) happy / negative / crash-resume / adversarial
  coverage - PASS; the happy path admits and every declared finding code
  has a driving negative, the crash/resume case is a stop certificate
  naming an uncommitted checkpoint, and the suite self-guards that the
  exercised set equals FINDING_CODES. (3) no candidate, model, prompt,
  backend or hook acquires evaluator, holdout or promotion authority -
  PASS. (4) all effects resolve to immutable, re-derivable receipts -
  PASS.
- Evolution-integrity: PASS. This is an integration gate that composes
  the sealed lifecycle/intake/operator owners rather than re-deriving
  them: the lifecycle and stop-certificate verdict is F05's own
  evaluate_run / require_valid_run output, the seed population is
  bootstrapped and reconciled through I05 intake, and every operator is
  resolved against the sealed R05 registry. Replay is read from the run's
  own ReplayReport and never trusted to flatter itself: a report that
  claims exact equivalence while its own counters record a hash mismatch,
  a missing pin, drift or a gate/verdict difference is refused as
  dishonest (REPLAY_REPORT_DISHONEST) before its verdict is taken at face
  value, and only a strict, exact, drift-free reproduction is honoured
  byte-for-byte. Evaluator immutability (EF4-I43) is a refusal axis: a
  run whose checkpoints bind more than one evaluator bundle hash is
  refused (EVALUATOR_BUNDLE_MUTATED), and the treated-as-a-leakage-channel
  evaluator is never a lever the gate can be pushed on. Nothing scores,
  selects, promotes or evaluates; the receipt is scanned by the
  provenance suite to hold no fitness/score/promote/rank/holdout/elevate
  fragment, and the decision is only ever ADMIT or REFUSE. EF4-I22 is
  honored: _vocab() reads every token from the canonical schema and fails
  closed on a reshape.
- Findings (all non-blocking): F1 - EF4-I22 is honored positionally
  (_vocab() derives the handoff phase from the schema's terminal phase and
  the replay tokens from schema enum order, guarding each length), so
  correctness depends on the schema-and-type suite asserting each token
  against the canonical schema text; that suite exists and passes (7
  tests), so the invariant is guarded rather than assumed; recorded as a
  design note. F2 - the ADMIT/REFUSE decision tokens and the
  EVALUATOR_BUNDLE_FIELD checkpoint field name are held as string literals
  rather than read from a schema; they are the gate's own outcome
  vocabulary and a documented checkpoint field, not a canonical wire enum,
  so this is a legibility note, not a correctness gap. F3 - _first_finding
  evaluates the axes in a fixed priority order (handoff, lifecycle,
  evaluator, seed, operator, candidate, replay); the ordering is
  deliberate and recorded so the precedence a refusal reports is explicit.
  F4 - report.json/commands.jsonl are materialized by this build/seal step
  (the sealing session's emission responsibility), now satisfied.
- Residual limitations: F06 gates the FORGE-EVOLVE handoff and records an
  auditable lifecycle-replay receipt only. It does not score, select,
  promote or evaluate any candidate; it makes no DSSAT or plant-model
  numerical parity claim; promotion remains a governance decision outside
  this module; and this review is not external actor-independent
  certification.
