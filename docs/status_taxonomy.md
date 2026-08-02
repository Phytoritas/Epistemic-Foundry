# Capability and release status taxonomy

## Work-package and execution outcomes

These outcomes describe a bounded operation or work package. They do not
describe product maturity and must not be substituted for capability or
scientific states.

| Outcome | Meaning |
|---|---|
| `PASS` | Every non-waivable criterion has resolving evidence, all required checks pass, and the required independent review approves the package. |
| `CONDITIONAL` | The checked result is usable only under stated conditions. It is not dependency-satisfying unless the governing contract explicitly permits it. |
| `FAIL` | A clear, non-waivable integrity, security, provenance, or acceptance requirement failed. |
| `BLOCKED` | The contract is clear, but a required external capability, credential, licensed source, infrastructure service, or independent authority is unavailable. |
| `SPEC_GAP` | Higher-order authorities omit or conflict on semantics needed to proceed safely. Lower-order documents and implementations must not invent the missing decision. |

`SPEC_GAP` takes precedence over a plausible local interpretation. `BLOCKED`
must not be used to hide an ambiguous contract, and `PASS` must not be emitted
from tests alone when receipts or independent review are required.

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

`SPECIFIED` and `REFERENCE_BLUEPRINT` are never aliases for `IMPLEMENTED`.
Source files, schemas, examples, or passing specification lint prove only the
surface they actually check. `IMPLEMENTED` requires the declared runtime and
integration gates for that capability.

## Scientific/evolution state

`NOVEL`, `FIT`, `SURVIVED`, `SUPPORTED`, `CAUSALLY_IDENTIFIED`, `REPLICATED`,
and `PROMOTED` are separate states. `UNASSESSED`, `UNDERDETERMINED`,
`REPLICATION_FAILED`, and `SEARCH_EXHAUSTED_WITHIN_SCOPE` are valid outcomes.

Scientific states never imply a work-package `PASS` or a release level. In
particular, `NOVEL`, `FIT`, `SURVIVED`, a model confidence value, or an
advisory backend score cannot be translated into `PROMOTED`.

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
