# Pro turn 01

- session: `pro-epistemic-045511-e25c0a`
- recorded: 2026-08-08T05:06:43Z
- prompt sha256: `2f32c3c96e19198ea3b06ad53f1d99c343de4b6a53a0c555e363fd5ccfcf26de`
- answer sha256: `eb3ae38dbb78b77fa9dd3e93fa22492fdc3e70aab0d0dec0a610249fddb11a42`

## Question

# Epistemic Foundry: choose the next real implementation slice

## Objective

Continue implementing the missing parts of Epistemic Foundry v4 from `MASTER_SPEC.md`. Pick one dependency-layer-sized slice that materially advances the real runtime, not another blueprint-only completion claim.

## Current verified facts

- `MASTER_SPEC.md` and `README.md` still label the product `SPEC_BUNDLE` / `REFERENCE_BLUEPRINT`; a working plugin and production readiness are not claimed.
- The repository already has sealed reports for all 156 A-Z work packages. Those reports prove their bounded package contracts, but they do not prove the complete runtime described by the master specification.
- `efoundry status` currently reports a partial implementation. `providers` and `shinka_adapter` are the only entries under `specified_only`, with truthful `DEGRADED` status.
- The X05 report explicitly excludes runtime execution or backend dispatch of any provider or external search backend.
- Retrieval is implemented only for three of eleven canonical lanes (`LEXICAL`, `CITATION_GRAPH`, `RELATION_GRAPH`); the other eight return explicit `UNSEARCHED` sentinels.
- The Shinka path has no reachable backend and no implementation-time revision/package digest. It must remain fail-closed unless the required external pin and qualification inputs exist.
- A prior RAH goal reached `done` for the reference-blueprint package DAG, but its current lifecycle is inconsistent after later integrity work: completion readiness is false and review state is stale/pending. Do not treat that old marker as proof that the user's broader runtime objective is finished.
- No test, build, server, benchmark, or repository gate run is authorized in this turn. Static source inspection and implementation are allowed.

## Decision needed

Select the single best next implementation slice. Consider, but do not assume, these possibilities:

1. a provider-neutral executable transport boundary with one safe local/mock-capable adapter and immutable effect receipts;
2. the next canonical retrieval lane whose dependencies are already present;
3. a non-backend Shinka adapter prerequisite that can be implemented without inventing the missing pin;
4. a necessary lifecycle/contract repair that must precede any feature work.

Apply the authority order `MASTER_SPEC.md` → development manifest → acceptance matrix → product invariants → schemas/workflows. If the necessary shared contract is absent, return `SPEC_GAP` and identify the smallest product-owner decision needed instead of inventing it.

## Required answer shape

Give one recommended next move with:

- the existing work package(s) and dependency layer it belongs to, or an explicit `SPEC_GAP` if no package authorizes it;
- the exact master-spec sections, schemas, workflows, invariants, and existing source files that govern it;
- the smallest coherent behavior to implement now and the files likely to change;
- fail-closed behavior, receipt/provenance obligations, and authority boundaries;
- what must remain explicitly unimplemented after this slice;
- the single next local inspection Codex should perform before editing.

Do not claim access to unseen local files or approve completion. This is an architecture decision for Codex to validate locally.

## Pro answer (advisory; verify locally)

## 결정

**다음 구현 슬라이스는 `provider-neutral executable transport boundary`로 선택합니다.**

새 패키지를 만들거나 `SPEC_GAP`으로 돌릴 필요는 없습니다. 업로드된 저장소 스냅샷 기준으로는 기존 **N02 — Codex/Claude role compilation and spawn adapters**의 다음 correction/extension attempt가 이 작업을 합법적으로 소유할 수 있습니다.

```text
권장 패키지: N02
계층: P13-N — Nodes, agents and graph execution
형태: 기존 sealed PASS 이력은 보존하고 next-unused N02 attempt로 확장
목표: compiled SpawnDescriptor를 실제로 한 번 실행하여
      receipt-bound ResultEnvelope로 되돌리는 최소 transport slice
```

