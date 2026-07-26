# Statistical Governance for Adaptive Hypothesis Evolution

## 1. Why ordinary p-values are insufficient

Evolution observes results, selects winners and generates related candidates repeatedly. The selected best estimate is upward biased. Reusing a holdout leaks information through aggregate feedback. Candidate families are dependent. v4 treats search as adaptive sequential inference.

## 2. Required ledgers

- candidate family and lineage;
- every test and generation;
- public/private metric exposure;
- selection events;
- stopping events;
- alpha/e-value spending;
- multiplicity adjustment;
- hidden-set exposure count;
- final selected candidate;
- bias-correction method.

## 3. Supported policies

A DomainPack chooses a justified method:

- fixed-horizon nested holdout;
- alpha-spending or alpha-investing;
- e-values/e-processes;
- Bayesian sequential monitoring;
- FDR controls for candidate families;
- hierarchical testing;
- selective-inference or bootstrap correction after selection.

`none_justified` requires an explicit non-inferential use and imposes a promotion ceiling.

## 4. Nested evaluation

Recommended split:

```text
public development → internal validation → hidden time/OOD → independent replication
```

Model/operator bandits update on delayed hidden/replication signals only within exposure budgets. The final effect estimate comes from a layer not used to choose the candidate whenever feasible.

## 5. Winner's curse

The `SelectiveInferenceReport` records:

- number/effective number of candidates;
- selection mechanism;
- naive estimate;
- bias-corrected estimate;
- uncertainty;
- winner's-curse risk;
- recommendation: allow, replicate first, lower or block.

## 6. Null and negative results

Nulls and failed replication remain in the archive, reduce repeated testing and inform priors. They are not silently dropped because they lower fitness.

## 7. Reporting language

The system distinguishes:

- search performance;
- held-out predictive performance;
- evidence support;
- causal identification;
- independent replication;
- scientific promotion.

No one metric substitutes for another.
