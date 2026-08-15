# Decision needed: giving the 29 shipped skills an executable path

## What changed since the last turn

Your Option B recommendation was implemented and verified by live JSON-RPC
round trip from outside the repository:

- The packaged server now advertises the canonical thirteen-tool catalog
  statically.
- `foundry.status` and `foundry.health` return observed facts: real plugin
  manifest identity, real skill inventory count and seal, real advertised
  catalog hash, and, when `efoundry` is reachable, the real Python status
  including `canonical_schemas_loaded = 127`.
- The eleven unbound tools return an explicit `UNAVAILABLE` result envelope
  with `data: null` and `receipts: []`, distinct from `UNKNOWN_TOOL`.
- All four envelope shapes validate against
  `contracts/mcp/t01/foundry-mcp-tool-result.schema.json` with zero errors.
- Python is never started during `initialize`, `ping`, or `tools/list`.
- Absent bridge degrades to `UNAVAILABLE` with reason
  `"efoundry is not installed"`; present bridge reports `READY`.

I also confirmed your conservative call on the eleven tools was correct.
`NoeticLedger` is a hash-chained JSONL *event* store exposing only `events()`,
`tail()`, `length()`, `append()`, `verify()`, `is_intact()`. The canonical
`artifact-manifest.schema.json` requires seventeen fields including
`storage_uri`, `retention_class`, `confidentiality`, `encryption`, and
`provenance_manifest_id`. Binding `foundry.artifact.get` to the ledger would
require inventing all of them. No FORGE session store and no workspace map
snapshot producer exist in the runtime.

## The remaining gap

The plugin now loads, registers 29 skills, and reports its state truthfully.
But the 29 skills are prose with no executable path. Representative bodies:

- `foundry-observe`: "Compile search lanes from the framed claim. Register
  source versions and exact spans. Distinguish UNSEARCHED, SEARCHED_NONE,
  SEARCHED_WITH_RESULTS, and FAILED. Build a dependency-adjusted Evidence Pack
  and SearchCompletenessCertificate."
- `foundry-map`: "Freeze the input snapshot, inventory typed entities, extract
  edges, compute baseline structural metrics... Emit a WorkspaceMapSnapshot."
- `foundry-intake`: "Resolve goal, scope, constructs, corpus authority,
  success, and falsification... Emit an InsightCard, ScopeVector, QueryPlan
  inputs, and explicit blockers."

None names a command, tool, or file path. An agent that reads them learns the
epistemic discipline but has no way to reach the kernel.

Meanwhile the Python CLI genuinely performs work that some of these skills
describe. Verified subcommand table is exactly five: `status`, `schemas`,
`validate`, `ledger verify`, `retrieve build|query`. `retrieve query --lane`
already produces schema-valid `retrieval-candidate` objects and a sealed
`search-lane-receipt`, and reconciles lanes with explicit `UNSEARCHED`
sentinels for the eight lanes it does not serve. That is very close to what
`foundry-observe` describes.

## The question

What is the smallest correct way to make the shipped skills executable, given
that skill bodies are budget-constrained and hash-sealed?

Constraints I must respect, from local evidence:

- Each skill body has a hard budget: 4096 UTF-8 bytes and 1024 o200k_base
  tokens. Total initial metadata is capped at 6400 bytes / 1600 tokens.
- Every skill body is sealed by sha256 in
  `plugins/epistemic-foundry/skills/skill-inventory.json`, and the inventory
  itself is sealed by a canonical `inventory_hash`. Editing any body requires
  recomputing that seal and the two J02 fixtures.
- The J02 exit criteria require exactly 29 active skills, exactly 17 reachable
  references, no orphan/cycle/drift, and all budgets failing closed.
- The canonical MCP surface is frozen at thirteen tools; I must not invent a
  fourteenth.

Please answer these specifically:

1. Should the executable path be expressed as (a) MCP tool calls, (b) `efoundry`
   CLI invocations named directly in skill bodies, (c) a reference file that
   skill bodies point to, or (d) something else? Justify against the byte
   budget and the seal-recompute cost.

2. Exactly which of the 29 skills can honestly carry an executable command
   today given only the five verified CLI subcommands? Be conservative and name
   them. If the honest answer is a small number such as two or three, say so.

3. For a skill whose described artifact has no producer (`foundry-map` needs a
   WorkspaceMapSnapshot; `foundry-intake` needs an InsightCard), what should the
   skill body say instead of a command, so it is neither silently useless nor
   falsely promising? Is naming the blocker inside the skill body the right
   move, or does that belong somewhere else?

4. Is there a materially better target than skill executability for this
   increment? Specifically compare against: implementing a real
   WorkspaceMapSnapshot producer so `foundry.map.query` can bind, versus
   implementing a FORGE session store so `foundry.session.get` can bind. If
   either is a better use of effort, say which and why, including a rough sense
   of whether it is a contained piece of work or a large one.

## Constraints on your answer

- Do not propose evolution, Parliament, promotion, Shinka, or hidden-holdout
  work.
- Flag explicitly as SPEC_GAP anything that would require changing a shared
  canonical contract or the frozen thirteen-tool catalog.
- Prefer the smallest change that produces a genuine end-to-end capability.
- Assume no tests will be run unless explicitly requested.
- Be concrete about file paths and command lines where you can.
