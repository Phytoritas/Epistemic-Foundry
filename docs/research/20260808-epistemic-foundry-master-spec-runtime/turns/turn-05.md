# Pro turn 05

- session: `pro-epistemic-085944-9b1062`
- recorded: 2026-08-08T09:13:51Z
- prompt sha256: `03548ce6b5e90eaa49d91cb757c3f84de959bb75e75ce81a835f87918741b889`
- answer sha256: `caab3bf05cc626e73d29710aad6fd8b9fec7cfa61de28ff7aecb8e5e2a16a1f0`

## Question

# Epistemic Foundry: adjudicate an N03-independent U01 runtime correction

Your last answer correctly found that the supplied packet did not prove another
dependency-ready package. Codex then inspected the live repository and found a
stronger, N03-independent candidate. Please inspect the attached current U01
source and canonical OpenAPI rather than relying on the prior packet.

## Newly observed current-state evidence

- U01 (`OpenAPI server and generated clients`) owns `packages/ui-api/**` and
  `web/src/generated/**` and depends only on C04 and T04.
- Its canonical public endpoint `GET /api/v1/health/live` is unauthenticated and
  returns exactly `{ "status": "live" }`.
- `packages/ui-api/src/openapi/server-surface.mjs` explicitly says it is not an
  HTTP server. It can load the route table and dispatch an operation ID to an
  injected handler, but it never accepts an HTTP request.
- No `node:http`, `createServer`, or `listen` implementation exists under
  `packages/ui-api/src/**`.
- The generated client can build the `getLiveness()` request descriptor, but a
  caller-supplied transport is still required.
- The historic U01 report explicitly excludes a live HTTP server. Therefore its
  PASS claim does not establish the current manifest title's executable server
  behavior; source observation outranks that report for runtime reachability.
- This endpoint does not perform scheduling, RoleSpec compilation, adapter
  selection, provider execution, run admission, or any canonical mutation. It
  therefore does not consume the unresolved N03-to-N02 execution binding.

## Proposed bounded correction

Within `packages/ui-api/src/openapi/**` only:

1. add a provider-neutral Node `http` adapter that accepts a canonical route
   table/bound server surface;
2. bind only `getLiveness` to the exact canonical response;
3. convert one matching GET request to `dispatch(operationId, request)` and an
   exact HTTP 200 JSON response;
4. fail closed for unbound operations, unsupported methods, invalid base paths,
   bodies, oversized input, malformed URLs, and handler exceptions;
5. expose lifecycle methods that permit an injected or ephemeral listener but
   do not auto-start a server on import;
6. leave the other OpenAPI operations unclaimed and unbound.

No schema, workflow, manifest, package metadata, N02/N03, provider, transport
kernel, plugin, status, or product-completion change is proposed.

## Decision requested

Return exactly one of:

- `U01_CORRECTION_AUTHORIZED`: give the smallest exact behavior and any
  additional fail-closed constraints required by the attached contracts; or
- `U01_CORRECTION_REJECTED`: cite the current authoritative locator that assigns
  the live HTTP listener elsewhere or makes U01 dependency-unready.

Do not authorize the separate N03 shared-contract amendment in this turn. Do
not claim the complete API, plugin, or product is operational.

## Pro answer (advisory; verify locally)

# `U01_CORRECTION_AUTHORIZED`

U01 may implement the bounded HTTP liveness correction **without resolving the separate N03 execution-binding gap**.

The supplied authority places API handlers and the server runtime in U01 or later runtime packages, while the current `server-surface.mjs` explicitly stops at an immutable operation-to-handler dispatch table and performs no I/O. The current public barrel likewise exposes only OpenAPI-derived route-table and dispatch primitives.    

The canonical contract defines exactly one suitable first endpoint:

```text
GET /api/v1/health/live
operationId: getLiveness
authentication: none
required capability: none
request body: none
response: 200 application/json
body: {"status":"live"}
```

The response schema is closed and permits no additional fields.  

## Exact authorized files

Create or modify only:

```text
packages/ui-api/src/openapi/node-http-adapter.mjs
packages/ui-api/src/openapi/index.mjs
```

