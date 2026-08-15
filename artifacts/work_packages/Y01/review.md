# Y01 package review record

Standing verdict: `PASS` (from attempt `0001`).

This file is the package-level projection the manifest requires. The
attempt review below, at `attempts/0001/review.md`, is the primary record.

---

# Y01-0001 independent review of bounded-agent work

- Author: the bounded implementation agent that wrote
  packages/foundry-kernel/src/budget. Reviewer: this seal-prep session, a
  distinct actor that did not author the budget subsystem. The author
  never approves its own work, so actor_independence HOLDS for this
  review; external actor-independent certification does NOT, and no such
  claim is made. Y01 is risk_class=high; the two exit criteria -- typed
  budget states truthful, and fan-out bounded -- were attacked on their
  contracts rather than skimmed.
- Typed budget states are truthful. The enforcement vocabulary is composed
  from the sealed @epistemic-foundry/contracts BudgetEnvelope contract
  whose source is schemas/budget-envelope.schema.json, never restated;
  only the HARD_ prefixed labels (HARD_METERED, HARD_PREALLOCATED) bound
  spend, and the composed source_sha256 tracks the canonical schema bytes.
  A hard meter that would push any cumulative dimension (tokens, calls,
  wall_seconds, storage_bytes, network_bytes) past its declared limit
  throws BUDGET_LIMIT_EXCEEDED and leaves usage unchanged, so the refusal
  is neither truncated nor partially applied. SOFT_ESTIMATE records a
  forecast and UNMETERED records nothing; both report spend_bounded=false
  and never refuse, so a non-bounding state cannot masquerade as a limit. A
  mislabelled envelope -- a hard bound with no hard limit, or an UNMETERED
  budget carrying a CANCEL breach policy that has no meter to breach -- is
  refused at seal time (BUDGET_ENVELOPE_INVALID), and a tampered budget_hash
  (BUDGET_HASH_MISMATCH) or tampered contract (BUDGET_VOCABULARY_INVALID)
  is rejected. No fabricated budget state was found.
- Fan-out is bounded by construction. The adaptive fleet sizes workers as
  target_workers = clamp(backlog, min_workers, effective_max_workers). The
  effective maximum is the declared max_workers capped by the budget's
  concurrency hard limit whenever spend is bounded; a fleet that declares
  more workers than a bounding concurrency limit permits is REFUSED
  (FLEET_BOUND_EXCEEDS_BUDGET), not silently clamped, and an explicit
  worker request outside the [min, effective_max] window is refused
  (FLEET_BOUND_EXCEEDED). An unbounded backlog (plan(1000)) cannot raise
  the target above the budget-bounded maximum, so the fleet size is derived
  and capped, never unbounded. An advisory (SOFT_ESTIMATE) budget imposes
  no concurrency cap but is still bounded by the declared max_workers.
- No authority acquired. Both the meter and the fleet emit only
  deterministic, re-derivable receipts of counts and hashes; a fleet plan
  receipt is plain frozen data with exactly the count/hash keys and no
  lease or capability grant, and neither component mints leases nor mutates
  external state.
- Dependency and checks: the subsystem builds on the sealed B04 (B04-0002),
  D04 (D04-0001), Q04 (Q04-0001), W04 (W04-0001) and X04 (X04-0001) PASS
  attempts and adds no new production dependency. Ruff lint and format, the
  two required checks (budget_enforcement_test 12/12, adaptive_fleet_test
  8/8), targeted 20/20, full Python 1261/1261, full Node 1253/1253 across
  111 files, and git diff --check all pass with zero failures.
- Residual limitations: Y01 provides typed budgets, the adaptive fleet, and
  their in-process performance controls; observability and SLO telemetry
  (Y02) and backup/recovery runbooks (Y03) build on this package and are
  out of scope here. Verdict: PASS on the exact Y01 package contract.
