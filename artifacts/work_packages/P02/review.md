# P02 package review record

Standing verdict: `PASS` (from attempt `0001`).

This file is the package-level projection the manifest requires. The
attempt review below, at `attempts/0001/review.md`, is the primary record.

---

# P02-0001 primary-session separate adversarial review

- Reviewer: primary session in a separate adversarial pass under the
  product-owner instruction forbidding subagents and Fleet;
  actor_independence=false is recorded, not hidden.
- The promotion ladder is read from the canonical passport schema
  rather than re-spelled, so a level this component invented would not
  resolve and a level added to the schema appears automatically.
- The combined ceiling is derived, not declared. It is the lowest any
  auditor set, so three satisfied auditors cannot overrule the fourth,
  and it is invariant to the order the verdicts arrive in. A declared
  ceiling above the derived one is refused, while a more cautious
  declaration is allowed; a sealed audit cannot have its ceiling
  raised afterwards even when its hash is recomputed.
- Method incompatibility is never pooled. The method auditor must
  report one ceiling per stratum, its component ceiling must equal the
  strongest stratum rather than a blend, and a mid-range figure
  spanning two strata is refused as pooling. Only the method auditor
  stratifies, and a sealed audit cannot be relabelled as pooled.
- The veto is narrow and accountable. Only the method auditor holds
  it; every other auditor is refused even for withdrawing a veto it
  never had. A veto must carry a reason, a verdict without one may not
  carry a reason, and a sustained veto floors the ladder at INBOX
  however optimistic the other three are. A withdrawn veto stops
  constraining but stays on the record, and removing a veto from a
  rehashed audit fails closed because the ceiling is recomputed from
  the verdicts.
- A vetoed audit still records what each auditor found, so the reason
  a promotion stopped is legible rather than a bare refusal.
- Residual limitations: the auditors' judgements arrive as inputs and
  are not produced here; the evidence-class to ceiling policy belongs
  to the ingest layer and is not duplicated; a method incompatibility
  the auditor never stratified is invisible to this component; and
  promotion itself is committed by the governance gates. This review
  is not external actor-independent certification.
