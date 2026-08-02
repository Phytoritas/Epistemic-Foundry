# B02-0002 exact dependency-lock correction review

Overall correction status: `PASS`

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_REVIEW`

Assurance limitation: `actor_independence=false`. This is a procedurally
separate primary-session review, not external or actor-independent
certification. Fleet and subagents were prohibited and were not used.

## Verified correction

- `pyproject.toml` declares only the canonical `skill-context` group with
  exact `tiktoken==0.13.0`; it is absent from runtime and optional dependency
  metadata.
- uv 0.7.21 reconstructs the preserved pre-correction hashes exactly and the
  new lock adds only `tiktoken` plus `certifi`, `charset-normalizer`, `idna`,
  `regex`, `requests`, and `urllib3`. Unrelated upgrade, downgrade, removal,
  source change, editable path, and floating Git dependency counts are zero.
- Frozen sync passes, the installed version is exactly 0.13.0, `o200k_base`
  loads, all 7 tokenizer vectors pass, and the targeted pytest is 1/1.
- The lock checker passes with 21 packages and 20 registry packages.
- The attempt-local current-input build adapter stages `packages`, `src`,
  `toolchains`, `scripts`, `schemas`, and `openapi`; two builds yield the same
  source snapshot and 11 byte-identical artifacts with zero mismatches.

## Preserved integration finding

The production `scripts/build/double_build.py` remains byte-identical at
`sha256:99f223bd8d4a3d397cf9c560274c498a3a51c15116e094f9896278640aca32df`.
It predates the B04 canonical build hook: its historical staging omits
`scripts`, `schemas`, and `openapi`, and its name-only `build` exclusion also
removes `scripts/build/canonical_registry`. The preserved production-helper
run therefore fails with `ModuleNotFoundError: No module named 'scripts'`.
This failure is not relabeled as PASS and the helper is not modified under
B02's narrow write scope. HD-EF4-J02-SG002-20260730-001 assigns the independent
dependency/build revalidation and any integration correction to the next B04
attempt.

Two exact scratch-cleanup commands were rejected before execution by the
Windows safety hook. No destructive workaround was used; the remaining cache
and diagnostic leaves are recorded in `write-scope-verification.json` and are
not treated as product changes.

## Decision

The exact dependency correction satisfies the B02 correction contract with
product write-scope violations 0 and blocking B02-owned findings 0. B02-0002
passes, while B04 revalidation remains mandatory. The historical B02 root PASS,
J02-0002 FAIL, all retained RAH history, and the dirty worktree remain
immutable. J02-0003 has not started and `completion_ready=false`.