이 슬라이스가 최선인 이유는 현재 가장 큰 공백이 “계약이 없음”이 아니라 **이미 컴파일되는 역할·노드 계약이 실제 executor 호출로 이어지지 않는 것**이기 때문입니다. Epistemic Foundry의 핵심도 모델 수를 늘리는 것이 아니라 주장–증거 계약, provenance, 독립 검증을 먼저 닫는 데 있습니다. 

남은 retrieval lane들은 각각 vector backend, 관계 방향, null 분류, moderator 추출, 외부 색인 등 선행 의존성이 없으므로 지금 선택하면 lane 이름만 구현하거나 새 의미 계약을 발명하게 됩니다. Shinka 경로 역시 immutable revision/package digest가 없으므로 계속 fail-closed여야 합니다.

---

# 1. 권한이 있는 기존 패키지와 dependency layer

## 구현 소유자

```text
N02
Codex/Claude role compilation and spawn adapters
```

N02의 기존 범위인 다음 디렉터리 안에서만 구현합니다.

```text
packages/role-router/src/adapters/**
```

새 영구 dependency를 추가할 필요는 없습니다. N02는 이미 N01을 통해 kernel·policy·capability 계약 위에 있고, 동일 저장소의 `packages/role-router/package.json`도 Foundry Kernel을 의존하므로 기존 E02 effect coordinator를 사용할 수 있습니다.

## 관련 dependency 구조

```text
E02 — ActionIntent / EffectReceipt coordination
  ↓
E03 — capability lease and fencing
  ↓
E04 — integration gate
  ↓
N01 — RoleSpec and ACL
  ↓
N02 — compile + executable provider boundary   ← 이번 슬라이스
  ↓
N03 — scheduling
  ↓
N04 — fan-in / independent integration gate
```

이번 구현은 **N03 scheduler 전체나 N04 integration을 앞당기지 않습니다.** N02에서 “하나의 invocation을 안전하게 실행할 수 있는 boundary”만 닫습니다.

---

# 2. 이 결정을 지배하는 상위 계약

Codex는 라이브 저장소에서 아래 항목의 실제 문구와 최신 revision을 다시 확인해야 합니다.

## `MASTER_SPEC.md`

### Part II — Product Constitution

* `EF4-I01 Kernel authority`
  Provider SDK나 plugin shell은 canonical state를 소유하지 않습니다.

* `EF4-I13 Receipt-bound completion`
  외부 효과는 EffectReceipt와 ArtifactReceipt 없이 완료로 인정되지 않습니다.

* `EF4-I15 Capability negotiation`
  capability가 없으면 명시적으로 `DEGRADED` 또는 `BLOCKED`여야 합니다.

* `EF4-I34 Provider neutrality`
  모델과 provider는 교체 가능한 node executor이며 canonical semantics를 변경하지 못합니다.

* `EF4-I39 Replayability`
  입력, context, model route, tools, effects와 receipts로 실행을 재구성할 수 있어야 합니다.

### Part III

* **§5 Module map**

  * Foundry Kernel
  * role router
  * provider adapter
  * Noetic Ledger

* **§6 Authority planes**

  * execution plane은 invocation을 수행할 수 있지만
  * policy·evidence·promotion authority를 획득할 수 없음

* **A–Z/E — Events, effects and capabilities**

  * 특히 `E02`

* **A–Z/N — Nodes, agents and graph execution**

  * `N01–N04`
  * 이번 직접 소유자는 `N02`

* **A–Z/X — Cross-provider adapters**

  * `X01–X04`는 이후 host별 실제 adapter와 parity qualification
  * `X05`는 이번 executable transport의 소유자가 아님

Provider SDK는 실행 어댑터로만 사용하고 RunSpec, Evidence Pack, ResultEnvelope, provenance는 자체 kernel이 소유해야 한다는 기존 설계 원칙과 정확히 일치합니다. 

## 개발 manifest와 acceptance matrix

Codex가 확인해야 할 항목:

```text
manifests/development_manifest.yaml
  N02 depends_on
  N02 write_scope
  N02 required_checks
  N02 exit_criteria

manifests/acceptance_matrix.yaml
  N02 adapter compilation
  injection resistance
  effect/receipt checks
  replay or idempotency checks
```

