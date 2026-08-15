# Decision needed: the release manifest inventory contract

## What changed since the last turn

Your hook recommendation was implemented exactly as scoped and verified.

Only `SessionStart` is registered now. `plugin.json` declares
`"hooks": "./hooks/session.json"`, the timeout dropped from 15s to 3s, and the
status message no longer claims to resume FORGE. The runner lives at
`adapters/codex/hook-runner.mjs` (H01) and is bundled into
`plugins/epistemic-foundry/dist/hook-runner.mjs` (T03) with a provenance hash;
I verified drift detection by mutating the payload copy and restoring it.

Live behavior, invoked as a process with Codex-shaped stdin:

- `source: startup` → "No FORGE session was created; the Foundry holds no session state."
- `source: compact` → "The host compacted the conversation. No Foundry ContextCapsule was rebuilt..."
- `source: resume` → "The host resumed a Codex session. No FORGE session was resumed..."
- verb `pre-tool-use` → exit 1, stderr `HOOK_VERB_UNREGISTERED`
- verb `session-start` with `hook_event_name: PostToolUse` → exit 1, same code

Emitted context is 385 bytes, under the 1024 cap. `prompt.json`, `tools.json`,
and `delegation.json` were removed from the installed payload and from
`codex-binding.json`; H02 and H03 manifest scopes and exit criteria were
updated so they no longer claim ownership of files that no longer exist.

I also confirmed your point about structural binding: `blueprint_hook_bundle_count: 7`
in the acceptance matrix refers to `plugin_blueprint/`, not the installed
plugin, so removing three installed hook files did not move that gate. The
structural validator still reports `plugin_blueprint: {skills: 29, hook_bundles: 7}`.

## The finding that prompts this question

Running `tools/validate_spec_bundle.py` produces 56 errors. Every one is a
`PACKAGE_MANIFEST.json` problem; all other checks pass. None of them are
caused by my hook, skill, snapshot, or MCP work — filtering the error list for
`hook`, `plugins/`, or `skill` returns nothing.

The real state is worse than 56 suggests. Recomputing the inventory with the
validator's own `_is_non_bundle_path` gives:

| Root | Files the validator considers bundle content but the manifest omits |
|---|---|
| `artifacts/` | 8,826 |
| `.ruff_cache/` | 518 |
| `packages/` | 204 |
| `node_modules/` | 203 |
| `docs/` | 159 |
| `python/` | 132 |
| `plugins/` | 97 |
| others | ~279 |

Total missing: 10,418. Extra: 0.

Both `tools/build_release.py` and `tools/validate_spec_bundle.py` share an
identical `NON_BUNDLE_PREFIXES` tuple:

```
.git/  .ai-bridge/  .rah/  .venv/  __pycache__/  .pytest_cache/
build/  dist/  docs/architecture/  src/  tests/
```

`node_modules/`, `.ruff_cache/`, `.codex/`, and `.github/` are absent from that
list, so a local dependency tree and two tool caches are currently treated as
shippable specification-bundle content. That looks like a straightforward
defect rather than a policy decision.

`artifacts/` is the harder question: 8,826 files of work-package evidence.

## The questions

1. Which of these belong in `NON_BUNDLE_PREFIXES`? My reading is that
   `node_modules/`, `.ruff_cache/`, and `.codex/` are unambiguous defects —
   none is authored bundle content. `.github/` is less obvious: CI workflow
   definitions are authored and versioned, so they might legitimately ship.
   What is your call on each?

2. Is `artifacts/` bundle content? The acceptance matrix ties SPEC_BUNDLE to
   evidence, and `evidence_artifacts` paths are declared per work package in
   the development manifest, which argues for inclusion. But 8,826 evidence
   files in a specification bundle, each hashed, is a large and constantly
   churning surface. Should the manifest include all of it, a declared subset
   (only the `evidence_artifacts` paths named in the manifest), or none of it?

3. Once the prefix list is correct, is regenerating `PACKAGE_MANIFEST.json` the
   right move, or does regenerating it defeat its purpose? It exists to detect
   drift; if the answer to drift is always "regenerate", it detects nothing.
   Is there a distinction between legitimate regeneration (the bundle genuinely
   changed) and papering over an unexplained change?

4. `tools/build_release.py` and `tools/validate_spec_bundle.py` each carry
   their own copy of the prefix tuple, with a comment on the builder's copy
   warning that they must be kept in sync or "every local checkout reports a
   spurious manifest mismatch". That duplication is exactly the failure mode
   the comment predicts. Should one become the authority, and which?

5. Who owns this? The two tools are `tools/build_release.py` and
   `tools/validate_spec_bundle.py`. I have not found a work package declaring
   either in its `write_scope`. If none does, is that a SPEC_GAP requiring a
   manifest amendment, and to which package?

6. Is this the right thing to work on at all? It is release-integrity
   plumbing, not new capability. If you think a different increment moves the
   objective further, say so. But my read is that a release-integrity gate
   reporting 56 errors on a clean checkout is a broken gate, and a broken gate
   is worse than no gate because it trains everyone to ignore it.

## Constraints on your answer

- Do not propose evolution, Parliament, promotion, Shinka, or hidden-holdout
  work.
- Flag explicitly as SPEC_GAP anything requiring a shared canonical contract
  change or a manifest ownership amendment.
- Prefer the smallest change that makes the gate meaningful again.
- Assume no tests will be run unless explicitly requested.
- Be concrete about file paths and exact tuple entries.
