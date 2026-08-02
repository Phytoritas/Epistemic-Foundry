# S01-0001 independent review of bounded-agent work

- Author: the bounded implementation agent that wrote
  packages/foundry-kernel/src/security/trust. Reviewer: this seal-prep
  session, a distinct actor that did not author the trust boundary. The
  author never approves its own work, so actor_independence HOLDS for this
  review; external actor-independent certification does NOT, and no such
  claim is made. S01 is risk_class=critical, so the boundary was attacked
  on its evidence-is-not-instruction, no-self-authorization, and
  explicit-authority-crossing contracts rather than skimmed.
- Evidence cannot become instruction. Every untrusted source kind maps to
  the EVIDENCE_DATA or MODEL_OUTPUT plane and seals with a frozen
  disposition in which instructionEligible and authorityEligible are false.
  The DATA_ONLY_USE allowlist is transforms only (quote, parse, extract,
  summarize, analyze, classify, index, cite); assertDataOnlyUse denies any
  other requested use -- including 'instruction' and 'alter_policy' -- with
  UNTRUSTED_USE_DENIED. assembleDataOnlyContext returns a frozen data-only
  context that carries evidence and model-output plane identity but exposes
  neither an instruction nor a messages field. A NO_SIGNAL scan and a
  'trusted' extraction label never upgrade the plane.
- Model output cannot self-authorize. denyUntrustedAuthorityRequest returns
  a frozen DENY with reasonCode UNTRUSTED_ORIGIN and empty
  capabilityGrantIds, approvalRecordIds, policyDecisionIds,
  phaseTransitionIds, and instructionIds for every request type, including
  the unknown-future 'unknown_future_authority_action'. The decision does
  not inspect the content, so a JSON-shaped self-approval carrying
  capability_grant_ids, policy_decision_ids, and phase_transition_ids is
  denied exactly like plain prose. Sidecar role, approval, capability,
  policy, or phase fields beside the content are rejected with
  UNEXPECTED_FIELD; the module exports no capability-grant, policy-mutation,
  phase-change, execution, or approval API at all.
- A trust-zone crossing needs explicit authority the module never provides.
  There is no promotion API. Segments are sealed with a runtime-private
  WeakMap brand, so a shallow copy or a JSON round trip is denied with
  UNSEALED_CONTENT before scanning, data-use, or context assembly. Unknown
  or forged source kinds (host_instruction, plugin_control, managed_policy)
  fail closed with UNKNOWN_SOURCE_KIND. Proxy records and Proxy arrays are
  rejected with PROXY_INPUT_DENIED via the trap-free node:util.types.isProxy
  predicate, and accessor-bearing record fields and array elements are
  denied by descriptor-only reads, so none of an attacker's prototype,
  ownKeys, descriptor, getter, or Symbol.toPrimitive hooks executes during
  validation.
- Dependency and checks: the boundary is a pure ESM module that imports only
  node:util and adds no new production dependency. It builds on the sealed
  A04 and B01 packages (A04-0001 PASS, B01-0001 PASS), which are
  report-level dependencies rather than imported code. Ruff lint and format,
  the two required checks (prompt_injection_suite 8/8,
  authority_escalation_test 9/9), targeted 17/17, full Python 1261/1261,
  full Node 1253/1253 across 111 files, and git diff --check all pass with
  zero failures.
- Residual limitations: prompt-injection signal matching is advisory and
  intentionally does not claim exhaustive linguistic detection; origin-based
  authority denial is the enforcement boundary. The primitive is not yet
  wired through every provider, corpus-ingest, context-capsule, execution,
  or release path, and the private scaffold has no declared public export
  map; those runtimes and the S04 red-team integration are later scope.
  Verdict: PASS on the exact S01 package contract.
