# Epistemic Foundry v4 — four blocked authority carriers, one ratification order

We are continuing implementation against `MASTER_SPEC.md` in the current dirty
workspace. Authority order is `MASTER_SPEC.md` > `manifests/development_manifest.yaml`
> `manifests/acceptance_matrix.yaml` > `manifests/product_invariants.yaml` >
`schemas/*.schema.json` and `workflows/*.workflow.yaml` > `manifests/role_registry.yaml`.
Do not propose fake receipts, convenience wrappers, or any path that bypasses
that order. Do not treat prior work-package PASS reports as proof of runtime
reachability.

## What just landed (context, not the question)

A read-only census reproduced, with concrete values, a repeated defect class:
validators that check a digest's *shape* but never re-derive it, so tampered
content re-sealed under a recomputed hash passes. Six instances are now fixed
in-scope, each verified by direct probe:

- `parliament-view.mjs` — a tampered adjudication displayed `NO_OVERRIDE_ATTEMPT`;
  the three canonical self-hashes are now re-derived.
- `aporia-view.mjs` — a graph with an unresolved objection displayed `RESOLVED`;
  `graph_hash` is now re-derived.
- `passport-view.mjs` / `aporia-view.mjs` — an arbitrary non-canonical `scope`
  field survived into the returned read model; both now validate the canonical
  20-field `ScopeVector`.
- `replay/drift.mjs` — `sealDriftReport` trusted the caller's `drift_class`; a
  path `classifyDifference` calls `UNCLASSIFIED` was sealed as
  `REPRODUCIBLE_WITH_STRICT_DRIFT`. Every record's class is now re-derived.
- `v4_f06/gate.py`, `v4_k06/gate.py` — tampered `ForgeSession.state_hash`,
  `ReplayReport.report_hash`, and search-lane receipt identity now refuse.
- `evolution_authority/nodes.py` — an unrelated `ArtifactReceipt`
  (`EVIL-ARTIFACT`) passed the "promotion pack receipts verified" node; the pack
  is now hardened (set_hash, phase E, completeness, core kinds, VALID status)
  and the receipt must resolve the pack triplet exactly.

## The actual question

Four separate blockers stopped, each independently, at the *same shape of
missing thing*: a canonical carrier that binds authoritative evidence to the
decision that consumes it. In every case the local code cannot proceed without
inventing a shared contract, so it fails closed instead.

**A05 — gate evidence carrier.** `_gate_node` returns the caller's `GateDecision`
unchanged for G01–G11 and G13. Verified: a genuine `FAIL` flipped to `PASS` with
a fabricated evidence ID and a recomputed `decision_hash` yields a
self-consistent `PROMOTE CANDIDATE`. `schemas/node-invocation.schema.json` is a
closed 12-field object carrying artifact **IDs only** — no bodies, no
type-to-ID map, no trusted resolver — so no gate can recompute its own verdict.
`schemas/gate-decision.schema.json` also does not pin `gate_id` stability,
evaluation time, reason/evidence ordering, or the `input_hash` rule, so even a
correct semantic recomputation could not assert byte-equality. G14 is worse:
the workflow says it emits a `GateDecision` but its output schema and actual
return are an `EffectReceipt`, and its evidence only exists *after* commit,
while the shared contract demands it *before*.

**N03 — effect-receipt resolution.** The scheduler admits any non-empty string
as `terminal_receipt_id` / `effect_receipt_ids`. Verified: `"NOT-A-RECEIPT"`
drives an effectful node to `SUCCEEDED`, and the checkpoint runtime then seals
`replay_verified: true` with `pending_effect_ids: []`. But `EffectReceipt`
carries `intent_id` and `run_id` and **no** `node_id` or `attempt_id`, while a
scheduler attempt carries `run_id`/`node_id`/attempt-number and no `intent_id`.
E02's only public read is `readReceipts(intentId)`. There is also no canonical
type for `terminal_receipt_id` and no transition-to-status matrix. A
fail-closed resolver added to N03 alone would also halt every W02 checkpoint
seal and resume, which call the scheduler with no resolver.

**W04 — run reference inventory.** `buildAuditExport` reconciles against an
authoritative `referenced` input, but the stored export keeps only the *derived*
reconciliation. `validateAuditExport` therefore compares the forger's numbers
against each other. Verified: deleting an entry and its `referenced_ids` mention,
then recomputing counts and `export_hash`, yields `complete: true`. Checkpoints
are not a substitute — `artifact_ids` and `gate_decision_ids` are caller-supplied,
not derived from canonical state. The ledger has a real hash chain but no
inventory projection, and `verifyRun()` does not produce the four export sections.

**Q05 — selective-inference provenance.** Schema validation, `report_hash`
re-derivation, and risk→recommendation consistency now land. The residue:
`winner_curse_risk_for` derives risk from `candidates_considered` and
`replication_count`, and the canonical report — `additionalProperties: false`,
11 required fields — persists **neither**. So an honest `low/ALLOW` and a
re-sealed forgery of a true `high/BLOCK` are byte-identical to Q05. Verified:
both produce report hash `sha256:a7be7855…`.

## What we need from you

Name the **one** shared authority decision to ratify first, judged by how much
genuinely dependency-ready runtime work it unlocks per unit of contract change,
without weakening any Foundry invariant.

Please be concrete about:

1. **Which decision, and why it dominates the other three.** If two of these
   four are actually the same missing carrier wearing different names, say so
   plainly — that would change the sequencing.
2. **Owner and write path.** `C01` is the canonical schema authority but its
   current write_scope does not include `schemas/node-invocation.schema.json`,
   and it declares a dependency on `A05`. Say exactly which manifest entries and
   dependencies must move, and whether that creates a cycle.
3. **The carrier's shape**, in enough detail to implement: what binds to what,
   what is re-derived versus supplied, and what must fail closed. We would
   rather have one narrow correct carrier than a general resolver framework.
4. **The interim posture.** Until ratification, should A05's G01–G13 be changed
   from silent pass-through to explicit fail-closed `SPEC_GAP` stubs? That
   removes a live forged-`PROMOTE` path but will stop existing integration
   fixtures. Is that the right trade, or does it break something we should
   preserve?
5. **What this does NOT fix.** Name the blockers that will still be blocked
   after your recommended decision ships, so we sequence honestly.

One recommendation only. Prefer refusing to answer over inventing a contract
that the authority order does not support.
