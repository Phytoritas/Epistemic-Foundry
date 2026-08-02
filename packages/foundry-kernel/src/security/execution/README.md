# Execution security boundary

`execution-policy.mjs` implements the S02 kernel-observable boundary:

- secret references are runtime-private, non-serializing opaque handles;
- handles and secret-shaped data are denied at prompt, evidence-artifact, log,
  export, and ordinary network-request boundaries;
- last-mile secret use requires both an exact egress policy match and a handle
  independently bound to that canonical origin;
- resource paths are portable relative paths, canonicalized beneath an
  existing real root, operation-scoped, and checked with a no-follow,
  same-filesystem walk; only `create` may name an absent final component, and
  every other operation requires an existing target;
- network destinations use exact canonical HTTP(S) origins and default deny;
- every authorization result is bound to an exact sandbox profile identifier.

Kernel bootstrap creates one `createExecutionSecurityBoundary()` compartment,
retains its `issuer`, and exposes only its `guard` to effect paths. Handles,
policies, and authorization decisions carry per-boundary private brands;
objects minted by another boundary or copied through JSON are rejected. Secret
handles may bind only to HTTPS origins.

The boundary rejects Proxies, accessors, coercion-bearing objects, copied
handles/policies, ambiguous Windows path forms, URL credentials, and unknown
policy modes without invoking caller code. Raw secret strings are prohibited
at their source; shape checks are defense in depth and are not represented as
a complete secret detector.

Secret-free payload inspection returns a non-authoritative `PASS` record. It
never returns an authorization decision; effect adapters accept only decisions
carrying their boundary's private brand.

This module does **not** claim to provide process, container, network-namespace,
DNS-rebinding, quota, or atomic descriptor-relative filesystem isolation.
Callers must revalidate at the effect boundary, reauthorize every redirect,
verify authorization-decision brands, and use a qualified execution adapter.
S04 owns the phase red-team gate and T04 owns sandbox/tool integration.

Required checks:

```text
node --test packages/foundry-kernel/src/security/execution/secret-exfiltration.test.mjs
node --test packages/foundry-kernel/src/security/execution/path-escape.test.mjs
```
