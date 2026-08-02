# H02-0001 independent review of bounded-agent work

- Author: the bounded implementation agent(s) that authored the H02
  session and prompt lifecycle hook declarations
  (plugins/epistemic-foundry/hooks/session.json,
  plugins/epistemic-foundry/hooks/prompt.json), byte-equal to the plugin
  blueprint, and the eight-case hook-contract test harness
  (artifacts/work_packages/H02/attempts/0001/h02-hook-contract-tests.mjs).
  Reviewer: this sealing session, a distinct actor that did not author
  this attempt. Author/reviewer separation holds (actor_independence=true);
  external actor-independent certification does not.
- Mode: INDEPENDENT_REVIEW_OF_BOUNDED_AGENT_WORK. Blocking findings: 0.
- Scope: the manifest write scope is exactly the two hook declaration
  files. This session makes ZERO edit to them: both are hash-pinned as
  they currently are, both are byte-equal to the plugin blueprint, and
  every mutation counter is zero. No canonical source, schema, manifest,
  harness outside H02, or .rah/ state was touched.
- Exit criterion 1 - session bootstrap is bounded: VERIFIED.
  session_hook_test asserts session.json declares only a SessionStart
  route (matcher startup|resume|clear|compact, timeout 15) and a
  PostCompact route (matcher manual|auto, timeout 15); every hook is a
  type: command rooted at ${PLUGIN_ROOT} with a positive bounded integer
  timeout and no direct authority command. A timeout expansion to 16, an
  extra lifecycle event (SessionEnd), and a direct transition / set-phase
  command each FAIL CLOSED via validateSession, and the installed
  declaration is byte-equal to the blueprint.
- Exit criterion 2 - prompt classification cannot change state directly:
  VERIFIED. prompt_hook_test asserts prompt.json declares only one bounded
  UserPromptSubmit classification route (timeout 8). A direct
  state-mutation / commit command, an authority field (decision, phase,
  state, revision, action_intent_id, effect_receipt_id), and a timeout
  expansion each FAIL CLOSED via validatePrompt; the prompt declaration
  cannot register tool, completion, or delegation events (PreToolUse,
  Stop, SubagentStart); and the installed declaration is byte-equal to the
  blueprint.
- Fail-closed maturity boundary (honest, not a weakening) - the crux. The
  harness's fourth session and fourth prompt case assert the plugin
  manifest (plugins/epistemic-foundry/.codex-plugin/plugin.json) declares
  NO hooks key and empty interface.capabilities, and that
  plugins/epistemic-foundry/dist/hook-runner.mjs is ABSENT. H02 is a
  STATIC declaration boundary: it does not claim a hook runner,
  plugin-manifest hook registration, host capability probing, or packaged
  runtime integration. That is a correct SPECIFIED != IMPLEMENTED posture
  -- runtime integration is deferred to H04 / X01 / G06 -- not a
  weakening. Reaching GREEN required no edit to the declarations, the
  harness, or the plugin manifest.
- Attestation, not authorship. The two required checks are the package's
  own Node contract harness, run via node --test exactly as the manifest
  names them; the session_hook_test and prompt_hook_test four-case subsets
  each pass in the shared eight-case run. H02 reached GREEN with no
  substantive edit.
- Gates at review time: session_hook_test 4/4 and prompt_hook_test 4/4 in
  the shared eight-case harness (8/8, zero failures), the full Python
  suite green, the live full Node suite green with zero failures, and git
  diff --check clean. H02 depends on H01; the sealed H01-0001 attempt is
  the build dependency and regression baseline.
- Residual limitations: H02 attests the static hook declarations the
  repository already carries; it does not re-author them, makes no
  product-maturity or release-readiness claim, does not assert any runtime
  hook execution, hook-runner, plugin-manifest hook registration or host
  capability probing (H04 / X01 / G06 integration scope), and this review
  is not external actor-independent certification.
