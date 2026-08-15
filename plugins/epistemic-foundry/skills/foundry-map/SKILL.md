---
name: foundry-map
description: "Inspect workspace mapping contracts and report current map-tool availability. Use for dependency and blast-radius mapping."
metadata:
  architecture-version: "4.0.0"
  status: "ACTIVE"
---

# Workspace Cartographer

For an authorized mapping implementation, freeze the input snapshot, inventory typed entities, extract edges, and compute structural metrics, query personalization, and blast radius separately. Preserve algorithms, exclusions, and coverage in the result.

## Current availability

`foundry.map.query` is advertised but currently returns `UNAVAILABLE`. Local stdio principal, workspace, and capability binding is not ratified, and environment paths do not grant `mcp.read.map`.

Do not claim that a `WorkspaceMapSnapshot` was produced, and do not synthesize one by hand. Use `foundry.status` or `foundry.health` to report the unavailable state until an authorized binding is implemented and installed.

When the binding contract is later authorized, require the produced snapshot to state its included and excluded scopes. Treat it as a read model, not a registered artifact or receipt.
