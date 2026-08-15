**Decision: authorize the executable cutover, but do not change the current release status.** `MASTER_SPEC.md` must stop treating a fail-closed stub as an unconditional invariant and instead make it conditional on the authorized implementation target. The repository’s authorized target becomes `PLUGIN_ALPHA`; `status_of_this_bundle` remains `SPEC_BUNDLE` until all fifteen gates have executable, independently accepted evidence. No intermediate status such as `PLUGIN_ALPHA_CANDIDATE` should be invented.

## 1. `MASTER_SPEC.md`: exact authorization without a release claim

Replace the unconditional sentence:

```text
Reference plugin executables remain fail-closed stubs.
```

with this normative block:

```text
### Plugin implementation authority and release qualification

The authorized implementation target for this repository is `PLUGIN_ALPHA`.
An executable installed-plugin candidate MAY be built, packaged, installed,
and exercised while the qualified status of this bundle remains
`SPEC_BUNDLE`.

The fail-closed-stub requirement applies only when the authorized
implementation target is `SPEC_BUNDLE`. It does not prohibit the executable
candidate authorized by
`docs/decisions/20260815-plugin-alpha-goal.md`.

`status_of_this_bundle` records the highest release level for which every
required acceptance gate has executable and accepted evidence. It does not
assert that no unqualified implementation artifacts exist.

The existence of an executable candidate, successful manual exercise, or
partial satisfaction of the `PLUGIN_ALPHA` gate set MUST NOT be represented
as a `PLUGIN_ALPHA` release. `PLUGIN_ALPHA` MAY be claimed only after all
fifteen gates named under `PLUGIN_ALPHA` in
`manifests/acceptance_matrix.yaml` have executable, reviewable evidence bound
to the candidate source revision and installed payload, and the authorized
acceptance owner changes `status_of_this_bundle` to `PLUGIN_ALPHA`.

Entries in `runtime_capabilities` describe mechanisms present in the candidate
payload. They do not establish host-cell verification or release
qualification. A capability whose corresponding acceptance evidence is
incomplete remains unqualified.
```

Where `MASTER_SPEC.md` currently summarizes implementation and release state, use these exact labels:

```text
Implementation target: `PLUGIN_ALPHA` — authorized; incomplete.
Current qualified bundle status: `SPEC_BUNDLE`.
```

Remove or replace any adjacent statement saying implementation is entirely “unclaimed” or that no working implementation may exist. Retain the narrower statement that **`PLUGIN_ALPHA` completion and release remain unclaimed**.

This patch changes permission, not status:

```text
Before:
  executable candidate permitted: no
  qualified status: SPEC_BUNDLE

After:
  executable candidate permitted: yes
  authorized target: PLUGIN_ALPHA
  qualified status: SPEC_BUNDLE
```

## 2. `status_of_this_bundle`: retain `SPEC_BUNDLE`

During implementation, keep:

```yaml
status_of_this_bundle: SPEC_BUNDLE
```

Do not introduce any of these:

```yaml
status_of_this_bundle: PLUGIN_ALPHA_CANDIDATE
status_of_this_bundle: IMPLEMENTATION_CANDIDATE
status_of_this_bundle: MVP_RUNTIME_BUNDLE
```

No such intermediate status has been established as canonical in the facts provided. The candidate state is represented by the authorized target in `MASTER_SPEC.md`, the goal decision, the nonpassing `PLUGIN_ALPHA` gates, and the candidate capabilities in `compatibility_matrix.yaml`.

In `manifests/acceptance_matrix.yaml`, replace any prose equivalent to:

```text
No working-runtime claim.
```

with:

```text
No `PLUGIN_ALPHA` release claim. An executable `PLUGIN_ALPHA` candidate is
authorized, but the current qualified status remains `SPEC_BUNDLE` until all
fifteen `PLUGIN_ALPHA` gates have accepted executable evidence.
```

The eventual status transition is exactly:

```diff
-status_of_this_bundle: SPEC_BUNDLE
+status_of_this_bundle: PLUGIN_ALPHA
```

That transition is authorized only when all of the following are true:

1. All fifteen gate keys are present.
2. Every gate is in its canonical passing state.
3. Every gate refers to executable evidence rather than prose or manual assertion alone.
4. Evidence is bound to the accepted source revision and installed payload digest where applicable.
5. An acceptor independent of the implementation package has accepted the evidence.
6. The acceptance-matrix validator passes after the transition.

The existing `156/156 PASS` result does not perform this transition automatically. It remains package-level conformance evidence against its recorded contract revisions.

## 3. The exact fifteenth gate

Use this exact key:

```yaml
installed_dist_execution_automation:
```

Do not shorten it to `dist_automation`, `installed_execution`, or another alias. It directly names the separately required condition that is missing from the fourteen-gate block.

