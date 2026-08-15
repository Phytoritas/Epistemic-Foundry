# W04 package review record

Standing verdict: `PASS` (from attempt `0001`).

This file is the package-level projection the manifest requires. The
attempt review below, at `attempts/0001/review.md`, is the primary record.

---

# W04-0001 primary-session separate adversarial review

- Reviewer: primary session in a separate adversarial pass under the
  product-owner instruction forbidding subagents and Fleet;
  actor_independence=false is recorded, not hidden.
- The two drift kinds are separated structurally. Every leaf
  difference is typed STRICT, SEMANTIC, or UNCLASSIFIED, and the
  verdict is a function of the semantic bucket alone: any amount of
  strict drift still reads REPRODUCIBLE_WITH_STRICT_DRIFT, and one
  semantic difference forces DIVERGED however clean the rest is.
- The allowlist that makes a difference harmless cannot swallow a
  semantic field. The volatile and semantic lists are checked for
  overlap at module load, the semantic list wins in classification,
  and a report that files a semantic field as strict is refused at
  seal time even after its counts and hash are recomputed.
- A difference the engine cannot type is UNCLASSIFIED and blocks the
  seal rather than defaulting to harmless, so a field nobody
  considered cannot quietly pass as noise. A declared verdict that
  does not follow from the buckets, and counts that do not reconcile
  with the records, are both refused.
- Audit completeness is a reconciliation, not a claim. A referenced
  entry that is simply absent fails; an absence is allowed only with a
  typed reason from a closed list, and that exclusion may neither
  contradict a bundled entry nor name something the run never
  referenced. An entry the run never referenced is an orphan and also
  fails, so a bundle can be neither short nor padded.
- The drift report is sealed as part of the export rather than
  attached to it, so a bundle cannot carry an unclassified report and
  let a reader believe the run was checked. A diverged run can still
  be exported and says so plainly.
- Every bundled entry carries a sha256 content hash, hash coverage
  must equal the present set exactly, and the bundle is content-
  addressed so a tamper is caught by its own hash.
- Residual limitations: this package classifies differences and seals
  exports; it does not execute the replay that produces them, cannot
  see a semantic change in a field neither list names, and does not
  store or transport the bundle. Independent re-verification by
  another actor remains outside it. This review is not external
  actor-independent certification.