기존 N02 범위가 `packages/role-router/src/adapters/**`를 포함한다면 별도 제품 결정 없이 진행할 수 있습니다.

반대로 구현에 다음 중 하나가 필요하다면 그 시점에서 중단해야 합니다.

* 새 canonical schema
* workflow 의미 변경
* kernel effect semantics 변경
* N02 범위 밖 source 수정
* 새로운 provider credential 정책
* live provider를 기본값으로 선택하는 정책

그 경우에만 `SPEC_GAP`을 선언하고 필요한 exact path와 의미 한 가지만 요청합니다. 과거 C01 사례처럼 상위 계약과 파생 구현을 함께 바꿀 권한·순서가 없으면 진행하지 않는 것이 맞습니다. 

---

# 3. 적용할 canonical schemas

이번 슬라이스는 기존 schema를 수정하지 않고 소비해야 합니다.

```text
schemas/node-invocation.schema.json
schemas/node-contract.schema.json
schemas/context-assembly-manifest.schema.json
schemas/model-routing-receipt.schema.json
schemas/host-capability-report.schema.json

schemas/action-intent.schema.json
schemas/effect-receipt.schema.json
schemas/artifact-receipt.schema.json
schemas/result-envelope.schema.json
```

핵심 연결은 다음과 같습니다.

```text
NodeInvocation
+ compiled SpawnDescriptor
+ ContextAssemblyManifest
+ ModelRoutingReceipt
+ HostCapabilityReport
        ↓
ProviderExecutor
        ↓
ActionIntent
        ↓
EffectAttempt
        ↓
local_scripted adapter
        ↓
schema-validated output artifact
        ↓
ArtifactReceipt + EffectReceipt
        ↓
ResultEnvelope
```

`ResultEnvelope`만 반환하고 실제 output artifact나 receipt가 없는 구현은 허용하지 않습니다.

---

# 4. 관련 workflow

이번 슬라이스에서 canonical workflow YAML을 수정하지 않습니다.

첫 번째 후속 smoke target은 다음이 적절합니다.

```text
workflows/claim_extraction.workflow.yaml

node:
  detect_claim_candidates
```

이 노드는 다음 특성을 가져 최소 executable boundary 검증에 적합합니다.

* `executor_type: llm`
* 명시된 prompt reference
* `NodeInvocation` 입력
* schema-constrained 결과
* `llm_inference` capability
* 산출물이 아직 Evidence 승격 권한을 갖지 않는 candidate 단계

단, 이번 턴에서는 test·server·workflow 실행이 금지되어 있으므로 **연결 지점만 구현**하고 실제 smoke run은 후속 검증 attempt에 남깁니다.

`forge_research_cycle.workflow.yaml`, scheduler 또는 전체 claim-extraction DAG를 이번 슬라이스에서 수정하지 않습니다.

---

# 5. 지금 구현할 최소 coherent behavior

## 5.1 ProviderExecutor

다음과 같은 provider-neutral 실행 API를 추가합니다.

개념적 입력:

```text
SpawnDescriptor
NodeInvocation
ContextAssemblyManifest
ModelRoutingReceipt
HostCapabilityReport
ProviderAdapterRegistry
EffectCoordinator
ArtifactWriter
CancellationSignal
```

개념적 출력:

```text
ResultEnvelope
```

ProviderExecutor는 아래 순서를 강제합니다.

1. SpawnDescriptor 무결성 검증
2. NodeInvocation schema와 `expected_output_schema_hash` 검증
3. input artifact와 context manifest hash 검증
4. model route의 exact provider/model/adapter revision 확인
5. deadline과 cancellation 상태 확인
6. capability grant와 lease/fencing 확인
7. idempotency key 계산
8. `ActionIntent`를 실행 전에 봉인
9. E02 coordinator에 intent 등록
10. effect attempt 시작
11. 선택된 adapter를 정확히 한 번 호출
12. 반환값을 expected output schema로 검증
13. immutable output artifact 기록
14. ArtifactReceipt 생성
15. EffectReceipt 생성·reconcile
16. receipt IDs가 결박된 ResultEnvelope 반환

## 5.2 안전한 최초 adapter

