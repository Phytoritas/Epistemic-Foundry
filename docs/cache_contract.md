# Cache and reproducibility contract

## Authority

Caches are disposable performance projections, never canonical evidence or workflow state. A cache hit may accelerate a node only when the cache key covers every semantic input that could change the result.

## Required key material

- artifact content hashes and source-version IDs;
- schema, ontology, DomainPack and measurement-contract versions;
- prompt, model, provider-adapter and parser versions;
- normalized parameters, random seed and deterministic environment fingerprint;
- policy pack, evidence ACL and workspace snapshot hash;
- code revision and platform-sensitive dependency lock hash.

## Rules

1. Cache keys are content-addressed and namespace-scoped.
2. A cached result retains its original provenance and cannot be relabelled as a new execution.
3. Policy, consent, retraction, correction, lifecycle or security changes may invalidate a cache independently of payload equality.
4. Negative and partial results carry explicit expiry and failure context.
5. Cache restoration validates artifact hashes before registration.
6. Cross-machine reuse is disabled for environment-sensitive outputs unless equivalence is attested.
7. Cache deletion cannot delete Noetic Ledger history.
8. CI measures hit correctness as well as hit rate.

## Required tests

- false-hit mutation tests;
- stale-policy and stale-consent invalidation;
- cross-platform path and locale normalization;
- concurrent writer atomicity;
- corrupted entry quarantine;
- deterministic rebuild comparison;
- eviction without provenance loss.

## B03 continuous-integration cache profile

The cross-platform workflow uses one dependency-cache namespace,
`efoundry-deps-v1`, for npm download data and uv download/build data only. Its
primary key binds the explicit runner-image label, runner architecture,
`package-lock.json`, `uv.lock`, `toolchains/toolchain-lock.json`, and the hashed
Python build-backend constraints. Prefix restore keys are forbidden: a change
to any bound input is a cache miss, not permission to restore stale bytes.

Cache directories live below `runner.temp` and may be discarded at any time.
They never include source, tests, build outputs, reports, work-package
evidence, `.rah` state, credentials, hidden holdouts, Noetic Ledger content, or
any other canonical artifact. Cross-OS archives are disabled, and a cache miss
is explicitly non-fatal; locked dependency installation reconstructs the state.

The workflow pins action revisions to reviewed full commit SHAs and pins
versioned hosted-runner labels. Changing an action revision, runner label,
cache namespace, key material, path, or restore policy requires a new review.
The B03 lint and cache audit validate this policy locally. They prove the
workflow definition, not that GitHub-hosted lanes have run; remote execution
evidence belongs to the B04 integration gate.

Primary documentation checked on 2026-07-27:

- GitHub Actions matrix workflow syntax:
  <https://docs.github.com/en/actions/how-tos/writing-workflows/choosing-what-your-workflow-does/running-variations-of-jobs-in-a-workflow>
- GitHub-hosted runner image labels:
  <https://github.com/actions/runner-images>
- `actions/cache` v5 cache-miss and immutable-cache semantics:
  <https://github.com/actions/cache/tree/v5.0.3>
