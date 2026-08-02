# G02-0001 independent review of bounded-agent work

- Author: the bounded implementation agent that wrote
  plugins/epistemic-foundry/bin/efoundry.mjs and its two cli-dispatch
  contract tests. Reviewer: this seal-prep session, a distinct actor that
  did not author the dispatcher. The author never approves its own work, so
  actor_independence HOLDS for this review; external actor-independent
  certification does NOT, and no such claim is made. G02 is risk_class=high
  and governs the plugin entry boundary, so the dispatcher was attacked on
  its contract rather than skimmed.
- PATH-less invocation works. The dispatcher computes exactly one payload
  target, ../dist/cli.mjs, from its own module URL via fileURLToPath, and
  spawns the current absolute Node executable (process.execPath) with
  shell:false, inherited stdio, the caller's working directory and
  environment, and unchanged arguments. payload_cli_smoke copies an
  installed-plugin fixture into a directory with spaces and Korean
  characters, runs it with an empty PATH, and confirms argv, stdin, stdout,
  stderr, cwd, env, and a non-zero exit code 23 all survive the hop. No
  efoundry PATH alias is required.
- Fail-closed on a missing payload. Removing the fixture dist/cli.mjs makes
  the dispatcher exit non-zero with a diagnostic naming dist/cli.mjs and no
  stdout; it never falls back to a repository checkout, an editable
  src/epistemic_foundry install, or a PATH lookup, so a missing packaged
  payload cannot silently execute foreign code.
- No domain logic (fixed process adapter). dispatcher_boundary_test parses
  the dispatcher source and admits only node:child_process and node:url,
  requires a single spawn of ../dist/cli.mjs, and rejects PLUGIN_ROOT,
  PLUGIN_DATA, epistemic_foundry, node:fs/http/https, schema, openapi,
  Noetic, PolicyBundle, and PromotionDecision tokens, any
  CLI/PYTHON/ROOT/PATH environment override, and any
  exec/execFile/fork/spawnSync or cmd/powershell/pwsh/bash/sh/python shell
  path. A byte-size ceiling keeps it a thin adapter. This review re-derived
  every one of those invariants directly from the dispatcher bytes.
- Dependencies and checks: G02 builds only on the sealed G01 gateway
  (G01-0001 PASS) and adds no new production dependency; the downstream-built
  dist/cli.mjs payload is neither created nor claimed here. Ruff lint and
  format, the two required checks (payload_cli_smoke 2/2, dispatcher_boundary_test 2/2), targeted 4/4, full Python 1261/1261, full Node 1291/1291 across 115 files, and git diff --check all pass with
  zero failures.
- Residual limitations: G02 proves payload process forwarding and
  fail-closed targeting only. PLUGIN_ROOT/PLUGIN_DATA and workspace
  resolution remain G03-owned, downstream efoundry command semantics and
  stable JSON errors remain T03-owned, and marketplace fresh-install remains
  G04-owned. Verdict: PASS on the exact G02 package contract.
