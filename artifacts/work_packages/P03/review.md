# P03 package review record

Standing verdict: `PASS` (from attempt `0001`).

This file is the package-level projection the manifest requires. The
attempt review below, at `attempts/0001/review.md`, is the primary record.

---

# P03-0001 primary-session separate adversarial review

- Reviewer: primary session in a separate adversarial pass under the
  product-owner instruction forbidding subagents and Fleet;
  actor_independence=false is recorded, not hidden.
- Both vocabularies are read from their declaring schemas rather than
  restated, so an attack type or resolution status this component
  invented would not resolve.
- An attack must be grounded in real ids. It must name a brief this
  round carries, an assertion that exists inside that brief, and at
  least one evidence id; a challenge that cites nothing is refused
  rather than recorded as scrutiny. Citing evidence withheld from the
  attacker's own P01 context is refused with the same force as citing
  evidence no context ever held, so cross-examination cannot become a
  side channel around the Evidence ACL. A role may not cross-examine
  its own brief, and an attacker with no context this round is
  refused outright.
- An unanswered challenge stays open and must not carry a response,
  while an answered one must; the sealed round lists its open
  challenges so an unresolved objection cannot vanish into a summary.
- The strongest dissent is preserved by construction. It is the report
  with the greatest expected information gain, ties broken
  deterministically by id so both the seal and a caller agree on which
  one may not be dropped. It may be marked required or preserved, or
  superseded only by cited new evidence; superseding with no evidence
  is refused, and stripping that evidence from a sealed round fails
  closed. Dropping or renaming the strongest dissent in a rehashed
  round is caught because it is recomputed from the reports rather
  than trusted.
- Every report supplied is retained with its status; nothing is pruned
  for being inconvenient, and a round with no dissent still seals
  rather than pretending one existed.
- Cross-examination cannot run in the blind first round, which keeps
  the P01 isolation guarantee intact.
- Residual limitations: challenges and dissents arrive as inputs and
  are not generated here; the component checks that an attack is
  grounded, not that it is correct; it does not execute the unresolved
  test a dissent names; and adjudication belongs to the Parliament
  verdict. This review is not external actor-independent
  certification.
