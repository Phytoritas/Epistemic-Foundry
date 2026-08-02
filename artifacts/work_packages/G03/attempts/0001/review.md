# G03-0001 independent review of bounded-agent work

- Author: the bounded implementation agent that wrote
  packages/plugin-host/src/paths. Reviewer: this seal-prep session, a
  distinct actor that did not author the resolver. The author never
  approves its own work, so actor_independence HOLDS for this review;
  external actor-independent certification does NOT, and no such claim is
  made. G03 is risk_class=high; the resolver was attacked on its
  determinism, boundary-separation, and fail-closed traversal contracts
  rather than skimmed.
- Deterministic resolution from explicit inputs only. resolvePluginPaths
  reads pluginRoot, pluginData, and workspaceRoot as own data properties
  and never consults cwd, HOME, environment variables, a repository
  checkout, or a PATH fallback: a missing field fails MISSING_FIELD, a
  relative root fails ROOT_NOT_ABSOLUTE, and even with PLUGIN_ROOT and
  PLUGIN_DATA exported into the environment the resolver still refuses to
  fall back. Unknown fields (UNEXPECTED_FIELD), accessor properties
  (ACCESSOR_FIELD_DENIED, getter never invoked), and Proxies
  (PROXY_INPUT_DENIED, ownKeys trap never invoked) are rejected before any
  filesystem access. The returned record is frozen and carries a fresh
  workspace-state location whether or not .epistemic-foundry exists yet.
- Spaces and non-ASCII preserved. Roots and portable children with spaces
  and Hangul segments resolve through realpathSync.native to their exact
  canonical path; a fresh workspace has exactly one deterministic
  .epistemic-foundry state location, and creating it then re-resolving is
  required before a CREATE target is granted.
- Installed code and writable data separated. assertDisjoint proves
  PLUGIN_ROOT, PLUGIN_DATA, and the workspace boundary share no directory
  identity and neither nests inside another: nesting plugin data under the
  install root, pointing data at the root, nesting the workspace under the
  install root, or overlapping data with the workspace each fail
  PATH_BOUNDARY_OVERLAP. PLUGIN_ROOT and WORKSPACE_ROOT are read-only, so a
  CREATE against them is denied BOUNDARY_WRITE_DENIED; writable targets are
  limited to PLUGIN_DATA and WORKSPACE_STATE.
- Traversal fails closed. resolveBoundaryPath rejects ../, absolute,
  drive-letter, mixed-separator, //, ./, trailing-dot, trailing-space,
  reserved-name (NUL, CONIN$, COM-superscript), stream (:alternate),
  wildcard/quote/pipe, and embedded-NUL relative paths with
  INVALID_PATH/PATH_ESCAPE_DENIED. Symlinks and junctions inside a boundary
  and linked roots are denied by lstat no-follow plus realpath canonical
  equality (PATH_LINK_DENIED/ROOT_UNSAFE), a missing intermediate parent
  fails PATH_PARENT_MISSING, and mismatched target modes fail
  PATH_TARGET_MISSING/PATH_TARGET_EXISTS. A root replaced after resolution
  is caught by device/inode/birthtime identity recheck
  (BOUNDARY_ROOT_CHANGED), and a spread-copied resolution loses authority
  because the backing roots live in a WeakMap keyed by the frozen record
  (UNRECOGNIZED_PATH_RESOLUTION).
- Dependency and checks: the resolver builds on the sealed G01 plugin
  package scaffold (G01-0001 PASS) and adds no new production dependency.
  Ruff lint and format, the two required checks (path_resolution_test 8/8,
  path_traversal_test 5/5), targeted 13/13, full Python 1261/1261, full
  Node 1291/1291 across 115 files, and git diff --check all pass with zero
  failures.
- Residual limitations: G03 proves path authority resolution, not the
  marketplace install/enable/disable/uninstall lifecycle (the later G04
  gate), and does not claim an OS-enforced sandbox or a race-free durable
  file-handle capability; returned checked paths require effect-time
  re-resolution and are not durable capabilities. Verdict: PASS on the
  exact G03 package contract.
