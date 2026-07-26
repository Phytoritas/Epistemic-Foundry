# Epistemic Foundry v4 — Evolution-Governed Hypothesis Discovery Architecture

## 1. Thesis

v4 adds an **Evolution Chamber** to Epistemic Foundry. The Chamber searches over typed scientific objects; it does not own truth.

```text
Evolution authority:
  propose → mutate → cross → challenge → prioritize → archive

Non-evolvable authority:
  source evidence → current RunSpec → current evaluator → hidden holdout
  → safety/provenance gates → statistical policy → promotion → release
```

This asymmetry is the central safety and scientific-integrity property. A search system is rewarded for finding candidates that score well. Therefore any evaluator, prompt, policy or hidden fixture exposed to the candidate population becomes a target for optimization. v4 treats the verifier as a protected scientific instrument.

## 2. Two nested protocols

### FORGE research lifecycle

```text
Interview(optional) → Frame → Observe → Reason → Gate → Export/Evolve
```

FORGE still governs the research session and the final Hypothesis Passport.

### EVOLVE search subprotocol

```text
Encode → Vary → Oppose → Learn → Validate → Elevate
```

- **Encode:** materialize typed seed genomes and immutable run/evaluator contracts.
- **Vary:** apply bounded mutation or compatibility-gated crossover.
- **Oppose:** expose candidates to Red Queen falsifier/challenge populations.
- **Learn:** update FitnessVectors, Pareto front, epistemic niches, lineages and operator/model bandits.
- **Validate:** run hidden/OOD stages, adaptive-search statistics and independent replication.
- **Elevate:** request Evidence Parliament promotion; evolution itself cannot grant it.

Every EVOLVE edge emits a typed artifact or receipt. Return edges preserve old revisions and mark dependent artifacts stale.

## 3. Evolvable object model

### 3.1 HypothesisGenome

A hypothesis is not a prose string. It contains:

- canonical claim and ScopeVector;
- MechanismGraph and explicit assumptions;
- one or more observable PredictionGenes;
- one or more FalsifierGenes;
- competing hypotheses;
- measurement/construct contracts;
- current Evidence Pack reference;
- causal-identification status;
- preregistered ValidationPlan;
- complexity budget and uncertainty;
- immutable CandidateLineage.

A mutation changes only declared JSON paths. Source evidence and parent history are immutable.

### 3.2 ExperimentGenome

An experiment or analysis candidate states intervention/exposure, comparator, outcomes, controls, sample/compute budget, risks, information gain and a validation plan. Its objective is discrimination among hypotheses, not merely finding significance.

### 3.3 ChallengeGenome

The Red Queen population searches for:

- counterexamples and null models;
- common causes and reverse causation;
- measurement artifacts and method failures;
- boundary/scope shifts;
- OOD failures;
- hidden-test leakage;
- replication failures;
- adversarial executable inputs.

Challenges must be relevant, safe and reproducible. An irrelevant exploit does not refute a scientific claim.

### 3.4 PromptGenome

Mutation prompts may evolve only in quarantine. They have explicit allowed context, forbidden authority, lineage, fitness history and status. They cannot read holdout content or modify the active evaluator. Approval affects future runs only.

## 4. Candidate populations

A run may maintain separate populations:

1. hypothesis population;
2. mechanism/model population;
3. challenge/falsifier population;
4. experiment/probe population;
5. measurement/operationalization population.

They share the same Noetic Ledger but have separate schemas, mutation operators, niches, budgets and promotion rules.

## 5. Mutation operator taxonomy

| Class | Example mutation | Required audit |
|---|---|---|
| scope | move population, setting or time scale | scope transfer |
| mechanism | add/remove mediator or moderator edge | causal and temporal |
| prediction | sharpen direction/range/horizon | observable validity |
| falsifier | replace rhetorical disproof with decision rule | feasibility |
| alternative | add common-cause or reverse-causal explanation | evidence relevance |
| measurement | substitute proxy or method | construct/unit/error |
| causal | edit DAG or identification assumptions | collider/confounder |
| scale transfer | component → system, acute → chronic | invariance |
| method transfer | import adjacent-domain mechanism | ontology compatibility |
| contradiction resolution | introduce minimum moderator | competing predictions |
| simplification | remove unnecessary state/edge | explanatory sufficiency |
| crossover | combine two compatible genomes | four compatibility reports |

