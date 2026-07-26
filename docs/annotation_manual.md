# Gold-corpus annotation and adjudication manual

## Purpose

The gold corpus evaluates claim atomicity, source grounding, scope extraction, author stance, evidence class, relation direction, counter/null/boundary retrieval, measurement compatibility, dependency clustering and final verdict calibration.

## Unit of annotation

The primary unit is a candidate Claim paired with immutable SourceSpan locators. Papers, abstracts and paragraphs are context, not the annotation unit.

## Annotator workflow

1. Confirm the source version and page/character/table/figure locator.
2. Mark whether the span states, implies, speculates about, limits or contradicts the candidate Claim.
3. Split compound propositions until each Claim has one principal relation.
4. Record scope, population/entity, exposure/intervention, comparator, outcome, time and setting.
5. Record measurement construct, method, unit, protocol and statistical context.
6. Label direct, indirect, model, review-derived, introduction-only or unsupported evidence.
7. Mark shared dataset/experiment/version dependencies.
8. Record uncertainty and an explicit abstention reason where adjudication is impossible.
9. Never repair source text or infer missing quantitative values.

## Independence and adjudication

- Two trained annotators independently label promoted-evaluation items.
- Disagreements are hidden until both submissions are sealed.
- A third adjudicator resolves disagreements with a written rationale.
- Annotators disclose authorship, laboratory, financial and topic conflicts.
- Agreement is reported per field; aggregate agreement cannot hide poor source-span or contradiction labels.
- Thresholds are fixed before scoring and stored in the evaluation snapshot.

## Required challenge sets

- known-false and overgeneralized claims;
- author speculation presented as fact;
- review-primary citation laundering;
- same-dataset publication families;
- true contradiction versus scope/method/time difference;
- null and unpublished-looking negative language;
- tables, figures, captions and formulas;
- multilingual and malformed layouts;
- prompt-injection text embedded in sources;
- correction, retraction and version-replacement cases.

## Release rule

Gold labels, adjudication rationales and holdout identities remain sealed from systems under evaluation. Production thresholds remain conditional until domain experts approve a real annotated set.
