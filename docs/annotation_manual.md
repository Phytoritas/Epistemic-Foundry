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

## Bound corpus: `evals/gold/insight_gold_cases.json`

The sections above govern annotation generally. This section is the executable
contract for the one corpus that ships with the repository. The corpus cites
this file by path and `evals/gold/validator.py` refuses a corpus that cites
anything else, so a label set can always be traced to the rules it was produced
under.

### The three case classes

A benchmark containing only clear positives measures nothing: a system that
answers "yes" to everything scores perfectly on it. The corpus therefore
requires at least three cases of each class, and the validator fails a corpus
thin in any one of them rather than reporting a high score on a corpus that
could not have discriminated anything.

`TRUE_INSIGHT` — the claim is supported by what the source actually measured,
within the scope the source states. Being interesting is not a marker, and
neither is being correct in the annotator's opinion: the question is whether the
source supports the claim, not whether the claim is true.

`FALSE_INSIGHT` — the claim is not supported by what the source measured,
whatever the source asserts. A causal mechanism asserted in an abstract that the
results never measure, review prose presented as direct measurement, and
incompatible methods pooled into one average all belong here.

`BOUNDARY` — the claim holds under a condition the source itself names, and the
source is explicit that it does not hold, or has not been checked, outside it. A
boundary case must state that condition in `boundary_condition`; the validator
refuses one that does not. This requirement exists because "boundary" is
otherwise a comfortable label for anything hard: an annotator who cannot name
the condition is looking at a supported or unsupported case, not a boundary.

### Standing rule: scope jump versus boundary

If a conclusion reaches past the stated inclusion criteria:

- the source **names** the limiting condition → `BOUNDARY`;
- the source **does not name** it → `FALSE_INSIGHT`.

This rule decides `GC-false-004` and `GC-boundary-004`, the two adjudicated
cases in corpus v1.0.

### Adjudication record

The general rule above — two independent annotators, a third adjudicator, a
written rationale — is enforced here as a record shape:

1. The adjudicator must be neither annotator; the validator refuses an
   adjudication signed by an annotator on the same case.
2. The `resolution` is one canonical value: `ANNOTATOR_A_CORRECT`,
   `ANNOTATOR_B_CORRECT`, `NEITHER_CORRECT`, or `GUIDANCE_AMBIGUOUS`. The last
   means this manual does not decide the case: the case is still resolved, but
   the resolution is a signal that the manual needs a rule, not that the
   annotators were careless.
3. The `reason` cites the rule applied.
4. The `gold_label` is the label that survived adjudication.

A unanimous case must carry no adjudication record. An adjudication with nothing
to adjudicate makes the corpus look more scrutinised than it is.

### Measured agreement

Agreement is measured, not asserted. The validator computes Fleiss' kappa over
the raw annotations and reports the observed and expected agreement it derives
from, so a reader can recompute the coefficient rather than take it on trust.

- The corpus declares a `kappa_floor`; a floor weaker than the contract floor of
  `0.60` is refused.
- A kappa below the declared floor fails the corpus. Labels two trained
  annotators cannot reproduce are not a benchmark.
- A corpus in which every annotation used one label has no variance to measure.
  It is reported as undefined and refused rather than as perfect agreement:
  unanimity across a single-label corpus means the corpus is degenerate, not
  that the annotators were exceptional.

Corpus v1.0 measures kappa = 0.749 over 12 cases and 2 raters.

### What this section does not do

It does not judge whether a claim is true in the world, only whether the source
supports it. It does not resolve disagreement by majority — two annotators
cannot form one, and adding a third to vote would replace adjudication with a
poll. It does not permit a label to change after adjudication without a new
adjudication record.
