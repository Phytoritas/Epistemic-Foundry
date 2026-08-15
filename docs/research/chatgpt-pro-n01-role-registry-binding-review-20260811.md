SPEC_GAP

`createRoleSpec` is **not itself incorrect**. It remains a provider-neutral, closed constructor and validator for an already complete RoleSpec. Rejecting dotted or colon-delimited capability aliases is correct at that boundary. Its limitation is that it proves RoleSpec structural validity, **not provenance from `role_registry.yaml`**.

A deterministic registry-entry compiler is not locally authorized. The two authorities currently disagree in ways that cannot be reduced to syntax:

* The six registry capabilities have no literal overlap with the RoleSpec vocabulary. Even the five apparent punctuation substitutions require an explicit cross-contract mapping; `search.read` has several materially different possible projections.
* The registry omits numerous required RoleSpec fields. N01 cannot choose defaults, accept caller-authored overlays, or reinterpret `forbidden`, `codex_agent_type`, and `default_timeout_seconds` as different RoleSpec fields without creating product meaning.
* A partial mapping would be especially unsafe: it would make five capabilities appear canonical while leaving `search.read` dependent on package-local judgment.

The required shared decision is:

```text
N01-ROLE-REGISTRY-TO-ROLESPEC-BINDING
```

It must freeze:

1. whether `role_registry.yaml` becomes the complete RoleSpec source or a separate canonical RoleSpec profile supplies the missing fields;
2. one total capability mapping, including an explicit disposition for `search.read`;
3. the authoritative source and exact mapping for every missing or differently named RoleSpec field;
4. registry/profile version and hash binding in compiled RoleSpecs;
5. write ownership for the registry or profile contract, with N01 assigned only the deterministic compiler implementation under `packages/role-router/src/contracts/**`.

Missing or inconsistent shared semantics must remain `SPEC_GAP` under the frozen authority order. 

**Smallest safe change now:** keep `createRoleSpec` and its closed capability vocabulary unchanged; do not add a registry compiler or alias table. Any newly exposed registry-compilation boundary must fail closed with a typed `ROLE_REGISTRY_BINDING_UNRESOLVED` result identifying the ambiguous capabilities and unsourced fields. N02 requires no change.
