# Q02 package review record

Standing verdict: `PASS` (from attempt `0001`).

This file is the package-level projection the manifest requires. The
attempt review below, at `attempts/0001/review.md`, is the primary record.

---

# Q02-0001 primary-session separate adversarial review

- Reviewer: primary session in a separate adversarial pass under the
  product-owner instruction forbidding subagents and Fleet;
  actor_independence=false is recorded, not hidden.
- The numbers are recomputable, not announced. The report exposes the
  true/false positive and false negative counts and the exact match
  key those counts came from, and the tests re-derive precision,
  recall and F1 from them rather than trusting the reported values.
  v1 measures 0.75/0.75/0.75 over eight gold and eight predicted
  claims.
- Unsupported promotion is measured separately on purpose. Folding it
  into precision would let a system that invents evidence strength
  hide behind a good F1, so a matched claim whose gold layer is
  unsupported and whose prediction is stronger is counted by name: v1
  names PC-003 and PC-004, two of six matches. With no matched pair
  the rate is reported undefined rather than a flattering zero.
- The corpus is built where parsers actually fail. Ten spans cover
  table cells, figure captions, an equation and running prose across
  two documents and two pinned parsers; two gold claims are grounded
  only in a table cell and two only in a figure caption, and the
  evaluator refuses a corpus that drops either. One span records a
  parser conflict and one a human resolution, so disagreement is
  retained rather than smoothed away.
- Grounding is verified against the canonical contract, not a local
  restatement: every span is validated with jsonschema against
  source-span.schema.json, its text_hash is recomputed from the
  verbatim bytes, and the claim vocabularies are read from
  claim-card.schema.json. A claim citing an absent span, citing no
  span, or whose text does not appear in a cited span is refused.
- The extractor is declared synthetic and the evaluator refuses a
  corpus that claims otherwise, so v1's scores can never be read as a
  measurement of a real parser.
- Residual limitations: the documents are synthetic fixtures written
  for this benchmark rather than real papers; the predictions are a
  fixture, so the measured values characterise the harness and not any
  deployed extractor; exact match on subject/relation/object/direction
  is a strict identity that will under-credit paraphrase, which a
  later semantic-matching package would address; and calibration and
  verdict evaluation belong to Q03. This review is not external
  actor-independent certification.
