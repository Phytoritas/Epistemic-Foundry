# J01-0001 parent skill router and trigger-boundary review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW`

Final verdict: `PASS`

Blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW`

The product owner requires primary-session execution without subagents or Fleet.
This is a procedurally separate review of the final J01 product bytes and
receipts. It is not actor-independent certification.

## Reviewed product boundary

- `packages/plugin-host/src/skill-router/skill-router.mjs` — `sha256:6320ea8bb09eb3b69b9b2ea180b3d14bb8dbbf501f3a5afbe5dea63060a9b737`
- `packages/plugin-host/src/skill-router/skill-router.test.mjs` — `sha256:484920cf57202a2134011c95443bb3361242843e4e042bc82bb3fb6eb938b5ee`
- `packages/plugin-host/src/skill-router/skill-metadata-lint.test.mjs` — `sha256:07ff87d2f46d41cc82edc88e7f95e7a0a2c24119e7b5a89a30c98303713bdb34`
- `plugins/epistemic-foundry/skills/foundry/SKILL.md` — `sha256:ff97cecc79fe2eb4d7614676b4767a2bd61ec84039e797d765e88cc41d4b237b`
- `plugins/epistemic-foundry/skills/foundry/agents/openai.yaml` — `sha256:34be52ff5e0e7f4db1493eb88cf064125a4ab292938af8c3ec7665fe0ae7a762`

## Findings

1. Implicit routing is fail-closed. Exactly one bundled candidate must have an
   explicit `allow_implicit_invocation=true`, be non-sensitive and
   non-side-effecting, match a bounded trigger, and avoid every exclusion.
   Missing policy, absent triggers, exclusions, remote sources, and ties all
   abstain.
2. Exact explicit selection can route sensitive or side-effecting bundled
   skills, while a remote skill additionally requires an S03-branded
   authorization bound to the exact skill ID, content hash, policy hash,
   approval, conformance, rollback, and no-effect state.
3. The always-visible input surface is metadata-only. Unknown fields, skill
   bodies, references, accessors, proxies, sparse arrays, custom prototypes,
   invalid Unicode, duplicate IDs, and invalid hashes fail closed before they
   can influence a decision.
4. Decision hashing is deterministic over canonical metadata. Candidate and
   phrase ordering do not change the result, while a content-hash change does.
   Caller-owned input is not mutated and the returned decision is deeply
   frozen.
5. Routing remains advisory. It does not activate a skill, approve an effect,
   mutate FORGE state, issue a promotion, or claim completion. Child bodies and
   references remain on-demand concerns for J02 and later packages.
6. The emitted decision is validated against the existing canonical Draft
   2020-12 schema. J01 adds no canonical schema and preserves the count of 124.
7. The final targeted suite is 19/19, full Python is 947/947, and final serial
   Node is 411/412 with only exact unchanged S04-TM004. Product writes remain
   within the two J01 scopes.

## Assurance boundary

J01 implements parent routing and bounded trigger metadata only. It does not
implement progressive reference loading, ContextCapsule assembly, skill
activation, remote installation, authorization issuance, or effect execution.
S04-TM004 remains outside J01 ownership. This review does not claim
actor-independent certification.

## Decision

Both J01 exit criteria and both required checks pass. Product completion,
release readiness, a globally green repository, and `completion_ready=true`
remain unclaimed.
