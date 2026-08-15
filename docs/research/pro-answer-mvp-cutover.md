**판정: (b)**입니다. 상위 결정 16건의 전면 비준을 중단하고, 이미 실행이 확인된 Python 표면인 `status/schemas/validate/ledger/retrieve`를 설치된 플러그인에 먼저 연결해야 합니다. 현재 제품을 막는 직접 원인은 계약 의미론이 아니라 `dist/cli.mjs` 부재, 전역 Python 설치 가정, untracked 배포물, 허위에 가까운 MCP capability 광고입니다. 16건을 먼저 닫아도 이 네 결함은 하나도 고쳐지지 않으며, 오히려 실제 설치 피드백 없이 68개 이상 패키지에 공유 계약 변경을 전파하게 됩니다. 다만 `(b)`는 “아무 결정도 하지 않는다”가 아니라, **MVP 릴리스에만 한정된 runtime source binding과 capability allowlist를 동결하고 전역 v4 결정은 유보한다**는 뜻이어야 합니다.

# Q2. 정확한 최소 절단면

## 먼저 고정할 MVP 성공 조건

MVP는 다음 여섯 사용자 행위까지만 보장하십시오.

1. 런타임 상태 확인
2. canonical schema 목록 확인
3. 파일 또는 아티팩트 검증
4. ledger 조회
5. retrieval index 생성
6. `lexical` / `citation` / `entity_variable` 레인 조회

반대로 다음은 MVP에서 명시적으로 제외합니다.

* 23개 워크플로 350개 노드 실행
* executor 합성
* G01–G13 증거 재계산
* effect terminal proof
* 11개 retrieval lane 완성
* search-completeness `PASS`
* “완전한 v4” 또는 “전 기능 operational” 주장
* public ChatGPT용 원격 MCP 배포

초기 배포 표적은 **Windows의 local/repo Codex plugin + local stdio MCP**로 제한하는 것이 최단 경로입니다. Codex의 로컬 MCP host는 stdio 서버를 지원하며, plugin manifest는 plugin root 안의 `.mcp.json`, hooks, skills 등을 상대경로로 연결하는 구조입니다. ([OpenAI Developers][1])

깨끗한 설치 테스트에서 다음이 성립하면 MVP입니다.

```text
global efoundry executable: absent
global epistemic_foundry package: absent
monorepo src/: absent
host Python interpreter: present
copied plugins/epistemic-foundry/: present
```

그 상태에서 다음이 실제 성공해야 합니다.

```powershell
node .\bin\efoundry.mjs --json status
node .\bin\efoundry.mjs --json schemas
node .\bin\efoundry.mjs --json validate ...
node .\bin\efoundry.mjs --json ledger ...
node .\bin\efoundry.mjs --json retrieve build ...
node .\bin\efoundry.mjs --json retrieve query --lane lexical ...
```

`status`는 적어도 다음을 반환해야 합니다.

```json
{
  "runtime_status": "READY",
  "canonical_schemas_loaded": 127,
  "served_retrieval_lanes": [
    "lexical",
    "citation",
    "entity_variable"
  ],
  "unserved_retrieval_lanes": [
    "... eight canonical lanes ..."
  ],
  "runtime_source_scope": "MVP_RELEASE_ONLY",
  "full_v4_operational": false
}
```

## `dist`: `dist/cli.mjs`를 새로 만들고 `bin` 계약은 유지

**`bin/efoundry.mjs`가 다른 소스를 가리키게 바꾸지 마십시오. `dist/cli.mjs`를 만들어야 합니다.**

이유는 세 가지입니다.

* 이미 존재하는 plugin-local CLI publication boundary를 유지합니다.
* 빠진 release artifact를 복구하는 것이지, 결함을 source 경로로 우회하지 않습니다.
* 향후 build/source 구조가 바뀌어도 `bin/efoundry.mjs`는 안정된 진입점으로 남습니다.

권장 구조는 다음과 같습니다.

