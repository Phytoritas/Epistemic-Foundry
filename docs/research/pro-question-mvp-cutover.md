# Epistemic Foundry v4 — 결정 요청: 사용 가능한 MVP까지의 최단 경로

## 이 대화의 성격

이것은 새 대화입니다. 이전 대화는 컨텍스트가 가득 차서 종료했습니다.
아래에 필요한 배경을 전부 담았으므로 이전 히스토리를 가정하지 마십시오.

저는 Codex(로컬 구현 에이전트)이고, 당신은 자문 역할입니다. 저장소는
`C:\dev\insight\Epistemic-Foundry` (Windows)이며, 제가 직접 읽고 수정합니다.
당신에게 파일 시스템 접근 권한은 없습니다. 아래 사실은 전부 제가 이번 세션에
실제로 확인한 것이며, 추측은 명시했습니다.

## 프로젝트 한 줄 설명

Epistemic Foundry v4는 증거 게이트 기반 연구 시스템의 사양 번들입니다.
156개 work package가 A01–Z06으로 나뉘어 있고, 각 패키지는 계약(schema),
워크플로(DAG), 불변식, 증거 아티팩트를 갖습니다. 최종 산물은 Codex에
설치되는 네이티브 플러그인 `plugins/epistemic-foundry`입니다.

## 현재 상태 — 확인된 사실만

### 장부상으로는 전부 완료

`artifacts/work_packages/<ID>/report.json` 156개가 모두 `status: PASS`입니다.
canonical ledger 기준으로 활성 `SPEC_GAP` 패키지는 0개입니다.

### 그러나 설치된 제품은 동작하지 않습니다

플러그인 페이로드 실측:

- `plugins/epistemic-foundry/dist/`에 15개 파일이 있으나 **전부 git untracked**
  입니다 (`git ls-files`가 빈 출력). 즉 릴리스/클론에는 포함되지 않습니다.
- `dist/cli.mjs`가 **없습니다**. 그런데 `bin/efoundry.mjs:6`이 정확히 그 파일을
  spawn합니다. 따라서 플러그인 CLI 진입점은 즉시 깨집니다.
- `dist/mcp-server.mjs`(20KB)는 13개 MCP 도구를 등록하지만 실제 데이터를
  반환하는 것은 3개(`foundry.status`, `foundry.health`, `foundry.map.query`)
  뿐이고 나머지 10개는 하드코딩된 `UNAVAILABLE`입니다.
- 그 3개 중 `status`/`health`는 PATH의 Python `efoundry --json status`를
  spawnSync로 호출하도록 되어 있습니다 (`dist/mcp-server.mjs:159-223`).
- `foundry.map.query`는 `EFOUNDRY_WORKSPACE_ROOT` 환경변수를 요구하는데
  `.mcp.json`이 그것을 설정하지 않습니다. 따라서 항상 unavailable입니다.
- `dist/hook-runner.mjs`는 `SessionStart`만 처리하며, 설치 페이로드를 관찰해
  안내 문구를 반환하는 것 외에 아무 일도 하지 않습니다.
- `dist`를 만드는 checked-in 빌드 스크립트가 없습니다. 유일하게 dist에 쓰는
  `packages/plugin-host/src/cli/bundle-map-worker.mjs`조차 untracked이고,
  그것도 workspace-map 11개 파일과 hook만 다루며 `mcp-server.mjs`와
  `tool-descriptors.json`은 다루지 않습니다.

### Python 런타임 실측

- `efoundry`는 PATH에 **없습니다**. `python -c "import epistemic_foundry"`는
  `ModuleNotFoundError`입니다. 즉 패키지가 설치되어 있지 않습니다.
- 그러나 `PYTHONPATH=src`를 주면 CLI가 **실제로 동작합니다**. 제가 이번 세션에
  직접 실행했습니다:
  - `efoundry --json status` → `canonical_schemas_loaded: 127`과 30개 가까운
    구현 컴포넌트 목록을 실제로 반환
  - 등록된 서브커맨드: `status`, `schemas`, `validate`, `ledger`, `retrieve`
  - `retrieve build`는 SQLite FTS5 인덱스를 실제로 만들고, `retrieve query`는
    `lexical`/`citation`/`entity_variable` 3개 레인을 실제로 실행합니다.
    나머지 8개 canonical lane은 의도적으로 `UNSEARCHED` 센티널을 반환합니다.

즉 **기능이 없는 게 아니라, 있는 기능이 설치 경로에 연결되어 있지 않습니다.**

### 남은 상위 결정 16건

별도 조사에서, 아직 상위 권위 문서에 반영되지 않은 자문성 결정 16건을
식별했습니다. 파급 범위 상위 5개만 적으면:

1. 정식 Python 루트 확정 (`src/epistemic_foundry` vs `python/epistemic_foundry`).
   tracked 기준 `python/` 아래 131파일 / 2,564,102바이트, 그중 `.py` 114파일 /
   1,860,064바이트. 정확한 상대경로 중복 3건(`contracts/__init__.py`,
   `ingest/registry/__init__.py`, `retrieval/__init__.py`). 68개 패키지 영향.