첫 adapter는 live OpenAI·Anthropic transport가 아니라 다음이어야 합니다.

```text
adapter_id: local_scripted
transport: in_process
network: forbidden
tool_calls: forbidden
canonical_state_write: forbidden
scientific_evidence_class: none
```

이 adapter는 invocation hash 또는 명시된 fixture key에 대응하는 **사전 봉인된 structured result**만 반환합니다.

용도:

* provider boundary 자체 검증
* effect lifecycle 검증
* schema-invalid response 검증
* cancellation·deadline 검증
* retry·reconciliation 검증
* live credential 없이 scheduler 연결 준비

`local_scripted` 결과는 실제 provider 실행이나 과학적 증거로 표시해서는 안 됩니다.

최소 provenance에는 다음이 필요합니다.

```text
provider_id: local_scripted
adapter_version
fixture_artifact_id
fixture_hash
synthetic: true
live_provider: false
input_hash
context_manifest_id
routing_receipt_id
action_intent_id
effect_receipt_id
output_artifact_id
artifact_receipt_id
```

---

# 6. 변경 가능성이 높은 파일

권장 신규 파일:

```text
packages/role-router/src/adapters/provider-executor.mjs
packages/role-router/src/adapters/provider-adapter-registry.mjs
packages/role-router/src/adapters/local-scripted-adapter.mjs
packages/role-router/src/adapters/provider-execution-errors.mjs
```

기존 파일 갱신:

```text
packages/role-router/src/adapters/index.mjs
```

후속 verification attempt에서만 추가할 테스트 후보:

```text
packages/role-router/test/provider-executor.test.mjs
packages/role-router/test/local-scripted-adapter.test.mjs
packages/role-router/test/provider-effect-reconciliation.test.mjs
packages/role-router/test/provider-output-schema-gate.test.mjs
```

라이브 저장소의 실제 테스트 디렉터리 관례가 다르면 기존 convention을 따라야 하며, 중복 test tree를 만들어서는 안 됩니다.

다음은 이번 슬라이스에서 수정하지 않습니다.

```text
schemas/**
workflows/**
packages/foundry-kernel/src/effects/**
packages/foundry-kernel/src/scheduler/**
src/epistemic_foundry/providers/v4_x05/**
retrieval/**
plugin manifest
CLI
UI
```

---

# 7. Fail-closed 계약

## 호출 전 실패

다음은 adapter를 호출하지 않습니다.

```text
invalid NodeInvocation
invalid SpawnDescriptor
context hash mismatch
routing receipt mismatch
missing exact model/adapter revision
missing capability
invalid or expired lease
expired deadline
already-cancelled invocation
unknown adapter
expected schema hash mismatch
```

결과:

```text
EffectReceipt.status = NOT_EXECUTED
output artifacts = []
canonical state mutation = none
```

## 호출 후 확정 실패

예:

```text
adapter returned explicit failure
output fails schema validation
artifact persistence fails before commit
```

결과:

```text
EffectReceipt.status = FAILED
ResultEnvelope.status = FAIL
promotion/evidence eligibility = none
```

## 결과가 불확실한 실패

호출이 시작된 뒤 timeout, process termination 또는 연결 손실로 실제 효과 여부를 알 수 없는 경우:

```text
EffectReceipt.status = UNKNOWN
reconciliation_required = true
```

이 상태에서는 자동 retry를 금지합니다.

먼저 동일 idempotency key로 effect state를 reconcile해야 합니다. 같은 요청을 무작정 다시 보내면 이중 실행 가능성이 생기므로 fail-closed합니다.

## Idempotency

```text
same idempotency key + same canonical input hash
→ 기존 receipt/result 재사용

same idempotency key + different canonical input hash
→ IDEMPOTENCY_CONFLICT
```

## Authority boundary

Adapter가 할 수 없는 일:

* canonical RunSpec 변경
* policy 변경
* capability 자체 발급
* HumanDecision 생성
* Evidence 승격
* Parliament 판정
* Hypothesis Passport 승격
* hidden holdout 접근
* ResultEnvelope 성공을 EffectReceipt 없이 주장
* 다른 provider로 silent fallback

