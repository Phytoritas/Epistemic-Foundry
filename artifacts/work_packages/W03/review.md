# W03 package review record

Standing verdict: `PASS` (from attempt `0001`).

This file is the package-level projection the manifest requires. The
attempt review below, at `attempts/0001/review.md`, is the primary record.

---

# W03-0001 primary-session separate adversarial review

- Reviewer: primary session in a separate adversarial pass under the
  product-owner instruction forbidding subagents and Fleet;
  actor_independence=false is recorded, not hidden.
- Transitive propagation (EF4-I38): the blast radius is the full
  dependent closure, not one hop.  A retracted document reaches its
  evidence, claims, packs, and every downstream Passport, including a
  Passport that depends on another Passport.  A provenance cycle
  terminates instead of hanging.
- Correction versus retraction: both invalidate dependents, but a
  retraction voids reached Passports (INVALIDATED) while a correction
  leaves them questionable (STALE); a new document prompts
  reassessment without invalidating.  Priority follows the trigger.
- No silent staleness: every affected Passport must carry an explicit
  state, a reached Passport can never be FRESH, an affected Passport
  missing from the supplied set fails closed, and marking creates a
  new revision bound to the plan id, plan hash, and trigger event.
- No empty remediation: an invalidating trigger whose only required
  action is no_action fails closed, so a recorded update cannot stand
  in for an applied one.
- Graph integrity: unknown dependencies, self-dependencies, duplicate
  artifacts, unknown artifact classes, unknown trigger types, and
  trigger artifacts outside the graph all fail closed.
- Determinism: identical inputs seal byte-identical plans with
  content-addressed ids; validation is exact reconstruction, so a
  tampered or rehashed plan is rejected.
- Residual limitations: the component computes and seals plans from a
  declared provenance graph; live graph extraction, ledger-backed
  invalidation events, and reassessment execution remain later
  packages.  This review is not external actor-independent
  certification.
