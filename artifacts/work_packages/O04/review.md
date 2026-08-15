# O04 package review record

Standing verdict: `PASS` (from attempt `0001`).

This file is the package-level projection the manifest requires. The
attempt review below, at `attempts/0001/review.md`, is the primary record.

---

# O04-0001 primary-session separate adversarial review

- Reviewer: primary session in a separate adversarial pass under the
  product-owner instruction forbidding subagents and Fleet;
  actor_independence=false is recorded, not hidden.
- Certificate binding (EF4-I04): a claim can only be sealed after the
  completeness certificate is deterministically recomputed through
  the O01 public API from its plan and receipts; a tampered
  certificate fails in O01 before any claim logic runs, and claims
  hash-bind the certificate identity.
- Search-state type safety (EF4-I05): SEARCHED_NONE is the only zero-
  evidence state.  UNSEARCHED, PARTIAL, BLOCKED, and FAILED lanes are
  classified as ignorance: they ground no absence or novelty claim,
  and the zero-evidence report keeps the three classes disjoint.
- Partial honesty: a PARTIAL lane supports only scope-bounded claims
  over executed scope ids, with the absence ceiling demoted to
  LOCAL_CORPUS_ONLY; full-scope claims over remaining unsearched
  scope fail closed.
- Contradiction guards: results contradict absence; PRIOR_ART_FOUND
  contradicts novelty; claims against unexecuted scopes fail closed.
- O-phase integration: an EvidencePack whose ignorance lane is
  reported complete fails the gate (the exact failed-lane-as-zero-
  evidence defect), and packs must bind the recomputed certificate;
  the O03 assembler's honest output passes the same gate.
- Determinism: identical inputs seal byte-identical claims with
  content-addressed ids; validation is exact reconstruction; tampered
  fields, rehashed statements, and field-set drift fail closed.
- Residual limitations: live corpus retrieval, downstream O05/O06
  novelty acquisition, and external prior-art search remain later
  packages; this review is not external actor-independent
  certification.
