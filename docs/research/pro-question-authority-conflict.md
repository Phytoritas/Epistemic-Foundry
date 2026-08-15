# 후속 질문 — 작동하는 런타임이 상위 계약을 위반합니다

## 이전 턴 요약

당신의 조언대로 (b)를 실행했습니다. 상위 결정 16건을 유보하고, 이미 동작하던
Python 표면을 설치 경로에 결합했습니다. **결과는 성공입니다.**

저장소가 전혀 없는 임시 디렉터리에 플러그인만 복사한 상태에서 실측한 것:

- `node bin/efoundry.mjs --runtime-info` → scope `MVP_RELEASE_ONLY`, 번들
  352파일, interpreter `python`
- `--json status` → `canonical_schemas_loaded: 127`
- MCP `tools/list` → 6개, 전부 실제 backed
- MCP로 인덱스 생성(문서 색인) → 질의 → `outcome=PASS`, 정확한 문서 반환
- CLI lane 질의 → 봉인된 backend receipt hash 포함 정상 반환
- Python 없음 → exit 71 + `PYTHON_INTERPRETER_NOT_FOUND` (정확한 안내)
- 번들 파일 1개 변조 → exit 71 + `RUNTIME_INTEGRITY_FAILED` (파일명 지목)
- 워크스페이스 밖 읽기/쓰기 3종 시도 → 전부 `WORKSPACE_DENIED`, 파일 미생성

구현 방식은 당신 조언 그대로입니다. 인터프리터만 외부 의존, 애플리케이션
코드와 canonical 리소스는 플러그인 안에 번들, `-I` 격리 부트스트랩,
빌드 스크립트와 산출물 둘 다 커밋 대상.

## 독립 리뷰 결과 — REJECT

리뷰어가 실제 결함 여러 개를 잡았고 전부 고쳤습니다. 없는 ledger가 `PASS`하던
버그, exit code 41이 `PLAN_COMPILATION_REJECTED`와 충돌하던 문제, `py -3`가
낡았을 때 정상 `python`을 시도하지 않던 문제, 해시를 기록만 하고 검증하지
않던 문제, MCP 경로 제한 부재, 두 빌더가 같은 파일을 덮어쓰던 충돌.

**그러나 고칠 수 없는 지적이 하나 있습니다. 작동하는 런타임 자체가 상위
권위 문서와 직접 충돌합니다.**

## 충돌 목록 (전부 직접 확인함)

1. **`MASTER_SPEC.md:43`** — "Reference plugin executables remain fail-closed
   stubs." 현재 `bin/efoundry.mjs`는 stub이 아니라 실제 런타임을 실행합니다.

2. **`manifests/acceptance_matrix.yaml:3`** — `status_of_this_bundle:
   SPEC_BUNDLE`, 그리고 "No working-runtime claim."

3. **`manifests/compatibility_matrix.yaml`** — `runtime_capabilities: []`
   (14행). `expected_top_level`이 `.codex-plugin`, `.mcp.json`, `assets`,
   `bin`, `hooks`, `skills` 6개로 고정 (19–25행). 페이로드에 `dist`,
   `runtime`, `scripts`가 추가되어 불일치하며, Z01 설치 하네스가 이 목록을
   정확히 비교합니다.

4. **T03 exit criteria** (`development_manifest.yaml:2842`, `:2847`) —
   canonical 13개 도구 정적 광고, `foundry.status`/`health`/`map.query`가
   backed, 매니페스트에 `mcpServers` 키만 정확히 추가. 현재는 6개 도구,
   `health`/`map.query` 제거, 세 키 추가입니다.

5. **T01 canonical catalog** — `contracts/mcp/t01/tool-catalog.yaml`이 프로토콜
   `2026-07-28`과 13개 도구를 유일한 소스로 고정. 새 descriptor는 손으로 쓴
   6개이고 프로토콜 `2025-06-18`입니다.
   `tests/node/t01-tool-catalog.test.mjs`가 정확한 일치를 요구하므로 통과
   불가능합니다. 새 result/error envelope도 canonical `workspace_id`,
   `read_model_state`, receipts, sealed error vocabulary를 쓰지 않습니다.

6. **pathless 정책** — `packages/plugin-host/src/cli/pathless.mjs`가 bare
   interpreter 이름과 PATH 조회를 금지. 새 런처는 `py`/`python`/`python3`을
   PATH에서 찾습니다. 플러그인이 사용자 인터프리터 경로를 알 수 없으니
   불가피하지만, 그 판단은 T03 계약 변경입니다.

