# J01-0001 independent review of bounded-agent work

- Author: the bounded implementation agent that wrote the parent skill
  router under packages/plugin-host/src/skill-router and the bounded
  foundry skill metadata (SKILL.md, agents/openai.yaml). Reviewer: this
  seal-prep session, a distinct actor that did not author the router. The
  author never approves its own work, so actor_independence HOLDS for this
  review; external actor-independent certification does NOT, and no such
  claim is made. J01 is risk_class=medium; the router was attacked on its
  implicit-invocation boundary, explicit and remote authorization,
  metadata-only input surface, decision hashing, and fail-closed contracts
  rather than skimmed.
- Bounded implicit invocation. A single bundled candidate is routed
  implicitly only when its metadata explicitly sets
  allow_implicit_invocation=true, it is non-sensitive and
  non-side-effecting, it matches a bounded trigger phrase, and it hits no
  exclusion (BOUNDED_TRIGGER_MATCH). Missing or unspecified policy
  (IMPLICIT_POLICY_UNSPECIFIED), sensitive (SENSITIVE_EXPLICIT_ONLY),
  side-effecting (SIDE_EFFECTING_EXPLICIT_ONLY), remote
  (REMOTE_EXPLICIT_ONLY), excluded (EXCLUSION_MATCH), and tied
  (AMBIGUOUS_TRIGGER_MATCH) candidates all abstain into mode none with an
  empty selection.
- Explicit and remote authorization. An exact explicit skill id may route
  a sensitive or side-effecting bundled skill (EXPLICIT_EXACT_ID), while an
  unknown explicit id fails closed (UNKNOWN_EXPLICIT_SKILL). A remote skill
  is never implicit and, when explicitly named, requires an S03-branded
  activation authorization whose skill id, content hash, and policy hash
  match exactly (EXPLICIT_EXACT_ID_REMOTE_AUTHORIZED); a missing brand is
  REMOTE_ACTIVATION_AUTHORIZATION_REQUIRED and a mismatched policy hash is
  REMOTE_ACTIVATION_AUTHORIZATION_MISMATCH.
- Metadata-only fail-closed surface. Full instructions, bodies, and
  references are rejected as UNEXPECTED_FIELD; proxies and invalid input
  are INVALID_INPUT; accessor getters are ACCESSOR_FIELD_DENIED and never
  run; sparse candidate arrays are INVALID_INPUT; duplicate ids are
  DUPLICATE_SKILL_ID; malformed hashes are INVALID_HASH; and non-canonical
  JSON is NON_CANONICAL_JSON. The decision hash binds the exact indexed
  skill content (authority_notes include SKILL_METADATA:<id>:<source>:<hash>),
  candidate and phrase order do not change the hash or id, caller input is
  not mutated, and the returned decision is deeply frozen.
- skill_metadata_lint scope. The lint reads only this skill's own SKILL.md
  and agents/openai.yaml and enforces BOM-less UTF-8/LF, bounded
  frontmatter (allow_implicit_invocation:true, sensitive:false,
  side_effecting:false, load_full_instructions:on_demand), routing-only
  authority prose, the exact trigger and exclusion lists, and the absence
  of embedded full instructions or references. Both files are clean.
- Downstream-validator disclosure. A whole-plugin external metadata
  validator additionally flags OTHER downstream skill packages'
  skills/*/agents/openai.yaml. Those skills are outside J01's write scope
  and outside the J01 required checks: skill_metadata_lint covers only the
  foundry skill, which is clean. Likewise, progressive-reference files
  under plugins/epistemic-foundry/skills/foundry/references/** are J02-and-
  later work carried in the shared write-scope prefix, not J01 product.
  This is disclosed transparently; it is not a J01 defect, is not gated by
  a J01 required check, and is not masked.
- Dependency and checks: the router builds on the sealed C04 content-
  addressed artifact store, the sealed G04 and H01 host contracts, and the
  sealed S03 remote-authorization brand, and adds no new production
  dependency. Ruff lint and format, the two required checks
  (skill_routing_eval 15/15, skill_metadata_lint 4/4), targeted 19/19, full
  Python 1261/1261, full Node 1291/1291 across 115 files, and git diff
  --check all pass with zero failures.
- Residual limitations: J01 routes bounded metadata only; it does not load
  progressive references or child skill bodies, assemble a ContextCapsule,
  activate a skill, install a remote skill, issue authorization, mutate
  FORGE state, or claim completion. Those belong to J02 and later gates.
  Verdict: PASS on the exact J01 package contract.
