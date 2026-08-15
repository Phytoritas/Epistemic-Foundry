# PLUGIN_ALPHA upgrade and rollback composition gap

Status: `APPROVED_FOR_IMPLEMENTATION`

Approved freeze: `PLUGIN_LIFECYCLE_V1`  
Approved by: repository owner, 2026-08-15

This record does not pass `upgrade_rollback_uninstall` and does not treat a
remove followed by an add as an upgrade or rollback.

## Current boundary

The installed Codex CLI exposes plugin `add`, `list`, and `remove`, plus
marketplace management. Marketplace refresh is not a package rollback
primitive. There is no host command that atomically upgrades one installed
plugin version or restores its prior package and state.

The canonical `plugin_upgrade_migration` workflow requires package
verification, isolated probing, migration planning and dry-run, approval,
package/store application, hook re-trust, post-upgrade health and replay,
rollback, and a final immutable install record. Its
`epistemic_foundry.plugin.*` executors do not exist. Z01 owns install-matrix
tests and Z03 owns migration tests/documentation; neither package owns the
missing host lifecycle adapter or Kernel composition.

Consequently, checked-in automation can prove fresh install and uninstall,
but it cannot truthfully manufacture upgrade/rollback semantics by rewriting
the cache, editing Codex configuration, or chaining `plugin remove` and
`plugin add`. Those approaches do not provide atomic activation, failed-health
rollback, migration rollback, hook re-trust, or history preservation.

## Approved product-owner freeze — `PLUGIN_LIFECYCLE_V1`

The following decision is approved for implementation:

1. Define one provider-neutral host lifecycle port with immutable package
   identity, active and previous version identity, prepared/activated state,
   health result, and typed failure outcome.
2. Assign an implementation package and write scope for that port. Z03 keeps
   ownership of the upgrade/rollback matrix; it does not become the package
   installer or state authority.
3. Preparation verifies the exact candidate payload and records the current
   installed payload before any activation. Candidate probing cannot mutate
   the active install or `PLUGIN_DATA`.
4. Activation switches only to the prepared exact package. Store migrations
   run through their existing owners and must supply a rollback operation
   before the candidate becomes active.
5. Changed hooks require new host trust. Declined or unavailable trust yields
   a visible degraded/blocked result and never silently reuses an old trust
   decision for changed bytes.
6. A non-waivable post-upgrade health, replay, integrity, or migration failure
   restores the previous exact package and compatible store state. The failed
   candidate and failure outcome remain visible; rollback never erases
   history.
7. Uninstall removes only the active package cache and plugin/marketplace
   configuration. It preserves `PLUGIN_DATA` and every user-data location
   named by the compatibility matrix.
8. `upgrade_rollback_uninstall` requires a checked-in two-version run covering
   prepare, activate, forced post-upgrade failure, rollback, restored execution,
   and uninstall. Repeated add/remove cannot satisfy this gate.

The implementation owner/path and dependencies are assigned in
`manifests/development_manifest.yaml`. Upgrade and rollback remain `UNVERIFIED`
until the approved lifecycle is implemented and executed; fresh install and
uninstall work may continue independently.

## Implementation ownership

X01 owns the Codex host lifecycle port under `adapters/codex/**`. Its
prepared, active, failed and rollback state is a private versioned adapter
record, not an expansion of canonical `PluginInstallState`. Z03 remains the
two-version execution-matrix owner and depends on X01; it does not install
packages or become lifecycle state authority.

The port never edits Codex cache or configuration directly. It publishes an
exact candidate or captured previous package through a lifecycle-owned local
marketplace and uses the supported `plugin marketplace add`, `plugin add`,
`plugin list` and `plugin remove` operations. Host-reported versions are
advisory: every prepare, activation and rollback result is accepted only after
the concrete installed payload is found and its closed-tree identity matches
the expected package. The host does not expose version-pinned activation, so
that limitation remains an explicit typed capability rather than a guessed
selection rule.

The canonical install-state schema describes a committed installation and is
unchanged. Previous-package bytes, prepared state, failed candidate history
and rollback availability belong only to the X01 transition record until the
canonical upgrade workflow gains a real Kernel executor.
