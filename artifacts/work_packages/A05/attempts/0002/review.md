# A05 attempt 0002 contract review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_REVIEW`

Review procedure: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_PASS`

Reviewer identity: primary session contract review. The product owner explicitly
prohibited Fleet and subagents and explicitly approved the required reviews for
this execution. No distinct actor, subagent, or Fleet reviewer was used or
represented. This was a separate review pass after authoring and deterministic
verification, but it is procedural separation, not actor-independent assurance.

## Authority and evidence reviewed

- `HD-EF4-A05-C01-B04-20260727-001` and requirements R14-R67;
- `MASTER_SPEC.md` and `MASTER_EXECUTION_PROMPT.md`;
- A04 dependency report (`PASS`);
- immutable A05 attempt-0001 `SPEC_GAP` report, commands, review, gap document,
  probe, and probe output;
- `docs/v4_a05/evolution_authority_and_promotion_charter.md`;
- `docs/v4_a05/adversarial_contract_tests.md`;
- `authority-contract-verifier.py` and its checked machine-readable output;
- the unchanged schema, workflow, prompt, and governance-runtime inputs that
  A05 is forbidden to modify.

The reviewed charter hash is
`sha256:5d8b1b5d7b8bfed727e823ab49996de4ed40ba520a1958bbb519dda36639a181`.
The adversarial registry hash is
`sha256:089944826184843854f0af4415a5bca6f31c83e88227597b20f7bd8db37d5290`.
The deterministic verification hash is
`sha256:b2a228ca578d8fdb70e1d893aaa0b23da500a44dc5609ef3f81c76741b6f7ff0`.

## Adversarial review findings

1. **Historical integrity — PASS.** The prior A05 top-level report remains
   `SPEC_GAP` with `A05-SG001` and `A05-SG002`; all seven bound attempt-0001
   artifacts byte-match their sealed hashes. Attempt 0002 is additive under
   `attempts/0002` and explicitly supersedes rather than rewrites the prior
   result.
2. **Authority resolution — PASS.** The charter defines all nine tuple fields
   and the complete 21-key resolved-reference inventory, including exact
   backend pins and remote-model reproducibility disclosure. A bare ID,
   floating alias, mutable path, or current-value lookup is not treated as a
   pin.
3. **Hash/seal behavior — PASS.** RFC 8785 JCS-equivalent UTF-8 hashing,
   `spec_hash` exclusion, schema-declared sorting for set-semantic arrays,
   post-resolution hashing, immutable seal behavior, and typed
   FAIL/BLOCKED/SPEC_GAP outcomes are unambiguous.
4. **Promotion vocabulary — PASS.** The six levels are closed and ordered;
   `BLOCK` is kept out of the level vocabulary. Each level states its minimum
   evidence and avoids conflating validation screening, empirical testing, and
   independent replication.
5. **Gate authority and order — PASS.** G00-G14 are present in the exact order
   and each has a deterministic responsibility. Every gate produces a
   GateDecision. The applicability matrix does not omit lower-tier gates:
   non-applicable substantive checks require sealed `NOT_REQUIRED` evidence,
   not `WAIVE`.
6. **Non-waivable failures — PASS.** Evaluator mutation, holdout leakage,
   missing provenance, self-approval, scalar-only promotion, unreconciled
   counts, missing adaptive statistics, missing/fabricated receipts, and
   integrity failures cannot be converted to PASS by a human or policy actor.
7. **Replication ceiling — PASS.** Not-run/BLOCKED, PARTIAL, INCONCLUSIVE,
   FAILED, REPLICATED, and formal/deductive cases each have explicit ceilings
   and conditions. A result of `REPLICATED` is eligibility only, never automatic
   promotion.
8. **Parliament and attestation — PASS.** Parliament is required above
   CANDIDATE, independent attestation at VALIDATION_SCREENED or above, and the
   attestor independence axes and sealed artifact view are explicit. No search
   actor or backend receives promotion authority.
9. **Approval authority — PASS.** All seven mandatory human-approval trigger
   classes are represented; the low-risk policy path requires an explicit
   PolicyBundle rule. Missing approval is never normalized to an empty success.
10. **Commit, retry, and reconciliation — PASS.** The canonical 18-step order,
    idempotency key, same-key conflict behavior, expected-revision CAS,
    immutable revisions, crash-without-receipt rule, and state/ledger
    reconciliation are complete.
11. **Negative/adversarial coverage — PASS.** Twenty-four negative fixtures and
    four positive boundary controls cover the six product-owner-required
    rejection cases plus floating pins, tampering, count mismatch, missing
    statistics, non-independent attestation, idempotency conflict, and crash
    ambiguity. Failures must resolve to typed GateDecision evidence.
12. **Scope and maturity claims — PASS.** Only `docs/v4_a05/**` and
    `artifacts/work_packages/A05/**` were added for attempt 0002. Bound schema,
    workflow, prompt, and runtime inputs retain their hashes. The charter
    explicitly assigns implementation to C01/later packages and does not claim
    a working promotion runtime.

## Validation reviewed

- deterministic evidence regeneration and byte-for-byte check: PASS;
- verifier compilation: PASS;
- targeted governance/evolution regression: 73 passed;
- full Python regression: 789 passed;
- `git diff --check` for the A05 write scope: PASS;
- whole-bundle diagnostic: FAIL only on seven pre-existing/staged
  `PACKAGE_MANIFEST` hash/inventory mismatches in the dirty worktree. This
  known broader inventory state neither changes the A05 contract result nor
  serves as A05 evidence.

## Decision

No blocking finding remains within A05 attempt 0002. The authority decision is
fully represented without schema/runtime changes, and `A05-SG001` plus
`A05-SG002` are prospectively resolved. A05 attempt 0002 is approved as
`PASS` and C01 may begin.

Remaining assurance limitation: because the product owner prohibited
subagents/Fleet, this review is not actor-independent. That limitation is
disclosed and cannot be used to claim external certification. The product
owner's explicit review approval satisfies the authorized procedure for this
serial unblock execution.
