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