Insert it using the same object/value shape and nonpassing initial state used by the other fourteen gates. Do not introduce a new per-gate schema merely for this key.

Its normative semantics are:

```text
`installed_dist_execution_automation` passes only when a checked-in,
machine-executed test assembles the declared installed plugin payload and
invokes every public installed entrypoint whose implementation is supplied by
`dist/`, using the installed copy rather than repository source files.

The automation must fail when `dist/` is absent, stale, inconsistent with the
declared payload, or bypassed through repository `src/`, development-only
module resolution, `PYTHONPATH`, editable installation, or another source-tree
fallback.

The evidence must identify the source revision, installed-payload digest,
`dist/` digest, invoked entrypoints, commands, exit results, and test-harness
revision. Manual invocation is not sufficient.
```

At minimum, the automated run must cover:

```text
bin/efoundry.mjs
the MCP server command declared by .mcp.json
any installed hook command that loads implementation from dist/
```

This does not require adding runtime or MCP behavior; it tests the entrypoints that the candidate already declares.

### Difference from `fresh_install_matrix`

The gates are independent:

| Gate                                  | Question answered                                                                                                                  |
| ------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `installed_dist_execution_automation` | Does checked-in automation execute the exact installed `dist/` implementation, without silently falling back to repository source? |
| `fresh_install_matrix`                | On which declared host/environment cells does the complete fresh-install and lifecycle sequence have accepted evidence?            |

`installed_dist_execution_automation` is about **artifact provenance and execution path**. It may initially run on one designated reference runner.

`fresh_install_matrix` is about **host coverage and lifecycle coverage**. It retains `UNVERIFIED` for every cell lacking the required install, open/start, transition, restart/restore, and related evidence.

One CI execution may contribute evidence to both gates, but it must emit separate assertions. Passing the installed-`dist` gate does not verify a host cell; passing one host installation does not prove that execution came exclusively from the packaged `dist/`.

The mismatch must therefore be corrected by adding this key, not by changing the goal text from fifteen gates to fourteen.

## 4. `compatibility_matrix.yaml`: exact candidate declarations

Set `runtime_capabilities` to the following exact identifiers:

```yaml
runtime_capabilities:
  - installed_plugin_cli_execution
  - installed_plugin_mcp_execution
  - bundled_python_runtime_execution
  - runtime_payload_integrity_verification
  - workspace_path_confinement
  - degraded_runtime_diagnostics
```

Their claim boundaries are:

| Identifier                               | What it asserts                                                                    | What it does not assert                                       |
| ---------------------------------------- | ---------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| `installed_plugin_cli_execution`         | The installed candidate CLI has executed                                           | Complete CLI semantics or `PLUGIN_ALPHA` qualification        |
| `installed_plugin_mcp_execution`         | The installed MCP server and at least one backed operation have executed           | Nine canonical read-tool bindings or complete MCP conformance |
| `bundled_python_runtime_execution`       | Bundled application/runtime resources have executed through the candidate launcher | Durable state composition or clean-clone reproducibility      |
| `runtime_payload_integrity_verification` | The candidate detects payload divergence from its declared integrity manifest      | Signed distribution authenticity                              |
| `workspace_path_confinement`             | Candidate path checks have rejected tested out-of-workspace operations             | Full host-cell or lifecycle verification                      |
| `degraded_runtime_diagnostics`           | Missing or unusable runtime prerequisites produce a deliberate diagnostic failure  | General recovery or session restoration                       |

Do **not** add any of these yet:

```text
durable_sqlite_cas_ledger_composition
canonical_read_tool_bindings
nine_canonical_read_tool_bindings
session_lifecycle
session_restart_restore
clean_clone_reproducibility
installed_dist_execution_automation
plugin_alpha
```

Those describe incomplete gates or a qualified release, not current candidate mechanisms.

Update `expected_top_level` to the exact current candidate root:

```yaml
expected_top_level:
  - .codex-plugin
  - .mcp.json
  - assets
  - bin
  - dist
  - hooks
  - runtime
  - scripts
  - skills
  - src
```

This is the smallest amendment to the existing list. Do not introduce separate `source_top_level` and `installed_top_level` fields in this cutover; that would be a new compatibility-matrix schema decision. The fifteenth gate must instead prove that installed execution actually consumes `dist/` and does not fall back to `src/` or `scripts/`.

All host cells remain unchanged:

```yaml
status: UNVERIFIED
```

Manual execution, even successful execution, is not sufficient to change a cell to `VERIFIED`, `SUPPORTED`, `PASS`, or another positive state. Bundle-level candidate capabilities and host-cell verification are separate assertions.

Because the six capability identifiers are new canonical vocabulary, the cutover authority record must enumerate these exact six names. Adding them only in `compatibility_matrix.yaml`, without the authority record authorizing that vocabulary change, would remain an unauthorized contract invention.

