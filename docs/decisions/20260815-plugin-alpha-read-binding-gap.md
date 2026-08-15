# PLUGIN_ALPHA installed read-tool binding gap

Status: `APPROVED_FOR_IMPLEMENTATION`

Approved freeze: `LOCAL_STDIO_READ_V1`  
Approved by: repository owner, 2026-08-15

This record defines the truthful installed surface while the qualified release
status remains `SPEC_BUNDLE`. It does not pass T01 or any PLUGIN_ALPHA gate.

Current source disposition: `foundry.status` and `foundry.health` are the only
bound MCP handlers. `foundry.map.query` is advertised in the canonical catalog
but dispatches to `UNAVAILABLE` before any workspace scan. The remaining ten
stateful/planning reads are likewise advertised and unavailable with their
individual reason. This source disposition is not an installed-runtime or gate
claim.

The currently enabled cached install
`4.0.0+codex.20260814202914` predates that disposition. Its generated
`dist/mcp-server.mjs` still binds `foundry.map.query`, accepts
`workspace_id` from tool arguments, and uses `EFOUNDRY_WORKSPACE_ROOT` without
an authenticated authorization context. It must not be treated as the
qualified implementation. The next source-to-installed cutover must regenerate
`dist/` from the fail-closed source and replace the cached install; copying the
old generated handler back into source is forbidden.

The fail-closed source still has one transport-compatibility gap: its local
JSON-RPC parser accepts only safe-integer numeric IDs, while canonical T01
preserves and echoes every exact integral JSON number. This must be removed by
projecting the canonical T01 framing into the payload, not by maintaining a
second numeric-ID parser in the plugin source.

## Safe installed diagnostics

`foundry.status` and `foundry.health` may remain available as non-secret,
Node-local diagnostics. They report the installed payload and explicit
degraded state and do not claim a durable Foundry read model.

## `foundry.map.query`

`EFOUNDRY_WORKSPACE_ROOT` and `EFOUNDRY_WORKSPACE_ID` are selectors only. They
do not prevent caller-controlled relabeling and are not an authenticated T01
`AuthContext`. T01 additionally requires a trusted principal, a binding-owned
workspace identity, and a policy-derived `mcp.read.map` capability before
handler execution. The current installed stdio server has no ratified producer
for those values and bypasses the shared `ToolService` authorization path.

The first required decision is runtime ownership, not credential format. The
installed entry point is a Node stdio server and never invokes the existing
Python T01 `AuthProvider`/`ToolService`; Python also has no workspace-map
producer. Delegating to Python would therefore create a second producer or a
Python-to-Node loop. The coherent owner is the existing Node T01
`handlerPort.call` boundary in `packages/plugin-host/src/mcp/read/**`.

### Approved product-owner freeze — `LOCAL_STDIO_READ_V1`

The following decision is approved for implementation:

1. T01's canonical Node JSON-RPC framing and injected handler port are the sole
   installed read boundary. The payload projects that framing; it must not keep
   a second request-ID parser, error mapper, or ToolService implementation.
   T01's descriptor projection also carries the canonical authorization order.
2. `foundry.map.query` is the only newly bound read in v1. It calls the existing
   workspace-map producer. The four durable-plan tools remain `UNAVAILABLE`;
   the other reads remain unavailable until their canonical producers exist.
3. A separate versioned `LocalStdioBinding` is stored only at
   `<PLUGIN_DATA>/local-stdio-binding.json`. A binding inside a workspace is
   ignored and can never grant authority. The record binds `principal_id`,
   `principal_type`, `workspace_id`, the absolute workspace root and its G03
   root identity, an `mcp.read.*`-limited capability set, issue/expiry times,
   the protocol and binding versions, and `grant_hash`.
4. This binding is deliberately not `CapabilityLease v2`: changing that
   preimage would invalidate E03 lease hashes and make one local read depend on
   the blocked durable substrate. `LocalStdioBinding` cannot express E03
   privileged capabilities and cannot be promoted into a lease.
5. `PLUGIN_DATA` and the workspace root are location selectors until G03
   resolves them as disjoint, ordinary, non-link roots. Every map request
   reopens the binding through the `plugin_data` boundary and rechecks both root
   identities before scanning. Environment values and tool arguments never
   grant capabilities.
