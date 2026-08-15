# W05 package review record

Standing verdict: `PASS` (from attempt `0001`).

This file is the package-level projection the manifest requires. The
attempt review below, at `attempts/0001/review.md`, is the primary record.

---

# W05-0001 independent contract review

- Author: a bounded implementation agent under the primary session's
  delegation. Reviewer: an independent reviewer agent that did not
  author the subject workflow and reviewed it adversarially against the
  authority chain and the evolution-integrity rules. Actor-independence
  between author and reviewer HOLDS; external actor-independent
  (provider-independent) certification does NOT hold. Verdict: PASS,
  blocking_finding_count=0.
- Verification basis: static reading of the subject
  (recovery/v4_w05/workflow.py) plus the composed dependencies
  (evolution.v4_f05 machine, evolution_chamber.checkpoint,
  verifier_firewall.firewall, governance.quarantine), plus
  inspection-only execution: the W05 targeted suite and
  check_packaging.py pass, and the four sealed dependency regressions
  (W04 replay/drift Node, D05 store, F05 machine, N05 scheduler) are
  green. No FORGE state was mutated by the review.
- Per-exit-criterion: (1) governing schemas / authority boundaries /
  failure states exact - PASS: the resume point is validated against the
  canonical evolution-checkpoint schema and must re-derive its digest;
  the cancel stop reason must be one the checkpoint module classifies;
  the two reassessment statuses are package-local by necessity and are
  deliberately NOT schema enum values (EF4-I22). (2) happy / negative /
  crash-resume / adversarial coverage - PASS. (3) no candidate, model,
  prompt, backend or hook acquires evaluator / holdout / promotion
  authority - PASS. (4) all effects resolve to immutable, re-derivable
  receipts - PASS.
- Evolution-integrity: PASS. Checkpoint/resume/cancel reconcile the
  candidate and niche counts EXACTLY: the cancel derives the remaining
  map from proposed-vs-evaluated candidates and mapped-vs-assessed
  niches rather than accepting an assertion, refuses a disclosure that
  hides remaining work (CANCEL_PARTIAL_WORK_HIDDEN) or invents it
  (CANCEL_DISCLOSURE_UNACCOUNTED), and refuses a finished id the run
  never started (CANCEL_COUNTS_UNRECONCILED). Evaluator drift is
  detected by the firewall's content-recomputed digest (an edit that
  also rewrote bundle_hash still fires); when it fires the affected
  comparisons are MARKED potentially invalid, never removed and never
  re-scored, and the fix is a future-only quarantined proposal whose
  retroactive application to the producing run is refused by
  quarantine's own rule (no promotion authority is granted). Resume
  binds atomically: the resume record is constructed only after the F05
  machine's require_valid_run passes, and the machine's own refusals
  (RETURN_EDGE_UNCHECKPOINTED, CHECKPOINT_INCOMPLETE) travel out
  unwrapped rather than being re-decided here. Canonical vocabulary is
  composed from the owning modules, not restated as string literals
  (EF4-I22).
- Findings (all non-blocking): F1 - recovery/__init__.py is a namespace
  marker one level above the v4_w05 write glob; its creation is
  pre-authorized by HD-EF4-W05-SCOPE-20260802-001 and its docstring
  cites the exact scope and authority, so this is a recorded
  scope-precision note, not a violation. F2 - the D05 dependency
  regression provisions a real PostgreSQL container through Docker; it
  is green here but depends on Docker being available, which is recorded
  as an environment prerequisite rather than a code defect. F3 -
  physical checkpoint recovery (reading a checkpoint back out of the
  store, replaying a partial transaction) is explicitly out of scope and
  belongs to D06; informational.
- Residual limitations: W05 is the workflow logic over records already
  in hand. It does not score, select, promote or evaluate any candidate;
  it makes no DSSAT or plant-model numerical parity claim; promotion
  remains a governance decision outside this module; it recovers nothing
  physical; and this review is not external actor-independent
  certification.
