# X04 package review record

Standing verdict: `PASS` (from attempt `0001`).

This file is the package-level projection the manifest requires. The
attempt review below, at `attempts/0001/review.md`, is the primary record.

---

# X04-0001 independent review of bounded-agent work

- Author: a bounded implementation agent (X04 maker) that produced the
  cross-provider parity and error-correlation evaluation under the frozen
  write scope evals/provider_parity/**. Reviewer: the sealing session,
  which did not author this attempt. Author/reviewer separation holds
  (actor_independence=true); external actor-independent certification
  does not.
- Mode: INDEPENDENT_REVIEW_OF_BOUNDED_AGENT_WORK. Blocking findings: 0.
- Scope: the product write scope is evals/provider_parity/** only (the
  seal scripts sit in the second granted scope
  artifacts/work_packages/X04/**). No schema, manifest, adapter surface
  or .rah/ state was touched; the six product files sit exactly inside
  the granted scope and are hash-pinned.
- Parity is derived from the sealed adapter surfaces, never invented: the
  canonical role set is read from manifests/role_registry.yaml, the Codex
  (X01) and Claude Code (X02) adapter role maps are measured as they
  stand, and a dropped role, a rebound canonical output schema, an
  unnamed host agent type, a non-uniform Claude surface, and isolation
  that stops tracking a write scope are each refused with a typed
  finding; the refusal cases mutate in-memory copies so the sealed
  adapter files on disk are never touched.
- Diversity is measured, not assumed independent: the 2x2 error
  contingency and phi coefficient are recomputed from the raw synthetic
  trials, the observed joint-error rate exceeds what independence would
  predict (positively correlated), and a fixture asserting independence
  or a provider presented as live is each refused. The committed results
  artifact is re-derived from the sources and any edit breaks its own
  hash.
- Authority and provider boundary: nothing here scores, selects,
  promotes or evaluates any candidate, no eval or fixture acquires
  evaluator/holdout/promotion authority, and no live provider is invoked
  (every provider is declared synthetic).
- Gates at review time: provider_parity_eval 8/8, error_correlation_eval
  8/8, the full Python suite and the full Node suite green, and git diff
  --check clean. Dependencies X02-0001 and X03-0001 are bound and
  G06-0001 is the live latest-sealed regression baseline.
