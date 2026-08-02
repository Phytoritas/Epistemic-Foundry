# G01-0001 independent review of bounded-agent work

- Author: the bounded implementation agent(s) (G01 maker) that authored
  the native plugin manifest plugins/epistemic-foundry/.codex-plugin/
  plugin.json, the two square SVG brand assets under
  plugins/epistemic-foundry/assets/, and the deterministic verifier
  g01_verify.py under artifacts/work_packages/G01/attempts/0001/, while
  attesting those files without editing their content. Reviewer: the
  sealing session, a distinct actor that did not author this attempt.
  Author/reviewer separation holds (actor_independence=true); external
  actor-independent certification does not.
- Mode: INDEPENDENT_REVIEW_OF_BOUNDED_AGENT_WORK. Blocking findings: 0.
- Scope: the manifest write scope is
  plugins/epistemic-foundry/.codex-plugin/plugin.json and
  plugins/epistemic-foundry/assets/** plus
  artifacts/work_packages/G01/attempts/0001/**. G01 makes NO edit to the
  manifest or assets; the manifest and both asset bytes are hash-pinned
  as they currently are, the live assets tree is confirmed undrifted,
  and the mutation counters are all zero. No src, schema, manifest, skill
  file, harness outside G01, or .rah/ state was touched.
- Exit criterion 1 - manifest paths remain inside plugin root: VERIFIED.
  plugin_manifest_validation and asset_path_test resolve both interface
  asset paths (composerIcon, logo) inside the plugin root and reject
  parent traversal, Windows-absolute, missing-file, and outside-root
  shapes. Both assets exist, are distinct square SVGs (64x64 and
  256x256), and carry no active/external content
  (asset_path_test 7/7 negatives).
- Exit criterion 2 - version and capabilities accurate: VERIFIED.
  plugin_manifest_validation asserts name=epistemic-foundry, version is
  strict semver pinned to 4.0.0, interface.capabilities is exactly [],
  and no ungated component field (skills/hooks/mcpServers/apps) is
  declared before its downstream gate passes
  (plugin_manifest_validation error_count 0).
- Gating decision (the crux). G01's manifest declares required_checks
  EXACTLY [plugin_manifest_validation, asset_path_test], both implemented
  by g01_verify.py, and BOTH pass. This seal runner gates on those two
  required checks only, plus a repository-wide full-python-suite (green)
  and git diff --check as the regression baseline.
- Whole-plugin-validator DISCLOSURE (transparent, non-gating). The
  external whole-plugin validate_plugin walk (plugin-creator), when
  present at seal-prep time, reports 120 errors over the whole
  plugin tree -- EVERY one skill-scoped
  (skills/*/agents/openai.yaml, added by DOWNSTREAM skill packages),
  and ZERO referencing G01's own plugin.json or assets/
  (g01_write_scope_error_count=0, verified). Those files are OUTSIDE
  G01's write scope and OUTSIDE G01's manifest+asset contract. Their
  FAIL is a cross-package integration item owned by the downstream skill
  packages (G02-G05 etc.) and a later whole-plugin integration gate --
  NOT a G01 defect and NOT a weakening: G01's own files are unchanged and
  valid, and this attempt gates only on G01's two required checks. The
  runner records the disclosure with gating=false and the builder asserts
  g01_write_scope_error_count=0 so a regression that DID touch G01's
  files could never hide behind this disclosure.
- Regression at review time: the two required checks PASS, the
  repository-wide Python suite is green with zero failures, and
  git diff --check is clean. The Node suite is not part of G01's
  attestation contract; it carries a pre-existing repository-owned debt
  (S04-TM004) unrelated to G01's files. G01 depends on B04, C04 and S01,
  each a sealed PASS work package bound by content.
- Residual limitations: G01 attests local plugin manifest and asset
  package shape, not fresh marketplace installation; declares no skill,
  hook, MCP, app, dispatcher or runtime capability; makes no
  product-maturity or release-readiness claim; and this review is not
  external actor-independent certification.
