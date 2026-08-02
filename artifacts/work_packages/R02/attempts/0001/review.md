# R02-0001 primary-session separate adversarial review

- Reviewer: primary session in a separate adversarial pass under the
  product-owner instruction forbidding subagents and Fleet;
  actor_independence=false is recorded, not hidden.
- Premise binding is structural. A node typed premise must cite
  evidence, so an unevidenced statement can only stand as an
  assumption, and any other node type that carries support without
  evidence is refused outright. A conclusion resting on nothing, or on
  a floating intermediate claim, cannot be sealed.
- The assumption ledger is derived, not trusted. The engine computes
  the load-bearing unevidenced assumptions from the supporting graph
  and requires the graph's declared hidden_assumption_ids to equal
  them exactly, so both an undeclared assumption and an over-declared
  one fail closed. Each ledger entry records its grounding and the
  conclusions that rest on it; stripping the ledger from a rehashed
  trace is still caught because the conclusions still cite it.
- Scope widening is rejected rather than downgraded. A conclusion may
  narrow a ScopeVector but may not drop a scalar boundary, an
  inclusion or exclusion criterion, or a condition that any premise
  carried, nor move to a value no premise covers. Every scalar, set,
  and map field of the canonical ScopeVector is exercised, and an
  unconstrained assumption cannot launder a scope the evidence never
  had because only premise scopes bound the conclusion.
- Trace integrity: the supporting graph must be acyclic, every edge
  endpoint must exist, a deductive edge must name its rule, a
  conclusion resting on rejected support cannot be accepted, and a
  standing objection must be declared. Identical inputs seal
  byte-identical artifacts and a tampered trace is rejected.
- The fixtures are validated against the canonical
  schemas/argument-graph.schema.json with its ScopeVector reference
  resolved, so the component's shape is bound to the shared contract
  rather than to a local convention.
- Residual limitations: the engine checks a declared ArgumentGraph and
  does not construct proofs or verify that a named rule licenses its
  inference; rule_ref is an identifier, not a checked derivation.
  Abduction and contradiction handling are R03 and causal
  identification is R04. This review is not external
  actor-independent certification.
