# S05 package review record

Standing verdict: `PASS` (from attempt `0001`).

This file is the package-level projection the manifest requires. The
attempt review below, at `attempts/0001/review.md`, is the primary record.

---

# S05-0001 primary-session separate adversarial review

- Reviewer: primary session in a separate adversarial pass under the
  product-owner instruction forbidding subagents and Fleet;
  actor_independence=false is recorded, not hidden.
- The gap this package closes is the one EF4-I64 names: the firewall
  seals evaluators, the quarantine holds proposals inert, and the
  sandbox bounds ordinary tools, but nothing decided whether an
  evolution candidate's code may execute at all. Now nothing runs
  without declared capabilities, an enforceable quota, a bound
  effect-receipt channel, a declared sandbox class and verified
  evaluator/holdout isolation — and the isolation is probed live
  against the sealed firewall for every candidate-generating role,
  not read from a flag.
- The repository's own EF4-I22 gate caught a real violation during
  this attempt: the minimum leakage surfaces were first held as
  literals, and 'tool' is a canonical enum value elsewhere. The fix
  is better than the original intent — the surfaces are now parsed
  from EF4-I44's own statement, so a widened invariant widens the
  audit floor without an edit here.
- Every positional enum assumption is pinned. The engine refuses the
  last network policy and requires approval at the last safety class
  by position, because holding the enum values would violate
  EF4-I22; the schema-and-type suite asserts the declared orderings
  verbatim so the assumption cannot rot in silence.
- The gates are passable, which matters as much as their refusals: a
  closed-network bounded target qualifies, an allowlisted network
  qualifies exactly when its capabilities are declared, every
  declared sandbox class is acceptable, and an APPROVED proposal
  activates for a future run while its own source run stays refused
  through the quarantine module's own retroactivity rule.
- The threat register is exact in both directions: coverage without
  evidence is refused, and evidence for an invented threat is
  refused rather than padding the record. A failed leakage audit
  carries the incident actions in the threat model's own words and
  never converts an exposure into a score.
- Nothing is reimplemented: influence and retroactivity come from
  the quarantine module, isolation and drift detection from the
  firewall, quota normalization from the budget module, and the
  search space from the sealed C05 index.
- Residual limitations: the qualification decides, it does not
  execute — the lease, the sandbox process and the effect receipt
  belong to the T-phase and the runtime; similarity alerts are
  recorded from the caller because deriving them needs content
  access this module does not have; and this review is not external
  actor-independent certification.
