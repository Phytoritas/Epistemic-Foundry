# Codex and Claude Code adapter contract

## 1. Provider-neutral authority

Codex and Claude Code are execution surfaces. They do not own:

- FORGE phase;
- canonical artifacts;
- policy or consent;
- capability leases;
- evidence promotion;
- final replay state.

Each adapter translates the same `RoleSpec`, `NodeContract`, `ContextCapsule`, and `ResultEnvelope`.

## 2. Codex adapter

Uses:

- `.codex-plugin/plugin.json`;
- progressive skills;
- plugin-bundled hooks where supported and trusted;
- optional local MCP;
- built-in subagent types with inline compiled role prompts;
- worktrees for isolated parallel writes;
- `PLUGIN_ROOT` and `PLUGIN_DATA`;
- payload-resident `efoundry` dispatcher.

Rules:

- feature probe rather than assume hook support;
- hosted tool paths not observed by local hooks are listed as coverage gaps;
- custom scientific role semantics are compiled into built-in host roles;
- subagent results require schema validation and expected-count reconciliation;
- managed enterprise hooks can strengthen policy, but the plugin still retains kernel gates;
- plugin hook approval status is visible in health.

## 3. Claude Code adapter

Uses:

- repository `CLAUDE.md`;
- `.claude/agents/*.md` custom role definitions;
- `.claude/skills/`;
- hooks only as host guardrails;
- worktree isolation for parallel writes;
- CLI/MCP bridge to Foundry Kernel.

Rules:

- custom agent metadata is generated from canonical RoleSpec;
- main session remains Parent Architect/Research Governor;
- parallel writers require disjoint scopes and frozen contracts;
- every returned result is a ResultEnvelope, not a prose completion claim.

## 4. Model routing

Route by failure cost and empirical evaluation:

```text
high blast radius, causal or security decision → frontier + independent review
bounded extraction/classification             → economy/balanced
semantic synthesis and adversarial critique   → balanced/frontier
deterministic transform/gate                  → code, not model
validation execution                          → sandbox/tool, not model narration
```

Routing inputs:

- task class and node contract;
- observed model accuracy for that task;
- blast radius;
- error diversity from other roles;
- latency and hard/soft budget;
- privacy/provider constraints;
- current availability and rate limits.

Different vendors are not presumed independent. Independence is measured through eval disagreement and shared retrieval/prompt lineage.

## 5. Result envelope

Every adapter returns:

```text
node_id
role_spec_id
resolved_provider/model/version
input artifact and context hashes
output artifact IDs
claims with Evidence IDs
uncertainty and abstentions
tool/action receipts
checks
partial/missing status
token/latency accounting
adapter version
```

Free text may be attached as presentation but is not the contract.

## 6. Fallback

- unavailable preferred model → use only policy-approved fallback and record it;
- unavailable host subagent → serial execution with same RoleSpec;
- unavailable worktree → no parallel writes;
- unavailable MCP → CLI or local library adapter;
- unavailable hooks → explicit invocation and health DEGRADED;
- no compliant fallback → BLOCKED, not silent substitution.
