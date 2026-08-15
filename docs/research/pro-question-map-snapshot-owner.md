# Decision needed: who owns WorkspaceMapSnapshot assembly

## What changed since the last turn

Your previous recommendations were implemented and verified.

`foundry-observe` now names a real, executed command. Before writing it into
the skill body I ran it end to end: built an index over a two-document corpus,
ran the lexical lane, and got 1 `retrieval-candidate`, 11 sealed
`search-lane-receipt` entries, and 10 explicit `UNSEARCHED` lanes. A
`counterevidence` lane query returned `UNSEARCHED` with zero candidates rather
than a misleading empty result. The verified command shape is
`efoundry --json retrieve query <db_path> --lane <lane> ...` with all plan
bindings caller-supplied.

`foundry-map` and `foundry-intake` now carry your producer-absence boundary
text. Seals were recomputed through the canonical counter, and
`count_tokens.py verify-inventory` reports PASS with 29 skills, 17 references,
and all three edited bodies inside the 4096-byte / 1024-token budget. I also
turned the reseal step into `tools/skill-context/reseal_inventory.py` so the
inventory cannot drift from its validator, and confirmed it reproduces the same
`inventory_hash` on a second run.

## The finding that prompts this question

You recommended a real `WorkspaceMapSnapshot` producer as the next kernel
target. On inspection, far more of it already exists than I expected. What is
missing is only the final assembly step.

Already implemented in `packages/workspace-map/src`:

- `inventory/workspace-inventory.mjs` — `buildWorkspaceInventory`,
  `extractWorkspaceEdges`, `validateWorkspaceInventory`,
  `validateWorkspaceEdgeExtraction`, `computeWorkspaceInventoryHash`,
  `computeWorkspaceEdgeExtractionHash`, plus frozen `ENTITY_KINDS`,
  `EDGE_KINDS`, `ENTITY_LAYERS`, `SOURCE_CLASSES`, `IDENTITY_NAMESPACES`, and
  a canonical JSON serializer.
- `ranking/baseline/baseline-centrality.mjs` — `computeBaselineCentrality`
  with `BASELINE_CENTRALITY_ALGORITHM = "WEIGHTED_PAGERANK"`, validation, and
  a hash function. There is even a `uniform-rank-regression.test.mjs`, so
  placeholder uniform ranking is already guarded against.
- `ranking/query/query-personalization.mjs` — `computeQueryPersonalization`.
- `ranking/query/risk-change-impact.mjs` — `computeRiskAndChangeImpact`, with
  risk kept separate from relevance.

The canonical `schemas/workspace-map-snapshot.schema.json` requires exactly
thirteen fields: `map_id`, `workspace_id`, `root_hash`, `query`, `nodes`,
`edges`, `ranking_algorithm`, `personalization`, `included_scopes`,
`excluded_scopes`, `tool_versions`, `generated_at`, `map_hash`. Each node
requires `node_id`, `kind`, `label`, `baseline_centrality`, `query_relevance`,
`risk_score`, `content_hash`; each edge requires `source`, `target`, `kind`,
`weight`. Every one of those appears derivable from the four modules above.

So the gap is a composition root: something that runs inventory → edges →
baseline centrality → personalization → risk, projects the result into the
canonical snapshot shape, computes `map_hash`, and validates.

## The ownership problem

No work package owns that assembly. Exact declared write scopes:

- M01: `packages/workspace-map/src/inventory/**`
- M02: `packages/workspace-map/src/ranking/baseline/**`
- M03: `packages/workspace-map/src/ranking/query/**`
- M04: `web/src/features/map/**` (UI only)

There is no owner for `packages/workspace-map/src/snapshot/**` or equivalent,
and no owner for a producer command. This looks like a genuine SPEC_GAP rather
than something I should decide unilaterally.

## The questions

1. Is the missing snapshot-assembly owner a SPEC_GAP requiring a manifest
   amendment, or does one of M01–M04 already implicitly own composition? If an
   amendment is right, which package should own it and what exact write_scope
   line would you add? Prefer the smallest amendment.

2. Where should the producer be invocable from? Options I see:
   (a) a Node API only, called by whatever later binds `foundry.map.query`;
   (b) a new `efoundry map ...` CLI subcommand, which changes the frozen
       five-command table and which you previously flagged as a possible
       SPEC_GAP;
   (c) a Node CLI inside `packages/workspace-map`;
   (d) something else.
   Note the boundary policy: `duplicateImplementationPolicy: forbidden`, and
   the existing implementation is Node, while the packaged plugin bridge calls
   Python. If the map producer is Node and the bridge is Python, how should
   `foundry.map.query` eventually reach it without duplicating logic?

3. What is the honest minimum first profile? Specifically: is a
   repository-only snapshot (code files, imports, and declared research or
   artifact entities that actually exist on disk) legitimate, provided
   `included_scopes` and `excluded_scopes` state the coverage boundary
   truthfully? Or does the canonical schema's `included_scopes` /
   `excluded_scopes` pair require something stronger than "we only walked the
   repository"?

4. `personalization` and `query` are required fields. For a baseline snapshot
   with no user query, what are the correct truthful values? Empty string,
   null, or an explicit "no personalization applied" marker? I do not want to
   fabricate a query just to satisfy a required field.

5. Does binding `foundry.map.query` require a persisted snapshot store, or may
   a pure-read tool compute a snapshot on demand from a frozen input? You
   previously warned that a pure-read tool must not persist as a side effect.
   If on-demand computation is acceptable, say so explicitly; if a store is
   required, that changes the size of this work substantially.

## Constraints on your answer

- Do not propose evolution, Parliament, promotion, Shinka, or hidden-holdout
  work.
- Flag explicitly as SPEC_GAP anything requiring a shared canonical contract
  change or a change to the frozen thirteen-tool catalog.
- Prefer the smallest change that yields a genuine, verifiable capability.
- Assume no tests will be run unless explicitly requested.
- Be concrete about file paths, function names, and manifest lines.