## 5. Smallest authority and ownership amendment

Use the existing decision file as the one-time higher-authority cutover record:

```text
docs/decisions/20260815-plugin-alpha-goal.md
```

Add this section to it:

```text
## Authority grant

Authority ID: `PLUGIN_ALPHA_CUTOVER_20260815`
Grantor: repository owner
Authorized implementation target: `PLUGIN_ALPHA`
Current qualified-status ceiling: `SPEC_BUNDLE`

This decision authorizes only the following shared-contract amendments:

1. Qualify the fail-closed-stub rule in `MASTER_SPEC.md` so that it does not
   prohibit an executable `PLUGIN_ALPHA` candidate.
2. Retain `status_of_this_bundle: SPEC_BUNDLE` during implementation.
3. Add the `installed_dist_execution_automation` gate, bringing the
   `PLUGIN_ALPHA` gate count to fifteen.
4. Add the six candidate `runtime_capabilities` identifiers enumerated by this
   decision.
5. Add `dist`, `runtime`, `scripts`, and `src` to the existing
   `expected_top_level` list.
6. Assign custodial write scope for `docs/decisions/**` to A01.

This authority does not authorize a `PLUGIN_ALPHA` release claim, a positive
host-cell status, a passing gate without executable evidence, a new release
status, or a broader runtime/protocol contract.

X01 may implement the plugin and submit evidence. X01 may not accept its own
evidence, mark a `PLUGIN_ALPHA` gate as passing solely on its own authority, or
change `status_of_this_bundle`.

A01 may maintain the decision record and record an accepted status transition.
A01 does not thereby gain authority to manufacture or accept implementation
evidence.

Every gate acceptance requires an acceptor independent of the implementation
author. The final `status_of_this_bundle` transition requires all fifteen
independently accepted gate records.
```

The bootstrap edit is a repository-owner act. It is not made under an authority that A01 already possesses. After that owner-approved commit lands, add only this ownership change to `manifests/development_manifest.yaml`:

```text
A01 write scope += docs/decisions/**
```

Preserve the existing ownership of all other shared files. In particular:

```text
MASTER_SPEC.md                         existing authority owner
manifests/acceptance_matrix.yaml       existing acceptance owner
manifests/compatibility_matrix.yaml    existing compatibility owner
plugins/epistemic-foundry/**           X01
installed-dist evidence                Z01 or existing installation-test owner
docs/decisions/**                      A01 custodial write scope
```

Do not transfer `MASTER_SPEC.md`, either matrix, or `status_of_this_bundle` to X01.

The minimum separation of duties is:

```text
X01:
  implement candidate
  produce implementation evidence
  cannot accept own evidence

Z01 / installation-test owner:
  produce installed-payload automation evidence
  cannot alone change overall release status

independent acceptor:
  accept or reject gate evidence

A01:
  maintain decision record
  record final status only after all accepted gates
```

No new work package is required merely to authorize this cutover. Creating one would reopen the same question of who had authority to create and empower it.

## 6. Edits that remain unauthorized contract inventions

Even after branch A is recorded, the following edits are not authorized by this cutover:

* Setting `status_of_this_bundle: PLUGIN_ALPHA` before all fifteen gates pass.
* Adding a new status such as `PLUGIN_ALPHA_CANDIDATE`.
* Marking `installed_dist_execution_automation` as passing based on manual execution.
* Renaming, deleting, weakening, or reinterpreting any of the existing fourteen gates.
* Adding a sixteenth gate without a separate authority decision.
* Setting any host cell to a positive state without its required lifecycle evidence.
* Adding capability identifiers beyond the exact six listed above.
* Declaring durable SQLite/CAS/ledger composition, nine canonical read-tool bindings, session restoration, clean-clone reproducibility, or installed-`dist` automation as present before their evidence exists.
* Treating `runtime_capabilities` as proof of `PLUGIN_ALPHA`.
* Introducing a new compatibility-matrix structure such as separate source and installed layout fields in this patch.
* Changing MCP catalog, protocol, envelope, or tool-binding contracts under the authority of this cutover.
* Giving X01 ownership of shared acceptance or authority files.
* Allowing an implementation-produced report to be its own final acceptance.
* Rewriting historical `PASS` reports solely because an executable candidate is now permitted.

## Result immediately after the authority patch

The authoritative state should read:

```text
Authorized implementation target: PLUGIN_ALPHA
Executable candidate permitted: yes
PLUGIN_ALPHA gate count: 15
Current qualified bundle status: SPEC_BUNDLE
Current PLUGIN_ALPHA claim: no
Candidate runtime capabilities declared: 6
Host cells verified: 0
Self-certification permitted: no
```

The authority cutover is complete when those statements are simultaneously true. The later transition to `PLUGIN_ALPHA` is a separate acceptance action and must not be included in this patch.
