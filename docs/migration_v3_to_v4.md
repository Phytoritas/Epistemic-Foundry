# Migration: Epistemic Foundry v3 → v4

## 1. Compatibility

v4 preserves v3 Claim, Evidence, FORGE, Parliament, Validation, Ledger, plugin and replay contracts. It adds typed evolution. Existing v3 runs remain valid historical records and are not rewritten.

## 2. New canonical objects

- Hypothesis/Experiment/Challenge/Prompt genomes;
- EvolutionRunSpec and CandidateLineage;
- mutation/crossover receipts;
- evaluator bundle, qualification and holdout;
- FitnessVector and fitness evidence;
- Pareto front, niches, islands and quality-diversity map;
- model/operator bandit state;
- Red Queen rounds and results;
- sequential testing, multiplicity and selective inference;
- replication plan/result;
- promotion decision and stop certificate;
- Shinka backend manifest/qualification;
- evolution checkpoint.

## 3. Migration steps

1. freeze v3 store and create backup;
2. deploy v4 schemas in additive mode;
3. map each v3 Insight/Hypothesis Passport to a non-evolving seed genome where eligible;
4. preserve v3 artifact IDs and create linkage, not replacement;
5. create default evaluator status `NOT_QUALIFIED`;
6. create no hidden holdout until governed data is available;
7. create archive entries for v3 promoted, rejected, null and minority artifacts;
8. generate niche assignments as projections;
9. enable read-only v4 inspection;
10. qualify evaluator and sandbox;
11. run shadow EVOLVE on gold fixtures;
12. enable mutation in PLUGIN_ALPHA only after gates pass.

## 4. Non-automatic mappings

The following require expert review:

- free prose to MechanismGraph;
- implicit falsifier to observable decision rule;
- v3 score/confidence to FitnessVector;
- old validation data to hidden holdout;
- local novelty to external prior-art status;
- same-run reruns to independent replication;
- legacy prompt to qualified PromptGenome.

## 5. Rollback

Rollback disables v4 mutation and returns to v3 read/write behavior while preserving all v4 ledger events and artifacts. Database down-migration must not delete v4 lineage or evaluator history; use compatibility reads or archive export.

## 6. Migration acceptance

Pass requires schema validation, full count reconciliation, stable v3 replay, no altered Passport hashes, archive preservation, evaluator status honesty and independent review.
