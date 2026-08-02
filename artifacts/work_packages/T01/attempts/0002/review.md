# T01-0002 primary-session separate adversarial review

- Reviewer: primary session in a separate adversarial pass under the
  product-owner instruction forbidding subagents and Fleet;
  actor_independence=false is recorded, not hidden.
- Wire-literal authority (EF4-I22): the thirteen tool names, classes,
  capabilities, and schema bindings exist once, in
  contracts/mcp/t01/tool-catalog.yaml.  The Python registry loads it,
  the plugin-host descriptor table is a generated projection guarded
  by a Python parity test, and Node tests resolve every reference to
  the exact canonical files.
- Frozen decision fidelity: protocol 2026-07-28; stateless STDIO and
  Streamable HTTP POST /mcp with no SSE fallback and no session
  state; nine PURE_READ plus four DURABLE_PLAN_ARTIFACT tools; exact
  shared result/error envelopes self-validated on every call.
- Authorization order is enforced and tested: protocol, input schema,
  authentication, workspace isolation (EF4-I19), capability, then
  confidentiality concealment where denied visibility and absence are
  indistinguishable NOT_FOUND answers.
- Read honesty (EF4-I23): provider failure maps to UNAVAILABLE and
  can never be rendered EMPTY_CONFIRMED; dishonest provider states
  (READY without data, EMPTY_CONFIRMED with data or reason) fail
  closed as INTERNAL.
- Read purity: nine read tools produce zero writes, receipts, or
  provider-state drift, including on every failure path; envelope
  mutation cannot reach the provider.
- Planning integrity: compilation is delegated to domain-owned ports
  (no duplicated business logic); artifacts must validate against the
  exact canonical schema before persisting; receipts address the
  stored canonical bytes; idempotent replay returns the original
  receipt and key reuse with a new request conflicts; nothing
  executes.
- Finding (resolved): the initial descriptor helper required a full
  service; it now derives from the catalog alone so generation and
  parity checking share one projection.
- Finding (resolved): the repository wire-literal guard correctly
  failed until the three new contract modules were registered as
  declaring sites, and the invariant-label guard rejected a
  duplicated EF4 citation in a runtime message.  The registry
  addition is the exact edit authorized by
  HD-EF4-T01-0002-SCOPE-20260731-001; no guard token, threshold, or
  assertion changed, and the citation moved out of the message.
- Residual limitations: the Node-to-Python process bridge and the
  dispatcher `mcp serve` route are T03 scope, so the registered
  .mcp.json entry fails closed at startup; no live read-model,
  artifact-store, or compiler binding to production stores is
  claimed; this review is not external actor-independent
  certification.
