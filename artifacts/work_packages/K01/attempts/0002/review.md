# K01-0002 document registration adversarial review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_ADVERSARIAL_REVIEW`

Final verdict: `PASS`

Blocking K01 findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_REVIEW`

Actor independence: `false`

The product owner requires serial execution in the primary session without
Fleet or subagents. This review is procedurally separate from implementation,
but it is not actor-independent certification.

## Findings

1. `DocumentRegistrationRequest`, immutable `DocumentRegistration`, and the
   later `DocumentManifest` remain distinct lifecycle artifacts. The initial
   node never requires or fabricates downstream parser, integrity, metadata,
   provenance, or SourceSpan results.
2. Registration accepts only immutable staged bytes whose ArtifactReceipt is
   present, hash/size/media-type bound, and entirely PASS. URI provenance is
   never used for network, local-file, CWD, or repository-root discovery.
3. D03/E01/E02/E03/CAS authority is injected through required ports. K01 has
   no in-memory or permissive default implementation and does not reimplement
   the artifact store, ledger, effect coordinator, lease authority, or state
   revision store.
4. The source ActionIntent is resolved and self-hash verified; source and
   registration ArtifactReceipts, EffectReceipt, ledger event, fencing token,
   and exact one-step CAS revision advancement are all required before a
   success ResultEnvelope can be emitted.
5. Same-key/same-request retry reopens the original immutable registration and
   evidence without repeating controlled effects. Same-key/different-request
   fails conflict. Missing or corrupt receipts, events, ActionIntent payload,
   lineage, or CAS evidence triggers shared reconciliation and otherwise fails
   `DOCUMENT_RECONCILIATION_REQUIRED`.
6. Supersession is same-workspace/same-corpus, append-only, bounded, and
   cycle-checked both before effects and during replay. Removing predecessor
   history after commit makes replay fail closed without repeating effects.
7. The exact 22-case oracle, lineage suite, effect/crash reconciliation tests,
   canonical schema/example validation, workflow binding, and no-fallback
   probes all pass. The new CAS offset probes reject both zero-step and
   two-step advancement at commit and replay.
8. K01 targeted tests pass 64/64 and full Python passes 1054/1054. The first
   full Node run's single non-K01 transient concurrency failure is preserved
   with its exact fingerprint; the isolated behavior and later full run pass,
   and the authoritative final Node result is 470/470 with no suppression.
9. Structure, boundaries, scoped Ruff, codegen parity, and `git diff --check`
   pass. Write-scope violations are zero, generated cache is absent, and prior
   attempts, RAH generations, and the dirty worktree remain preserved.

## Dependency effect

After K01 PASS, the live projection contains 46
PASS packages. The manifest-order READY set is
`K02, K03, L01, N01, T01, A06`, with `K02`
as the next serial package. This projection is provisional until independently
recomputed and RAH-sealed after K01 closeout.

## Assurance boundary

K01 proves immutable initial document registration and reconciliation at its
defined authority boundary. It does not claim downstream parsing, corpus
release, the full 156-package product, actor-independent certification, or
production readiness. Global `implementation_gate=fail` and
`completion_ready=false` remain required.
