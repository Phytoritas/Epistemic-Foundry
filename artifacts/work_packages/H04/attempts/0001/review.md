# H04-0001 independent review of bounded-agent work

- Author: the bounded implementation agent(s) (H04 maker) that authored
  the capability-probe module
  packages/plugin-host/src/capability-probe/capability-probe.mjs and its
  two compatibility test suites
  tests/compatibility/hooks/hook-feature-probe.test.mjs and
  hook-degraded-mode.test.mjs, plus the Node contract harness
  h04-capability-probe-tests.mjs under
  artifacts/work_packages/H04/attempts/0001/. Reviewer: the seal-prep
  session, a distinct actor that did not author this attempt. Author/
  reviewer separation holds (actor_independence=true); external
  actor-independent certification does not.
- Mode: INDEPENDENT_REVIEW_OF_BOUNDED_AGENT_WORK. Blocking findings: 0.
- Scope: the manifest write scope is
  packages/plugin-host/src/capability-probe/** and
  tests/compatibility/hooks/** plus artifacts/work_packages/H04/**. The
  three product files are hash-pinned and decode as BOM-less UTF-8. No
  src, schema, manifest, harness outside H04, or .rah/ state was touched,
  and the mutation counters are all zero.
- Exit criterion 1 - unsupported coverage explicit: VERIFIED.
  hook_feature_probe_test (11/11) asserts missing observations fall to
  UNKNOWN rather than optimistic support, empty hook-event and tool
  scopes never prove FULL, unobserved hosted tool paths stay explicit,
  and unsupported claims, forged hook-trust, undeclared capabilities, and
  hostile/non-plain inputs (proxies, accessors, sparse arrays) each fail
  closed. Reports are schema-shaped, hash-bound, and deeply frozen.
- Exit criterion 2 - changed hooks require re-trust: VERIFIED.
  hook_feature_probe_test asserts changed active hook bytes, removed hook
  hashes, and disabled-but-changed hooks each force exact re-trust
  (state UNKNOWN, HOOK_RETRUST_REQUIRED, stale/untrusted hash detail), and
  hook_degraded_mode_test (7/7) asserts re-trust debt is visible in the
  PluginHealthReport and cannot be masked as FULL, that the strongest
  declared degraded mode (DEGRADED/READ_ONLY/SAFE_MODE) is selected, and
  that a required capability without a declared fallback is BLOCKED.
- Maturity boundary (the crux, honestly disclosed). H04 supplies a
  BOUNDED OBSERVATION PROJECTION only. The capability-probe module is a
  pure function over supplied observations (it imports node:crypto and
  node:util and the sealed H01 gateway canonicalizer; it performs no
  node:fs or child_process live host I/O). The plugin manifest
  plugins/epistemic-foundry/.codex-plugin/plugin.json carries no hooks key
  and an empty interface.capabilities, and
  plugins/epistemic-foundry/dist/hook-runner.mjs is ABSENT. Live
  cross-host discovery, runtime hook-runner registration, and hosted-tool
  interception are H05/H06/X01/G06 scope and are correctly NOT claimed
  executable: this is a specified-not-yet-implemented posture, not a
  weakening of the gate.
- Gates at review time: capability-probe-tests 18/18
  (hook_feature_probe_test 11/11, hook_degraded_mode_test 7/7), the full
  Python suite green, the live full Node suite green with zero failures,
  and git diff --check clean. H04 depends on H02 and H03; both sealed
  PASS attempts are bound as build dependencies.
- Residual limitations: H04 projects bounded observations and attests
  its trust/coverage/degraded-mode logic only. It does not claim a live
  cross-host discovery adapter, exhaustive enforcement from observed
  hooks, runtime hook-runner registration, hosted-tool interception,
  evolution/holdout observability, packaged runtime integration, or
  release readiness, and this review is not external actor-independent
  certification.
