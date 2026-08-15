# L05 package review record

Standing verdict: `PASS` (from attempt `0001`).

This file is the package-level projection the manifest requires. The
attempt review below, at `attempts/0001/review.md`, is the primary record.

---

# L05-0001 primary-session separate adversarial review

- Reviewer: primary session in a separate adversarial pass under the
  product-owner instruction forbidding subagents and Fleet;
  actor_independence=false is recorded, not hidden.
- The gap this package closes is real: the archive decides what may
  be evicted for capacity and the memory policy decides what may be
  recalled, but nothing decided what survives an actual forget or
  what an export may carry out. Erasure obligations exist — consent
  withdrawal, regulated erasure, workspace purge — so a module that
  could only refuse would be as wrong as one that deletes freely.
- Two real defects were found by this review before any test was
  written against them, and both fixes are proven by regression
  tests. First, the lineage cycle check compared bound-method
  identity, which is a fresh object on every access, so it never
  fired and a self-ancestry passed silently. Second, erasure
  eligibility was computed against the requested set rather than the
  erased set, so an ancestor could be erased while its descendant
  survived as a tombstone whose lineage record then pointed at
  nothing. Eligibility now iterates to fixpoint, and the whole-chain
  forget stops at the protected tombstone instead of deleting the
  ancestry above it.
- Negative knowledge has an asymmetric rule and the tests hold it in
  both directions: capacity pressure can never erase any of the five
  protected classes, while an external obligation may reduce them to
  a tombstone that keeps the class, the reason, the hash, the
  lineage id and the generation — the facts that outlive the
  payload. An export of only negative knowledge is permitted; an
  export that keeps results while dropping any negative class beside
  them is refused as survivorship bias.
- Nothing is restated. Entry classes come from the canonical schema
  with the archive partition verified on every use; export scope is
  delegated to require_recall_permitted so consent, class, retention
  and workspace checks cannot be partially honoured; and the engine
  source holds no canonical enum value as a literal, enforced by the
  repository's own EF4-I22 gate running as a named check.
- The D05 regression ran against real PostgreSQL via the pinned
  container image, 84/84, because mock-only store tests are
  forbidden in this repository.
- Residual limitations: the plan decides, it does not delete — the
  transaction against the D05 store and its effect receipt belong to
  the runtime; external-sync dispositions are recorded, not
  interpreted, because their vocabulary belongs to the policy owner;
  and this review is not external actor-independent certification.
