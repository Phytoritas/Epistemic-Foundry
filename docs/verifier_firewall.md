# Verifier Firewall

## 1. Why the verifier is the highest-risk component

Evolution optimizes whatever is repeatedly scored. Even a scientifically motivated metric can become a proxy target. The population may exploit implementation bugs, data leakage, an unmodeled corner case, a weak test distribution or a linguistic grader. The verifier must therefore be treated like a calibrated scientific instrument with a protected trust domain.

## 2. Sealed EvaluatorBundle

Before candidate generation, the run binds:

- evaluator code and dependencies;
- metric definitions and directions;
- environment/container digest;
- public training/evaluation fixtures;
- hidden/OOD/challenge manifests;
- policy bundle and capability limits;
- metamorphic tests;
- calibration/gold set references;
- disclosure policy;
- exact content hash.

`mutable_during_run=false` is non-waivable. Any change creates a new bundle and a new run.

## 3. Trust domains

```text
Candidate domain:
  genomes, public evidence, public feedback, public metrics

Evaluator domain:
  evaluator bytes, hidden data, private metrics, access logs

Governance domain:
  evaluator qualification, approvals, release and re-assessment
```

Candidate-generating roles cannot mount evaluator/holdout storage, inspect private logs, query hidden metadata or authorize evaluator changes.

## 4. Qualification cascade

1. supply-chain and active-content scan;
2. construct-validity audit;
3. leakage audit across prompt/context/cache/embedding/log/tool surfaces;
4. deterministic and crash behavior;
5. metamorphic invariants;
6. adversarial reward-hacking fixtures;
7. false-positive/false-negative gold comparisons;
8. calibration and OOD analysis;
9. distributional/domain bias analysis;
10. independent review;
11. human/policy approval;
12. content-addressed seal.

A failure yields `REJECTED` or a lower release ceiling, not narrative acceptance.

## 5. Hidden holdout policy

Holdouts are segmented by time, domain/scope and adversarial strata. Candidate access is `NONE`, `METADATA_ONLY` or `AGGREGATE_ONLY`; the default is `NONE`. Exposure counts are tracked and trigger rotation. Unblinding happens only after run freeze and promotion decision.

## 6. Evaluator defect handling

A candidate may reveal that the evaluator is wrong. It submits an `EvaluatorMutationProposal` with reproducible evidence. The current run remains unchanged. A shadow evaluator is built, qualified and backtested. Approved changes apply to future runs. Prior artifacts may be explicitly reassessed under a new run, never silently rewritten.

## 7. Metamorphic and adversarial checks

Depending on domain, the evaluator should verify:

- invariance to irrelevant formatting or identifier changes;
- monotonicity under known physical/logical transformations;
- stability across seeds and environments;
- conservation or dimensional constraints;
- sensitivity to known true and false cases;
- resistance to output spoofing and file injection;
- correct handling of missing/partial results;
- no reward for unsafe shortcuts.

## 8. Promotion implication

Passing an evaluator means only “passed this qualified evaluation bundle.” It is not empirical confirmation, causal identification or global novelty. Evidence class and scope remain explicit.