```text
plugins/epistemic-foundry/
├─ .codex-plugin/
│  └─ plugin.json
├─ .mcp.json
├─ bin/
│  └─ efoundry.mjs
├─ hooks/
│  └─ hooks.json
├─ src/
│  ├─ cli.mjs
│  ├─ python-runtime.mjs
│  ├─ mcp-server.mjs
│  ├─ hook-runner.mjs
│  └─ tool-descriptors.json
├─ dist/
│  ├─ cli.mjs
│  ├─ python-runtime.mjs
│  ├─ mcp-server.mjs
│  ├─ hook-runner.mjs
│  └─ tool-descriptors.json
├─ runtime/
│  ├─ bootstrap.py
│  ├─ python/
│  │  ├─ epistemic_foundry/
│  │  └─ <locked third-party dependencies>
│  ├─ spec/
│  │  └─ <schemas and static resources required by the six operations>
│  └─ runtime-manifest.json
└─ scripts/
   ├─ build-python-runtime.py
   └─ build.mjs
```

MVP `dist/` allowlist는 위의 다섯 논리 아티팩트면 충분합니다. 현재 workspace-map 전용 파일들이 `foundry.map.query`만 지원한다면 MVP payload에서 제거하십시오.

`dist/cli.mjs`의 역할은 제한적이어야 합니다.

* 자신의 `import.meta.url`에서 plugin root 계산
* Python interpreter 탐지
* `runtime/bootstrap.py` 실행
* 원래 인수, stdout, stderr, exit code 전달
* `Ctrl-C`와 종료 신호 전달
* Python 부재 시 구조화된 degraded 결과 반환

여기에 schema 해석, ledger 조회, retrieval 알고리즘을 넣으면 안 됩니다.

## Python 결합 방식: 후보 (ii), 단 “interpreter만 외부 의존”

선택은 **(ii)**입니다. 다만 현재처럼 PATH의 `efoundry`를 찾는 방식이 아니라 다음 형태여야 합니다.

> 플러그인이 Python interpreter만 탐지하고, application code·dependencies·schemas·runtime resources는 plugin root 안에 번들한다.

탐지 순서는 Windows 기준으로 다음과 같이 고정하십시오.

1. `EFOUNDRY_PYTHON`에 지정된 실행 파일
2. `py -3`
3. `python`
4. `python3`

각 후보는 단순 존재 확인이 아니라 다음을 probe해야 합니다.

* 지원 Python version
* `runtime/bootstrap.py` 실행 가능성
* bundled `epistemic_foundry` import 가능성
* `status` smoke result

실제 실행은 다음 개념이어야 합니다.

```text
<detected-python> -I <plugin-root>/runtime/bootstrap.py <original args>
```

`bootstrap.py`가 직접 다음을 수행합니다.

* `<plugin-root>/runtime/python`을 `sys.path` 선두에 삽입
* `<plugin-root>/runtime/spec`을 명시적 resource root로 설정
* `epistemic_foundry` CLI main을 실행
* 사용자 site-packages 또는 monorepo 경로에 fallback하지 않음

### 왜 `(i) pip install -e .`가 아닌가

`pip install -e .`는 개발 checkout 위치를 설치된 제품의 전제조건으로 만듭니다. 또한 사용자 Python 환경을 변경하며, plugin directory만 복사된 설치에서는 성립하지 않습니다. editable install은 개발 smoke 경로로는 쓸 수 있지만 제품 계약으로 두면 안 됩니다.

### 왜 `(iii) Node 재구현`이 아닌가

Node 재구현은 이미 작동하는 schema registry, validation, ledger, FTS5 retrieval 의미론을 복제합니다. 이 순간 전역 canonicalization, schema parity, retrieval receipt parity 같은 상위 결정들이 실제 MVP blocker로 바뀝니다. 현재 가장 비싼 경로입니다.

### 중요한 추가 게이트: `PYTHONPATH=src` 성공은 relocatability 증명이 아님

현재 성공은 repository cwd와 repository resources를 암묵적으로 사용했을 가능성이 있습니다. 따라서 build 단계에서 다음 폐쇄성을 검증해야 합니다.

* runtime code는 `src/epistemic_foundry`의 tracked bytes에서만 취함
* `python/epistemic_foundry`와 섞지 않음
* 필요한 schemas, manifests, templates, registries를 `runtime/spec`에 명시적으로 복사
* third-party dependency를 hash-pinned lock에서 `runtime/python`에 설치
* clean-copy 테스트에서는 repository root를 전혀 볼 수 없게 함

