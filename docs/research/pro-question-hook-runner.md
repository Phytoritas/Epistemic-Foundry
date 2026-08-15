# Decision needed: the missing hook runner

## What changed since the last turn

Your snapshot recommendations were implemented and verified end to end.

`foundry.map.query` is now the third backed tool. Calling it against
`packages/workspace-map` with `query: "centrality", limit: 5` returned the top
5 of 17 real nodes, ranked by query relevance then centrality, with
`baseline-centrality.mjs` first. The result envelope and the embedded snapshot
both validate against their canonical schemas with zero errors, and
`data_schema_refs` carries the real workspace-map-snapshot schema ID.

I followed your ownership call: M04 owns `packages/workspace-map/src/snapshot/**`,
the producer is a public Node API, and the tool computes on demand with
`receipts: []` and no persistence. Truncation is reported explicitly
(`DEGRADED`, "5 of 17") rather than silently narrowing coverage. A missing
workspace root returns `UNAVAILABLE` with the exact reason instead of guessing
from the process working directory.

On the Node/Python boundary: I did not port any map logic to Python. Because
the repository declares `sourceImportPolicy: public-package-api-only` and every
package ships `"exports": {}`, I bundle the exact 11 source files into the
payload with a recorded provenance hash. Editing a bundled copy is detected as
`DRIFTED`; I verified that by mutating a file and restoring it.

## The finding that prompts this question

The plugin ships four hook files declaring eight hooks:

| File | Events |
|---|---|
| `session.json` | `SessionStart` (startup\|resume\|clear\|compact), `PostCompact` (manual\|auto) |
| `delegation.json` | `SubagentStart`, `SubagentStop` (matcher `.*`) |
| `prompt.json` | `UserPromptSubmit` |
| `tools.json` | `PermissionRequest`, `PreToolUse`, `PostToolUse` (matcher `Bash\|apply_patch\|Edit\|Write\|mcp__.*\|Agent`) |

Every one invokes `node "${PLUGIN_ROOT}/dist/hook-runner.mjs" <subcommand>`
with a 15-second timeout. That file does not exist.

Right now this is latent rather than broken: the plugin manifest declares
`skills` and `mcpServers` but no hooks key, so nothing registers them. The
moment hooks are registered, all eight fail.

There is a hook gateway in `packages/plugin-host/src/hooks/gateway/hook-gateway.mjs`
that H01 owns, but no packaged runner binds it to these declarations.

## Why I am asking rather than implementing

Three of these hooks sit on a security boundary. `PermissionRequest` and
`PreToolUse` intercept `Bash`, `apply_patch`, `Edit`, `Write`, `mcp__.*`, and
`Agent`. A runner that returns the wrong shape could deny legitimate work, or
worse, approve something it should not. A 15-second timeout on
`UserPromptSubmit` also sits directly in the user's interactive path.

I do not want to invent hook response semantics.

## The questions

1. Is implementing `dist/hook-runner.mjs` the right next increment at all, or
   is the honest move to leave hooks unregistered and delete or quarantine the
   four declaration files until their runner exists? Consider that an
   unregistered hook file that points at a missing binary is dead weight that
   looks like capability.

2. If a runner is right, what is the minimum truthful behavior per event? My
   instinct is that most should be observational no-ops that emit nothing and
   exit 0, because the Foundry has no session store, no context capsule
   producer, and no policy engine to consult. Specifically:
   - `SessionStart` / `PostCompact`: there is no FORGE session store and no
     ContextCapsule producer, so what can these truthfully do?
   - `PreToolUse` / `PermissionRequest`: with no policy engine, should these
     always allow, or is "always allow" itself a false safety claim that is
     worse than not registering the hook?
   - `PostToolUse`: could this append to the Noetic Ledger, which does exist
     and is hash-chained? Or does an unsolicited ledger append violate the
     receipt/effect contract?
   - `SubagentStart` / `SubagentStop`: anything truthful available?

3. What exact response contract do Codex hooks expect? I have
   `hook-gateway.mjs` locally but I do not want to assume its shape matches the
   host's actual protocol. If the host contract is not knowable from this
   repository, say so plainly and I will treat it as a SPEC_GAP rather than
   guessing at exit codes and JSON shapes.

4. Who owns `plugins/epistemic-foundry/dist/hook-runner.mjs`? G02 owns
   `plugins/epistemic-foundry/bin/**` and `packages/plugin-host/src/cli-dispatch/**`.
   T03 now owns `plugins/epistemic-foundry/dist/**`. H01 owns the gateway. Is
   T03 the right owner for the packaged runner, with H01 owning the semantics
   it delegates to?

5. Is there a materially better target than hooks for this increment? The
   remaining ten MCP tools all require domain stores that do not exist
   (`forge-session-state` needs 15 required fields, `claim-card` 26,
   `hypothesis-passport` 28, `coverage-snapshot` needs InsightCard plus search
   lane receipts). If a real FORGE session store is now the better target
   despite your earlier "not next" call, say so and I will reconsider.

## Constraints on your answer

- Do not propose evolution, Parliament, promotion, Shinka, or hidden-holdout
  work.
- Flag explicitly as SPEC_GAP anything requiring a shared canonical contract
  change, a change to the frozen thirteen-tool catalog, or knowledge of a host
  protocol this repository does not define.
- Prefer the smallest change that yields a genuine, verifiable capability.
- Strongly prefer removing a false capability signal over adding a hollow one.
- Assume no tests will be run unless explicitly requested.
