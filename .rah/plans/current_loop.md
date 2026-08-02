# Current Loop

## Earliest Restart Point
Stage 0. Source intake for the Epistemic Foundry v4 spec bundle

## Read First
- `AGENTS.md` (Epistemic Foundry v4 bundle; authoritative)
- `MASTER_SPEC.md`, then `manifests/development_manifest.yaml`
- `.rah/state/status.json`
- `.rah/state/gates.json`
- `.rah/memory/wakeup.md`

## Next Actions
Done during setup (2026-07-27): doctor + status surfaces run, Memento context/recall
hydrated and fed back, repo-local `AGENTS.md` confirmed present.

1. Register the real goal and source binding:
   `rah run <repo-root> --goal "<objective>" --source MASTER_SPEC.md`
   (or the specific work package from `manifests/development_manifest.yaml`).
2. Work coverage rows one at a time; record evidence/validation/semantic/provenance/negative-test.
3. Perform current-system recon against the v4 bundle and update `00_workspace_audit.md`.
4. Keep implementation blocked until acceptance, coverage, validation, review, and closeout are honest.

## Repo-specific constraints
- The bundle is a SPEC_BUNDLE / REFERENCE_BLUEPRINT: do not claim runtime, search,
  ledger, MCP, or UI components are implemented merely because contracts exist.
- Bundle authority order (`MASTER_SPEC.md` first) outranks the harness overlay at
  `.rah/runtime/AGENTS.overlay.md`; conflicts stop with `SPEC_GAP`.
- `PACKAGE_MANIFEST.json` verifies clean against `MANIFEST.sha256`; keep it that way.

<!-- RALPH MANAGED BLOCK START -->
## RALPH Goal Loop

- goal_id: `ralph-continue-epistemic-foundry-v4-0-0-under-product-owner-decision-hd-ef4-b04-sg002-20260730-001-preserve-b04-0006-projection-pass-and-package-spec-gap-plus-every-prior-attempt-report-review-command-receipt-rah-evidence-and-generation-and-the-dirty-worktree-in-the-primary-session-without-fleet-or-subagents-execute-serially-c03-0003-f04-0002-j02-0003-s04-0003-b04-0007-projection-and-regression-revalidation-c04-0002-full-conformance-b04-0008-final-packaging-then-recompute-the-156-package-dag-and-continue-dependency-ready-packages-until-the-verified-external-goal-is-terminal-keep-completion-ready-false-until-all-objective-gates-pass`
- status: `done`
- iteration: `1` / `12`
- completion_mode: `exhaustive`
- checkpoint_required: `False`
- loop_phase: `bounded-implementation`
- state: `done`
- implementation_gate: `fail`
- completion_ready: `True`
- review_status: `approved`
- missing_closeout_ids: `[]`
- blocked_reason: `None`

### Next Actions

- No remaining RALPH gate work; closeout, review, source coverage, and driver terminal state are complete.
- If /goal is active, mark it complete after final audit acceptance.

### State

- `.rah/ralph/goal.json`
- `.rah/ralph/loop_state.json`
- `.rah/ralph/evidence_ledger.json`
- `.rah/ralph/plan_graph.json`
- `.rah/ralph/goal_bridge.json`
- `.rah/ralph/review_gate.json`
- `.rah/ralph/iterations/`
<!-- RALPH MANAGED BLOCK END -->
