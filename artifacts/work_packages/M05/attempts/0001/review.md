# M05-0001 primary-session separate adversarial review

- Reviewer: primary session in a separate adversarial pass under the
  product-owner instruction forbidding subagents and Fleet;
  actor_independence=false is recorded, not hidden.
- The map answers three questions nothing else owned: which cell a
  candidate occupies, how concentrated the population has become, and
  what a change would actually touch. All three are descriptive — the
  map recommends and records, it never promotes, evicts or erases.
- Cell identity is the load-bearing decision. A niche id is derived
  from the canonical axis coordinates, so the same cell is always the
  same cell: a duplicate coordinate set, a forged id, and coordinates
  edited after the id was derived are all refused, and a candidate
  occupying two cells is refused because a MAP-Elites assignment must
  be a function of the candidate.
- The repository's own EF4-I22 gate caught a real violation during
  this attempt: reading the axis names from the schema's required
  list put the literal 'required' — a canonical minority-report enum
  value — into the module. The fix reads the axis object's property
  keys instead, and a test asserts the two declarations agree.
- One numerical decision is recorded openly: the effective lineage
  count is the exponential of the *published* entropy, so the pair
  re-derives exactly from the report's own fields. Four uniform
  founders therefore report 3.999999 rather than 4.0; coherence beats
  prettiness, and a re-derivation test holds it.
- Diversity is measured against hand-computed values: zero entropy
  for a single founder, ln(4) for four uniform founders, dominant
  share 4/5 on the fixture population, and the within-lineage
  crossover alert distinguishes crossing two branches of one founder
  from a genuine cross between lineages.
- Entropy over a partial population is refused rather than
  published: model attribution, operator attribution and island
  membership must each cover every candidate, and the blast radius
  names unmapped candidates instead of dropping them.
- The blast radius composes the sealed L05 lineage memory rather
  than re-walking ancestry, the coverage summary is delegated to the
  sealed archive builder, and the D05 store regression ran against
  real PostgreSQL via the pinned container, 84/84.
- One file outside the manifest grant was authorized and recorded:
  src/epistemic_foundry/cartography/__init__.py, on the same verified
  packaging grounds as the effects and evolution markers
  (HD-EF4-M05-SCOPE-20260802-001), with a named packaging-discovery
  check proving the package stays discoverable.
- Residual limitations: stagnation detection is temporal and belongs
  to the run that observes it; model attribution belongs to the
  caller; the map does not decide anything downstream of what it
  reports; and this review is not external actor-independent
  certification.
