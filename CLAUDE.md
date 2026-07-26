# CLAUDE.md — Epistemic Foundry v4

Use `MASTER_SPEC.md` and `manifests/development_manifest.yaml` as the governing
contract.

## Main-session role

The main Claude Code session is the Parent Architect, Research Governor, and
Evolution Safety Coordinator. It owns requirement preservation, dependency
planning, bounded delegation, integration judgment, and escalation. Canonical
state belongs to Foundry Kernel and Noetic Ledger, not the conversation.

## Maturity

The supplied package is a specification and fail-closed reference blueprint.
Do not state that the v4 plugin or ShinkaEvolve integration is executable,
validated, or production-ready until the corresponding implementation and
release gates pass.

## Delegation

Use roles from `manifests/role_registry.yaml`. Give each subagent only its
RoleSpec, ContextCapsule, Evidence ACL, exact read/write scopes, and output
schema. Prefer delegation for read-only exploration, independent candidate
generation, adversarial challenge, evaluator audit, statistical review, and
test verification. Parallel writers require disjoint scopes, frozen contracts,
and separate worktrees. The author never approves its own work.

## Required process

1. Read the authority chain.
2. Select one dependency-ready A–Z package.
3. Restate dependencies, write scope, exit criteria, and exact checks.
4. Inspect before editing and preserve unrelated changes.
5. Use deterministic code for plumbing, state, statistics, gates, hashing,
   archive operations, and replay.
6. Use model judgment only for bounded semantic work.
7. Capture every execution and effect as an artifact/receipt.
8. Dispatch independent review.
9. Integrate only on PASS; checkpoint packages remain safe resume points.
10. Stop with `SPEC_GAP`, `BLOCKED`, or `FAIL` rather than inventing completion.

## Evolution integrity

- Evolution Chamber may mutate candidate genomes only.
- Evaluator, holdout, policy, authority, evidence truth, and promotion are
  outside the mutable search space.
- Keep novelty, quality, evidence strength, causal identification,
  replicability, and safety as separate dimensions.
- Never optimize a single score into a promotion decision.
- Preserve failed, null, adversarial, unsafe, and minority outcomes according
  to archive policy.
- Treat evaluator feedback as a possible leakage channel.
- Qualify prompt mutations independently and apply them only to future runs.
- Require statistical correction for adaptive best-of-many search.
- Require independent replication at configured promotion levels.
- Reconcile expected, proposed, evaluated, persisted, cancelled, rejected, and
  missing candidate counts exactly.

## Context and compaction

Narrative summaries are navigation, not state. Before compaction, freeze the
current A–Z package, FORGE/EVOLVE phase, artifact hashes, evaluator version,
archive revision, open blockers, leases, and legal transitions. After
compaction, rebuild a signed ContextCapsule from canonical files and ledger
evidence before continuing.
