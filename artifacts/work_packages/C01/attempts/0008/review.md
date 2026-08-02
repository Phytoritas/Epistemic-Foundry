# C01-0008 independent contract review

Package recommendation: `SPEC_GAP (C01-SG005)`

Implementation finding: `VERIFIED`

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW`

Assurance limitation: `actor_independence=false`. Fleet and subagents are
forbidden by the active product-owner contract, so this is a procedurally
separate primary-session review, not external actor-independent certification.

## Contract result

- The active authority is exactly 127 Draft 2020-12 schemas and 127 matching
  examples. All schemas meta-validate, all `$id` values are unique, mapping is
  one-to-one, and all examples validate.
- RetrievalCandidate is strict (`additionalProperties=false`), recomputes
  candidate ID `RC-bead81fad2a047285297611ac44e28646e764716b42fc53f07fecddff5aa3a3b`, query hash `sha256:3cc4c6b54c5e182f3f1c25d505244f0ed601221adb0654293f006732099fb309`,
  and content hash `sha256:6125d56bf4d2097f3081b85d522bdfcb0cbad008bc6c693bc89f5e579ddc72da`. Missing fields, unknown fields,
  and semantic tampering fail closed.
- OpenAPI remains 3.1.1 with 33 unique operations and resolvable canonical
  schema references.
- The targeted C01 gate is 104/
  104 with zero failures or skips.

## Regression disposition

- Full Python is 1056 passed and
  17 failed. Every failure is the exact
  `expected 126 canonical schemas, found 127` B04 materializer signature and is
  classified `EXPECTED_B04_0009_PROJECTION_DEBT`; B04-0009 is already ordered
  after C02-0004.
- Full Node is 817 passed and
  3 failed by the authoritative Node footer.
  O01-0002 previously passed 819/819. The two J02 failures bind the old
  MASTER_SPEC hash in `skill-inventory.json`; the S04 failure binds the old
  development-manifest successor hash.
- `skill-inventory.json` still has the exact J02-0003 PASS hash and
  `development-manifest.binding.json` still has the exact S04-0003 PASS hash.
  C01-0008 did not modify either downstream-owned file.

## Blocking decision

C01 owns neither downstream projection. The active decision authorizes the
serial sequence beginning with C01-0008 but does not authorize J02-0004 or
S04-0004 correction attempts. Continuing by editing those files would expand
authority without a product-owner decision. Therefore the correct package
result is SPEC_GAP, not PASS, FAIL, or BLOCKED.

The recommended prospective order is J02-0004, S04-0004, C01-0009
revalidation, then the previously authorized C02-0004 → B04-0009 → O02-0002 →
C04-0004 → final B04 sequence. No downstream attempt starts before the new
decision. Existing attempts, RAH evidence/generations, and the dirty worktree
remain preserved; `completion_ready=false`.
