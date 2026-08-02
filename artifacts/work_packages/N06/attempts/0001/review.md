# N06-0001 independent review of bounded-agent work

- Author: a bounded implementation agent (disjoint write scope, frozen
  contracts) that implemented the v4_n06 gate and drove it targeted-green.
  Reviewer: an independent reviewer that did NOT author the gate and read
  it adversarially against the N06 contract, the exit criteria and the
  evolution-integrity invariants. Actor-independence between author and
  reviewer HOLDS; external actor-independent (provider-independent)
  certification does NOT hold. Verdict: PASS, blocking_finding_count=0.
- Verification basis: static reading of the subject (integration.py) plus
  the composed sealed scheduler (scheduler.v4_n05) and the hashing and
  receipt primitives it reuses (domain.hashing, noetic_ledger.receipts),
  plus inspection-only execution: the four required suites, the N05
  dependency regression, packaging-discovery, and the full Python and
  Node suites all pass. No FORGE state was mutated by the review.
- Backpressure: verified the gate refuses only the shed case
  (ADMISSION_SILENTLY_SHED) — a deferred candidate that later starts, or
  one that lands in explicit failure/refusal accounting, is not refused —
  and that a declared policy is checked against the schedule in BOTH
  directions (ADMISSION_POLICY_CONTRADICTED), so neither a silent drop nor
  a false promise passes. Refusal ledger entries must be receipted and
  warranted by real pressure.
- Missing worker: LANE_PROGRESS_STALLED counts event indices, not wall
  clock, so a stall is machine-speed-independent; in-flight work no
  declared worker holds is refused first (WORKER_ATTRIBUTION_MISSING) so a
  stall is always attributable. Per-candidate-per-lane progress tracking
  correctly catches one stuck candidate hiding inside a busy lane.
- Resource locks: overcommit over a named interval, progress without a
  required lock, a resource retained at end, an impossible lock sequence,
  and a declared wait cycle are each refused by their own code; the
  deadlock is a strongly-connected component over SORTED adjacency, so the
  same declaration always names the same participants (deterministic).
- No silent partial fan-in: a schedule that ENDS holding in-flight work is
  not restated here — it is N05's FANIN_INCOMPLETE, re-raised under N05's
  own ScheduleError, and require_integrated_run checks this gate's own
  findings BEFORE schedule validity so the cause (stall/deadlock) is named
  ahead of the symptom (incomplete fan-in). One defect keeps one name.
- Evolution-integrity (EF4-I22 and authority containment): PASS. The gate
  takes no evaluator/holdout/fitness/promotion parameter, names none in
  any FINDING_CODE (asserted by a forbidden-token test), and derives
  `integrated` as `schedule.valid AND no finding` — a conjunction, never a
  score that could be optimised into a pass. It holds no canonical schema
  enum string literal and no lane/action/stage identity of its own; all of
  those are imported from the sealed scheduler. seal_integration_record
  chains N05's verdict hash rather than re-opining, and is timestamp- and
  mint-free, so records replay byte-for-byte.
- Findings (all non-blocking): F1 — verify_integration accepts
  effect_receipts and mutation_receipts kwargs; these are forwarded
  unchanged to N05's verify_schedule for the schedule's own failure and
  reconciliation accounting and are never scored here, so the authority
  boundary holds; recorded as a surface-area note. F2 — the gate is
  quadratic by design (one N05 call per prefix) and bounds itself at
  MAX_SCHEDULE_EVENTS=512, refusing longer schedules
  (SCHEDULE_LENGTH_UNSUPPORTED) rather than adding a faster second walk
  that could drift; informational.
- Residual limitations: N06 gates a DECLARED run (lock and wait ledgers
  are declarations, not observations); a runtime that takes a lock or
  stalls a worker without declaring it is outside what a declaration can
  reveal, as the module states. It scores, selects, promotes and evaluates
  nothing; it makes no DSSAT or plant-model parity claim; promotion
  remains a governance decision; and this review is not external
  actor-independent certification.
