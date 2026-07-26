# Epistemic Foundry brand and module language

## Canonical product name

**Epistemic Foundry** is the product and architecture name. It describes a process that transforms raw scholarly material into source-grounded, scope-bounded, adversarially tested research objects. The name does not claim that the system manufactures truth.

## Canonical module names

| Name | Meaning | Contract boundary |
|---|---|---|
| Foundry Kernel | provider-neutral runtime and authority | owns RunSpec, policy, capability, state, replay |
| Claim Forge | claim/evidence extraction | owns SourceSpan→ClaimCard→EvidenceNode pipeline |
| Epistemic Atlas | coverage and gap interface | owns coverage slices, bias/gap display, convergence board |
| Evidence Parliament | asymmetric deliberation | owns role ACL, briefs, attacks, gates, adjudication |
| Aporia Engine | contradiction and abduction | owns moderator candidates, competing explanations, discriminating tests |
| Noetic Ledger | immutable provenance | owns artifacts, events, approvals, actions, effects, decisions |
| Validation Bay | optional controlled execution | owns target eligibility, preregistration, sandbox execution, reconciliation |
| Hypothesis Passport | durable research decision object | carries multidimensional status, evidence, dissent, stability, next test |

## Naming rules

- Source code package: `epistemic_foundry`.
- CLI executable: `efoundry`.
- JSON `$id` namespace: `https://epistemic-foundry.local/schemas/` until a public namespace is approved.
- Internal abbreviations may use `EF`, but public headings prefer the full name.
- Do not call the product a “truth engine,” “proof machine,” or “autonomous scientist.”
- Provider names may appear only at adapter and developer-harness boundaries.
- Domain names may appear only in DomainPacks, fixtures, or project-local specializations.

## Product sentence

> Epistemic Foundry is a coverage-first, evidence-governed research reasoning architecture that anchors claims to source spans, exposes missing and contradictory evidence, runs asymmetric adversarial deliberation, and preserves every decision as a replayable artifact.