`src/epistemic_foundry`를 선택하는 이유는 현재 유일하게 실행이 관찰된 root이기 때문입니다. 단, 다음 검사가 실패하면 그 root는 MVP source가 될 수 없습니다.

```powershell
git ls-files src/epistemic_foundry
git status --porcelain -- src/epistemic_foundry
```

필요한 실행 파일이 untracked라면 먼저 그 정확한 bytes를 commit해야 합니다. 검증되지 않은 `python/epistemic_foundry`로 조용히 전환해서는 안 됩니다.

`runtime/runtime-manifest.json`에는 최소한 다음을 기록하십시오.

```json
{
  "scope": "MVP_RELEASE_ONLY",
  "source_root": "src/epistemic_foundry",
  "source_commit": "<git commit>",
  "python_requirement": "<actual supported range>",
  "files": [
    {
      "path": "runtime/python/...",
      "sha256": "..."
    }
  ],
  "canonicality_claim": "NONE",
  "served_retrieval_lanes": [
    "lexical",
    "citation",
    "entity_variable"
  ]
}
```

이것은 `src/`를 전역 canonical Python root로 비준하는 문서가 아닙니다. 해당 릴리스가 어떤 bytes를 실행하는지 밝히는 release binding입니다.

## MCP: MVP에서는 정확히 6개 도구

등록할 도구는 다음 여섯 개입니다.

| MCP tool                 | 실제 backend                             | 성격           |
| ------------------------ | -------------------------------------- | ------------ |
| `foundry.status`         | Node bootstrap probe + Python `status` | 읽기           |
| `foundry.schemas.list`   | Python `schemas`                       | 읽기           |
| `foundry.validate`       | Python `validate`                      | 읽기           |
| `foundry.ledger.query`   | Python `ledger`                        | 읽기           |
| `foundry.retrieve.build` | Python `retrieve build`                | workspace 쓰기 |
| `foundry.retrieve.query` | Python `retrieve query`                | 읽기           |

OpenAI의 현재 MCP builder guidance도 도구를 실제 사용자 목표 단위로 한정하고, 그 목표에 필요한 데이터와 동작만 노출하도록 요구합니다. ([OpenAI Developers][2])

다음과 같이 정리하십시오.

* `foundry.health`는 제거하고 `foundry.status`에 합칩니다.
* `foundry.map.query`는 MVP에서 제거합니다.
* 하드코딩 `UNAVAILABLE` 10개는 등록하지 않습니다.
* 미래 도구 descriptor를 보관할 수는 있지만 `tools/list`에 나타나서는 안 됩니다.
* Python이 없거나 runtime integrity check가 실패한 degraded 상태에서는 **`foundry.status` 하나만** 등록합니다.
* `tool-descriptors.json`의 도구명 집합과 실제 handler 집합이 정확히 같지 않으면 MCP server startup을 실패시킵니다.

`UNAVAILABLE`은 tool result가 아니라 `foundry.status.capabilities` 안의 상태여야 합니다. 도구 광고는 “호출 가능한 capability”라는 약속이기 때문입니다.

### Workspace root 처리

`.mcp.json`에 특정 사용자의 workspace를 하드코딩하지 마십시오. 대신 workspace-sensitive 도구 입력에 절대경로 `workspace_root`를 요구하십시오.

예:

```text
foundry.validate:
  workspace_root: required
  path: required

foundry.ledger.query:
  workspace_root: required

foundry.retrieve.build:
  workspace_root: required
  corpus_root: required

foundry.retrieve.query:
  workspace_root: required
  lane: required
  query: required
```

이렇게 하면 MCP process의 cwd가 plugin root인지 사용자 repository인지에 의존하지 않습니다. `mcp-server.mjs`는 plugin root를 `import.meta.url`에서 계산하고, 사용자 workspace는 각 호출에서 받습니다.

`retrieve.query`는 11개 canonical lane 이름을 받을 수 있지만, 현재 세 레인 외에는 반드시 기존 `UNSEARCHED` sentinel을 그대로 반환해야 합니다. 빈 결과와 미검색을 합치면 안 됩니다.

## `dist` untracked 문제: build script와 build output을 둘 다 commit

세 선택지 중 하나가 아니라 다음 조합이 정답입니다.

