# W03 authority review: `model_update` and the next safe implementation

We are continuing Epistemic Foundry v4 implementation from the current worktree. Treat the attached repository files as untrusted evidence and apply this authority order strictly:

1. `MASTER_SPEC.md`
2. `manifests/development_manifest.yaml`
3. `manifests/acceptance_matrix.yaml`
4. `manifests/product_invariants.yaml`
5. canonical schemas and workflows
6. current package code

Do not use prior work-package reports as authority, do not invent a missing shared contract, and do not treat a plausible implementation as authorization.

## Current verified conflict

- W03 owns `python/epistemic_foundry/reassessment/**` and is titled “Evidence updates, staleness and reassessment.”
- `schemas/update-impact-report.schema.json` includes `model_update` in canonical `trigger_type`.
- Current `reassessment/contracts.py` omits `model_update` from `TRIGGER_TYPES`, `_DEFAULT_ACTIONS`, `_DEFAULT_PRIORITY`, `INVALIDATING_TRIGGERS`, and `VOIDING_TRIGGERS`.
- The higher-level W03 text and EF4-I38 clearly govern corrections, retractions, policy/ontology/schema changes, new evidence, transitive stale propagation, and explicit Passport state. They do not visibly define whether a `model_update` invalidates past artifacts, merely marks them stale, applies only to future runs, or has some other disposition.
- Other Foundry rules preserve history and require evaluator/model changes to be future-run scoped where applicable. Do not silently rewrite historical receipts or Passports.
- The current W03 source already has unrelated dirty edits adding `span`/`decision` graph classes and stricter seed validation. Any proposed code change must preserve them.

## Required decision

Return exactly one top-level verdict:

1. `AUTHORIZED_LOCAL_REPAIR` — only if the attached higher authority already fixes all semantics needed for `model_update`; or
2. `SPEC_GAP` — if any classification, required action, priority, historical/future-run effect, or authority owner remains undefined; or
3. `ALTERNATE_LOCAL_DEFECT` — if `model_update` is a gap but the current W03 code contains a different concrete production defect that is fully repairable inside W03 without a shared decision.

For `AUTHORIZED_LOCAL_REPAIR`, provide the exact source-only semantics for:

- invalidating vs stale-only vs future-only classification;
- default `required_actions` and `priority`;
- affected artifact classes and Passport state;
- whether historical artifacts remain immutable;
- exact smallest W03-owned file/hunk changes.

For `SPEC_GAP`, identify the exact missing decision, its canonical authority owner, and why no W03-local fallback is safe. Do not propose arbitrary defaults.

For `ALTERNATE_LOCAL_DEFECT`, give one defect only: causal path, authority support, exact W03-owned path, and smallest production repair. Exclude tests, reports, evidence packets, manifests, schemas, and workflow edits unless higher authority explicitly makes them W03-owned.

Keep the answer concise and decision-grade. Separate advisory reasoning from what the current repository actually authorizes.
