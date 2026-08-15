# T01 MCP transport contract

Frozen by `HD-EF4-T01-SG001-20260730-001`.  The single source of MCP wire
literals is `contracts/mcp/t01/tool-catalog.yaml`; this document explains the
frozen semantics and adds no new names (EF4-I22).

## 1. Protocol and transports

- MCP protocol version: `2026-07-28`.
- Transports: stateless STDIO (one JSON-RPC 2.0 message per line) and
  stateless Streamable HTTP `POST /mcp` (one JSON-RPC message per request
  body, `content-type: application/json`).
- There is no SSE fallback, no session object, and no server-held state
  between requests.  `initialize` echoes constants only.
- Both transports call the same provider-neutral handler set
  (`src/epistemic_foundry/application/`); the plugin-host adapter
  (`packages/plugin-host/src/mcp/`) owns framing only and re-implements no
  business logic.

## 2. Tool surface

Exactly thirteen tools: nine `PURE_READ` and four `DURABLE_PLAN_ARTIFACT`
(see the catalog).  Execution-capable tools (`foundry.search.execute`,
`foundry.session.transition`, …) are outside T01 and are not exposed.

- `PURE_READ` tools consult one injected read-model port and cause no write,
  receipt, ledger event, or state drift.  Their envelopes always carry
  `receipts: []`.
- `DURABLE_PLAN_ARTIFACT` tools delegate compilation to the domain-owned
  plan-compiler port, validate the compiled artifact against the exact
  canonical schema bound in the catalog, and persist it through the
  append-only plan-artifact store under the caller's `idempotency_key`.
  Their envelopes carry exactly one `{artifact_id, receipt_id, sha256}`
  receipt.  Planning never executes retrieval, deliberation, or validation.

## 3. Envelopes

Every tool answers with the shared result envelope
(`contracts/mcp/t01/foundry-mcp-tool-result.schema.json`) or the shared error
envelope (`contracts/mcp/t01/foundry-mcp-tool-error.schema.json`).  Inside
JSON-RPC, envelopes ride in `result.structuredContent` with
`result.isError`; JSON-RPC `error` objects are reserved for protocol
failures (`-32700`, `-32600`, `-32601`, `-32602`).

Read-model states are honest (EF4-I23): `READY` requires data,
`EMPTY_CONFIRMED` is a confirmed-complete empty projection and can carry
neither data nor a degradation reason, backend failure maps to `UNAVAILABLE`
(never `EMPTY_CONFIRMED`), and partial backends map to `DEGRADED` with an
explicit `degradation_reason`.

## 4. Authorization and confidentiality ordering

The frozen order is:

```text
PROTOCOL_VALIDATION
→ INPUT_SCHEMA_VALIDATION
→ AUTHENTICATION
→ WORKSPACE_ISOLATION
→ CAPABILITY_AUTHORIZATION
→ CONFIDENTIALITY_CONCEALMENT
→ HANDLER_EXECUTION
```

Principals and capabilities come from transport metadata, never from tool
arguments.  Cross-workspace access is denied by default (EF4-I19,
`WORKSPACE_DENIED`).  For concealing tools, a resource outside the caller's
authorized scope answers the same `NOT_FOUND` as a genuinely absent
resource; existence is checked only after authorization.

After the provider returns, its read outcome is validated before any
post-provider confidentiality concealment.  Only a validated `found: false`
with `EMPTY_CONFIRMED` establishes confirmed absence and may map to
`NOT_FOUND` for a concealing tool.  A `found: false` outcome in `DEGRADED` or
`UNAVAILABLE` remains an honest result envelope and is never concealed as
absence.

## 5. Idempotency and error codes

Planning requests carry an `idempotency_key`.  Replaying the same key with
the same canonical request returns the original artifact and receipt;
reusing the key with a different request fails with
`IDEMPOTENCY_CONFLICT`.  The closed error vocabulary is defined in the
error envelope schema; only `INTERNAL` is retryable.

## 6. Host registration and pending bridge

`plugins/epistemic-foundry/.mcp.json` registers the STDIO server through the
payload-resident dispatcher (`bin/efoundry.mjs mcp serve --transport
stdio`).  The dispatcher's `mcp serve` route and the cross-process bridge
from the Node adapter to the Python handler set are T03 scope; until T03
lands, startup fails closed through the dispatcher's unknown-target
behavior, and no degraded imitation of the tool surface is offered.
