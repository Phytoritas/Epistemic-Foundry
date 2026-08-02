# U03-0001 independent review of bounded-agent work

- Author: a bounded implementation agent (write scope
  web/src/features/{atlas,parliament,aporia,passport}/**) under the
  product owner's instruction. Reviewer: a separate sealing agent that
  did not author U03. Author/reviewer separation holds
  (actor_independence=true between two distinct agents); external
  actor-independent certification does not.
- Manifest conformance: U03 declares exactly two required_checks
  (research_view_e2e, source_span_view_test) and two exit_criteria
  (source span accessible; minority/counterevidence visible), verified
  against manifests/development_manifest.yaml. These are NOT the standard
  five checks. There is no Python targeted suite and no Ruff gate for
  this Node/Web package, and none was invented.
- required_checks-mapping reconciliation: the two required checks are
  cross-cutting concerns over the same four *-view.test.mjs modules
  (atlas, parliament, aporia, passport), not a partition of the files.
  Every view suite is a full end-to-end read-model projection
  (build*View -> render*Panel) and every view suite carries a named
  'the view carries its (source|graph) receipt' provenance test. The
  four view test-file docstrings each reference generic 'five required
  checks' named-test dimensions (schema_and_type_check,
  unit_and_contract_tests, negative_and_adversarial,
  provenance_and_receipt_audit, independent_review); those are the
  suite's internal organisation and are NOT the manifest's required
  checks. Mapping was therefore done to the manifest's ACTUAL two checks
  by closest-covering named tests, without weakening or excluding any
  test: research_view_e2e -> all four suites (52 tests), carrying
  'minority/counterevidence visible'; source_span_view_test -> all four
  suites (52 tests), carrying 'source span accessible' via the per-view
  source-receipt tests (atlas L302, parliament L291, aporia L264,
  passport L251). Both checks run the full 52-test set; the overlap is
  inherent to the manifest bundling four views into two cross-cutting
  checks, and is not a gap.
- research_view_e2e (52/52): parliament keeps dissent/counter-evidence
  first-class and refuses hidden, unrecorded or invented dissent and
  majority-vote presentation; aporia renders open questions first and
  refuses hiding or resolution overclaim; passport renders
  counter-evidence beside the verdict, keeps the seven confidence
  dimensions separate and refuses aggregation; atlas surfaces
  counter_count and the coverage-claim vocabulary bound to the coverage
  certificate hash. Views are deep-frozen and deterministic and read no
  clock, random source or environment.
- source_span_view_test (52/52): each view exposes a source receipt back
  to provenance manifests, evidence packs, attestations, bias registers
  and artifact hashes, and binds only the declared read operations from
  the generated route manifest; undeclared or write operations refuse.
- Write-scope audit: the product bytes hashed here sit exactly inside
  the four approved feature trees; no composed module, schema, manifest
  or test outside scope was modified or weakened.
- full-node-suite: captured GREEN at 107 modules / 1192 tests. This
  absolute total is a repository-wide, integration-owned number that
  concurrent in-flight packages actively move; the frozen JUnit is the
  deterministic evidence, and reconciling the live inventory total is
  the integrating session's responsibility, not this leaf package's.
- Dependency binding: U01 (U01-0001, E0199/E0200) is the declared
  dependency; the regression baseline is the current latest-sealed
  report F06-0001 (E0237/E0238), both bound by report byte-hash.
- No blocking findings.