2. executor 합성 루트. 23개 워크플로 350개 노드가 `executor_ref`를 선언하지만
   `executor_status`를 선언한 노드는 0개이고, 행위가 검증된 결합은 0건.
3. 전역 canonicalization 프로파일 (JCS 규칙이 산재).
4. A05 G01–G13 증거 권위/재계산 계약.
5. `NodeAttemptEffectTerminalProof` 반송 계약.

이 16건은 대부분 "공유 계약을 바꿔야 하는데 그럴 권한을 가진 패키지가 없다"는
형태입니다. 매니페스트 자체를 소유한 패키지가 없어서 순환이 생깁니다.

## 제가 겪은 실패 패턴

지난 2주간 계속 이런 식이었습니다. 패키지를 하나 열어 결함을 찾고, 고치고,
리뷰를 붙이고, 증거를 봉인합니다. 그러면 다음 패키지에서 같은 상위 계약 공백이
다른 이름으로 다시 나타납니다. 156개 리포트가 전부 PASS인데도 설치하면 아무것도
동작하지 않는 상태가 유지됩니다. 개별 결함 수정이 제품 사용성으로 수렴하지
않고 있습니다.

## 질문

제가 원하는 것은 "이 시스템을 실제로 쓸 수 있게 되는 최단 경로"입니다.
학술적으로 완전한 v4가 아니라, 사용자가 설치해서 진짜 답을 받는 상태입니다.

구체적으로 답해주십시오.

### Q1. 순서 판정

지금 해야 할 일은 (a) 상위 결정 16건을 먼저 비준해서 계약 공백을 닫는 것입니까,
아니면 (b) 그 16건을 전부 유보한 채 이미 동작하는 Python 기능(schemas/validate/
ledger/retrieve 3레인)을 설치 경로에 연결해 최소 사용 가능 제품을 먼저 만드는
것입니까? 하나를 고르고, 다른 쪽을 고르면 안 되는 이유를 구체적으로 말해
주십시오. "둘 다 중요하다"는 답은 쓸모가 없습니다.

### Q2. (b)라면 정확한 최소 절단면

(b)를 고른다면, 다음을 정확히 지정해 주십시오.

- `dist`를 무엇으로 채워야 하는가. 특히 `dist/cli.mjs`를 새로 만들어야 하는가,
  아니면 `bin/efoundry.mjs`가 다른 것을 가리키게 바꿔야 하는가.
- Python 런타임 결합 방식. 세 후보 중 무엇이며 왜인가:
  (i) 사용자가 `pip install -e .`를 하도록 요구, (ii) 플러그인이 Python을
  탐지하고 없으면 정직하게 degraded 보고, (iii) Python 의존을 끊고 필요한
  기능을 Node로 재구현.
- MCP 도구 13개 중 MVP에 실제로 필요한 것은 몇 개이며 어느 것인가. 나머지를
  advertise하지 않는 것이 정직한가, 아니면 `UNAVAILABLE`로 남기는 것이 맞는가.
- `dist` untracked 문제. 빌드 산출물을 커밋해야 하는가, 재현 가능한 빌드
  스크립트를 만들어야 하는가, 아니면 소스에서 직접 실행하도록 바꿔야 하는가.

### Q3. 소유권 순환 해소

`manifests/development_manifest.yaml`을 소유한 패키지가 없어서, 소유권 변경을
매니페스트 안에서 정하는 것이 순환입니다. 이 부트스트랩을 어떻게 끊습니까?
A01에 매니페스트 관리권을 주는 것이 맞습니까, 아니면 매니페스트 밖의 별도
권위 문서가 필요합니까? 자기 권한 확대를 막는 최소 안전장치는 무엇입니까?

### Q4. 16건 중 MVP에 실제로 필요한 것

16건 전부가 MVP를 막습니까, 아니면 대부분은 완전한 v4에만 필요합니까?
MVP를 실제로 막는 최소 부분집합을 지정해 주십시오.

### Q5. 정직성 경계

156개 리포트가 PASS인데 제품이 동작하지 않는 상황을, 어떻게 표현하는 것이
정직합니까? 리포트를 되돌려야 합니까, 아니면 "계약 준수"와 "런타임 결합"이
원래 다른 축이라고 문서화하는 것으로 충분합니까?

## 출력 형식

- Q1 판정을 첫 문단에 명시. 선택지 하나와 그 이유.
- Q2–Q5는 각각 별도 절.
- 마지막에 "다음 10개 작업"을 순서대로, 각각 어느 파일을 건드리는지 포함해
  나열.
- 저는 로컬에서 실제로 실행 가능한 지시를 원합니다. 추상적 원칙은 최소화해
  주십시오.
- 한국어로 답하되 식별자와 경로는 영어로 유지해 주십시오.
