# N01 RoleSpec to role-registry binding review

Act as an advisory contract reviewer for Epistemic Foundry v4. Return exactly
one of `AUTHORIZED_LOCAL_REPAIR`, `SPEC_GAP`, or `NO_BLOCKER`, followed only by
decisive reasoning and the smallest safe change. Do not ask to run tests.

## Authority and scope

- N01 is `Canonical RoleSpec and evidence/tool ACLs` and solely owns
  `packages/role-router/src/contracts/**`.
- Its exit criteria require explicit mission/forbidden behavior and
  representable evidence asymmetry.
- `manifests/role_registry.yaml` is the canonical role declaration source at a
  lower authority tier than schemas/workflows but above package-local notes.
- N02 owns provider adapters; N01 must remain provider-neutral.

## Current exact mismatch

`role-spec.mjs` freezes a 24-value underscore capability vocabulary such as
`artifact_read`, `artifact_write`, `filesystem_read`, `llm_inference`, and
`sandbox_execute`. It deliberately rejects every dotted or colon-delimited
alias with `CAPABILITY_VOCABULARY_MISMATCH`.

The canonical role registry uses only these six dotted values:

```text
artifact.read
artifact.write
filesystem.read
llm.inference
sandbox.execute
search.read
```

No production registry-to-RoleSpec compiler or mapping exists. The only
`createRoleSpec` callers are tests and downstream adapters receiving an
already-created RoleSpec. `search.read` is not a one-to-one spelling alias:
the N01 vocabulary separately contains `approved_external_search`,
`fulltext_search`, `vector_search`, `graph_query`, `network_read`, and related
capabilities.

The registry entry shape also omits required RoleSpec fields including
fallback tiers, read scope, network ACL, input schema refs, budget tokens,
expected count, independence group, acceptance checks, failure policy,
max attempts, and dependency IDs. It uses field names such as `forbidden`,
`codex_agent_type`, and `default_timeout_seconds` rather than the RoleSpec
names.

## Decision requested

Decide whether N01 may locally add a deterministic registry-entry compiler or
capability mapping without changing `role_registry.yaml`, schemas, workflows,
or N02. If not, identify the exact shared owner decision needed. Do not invent
defaults, choose a meaning for `search.read`, weaken the existing closed
RoleSpec vocabulary, or silently normalize two authority vocabularies into one.

Also state whether the existing standalone `createRoleSpec` contract is itself
incorrect, or whether the missing problem is only the cross-authority
registry-to-RoleSpec composition root.
