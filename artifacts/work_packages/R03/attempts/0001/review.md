# R03-0001 primary-session separate adversarial review

- Reviewer: primary session in a separate adversarial pass under the
  product-owner instruction forbidding subagents and Fleet;
  actor_independence=false is recorded, not hidden.
- Disagreement is typed before it is filed. Opposite directions alone
  do not make a contradiction: identical conditions and measurement
  give DIRECT_CONTRADICTION, differing conditions give
  CONDITION_DIFFERENCE, a strict refinement gives SCOPE_NESTED, and
  the same conditions under different instruments give
  MEASUREMENT_DIFFERENCE. A pair the engine cannot attribute is
  UNCLASSIFIED and cannot be sealed, so nothing is filed as a
  contradiction by default. Directions that assert no position -
  unknown, not_applicable, mixed - can never manufacture a conflict.
- Competing explanations survive by construction. Each conflict needs
  at least two standing explanation kinds; two restatements of one
  kind are not competing, and an explanation with no discriminating
  test cannot compete because nothing could tell it apart. A refuted
  explanation stays in the record with the evidence that refuted it,
  and refuting the field down to a single kind is itself a
  monoculture failure rather than a resolution.
- R03 never adjudicates. selected_explanation_id is always null and
  the adjudication owner is the Evidence Parliament; injecting either
  a selection or a different owner is refused even after the record is
  rehashed.
- Integrity: conflict ids are stable under input order, identical
  inputs seal byte-identical artifacts, and a rehashed tamper is still
  caught because the recorded competing kinds are recomputed from the
  explanations rather than trusted.
- Residual limitations: the engine types and preserves explanations
  supplied by a caller rather than generating them, does not execute
  the discriminating tests it requires, and treats conditions as an
  opaque key/value map rather than a full ScopeVector comparison.
  Causal identification remains R04. This review is not external
  actor-independent certification.
