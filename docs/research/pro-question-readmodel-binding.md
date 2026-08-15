# Decision needed: binding real read models into the packaged plugin MCP surface

## Objective

Make the installed Epistemic Foundry Codex plugin genuinely useful end-to-end,
not merely loadable, while staying inside MASTER_SPEC authority.

## Verified current state

The plugin now loads and runs. Confirmed by live JSON-RPC round trip from a
directory outside the repository, with no repository checkout on the path:

- `plugins/epistemic-foundry/.codex-plugin/plugin.json` declares
  `"skills": "./skills/"` and `"mcpServers": "./.mcp.json"`.
- `.mcp.json` runs `node ./dist/mcp-server.mjs`.
- `dist/mcp-server.mjs` is a self-contained Node stdio JSON-RPC server with no
  Python and no repository dependency.
- `initialize`, `ping`, `tools/list` succeed; `foundry.status` and
  `foundry.health` return schema-shaped result envelopes; a wrong argument type
  returns `INVALID_INPUT`; an unlisted tool returns `UNAUTHORIZED`.

The packaged server currently advertises exactly two tools. The other eleven
T01 tools are deliberately not advertised because no read model is bound.

Crucially, the two advertised tools return hardcoded values. They report
`read_model_state: "DEGRADED"` and constants such as
`release_level: "SPEC_BUNDLE"`. They do not observe anything real.

## What already works in Python

The Python runtime under `src/epistemic_foundry` is executable and tested:

- `efoundry` CLI with `status`, `schemas`, `validate`, `ledger verify`,
  `retrieve build|query` (confirmed: the subcommand table is exactly these five).
- `NoeticLedger.verify()` and `NoeticLedger.length()` in
  `src/epistemic_foundry/noetic_ledger/ledger.py`.
- SQLite FTS5 lexical index with `read_index_stats()` and `query()` in
  `src/epistemic_foundry/retrieval/lexical_index.py`.
- 127 canonical schemas packaged as importable package data (`_canonical`),
  loaded through `default_registry()` with integrity checking.

So the honest gap is not "no runtime exists". It is that the plugin surface and
the working runtime are not connected.

## The boundary constraint

`packages/boundary-policy.json` declares a Python runtime root of
`src/epistemic_foundry`, a component root of `python/epistemic_foundry`, and
`duplicateImplementationPolicy: forbidden`.

The Node and Python halves already duplicate MCP framing, ledger, and kernel
concepts. Reimplementing ledger verification or index reading in Node would add
another duplicate implementation.

But the packaged plugin is currently pure Node specifically so that it starts
with no checkout and no Python runtime copy. An earlier attempt to make the
packaged path depend on a repository checkout failed, and an attempt to copy a
191MB runtime tree into a protected directory was rejected as unacceptable
overhead.

## The question

Given the above, which binding strategy should the packaged plugin use for real
read models, and how far should it go now?

Please choose one and justify it against the duplicate-implementation policy,
startup cost, and truthfulness of the reported state.

Option A, Node-only, honest and shallow: keep the packaged server pure Node.
Bind only what Node can observe without duplicating domain logic, such as
plugin payload identity, skill inventory presence and hash, and its own tool
surface. Continue reporting kernel and workspace read models as `UNAVAILABLE`.
Do not advertise the other eleven tools.

Option B, optional Python bridge that degrades honestly: keep Node as the MCP
transport, but let it detect an available `efoundry` (installed console script
or importable package) and, when present, shell out for real `status`,
`ledger verify`, and `retrieve query` data, binding some subset of the
unadvertised tools. When absent, report `UNAVAILABLE` exactly as now. This adds
a process boundary rather than a duplicate implementation.

Option C, something else you consider materially better, including doing less.

For the chosen option, state specifically:

1. Whether a Node MCP server spawning the Python CLI counts as a duplicate
   implementation under the declared policy, or as an adapter calling a service.
2. Which of the eleven unadvertised tools, if any, can be truthfully bound from
   the existing Python surface without inventing new domain semantics. Be
   conservative: `foundry.session.get` requires FORGE session state and
   `foundry.map.query` requires a workspace map snapshot. Say plainly if those
   do not exist yet.
3. What the packaged server must report when the Python side is missing, so the
   result stays truthful rather than silently empty.
4. Whether advertising a tool that can return `UNAVAILABLE` is better or worse
   than not advertising it at all, from the perspective of an agent consuming
   the MCP surface.

## Constraints on your answer

- Do not propose evolution, Parliament, promotion, Shinka, or hidden holdout
  work. Those are far out of scope.
- Do not propose a plan that requires changing shared canonical contracts
  unless you explicitly flag it as a SPEC_GAP requiring an authority decision.
- Prefer the smallest change that makes the plugin genuinely useful.
- Assume no tests will be run unless explicitly requested.
