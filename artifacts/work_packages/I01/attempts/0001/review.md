# I01-0001 independent review of bounded-agent work

- Author: a bounded implementation agent (disjoint write scope, frozen
  contracts) under the product owner's explicit instruction. Reviewer:
  the sealing agent, which did not author this attempt; author/reviewer
  separation holds with actor_independence=true, while external
  actor-independent certification does not.
- Only decision-critical questions surface: a question is emitted only for
  a missing decision-critical dimension or a recorded critical
  contradiction. Non-critical needs are recorded and deferred, duplicate
  needs on one dimension merge to a single stable question, and question
  order is canonical rather than input order (order-independent replay).
- Answered and known priors are never re-asked: a known fact or an
  answered prior question resolves its dimension, an open prior question is
  held pending rather than re-emitted, and a prior blocker is sticky for
  the same request revision; a new revision mints a new question identity.
- Critical contradictions are recorded and routed: every contradiction is
  preserved verbatim, a critical unresolved one routes a question, and an
  accepted-as-blocker contradiction sets an explicit blocker that is never
  silently downgraded.
- Fail-closed on adversarial input: raw-enum aliases, mutable record
  collections, duplicate identifiers, forged or mismatched prior-question
  ids, unknown prior targets, invalid disposition linkage, invalid
  revisions, and blocker mismatches each raise the exact finding code
  (INTERVIEW_INPUT_INVALID, INTERVIEW_INPUT_DUPLICATE,
  INTERVIEW_RULE_DIMENSION_MISMATCH, CONTRADICTION_DISPOSITION_INVALID,
  CONTRADICTION_EVIDENCE_REQUIRED, CONTRADICTION_BLOCKER_MISMATCH,
  PRIOR_QUESTION_ID_MISMATCH, PRIOR_QUESTION_TARGET_INVALID,
  PRIOR_QUESTION_STATE_INVALID) rather than degrading silently.
- Boundary: the engine imports the standard library alone and plans an
  interview; it does not score, rank, select, promote or evaluate any
  candidate, and C04/F04 are manifest-order dependencies, not composed
  code. The component ships under python/ and stays out of the wheel.
- Integration gates at review time: ruff check clean, git diff --check
  clean, the two required suites green at 19/19 and 17/17 (36 targeted),
  the EF4-I22 wire-literal gate 5/5, packaging discovery PASS, full Python
  1261/1261 and full Node 1702/1702 across the 136-file inventory. Zero
  blocking findings.
