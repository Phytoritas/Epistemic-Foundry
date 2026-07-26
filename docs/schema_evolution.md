# Schema evolution and compatibility

## Versioned objects

Every canonical schema has a stable `$id`, explicit version in artifacts, strict unknown-field policy, and fixtures. Runtime stores the schema bundle hash in RunSpec.

## Compatibility classes

- `BACKWARD_COMPATIBLE`
- `FORWARD_COMPATIBLE`
- `FULLY_COMPATIBLE`
- `BREAKING`
- `LOSSY`

## Breaking-change sequence

1. proposal and affected-object inventory,
2. SchemaMigration artifact,
3. forward transform and, where possible, reverse transform,
4. golden fixtures,
5. dry run against a frozen snapshot,
6. independent contract review,
7. approval record,
8. migration event,
9. projection rebuild,
10. replay and semantic-equivalence report.

## Prohibitions

- changing a schema in place while keeping the same hash,
- silently dropping unknown or unconvertible data,
- using application fallback to hide an incomplete migration,
- rewriting old artifacts to look native to the new schema,
- starting parallel consumers before the shared contract is frozen.
