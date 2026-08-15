AUTHORIZED_LOCAL_REPAIR

O03 may **reclassify the current one-record validator as structural integrity validation** and add a source-reconstructing validator entirely within its owned path. O03 owns dependency-cluster and Evidence Pack assembly, including deduplication and retention of counter/null/boundary evidence. 

Smallest safe public API change:

```python
validate_evidence_dependency_cluster_shape(payload)
```

This should contain the current closed-schema, vocabulary, ordering, arithmetic-consistency, and self-hash checks. Its documentation must state explicitly that it **does not prove** that the cluster is the deterministic connected component of source evidence units and does not grant scientific independence authority.

Keep the existing:

```python
validate_evidence_dependency_cluster(payload)
```

as a compatibility wrapper or alias to the shape validator, with the same explicit non-authoritative documentation. Do not remove it or strengthen its signature in place: that would deterministically break the R01 caller outside O03’s write scope.

Add an authoritative, plural boundary:

```python
validate_evidence_dependency_clusters_from_sources(...)
```

using the exact existing cluster-builder inputs: all evidence units, all dependency-producing links, `run_id`, `created_at`, and the complete supplied cluster collection. It must rebuild the entire deterministic cluster set and require exact equality—including membership, counts, IDs, and hashes—then return only the rebuilt existing cluster records. It creates no new receipt or artifact type. `validate_evidence_pack` should remain the authoritative pack-admission path and may delegate to this function.

R01’s current standalone use remains:

```text
SPEC_GAP: O03_TO_R01_AUTHORITATIVE_CLUSTER_RECONSTRUCTION_BINDING
```

A self-hashed cluster plus Evidence Pack membership cannot prove the omitted source graph. Treating it as sufficient for `support_count_adjusted / support_count_raw` would violate the invariant that shared samples, datasets, publication families, and derived analyses are clusters rather than independent votes.  R01’s owner must later adopt the full reconstruction-input API; O03 cannot make that cross-package change unilaterally. Missing shared semantics must remain `SPEC_GAP`. 

Thus the O03-local repair can complete truthfully, but neither the legacy one-record validator nor the unchanged R01 caller may be described as establishing authoritative scientific independence.
