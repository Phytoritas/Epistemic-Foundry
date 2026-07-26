# Codex adapter

The production adapter packages the Foundry skills and optional MCP in a native plugin. Canonical roles are compiled into built-in Codex subagent types because host role registration may be narrower than the Foundry role vocabulary. The adapter injects only the selected RoleSpec, ContextCapsule and schemas, then validates ResultEnvelope and expected count.

The adapter must feature-probe plugin hooks and list unobserved hosted-tool paths. A missing hook selects DEGRADED mode; it does not disable kernel gates.