The second file may change only to export the new bounded adapter and its lifecycle surface.

Keep these read-only:

```text
packages/ui-api/src/openapi/server-surface.mjs
packages/ui-api/src/openapi/route-table.mjs
packages/ui-api/src/openapi/openapi-source.mjs
openapi/epistemic-foundry-v1.openapi.yaml
```

Do not change:

```text
schemas/**
workflows/**
manifests/**
packages/*/package.json
web/src/generated/**
packages/transport-kernel/**
packages/foundry-kernel/**
packages/role-router/**
N02/N03 source
plugin or product-status files
```

If the attached 30-line OpenAPI public barrel is not locally located at `packages/ui-api/src/openapi/index.mjs`, stop and report its actual authoritative path rather than creating a second barrel.

# Smallest exact behavior

## 1. Construction

Add one factory with the semantic role:

```text
createNodeHttpLivenessAdapter({
  routeTable,
  requestIdFactory,
  serverFactory
})
```

`serverFactory` may default to Node’s `node:http.createServer`, but it must remain injectable.

At construction time, the adapter must:

1. accept only a route table derived from the canonical OpenAPI document;
2. locate exactly one canonical `getLiveness` operation;
3. verify that its projected method and relative path are `GET` and `/health/live`;
4. derive the full request target from the canonical `/api/v1` base path;
5. call the existing `bindServerSurface()` with exactly one handler;
6. bind that handler only to `getLiveness`;
7. return exactly the immutable value:

```json
{"status":"live"}
```

The existing surface already rejects undeclared handlers and records every declared-but-unbound operation as an immutable coverage gap. The new adapter must preserve that behavior rather than pretending the route surface is complete. 

For the current 33-operation document, the resulting coverage must remain:

```yaml
coverageState: PARTIAL
boundOperationCount: 1
boundOperationIds:
  - getLiveness
missingOperationCount: 32
```

Do not bind readiness, capabilities, runs, documents, retrieval, deliberation, evolution, validation, approvals, artifacts, or any other operation. The canonical contract currently contains 33 operations, but only liveness is authorized by this correction. 

## 2. Request handling

A request may reach `surface.dispatch()` only when all of the following are true:

```text
method is exactly GET
raw request target is exactly /api/v1/health/live
query string is absent
fragment is absent
trailing slash is absent
request body contains exactly zero bytes
Transfer-Encoding is absent
Content-Length is absent or exactly 0
operation isBound(getLiveness) is true
```

Do not normalize any of the following into the liveness route:

```text
/api/v1/health/live/
/api/v1//health/live
/api/v1/health/../health/live
/api/v1/health/live?x=1
percent-encoded aliases
absolute-form foreign URLs
HEAD /api/v1/health/live
OPTIONS /api/v1/health/live
POST /api/v1/health/live
```

Use the WHATWG `URL` parser only as validation; also require the original request target to match the canonical target exactly. Node provides a standards-based WHATWG `URL` implementation for parsing absolute or base-relative input. ([Node.js][1])

Do not dispatch before the request stream reaches `end` and zero body bytes have been confirmed. Receipt of any body byte is a bounded payload violation, not an ignored extension.

## 3. Success response

A successful dispatch must produce exactly:

```http
HTTP/1.1 200 OK
Content-Type: application/json; charset=utf-8
Cache-Control: no-store
Content-Length: <exact UTF-8 byte length>

{"status":"live"}
```

The adapter must validate the handler return value after dispatch:

```text
plain object
own enumerable key set exactly ["status"]
status exactly "live"
no accessor
no prototype-dependent property
no additional data
```

Do not expose any of the following in headers or body:

```text
software or package version
filesystem path
OpenAPI document path
route-table hash
host capabilities
credentials
provider state
dependency readiness
N02/N03 state
stack trace
internal error text
```

The OpenAPI contract explicitly defines liveness as minimal and prohibits version, path, or credential detail in the response. 

# Required fail-closed behavior

## Route and method failures

No unbound operation may fall through to another handler.

