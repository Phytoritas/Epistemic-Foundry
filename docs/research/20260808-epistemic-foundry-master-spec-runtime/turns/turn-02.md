# Pro turn 02

- session: `pro-epistemic-051228-392e98`
- recorded: 2026-08-08T05:19:24Z
- prompt sha256: `81316ca968091151057fbeba30c70368c5e85f346c3e952c00f78b074a8715d9`
- answer sha256: `9dcf60d90157eca0ce819383297652be7df26edff1975a0212fbb33e59ac25a7`

## Question

# Local adjudication needed before implementing the proposed N02 executor

Your first recommendation was `N02 provider-neutral executable boundary + local_scripted adapter`. Local inspection confirmed part of it, but found contract and ownership conflicts that may change the decision.

## Confirmed

- N02 depends on N01 and its write scope is exactly `packages/role-router/src/adapters/**`.
- N01 transitively depends on E04, so E02/E03 effect semantics are upstream.
- No callable currently accepts `SpawnDescriptor + NodeInvocation` and returns a receipt-bound `ResultEnvelope`.
- The E02 coordinator exposes `sealActionIntent`, `sealEffectReceipt`, `registerIntent`, `beginAttempt`, `recordReceipt`, and reconciliation behavior.

## Conflicting local authority

1. `packages/boundary-policy.json` declares `transport-kernel` as a foundation component and `role-router` as a service component, with `sourceImportPolicy: public-package-api-only`.
2. `packages/transport-kernel/package.json` describes provider-neutral transport, retry, timeout, redaction, and receipt primitives, but the package contains no source files and no development-manifest package has write scope over it.
3. `@epistemic-foundry/foundry-kernel` has no root `exports`; importing its effect coordinator by relative source path from role-router would violate the boundary policy.
4. The provider adapter document requires a signed `NodeInvocation`, but the strict `node-invocation.schema.json` has no signature field and forbids additional properties.
5. The provider adapter document says every adapter returns resolved provider/model/version, usage, tool calls, and adapter version. The strict `result-envelope.schema.json` has no typed fields for these; only an open primitive `metrics` map.
6. `model-routing-receipt.schema.json` does not directly bind provider/runtime/fallback approval metadata required by the existing role-router descriptor.
7. An independent local contract scan therefore judged shared live provider transport to be `SPEC_GAP`, while agreeing that a purely injected, in-process scripted boundary could fit N02 if it does not claim to close transport-kernel or live-provider capability.

## Decision needed

Choose exactly one:

### A — bounded N02 orchestration

Proceed inside N02 only, but require all cross-layer behavior as injected public ports (`contractValidator`, `effectCoordinator`, `effectSealer`, `artifactWriter`, clock/cancellation). Add only an in-process `local_scripted` adapter and orchestration. It must not import another component's source, claim signed invocation, claim live provider transport, or move `providers` out of `DEGRADED`.

### B — SPEC_GAP first

Do not write provider execution code. Define the smallest missing product-owner decision: owner/write scope for `transport-kernel`, public package APIs, invocation signature, provider telemetry/result contract, and first transport type. Identify the minimum existing package or manifest amendment that must own it.

Tests/builds/servers/gates are not authorized in this turn. We can implement code and perform static source inspection only.

Return the selected option, precise rationale against the authority order, exact allowed files, the smallest behavior, and the one stop condition that would invalidate your choice. Do not approve completion.

## Pro answer (advisory; verify locally)

## 결정: **A — bounded N02 orchestration**

`N02` 안에서만 **주입식(injected) 포트 기반 실행 오케스트레이션과 `local_scripted` 어댑터**를 구현하십시오.

다만 이것은 **provider transport 구현이 아닙니다.** 다음 상태를 그대로 유지해야 합니다.

```text
transport-kernel: specified_only / unimplemented
providers: DEGRADED
live provider execution: unimplemented
signed NodeInvocation: unimplemented
typed provider telemetry: unimplemented
```

`B — SPEC_GAP first`는 폐기하는 것이 아니라 **실제 live-provider transport를 시작하기 전의 필수 후속 결정**으로 유보합니다.

---

# 1. 권한 순서에 따른 판단

## 1.1 `MASTER_SPEC.md`

이번 선택은 다음 상위 원칙을 만족합니다.