6. Missing, malformed, expired, or root-mismatched binding returns
   `UNAUTHENTICATED`; missing `mcp.read.map` returns `UNAUTHORIZED`; a request
   workspace mismatch or changed boundary root returns `WORKSPACE_DENIED`;
   scan-time workspace mutation returns retryable `INTERNAL`. Runtime-specific
   path codes remain in `details`, never as new top-level error codes.
7. Without a binding, `foundry.status` and `foundry.health` remain pre-auth
   degraded diagnostics, return the fixed result scope
   `WS-UNBOUND-DIAGNOSTIC`, and never echo a caller or environment workspace ID.
   With a binding they follow the full T01 authorization order.
8. T01 owns the read composition and the binding contract under
   `contracts/mcp/t01/**`; T03 alone owns `.mcp.json`; X01 owns the payload but
   excludes those named T01/T03 paths. The manifest scope amendment is bundled
   with the `DURABLE_FORGE_V1` scope amendment in one authorized patch plan.
9. The enabled pre-cutover cache is not a rollback target because it restores
   an unauthenticated `map.query`. The first valid rollback target is a newly
   generated fail-closed payload.

### G03 root identity projection

`LOCAL_STDIO_READ_V1` authorizes the following code-local
`G03_ROOT_IDENTITY_V1` projection. G03 remains its only producer; T01 embeds
the returned record unchanged and includes it in `grant_hash`.

The closed record is:

```json
{
  "identity_version": "G03_ROOT_IDENTITY_V1",
  "volume_id": "1861384736",
  "file_id": "95701492086585563",
  "birthtime_ns": "1785139035485633300"
}
```

G03 derives the values from `fs.lstatSync(canonicalPath, { bigint: true })`
after its existing ordinary-directory, no-link and native-realpath checks.
`volume_id` is the canonical unsigned decimal `dev`; `file_id` is the
canonical non-zero unsigned decimal `ino`; `birthtime_ns` is the canonical
positive decimal `birthtimeNs`, or `null` only when the host reports zero.
An absent or non-injective file identity fails closed as
`ROOT_IDENTITY_UNSUPPORTED`.

Canonical serialization is compact JSON with keys ordered
`birthtime_ns`, `file_id`, `identity_version`, `volume_id`. There is no
separate root-identity hash: T01's `grant_hash` is the sole digest. Equality
requires all four semantic fields to match exactly. Each map request obtains
a fresh G03 resolution and compares both the workspace and `PLUGIN_DATA`
records; a changed capture capability or root is a boundary change.

G03 exposes only a resolver-gated accessor, strict serializer and equality
function under `packages/plugin-host/src/paths/**`. The existing resolution
object shape does not grow, and copied caller objects cannot obtain an
identity because the private WeakMap gate remains authoritative.

This binding is not a security boundary against the same local user who owns
`PLUGIN_DATA`; it prevents workspace/repository content and model-supplied tool
arguments from granting or relabeling authority. Its exact host-provided
`PLUGIN_DATA` location is resolved through the approved host boundary on every
request. Until that implementation is installed and its binding validates,
`foundry.map.query` must continue to return `UNAVAILABLE`.

## `foundry.artifact.get`

This tool remains `UNAVAILABLE`. The catalog references both ArtifactManifest
and ArtifactReceipt, but no canonical composite `data` projection, receipt
cardinality/order, atomic artifact-ID lookup, or workspace/confidentiality
resolver is defined. D03 alone is a byte store, not an authorization port.

Required decision: T01 must define one versioned ArtifactGetProjection (or
explicitly reduce the response to one canonical schema), deterministic receipt
selection, actual domain-schema validation, and an authorized workspace-root
resolver. The outer pure-read envelope keeps `receipts: []`.

## Other read tools

- `foundry.session.get`: unavailable until the durable session composition
  contract is authorized and implemented.
- `foundry.claim.get`, `foundry.atlas.query`, `foundry.passport.get`: unavailable
  because their authoritative promotion/publication producers do not exist.
- `foundry.replay.diff`: unavailable because no canonical run-store projection
  is bound.

The honest installed count is therefore two diagnostic tools now. Additional
canonical reads become available only through their existing authority and
authorization boundaries; the plugin adapter must not fabricate stores or
wire projections to increase the count.
