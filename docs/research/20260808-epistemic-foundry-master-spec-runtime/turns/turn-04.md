# Pro turn 04

- session: `pro-epistemic-081741-8c0f87`
- recorded: 2026-08-08T08:30:55Z
- prompt sha256: `a7b746d8115e09600f6543deebec01d0d318acacf19f9f5f740cc148dc10b3d1`
- answer sha256: `bcb4fc2a946ddcdaca65d2d8d07df6c20acaad6c3a09b35bd6dbedf54cb0f20f`

## Question

# Epistemic Foundry: select the next authority-safe implementation slice

Continue the same MASTER_SPEC runtime implementation thread in the exact
conversation. Codex has now completed the bounded N02 correction you requested,
and an independent contract review found that the proposed N03 reachability
slice has no current owner.

## Current authoritative delta

- `packages/role-router/src/adapters/execute-bounded-adapter-invocation.mjs`
  now binds fresh `STARTED` attempts to the requested attempt ID, intent ID, and
  start timestamp; rejects start before authorization; rejects finish before
  attempt start before sealing the EffectReceipt; and uses an exact RFC 3339
  comparator that preserves arbitrary fractional-second precision and timezone
  offsets.
- The bounded executor version is `4.0.0-n02.bounded.2`.
- An author-independent focused review reports no remaining BLOCKING/HIGH issue
  in that chronology correction.
- No provider transport, live provider route, schema, workflow, manifest,
  package-metadata, or product-status claim was added.

## N03 authority finding

The current manifest gives N03 write ownership only of
`packages/foundry-kernel/src/scheduler/**`. The scheduler public API has plan,
state, lease, attempt, and replay operations but no executor registry or dispatch
port. N02's public bounded executor is in `role-router`, while `role-router`
already depends on `foundry-kernel`. A reverse `foundry-kernel -> role-router`
import would create a package cycle and violate ADR-032. The architecture names
L4 as the composition layer but no current work package owns the missing binding.

Independent contract result:

`SPEC_GAP: N03-EXECUTION-REACHABILITY-OWNER`

Smallest missing authority is an owner for the execution-binding contract and
its L4 composition root. If N03 retains scheduler ownership, authority must name
an N03-owned provider-neutral injected execution port and an L4 root that binds
it to N02; `foundry-kernel -> role-router` remains prohibited.

## Decision requested

Inspect the current work-package ordering and choose the earliest
dependency-ready implementation package that Codex can advance without
inventing this missing shared contract or editing outside its exact write scope.

Return exactly one of:

1. `NEXT_PACKAGE`: package ID, why its dependencies are ready, exact authoritative
   locators, exclusively owned paths, smallest behavior to implement, and
   stop conditions; or
2. `PRODUCT_OWNER_DECISION_REQUIRED`: if every next meaningful package depends
   on the unresolved N03 execution owner, give the single smallest decision the
   user must make. Do not silently grant that authority yourself.

Do not approve product completion. Do not propose schema, workflow, manifest,
package-metadata, private cross-package import, live-provider, fallback, or
status-promotion changes unless the current authority already assigns them to
the selected package.

## Pro answer (advisory; verify locally)

# `PRODUCT_OWNER_DECISION_REQUIRED`

No authority-safe `NEXT_PACKAGE` can be selected from the supplied record for this runtime thread.

The corrected N02 slice may be accepted **only as the bounded primitive** already authorized: injected validation/effect/artifact ports, deterministic `local_scripted` execution, immutable receipts, and idempotent replay. Scheduler reachability and live-provider execution remain explicitly outside that slice.  

N03 cannot legally consume N02 because:

* N03 owns only `packages/foundry-kernel/src/scheduler/**`.
* No scheduler execution port or executor registry exists.
* `role-router` already depends on `foundry-kernel`.
* A reverse `foundry-kernel → role-router` dependency would create a package cycle.
* No current work package owns the L4 composition root that must depend on both packages.

Private subpath import is not an acceptable workaround. Node package `exports` defines the public package interface and excludes undeclared entry points. ([Node.js][1])