* Foundry Kernel이 canonical state와 권한을 소유한다.
* provider와 adapter는 교체 가능한 executor일 뿐이다.
* 외부 또는 실행 효과는 receipt 없이 완료될 수 없다.
* capability가 없으면 명시적으로 `DEGRADED` 또는 `BLOCKED`여야 한다.
* replay 가능한 입력·효과·결과 연결을 보존해야 한다.

로컬에서 앞서 식별된 적용 지점은 다음입니다.

```text
Part II — Product Constitution
- EF4-I01 Kernel authority
- EF4-I13 Receipt-bound completion
- EF4-I15 Capability negotiation
- EF4-I34 Provider neutrality
- EF4-I39 Replayability

Part III
- §5 Module map
- §6 Authority planes
- A–Z/E02: effect coordination
- A–Z/E03: capability lease/fencing
- A–Z/N02: role compilation and spawn adapters
```

이번 구현은 provider SDK나 adapter에 authority를 넘기지 않으므로 이 원칙을 위반하지 않습니다.

## 1.2 Development manifest

확인된 권한은 다음 하나입니다.

```text
N02 write_scope:
  packages/role-router/src/adapters/**
```

Option A는 이 디렉터리 안에서 끝낼 수 있습니다.

반면 live transport를 구현하려면 적어도 다음이 필요하므로 현재 N02가 소유할 수 없습니다.

```text
packages/transport-kernel/**
packages/foundry-kernel/package.json exports
canonical schema 변경
provider credential/policy surface
```

따라서 **live transport를 N02에서 구현하는 것은 금지**하지만, 외부 계층을 주입 포트로 받는 bounded executor는 허용됩니다.

## 1.3 Boundary policy

`packages/boundary-policy.json`의:

```text
sourceImportPolicy: public-package-api-only
```

를 그대로 적용합니다.

`@epistemic-foundry/foundry-kernel`에 public export가 없으므로 다음과 같은 우회는 금지합니다.

```js
import ... from "../../foundry-kernel/src/effects/...";
```

Node의 package `"exports"`는 패키지가 공개하는 entry point를 정의하고, 선언되지 않은 subpath를 public interface 밖에 두는 장치입니다. 따라서 private source 경로 import를 편의상 사용하는 것은 package boundary를 우회하는 것입니다. ([Node.js][1])

해법은 import가 아니라 **dependency injection**입니다.

## 1.4 Canonical schemas

다음 schema를 수정하지 않고 현재 의미 그대로 소비합니다.

```text
schemas/node-invocation.schema.json
schemas/result-envelope.schema.json
schemas/model-routing-receipt.schema.json
schemas/action-intent.schema.json
schemas/effect-receipt.schema.json
schemas/artifact-receipt.schema.json
```

특히:

* `NodeInvocation`에 signature가 없으므로 “signed invocation”이라고 표현하지 않습니다.
* `ResultEnvelope`에 typed provider telemetry가 없으므로 provider/model/version, usage, tool call 내역을 억지로 삽입하지 않습니다.
* `ModelRoutingReceipt`가 live runtime/fallback approval을 완전히 결박하지 않으므로 `local_scripted`를 live provider route로 표현하지 않습니다.

엄격한 object schema에서 `additionalProperties: false`이면 정의되지 않은 필드는 유효하지 않으므로, signature나 provider telemetry를 임의 필드로 밀어 넣는 것은 허용되지 않습니다. ([JSON Schema][2])

## 1.5 Workflow

이번 슬라이스에서는 canonical workflow를 수정하지 않습니다.

```text
workflows/**
```

는 전부 read-only입니다.

N02가 만든 callable은 이후 N03/N04 또는 기존 LLM-node 실행 경로가 소비할 수 있는 **하위 실행 primitive**일 뿐입니다. 이번 구현만으로 어떤 workflow도 executable 또는 complete로 승격하지 않습니다.

---

# 2. 정확한 허용 파일

다음 파일만 생성 또는 수정하도록 제한합니다.

```text
packages/role-router/src/adapters/execute-bounded-adapter-invocation.mjs
packages/role-router/src/adapters/local-scripted-adapter.mjs
packages/role-router/src/adapters/adapter-execution-errors.mjs
```

그리고 해당 디렉터리에 이미 존재하는 public adapter barrel이 있을 때만 그 파일을 수정합니다.

예:

```text
packages/role-router/src/adapters/index.mjs
```

실제 barrel 파일명이 다르면 기존 파일을 사용하고 새 barrel을 중복 생성하지 마십시오.

