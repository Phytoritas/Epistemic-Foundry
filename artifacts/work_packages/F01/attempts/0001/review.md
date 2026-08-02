# F01-0001 independent implementation review

Overall package recommendation: `PASS`

Review mode: `INDEPENDENT_REVIEW_OF_BOUNDED_AGENT_WORK`

Blocking findings: 0

- Author: a bounded implementation agent produced the F01 classifier,
  committer, schema, example, workflow node, advisory prompt and golden
  fixtures. Reviewer: this independent seal-prep session together with an
  independent `contract_reviewer` subagent that did not author the
  subject code and reviewed it adversarially against the authority chain.
  Actor-independence between author and reviewer HOLDS; external
  actor-independent (provider-independent) certification does NOT.
- Verification basis: independent execution of the six Node classifier
  suites (33 tests), the F01 Python trio plus the canonical-registry and
  two protective-regression suites, an independent pure-Python SHA-256
  recompute of all four frozen hash vectors, an independent end-to-end
  run of the real classifier confirming it emits those four hashes
  exactly, independent Draft2020-12 metaschema and example validation,
  and two custom adversarial state-machine probes against the committer.
  No FORGE state was mutated by the review.
- Per-exit-criterion: (1) closed vocabulary and deterministic maximum
  floor - PASS; (2) exact E0-E5 phase / role-count / human-gate /
  conditional-Interview projections - PASS; (3) added signals cannot
  reduce class or any protection (1023 subsets, 58025 pairs, zero
  violations) - PASS; (4) identity / retry / replay / receipt / immutable
  upward-only override contracts - PASS; (5) workflow emits the canonical
  EpistemicWorkClassification artifact and the prompt is advisory only -
  PASS. Gold 14/14, adversarial 16/16, hash vectors 4/4, override 6/6.
- E0-E5 classification is exact and order/duplicate-invariant. The
  identity preimage covers exactly the published semantic fields under
  canonical JSON; volatile fields (classified_at, ids, receipt, sequence)
  are outside the hash, confirmed by stable hashes across a changed clock.
  There is no Math.random or Date on the identified path.
- Override is upward-only (HUMAN_OVERRIDE_LOWERING_DENIED on a downward
  target), immutable/idempotent (bound by human_decision_hash), and
  requires a human-actor HumanDecision with decision_type `correct`
  scope-bound to the base classification and verified through its
  manifest and receipt.
- Non-blocking observation (spec-conformant, not a defect): `classify()`
  can lower the active classification for the same immutable request when
  the caller supplies a NEW policy_bundle_hash with reduced trusted
  signals; `assertMonotonicProtection` is intentionally wired only into
  the override path. This is explicitly sanctioned by the authoritative
  contract docs/forge_protocol.md section 2 (a lower classification
  requires a new request revision or PolicyBundle; the no-lowering
  invariant is scoped to the override path). The prior classification
  stays immutable, the supersedes chain and ledger event are recorded,
  and the active compare-and-swap still names the current active hash.
- Assurance boundaries: F01 accepts policy_bundle_hash and
  policy_bundle_signals as opaque TRUSTED inputs (format-validated only),
  so the safety of PolicyBundle-triggered downgrades depends on the
  upstream C04 policy layer authenticating bundles and matching signals;
  this is out of F01 scope but load-bearing end to end. The determinism
  verdict covers the identified path; the separate artifact-store /
  ledger / state-store packages were not exhaustively fuzzed. No live-LLM
  or network path exists or was exercised. This review is not external
  actor-independent certification, and it does not advance product
  completion; `completion_ready` remains false.