> 재현 가능한 source/build script를 commit하고, 설치에 필요한 `dist/` 및 `runtime/` 결과물도 commit한다.

공식 plugin 패키징은 plugin root 안의 manifest와 bundled components를 설치 대상으로 삼습니다. manifest 경로도 plugin root 내부 상대경로여야 합니다. 따라서 별도 custom build phase가 실행될 것이라고 가정하지 않는 것이 안전합니다. ([OpenAI Developers][1])

다음은 각각 부적절합니다.

* **build output만 commit:** 재현성과 reviewability가 없음
* **build script만 commit:** 설치 직후 실행되지 않음
* **source 직접 실행:** monorepo 구조와 development dependencies에 결합
* **untracked dist 유지:** clone/release에서 기능 소실

필수 CI gate는 다음입니다.

```powershell
node plugins/epistemic-foundry/scripts/build.mjs
git diff --exit-code -- `
  plugins/epistemic-foundry/dist `
  plugins/epistemic-foundry/runtime
```

그리고 다음 출력이 비어 있으면 안 됩니다.

```powershell
git ls-files `
  plugins/epistemic-foundry/dist `
  plugins/epistemic-foundry/runtime
```

# Q3. 소유권 순환 해소

**매니페스트 밖의 별도 bootstrap authority 문서가 필요합니다.** 그 문서가 A01에 제한된 manifest custodianship을 부여해야 합니다. `development_manifest.yaml` 안에서 A01이 자기 자신에게 관리권을 부여하는 방식은 권한의 근거가 될 수 없습니다.

권위 사슬은 다음이어야 합니다.

```text
repository/product owner
    ↓
governance/development_manifest_authority.yaml
    ↓
A01 as manifest custodian
    ↓
manifests/development_manifest.yaml changes
```

권장 파일은 두 개입니다.

```text
governance/BOOTSTRAP_AUTHORITY.md
governance/development_manifest_authority.yaml
```

`development_manifest_authority.yaml`에는 최소한 다음을 둡니다.

```yaml
governed_artifact: manifests/development_manifest.yaml
grantor: product_owner
custodian: A01
authority_kind: bounded_custodianship
effective_from_commit: <commit>
self_amendment: prohibited

allowed_changes:
  - apply_approved_ownership_decision
  - correct_manifest_integrity_defect
  - update_reference_to_approved_authority

prohibited_without_product_owner_approval:
  - change_custodian
  - change_A01_scope_or_owner
  - create_or_delete_work_package
  - change_global_completion_semantics
  - grant_shared_contract_authority
  - modify_this_authority_record

approval:
  independent_approver_required: true
  author_may_not_approve: true
  decision_reference_required: true
```

그 후 `manifests/development_manifest.yaml`에는 A01을 `owner`보다 좁은 의미인 `custodian` 또는 `steward`로 표시하고 위 authority file을 참조하십시오.

최소 안전장치는 세 가지입니다.

1. **자기 수정 금지:** A01은 A01 자신의 scope, owner, custodian 권한을 단독 변경할 수 없습니다.
2. **두 열쇠 승인:** manifest 변경 작성자와 승인자가 달라야 하며, A01 권한 관련 변경은 product owner 승인이 필요합니다.
3. **기계 검증:** authority reference, 승인 record, 대상 diff class가 없으면 CI가 manifest 변경을 거부해야 합니다.

A01은 manifest를 편집하고 검증하는 관리자이지, 공유 계약을 임의로 바꾸는 헌법 제정자가 아닙니다.

# Q4. 16건 중 MVP에 실제로 필요한 것

**16건의 전면 비준이 필요한 수는 0건입니다.**
**MVP-local disposition이 필요한 것은 1건입니다:** 정식 Python 루트 문제의 제한된 하위 결정입니다.

정확히는 다음과 같이 처리하십시오.

```text
Global decision:
  canonical Python root = unresolved

MVP release binding:
  runtime bytes are staged from src/epistemic_foundry
  scope = this MVP release only
  no authority over the other 68 packages
  no deletion or deprecation of python/epistemic_foundry
  no cross-root imports
```

제시된 상위 5건의 판정은 다음과 같습니다.

