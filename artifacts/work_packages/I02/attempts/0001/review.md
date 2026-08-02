# I02-0001 independent review of bounded-agent work

- Author: a bounded implementation agent (disjoint write scope, frozen
  contracts) under the product owner's explicit instruction. Reviewer:
  the sealing agent, which did not author this attempt; author/reviewer
  separation holds with actor_independence=true, while external
  actor-independent certification does not.
- Falsifiability is mandatory before council-readiness: falsifiers are
  checked ahead of every other required field, and an absent, empty,
  blank, or scalar falsifier list is refused FALSIFIER_REQUIRED.
  predictions and mechanism_path are likewise mandatory, so a frame with
  no way to be wrong can never reach the council.
- Scope normalization preserves unknowns without inference: a missing,
  explicit-null, or blank scalar position becomes a canonical null while
  list/map positions become the canonical empty [] / {}, and a typed
  ScopeUnknown sidecar records ABSENT, EXPLICIT_NULL, or BLANK_STRING for
  the path. Explicit empty collections are not relabelled unknown, and a
  partial intervention keeps its nested unknowns.
- Eligibility is fail-closed: an eligible card that retains a required
  domain/population/unit_of_analysis unknown or an undefined construct is
  refused FRAME_ELIGIBILITY_CONFLICT, while inbox and withdrawn cards
  preserve their unknowns but never claim council readiness.
- The compiler validates but never generates authority: supplied
  insight_id, revision, created_at, registration_hash, and schema_version
  are checked for canonical form (ID pattern, RFC 3339 with an explicit
  offset, sha256 hex, semver) and preserved byte-for-byte; identifier,
  timestamp, and registration-hash content generation stay outside I02.
- Fail-closed on adversarial input: fields outside the InsightCard or
  ScopeVector contract, non-finite scope numbers, NUL-bearing strings, a
  domain axis outside domain_extensions, an intervention without a name,
  and loose or invalid RFC 3339 timestamps each raise the exact finding
  code (FRAME_FIELD_UNKNOWN, FRAME_FIELD_REQUIRED, FRAME_INPUT_INVALID,
  SCOPE_FIELD_UNKNOWN, SCOPE_INPUT_INVALID, SCOPE_INTERVENTION_NAME_REQUIRED)
  rather than degrading silently; a valid RFC 3339 leap second is kept.
- Output is deterministic: canonical JSON is mapping-order independent,
  the input proposal is never mutated, and array order is retained.
- Disclosed non-blocking note: the compiler holds module-level enum
  literals that match schemas/insight-card.schema.json exactly (verified
  no drift), and the frame-gold suite cross-validates the compiled card
  and ScopeVector against the real schemas at runtime -- the same idiom as
  the sealed sibling I01. The enforced EF4-I22 wire-literal gate scans
  only src/, so it does not cover this python/ component; the runtime
  schema cross-validation is the honest guard here.
- Integration gates at review time: ruff check clean, git diff --check
  clean, the two required suites green at 19/19 and 12/12 (31 targeted),
  the EF4-I22 wire-literal gate 5/5, packaging discovery PASS, full Python
  1261/1261 and full Node 1702/1702 across the 136-file inventory. Zero
  blocking findings.
