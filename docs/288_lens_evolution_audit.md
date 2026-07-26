# 288-Lens Evolution Architecture Audit

This is a structured **24 failure-surface × 12 contract-lens** specification audit. It is not 288 independent agents, reviewers, experiments, or proofs.

**Result:** 264 PASS / 24 CONDITIONAL / 0 FAIL.

| Family | Focus | PASS | Conditional | Fail |
|---|---|---:|---:|---:|
| A — Evolution authority | Can the search layer acquire evidence, evaluator, policy, holdout, promotion, or release authority? | 11 | 1 | 0 |
| B — Genome semantics | Are scientific candidates typed, falsifiable, scoped, measurable, and lineage-bound? | 11 | 1 | 0 |
| C — Mutation and crossover | Do operators preserve invariants and reject incompatible semantic crossover? | 11 | 1 | 0 |
| D — Fitness and Pareto | Are hard gates, uncertainty, multi-objective trade-offs, and no-scalar promotion enforced? | 11 | 1 | 0 |
| E — Quality-diversity archive | Are epistemic niches, negative memory, migration, and replacement scientifically governed? | 11 | 1 | 0 |
| F — Parent selection and bandits | Are acquisition, delayed reward, cost, safety, and diversity receipts complete? | 11 | 1 | 0 |
| G — Novelty and prior art | Are multi-layer novelty, search completeness, failure typing, and truth separation enforced? | 11 | 1 | 0 |
| H — Verifier Firewall | Are evaluator validity, immutability, calibration, gameability, and future-only updates governed? | 11 | 1 | 0 |
| I — Holdout and leakage | Are hidden/OOD assets isolated across prompts, tools, caches, logs, embeddings, and backends? | 11 | 1 | 0 |
| J — Red Queen challenges | Are challenges relevant, safe, diverse, replicated, and audited for overfit? | 11 | 1 | 0 |
| K — Adaptive-search statistics | Are sequential testing, multiplicity, selection bias, and winner's curse addressed? | 11 | 1 | 0 |
| L — Replication | Is replication preregistered, independent, complete, heterogeneous, and promotion-linked? | 11 | 1 | 0 |
| M — Async execution | Are queues bounded and proposed/evaluated/persisted/failed/missing identities reconciled? | 11 | 1 | 0 |
| N — State, checkpoint, replay | Are population, archive, bandit, budget, testing and evaluator state atomically replayable? | 11 | 1 | 0 |
| O — Security and sandbox | Are candidate code, skills, providers, effects, secrets, and egress zero-trust? | 11 | 1 | 0 |
| P — Shinka backend adapter | Is the optional backend pinned, mapped, isolated, qualified, and non-authoritative? | 11 | 1 | 0 |
| Q — Plugin skills and UX | Do skills route minimally and does UI expose truthful state, gaps, and degraded modes? | 11 | 1 | 0 |
| R — Provider and model routing | Are adapters neutral, model errors visible, diversity measured, and reward delayed? | 11 | 1 | 0 |
| S — Evidence integration | Do evolved candidates remain source-grounded with coverage, method, dependency, and evidence-class controls? | 11 | 1 | 0 |
| T — Parliament and promotion | Can hard gates, veto, statistics, replication, strongest challenge, and minority reports constrain promotion? | 11 | 1 | 0 |
| U — Domain neutrality | Can DomainPacks extend semantics without coupling core to one model, discipline, or ontology? | 11 | 1 | 0 |
| V — Cost, scale, operations | Are budgets truthful, multi-fidelity evaluation bounded, and production load measurable? | 11 | 1 | 0 |
| W — Migration, release, supply chain | Are v3 history, schema evolution, builds, manifests, signing, install, rollback and uninstall governed? | 11 | 1 | 0 |
| X — Evaluation and benchmark | Are baselines, gold sets, time-sliced/OOD tests, ablations, calibration and success language adequate? | 11 | 1 | 0 |

## Conditional meaning

Each family retains one production-evidence conditional. A specification can define a control but cannot prove real corpus quality, leakage resistance, crash recovery, operator usability, cross-platform installation, security, statistical calibration, or discovery performance before implementation and measured evaluation.