## Single smallest product-owner decision

The product owner must issue **one shared-contract decision** named:

```text
N03-EXECUTION-REACHABILITY-OWNER
```

That decision must contain all of the following, and is incomplete until the **exact L4 work-package ID and exact write path** are named.

```text
1. N03 remains the scheduler owner.

   Existing source scope:
   packages/foundry-kernel/src/scheduler/**

2. N03 is authorized to define one provider-neutral injected execution port.

   Conceptual contract:

   NodeExecutionPort.execute({
     spawnDescriptor,
     nodeInvocation,
     actionIntent,
     attemptId,
     effectReceiptId
   }) -> Promise<ResultEnvelope>

3. The scheduler must receive this port by dependency injection.

   foundry-kernel must not:
   - import role-router;
   - inspect local_scripted fixtures;
   - construct provider adapters;
   - resolve live providers;
   - implement provider fallback;
   - import another package's private source path.

4. A separate L4 composition owner must be named.

   The decision must specify:
   - exact existing or newly authorized work-package ID;
   - exact repository-relative write scope;
   - dependencies on both N02 and N03;
   - authority to consume only the public APIs of
     @epistemic-foundry/foundry-kernel and
     @epistemic-foundry/role-router.

5. The L4 composition root may bind only:

   N03 injected NodeExecutionPort
       ↓
   N02 public createBoundedAdapterExecutor
       ↓
   branded local_scripted adapter
       ↓
   existing injected E02/E03, validator, artifact,
   clock, cancellation, and replay ports.

6. The first route is restricted to local_scripted.

   The binding must not authorize:
   - OpenAI, Anthropic, Codex, or Claude transport;
   - credentials or network access;
   - streaming;
   - tool calls;
   - provider fallback;
   - Shinka dispatch;
   - provider status promotion;
   - transport-kernel completion claims.

7. Receipt-bound success remains mandatory.

   A scheduler node may become terminal-success only when the returned
   ResultEnvelope is bound to:
   - one complete output artifact;
   - its ArtifactReceipt;
   - its resolving EffectReceipt;
   - the original NodeInvocation and SpawnDescriptor;
   - complete node accounting.

8. Fail-closed behavior is mandatory.

   missing execution port
   → BLOCKED / no dispatch

   unsupported or non-local route
   → DEGRADED or UNSUPPORTED / no fallback

   unresolved existing attempt
   → reconciliation required / no second execution

   missing output artifact or ArtifactReceipt
   → terminal success prohibited

   missing or unresolved EffectReceipt
   → terminal success prohibited

   partial node accounting
   → workflow completion prohibited

9. Only the minimal development-manifest authority amendment needed to
   assign the L4 owner and exact write scope is authorized.

   No schema, canonical workflow, package metadata, provider policy,
   product-status, or live-transport change is included.
```

## Why no other package should be selected

The supplied packet does not include evidence that another package is both:

1. dependency-ready in the current live manifest, and
2. capable of materially advancing this runtime path without consuming the missing execution-binding contract.

Naming a different package would therefore rely on unseen ordering information. Advancing N03 directly would invent a shared port and composition owner that current authority does not define.

## Required state until the decision exists

```yaml
N02_bounded_execution:
  status: ACCEPTED_WITHIN_BOUNDED_SCOPE

N03_execution_reachability:
  status: SPEC_GAP
  blocker: N03-EXECUTION-REACHABILITY-OWNER

providers:
  status: DEGRADED

live_provider_transport:
  status: UNIMPLEMENTED

completion_ready: false
product_completion: false
```

## Stop condition after the decision

Even after the product-owner decision is issued, implementation must stop again if the designated L4 package cannot bind N03 to N02 using **public package APIs only** within the newly approved exact write scope. No private import, reverse dependency, schema change, live-provider route, or fallback may be introduced to bypass that failure.

[1]: https://nodejs.org/api/packages.html "Modules: Packages | Node.js v26.7.0 Documentation"
