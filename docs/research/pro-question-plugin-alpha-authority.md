# PLUGIN_ALPHA authority cutover decision

We are implementing `docs/decisions/20260815-plugin-alpha-goal.md`. The user has
explicitly selected the outcome “complete Epistemic Foundry v4 to
`PLUGIN_ALPHA`”, so branch A is authorized: the higher authority must permit a
working installed plugin rather than force the reference executable to remain
a stub.

Current facts:

- `MASTER_SPEC.md` still says the reference plugin executables remain
  fail-closed stubs and labels implementation/current release as unclaimed /
  `SPEC_BUNDLE`.
- `manifests/acceptance_matrix.yaml` still selects `SPEC_BUNDLE`.
- `manifests/compatibility_matrix.yaml` still declares
  `runtime_capabilities: []` and omits `dist`, `runtime`, `scripts`, and `src`
  from `expected_top_level`.
- A working plugin payload is already installed and manually exercised, but
  durable SQLite/CAS/ledger composition, the nine canonical read-tool bindings,
  session open/transition/restart restore, clean-clone reproducibility, and
  installed-dist automation remain incomplete.
- The PLUGIN_ALPHA block currently contains 14 gate keys, while the goal text
  repeatedly says 15 gates and separately requires installed `dist/` automation.
- We must not claim `PLUGIN_ALPHA` before all gates have executable evidence.

Give a decision-grade patch contract, not general advice:

1. Exact wording/field changes that authorize an executable
   `PLUGIN_ALPHA` candidate in `MASTER_SPEC.md` now without prematurely claiming
   the release is complete.
2. Whether `status_of_this_bundle` should remain `SPEC_BUNDLE` during
   implementation and flip only after all gates are proven, or whether another
   existing status is canonical.
3. The exact 15th PLUGIN_ALPHA gate name and semantics. Decide whether it is
   `installed_dist_execution_automation` (or another existing canonical concept)
   and how it differs from `fresh_install_matrix`.
4. Exact `compatibility_matrix.yaml` capability names and payload top-level
   entries that truthfully describe the current candidate while keeping host
   cells `UNVERIFIED` until lifecycle evidence exists.
5. The smallest authority/ownership amendment needed for these shared files and
   `docs/decisions/**`, without allowing an implementation package to certify
   itself.
6. Call out any requested edit that would still be an unauthorized contract
   invention.

Keep the answer bounded to this authority cutover. Do not design the durable
runtime or MCP bindings in this turn.
