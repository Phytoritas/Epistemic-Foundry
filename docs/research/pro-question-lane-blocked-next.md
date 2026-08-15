# Epistemic Foundry v4 — next implementation decision

This is a fresh conversation. The previous one grew too long to continue.
Prior context is summarised below; treat it as established fact, not as a
question.

## What this repository is

`MASTER_SPEC.md` describes Epistemic Foundry v4: a Codex plugin plus a
contract-first kernel for evidence-gated research. The bundle is currently a
SPEC_BUNDLE / REFERENCE_BLUEPRINT — most contracts exist as schemas, manifests,
and workflows; only some have running implementations. The goal of this work is
to close the gap between the contracts and actually running code, one bounded
work package at a time, without inventing shared contracts.

Authority order: `MASTER_SPEC.md` > `manifests/development_manifest.yaml` >
`manifests/acceptance_matrix.yaml` > `manifests/product_invariants.yaml` >
`schemas/*.schema.json` and `workflows/*.workflow.yaml` > work-package notes.
When a lower source contradicts a higher one, the correct action is to stop
with `SPEC_GAP` rather than to invent a missing contract.

## What was just completed (verified by running it)

A previous decision of yours in the old conversation was: the eleven-lane
retrieval contract had a state-representation defect, not a missing fourth
lane. A lane the query plan **selected** but no backend can serve was being
reported as `UNSEARCHED`, which is the state reserved for lanes the plan
**declined**. That collapsed an unmet obligation into a deliberate scope
decision, and the O06 completeness gate then refused the whole chain with
`WORK_CLASS_LANE_RULE_VIOLATED`.

Implemented and verified since:

- `manifests/development_manifest.yaml`: O02's `write_scope` declared
  `python/epistemic_foundry/retrieval/lanes/**`, but the real code lives at
  `src/epistemic_foundry/retrieval/lanes.py`. Added the two real paths
  (`lanes.py`, `search_state.py`). No broad `src/epistemic_foundry/retrieval/**`
  grant.
- `src/epistemic_foundry/retrieval/search_state.py`: the four-value coverage
  vocabulary and the six-value receipt wire vocabulary are now named separately
  (`RECEIPT_STATE_*`, `BLOCKED_STOP_REASONS`, `PARTIAL_STOP_REASONS`). The
  `SearchState` enum still has exactly four members, so EF4-I05 and the O05
  `coverage_state` projection are unchanged.
- `src/epistemic_foundry/retrieval/lanes.py`: added `blocked_lane_receipt` and
  `blocked_lane_result`. A selected-but-unservable lane now seals an EXECUTION
  receipt with `search_state: BLOCKED`, `stop_reason: backend_unavailable`,
  non-empty `errors`, null result fields, and the query batch it would have run
  (the schema requires `query_text`/`query_hash` on non-UNSEARCHED receipts, and
  a blocked receipt that named no query would not say what went unanswered).
  `reconcile_lanes` now also reports `receipt_states` and `blocked_lanes`.
- `src/epistemic_foundry/cli/main.py`: `retrieve query --lane <x>` gained
  `--lane-selected`. Without it an unserved lane is still the UNSEARCHED
  sentinel; with it the lane gets the BLOCKED receipt and must supply
  `--expression`.
- No change was needed inside O06's `gate.py`: it already converts a required
  lane's BLOCKED state into `completion_state: BLOCKED` and caps the ceilings.

Verified by actually running the chain (snapshot → boundary → plan → CLI lane
execution → certificate), not by reading code:

- E1 plan with `lexical, semantic, citation, temporal` selected, of which only
  lexical and citation have backends → 11 receipts, and a sealed certificate
  with `completion_state: BLOCKED`, `blocked_lanes: [semantic, temporal]`,
  `completed_lanes: [lexical, citation]`, 7 UNSEARCHED sentinels,
  `absence_claim_ceiling: NONE`, `novelty_claim_ceiling: NOT_ASSESSED`.
- Making temporal genuinely complete still yields BLOCKED because of semantic
  alone.
- The seven unselected lanes are exactly one SENTINEL receipt each, with every
  execution field null — no backend was called.
- E0 with searched lanes is still refused (`CERTIFICATE_REFUSED`).
- Replaying the same inputs reproduces the identical `certificate_hash`.

No semantic lane was faked, no embedding or network dependency was added, no
MCP change was made, and `PACKAGE_MANIFEST.json` was not touched.

## Current state of the plugin, honestly

- The plugin loads: `plugin.json` registers `skills/` and `.mcp.json`, and
  `plugins/epistemic-foundry/dist/mcp-server.mjs` is a self-contained Node stdio
  MCP server that needs neither the checkout nor Python.
- It advertises the canonical 13-tool T01 catalog. Exactly three are bound to
  real observation: `foundry.status`, `foundry.health`, `foundry.map.query`.
  The other ten answer `UNAVAILABLE` rather than a plausible fake.
- Local retrieval works end to end through `efoundry retrieve build/query`:
  three lanes (`lexical`, `citation`, `entity_variable`) have real backends over
  a SQLite FTS5 index; the other eight do not.
- Skills exist and are discoverable; two of them now state plainly that their
  producer does not exist yet.

## The decision I need

Given the above, what is the single highest-value next implementation step, and
why that one rather than the obvious alternatives?

Candidates I can see, but I do not want you to simply rank my list — tell me if
the right answer is outside it:

1. Bind more of the ten `UNAVAILABLE` MCP tools to real producers, so the
   plugin does more than observe itself.
2. Implement the `temporal` lane properly, which needs a real publication-date
   and correction/retraction field that the corpus does not currently carry.
3. Implement `counterevidence`/`null`/`boundary`/`method` — the adversarial
   lanes EF4-I06 calls mandatory whenever applicable — which currently have no
   extraction path at all.
4. Move up the stack instead: make one full evidence→claim→promotion path run
   for a single trivial claim, even if narrow, so the constitution's central
   guarantee (a promoted Claim resolves to immutable source evidence) is
   demonstrated once rather than described.
5. Something else entirely that the contracts make more urgent.

Constraints on your answer:

- Name one step, not a roadmap. State the exact files/packages it touches and
  which manifest work package owns them.
- If it requires a shared-contract change, say so explicitly and name the owner
  package, because that is a `SPEC_GAP` I must stop on rather than improvise.
- Do not propose adding an embedding model, a network dependency, or any
  external service; local determinism is a hard constraint.
- Assume I will verify by running the real chain, so tell me the specific
  observable outcome that would prove the step actually worked, and the
  specific outcome that would prove it only appeared to work.
