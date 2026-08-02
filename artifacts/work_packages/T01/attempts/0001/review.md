# T01-0001 contract review

## Outcome

`T01-0001` is `SPEC_GAP` (`T01-SG001`). No T01 product implementation was started, the package is not `PASS`, and `completion_ready` remains `false`.

## Blocking finding

The canonical UX document fixes nine MCP read tool names and four planning tool names. It also states that domain JSON Schema is canonical, OpenAPI is canonical for HTTP, MCP tool schemas must reference those canonical definitions, and read models distinguish `READY`, `EMPTY_CONFIRMED`, `DEGRADED`, and `UNAVAILABLE`. The T01 manifest limits product writes to `packages/plugin-host/src/mcp/read/**` and requires canonical schemas plus side-effect-free reads.

Those rules do not define a usable per-tool wire contract. None of the thirteen names appears in machine-readable schemas, OpenAPI, workflows, manifests, packages, or tests as a descriptor or binding. Fourteen existing domain schemas are plausible outputs, but several tools have multiple plausible meanings: status may be a session projection or aggregate status; health may combine plugin health and host capability; atlas, replay, map, and frame need query and envelope semantics; and planning tools may be pure calculations or creation of durable canonical plan artifacts.

No authority freezes the MCP protocol/version, descriptor shape, schema-reference resolution base, result framing, errors, principal/workspace/capability scoping, confidentiality concealment, or shared handler interface. The contract also does not say whether a read may emit audit telemetry or receipts while remaining side-effect free. The provider-neutral transport package contains only its scaffold package manifest, and the T01 adapter directory does not yet exist.

Implementing local JSON literals, selecting plausible schemas, or inventing handlers and planning effects inside T01 would violate EF4-I22 and exceed the exact adapter write scope. The required `mcp_schema_test` and `read_side_effect_test` therefore lack canonical test oracles and were not fabricated.

## Dependency and classification review

E04, G04, and S04 all pass, so this is not a dependency blocker. No external credential, service, licensed source, host capability, or tool is unavailable, so the correct outcome is not `BLOCKED`. No defined T01 implementation was attempted or failed, so the correct outcome is not `FAIL`. The missing cross-surface wire and authority decisions require `SPEC_GAP`.

## Required product-owner decision

The resolving decision must freeze an exact thirteen-row input/output/envelope/handler/side-effect/capability matrix; the MCP protocol, descriptor, reference, framing, and error contracts; planning persistence and receipt semantics; authorization and workspace rules; the permitted audit effects of reads; the provider-neutral shared handler owner; and the minimum exact central contract, adapter, fixture, test, documentation, and evidence write scopes.

## RAH and assurance limitation

RAH remains read-only and blocked at generation `000081-843d5565` by the pre-existing J02 tokenizer-lock and S04 traceability failures. Its generation manifest and all six payload hashes match, but T01 appended no evidence and created no generation.

The product owner prohibited Fleet and subagents. This is a procedurally separate primary-session contract review, not actor-independent certification.
