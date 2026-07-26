# Evolution Chamber UI/UX Contract

## Primary views

1. **Run Charter** — objective, scope, evaluator hash, holdout status, budgets, statistical family and stop rules.
2. **Species Map** — epistemic niche grid with occupied, sparse, stagnant and unsearched cells.
3. **Pareto Studio** — selectable objective axes, uncertainty and hard-gate overlays.
4. **Lineage Graph** — parent/inspiration/operator/model ancestry and branch outcomes.
5. **Red Queen Arena** — challenge classes, survival, refutation, boundary and replication status.
6. **Verifier Firewall** — evaluator qualification, leakage, calibration, exposure budget and version.
7. **Replication Board** — plans, independence, deviations, heterogeneity and promotion effects.
8. **Archive Vault** — elites, nulls, counterexamples, failed replications, unsafe and minority entries.
9. **Operator Console** — pause/resume/stop, budget, concurrency and approvals.
10. **Promotion Docket** — sealed pack, Parliament, statistics, replication and Passport decision.

## Honest visual semantics

- hard failure is not hidden by a high score;
- hidden holdout status is shown without content;
- unsearched, searched-none, failed and unavailable are distinct;
- estimated and realized cost are separate;
- proxy, public, hidden and replication metrics are labeled;
- partial/missing workers remain visible;
- novelty and support use different encodings;
- UI backend outage never renders as empty archive;
- no default sort by one combined score.

## Accessibility and scale

All graph views have table alternatives, keyboard navigation, text summaries and stable IDs. Large populations use aggregation and drill-down, never a single unreadable node cloud.
