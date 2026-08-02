# W06-0001 independent contract review

- Author: a bounded implementation agent dispatched in parallel under
  the product owner's explicit aggressive-parallel-agent authorization.
  Reviewer: this sealing session, which did not author the subject code
  and reviewed it independently against the authority chain. The author
  and the reviewer are distinct actors, so actor-independence HOLDS;
  external actor-independent (provider-independent) certification does
  NOT hold. Verdict: PASS, blocking_finding_count=0.
- Verification basis: static reading of
  src/epistemic_foundry/recovery/v4_w06/gate.py and the modules it
  composes (recovery.v4_w05 resume/quarantine, evolution_chamber.
  reconciliation, release.replay, scheduler.v4_n06, evolution.v4_f05,
  domain.hashing), plus inspection-only execution: the W06 targeted
  suite (50 tests: 12 schema-and-type, 10 unit-and-contract, 18
  negative-and-adversarial, 10 provenance-and-receipt) and
  check_packaging.py pass. No FORGE state was mutated by the review.
- Per-exit-criterion: (1) all governing schemas, authority boundaries
  and failure states implemented exactly - PASS; the disposition
  vocabulary is read from the reconciliation owner and the replay
  equivalence tokens are reached only through release.replay predicates,
  proven by the repository wire-literal scanner narrowed to this package
  (EF4-I22). (2) happy / negative / crash-resume(=replay determinism) /
  adversarial coverage - PASS; the five finding codes each have a driving
  negative and the two adversarial forgeries (a rewritten equivalence and
  a self-consistent re-hash) are both refused. (3) no candidate, model,
  prompt, backend or hook acquires evaluator, holdout or promotion
  authority - PASS. (4) all effects resolve to immutable, re-derivable
  receipts - PASS.
- Evolution-integrity: PASS. This is an integration gate that composes
  the sealed owners rather than re-deriving them: the resume is W05's and
  its F05 codes travel out intact, the fan-out is the EF4-I60 owner's
  report carried verbatim under its own key, replay equivalence is the
  release module's byte-for-byte verdict, and the schedule verdict is
  N06's. The crash boundary the gate adds - a lost candidate and one
  driven into two terminal states - is exactly the failure no single
  fan-out can see; double-counting is reported before a lost candidate so
  the more immediate corruption of the population totals is named first.
  A replay report is re-hashed before its verdict is trusted, so a forged
  equivalence is caught (INPUT_INVALID) and a comparable-but-not-identical
  replay is refused (REPLAY_NOT_REPRODUCED) rather than folded into
  success; the schedule report carries no run identity of its own, so it
  is bound to the recovered run by sealing rather than by trusting a
  label, and the one asserted run identity (the replay's source_run_id) is
  refused when it disagrees (RECOVERY_RUN_MISBOUND). The forward-only
  evaluator-update rule is quarantine's and its QuarantineViolation is
  unwrapped. Nothing scores, selects, promotes or evaluates; an AST scan
  asserts the gate holds no promote/promotion/fitness_score/holdout_content
  name. EF4-I22 is honored: no canonical enum token is held as a literal.
- Findings (all non-blocking): F1 - the full-node-suite inventory guard is
  pinned to the live count of Node test files under packages/tests/web at
  build time; it is a fail-closed tripwire (a drift is rejected, never
  silently absorbed) and the count is recorded in node-test-inventory.json,
  so it is documented rather than assumed. F2 - the unassessed replay
  sentinels live in release.replay and are reached only through its
  predicates, so no equivalence token is a literal here; recorded as a
  legibility note. F3 - D06 is a schema/migration dependency composed
  transitively through W05 and exposes no importable module, so it has no
  dedicated dependency regression; its sealed report is still pinned and
  verified. F4 - report.json/commands.jsonl are materialized by this
  build/seal step (the sealing session's emission responsibility), now
  satisfied.
- Residual limitations: W06 accounts for a crash recovery and records an
  auditable, re-derivable receipt only. It does not score, select,
  promote or evaluate any candidate; the fan-out reconciliation, the
  forward-only rule and the replay equivalence are each the sealed
  owner's, composed rather than re-implemented; it makes no DSSAT or
  plant-model numerical parity claim; promotion remains a governance
  decision outside this module; and this review is not external
  actor-independent certification.
