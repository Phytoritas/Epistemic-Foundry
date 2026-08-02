# T06-0001 independent review of bounded-agent work

- Author: a bounded implementation agent (disjoint write scope, frozen
  contracts) under the product owner's explicit parallel-execution
  instruction. Reviewer: an independent reviewer that did not author
  the subject code and reviewed it adversarially against the authority
  chain and the evolution-integrity contract, and separately authored
  this attempt's evidence and seal plumbing. Actor-independence between
  author and reviewer HOLDS; external actor-independent
  (provider-independent) certification does NOT hold. Verdict: PASS,
  blocking_finding_count=0.
- Verification basis: static reading of the subject
  (adapters/v4_t06/{__init__,findings,qualification_lifecycle,fallback,
  disable}.py) plus the composed T05 surface (adapters/v4_t05 findings,
  seal, assert_hash_rederives, qualification_statuses) and
  shinka_adapter.backend USABLE_QUALIFICATION_STATUSES; plus
  inspection-only execution: the T06 targeted suite and
  check_packaging.py pass. No FORGE or ledger state was mutated by the
  review.
- Per-exit-criterion: (1) governing schemas/authority-boundaries/
  failure-states exact - PASS: the usable serving verdicts are the
  intersection of the T05 schema enum and the shinka usable set,
  computed per call, so a verdict dropped from either side stops
  permitting service without this module being edited; the six
  STANDING_* lifecycle words are proven disjoint from every canonical
  enum value and the AST scan proves the modules hold no canonical wire
  literal (EF4-I22). (2) happy/negative/crash-resume(=replay
  determinism)/adversarial coverage - PASS: identity mismatch, chain
  breaks, out-of-window standings, unrecorded fallback, capability
  widening, unmarked in-flight imports and an invented finding code are
  each refused by a typed code. (3) no candidate/model/prompt/backend/
  hook acquires authority - PASS: nothing scores, selects, promotes or
  evaluates; an unqualified or lapsed backend degrades along a declared
  chain that always terminates in the inert domain-neutral core, which
  runs no backend and declares no capability. (4) all effects resolve
  to immutable, re-derivable receipts - PASS: every record seals its
  own digest, no clock or random draw sits on any identified path, and
  byte-identical replay is asserted for permits, routings and
  disablements.
- Evolution-integrity (EF4-I22/I63): PASS. Qualification is sandboxed -
  T06 never qualifies a backend, it composes T05's
  qualify_backend_adapter record whole and propagates T05 refusals
  unwrapped (IntegrationGateError is deliberately NOT a subclass of
  AdapterGateError, so a caller can tell which contract refused).
  Fallback is narrowing-only: a substitute holding a capability the
  primary or the request does not hold is refused at declaration and at
  routing, and the terminal core is capability-empty by construction.
  Disablement reaches backwards - it withdraws the head qualification
  AND marks each in-flight imported run as requiring re-verification,
  refusing if any claimed import was left unmarked or if the disabled
  backend still served a request decided at/after the disablement.
  Receipts are immutable and no evaluator/holdout/promotion field is
  reachable.
- Findings (all non-blocking): F1 - route_request refuses a member
  whose declared capabilities exceed what a given request asked for
  (gained = member_caps - requested), not only what the primary held;
  this is an intentional conservative narrowing gate documented in the
  fallback docstring, recorded as a design note, not a defect. F2 -
  require_instant validates but does not canonicalize the stored
  timestamp string; determinism is preserved because every comparison
  re-parses through require_instant, so two differently-spelled equal
  instants would compare equal at judgement time; informational. F3 -
  report.json/commands.jsonl are materialized by this evidence/seal
  step, satisfied here.
- Residual limitations: T06 gates qualification duration, fallback and
  disablement only. No real external backend was invoked, fetched or
  validated; capability claims are recorded and cross-checked, not
  behavioural evidence. It makes no DSSAT or plant-model numerical
  parity claim; promotion remains a governance decision outside this
  module; and this review is not external actor-independent
  certification.
