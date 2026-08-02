# S04-0005 primary-session separate adversarial security review

Overall package status: `PASS`

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_SECURITY_AND_CONTRACT_REVIEW`

Actor independence: `false`

Fleet and subagents are forbidden by the product-owner decision. This is a
procedurally separate review of the final bytes, not actor-independent
certification.

## Authority and lineage

- Active binding `DMB-EF4-20260731-003` has a valid canonical
  self-hash and binds parent `sha256:5dd99d2aae1e9ef662b9b8242b5fa921621434c6600c9c06e3a573d03079bb12` to
  current manifest `sha256:6ccf07571c34c9010a10605ba201ba698a09f6343a281565520d392e4c77e063`.
- Patch plan `MP-EF4-S04-SG001-20260731-001` contains exactly 12 unique
  replacements across B04, C01, C02, C04, and O02. Every replacement hash was
  recomputed from the live manifest; static dependency changes are zero.
- Both authorizing HumanDecisions validate against Draft 2020-12 and their own
  canonical hashes. The superseded revision-002 binding evidence, C01
  reconciliation binding, and reconciliation patch remain byte-identical.
- S04-TM004 reads the active binding's patch-plan path and decision list. It no
  longer freezes revision 002, and it rejects a forged replacement hash even
  when the attacker recomputes patch and binding self-hashes.
- S04-0004 remains immutable `SPEC_GAP` history. No prior report, review,
  command receipt, RAH generation, or evidence row was rewritten.

## Regression and debt boundary

- Direct S04 traceability is 4/4; the targeted security surface is
  67/67.
- Full Node is 819/819
  with zero failures, skips, todos, or cancellations. S04-TM004 is resolved.
- Full Python is 1056 passed and 17 failed.
  All 17 node IDs, normalized error texts, problem types, and canonical failure
  fingerprints exactly match the sealed C01-0008 and J02-0004 B04-0009
  projection-debt baselines. S04 causal failures and new failures are zero.
- The repository is not fully green. B04-0009 remains responsible for the
  `expected 126 canonical schemas, found 127` projection debt.

## Verdict and assurance boundary

Blocking S04-owned findings: 0. Write-scope violations: 0. S04-0005 is PASS
and C01-0009 becomes dependency-ready. This does not establish C01, C02,
B04-0009, O02, C04, final packaging, release readiness, or product completion.
The global `implementation_gate=fail` and `completion_ready=false` remain.
