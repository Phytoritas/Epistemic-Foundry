# ADR-033 — Adapter isolation and explicit degraded modes

**Status:** Accepted

## Context

Host features, model providers, parsers, retrieval systems, sandboxes, and the
optional ShinkaEvolve backend vary by deployment. Assuming a capability from
configuration or allowing an adapter's native score/state to cross the
authority boundary would create lock-in and silent scientific drift.

## Decision

Every external integration is a capability-probed adapter behind a canonical
contract. Adapter outputs are untrusted observations until validated and
recorded by Foundry-owned code. A missing, incompatible, or ambiguous
capability selects an explicit `DEGRADED`, `READ_ONLY`, `SAFE_MODE`, or
`BLOCKED` result as applicable; it never silently selects success or empty
research state.

Provider adapters may perform bounded inference but cannot alter canonical
schemas, policy, gates, evidence truth, evaluator identity, hidden holdout,
promotion, or release. Search backends such as ShinkaEvolve remain optional;
their scores, correctness flags, archive, novelty, island, lineage, and bandit
state are advisory observations mapped through Foundry contracts.

## Consequences

- The domain-neutral core starts and preserves semantics with no ShinkaEvolve
  installation and no particular model provider.
- Provider fallback is visible and receipt-bound.
- Adapter-specific types terminate at the mapping boundary.
- Ambiguous semantic mappings fail closed rather than inventing equivalence.

## Rejected alternatives

- Make one provider or search backend a mandatory canonical dependency.
- Treat backend `correct` or combined score as a promotion decision.
- Render adapter failure as an empty result set.
- Infer capability availability from documentation or profile name alone.

## Verification

- Provider-neutrality and backend-isolation tests exercise semantic mapping and
  authority rejection.
- Plugin and host acceptance gates exercise missing-capability paths.
- `boundary_cycle_policy_check` rejects inward layers importing adapter
  implementations.
