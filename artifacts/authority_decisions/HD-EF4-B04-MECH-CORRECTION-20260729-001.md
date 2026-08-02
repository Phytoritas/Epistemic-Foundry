# HumanDecision HD-EF4-B04-MECH-CORRECTION-20260729-001

Status: `CANONICAL PRODUCT-OWNER CORRECTION DECISION`

This decision records the product owner's explicit approval to continue past
the verified B04-0003 implementation failure. It applies prospectively to
`B04-0004`; it does not modify or relabel B04-0003, E0039, E0040, generation
`000038-73e31b8e`, prior B04 attempts, F01-0002, or the dirty worktree.
`completion_ready` remains false.

## Authorized correction

B04-0004 may modify only the following already B04-owned product surfaces:

- `scripts/build/canonical_registry/**`
- `tests/packaging/**`
- `src/epistemic_foundry/contracts/registry.py`
- `src/epistemic_foundry/_canonical/**`
- `artifacts/work_packages/B04/**`

The correction must resolve all six verified defects:

1. `B04-MECH001_SOURCE_BUNDLE_ALGORITHM_MISMATCH`
2. `B04-MECH002_PROJECTED_SNAPSHOT_HASH_MISSING`
3. `B04-MECH003_DISTINCT_SOURCE_PACKAGE_PATHS_MISSING`
4. `B04-MECH004_PROJECTION_TOOL_IDENTITY_MISSING`
5. `B04-MECH005_ATOMIC_TREE_REPLACEMENT_MISSING`
6. `B04-MECH006_SOURCE_CHANGE_ERROR_MISSING`

The source bundle uses deterministic canonical JSON over the approved sorted
inventory. The registry binds the source bundle and projected snapshot,
distinct source and package paths, counts, identities, content hashes, and the
projection tool identity/version. Projection stages a complete tree, rechecks
the sealed source bundle, replaces the live tree as a unit with fail-closed
recovery, and emits `SOURCE_CHANGED_DURING_PROJECTION` when authority bytes
change during projection.

## Preserved prohibitions

The following remain read-only for this correction:

- `schemas/**`
- `openapi/**`
- `pyproject.toml`
- F01/F02/F03 implementation and test paths
- every prior attempt, report, review, command ledger, receipt, and RAH
  generation

Root schemas and OpenAPI remain the sole canonical authority. The package
snapshot remains a one-way derived projection. Reverse synchronization,
source-tree runtime fallback, editable-install-only success, partial-copy
success, placeholder hashes, skip/xfail masking, reset/clean/stash, Fleet,
and subagents remain forbidden.

## Gate order

```text
B04-0003 immutable FAIL
  --resolved prospectively by this decision--> B04-0004
B04-0004 verified PASS
  --matching projection receipt--> F01-0003
F01-0003 verified PASS
  --> F02 and F03 dependency-ready
```

B04-0004 must pass projection, registry, clean wheel/sdist,
sdist-to-wheel, installed-wheel-only, arbitrary-cwd, tamper, deterministic
rebuild, regression, write-scope, receipt, and separate primary-session review
gates. F01-0003 must not start before that PASS.
