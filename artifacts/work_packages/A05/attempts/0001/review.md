# A05-0001 independent review of bounded-agent work

- Author: the bounded implementation agent authored the product code
  (the evolution_authority package, the four A05 workflows and the
  three governance suites). Reviewer: the parent seal-prep session, a
  DISTINCT actor that did not author that product code and audited it
  adversarially against the authority chain. actor_independence between
  author and reviewer HOLDS; external actor-independent (provider-
  independent) certification does NOT. Mode:
  INDEPENDENT_REVIEW_OF_BOUNDED_AGENT_WORK. Verdict: PASS,
  blocking_finding_count=0.
- Evolution-integrity boundary (adversarial spot-checks, all HOLD):
  (1) evaluator, holdout, policy and promotion are OUTSIDE the mutable
  search space -- the chamber may mutate genomes only and delegates
  promotion to the canonical subworkflow (verify_evolution_chamber_
  binding PASS, 26 nodes); (2) NO single score becomes a promotion -- a
  scalar-only request (neg_008) resolves UNDERDETERMINED with
  granted_level=None; (3) novelty/quality/evidence/causal/replicability/
  safety stay separate dimensions in the gate set; (4) evaluator
  feedback is treated as a leakage channel -- G02 evaluator/holdout
  firewall and G07 validation-leakage are non-waivable and cannot be
  overridden by Parliament majority or approval (neg_006, neg_015,
  neg_018); (5) statistical correction and independent replication are
  enforced (neg_012 adaptive-statistics, neg_013/neg_014 replication
  ceiling); (6) G00-G14 are exact/ordered/non-waivable-where-specified/
  receipt-bound (verify_promotion_workflow_binding enforces ancestry,
  WAIVE is rejected, G14 completes only after receipt reconciliation);
  (7) exactly ONE node (commit_promotion_atomically, deterministic)
  holds promotion:commit AND is the only PromotionDecision emitter --
  the two llm nodes emit advisory adjudication/attestation only; (8)
  tampering fails closed (executor swap -> GATE_EXECUTOR_INVALID,
  llm PromotionDecision -> LLM_AUTHORITY_VIOLATION, dropped node ->
  node-count failure). These were re-proved structurally against the
  live impl and canonical workflow, independent of the test run.
- Per exit criterion: governing schemas/authority boundaries/failure
  states exact -- PASS; happy/negative/crash-resume/adversarial
  coverage (24 negative + 6 positive, replay and crash-then-reconcile
  in neg_022/neg_023) -- PASS; no candidate/model/prompt/backend/hook
  acquires evaluator/holdout/promotion authority -- PASS; all effects
  resolve to immutable receipts -- PASS; G00-G14 exact/ordered/non-
  waivable/receipt-bound -- PASS; evolution_promotion holds the exact
  23-node fail-closed sequence -- PASS; all 24 negative and 6 positive
  constitutional cases pass exactly -- PASS.
- OBS-A05-01 (non-blocking, disclosed): the manifest write_scope
  enumerates 13 discrete module filenames; the impl consolidated the
  same constitutional semantics into __init__.py + registry.py +
  nodes.py, all inside the permitted evolution_authority/ package. The
  enumerated list is the maximal writable surface (the package
  boundary), not a mandatory per-file split; write_scope_verification
  proves the package holds exactly those three modules and no file was
  written outside the A05 scope roots.
- OBS-A05-02 (non-blocking, disclosed): tests/governance/__init__.py is
  the mandatory parent-package marker one level above the
  tests/governance/a05/** grant; it carries no logic and is pinned.
- Regression scope: wire-literal re-proves the two new modules stay
  registered in the guard; the A03 boundary_cycle_policy_check re-proves
  the new evolution_authority package introduces no import-boundary
  cycle or layer inversion (PASS, no new cycle); full Python (1261) and
  full Node suites and git diff --check reproduce the repository gate.
- Residual limitations: runtime orchestration of the promotion workflow
  inside the kernel scheduler, evaluator qualification and live
  promotion of any real candidate are not claimed; this review is not
  external actor-independent certification; and the seal itself is left
  as sentinel-pinned prep (the six ledger pins are unresolved).