다음은 수정하지 않습니다.

```text
packages/role-router/package.json
packages/foundry-kernel/**
packages/transport-kernel/**
schemas/**
workflows/**
manifests/**
src/epistemic_foundry/providers/**
tests/**
```

이번 턴에는 테스트·빌드·서버·repository gate 실행 권한도 없습니다.

---

# 3. 구현할 최소 행동

## 3.1 실행기 생성

다음 의미의 factory를 구현합니다.

```js
createBoundedAdapterExecutor({
  contractValidator,
  effectCoordinator,
  effectSealer,
  artifactWriter,
  clock,
  cancellation,
})
```

모든 cross-layer 기능은 인자로 주입합니다.

직접 import하면 안 되는 것:

```text
foundry-kernel effect implementation
transport-kernel implementation
ledger implementation
artifact-store implementation
provider credential resolver
scheduler implementation
```

## 3.2 실행 입력

실행 함수는 최소한 다음을 받습니다.

```text
SpawnDescriptor
NodeInvocation
local_scripted adapter
scripted response source
```

여기서 `scripted response source`는 호출자가 주입한 deterministic fixture 또는 response function입니다.

N02 내부에 연구 결론이나 provider 응답 예시를 하드코딩하지 않습니다.

## 3.3 `local_scripted` 제약

`local_scripted`는 다음 속성으로 고정합니다.

```text
adapter kind: local_scripted
execution: in-process
network access: forbidden
child process: forbidden
tool calls: forbidden
credential access: forbidden
provider fallback: forbidden
canonical state direct write: forbidden
scientific evidence status: none
live provider status: false
```

이 어댑터의 목적은 오직 다음 경계를 실제 코드로 닫는 것입니다.

```text
compiled invocation
→ injected execution boundary
→ deterministic structured output
→ artifact persistence
→ effect/artifact receipts
→ ResultEnvelope
```

## 3.4 실행 순서

오케스트레이터는 다음 순서를 바꾸지 않습니다.

```text
1. 필수 injected port 존재 확인
2. cancellation 사전 확인
3. SpawnDescriptor 구조·무결성 확인
4. NodeInvocation을 기존 strict schema로 검증
5. 입력 hash와 expected output contract 확인
6. ActionIntent 생성
7. effectSealer로 ActionIntent 봉인
8. effectCoordinator.registerIntent
9. effectCoordinator.beginAttempt
10. local_scripted adapter를 정확히 한 번 호출
11. adapter output을 기존 expected output schema로 검증
12. artifactWriter로 immutable output artifact 기록
13. ArtifactReceipt 확보
14. EffectReceipt 생성·봉인
15. effectCoordinator.recordReceipt
16. 기존 result-envelope schema가 허용하는 필드만 사용해 ResultEnvelope 반환
```

`ResultEnvelope`에는 로컬 schema가 이미 정의한 artifact/receipt 결박만 사용합니다.

다음을 `metrics`에 밀어 넣어 typed contract가 생긴 것처럼 가장하지 마십시오.

```text
resolved provider
resolved model
provider version
tool-call transcript
usage accounting
fallback approval
invocation signature
```

---

# 4. Fail-closed 동작

다음 중 하나라도 발생하면 adapter를 호출하지 않습니다.

```text
필수 injected port 누락
NodeInvocation schema invalid
SpawnDescriptor invalid
cancellation already requested
unknown adapter kind
local_scripted가 network/tool/credential capability 요구
ActionIntent seal 실패
intent registration 실패
attempt 시작 실패
expected output schema 확인 불가
```

이 경우:

```text
adapter_call_count = 0
output_artifact = none
success claim = forbidden
```

adapter 호출 후 다음 문제가 발생하면 성공으로 반환하지 않습니다.

```text
scripted response 생성 실패
response schema invalid
artifact write 실패
ArtifactReceipt 누락
EffectReceipt seal 실패
EffectReceipt 기록 실패
```

특히 다음 규칙을 강제합니다.

```text
ResultEnvelope success
requires
output artifact + ArtifactReceipt + EffectReceipt
```

receipt가 하나라도 없으면 “부분 성공”이나 “synthetic success”로 숨기지 않습니다.

재시도·reconciliation은 E02가 이미 제공하는 공개 주입 포트의 의미만 사용합니다. N02가 독자적인 retry semantics를 만들지 않습니다.

