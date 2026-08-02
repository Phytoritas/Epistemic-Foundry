# S04-0004 primary-session separate contract review

Package recommendation: `SPEC_GAP (S04-SG001)`

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW`

Assurance limitation: `actor_independence=false`. Fleet and subagents are
forbidden by the active product-owner decision, so this is a procedurally
separate primary-session review rather than external certification.

## Verified facts

- `HD-EF4-C01-SG005-20260731-001` authorizes S04-0004 to modify only
  `manifests/source_bindings/development-manifest.binding.json` and its attempt
  evidence. It requires a new immutable binding revision that preserves lineage,
  authorizing-decision binding, and the binding self-hash.
- The live manifest hash is
  `6ccf07571c34c9010a10605ba201ba698a09f6343a281565520d392e4c77e063`.
  The active binding and its immutable patch plan both bind successor
  `5dd99d2aae1e9ef662b9b8242b5fa921621434c6600c9c06e3a573d03079bb12`.
- The targeted S04 test has exactly one failure: S04-TM004. S04-TM001 through
  S04-TM003 pass. No skip or xfail masks the conflict.
- S04-TM004 requires both `sha256(manifest) == binding.successor_sha256` and
  `patchPlan.successor_sha256 == binding.successor_sha256`. Therefore it also
  requires `sha256(manifest) == patchPlan.successor_sha256`, which is false for
  the current immutable patch plan.
- The same test freezes binding ID `DMB-EF4-20260730-002` and the prior sole
  authorizing decision `HD-EF4-B04-SG002-20260730-001`, conflicting with the
  required new revision and latest authorizing decision.

## Classification

This is `SPEC_GAP`, not `FAIL`: a correct binding-only implementation cannot
satisfy the non-editable acceptance contract, and changing the old patch plan
would rewrite immutable history. It is not `BLOCKED`: no external service,
credential, licensed source, toolchain, or host capability is missing.

No product file was changed. S04-0002, S04-0003, J02-0004, prior reports, RAH
generations, and the dirty worktree remain preserved.

## Minimum resolving decision

A product-owner HumanDecision must authorize these exact additions:

1. `tests/security/s04-threat-model-traceability.test.mjs`
2. a new immutable `artifacts/authority_decisions/<decision>.manifest-patch-plan.json`

It must assign the next binding ID and define its parent/supersedes lineage,
bind the current manifest successor and latest HumanDecision, and require the
test to validate the active revision without rewriting revision 002 or its patch
plan. S04 must then execute a new attempt. Under the fixed serial order,
C01-0009 and every later attempt remain unstarted.