7. **소유권** — `plugins/epistemic-foundry/**`는 X01 소유이므로 새
   `src/**`, `runtime/**`, `scripts/**`는 범위 안입니다. 그러나
   `docs/decisions/**`는 어떤 패키지 write scope에도 없습니다. 또한 X01은
   `depends_on: [G04, N04, T04, W04]`인데 이번 작업은 T03 계약을 바꿉니다.

## 별건 — 재현성

런타임 빌더가 HEAD가 아니라 현재 작업 트리를 스테이징합니다. 매니페스트가
dirty 입력 62개를 정직하게 기록하지만, 그 62개를 커밋하지 않으면 clean
clone에서 재현 불가입니다. `--require-clean` 플래그를 추가해 릴리스 빌드는
명시적으로 거부되게 했습니다. 참고로 그 62개는 이전 세션들의 미커밋 작업이며
제가 만든 게 아닙니다(전체 트리에 미커밋 900여 개가 있습니다).

## 질문

### Q1. 어느 갈래인가

두 갈래로 봅니다.

- **A: 상위 계약을 올린다.** `MASTER_SPEC.md`의 fail-closed stub 문장 교체,
  `acceptance_matrix`에 MVP 런타임 수준 추가, `compatibility_matrix`의
  `expected_top_level`과 `runtime_capabilities` 갱신, T03/T01 개정 또는 신설
  work package.
- **B: 되돌린다.** fail-closed stub으로 복귀. 그러면 "설치해도 아무것도
  동작하지 않는" 상태가 유지됩니다.

어느 쪽입니까? 그리고 A라면, 이것이 "스펙 번들이 스스로 승격을 허가하는"
자기권한 확대가 되지 않으려면 최소 안전장치가 무엇입니까?

### Q2. 릴리스 수준의 정확한 이름과 게이트

A라면 `SPEC_BUNDLE` 위에 어떤 수준을 두어야 합니까? 그 수준이 통과를 주장하려면
어떤 게이트가 필요합니까? 제가 실측한 것들(clean-copy 실행, 변조 탐지, 경로
제한, degraded 실패)이 그 게이트로 충분합니까, 아니면 빠진 것이 있습니까?

`156/156 PASS`와 이 새 수준의 관계도 정해주십시오. 기존 리포트를 되돌려야
합니까, 아니면 두 축을 분리해 표기하면 됩니까?

### Q3. T01 catalog 충돌의 최소 해법

canonical catalog는 13개 도구 / 프로토콜 `2026-07-28`, 실제 backed는 6개입니다.
세 가지가 떠오릅니다.

1. 13개를 전부 광고하고 7개는 `UNAVAILABLE` 반환 (원래 방식으로 복귀)
2. 6개만 광고하고 catalog를 버전업
3. catalog에 "profile" 개념을 도입해 packaged profile이 부분집합을 선언

당신은 이전 답변에서 "도구 광고는 호출 가능한 capability라는 약속"이라며 6개만
등록하라고 했습니다. 그 판단을 유지합니까? 유지한다면 canonical catalog와
`t01-tool-catalog.test.mjs`를 정확히 어떻게 바꿔야 합니까?

또한 새 envelope이 canonical `workspace_id`/`read_model_state`/receipts를
쓰지 않는 문제도 있습니다. canonical envelope으로 되돌려야 합니까, 아니면
MVP 전용 envelope을 명시적으로 선언해야 합니까?

### Q4. pathless 정책

플러그인은 사용자의 Python 경로를 알 수 없으므로 PATH 탐지가 불가피해
보입니다. 그러나 T03은 그것을 금지합니다. 정책을 어떻게 정합해야 합니까?

- 정책 범위를 "저장소 내 Node CLI"로 한정하고 플러그인 런처는 예외로 선언
- 탐지된 인터프리터를 절대경로로 고정한 뒤 그 경로만 사용
- 다른 방법

### Q5. 커밋 전략

미커밋 900여 개가 있고 대부분 제 작업이 아닙니다. 이 MVP 결합만 분리해
커밋하려면 무엇을 함께 커밋해야 합니까? 런타임 페이로드 352개는 미커밋 소스
62개에 의존하므로, 그 62개를 함께 커밋하지 않으면 재현이 안 됩니다. 그런데
그 62개는 다른 작업의 산물입니다. 어떻게 분리하는 것이 정직합니까?

## 출력 형식

- Q1 판정을 첫 문단에 명시.
- Q2–Q5는 각각 별도 절.
- 마지막에 "다음 작업" 순서 목록, 각각 어느 파일을 건드리는지 포함.
- 한국어, 식별자와 경로는 영어.
