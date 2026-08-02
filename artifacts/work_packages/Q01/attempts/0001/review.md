# Q01-0001 primary-session separate adversarial review

- Reviewer: primary session in a separate adversarial pass under the
  product-owner instruction forbidding subagents and Fleet;
  actor_independence=false is recorded, not hidden.
- All three classes are required, not merely present. A benchmark of
  clear positives measures nothing: a system that answers yes to
  everything scores perfectly on it. The validator therefore fails a
  corpus that is missing or thin in true, false, or boundary cases
  rather than reporting a high score on a corpus that could not have
  discriminated anything. v1.0 carries four cases of each class.
- A boundary case must name the condition that makes it a boundary,
  because 'boundary' is otherwise a comfortable label for anything
  hard. A non-boundary case may not carry one, so the field cannot be
  used decoratively.
- Adjudication is a record, not a convention. Every case carries at
  least two independent annotations; a disagreement without an
  adjudication fails, an annotator may not adjudicate its own
  disagreement, the resolution must be canonical, the reason must cite
  the rule applied, and a unanimous case may carry no adjudication at
  all so the corpus cannot look more scrutinised than it is.
- Agreement is measured. Fleiss' kappa is computed over the raw
  annotations and reported with the observed and expected agreement it
  derives from, so the test recomputes the coefficient from those
  inputs rather than trusting it. v1.0 measures kappa 0.749 over 12
  cases and 2 raters, against a floor of 0.60 that a corpus may not
  declare weaker.
- The degenerate case is handled honestly: a corpus in which every
  annotation used one label has no variance and is reported as
  undefined rather than as perfect agreement, and an uneven rater
  count is reported rather than averaged over.
- The corpus cites the manual it was labelled under and the validator
  refuses any other citation, so a label set can always be traced to
  its rules. The existing manual content was extended, not replaced.
- Residual limitations: the labels are the primary session's own and
  have not been validated by domain experts; the source spans are
  synthetic identifiers rather than real document locators; twelve
  cases are enough to exercise the protocol but not to set production
  thresholds, which the release rule already holds conditional; and
  calibration and scoring belong to later Q-phase packages. This
  review is not external actor-independent certification.
