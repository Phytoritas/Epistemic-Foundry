# J03-0001 independent review of bounded-agent work

- Author: the bounded implementation agent that wrote the ContextCapsule
  assembler under packages/context-capsule (context-capsule.mjs, index.mjs,
  package.json and the two required-check test files). Reviewer: this
  seal-prep session, a distinct actor that did not author the assembler.
  The author never approves its own work, so actor_independence HOLDS for
  this review; external actor-independent certification does NOT, and no
  such claim is made. J03 is risk_class=medium; the assembler was attacked
  on its determinism, exclusion secrecy, freshness fail-closed contract,
  hash binding, and hostile-input surface rather than skimmed.
- Deterministic content-addressed assembly. assembleContextCapsule turns an
  explicit canonical-state snapshot into a deeply frozen capsule whose
  capsule_hash binds the exact canonical JSON preimage. There is no clock,
  random id, filesystem discovery, or previous-capsule fallback, so
  replaying the same snapshot yields identical immutable bytes; set-like
  input ordering of selections and capabilities cannot change the bytes or
  the hash; the caller input is not mutated; and every included artifact
  binds a source_hash and a nonblank summary whose summary_hash binds its
  bytes (UNBOUND_INCLUDED_ARTIFACT, EMPTY_SUMMARY, SUMMARY_HASH_MISMATCH).
- Explicit exclusions cannot smuggle content. EXCLUDE selections may carry
  no source_hash or summary; attempting to attach either fails closed as
  EXCLUDED_ARTIFACT_CONTENT_DENIED, duplicate or conflicting dispositions
  are ARTIFACT_DISPOSITION_CONFLICT, and an artifact cannot be both included
  and explicitly excluded. A capsule with no included canonical artifact is
  refused (CANONICAL_ARTIFACT_REQUIRED).
- Fail-closed freshness. requireFreshContextCapsule verifies capsule
  integrity first, then rejects session, phase, RunSpec, and policy drift,
  an undeclared or expired freshness window, a not-yet-valid creation
  instant, changed or missing included artifacts (CAPSULE_ARTIFACT_STALE),
  and any newly visible artifact that is neither included nor explicitly
  excluded (CAPSULE_CANONICAL_STATE_DRIFT); an excluded artifact's absence
  does not resurrect it. Capsule or summary tamper is CAPSULE_HASH_MISMATCH
  before any freshness decision is taken.
- Hostile and non-canonical input. Proxies, accessor getters (which never
  run), sparse arrays, custom prototypes, invalid Unicode, unexpected
  fields, invalid hashes, invalid phases and non-canonical numbers all fail
  closed before influencing a decision. The ContextCapsule boundary is bound
  to the generated @epistemic-foundry/contracts registry at module load and
  fails closed (CANONICAL_CONTRACT_MISMATCH) on contract drift; the emitted
  capsule validates against the canonical Draft 2020-12
  schemas/context-capsule.schema.json, which J03 did not modify.
- Dependency and checks: the assembler builds on the sealed J01 parent
  skill router (report sha256 1dccbcea..., core E0343 / final closeout
  E0344) and adds no new production dependency. Ruff lint and format, the
  two required checks (capsule_hash_test 11/11, stale_capsule_test 10/10),
  targeted 21/21, full Python 1261/1261, full Node 1291/1291 across 115
  files, and git diff --check all pass with zero J03-caused failures.
- Seal-prep boundary and residual limitations: this attempt did not touch
  .rah/ and did not bind a live RAH generation; report.json carries
  seal_prep_only=true, ready_for_seal=true, completion_ready=false,
  global_implementation_gate=fail and an unbound rah_state. J03 assembles
  and freshness-checks a capsule from explicit canonical state; it does not
  itself read the ledger, drive compaction recovery, or claim completion.
  Post-compaction recovery is the J04 gate. Verdict: PASS on the exact J03
  package contract.
