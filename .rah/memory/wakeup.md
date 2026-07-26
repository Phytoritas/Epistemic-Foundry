# Wakeup Packet

## Identity
- workspace: `epistemic-foundry`
- topic: `architecture-refactor`
- sessionId: `epistemic-foundry#adhoc:bootstrap`
- caseId: `case/epistemic-foundry/adhoc/generic`
- issue: `adhoc`
- branch: `unknown`

## Current State
- current_stage: `bootstrap-complete` (setup verified 2026-07-27)
- implementation_gate: `blocked` (intentional: no RALPH goal registered yet)
- agents_and_workflow_gate: `pass` (Epistemic Foundry v4 bundle `AGENTS.md` is authoritative)
- memory_freshness: `hydrated` (context 23 fragments, recall searchEventId 88182, feedback 3755)

## Read First
1. `AGENTS.md` (bundle; authority order starts at `MASTER_SPEC.md`)
2. `MASTER_SPEC.md`, then `manifests/development_manifest.yaml`
3. `.rah/plans/current_loop.md`
4. `.rah/state/status.json`
5. `.rah/state/gates.json`

## Memento Start Recipe
```python
context(types=["preference", "procedure", "error", "decision"], workspace="epistemic-foundry", sessionId="epistemic-foundry#adhoc:bootstrap")
recall(
    keywords=["epistemic-foundry", "architecture-refactor", "unknown", "issue-adhoc"],
    topic="architecture-refactor",
    workspace="epistemic-foundry",
    sessionId="epistemic-foundry#adhoc:bootstrap",
    caseMode=True,
    depth="standard",
    contextText="bootstrap -> recon -> architecture intake"
)
```

## Feedback Reminder
If recall results are useful or misleading, record `tool_feedback()` and update `.rah/memory/memento_feedback.json`.
