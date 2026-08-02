# W02-0001 primary-session separate adversarial review

- Reviewer: primary session in a separate adversarial pass under the
  product-owner instruction forbidding subagents and Fleet;
  actor_independence=false is recorded, not hidden.
- Recoverability is proven, not asserted: replay_verified is computed
  by replaying the recorded command log into a fresh scheduler and
  comparing state hashes, and sealing fails closed on divergence.
  A forged replay_verified=false manifest fails the field-set and
  self-hash validation instead of silently resuming.
- Resume authority (EF4-I12): a checkpoint resumes only under an
  APPROVE review whose reviewer differs from the author and whose
  checkpoint_hash binds the exact manifest; rejected, self-approved,
  mis-bound, and non-canonical decisions all fail closed.
- Replay identity: a truncated command log is rejected by sealed
  sequence length, a reordered log is rejected by the scheduler
  itself, and the rebuilt scheduler must reach the exact sealed
  state hash before it is handed back.  A resumed scheduler then
  continues the run to the same state a never-interrupted run
  reaches.
- Cancellation honesty (EF4-I13/I26): every LEASED, RUNNING, or
  RECONCILING attempt is a pending effect.  Cancellation is
  CANCELLED only when each one resolves to a terminal receipt;
  a missing receipt or an UNKNOWN status yields
  CANCELLED_WITH_UNRESOLVED_EFFECTS with the exact unresolved list.
  Foreign, duplicate, and non-canonical receipts fail closed, so a
  fabricated receipt cannot launder an unknown effect.
- Purity: cancellation and pause do not mutate the scheduler; both
  seal deterministic, hash-bound manifests.
- Finding (resolved): the runtime initially read a non-existent
  attempt field name and a plain-object scheduler shape; both were
  corrected against the real sealed scheduler snapshot rather than
  by relaxing the tests.
- Residual limitations: durable checkpoint storage, ledger-backed
  resume, and evidence-driven reassessment (W03) are outside this
  package; this review is not external actor-independent
  certification.