| 결정                               | MVP blocker 여부 | 이유                                                      |
| -------------------------------- | -------------: | ------------------------------------------------------- |
| 정식 Python root                   |        제한적으로 예 | 실행할 exact bytes를 정해야 함. 단, 전역 canonical 비준은 불필요         |
| executor 합성 루트                   |            아니오 | MVP는 workflow node를 실행하지 않음                             |
| 전역 canonicalization profile      |            아니오 | 기존 결과를 호출할 뿐 새 cross-system canonical digest 계약을 만들지 않음 |
| A05 G01–G13 권위/재계산               |            아니오 | 증거 재계산을 하지 않음                                           |
| `NodeAttemptEffectTerminalProof` |            아니오 | effectful node attempt를 실행하지 않음                         |

나머지 11건에도 동일한 차단 규칙을 적용하십시오.

> 그 결정이 없어서 여섯 MVP operation 중 하나의 **입력, 출력 또는 실행 bytes가 결정 불가능한 경우에만** MVP blocker로 승격한다.

다음 종류의 결정은 모두 유보합니다.

* workflow execution
* promotion
* effect terminalization
* evidence recomputation
* full search completeness
* unserved retrieval lanes
* aggregate v4 completion
* 전역 소유권 재배치

새 상위 결정을 MVP에 넣으려면 “중요해 보인다”가 아니라 **clean-install acceptance test의 구체적인 실패**가 있어야 합니다. 실패 테스트와 직접 연결되지 않은 결정은 `DEFERRED_NON_BLOCKING`입니다.

# Q5. 정직성 경계

현재 상태의 정확한 표현은 다음입니다.

```text
WORK-PACKAGE CONTRACT CONFORMANCE: PASS (156/156)
INSTALLABLE RUNTIME READINESS: FAIL
MCP CAPABILITY TRUTHFULNESS: FAIL
FULL V4 OPERATIONAL READINESS: NOT READY
```

`156/156 PASS`, `SPEC_GAP=0`을 단독으로 제품 완료 신호처럼 표시해서는 안 됩니다.

## 156개 보고서를 전부 되돌리지는 않음

보고서가 실제로 다음만 증명했다면 `PASS`를 유지할 수 있습니다.

* schema 존재
* workflow 문서 존재
* 패키지 내부 invariant 충족
* 정해진 evidence artifact 생성
* 해당 패키지의 제한된 acceptance criterion 충족

반면 다음을 명시적으로 주장한 보고서는 reopen 또는 supersede해야 합니다.

* 설치된 plugin CLI가 실행 가능함
* `dist/cli.mjs`가 release payload에 존재함
* Python runtime이 설치 경로에 결합됨
* 13개 MCP tool이 실제 호출 가능함
* build output이 reproducible/tracked임
* clone 또는 release에서 제품이 operational임

기존 report가 immutable evidence라면 원본 bytes를 수정하지 말고 다음 report나 defect record로 supersede하십시오. 현재 ledger pointer만 새 상태를 가리키게 하면 됩니다.

## 축을 문서화하는 것만으로는 부족

구분은 prose가 아니라 machine-readable aggregate gate에 반영되어야 합니다. 예를 들어:

```json
{
  "spec_conformance": {
    "status": "PASS",
    "passed_work_packages": 156,
    "total_work_packages": 156
  },
  "release_artifact": {
    "status": "FAIL",
    "dist_tracked": false,
    "runtime_bundle_tracked": false
  },
  "installability": {
    "status": "FAIL",
    "clean_install_test": "NOT_PASSING"
  },
  "mcp_surface": {
    "status": "FAIL",
    "advertised_tools": 13,
    "implemented_tools": 3
  },
  "retrieval": {
    "status": "PARTIAL",
    "served_lanes": [
      "lexical",
      "citation",
      "entity_variable"
    ]
  },
  "mvp_operational_readiness": "FAIL",
  "full_v4_operational_readiness": "NOT_READY"
}
```

MVP 완료 후에는 다음까지만 올릴 수 있습니다.

```text
SPEC_CONFORMANCE=PASS
MVP_RUNTIME_READINESS=PASS
RETRIEVAL_CAPABILITY=PARTIAL
FULL_V4_OPERATIONAL_READINESS=NOT_READY
```

즉 “계약 준수”와 “runtime binding”은 별도 축이 맞습니다. 그러나 기존 `PASS`가 installability까지 암시했다면 단순 설명 추가로는 부족하고, 해당 보고서는 반드시 supersede해야 합니다.

