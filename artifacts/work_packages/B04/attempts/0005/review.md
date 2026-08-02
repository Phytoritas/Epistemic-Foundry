# B04-0005 dependency and build revalidation review

Overall package status: `PASS`

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_INTEGRATION_REVIEW`

Assurance limitation: `actor_independence=false`. This is a procedurally
separate primary-session review and is not external actor-independent
certification. Fleet and subagents were not used.

## Verified boundary

- B02-0002 remains sealed by E0090/E0091. `pyproject.toml` declares exactly
  `dependency-groups.skill-context = ["tiktoken==0.13.0"]`; `uv.lock` is
  current, frozen sync passes, `o200k_base` loads, and 7/7 fixed tokenizer
  vectors pass.
- Runtime and optional distribution metadata do not expose `tiktoken`.
- The current wheel is byte-identical to B04-0004. The current sdist differs
  from B04-0004 only in `pyproject.toml`; unrelated sdist drift count is 0.
- Root canonical authority remains `schemas/**` and `openapi/**`. All 124
  schemas plus OpenAPI 3.1.1/33 operations match the 125-resource package
  snapshot and registry at source `sha256:47a8d63daadae502bc3fc91c19cebc1f8f04f885e24d6d409c444748e04fd340`, snapshot
  `sha256:dde63a97254b2432d0fc1f917e1bd294210f43e19720386ac4295e317a497ed7`, and registry `sha256:5f3c4514b3801cc66cc0a403d49c1dc380f7665ddc570d4987072a6f77fde1dd`.
- Two clean builds, sdist-to-wheel equality, installed-wheel-only registry and
  representative schema/OpenAPI loading, arbitrary empty cwd, missing-resource
  rejection, tamper rejection, and source fallback success count 0 pass.
- B04-0005 modified no product files; it adds attempt-local evidence only.

## Regression and ownership reconciliation

- Packaging: 24 passed, 0 failed, 0 skipped.
- Full Python is not green: 963 passed and exactly one
  `EXPECTED_J02_0003_MIGRATION_DEBT` remains. The J02 checker still omits the
  canonical `skill-context` dependency group. B04 causal impact is none.
- Full Node is not green: 457 passed and exactly one
  `EXPECTED_S04_ACTIVE_BINDING_MIGRATION_DEBT` remains. Its current actual
  manifest hash is `7d1d3248dc3e2ca56d8f08ec282aa3d95bea9466ba6b7580fccff81e0f639319` against stale expected hash
  `456330ae4aa950d1410d5180ad704927c5ec78a741d3c616d7a1cfd5bb0054a7`.
  This is not described as an unchanged pre-existing fingerprint; the approved
  successor manifest changed and S04 must update the active source binding.
- The production `scripts/build/double_build.py` stale-staging diagnostic is
  preserved and not hidden. The B04 canonical packaging verifier is the
  passing package-boundary evidence. No out-of-scope helper edit was made.
- New B04-owned Python or Node failures: 0. New skips/xfails: 0.

## Decision

The B02 dependency correction crosses the B04 build/package boundary without
runtime metadata exposure, canonical projection drift, unrelated distribution
drift, or a B04-owned regression. blocking B04-owned findings: 0. B04-0005
passes. The global implementation gate remains failed, both global suites are
truthfully non-green, S04-TM004 correction is next, and
`completion_ready=false`.
