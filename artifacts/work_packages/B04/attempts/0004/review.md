# B04-0004 canonical projection correction review

Overall package status: `PASS`

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_INTEGRATION_REVIEW`

Assurance limitation: this is a procedurally separate primary-session review;
it is not external actor-independent certification. Fleet and subagents were
not used under the governing correction contract.

## Authority boundary

- Sole canonical authority: `schemas/**` and `openapi/**`.
- Derived runtime snapshot: `src/epistemic_foundry/_canonical/**`.
- Root authority mutation count: 0; reverse synchronization count: 0.
- `pyproject.toml` remained byte-identical and the existing
  `setuptools.build_meta` backend was retained.

## Adversarial findings

1. `B04-MECH001` resolved: the source bundle is canonical-JSON hashed as
   `sha256:47a8d63daadae502bc3fc91c19cebc1f8f04f885e24d6d409c444748e04fd340`.
2. `B04-MECH002` resolved: the projected snapshot bundle is bound as
   `sha256:dde63a97254b2432d0fc1f917e1bd294210f43e19720386ac4295e317a497ed7`.
3. `B04-MECH003` resolved: every registry entry carries distinct typed
   `source_path` and `package_path` fields.
4. `B04-MECH004` resolved: the registry binds projection tool identity and
   version.
5. `B04-MECH005` resolved: staged complete-tree replacement is atomic and a
   second-rename failure restores the prior tree.
6. `B04-MECH006` resolved: source mutation both before and after swap raises
   `SOURCE_CHANGED_DURING_PROJECTION`; the post-swap case rolls back.
7. Missing resources, one-byte tampering, duplicate document IDs, registry
   binding tampering, unregistered extras, link traversal, and unrelated
   destination files all fail closed.
8. Two clean wheels and sdists are byte-equal, the sdist-derived wheel is
   equal, and installed-wheel-only resource use passes from an arbitrary empty
   current directory with source fallback success count 0.

## Regression reconciliation

- Packaging suite: 24 passed, 0 failed.
- Full Python: 946 passed and exactly one F01-owned expected-list migration
  debt. The failure requires F01-0003 to add the already-authorized
  `canonical_projection_freshness` check to its exact test expectation; B04
  causal impact is none.
- Full Node: 267 passed and exactly the pre-existing `S04-TM004` stale manifest
  hash debt. Its test ID, expected hash, actual hash, and affected path match
  the preserved fingerprint; B04 causal impact is none.
- New B04-caused Python or Node failures: 0. New skips/xfails: 0.

## Decision

All six non-waivable mechanism defects are resolved, root and snapshot bytes
converge across 125 resources, the registry is byte-bound by an
ArtifactReceipt, and the packaging/isolation/reproducibility checks pass.
Blocking findings: 0. B04-0004 passes. F01-0003 remains the next required
attempt, and the overall external goal remains active with
`completion_ready=false`.
