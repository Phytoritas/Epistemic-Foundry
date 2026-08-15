# C06 package review record

Standing verdict: `PASS` (from attempt `0001`).

This file is the package-level projection the manifest requires. The
attempt review below, at `attempts/0001/review.md`, is the primary record.

---

# C06-0001 primary-session separate adversarial review

- Reviewer: primary session in a separate adversarial pass under the
  product-owner instruction forbidding subagents and Fleet;
  actor_independence=false is recorded, not hidden.
- An integration gate is only worth the independence of what it
  reconciles. Four receipts cover the C05 family and none derives from
  another: the sealed C05 index and the TypeScript, Python and UI
  contract manifests C02 emits. All four must agree with the live
  canonical file for every one of the 42 members; a disagreement is
  refused rather than resolved by picking a winner.
- The gate caught a real error during this attempt. The first fixture
  mapping bound the whole fifteen-member genome family to the
  candidate composite, and candidate-generation-record failed. The
  composite was right and the mapping was wrong: only the four mutable
  genome kinds are candidates (EF4-I41). Rather than widen the
  composite, the mapping was corrected and the remaining eleven are
  now checked from the hostile side — each must be refused as a
  candidate — and recorded as schema-only with the reason.
- Fixtures are proved against the repository, not against themselves.
  Every member's canonical example validates against its own schema,
  and where a C05 composite governs it, against that composite too:
  84 validations over 42 members. This is what turns C05's composites
  from plausible structure into structure the repository's own
  fixtures satisfy.
- Compatibility is structure, not advice. A migration cannot validate
  without the compatibility matrix it applies under, and the binding
  adds no vocabulary: every constraint is a reference to the canonical
  contract that owns it, checked by the same forbidden-keyword scan
  C05 uses.
- Nothing outside the write scope was touched. The 127 canonical
  schemas, the canonical examples, the three generated projections and
  the sealed C05 bundle are all read-only inputs, hashed into the
  receipt and verified unchanged.
- Residual limitations: the gate reconciles receipts and fixtures, not
  the generators that produced them — regenerating the C02 projections
  is C02's own codegen_clean_diff check; the compatibility binding
  describes what a migration record must carry, not whether a proposed
  migration is correct, which C03 owns; and this review is not
  external actor-independent certification.
