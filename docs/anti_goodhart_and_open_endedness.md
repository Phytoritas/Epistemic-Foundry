# Anti-Goodhart and Open-Endedness Contract

## 1. Threat model

An open-ended search can overfit:

- scalar objective;
- public tests;
- stable grader language;
- evaluator bugs;
- archive replacement rules;
- mutation prompt style;
- model routing reward;
- stopping criteria;
- human preference proxies.

v4 counters this by separating search utility from promotion authority.

## 2. Defense layers

1. hard constraints before objectives;
2. vector fitness with uncertainty;
3. quality-diversity niches;
4. hidden time/OOD/adversarial evaluation;
5. Red Queen challenge co-evolution;
6. evaluator metamorphic tests;
7. delayed reward for bandits;
8. prompt/evaluator mutation quarantine;
9. adaptive-search statistical correction;
10. independent replication and Parliament;
11. negative-result archive;
12. evaluator rotation after exposure budget.

## 3. Challenge co-evolution

The challenge population must remain diverse and relevant. It is itself evaluated for:

- reproduction rate;
- distinct attack surface;
- boundary-discovery value;
- false-refutation rate;
- safety;
- transfer to unseen candidates;
- overfit to one candidate lineage.

A challenge that succeeds only by exploiting undefined I/O but says nothing about the claim is archived as an engineering defect, not scientific refutation.

## 4. Open-endedness without infinite search

Dynamic islands and mutation portfolios can expand when niches stagnate. Expansion requires:

- a documented uncovered epistemic region;
- budget headroom;
- a new operator or scope rationale;
- a bounded trial;
- a stop rule;
- archive and replay integration.

The system never interprets endless candidate production as progress.

## 5. Anti-monoculture

Monitor entropy over:

- candidate lineages;
- mutation operators;
- prompts;
- providers/models;
- evidence families;
- measurement methods;
- scientific mechanisms;
- scope classes.

Threshold breaches trigger migration, exploration or pause, not automatic promotion of diversity for its own sake.
