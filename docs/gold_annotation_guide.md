# Gold Corpus Annotation Guide v1.1

## Purpose

Gold annotation is not general document summarization. It creates a defensible benchmark for:
- atomic Claim detection
- exact source grounding
- domain-neutral ScopeVector extraction
- method/construct compatibility
- evidence-layer assignment
- contradiction/boundary classification
- dependency-family detection
- false-insight rejection

## Unit of annotation

One item is:
```text
one atomic proposition
+ one or more exact source spans
+ author stance
+ scope
+ method
+ quantitative context
+ evidence layer
```

A sentence can contain multiple claims. One claim can require paragraph plus caption,
table, appendix, or supplementary-method spans.

## Section policy

Priority:
1. Results or findings plus linked figure/table
2. Methods for design and measurement
3. Discussion for interpretation, boundary, and limitation
4. Abstract as index only
5. Background prose as low-evidence literature statement

Background or review prose cannot be labeled direct measurement unless it points to
and is reconciled with a primary observation or experiment.

## Atomicity

Split when propositions can differ in truth value.

Bad:
> The intervention improved accuracy and confidence, reduced completion time, and proved that deeper processing caused the benefit.

Possible splits:
- the intervention improves accuracy
- the intervention increases reported confidence
- the intervention reduces completion time
- deeper processing mediates the accuracy effect
- the authors interpret the pattern as evidence for deeper processing

The last two require different evidence and stance from the first three.

## Source locator

Record:
- document version
- page
- section
- character range
- bounding box when available
- passage hash
- linked table, figure, cell, appendix, or supplementary item

Highlight enough context to preserve comparator, direction, uncertainty, and
conditions, but do not copy entire pages.

## ScopeVector

Annotate reported values; use `null` or `unknown` rather than infer:
- domain
- population or entity
- entity subtype
- unit of analysis
- setting, geography, jurisdiction, and language
- lifecycle stage where relevant
- spatial and temporal scale
- intervention or exposure
- comparator
- inclusion and exclusion criteria
- measurement time
- material conditions
- domain-extension fields governed by the active DomainPack

Do not add a domain-specific core field. New specialist axes belong in
`domain_extensions` and must be declared by a versioned DomainPack.

## Author stance

Use the canonical schema vocabulary:
- asserted
- supported
- suggested
- speculative
- qualified
- negated
- unclear

Do not convert “may”, “suggests”, or “could” into a supported mechanism.

## Evidence layer

Use the canonical schema vocabulary:
- direct_measurement
- primary_analysis
- modeling
- formal_derivation
- benchmark_execution
- review
- background
- unsupported

Evidence layer is not a single universal quality ranking. Directness, design strength,
measurement validity, precision, replication, independence, and scope match remain
separate QualityVector fields.

## Method compatibility

Record:
- latent construct intended
- operational measurement
- instrument, protocol, or analysis
- temporal and spatial support
- calibration or quality control
- direct versus proxy status
- known limitations

Two measurements with the same label are not automatically exchangeable.

## Contradiction labels

- TRUE_CONTRADICTION
- SCOPE_DIFFERENCE
- BOUNDARY_CONDITION
- METHOD_DIFFERENCE
- TEMPORAL_DIFFERENCE
- MEASUREMENT_ARTIFACT_CANDIDATE
- DIFFERENT_QUESTION
- INSUFFICIENT_INFORMATION

## Dependency labels

- same experiment or execution
- same dataset or sample
- preprint and final publication
- review and primary citation
- reanalysis
- same source family continuation
- independent

A shared organization alone does not prove dependency; document the actual link.

## Negative controls

At least 10 benchmark insights must be known false, unsupported, reversed,
method-incompatible, or overgeneralized. The benchmark must penalize an agreeable
“supported” answer.

## Annotation process

1. annotator A independent
2. annotator B independent
3. machine comparison
4. adjudicator resolves
5. guideline updated only with a new version
6. frozen test set hidden from prompt and pipeline tuning

## Quality checks

- every Claim has an immutable SourceSpan
- no orphan page or bounding box
- extracted text hash matches
- units normalize without changing the original
- nulls distinguish absent from not reported
- reviewer agreement reported by field
- adjudication reason retained
- domain-specific fields are declared by the pinned DomainPack
