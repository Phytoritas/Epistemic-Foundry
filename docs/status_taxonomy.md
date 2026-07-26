# Capability and release status taxonomy

## Capability status

| Status | Meaning |
|---|---|
| `SPECIFIED` | A normative contract exists; production code is not implied. |
| `REFERENCE_BLUEPRINT` | A static example/package layout exists; it is not an installable implementation claim. |
| `IMPLEMENTED` | Source code exists and declared unit/integration gates pass. |
| `EXPERIMENTAL` | Implemented behind an explicit flag; compatibility or evidence is incomplete. |
| `DEFERRED` | Intentionally outside the current release. |
| `UNSUPPORTED` | The product explicitly does not provide the capability. |
| `DEGRADED` | The capability is partially available and limitations are surfaced. |
| `BLOCKED` | A non-negotiable contract cannot be preserved. |
| `INVALIDATED` | Previously accepted output is no longer valid after leakage, retraction, drift, or dependency change. |

## Scientific/evolution state

`NOVEL`, `FIT`, `SURVIVED`, `SUPPORTED`, `CAUSALLY_IDENTIFIED`, `REPLICATED`,
and `PROMOTED` are separate states. `UNASSESSED`, `UNDERDETERMINED`,
`REPLICATION_FAILED`, and `SEARCH_EXHAUSTED_WITHIN_SCOPE` are valid outcomes.

## Release levels

- `SPEC_BUNDLE`
- `PLUGIN_ALPHA`
- `EVOLUTION_MVP_50`
- `PILOT_200`
- `PRODUCTION_2000`
- `CROSS_DOMAIN_QUALIFIED`

This v4 package is a `SPEC_BUNDLE`. It does not claim `PLUGIN_ALPHA`,
evolution runtime implementation, qualified scientific performance, or
production readiness.