# 다음 10개 작업

## 1. MVP 경계와 release-local source binding을 동결

**파일**

```text
docs/decisions/20260814-mvp-runtime-binding.md
```

다음을 고정하십시오.

* 여섯 operation
* 세 served retrieval lane
* `src/epistemic_foundry`를 `MVP_RELEASE_ONLY` source로 사용
* `python/epistemic_foundry`와 혼합 금지
* full v4, workflow execution, completeness `PASS` 제외
* Windows local/repo Codex plugin이 첫 지원 표면

완료 게이트:

```powershell
git ls-files src/epistemic_foundry
git status --porcelain -- src/epistemic_foundry
```

필요 runtime input이 untracked이면 다음 작업으로 넘어가지 않습니다.

## 2. Manifest bootstrap authority를 외부에 수립

**파일**

```text
governance/BOOTSTRAP_AUTHORITY.md
governance/development_manifest_authority.yaml
manifests/development_manifest.yaml
```

외부 authority가 A01에 bounded custodianship을 부여하도록 하고, self-amendment와 단독 승인을 금지하십시오. `development_manifest.yaml` 자체는 이 외부 권위의 참조만 보유합니다.

## 3. Relocatable Python runtime closure를 생성

**파일**

```text
plugins/epistemic-foundry/scripts/build-python-runtime.py
plugins/epistemic-foundry/runtime/runtime-inputs.lock
plugins/epistemic-foundry/runtime/requirements-mvp.lock
plugins/epistemic-foundry/runtime/bootstrap.py
```

생성물:

```text
plugins/epistemic-foundry/runtime/python/
plugins/epistemic-foundry/runtime/spec/
plugins/epistemic-foundry/runtime/runtime-manifest.json
```

`src/epistemic_foundry`, 필요한 static resources, hash-pinned dependency만 staging하십시오. repository cwd fallback과 runtime network installation은 금지합니다.

## 4. 공통 Python launcher를 구현

**파일**

```text
plugins/epistemic-foundry/src/python-runtime.mjs
plugins/epistemic-foundry/dist/python-runtime.mjs
```

구현할 것:

* `EFOUNDRY_PYTHON` → `py -3` → `python` → `python3`
* version/import/integrity probe
* `runtime/bootstrap.py` 실행
* stdout/stderr/exit code/signal 전달
* `PYTHON_INTERPRETER_NOT_FOUND`
* `PYTHON_VERSION_UNSUPPORTED`
* `RUNTIME_INTEGRITY_FAILED`
* `BUNDLED_IMPORT_FAILED`

오류 코드는 문자열 식별자와 nonzero process exit를 함께 반환하십시오.

## 5. 빠진 `dist/cli.mjs`를 복구

**파일**

```text
plugins/epistemic-foundry/src/cli.mjs
plugins/epistemic-foundry/bin/efoundry.mjs
plugins/epistemic-foundry/dist/cli.mjs
```

`bin/efoundry.mjs`의 publication target은 유지합니다. 단, 상대경로 계산과 child exit propagation이 잘못되어 있다면 그 부분만 고칩니다. `dist/cli.mjs`는 task 4 launcher를 사용하고 domain logic을 포함하지 않습니다.

최초 smoke:

```powershell
node plugins/epistemic-foundry/bin/efoundry.mjs --json status
```

## 6. MCP surface를 여섯 도구 allowlist로 교체

**파일**

```text
plugins/epistemic-foundry/src/mcp-server.mjs
plugins/epistemic-foundry/src/tool-descriptors.json
plugins/epistemic-foundry/.mcp.json
plugins/epistemic-foundry/.codex-plugin/plugin.json
plugins/epistemic-foundry/dist/mcp-server.mjs
plugins/epistemic-foundry/dist/tool-descriptors.json
```

등록 집합:

```text
foundry.status
foundry.schemas.list
foundry.validate
foundry.ledger.query
foundry.retrieve.build
foundry.retrieve.query
```

`foundry.health`, `foundry.map.query`, 10개 stub tool을 제거합니다. 모든 workspace-sensitive tool에 `workspace_root`를 요구합니다. descriptor name set과 handler name set의 exact equality를 startup invariant로 둡니다.

