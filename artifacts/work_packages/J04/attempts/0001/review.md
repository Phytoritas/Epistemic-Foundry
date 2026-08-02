# J04-0001 post-compaction recovery integration review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_INTEGRATION_REVIEW`

Final verdict: `PASS`

Blocking J04 findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_INTEGRATION_REVIEW`

Actor independence: `false`

The product owner requires serial execution in the primary session without
Fleet or subagents. This review is procedurally separate from implementation,
but it is not actor-independent certification.

## Findings

1. Recovery first verifies the ContextCapsule's own integrity, then binds the
   observed capsule ID and hash to an external sealed receipt, and only then
   performs J03 freshness checks. Phase, blockers, RunSpec, policy, included
   artifacts, and exclusions are projected exclusively from that verified
   capsule.
2. Narrative prose is accepted only as an explicitly untrusted request field.
   The recovery implementation never reads it, so prose cannot replace an
   artifact, erase blockers, move the phase cursor, or acquire authority.
3. Direct hash tamper and semantic tamper fail ContextCapsule integrity. An
   attacker who changes phase/blockers and recomputes a valid capsule hash is
   still rejected because the external sealed receipt no longer matches.
4. Missing or changed included artifacts fail stale; newly visible unaccounted
   artifacts fail canonical-state drift. Phase, RunSpec, and policy drift also
   fail closed before any resumed state is returned.
5. Excluded content remains named as excluded and cannot regain authority via
   prose or a changed selection. Accessor-backed and unknown recovery fields
   fail without executing hostile accessors.
6. J03 runtime files remain byte-identical to their sealed J03 hashes. J04 adds
   only four golden recovery files and does not create a second ContextCapsule
   or recovery authority.
7. Required checks pass 10/10, J03 capsule regression passes 21/21, full Node
   passes 470/470, and full Python passes 990/990. There are no skips, xfails,
   todos, cancellations, or new failures. The earlier one-case Python
   collection error is preserved as a command-shape diagnostic and is not
   substituted for the authoritative green run.
8. Write-scope violations are zero. UTF-8/LF, syntax, structure, boundaries,
   and repository diff checks pass; the existing dirty worktree and all prior
   evidence remain preserved.

## Dependency effect

After J04 PASS, live projection contains 45 PASS
packages. The manifest-order READY set is
`K01, L01, N01, T01, A06`, with `K01`
as the next serial package. This projection will be independently recomputed
and RAH-sealed after J04 closeout.

## Assurance boundary

J04 proves post-compaction recovery from sealed artifacts. It does not claim
that downstream memory, ingest, role routing, or the full 156-package product
is complete. Global `implementation_gate=fail` and `completion_ready=false`
remain required.
