# AGENTS.md — Epistemic Foundry v4

## Authority

Read and obey in order:

1. `MASTER_SPEC.md`
2. `manifests/development_manifest.yaml`
3. `manifests/acceptance_matrix.yaml`
4. `manifests/product_invariants.yaml`
5. applicable `schemas/*.schema.json` and `workflows/*.workflow.yaml`
6. `manifests/role_registry.yaml`
7. this file
8. work-package-local notes

When a lower source conflicts with a higher source, stop with `SPEC_GAP`.
Never invent a missing shared contract.

## Current maturity

This bundle is a **SPEC_BUNDLE / REFERENCE_BLUEPRINT**. Do not claim that the
plugin runtime, evolutionary search, Shinka backend, hidden holdout,
replication service, hooks, MCP server, UI, parser stack, security properties,
or performance targets are implemented merely because their contracts exist.

## Constitution

- Foundry Kernel and Noetic Ledger own canonical state, authority, receipts,
  gates and replay.
- Plugin shells, hooks, skills, UIs, model SDKs, and optional search backends
  are adapters.
- Source evidence, RunSpec, policy, evaluator, holdout, promotion gates, and
  release state are never mutable genomes.
- Evolution may propose; it may not certify itself.
- Novelty, fitness, evaluator survival, and model confidence are distinct from
  scientific support.
- A promoted Claim resolves to immutable source evidence.
- An Insight requires scope, prediction, falsifier, and searched-scope
  accounting.
- Counter, null, boundary, method, leakage, and OOD lanes remain visible.
- Dependency clusters prevent evidence-count inflation.
- Induction, deduction, abduction, causal identification, simulation, and
  empirical observation remain typed and separate.
- Scalar fitness cannot override hard gates or become the promotion authority.
- Evaluator bundles are immutable within a run.
- Holdouts remain access-controlled; leakage creates invalidation, not a score.
- Adaptive search requires a sequential-testing ledger, multiplicity policy,
  and selective-inference report.
- Quality-diversity archives preserve negative knowledge, failed replications,
  unsafe candidates, and minority lineages where policy permits.
- Prompt and evaluator mutations are quarantined future-run proposals.
- Majority vote cannot promote.
- Method/safety veto and failed deterministic gates constrain promotion.
- Every effect and completion claim requires resolving receipts.
- `UNDERDETERMINED`, `UNASSESSED`, `BLOCKED`, `INVALIDATED`, and
  `REPLICATION_FAILED` are valid truthful outcomes.

## Work-package protocol

1. Select the earliest dependency-ready package from
   `manifests/development_manifest.yaml`.
2. Read exact dependencies, write scope, criteria, checks, and stop conditions.
3. Inspect the current repository and preserve unrelated user changes.
4. Freeze shared contracts before parallel work.
5. Use only bounded roles from `manifests/role_registry.yaml`.
6. Parallel writers require disjoint scopes and isolated worktrees; default
   implementation concurrency is four.
7. Implement the smallest change satisfying the package contract.
8. Use deterministic code for routing, transforms, hashing, policy, statistics,
   archive bookkeeping, state transitions, and gates.
9. Use model judgment only for bounded semantic tasks with typed input/output.
10. Run required checks and capture command outputs as immutable artifacts.
11. Dispatch a reviewer who did not author the change.
12. Integrate only after all non-waivable criteria pass.
13. Emit a `WorkPackageReport`; never substitute narrative confidence.

## Evolution work

Before running or implementing an evolution node, verify:

- immutable `EvolutionRunSpec` and `EvaluatorBundle`;
- genome schema and compatibility rules;
- parent-selection and model-routing receipts;
- novelty state including `UNASSESSED` and `FAILED`;
- hard validation cascade and budget;
- hidden/OOD access boundary;
- archive and island policy;
- complete candidate reconciliation;
- adaptive-search statistical policy;
- stop certificate conditions.

The same context may not generate a candidate, reveal the hidden holdout, alter
the evaluator, and promote that candidate.

## ShinkaEvolve adapter

The adapter is optional. Pin an exact upstream revision/package digest,
license record, configuration, and backend qualification result. Treat raw
Shinka `combined_score`, `correct`, novelty, island, archive, and bandit state
as advisory backend observations. Map them through Foundry contracts before
they can influence a Passport or promotion.

## Stop conditions

Stop with a typed blocker when:

- a required source, evaluator, holdout, corpus license, credential, or
  infrastructure is unavailable;
- a shared contract must change outside the current write scope;
- hidden-test leakage or evaluator mutation is detected;
- multiplicity or selective-inference policy is undefined;
- candidate/result counts cannot be reconciled;
- the only path requires fake evidence, silent fallback, or weakened gates;
- repeated review exposes an unresolved product or scientific decision.