Recommended mappings, using only the existing canonical error vocabulary:

```text
malformed request target
→ 400 MALFORMED_REQUEST

query, fragment, encoded alias, or structurally invalid request
→ 400 MALFORMED_REQUEST

unbound path or unsupported method
→ 404 NOT_FOUND

any body byte, positive Content-Length, or Transfer-Encoding
→ 413 PAYLOAD_TOO_LARGE

handler exception or noncanonical handler result
→ 500 INTEGRITY_RECONCILIATION_FAILED
```

Do not add a new error code or alter OpenAPI. When an HTTP response object exists, errors must use `application/problem+json` and satisfy the current closed `ApiProblem` shape.  

An HTTP parser failure occurring before a request object exists must close the connection with a minimal 400 response and must never invoke `dispatch()`.

Errors sent over HTTP must not serialize the existing `OpenApiSurfaceError` details directly, because those details may contain document paths, operation identifiers, or internal diagnostics.

## Protocol features excluded

Fail closed for:

```text
CONNECT
Upgrade / WebSocket
Expect: 100-continue
HTTP tunnelling
request trailers
streaming responses
compression
CORS negotiation
HTTP/2
TLS termination
proxy trust
```

No fallback route is permitted.

## Lifecycle

Importing the module must have no side effect:

```text
no createServer()
no listen()
no socket binding
no timer
no process signal handler
no process.exit()
no global singleton
```

The returned lifecycle surface may expose:

```text
handleRequest(request, response)
listen({host, port})
address()
close()
```

Constraints:

* `listen()` is explicit.
* Default host is loopback, not `0.0.0.0` or `::`.
* Default port is `0`, allowing an ephemeral listener.
* A second `listen()` while active fails.
* `close()` is idempotent and resolves only after the server has stopped accepting new connections.
* The adapter must not report itself as listening before Node emits the listening event.
* Header and request timeouts must be finite and nonzero.
* Parser, timeout, upgrade, and client-error paths must never reach the OpenAPI dispatch surface.

Node’s HTTP server exposes explicit request/header timeout controls and shutdown semantics; finite limits and explicit close behavior are required here rather than relying on an indefinitely open listener. ([Node.js][2])

# Authority and state boundaries

This endpoint is an unauthenticated, side-effect-free process liveness read. It must not:

```text
authenticate a scientific role
issue a capability
create ActionIntent or EffectReceipt
write an artifact
append a scientific ledger event
admit a run
inspect scheduler state
invoke N02
resolve N03
call a provider
change product status
```

The canonical REST contract states that `GET` never changes state or triggers another effect. 

The adapter must not claim:

```text
API_COMPLETE
SERVER_PRODUCTION_READY
PLUGIN_OPERATIONAL
transport-kernel implemented
readiness endpoint implemented
authentication middleware implemented
all 33 operations reachable
completion_ready=true
```

# Stop condition

Stop without editing if any one of the following is discovered locally:

1. C04 or T04 is not a current satisfied dependency of U01.
2. The existing U01 write scope does not include both authorized files.
3. The canonical route-table projection cannot derive and verify the liveness method, path, operation ID, base path, and response contract without introducing a second route authority.
4. Serving the endpoint requires changing OpenAPI, schemas, package metadata, another package, or any N02/N03 contract.
5. The listener can only be exposed through a package-private import rather than the current U01 public surface.

In that case, report the exact missing locator or owner as a new bounded `SPEC_GAP`; do not work around it.

This authorization is limited to one real runtime path:

```text
Node HTTP request
→ exact canonical liveness route
→ existing bound dispatch surface
→ exact 200 {"status":"live"}
```

It does **not** authorize the N03 shared-contract amendment or establish that the complete API, plugin, or product is operational. The supplied packet explicitly separates this endpoint from scheduling, provider execution, run admission, and canonical mutation. 

[1]: https://nodejs.org/api/url.html "https://nodejs.org/api/url.html"
[2]: https://r2.nodejs.org/docs/latest-v24.x/api/http.html "https://r2.nodejs.org/docs/latest-v24.x/api/http.html"