모델과 adapter는 교체 가능한 executor일 뿐 canonical 의미나 판정 권한을 소유하지 않습니다.

---

# 8. 이번 슬라이스 후에도 명시적으로 미구현인 것

다음은 계속 `specified_only`, `DEGRADED`, `UNSEARCHED` 또는 명시적 미구현 상태로 남겨야 합니다.

## Provider

* live OpenAI transport
* live Anthropic transport
* Codex/Claude credential acquisition
* streaming
* tool-call execution
* provider-specific retry/rate-limit normalization
* token·비용 계측
* live provider qualification
* cross-provider parity
* scheduler 전체 연결

## Retrieval

다음 8개 lane:

```text
SEMANTIC
MECHANISM
COUNTEREVIDENCE
NULL
BOUNDARY
METHOD
TEMPORAL
EXTERNAL_NOVELTY
```

현재 이들을 임의 placeholder 결과로 채우지 않고 계속 `UNSEARCHED`로 유지합니다.

## Shinka

* backend execution
* revision/package digest
* qualification
* provider dispatch
* promotion authority

필수 pin이 없으므로 계속 fail-closed합니다.

## 제품 전체

* working plugin 완성
* production readiness
* 전체 350-node executor binding
* 실제 PDF end-to-end 연구 검증
* 이전 RAH `done` marker의 재활성화
* `completion_ready=true`

이번 슬라이스의 성공은 오직 다음만 의미합니다.

```text
compiled role/node contract
→ one safe executable adapter call
→ immutable output artifact
→ receipt-bound ResultEnvelope
```

---

# 9. 다른 후보를 지금 선택하지 않는 이유

| 후보                        | 현재 판정                                                                   |
| ------------------------- | ----------------------------------------------------------------------- |
| 다음 retrieval lane         | 선행 index/extractor/backend가 없어 지금 구현하면 의미를 발명하게 됨                       |
| Shinka prerequisite       | immutable pin이 없고 backend도 도달 불가; fail-closed 유지                        |
| lifecycle repair          | stale 완료 표시는 바로잡아야 하지만, 현재 executable runtime을 직접 진전시키는 최우선 수직 슬라이스는 아님 |
| provider-neutral boundary | 기존 N02/E02 계약과 write scope 안에서 실제 실행 폐쇄성을 처음 만들 수 있음                    |

따라서 lifecycle 상태는 정직하게 보존하되, 이를 이유로 다시 blueprint-only 작업에 머물지는 않습니다.

---

# 10. 편집 전 Codex가 수행할 단 하나의 로컬 검사

아래 검색을 먼저 실행하십시오.

```bash
rg -n \
  "compileRoleSpawnDescriptor|verifySpawnDescriptorIntegrity|createEffectCoordinator|ResultEnvelope|NodeInvocation|executeProvider|invokeProvider" \
  packages/role-router/src/adapters \
  packages/foundry-kernel/src/effects \
  packages/foundry-kernel/src/scheduler
```

이 검사의 목적은 하나입니다.

> **이미 존재하는 callable이 `SpawnDescriptor + NodeInvocation`을 받아 receipt-bound `ResultEnvelope`를 반환하는지 확인하고, 없다면 기존 compiler와 E02 coordinator의 정확한 접점을 찾아 중복 executor를 만들지 않는 것.**

검색 결과에서 그런 callable이 이미 존재하면 새 구현을 만들지 말고 그 구현의 reachability gap을 고칩니다.

없고 N02 write scope 안에서 구현 가능하면 위 슬라이스를 진행합니다.

구현에 canonical schema 변경이나 N02 범위 밖 수정이 필수라는 사실이 확인되면 즉시 중단하고 다음 형식으로만 보고합니다.

```text
SPEC_GAP
missing decision:
  <정확히 하나의 의미 또는 exact write-scope>
evidence:
  <파일과 줄>
minimum owner:
  <기존 package 또는 product owner>
```

**최종 권고: `N02 provider-neutral executable boundary + local_scripted adapter`를 다음 실제 구현 슬라이스로 선택합니다. 이는 완료 승인이 아니라 Codex가 라이브 저장소에서 권한과 접점을 재검증한 뒤 수행할 아키텍처 결정입니다.**