The operator registry declares preconditions, preserved invariants, prompt reference, risk and audits. Operators are versioned and content-addressed.

## 6. Typed crossover

Crossover is prohibited until four questions are answered:

1. Are the scopes compatible or explicitly branched?
2. Are measurement constructs and methods compatible or stratified?
3. Are units identical or validly convertible?
4. Can causal assumptions coexist without contradiction?

The child must make a prediction not obtainable from either parent alone. Copy-pasting two fluent explanations is semantic collage and is rejected.

## 7. Multi-objective fitness

`FitnessVector` has a hard-gate layer and uncertainty-bearing dimensions.

Hard gates include:

- schema and lineage validity;
- source/evidence provenance;
- falsifiability and observable predictions;
- evaluator/holdout isolation;
- no unsafe capability or policy violation;
- method/construct validity floor;
- budget and effect-receipt completeness.

Soft dimensions include:

- grounding and direct support;
- resistance to counterevidence;
- predictive accuracy and calibration;
- robustness/OOD survival;
- causal identifiability;
- falsifiability;
- multi-layer novelty;
- parsimony;
- expected/realized information gain;
- coverage-debt reduction;
- replicability;
- cost efficiency;
- safety/ethics.

No weighted scalar may grant promotion. Pareto rank and niche placement guide search; the final gate remains external.

## 8. Quality-diversity search

v4 uses an epistemic MAP-Elites concept. A default niche key is:

```text
mechanism family
× scope class
× evidence state
× testability band
× causal status
```

DomainPacks may add axes. Each cell can retain multiple trade-off candidates plus protected negative entries. Coverage debt raises parent/experiment priority.

## 9. Parent selection

The `ParentSelectionReceipt` records the complete eligible set and acquisition components:

```text
expected information gain
+ uncertainty
+ coverage debt
+ replication debt
+ challenge survival
- lineage saturation
- cost/risk penalty
```

Random seeds, policy version and selected parents are explicit. Selection is a search decision, not a verdict.

## 10. Model/operator bandit

A safe UCB/Thompson policy may route mutation work. Reward has two time scales:

- immediate proxy: valid, nonduplicate, low-cost candidate;
- delayed scientific utility: hidden-stage improvement, challenge survival, calibration and replication.

Safety violations, leakage and unreconciled effects are negative/terminal observations. Model/provider diversity is measured rather than assumed.

## 11. Evolution cycle

The canonical workflow performs:

1. validate EvolutionRunSpec;
2. seal evaluator and holdout;
3. bootstrap typed populations;
4. map niches and lineage diversity;
5. select parents, operators and models;
6. generate hypotheses, experiments and challenges in parallel;
7. validate genomes and crossover compatibility;
8. run cheap contract/static stages;
9. retrieve balanced evidence and prior art;
10. run evidence/simulation/adversarial stages;
11. compute novelty and FitnessVectors;
12. update Pareto front and niche archive;
13. run Red Queen matches;
14. apply adaptive-search statistics;
15. run hidden/OOD and independent replication;
16. request Parliament promotion;
17. issue Passport revisions;
18. evaluate stop conditions and checkpoint.

## 12. Stop and convergence

A loop stops or pauses on:

- hard budget or capability loss;
- safety, leakage or integrity failure;
- max candidates/generations;
- configured dry rounds with no novel eligible candidate;
- Pareto hypervolume stability;
- coverage saturation;
- challenge/hypothesis co-evolution stagnation;
- human stop;
- irreducible blocker.

`EvolutionStopCertificate` records partial candidates, missing workers and unassessed niches. Stopping is not equivalent to scientific convergence.

## 13. Maturity boundary

This document specifies target behavior. The reference plugin blueprint remains fail-closed until implementation packages and release gates pass.
