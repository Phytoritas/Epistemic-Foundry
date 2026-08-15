# O03 Evidence Pack boundary review

Continue as an advisory reviewer for Epistemic Foundry v4. Determine whether
the current O03 input-boundary defects are locally repairable despite the
separate O01 scope-partition semantic gap. Return exactly one of
`AUTHORIZED_LOCAL_REPAIR`, `SPEC_GAP`, or `NO_BLOCKER`, followed by only
material findings and the smallest safe change. Do not ask to run tests.

## Authority and dependency boundary

- O03 is “Dependency clusters and Evidence Pack assembly”, depends on O01,
  and solely owns `python/epistemic_foundry/retrieval/evidence_pack/**`.
- Exit criteria: shared samples/preprints are deduplicated; counter/null/
  boundary lanes remain included.
- `MASTER_SPEC.md` and product invariants forbid evidence-count inflation from
  dependency clusters and require counter/null/boundary/method lanes to remain
  visible.
- Canonical `evidence-dependency-cluster.schema.json` and
  `evidence-pack.schema.json` define the emitted closed records.
- O01 has a separate unresolved contract for how `scope_filter` relates to
  `QueryPlan.scope_partitions`. O03 must not invent that projection. Its local
  assembly can still consume an already validated QueryPlan, lane receipts,
  and completeness certificate without deciding that missing O01 meaning.

## Current O03 behavior

`contracts.py` validates evidence units, derives dependency edges from shared
datasets/experiments/cohorts/publication families/team series/reused artifacts
and explicit review/citation links, seals deterministic clusters, requires
every evidence unit to hold exactly one pack role, reconciles every retrieval
result to evidence or a typed unresolved reason, keeps metadata-only evidence
out, computes effective independent count and role quotas, and can rebuild a
pack plus clusters from bound inputs.

## Concrete current-source candidates

1. `_mapping` shallow-copies an arbitrary Mapping and then calls
   `_canonical_json`, but nested arrays/mappings remain caller-owned. Public
   builders and validators subsequently read them again. A Mapping whose
   `items()` yields duplicate projected keys is silently last-wins collapsed;
   stateful nested sequences can change between hash/canonicalization and
   semantic use. The repair candidate is one primitive-first recursive JSON
   snapshot at each public boundary, rejecting duplicate projected keys,
   cycles, byte-like/non-JSON values, non-string keys, and non-finite numbers,
   followed by all validation/derivation on that owned snapshot.

2. `role_quotas` is normalized with `dict(role_quotas or {})`. Falsey values
   such as `""`, `[]`, or `0` therefore masquerade as “no quotas”, while other
   malformed values can leak raw constructor errors. The repair candidate is
   exact `None` or Mapping validation, primitive snapshot, closed role keys,
   and exact nonnegative integer values before any use.

3. `_text` currently calls `.strip()` and returns the stripped value for IDs,
   source keys, versions, result IDs, and provenance refs. The canonical output
   schemas generally require string/minLength but do not authorize identity
   rewriting. Decide whether O03 must preserve exact string bytes and reject
   edge-whitespace identifiers instead of silently normalizing them, while not
   loosening fields whose local input contract explicitly requires nonblank
   text.

## Decision requested

- Are these O03-local integrity repairs, or does any require a shared schema or
  O01 semantic decision?
- Identify the exact public boundaries that need a single snapshot so aliases
  cannot be read twice.
- Identify any more important local path that still allows dependency-count
  inflation, lane disappearance, or a caller-authored pack/cluster to pass
  without deterministic reconstruction.

Do not redefine QueryPlan partitions, retrieval execution, scientific support,
or promotion authority.
