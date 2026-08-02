# Q03-0001 primary-session separate adversarial review

- Reviewer: primary session in a separate adversarial pass under the
  product-owner instruction forbidding subagents and Fleet;
  actor_independence=false is recorded, not hidden.
- Counter and null recall are separated because that is where an
  agreement-seeking retriever fails. v1 measures supporting recall
  1.00 and null recall 1.00 while counter recall is 0.50, and the two
  missed documents are named rather than averaged away. A single
  undifferentiated recall would have read 0.85 and hidden it.
- The corpus cannot be gamed by removing the hard cases: a corpus that
  carries no counter evidence or no null result is refused as
  POLARITY_UNMEASURED rather than scored a perfect one, and a query
  with no relevant document at all is refused.
- Calibration is computed with its inputs exposed. The Brier score and
  the ECE come from the same confidence/outcome pairs, the reliability
  bins are reported, and the test re-adds the bins to recover the ECE
  rather than trusting it. v1 measures Brier 0.166 and ECE 0.305, so
  the status is WARN — the fixture is deliberately not well calibrated,
  and a PASS is proved separately on a well-calibrated variant.
- The emitted document is validated against
  calibration-report.schema.json, so what this evaluator produces is a
  CalibrationReport rather than something shaped like one, with its
  target and status read from that schema instead of restated.
- Small samples are handled honestly: below ten graded predictions the
  status is INSUFFICIENT_DATA and both statistics are null, and an
  empty reliability bin reports null rather than zero accuracy.
- UNDETERMINED is a first-class verdict, so the benchmark never forces
  a decision the evidence does not support.
- Residual limitations: the queries, relevance grades and retrieval
  results are synthetic fixtures written for this benchmark, and the
  retriever is declared synthetic with a corpus claiming otherwise
  refused, so the measured values characterise the harness rather than
  any deployed retriever; twelve graded predictions clear the
  calibration floor but are far too few to set production thresholds;
  ranking quality beyond binary recall is not measured; and this
  review is not external actor-independent certification.
