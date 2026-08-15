# Pro turn 03

- session: `pro-epistemic-072305-28fe35`
- recorded: 2026-08-08T07:36:24Z
- prompt sha256: `fa54266bca294ad3aafa08e98eafc559a314a3d36b86c3643c4d16b10411517a`
- answer sha256: `3e9abbbda2f1c8f631bcfefec4a901e268db3963952e92920460eac37b784ea7`

## Question

# Epistemic Foundry N02 bounded execution: implementation delta and next move

Continue the same architecture thread. Inspect the four attached current source
files, not just this summary.

## What Codex implemented

The change stays inside the exact N02 write scope:

- packages/role-router/src/adapters/adapter-execution-errors.mjs
- packages/role-router/src/adapters/local-scripted-adapter.mjs
- packages/role-router/src/adapters/execute-bounded-adapter-invocation.mjs
- packages/role-router/src/adapters/index.mjs

It adds:

- a branded local_scripted adapter containing only immutable plain-data
  fixtures keyed by canonical NodeInvocation.input_hash;
- an immutable SHA-256 digest of the complete canonical fixture set;
- a provider-neutral bounded executor whose schema validation, E03
  authorization, E02 sealing/coordination, artifact persistence, replay
  resolution, clock, and cancellation behavior are injected ports;
- exact binding from fixture-set digest to the SpawnDescriptor model version,
  from invocation input hash to ActionIntent arguments, and from
  ActionIntent/authorization/schema hash to ArtifactReceipt, EffectReceipt,
  and ResultEnvelope;
- canonical idempotent replay through an injected resolver without a second
  adapter call;
- tri-state NOT_STARTED | UNKNOWN | CONFIRMED tracking for effectful port
  calls so fulfilled-but-malformed or rejected-after-dispatch results do not
  become definite negatives;
- an empty provider-telemetry metrics object and a fixed
  local_scripted_complete terminal reason.

The executor requires a kernel-owned authorization result binding the exact
intent and intent hash, invocation grants, required capabilities, approval
records, policy bundle, lease token, deadline, input hash, expected schema
hash, SpawnDescriptor hash, and model-routing receipt before E02 registration
or attempt start.

For replay, the fresh authorization only authorizes access. The resolver must
return the original stored authorization, and the kernel authorization port
validates it separately. Stored artifact metadata and the immutable
ResultEnvelope remain bound to that original authorization ID/hash.

## Independent review already applied

An author-independent contract reviewer found and Codex corrected:

- request-level fixture selection outside idempotency binding;
- treating E02 EXISTING_RESULT as failure;
- missing fixture-set identity;
- validator substitution of scripted output;
- cancellation/deadline gaps before artifact persistence;
- false definite state after uncertain async port calls;
- unconfirmed register/record return values;
- incomplete EffectReceipt field binding;
- caller-controlled policy IDs;
- missing E03 authorization binding;
- missing stored schema-hash binding on replay;
- rewriting replay provenance with a fresh authorization.

The reviewer's final focused result was: no remaining BLOCKING/HIGH defect.

## Explicitly not implemented or claimed

This is not a provider transport and does not change product status. The
following remain unimplemented:

- packages/transport-kernel source and public transport API;
- live OpenAI, Anthropic, Codex, or Claude execution;
- signed NodeInvocation;
- typed provider/model/usage/tool-call telemetry;
- credentials, streaming, provider retry/rate-limit behavior, or fallback;
- workflow/scheduler reachability for this primitive;
- the eight remaining retrieval lanes;
- Shinka backend pin, qualification, or execution;
- plugin completeness, production readiness, or completion_ready=true.

No schema, workflow, manifest, package metadata, CLI status, test, report, or
RAH lifecycle file was changed for this slice.

## Decision needed

1. Review the attached source against your prior Option A decision. Report only
   a real BLOCKING/HIGH contract or authority defect, with an exact minimal
   correction.
2. If no such defect remains, treat this only as acceptance of the bounded N02
   slice, not product completion.
3. Then choose the single next dependency-layer-sized runtime slice that Codex
   should implement from the live repository. If that next move requires an
   absent shared contract or write-scope owner, return one exact SPEC_GAP
   product-owner decision instead of inventing it.

Do not ask Codex to weaken canonical gates, change tests, claim live-provider
execution, or repair the inconsistent RAH completion state by narrative.

## Pro answer (advisory; verify locally)

# 결정

**현재 N02 슬라이스에는 HIGH급 계약 결함 1건이 남아 있습니다. 따라서 아직 bounded N02 슬라이스를 수락하지 말고, 다음 단일 구현 작업을 `N02-H01 execution chronology binding correction`으로 제한하십시오.**

세 첨부 번들은 바이트 단위로 동일했으며, 아래 판정은 요약문이 아니라 번들에 포함된 네 소스 파일을 직접 대조한 결과입니다.

## HIGH — fresh success가 replay 시 거부될 수 있음

