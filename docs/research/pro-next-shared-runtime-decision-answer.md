# SPEC_GAP — first establish a provider-neutral workflow execution composition root

The first shared decision should create:

> **`X00 — Provider-neutral workflow execution host and executor-binding composition root`**

`X00` should be the sole L4 owner that binds a compiled workflow node to an exact executable implementation and coordinates that invocation with the existing scheduler, checkpoint, effect, capability, and reconciliation authorities.

This is the highest-leverage decision because every one of the 23 canonical workflows and 350 nodes ultimately crosses this boundary. The other four gaps affect a promotion branch, candidate qualification, process-host behavior, or context accounting; none turns an otherwise compiled scheduler plan into an executable run. 

The current authority does not assign this composition to anyone. N02 owns role/spawn adapters, N03 owns scheduling, and N04 is an independent integration gate with only test and evidence-artifact write scope. W01 owns compilation, while W02 owns checkpoint, pause, resume, and cancellation. Assigning production composition to N04 would compromise the separation between implementation and its integration review; assigning it to W01, W02, or N03 would make an authority-layer package import concrete adapters. X01 and X02 are already provider-specific.   

Under the declared authority order, that unassigned cross-package responsibility remains `SPEC_GAP` until the product owner creates and bounds `X00`. 

## Ownership boundary

The decision should freeze this division:

| Owner               | Retained authority                                                                                                                |
| ------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| **W01**             | NodeContract validation, compile-time executor resolution protocol, immutable binding projection, and compiled hash               |
| **N02**             | RoleSpec compilation and Codex/Claude or other role-executor adapters                                                             |
| **N03**             | Readiness, scheduler leases, resource claims, retries, fencing, attempt transitions, and reconciliation state                     |
| **W02**             | Pause, cancellation, checkpoint, and resume state                                                                                 |
| **E02/E03/E04**     | ActionIntent/Attempt/EffectReceipt, capability/approval authority, and strict/semantic replay                                     |
| **Domain packages** | The scientific or business callable named by each `executor_ref`                                                                  |
| **X00**             | Closed executor registry, exact binding resolution, scheduler-to-executor invocation, cross-runtime transport, and result handoff |
| **X01/X02**         | Provider-specific host integration over X00                                                                                       |

X00 must never own canonical state, mint scheduler or capability leases, approve policy, synthesize receipts, alter a scientific result, or reinterpret a NodeContract. That preserves Kernel authority, receipt-bound completion, provider neutrality, exact fan-in, and replayability.  

## Smallest authority and write-scope changes

### `MASTER_SPEC.md`

Add one package before the provider-specific X packages and change the package total from 156 to 157:

```text
X00 — Provider-neutral workflow execution host and executor-binding composition root
Dependencies: W02, N02, N03, E04
Risk: critical
Review: required
```

No existing package is removed or reassigned.

### `manifests/development_manifest.yaml`

Add exactly:

```yaml
- id: X00
  phase: P23-X
  phase_title: Cross-provider adapters
  title: Provider-neutral workflow execution host and executor-binding composition root
  depends_on:
    - W02
    - N02
    - N03
    - E04
  write_scope:
    - packages/plugin-host/src/workflow-execution/**
    - src/epistemic_foundry/application/workflow_execution/**
    - artifacts/work_packages/X00/**
```

Its exit criteria should require:

```text
every executable node resolves to exactly one sealed binding
compiled and runtime binding identities agree
NodeInvocation enters unchanged
only a validated ResultEnvelope can resolve execution
possible post-dispatch effects enter reconciliation
provider replacement cannot change canonical semantics
```

### Dependency edges

Using `X -> Y` to mean “X depends on Y”:

```text
X00 -> W02,N02,N03,E04

W04 -> W02,W03,X00
X01 -> G04,N04,T04,W04,X00
X02 -> X01,X00
```

The `W04 -> X00` edge makes real executor dispatch, interrupted invocation, binding drift, and reconciliation part of the replay gate rather than leaving W04 to validate only an in-memory scheduler.

These additions are acyclic against the current manifest graph. No lower scientific or domain package should depend upward on X00; those packages expose owned callables, while X00 registers and invokes them.

### Package exports

B01 should make only the narrow APIs needed by X00 public:

```text
@epistemic-foundry/foundry-kernel/scheduler
@epistemic-foundry/foundry-kernel/workflow-runtime
@epistemic-foundry/role-router/executor
@epistemic-foundry/plugin-host/workflow-execution
```

No wildcard or internal `src/` export is appropriate. The current Foundry Kernel export map is empty, so a production composition package cannot presently consume even the implemented authority primitives. 

This requires no B01 write-scope expansion; package boundary and export files are already B01 concerns.

## Minimal provider-neutral interface

### 1. Compile-time resolver

W01 should accept an injected resolver rather than importing X00:

```text
resolve_executor(NodeContract) -> ExecutorBinding | UNRESOLVED
```

`ExecutorBinding` should contain only:

```text
node_id
executor_type
executor_ref
input_schema_ref
output_schema_ref
implementation_id
implementation_version
implementation_sha256
```

W01, not the resolver, computes each `binding_sha256`. It then produces:

```text
executor_bindings
executor_binding_set_sha256
```

The rows must be sorted by `node_id`, deeply immutable, and included in `compiled_sha256`. `executor_ref` and all other strings retain their exact bytes; no import-path normalization, aliasing, case conversion, or fallback substitution is allowed.

