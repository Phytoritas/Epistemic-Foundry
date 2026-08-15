# P01 package review record

Standing verdict: `PASS` (from attempt `0001`).

This file is the package-level projection the manifest requires. The
attempt review below, at `attempts/0001/review.md`, is the primary record.

---

# P01-0001 primary-session separate adversarial review

- Reviewer: primary session in a separate adversarial pass under the
  product-owner instruction forbidding subagents and Fleet;
  actor_independence=false is recorded, not hidden.
- The Evidence ACL is read, not restated. Each role's permitted
  classes come from manifests/role_registry.yaml, so the component
  cannot drift from the declaring source, and a role the registry does
  not describe has no ACL and fails closed rather than defaulting to
  open. The defender and prosecutor contexts are disjoint on the
  fixture corpus, which is the asymmetry the panel exists to create.
- Withholding is visible rather than silent. The manifest names the
  withheld ids and counts them by class, so a role can tell that
  evidence exists outside its ACL without being able to read it, and a
  brief citing either withheld evidence or evidence no context ever
  held is refused with the offending ids named.
- First-round isolation is measured. Every ordered pair of first-round
  briefs is examined and the ratio is a computed fact: one
  cross-reference takes a two-brief round from 1.0 to 0.5, and the
  sealing path refuses anything below full isolation, any non-blind
  first-round brief, and any two roles sharing one context manifest.
  A sealed record whose isolation report does not cover every brief is
  rejected as unmeasured.
- A symmetric panel is refused. Roles briefed identically are one
  opinion repeated, so an assembly whose contexts all carry the same
  evidence fails rather than being recorded as unanimous, and a single
  role is not a parliament.
- A brief that names no condition which would change its verdict is
  refused: an unfalsifiable brief cannot be cross-examined later.
- Fixtures validate against the canonical
  schemas/council-brief.schema.json, so the component is bound to the
  shared contract rather than to a local convention.
- Residual limitations: the component assembles contexts and checks
  what the briefs cite; it does not generate briefs and cannot enforce
  the ACL inside a model that has already received the context, so
  collusion outside the recorded artifacts is invisible to it.
  Cross-examination, adjudication, and minority reports are later
  P-phase packages. This review is not external actor-independent
  certification.
