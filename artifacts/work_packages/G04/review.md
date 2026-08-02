# G04-0001 independent review of bounded-agent work

- Author: the bounded implementation agent that wrote
  tests/install/local-marketplace (lifecycle-harness.mjs and
  g04-lifecycle.test.mjs). Reviewer: this seal-prep session, a distinct
  actor that did not author the harness. The author never approves its own
  work, so actor_independence HOLDS for this review; external
  actor-independent certification does NOT, and no such claim is made. G04
  is risk_class=high and gates fresh install and clean uninstall, so the
  harness was attacked on its isolation and residue contracts rather than
  skimmed.
- Fresh install works and is functional. The test builds an isolated,
  uniquely named OS-temp root holding a disposable local marketplace, an
  isolated CODEX_HOME, an isolated user profile with AppData roots, and an
  empty cwd, all under spaced non-ASCII paths. The real codex host adds the
  marketplace, lists the plugin as available without the personal
  marketplace, and installs epistemic-foundry into the isolated plugin
  cache. The installed cache is a byte-for-byte hash-equal copy of the four
  source files (zero missing, extra, or mismatched paths), its manifest is
  valid with an empty capability set, and enable/disable/re-enable is
  observed through the host after edits confined to isolated config.
- The install survives marketplace-source detachment. The marketplace
  plugin source is renamed away and the installed cache still enumerates
  identically and lists enabled, proving no repository checkout or live
  source is assumed. The absolute installed dispatcher is then invoked from
  an empty cwd with an empty PATH; it fails closed naming the installed
  dist/cli.mjs target, does not leak the repository path, and no command
  success is fabricated because the T03-owned CLI payload is intentionally
  not yet packaged.
- Clean uninstall leaves no residue. Plugin remove deletes the installed
  cache and removes the selector from isolated config; marketplace remove
  drops it from the listing with zero G04 marketplace residue. The real
  user's ~/.codex/config.toml file state and selector cache are captured
  before the run, asserted absent during it, and compared byte-identical in
  a finally block that also tears the owned temp root down after verifying
  its OS-temp parent, owned prefix, directory type, and non-link identity.
- Evidence hygiene. Command evidence stores normalized argv, status, and
  byte-size/sha256 of normalized stdout and stderr only; no raw output,
  username, absolute repository path, or random temp path is retained, and
  every recorded command is a successful bounded call.
- Dependencies and checks: the harness installs the G02/G03-sealed plugin
  package shell (G02-0001 PASS, G03-0001 PASS) and adds no new production
  dependency. Ruff lint and format, the two required checks (fresh_install_test and clean_uninstall_test, both asserted in the 1/1 lifecycle module), full Python 1261/1261, full Node 1291/1291 across 115 files, and git diff --check all pass with
  zero failures.
- Residual limitations: G04 verifies the current capability-free plugin
  shell's local-marketplace install, state observation, cache independence,
  and clean removal only; the T03 CLI payload and command semantics, remote
  marketplace publication, OS-enforced sandboxing, and release readiness
  remain later packages. Verdict: PASS on the exact G04 package contract.