## 7. Hook을 동일 runtime probe에 연결

**파일**

```text
plugins/epistemic-foundry/src/hook-runner.mjs
plugins/epistemic-foundry/hooks/hooks.json
plugins/epistemic-foundry/dist/hook-runner.mjs
```

`SessionStart`에서는 다음만 알립니다.

```text
READY:
  six MVP operations available
  three retrieval lanes served

DEGRADED:
  exact runtime failure
  available tool: foundry.status only
```

hook에서 package 설치, index 생성, ledger 변경을 자동 수행하지 마십시오. Codex plugin hooks는 plugin root와 writable plugin data 위치를 별도 환경변수로 받으므로, plugin 설치 위치를 cwd로 추측할 필요가 없습니다. ([OpenAI Developers][3])

## 8. 단일 재현 build와 tracked payload를 확립

**파일**

```text
plugins/epistemic-foundry/scripts/build.mjs
plugins/epistemic-foundry/package.json
.gitignore
plugins/epistemic-foundry/dist/**
plugins/epistemic-foundry/runtime/**
```

`build.mjs`가 task 3의 Python bundle과 task 4–7의 Node dist를 모두 생성하게 하십시오. 전역 `dist/` ignore가 있다면 plugin path 예외를 추가합니다.

완료 게이트:

```powershell
node plugins/epistemic-foundry/scripts/build.mjs

git diff --exit-code -- `
  plugins/epistemic-foundry/dist `
  plugins/epistemic-foundry/runtime

git ls-files `
  plugins/epistemic-foundry/dist `
  plugins/epistemic-foundry/runtime
```

마지막 명령은 비어 있으면 실패입니다.

## 9. Repository와 격리된 clean-install tests를 추가

**파일**

```text
tests/plugin/clean-install.test.mjs
tests/plugin/mcp-tools.test.mjs
tests/plugin/degraded-runtime.test.mjs
tests/plugin/retrieval-lanes.test.mjs
```

반드시 검증할 경우:

* plugin directory만 임시 디렉터리에 복사
* 전역 `efoundry` 없음
* `import epistemic_foundry`가 사용자 환경에서는 실패
* plugin-local CLI는 성공
* schema count 127
* MCP `tools/list` 정확히 6개
* 세 retrieval lane 실제 실행
* 나머지 여덟 lane은 `UNSEARCHED`
* Python interpreter가 없으면 crash 대신 `DEGRADED`
* repository `src/` 또는 `python/`을 임시로 노출하면 테스트 실패

## 10. Product readiness를 별도 authoritative gate로 게시

**파일**

```text
schemas/product-runtime-readiness.schema.json
artifacts/product_readiness/current.json
README.md
```

현재 status 구현 파일은 다음으로 찾은 뒤 수정하십시오.

```powershell
rg -l "canonical_schemas_loaded" src/epistemic_foundry
```

또한 모순 가능성이 있는 PASS report를 찾으십시오.

```powershell
rg -l `
  "dist/cli\.mjs|bin/efoundry\.mjs|mcp-server|tool-descriptors|installable|runtime binding|release payload" `
  artifacts/work_packages docs
```

명시적으로 installability나 MCP availability를 주장한 report만 다음 형태로 supersede합니다.

```text
artifacts/work_packages/<affected-ID>/report.json
artifacts/work_packages/<affected-ID>/<new-superseding-report>.json
```

최종 gate는 다음 세 줄을 동시에 보여야 합니다.

```text
SPEC_CONFORMANCE: PASS
MVP_RUNTIME_READINESS: PASS
FULL_V4_OPERATIONAL_READINESS: NOT_READY
```

이 순서대로 진행하면 첫 사용자 가치가 발생하는 지점은 task 6이 아니라 **task 9의 clean-install 성공**입니다. 그 이전에는 repository 내부에서만 작동하는 개발 상태이며, task 10이 완료되어야 비로소 장부도 그 사실을 정직하게 표현합니다.

[1]: https://developers.openai.com/plugins/build/plugins "https://developers.openai.com/plugins/build/plugins"
[2]: https://developers.openai.com/plugins/build/mcp-server "https://developers.openai.com/plugins/build/mcp-server"
[3]: https://developers.openai.com/codex/hooks "https://developers.openai.com/codex/hooks"