현재 구현은 `canonical idempotent replay`와 원래 authorization provenance의 보존을 핵심 동작으로 선언합니다.  그러나 fresh-execution 경로와 replay 경로의 시간 순서 검증이 서로 다릅니다.

`normalizeAttemptResult()`는 `beginAttempt()`이 반환한 `attempt.started_at`이 유효한 RFC 3339 문자열인지만 확인합니다. 호출자가 전달한 `startedAt`과 같은지, 또는 authorization 시각보다 빠르지 않은지는 확인하지 않습니다. 

실제 호출 순서는 다음입니다.

```text
authorizationCheckedAt = clock()
authorizeExecution(...)
...
startedAt = clock()
beginAttempt({ started_at: startedAt })
normalizeAttemptResult(...)
```

그런데 `normalizeAttemptResult()`에는 `startedAt`이나 `authorizationCheckedAt`이 전달되지 않습니다. 따라서 잘못된 clock port 또는 잘못된 coordinator return이 authorization 이전의 `attempt.started_at`을 반환해도 fresh 실행은 계속될 수 있습니다. 

반면 replay 경로는 저장된 authorization이 original attempt보다 늦으면 명시적으로 `STORED_AUTHORIZATION_CHRONOLOGY_INVALID`를 발생시킵니다. 

따라서 현재 코드는 이 상태를 허용할 수 있습니다.

```text
fresh execution
→ artifact persisted
→ EffectReceipt recorded
→ ResultEnvelope success returned

same invocation replay
→ stored authorization chronology rejected
→ replay fails
```

이는 단순한 진단 품질 문제가 아니라 **동일한 receipt-bound 결과가 fresh path에서는 성공하고 strict replay에서는 거부되는 재현성 결함**입니다.

또한 `finishedAt` 역시 `attempt.started_at`보다 빠르지 않은지 확인하지 않은 채 성공 EffectReceipt에 들어갑니다.  RFC 3339 적합성은 timestamp 표현 형식을 규정할 뿐, authorization → attempt start → finish라는 사건 순서를 자동으로 보장하지 않으므로 그 순서는 실행 계약에서 별도로 강제해야 합니다. ([RFC 편집자][1])

# 정확한 최소 교정

수정 파일은 **하나로 제한**합니다.

```text
packages/role-router/src/adapters/
  execute-bounded-adapter-invocation.mjs
```

다음 네 가지를 구현하십시오.

### 1. Authorization 이후 clock regression 차단

`startedAt = readClock(clock)` 직후, `beginAttempt()` 호출 전에:

```js
Date.parse(startedAt) >= Date.parse(authorizationCheckedAt)
```

를 강제합니다.

위반 시:

```text
code: EXECUTION_CHRONOLOGY_INVALID
stage: before_attempt
adapterInvoked: false
attemptState: NOT_STARTED
```

로 fail-closed하십시오.

### 2. 새 attempt의 반환 timestamp를 요청값에 결박

함수를 다음 의미로 변경합니다.

```js
normalizeAttemptResult(
  candidate,
  attemptId,
  intentId,
  requestedStartedAt,
)
```

`execute_permitted === true`와 `status === "STARTED"`인 경우에는 다음을 모두 요구합니다.

```text
attempt.attempt_id === requested attemptId
attempt.intent_id === intentId
attempt.started_at === requestedStartedAt
```

`EXISTING_RESULT`와 `EXISTING_ATTEMPT`에는 새 요청의 `requestedStartedAt`을 강요하지 마십시오. 그 경로는 original stored attempt timestamp를 보존해야 합니다.

### 3. Finish chronology 차단

`finishedAt = readClock(clock)` 직후 `sealEffectReceipt()` 전에:

```js
Date.parse(finishedAt) >= Date.parse(attempt.started_at)
```

를 강제합니다.

이 검사는 output artifact가 이미 기록된 뒤 발생하므로, 위반 시 기존 tri-state가 다음을 정직하게 표현해야 합니다.

```text
attemptState: CONFIRMED
artifactState: CONFIRMED
receiptState: NOT_STARTED
reconciliationRequired: true
```

기존 `AdapterExecutionError`의 상태 계산은 이 경우를 이미 reconciliation 대상으로 처리할 수 있으므로, 상태 어휘나 schema를 변경할 필요는 없습니다. 

### 4. 구현 버전만 증가

```text
BOUNDED_ADAPTER_EXECUTOR_VERSION
4.0.0-n02.bounded.1
→ 4.0.0-n02.bounded.2
```

다음은 변경하지 않습니다.

```text
local_scripted adapter version
schemas/**
workflows/**
manifests/**
package metadata
transport-kernel/**
foundry-kernel/**
provider status
RAH lifecycle state
```

# N02 판정

현재 판정:

```yaml
slice: N02 bounded local_scripted execution
implementation_scope: compliant
authority_boundary: compliant
live_provider_claim: false
blocking_or_high_defects:
  - N02-H01 execution chronology binding
acceptance: NOT_YET
product_completion: false
completion_ready: false
```

