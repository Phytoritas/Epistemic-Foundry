# Provider adapter contract

## Principle

Codex, Claude Code, and future providers execute NodeContracts. They do not own canonical scheduling, policy, state, or adjudication.

## Required adapter behavior

- accept a signed NodeInvocation,
- resolve a pinned model identifier,
- enforce capability and read/write scopes,
- assemble context from ContextAssemblyManifest,
- delimit untrusted source content,
- request schema-constrained output,
- capture usage, latency, tool calls, errors, and model identifier,
- return ResultEnvelope and artifacts,
- never commit canonical state directly,
- support cancellation and deadline,
- expose provider limitations explicitly.

## Equivalence

Provider parity means contract conformance, not identical prose. Strict replay pins all available inputs and expects deterministic reducers to match. Semantic replay compares typed decisions and records model drift.

## Project harnesses

`.codex/agents` and `.claude/agents` support development review only. Production agent execution is compiled from provider-neutral workflow YAML.
