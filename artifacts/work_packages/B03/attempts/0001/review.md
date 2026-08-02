# B03-0001 independent review of bounded-agent work

- Author: the bounded implementation agent(s) that authored the B03
  cross-platform CI workflow (.github/workflows/ci.yml), the two
  required-check validators (scripts/ci/ci_matrix_lint.py,
  scripts/ci/cache_key_audit.py), the ten-test fail-closed mutation suite
  (scripts/ci/test_ci_policy.py) and the cache/reproducibility contract
  (docs/cache_contract.md). Reviewer: this sealing session, a distinct
  actor that did not author this attempt. Author/reviewer separation
  holds (actor_independence=true); external actor-independent
  certification does not.
- Mode: INDEPENDENT_REVIEW_OF_BOUNDED_AGENT_WORK. Blocking findings: 0.
- Scope: the manifest write scope is .github/workflows/**, scripts/ci/**
  and docs/cache_contract.md. This session makes ZERO edit to the CI
  config: the five product files are hash-pinned as they currently are
  and every mutation counter is zero. No canonical source, schema,
  manifest, or .rah/ state was touched.
- Exit criterion 1 - Linux/macOS/Windows lanes defined: VERIFIED.
  ci_matrix_lint (python scripts/ci/ci_matrix_lint.py) asserts matrix.os
  is exactly {ubuntu-24.04, macos-15, windows-2025} -- three versioned
  hosted-runner labels, no -latest moving alias -- with fail-fast: false
  so every OS produces a result, the job running on ${{ matrix.os }}.
  Permissions are exactly contents: read; pull_request_target and
  suppressed failures are rejected; every action is pinned to the
  reviewed full commit SHA and appears exactly once; and the
  setup-node/python/uv versions are bound to toolchains/toolchain-lock
  .json. The validator exits 0 with an empty failure list.
- Exit criterion 2 - caches are disposable and hash-keyed: VERIFIED.
  cache_key_audit (python scripts/ci/cache_key_audit.py) asserts exactly
  one reviewed actions/cache step whose two paths live below runner.temp
  (efoundry-cache/npm, efoundry-cache/uv) and overlap none of
  .git/.rah/.venv/artifacts/build/dist/ledger/node_modules/reports/src/
  tests. The key is bound to matrix.os + runner.arch + exactly one
  hashFiles over the four lock inputs (package-lock.json, uv.lock,
  toolchains/toolchain-lock.json, toolchains/python-build-constraints
  .txt); prefix restore-keys are absent, enableCrossOsArchive is false,
  and fail-on-cache-miss is false so a miss is non-fatal and locked
  installation reconstructs the state. The validator exits 0 with an
  empty failure list.
- Fail-closed proof. test_ci_policy runs ten mutation tests that feed
  mutated copies of the workflow to both validators and confirm each
  REJECTS the reviewed drift shapes: a moving runner alias
  (ubuntu-latest), a moving action tag (checkout@v6), a duplicate
  approved action, pull_request_target, a dropped uv.lock hash input, a
  prefix restore key, a cross-OS archive, a fatal cache miss, and a
  canonical (artifacts) cache path. All ten pass.
- Attestation, not authorship. The two required checks are the package's
  own Python validators, run via python scripts/ci/*.py exactly as the
  manifest names them; both report status=PASS with failures=[]. B03
  reached GREEN with no substantive edit to the workflow, the validators,
  the mutation suite, or the cache contract.
- Gates at review time: ci_matrix_lint PASS (failures=[]), cache_key_audit
  PASS (failures=[]), test_ci_policy 10/10, the full Python suite green,
  the live full Node suite green with zero failures, and git diff --check
  clean. B03 depends on B01; the sealed B01-0001 attempt is the build
  dependency and regression baseline.
- Honest standing risk (scope boundary, not a weakening): the local
  checks prove the workflow DEFINITION -- the three OS lanes, the pinned
  actions, and the disposable hash-keyed cache policy -- not that the
  GitHub-hosted ubuntu-24.04/macos-15/windows-2025 lanes have actually
  executed. Hosted-run evidence is the B04 integration gate, outside B03.
- Residual limitations: B03 attests the CI config the repository already
  carries; it does not re-author it, makes no product-maturity or
  release-readiness claim, does not assert a GitHub-hosted run, does not
  claim SBOM/signing/release-provenance (Z-phase scope), and this review
  is not external actor-independent certification.
