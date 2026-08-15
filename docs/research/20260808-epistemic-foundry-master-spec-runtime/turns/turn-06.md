# Pro turn 06

- session: `pro-epistemic-094927-26e119`
- recorded: 2026-08-08T10:01:21Z
- prompt sha256: `a89d37e3acb25873f4bc71eb868751888fb3cd743dabfe70c24514d885d3139e`
- answer sha256: `e7cdd5c2128824fc5c5f31440d38629713378b8684b2689a215a952ea7f39895`

## Question

We implemented the U01 liveness-only correction you authorized. Review only the
current bounded delta and return exactly one of:

- `U01_DELTA_ACCEPTED`
- `U01_DELTA_CHANGES_REQUIRED`

If changes are required, list only concrete BLOCKING/HIGH issues with exact
locators. Do not declare U01, the API, the plugin, or the product complete.

Current writable delta is limited to:

- `packages/ui-api/src/openapi/node-http-adapter.mjs` (new)
- `packages/ui-api/src/openapi/index.mjs` (one public export)

Implementation summary:

- The factory reads the canonical OpenAPI bytes once, parses that exact snapshot,
  and derives both the existing route table and a stricter public-constant
  eligibility proof from the same document hash.
- It requires exactly one eligible operation: explicit empty operation security
  and capability arrays, no path template/path-or-query parameter/request body,
  one non-bodiless 2xx response, exactly one JSON media representation, bounded
  local references, and a closed singleton response schema whose example agrees.
- Status, media, schema kind/ref, method, target, operation id, and body remain
  canonical-derived. The derived response media/schema is exact-matched to the
  existing route-table row.
- Exactly one synchronous constant body handler is bound through
  `bindServerSurface`; the same-snapshot immutable PARTIAL coverage is returned.
- Import has no effect. Factory construction creates but does not listen. The
  lifecycle is loopback-only explicit `listen/address/close`, with finite parser,
  request, header, socket, connection, and per-socket request bounds plus active
  socket cleanup.
- Dispatch requires byte-exact raw method and request target, zero body bytes, and
  no `Content-Length`, `Transfer-Encoding`, `Expect`, or `Trailer` header. Special
  HTTP events and all nonmatching/unspecified failure cases destroy the exchange
  without reaching dispatch or inventing an error wire contract.
- Success writes only the canonical-derived status, exact canonical media string,
  `Cache-Control: no-store`, exact byte length, and canonical singleton JSON body.
- Runtime server errors transition to a stored terminal failure, close/destroy the
  server surface, and remain observable through lifecycle calls.

Deliberate deviations from the prior advisory answer:

- `Content-Length: 0` is rejected, following the independent security boundary.
- The raw request target is not passed through WHATWG URL parsing or normalization.
- Unspecified failures close the exchange instead of inventing ApiProblem mappings.
- `Content-Type` uses the exact canonical media string; no noncanonical charset
  parameter is appended.

No schemas, manifests, package metadata, generated clients, N02/N03 sources, or
other packages changed. Independent contract and security re-reviews reported no
remaining BLOCKING/HIGH finding in this bounded scope.

## Pro answer (advisory; verify locally)

`U01_DELTA_CHANGES_REQUIRED`

* **HIGH — failed loopback verification can leave a bound listener active.** The adapter promises a loopback-only lifecycle with active socket cleanup.  After Node has emitted `listening`, `address()` correctly rejects a malformed or non-loopback bound address, but the catch path calls `settleReject()` only. That function marks the lifecycle failed and rejects the promise without invoking `server.close()` or `destroyTrackedSockets()`.  The required teardown already exists in `recordServerFailure()`.  Since `listening` is emitted after the server is bound, this can leave a listener accepting connections after `listen()` has reported failure. ([Node.js][1])

  **Exact minimal correction:** in `packages/ui-api/src/openapi/node-http-adapter.mjs`, within the `onListening` catch at lines 1215–1217, invoke the existing terminal teardown path—equivalent to `recordServerFailure(error)`—before `settleReject(error)`. The correction must close the server and destroy tracked sockets whenever post-bind address validation fails; no schema, OpenAPI, manifest, package, or other-file change is required.

[1]: https://nodejs.org/api/net.html "https://nodejs.org/api/net.html"