위 교정이 적용되고 정적 재검토에서 fresh path와 replay path의 chronology가 일치하면, 그때 다음 범위로만 N02를 수락할 수 있습니다.

```text
SpawnDescriptor + NodeInvocation
→ injected authorization/effect/artifact ports
→ in-process local_scripted execution
→ receipt-bound ResultEnvelope
→ exact replay without a second adapter call
```

그 수락은 다음을 의미하지 않습니다.

* provider transport 완성
* live OpenAI·Anthropic·Codex·Claude 실행
* signed `NodeInvocation`
* typed provider·model·usage·tool-call telemetry
* scheduler/workflow reachability
* retrieval lane 확장
* Shinka backend
* plugin 완성
* production readiness

이 항목들은 번들에서도 명시적으로 미구현 상태입니다. 

# 그 다음 dependency-layer runtime slice

N02-H01을 교정한 뒤의 **다음 후보는 `N03 single-node local_scripted scheduler reachability`**입니다.

최소 동작은 다음 하나뿐이어야 합니다.

```text
scheduler receives one ready NodeInvocation
→ resolves its already-compiled SpawnDescriptor
→ resolves explicit adapter kind local_scripted
→ obtains existing public E02/E03/artifact ports
→ calls N02 createBoundedAdapterExecutor
→ accepts only a receipt-bound ResultEnvelope
→ commits one terminal node result
```

N03에서 아직 구현하지 말아야 할 것:

```text
fan-out
multi-node concurrency
live provider routing
provider fallback
generic retry policy
transport-kernel
workflow-wide completion
partial fan-in
dynamic adapter discovery
Shinka dispatch
```

실패 시에는 다음을 강제해야 합니다.

```text
unknown executor             → fail closed
non-local provider route     → DEGRADED / unsupported
missing injected port        → BLOCKED
unresolved existing attempt  → reconciliation required
missing EffectReceipt        → terminal success 금지
missing output artifact      → terminal success 금지
partial node accounting      → workflow completion 금지
```

## N03 편집 전 단 하나의 로컬 검사

번들에는 N03의 최신 manifest entry와 scheduler 소스가 포함되어 있지 않으므로, 정확한 파일 범위를 추측해서는 안 됩니다. 다음 정적 검사를 먼저 수행하십시오.

```bash
rg -n \
  '"N03"|write_scope|depends_on|executor_status|executor_registry|dispatch|NodeInvocation|ResultEnvelope|createBoundedAdapterExecutor|local_scripted' \
  manifests/development_manifest.yaml \
  manifests/acceptance_matrix.yaml \
  packages/*/package.json \
  packages/*/src \
  workflows
```

판정은 두 갈래입니다.

### 기존 N03 권한과 public composition point가 존재함

N02-H01 교정 후 N03의 exact write scope 안에서 single-node reachability를 구현합니다. N02는 공개 barrel을 통해서만 소비하십시오. Node의 package `exports`는 선언된 entry point를 public interface로 한정하므로, 다른 package의 private source subpath로 우회해서는 안 됩니다. ([Node.js][2])

### N03가 executor registry 또는 composition root를 소유하지 않음

그때는 코드를 발명하지 말고 정확히 다음 `SPEC_GAP` 하나만 올리십시오.

```text
SPEC_GAP: N03-EXECUTION-REACHABILITY-OWNER

Smallest product-owner decision required:

- designate the existing N03 package as owner of the exact scheduler
  executor-registry and single-node dispatch paths;
- authorize only the local_scripted route from an already-compiled
  SpawnDescriptor + NodeInvocation to the public N02 bounded executor;
- authorize injection of existing E02/E03, validation, artifact, clock,
  cancellation, and replay ports;
- prohibit canonical schema changes, workflow semantic changes, private
  cross-package imports, live-provider routing, fallback, and provider
  status promotion.
```

## 최종 지시

```text
1. N02-H01 chronology correction만 먼저 구현
2. N02를 다시 정적으로 검토
3. 결함이 해소된 경우에만 bounded N02 slice를 제한적으로 수락
4. 위 rg 검사로 N03 ownership과 composition point 확인
5. 권한이 있으면 single-node local_scripted reachability 구현
6. 권한이 없으면 N03-EXECUTION-REACHABILITY-OWNER SPEC_GAP으로 중단
```

현재 단계에서 N02 완료나 제품 완료를 승인하지 않습니다. 독립 검토에서 기존 여러 결함이 교정되었다는 증거는 유효하지만, 최종 focused review가 놓친 chronology 불일치가 남아 있으므로 이를 먼저 닫아야 합니다. 

[1]: https://www.rfc-editor.org/info/rfc3339/?utm_source=chatgpt.com "RFC 3339: Date and Time on the Internet: Timestamps"
[2]: https://nodejs.org/api/packages.html?utm_source=chatgpt.com "Modules: Packages | Node.js v26.5.1 Documentation"