---

# 5. Provenance와 authority 경계

이번 슬라이스에서 기록 가능한 provenance는 **기존 계약으로 표현 가능한 범위**뿐입니다.

최소 결박:

```text
NodeInvocation identity/hash
SpawnDescriptor identity/hash
ActionIntent identity
effect attempt identity
output artifact identity/hash
ArtifactReceipt identity
EffectReceipt identity
ResultEnvelope identity
```

어댑터 ID나 버전을 기존 ActionIntent/EffectReceipt 계약에서 표현할 수 있는 필드가 이미 있다면 사용합니다.

그 필드가 없다면:

* 새 필드를 발명하지 않습니다.
* `metrics`를 pseudo-schema로 사용하지 않습니다.
* live-provider provenance가 완성됐다고 주장하지 않습니다.

adapter와 N02가 가질 수 없는 권한:

```text
PolicyBundle 변경
capability 자체 발급
RunSpec 변경
HumanDecision 생성
Evidence 승격
Parliament 판정
Passport promotion
holdout 접근
provider fallback 승인
completion 판정
```

provider-neutral runtime의 canonical state와 판정 권한은 특정 SDK가 아니라 Foundry Kernel이 소유해야 한다는 기존 설계 원칙도 그대로 유지됩니다. 

---

# 6. 이번 슬라이스 이후에도 명시적으로 미구현인 것

다음은 계속 미구현으로 남깁니다.

## Transport kernel

```text
packages/transport-kernel source
public transport API
retry policy
timeout normalization
redaction
streaming
network framing
live effect reconciliation
```

## Live providers

```text
OpenAI adapter
Anthropic adapter
Codex adapter
Claude adapter
credentials
rate-limit handling
usage accounting
tool calls
streaming
provider fallback
cross-provider parity
```

## Canonical contracts

```text
signed NodeInvocation
typed provider execution receipt
typed provider/model/version telemetry
typed token/usage report
tool-call result contract
fallback approval contract
```

## 제품 상태

```text
providers: DEGRADED
transport-kernel: specified_only
plugin complete: false
workflow complete: false
completion_ready: false
production_ready: false
```

## Shinka

```text
backend execution
revision/package digest
qualification
dispatch
```

도 계속 fail-closed 상태를 유지합니다.

---

# 7. 단 하나의 중단 조건

다음 조건이 확인되면 **Option A는 즉시 무효**이며 코드를 작성하지 말고 `SPEC_GAP`으로 전환하십시오.

> **bounded executor를 기존 N02 public surface와 기존 canonical schemas만으로 표현할 수 없어서, private cross-package source import, `packages/transport-kernel/**` 구현, package export 변경, canonical schema 변경 중 하나라도 필요해지는 경우.**

이 경우 필요한 최소 제품 소유자 결정은 다음입니다.

```text
- transport-kernel implementation owner
- exact write scope
- public effect/transport package exports
- invocation signature contract
- typed provider telemetry/result contract
- 최초 허용 transport type
```

---

# 8. 편집 전 마지막 정적 검사

다음 한 번의 inspection만 먼저 수행하십시오.

```bash
rg -n \
  '"exports"|export .*adapter|compileRoleSpawnDescriptor|verifySpawnDescriptorIntegrity|sealActionIntent|sealEffectReceipt|registerIntent|beginAttempt|recordReceipt' \
  packages/role-router/package.json \
  packages/role-router/src/adapters \
  packages/foundry-kernel/package.json \
  packages/foundry-kernel/src
```

판정:

* 기존 N02 public barrel과 주입 가능한 E02 facade가 확인됨
  → Option A 구현 진행

* private source import나 package/schema 변경 없이는 연결 불가
  → 위 단일 중단 조건에 따라 `SPEC_GAP`

제품 결정과 검증 가능한 exit condition을 구현 전에 고정하고, 불명확한 권한을 구현자가 임의로 메우지 않는 것이 맞습니다. 

**최종 선택은 A입니다.** 이번 목표는 `local_scripted`를 통해 N02의 실행 오케스트레이션 경계를 닫는 것이며, `transport-kernel` 또는 live provider가 구현됐다고 주장하는 것이 아닙니다.

[1]: https://nodejs.org/api/packages.html "Modules: Packages | Node.js v26.7.0 Documentation"
[2]: https://json-schema.org/understanding-json-schema/reference/object "JSON Schema - object"
