# J03-0001 ContextCapsule contract review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW`

Final verdict: `PASS`

Blocking J03 findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW`

The product owner requires primary-session execution without subagents or Fleet.
This is a procedurally separate review of the final J03 product bytes and
receipts. It is not actor-independent certification.

## Reviewed product boundary

- `packages/context-capsule/package.json` — `sha256:f768694a12bac2de3e187770b6f3c0c47b2226246eda22d13226e70cd3b36d4e`
- `packages/context-capsule/src/context-capsule.mjs` — `sha256:017b9b7d8638df51fa2f5a0a218eaf797bdca1ca64b4c02e2d8fde7f3c2c45a6`
- `packages/context-capsule/src/index.mjs` — `sha256:f92d0efb43f6bee745e0cfe442cfb0f8f3acc8002f8fecc979837a39d427a5d0`
- `packages/context-capsule/src/capsule-hash.test.mjs` — `sha256:89c01ee1981e93d6a6666d246c70061dbf00f5443129bde8ea034f4e263c192d`
- `packages/context-capsule/src/stale-capsule.test.mjs` — `sha256:29073639bde615df9edfe827d8c118fc8df4c12ecd3139aba6d4c8d516035ca8`

## Findings

1. Assembly is deterministic and authority-bounded. The caller supplies the
   canonical state, identifiers, timestamps, phase, RunSpec hash, policy hash,
   capability set, token budget, and complete inclusion/exclusion decisions.
   The package does not consult a clock, random source, previous capsule, or
   repository filesystem to invent authority.
2. Every included artifact is bound to an exact lowercase SHA-256 and a
   nonblank summary; the summary has its own canonical hash. Excluded
   artifacts are named explicitly and cannot smuggle source bytes or summaries
   into the capsule input.
3. Capsule hashing is deterministic canonical JSON over all semantic fields
   except `capsule_hash`. Set-like inputs are UTF-8 byte ordered, execution
   phase order is preserved where meaningful, caller input is not mutated, and
   returned capsules and freshness results are deeply frozen.
4. Resume is fail-closed. Integrity is checked before freshness; session,
   phase, RunSpec, policy, expiry, included-artifact hashes, missing artifacts,
   and newly visible unaccounted artifacts are all verified. A capsule with no
   expiry may be recorded but cannot authorize resume.
5. Accessor-backed, proxy, sparse-array, custom-prototype, invalid-Unicode,
   unexpected-field, duplicate, and conflicting-disposition inputs are
   rejected before they can influence a decision.
6. The implementation binds to the existing generated `ContextCapsule`
   contract and validates emitted data against the canonical Draft 2020-12
   schema. J03 changes neither the canonical schema nor generated registry.
7. Required checks pass exactly: `capsule_hash_test` 11/11 and
   `stale_capsule_test` 10/10. The existing Python I20 capsule contract also
   passes 20/20. Structure, package-boundary, syntax, UTF-8/LF, and scoped
   write checks pass.
8. Full regression introduces no J03-caused failure. Python in the unchanged
   locked environment is 960 passed and four J02-owned failures; an ephemeral
   pinned-tokenizer diagnostic is 963 passed with only the existing J02 lock
   gate. Node is 457 passed with only exact existing S04-TM004.

## Assurance and dependency boundary

J03 implements ContextCapsule assembly, integrity verification, and freshness
rejection only. It does not implement J02 progressive-reference budgets, J04
post-compaction orchestration, authorization issuance, artifact persistence,
or RAH lifecycle mutation. The blocked RAH lifecycle remains at generation
`000081-843d5565` with latest evidence `E0084`; no J03 evidence was appended to
it.

After J03 PASS, the latest-attempt DAG contains 43 PASS packages, four
attempted non-PASS packages, no dependency-ready package, and 109 unstarted
blocked packages. J04 still waits on J02. Product-owner decisions or bounded
remediation authority remain required for J02, K01, T01, and A06.

## Decision

Both J03 exit criteria and both required checks pass at the package boundary.
Repository-wide green status, J04 readiness, product completion, release
readiness, actor-independent certification, and `completion_ready=true` remain
unclaimed.