The current NodeContract already distinguishes a live `executor_bound` reference, an explicitly unbuilt `executor_unbound` reference, and an unverified absence of status. It specifically says that a bound reference is checked by an executor-resolution gate.  The compiler presently checks only executor vocabulary and reference syntax before preserving the reference in the scheduler plan; it does not resolve an implementation. 

Adding the binding projection changes `compiled_sha256` for newly compiled plans by design. Historical compiled artifacts and hashes remain unchanged and cannot be upgraded in place.

### 2. Runtime host

The public runtime operation should be:

```text
execute_node(
    compiled_artifact,
    node_id,
    scheduler_lease,
    node_invocation
) -> ExecutionOutcome
```

X00 must:

1. verify the compiled and scheduler-plan hashes;
2. select the binding already sealed for `node_id`;
3. re-resolve the installed implementation and require exact binding identity;
4. verify the active N03 scheduler lease and W02 cancellation state;
5. invoke the executor with the canonical `NodeInvocation`;
6. validate the returned canonical `ResultEnvelope`;
7. hand the validated outcome and real receipt IDs back to N03/E02.

The scheduler already preserves `executor_type` and `executor_ref` and owns lease, retry, success, failure, and reconciliation transitions, but it contains no executor-dispatch operation. 

### 3. Runtime outcome

`ExecutionOutcome` should be an X00 control type with exactly three states:

```text
RESOLVED
  result_envelope: ResultEnvelope

NOT_DISPATCHED
  failure_code: closed host failure code

OUTCOME_UNKNOWN
  reconciliation_key:
    hash(compiled_sha256, binding_sha256,
         run_id, node_id, attempt, input_hash)
```

Only `RESOLVED` carries a `ResultEnvelope`. The two other states are not receipts, scientific evidence, or proof of success.

Cross-process transport sends the existing canonical `NodeInvocation` and receives the existing canonical `ResultEnvelope`; therefore this decision does **not** require a 128th canonical schema. The binding set is a W01 hash-covered compiled projection, not a new public scientific artifact. This also avoids duplicating transport literals contrary to EF4-I22. 

## Failure semantics

The decision must require:

* `executor_status: executor_unbound` → compile fails as it does now.
* Missing `executor_status` → run admission is `BLOCKED` with `EXECUTOR_STATUS_UNVERIFIED`.
* `executor_bound` but no exact registered implementation → `FAIL`, because a claimed live binding is false.
* Implementation ID, version, or hash differs from the compiled binding → `FAIL/EXECUTOR_BINDING_DRIFT`; a fresh compilation is required.
* Required host, credential, interpreter, or external service unavailable before dispatch → `BLOCKED`; no alternative executor is selected silently.
* Failure proven before executor dispatch → `NOT_DISPATCHED`; normal retry policy may apply.
* Failure after dispatch may have occurred → `OUTCOME_UNKNOWN`; the attempt enters `RECONCILING` and cannot be blindly retried.
* Invalid `ResultEnvelope`, mismatched run/node/attempt/input identity, missing output artifacts, or absent required EffectReceipts → `FAIL`; the scheduler cannot record success.
* A cancellation request is not proof that a child stopped. Until termination or effect state is resolved, the attempt remains reconciling.

No executor may change its `executor_ref`, provider, model, prompt, implementation hash, or adapter version under an existing compiled hash.

## First three direct consumers

1. **W04** can become a real workflow replay gate: execute a bound node, replay its attempt history, detect binding drift, and reconcile an interrupted dispatch.

2. **X01** can compose Codex role execution and ordinary deterministic/Python workflow entrypoints through one host instead of owning a parallel scheduler or effect lifecycle.

3. **X02** can use the same compiled binding and invocation contract for Claude Code, making cross-provider parity an execution comparison rather than a comparison of disconnected adapter fixtures. The current X01/X02 scopes are explicitly provider-specific, which is why neither should own the shared host. 

Once these consumers exist, I01’s bounded interview, O02’s retrieval lanes, V03’s validation runner, and other domain-owned callables can be implemented and registered against the same boundary. That statement is an implementation opportunity, not evidence that those references currently resolve.

## Deferred shared gaps

**A05 G12/G13 applicability** should remain deferred because it is a narrow canonical payload/schema decision for promotion. Resolving it does not make the promotion workflow—or any other workflow—dispatchable without the execution host. It should later travel through the same NodeInvocation-to-executor boundary rather than adding an A05-specific invocation wrapper.

**S05 BudgetEnvelope migration** should follow X00 because the canonical budget authority already belongs to N03/Y01 through EF4-I28. Migrating candidate qualification first would risk creating a second candidate-only execution ABI. After X00, S05 can consume one canonical BudgetEnvelope at the common admission boundary and K06 can requalify downstream consumers once. 

**G02 process-tree termination** should remain deferred because G02 is explicitly a payload dispatcher with no domain logic. The first decision must establish the abstract cancellation and `OUTCOME_UNKNOWN` boundary; G02/T04 can then qualify concrete Windows and Unix child-tree termination without turning OS behavior into scheduler authority. 

**J02 tokenizer packaging** should remain deferred because its exact-tokenizer requirement is confined to context/reference budgeting. The manifest already fixes the token-counting acceptance requirement, while the current Python project keeps `tiktoken` outside ordinary runtime dependencies. Packaging that capability is necessary for J02, but it does not unlock node scheduling, dispatch, receipts, or workflow replay.  

The smallest human decision is therefore: **create X00 with the ownership, edges, and closed interface above, while leaving all canonical scientific and authority semantics in their existing packages.**
