# O02-0002 retrieval contract review

Package recommendation: `PASS`

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW`

Assurance limitation: `actor_independence=false`. Fleet and subagents were
not used. This is a procedurally separate primary-session review authorized by
the product owner, not external actor-independent certification.

## Verdict

The O02 implementation conforms to the closed provider-neutral retrieval
contract. Blocking findings: 0.

## Findings

1. The query-family, retrieval-channel, and relation-direction vocabularies are
   closed at 6,
   5, and
   6 values. Lane-to-family
   bindings fail closed, including bounded temporal and external-novelty scope.
2. Requests and responses bind QueryPlan, query, corpus snapshot, index,
   backend, adapter, policy, cutoff, receipt, and exact canonical bytes.
   Snapshot, response, candidate-ID, and candidate-content tampering are
   rejected before release.
3. Exact duplicates collapse within a channel before stable ranks. Multi-channel
   candidates use only `RRF_K60`; raw scores are not compared across channels,
   no learned reranker runs, and retrieval rank is not scientific support.
4. Candidate replay is byte-identical. Both candidates validate against the
   strict Draft 2020-12 schema; metadata-only retrieval remains visible and is
   not treated as direct evidence.
5. All seven direction fixtures and the versioned inverse guard pass. Every
   required benchmark lane exceeds its independent Recall@20 and nDCG@20
   threshold; fused Recall@20 and all four critical must-find cases pass with
   zero network and LLM calls.
6. A vector-only set remains retained but cannot pass release. Missing required
   lanes yield `PARTIAL`, silent fallback yields `FAIL`, and a fully bounded
   all-`SEARCHED_NONE` run may pass without fabricating candidates.
7. O02-only tests pass 42/42 and O02+O01 pass 83/83. Full Node passes
   819/819
   across 79 files.
8. The first full Python run recorded 1114 passes and the sole existing D04
   PostgreSQL startup race. Its exact node and fingerprint remain in evidence;
   the isolated D04 test then passed 1/1 and a complete recheck passed
   1115/1115.
   O02-caused and residual failures are zero; no skip or xfail masks the event.
9. All thirteen authorized product/fixture files match their sealed hashes,
   write-scope violations are zero, and O02-0001 plus the dirty worktree remain
   preserved.

## Assurance boundary

This proves the deterministic local O02 contract and fixtures. It does not
prove live provider availability, licensed corpus coverage, O03 evidence
assembly, C04 conformance, final B04 packaging, release readiness, production
readiness, or global completion. `completion_ready=false` remains mandatory.
