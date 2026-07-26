# v4 Evaluation and Benchmark Program

## Release ladder

```text
SPEC_BUNDLE
→ PLUGIN_ALPHA
→ EVOLUTION_MVP_50
→ PILOT_200
→ PRODUCTION_2000
→ CROSS_DOMAIN_QUALIFIED
```

## Gold assets

Minimum MVP:

- 50 licensed documents;
- 200 source-span Claim labels;
- 30 known hypothesis cases;
- 10 known-false or refuted cases;
- 10 boundary-condition cases;
- 10 evaluator-gaming fixtures;
- 10 leakage fixtures;
- 10 replication cases;
- 5 domains/niche axes when testing domain neutrality.

## Comparative baselines

- single-agent hypothesis generation;
- v3 Parliament without evolution;
- scalar best-of-N;
- Shinka-style executable search with one public evaluator;
- Pareto without Red Queen;
- quality-diversity without hidden holdout;
- full v4.

## Metrics

### Discovery
- valid/falsifiable candidate rate;
- unique mechanism/prediction/niche coverage;
- expected and realized information gain;
- rediscovery rate;
- external prior-art false novelty rate.

### Validation
- known-false rejection;
- hidden/OOD predictive accuracy;
- calibration/Brier/ECE;
- counter/null/boundary recall;
- false promotion;
- replication rate;
- causal overclaim.

### Evolution integrity
- candidate count reconciliation;
- lineage completeness;
- novelty outage type accuracy;
- evaluator/holdout leakage;
- reward-hacking success rate;
- archive negative-memory retention;
- lineage/operator/model entropy;
- checkpoint recovery.

### Statistical integrity
- false discovery under adaptive search;
- coverage of corrected intervals;
- alpha/e-value budget compliance;
- winner's-curse reduction.

### Operations
- cost per validated candidate;
- wall-clock per generation;
- queue/backpressure behavior;
- crash/recovery;
- provider failure/fallback;
- sandbox violations.

## Time-sliced backtesting

Freeze literature and datasets before a cutoff, evolve hypotheses, and compare with later outcomes. Publication bias and missing future studies remain explicit limitations.

## Success claim rule

The system may claim improvement only on preregistered baselines, hidden test design, confidence intervals and cost. “World best” is a research objective, not a release status.
