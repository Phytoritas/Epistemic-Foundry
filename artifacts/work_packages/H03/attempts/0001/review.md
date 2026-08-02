# H03-0001 independent review of bounded-agent work

- Author: the bounded implementation agent(s) (H03 maker) that installed
  the two static tool and delegation hook declarations
  plugins/epistemic-foundry/hooks/tools.json and delegation.json
  byte-for-byte from the authority blueprint and authored the Node
  contract harness h03-hook-contract-tests.mjs under
  artifacts/work_packages/H03/attempts/0001/. Reviewer: the sealing
  session, a distinct actor that did not author this attempt. Author/
  reviewer separation holds (actor_independence=true); external
  actor-independent certification does not.
- Mode: INDEPENDENT_REVIEW_OF_BOUNDED_AGENT_WORK. Blocking findings: 0.
- Scope: the manifest write scope is
  plugins/epistemic-foundry/hooks/tools.json and delegation.json plus
  artifacts/work_packages/H03/**. Both declarations are hash-pinned and
  confirmed byte-equivalent to plugin_blueprint/epistemic-foundry/hooks/
  tools.json and delegation.json; they decode as BOM-less UTF-8. No src,
  schema, manifest, harness outside H03, or .rah/ state was touched, and
  the mutation counters are all zero.
- Exit criterion 1 - observed tools use policy and effect receipts:
  VERIFIED. tool_hook_policy_test (4/4) asserts tools.json routes
  PermissionRequest (matcher Bash|apply_patch|mcp__.*) to the H01 gateway
  hook-runner permission-request command and binds PreToolUse guardrails
  and PostToolUse effect receipts with an identical
  Bash|apply_patch|Edit|Write|mcp__.*|Agent matcher (symmetric pre/post
  coverage). A direct-allow command rewrite, a timeout expansion beyond
  the canonical bound, dropped policy or receipt coverage, an asymmetric
  matcher, and any extra event each fail closed.
- Exit criterion 2 - subagent expected-count contract enforced: VERIFIED.
  subagent_result_gate_test (4/4) asserts delegation.json binds
  SubagentStart -> RoleSpec and SubagentStop -> ResultEnvelope over every
  subagent (matcher .*). Substituting the stop handler with
  accept-partial-result, a partial matcher, and a missing start or stop
  route each fail closed, so an untrusted subagent result cannot
  self-authorize or bypass review.
- Maturity boundary (the crux, honestly disclosed). H03 supplies STATIC
  declarations only. The plugin manifest
  plugins/epistemic-foundry/.codex-plugin/plugin.json carries no hooks
  key and an empty interface.capabilities, and
  plugins/epistemic-foundry/dist/hook-runner.mjs is ABSENT. Runtime
  enforcement is H04/N04/X01/G06 scope and is correctly NOT claimed
  executable: this is a specified-not-yet-implemented posture, not a
  weakening of the gate. The harness case
  'subagent_result_gate_test: handler substitution and premature runtime
  claims fail closed' asserts exactly this -- manifest lacks a hooks key,
  capabilities is [], and the runner file does not exist -- so a premature
  runtime claim fails closed.
- Gates at review time: hook_contract_tests 8/8 (tool_hook_policy_test
  4/4, subagent_result_gate_test 4/4), the full Python suite green, the
  live full Node suite green with zero failures, and git diff --check
  clean. H03 depends on H01; the sealed H01-0001 attempt is the build
  dependency and H02-0001 is a sealed PASS regression baseline.
- Residual limitations: H03 attests static declarations and their
  fail-closed handler bindings only. It does not claim an implemented hook
  runner, plugin-manifest registration, runtime policy or receipt
  execution, host capability probing, degraded-mode behavior, runtime
  expected identity/count reconciliation, adapter integration, exhaustive
  enforcement, or packaged runtime integration, and this review is not
  external actor-independent certification.
