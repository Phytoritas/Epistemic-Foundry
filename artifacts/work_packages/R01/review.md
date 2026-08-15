# R01 package review record

Standing verdict: `PASS` (from attempt `0001`).

This file is the package-level projection the manifest requires. The
attempt review below, at `attempts/0001/review.md`, is the primary record.

---

# R01-0001 primary-session separate adversarial review

- Reviewer: primary session in a separate adversarial pass under the
  product-owner instruction forbidding subagents and Fleet;
  actor_independence=false is recorded, not hidden.
- Independence adjustment is structural, not advisory. Every finding
  carries the independence weight of its O03 dependency cluster
  (support_count_adjusted / support_count_raw), so a cluster of k
  dependent replications contributes exactly its adjusted support and
  never k votes. The fixture pack clusters two of four positive
  findings, and the synthesis reports raw_count 4 against adjusted
  weight 3. The engine recomputes the pack's effective independent
  count from the clusters and refuses to proceed when the pack's own
  declared value disagrees, or when the supplied clusters do not match
  the membership the pack declares.
- The same weights enter the statistics. Inverse-variance weights are
  scaled by independence before Cochran Q, so dependent replications
  cannot present themselves as that many precise measurements; halving
  both weights halves Q while leaving the pooled effect unchanged.
- Heterogeneity fails toward ignorance. Fewer than two quantitative
  findings, or any finding with no positive independence weight,
  yields UNDETERMINED with a stated reason rather than a reassuring
  LOW, and a sealed record whose classification is UNDETERMINED with
  no reason is rejected. A band boundary resolves upward into the more
  cautious band.
- Moderators and nulls are retained by construction. Every observed
  moderator and level appears in the output whether it discriminates,
  agrees, or has a single level, because an absent moderator is
  indistinguishable from one never examined. A retained moderator with
  no levels and a declared null with no finding both fail closed, and
  a null stratum keeps its own direction rather than being absorbed.
- No causal promotion. The synthesis reports relation_kind ASSOCIATION
  and causal_identification NOT_ASSESSED; injecting either a causal
  relation kind or an identification verdict is refused. Identification
  belongs to R04.
- Integrity: identical inputs seal byte-identical artifacts, the
  synthesis id is the content address of the recorded conclusions, and
  a tamper that recomputes the self-hash is still caught because the id
  no longer derives from the content it claims.
- Residual limitations: the engine consumes findings supplied by a
  caller and does not itself extract effect sizes from sources;
  moderator discrimination is a direction-level screen rather than a
  between-group significance test; and R02/R03/R04 remain unbuilt. This
  review is not external actor-independent certification.
