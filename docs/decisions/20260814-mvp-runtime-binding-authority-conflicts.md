# MVP 런타임 결합 — 상위 계약과의 충돌 기록

상태: **부분 해소**. `PLUGIN_ALPHA_CUTOVER_20260815`가 아래 1–3번과
5번의 상위 권위 충돌을 해소했습니다. T03 결합, pathless runtime, durable
session composition 소유권은 아직 구현·계약 작업이 남아 있으며, 이 문서는
릴리스 승인이나 게이트 통과 기록이 아닙니다.

> 2026-08-15 갱신: `MASTER_SPEC.md`는 실행 가능한 `PLUGIN_ALPHA` 후보를
> 허용하고, qualified status는 `SPEC_BUNDLE`로 유지합니다.
> `acceptance_matrix`에는 15번째 installed-dist 게이트가 추가됐고,
> `compatibility_matrix`에는 후보 runtime mechanisms와 열 개 payload
> top-level 항목이 동결됐으며, A01이 `docs/decisions/**`를 관리합니다.

## 왜 이 문서가 있는가

[MVP 런타임 결합 결정](20260814-mvp-runtime-binding.md)에 따라 설치된
플러그인이 실제로 동작하도록 만들었고, 저장소 없는 복사본에서 여섯 동작이
모두 실행되는 것을 확인했습니다.

그러나 독립 리뷰에서 확인된 사실이 있습니다. **작동하는 런타임 자체가 현재
상위 권위 문서와 직접 충돌합니다.** 하위 결정 문서가 상위 계약을 덮을 수
없으므로, 이 구현은 아래 충돌이 해소되기 전까지 승인된 상태가 아닙니다.

`AGENTS.md`의 권위 순서상 이것은 `SPEC_GAP` 정지 조건입니다. 조용히 넘어가지
않고 명시적으로 기록합니다.

## 충돌 목록

### 1. `MASTER_SPEC.md:43` — 실행 파일은 fail-closed stub이어야 함

> Reference plugin executables remain fail-closed stubs.

현재 `bin/efoundry.mjs`는 stub이 아니라 실제 Python 런타임을 실행합니다.
이것이 가장 근본적인 충돌이며, 나머지는 대부분 여기서 파생됩니다.

### 2. `manifests/acceptance_matrix.yaml:3` — `SPEC_BUNDLE`

릴리스 수준이 `SPEC_BUNDLE`이고 "No working-runtime claim"을 명시합니다.
동작하는 런타임을 출하하면 이 수준을 벗어납니다.

### 3. `manifests/compatibility_matrix.yaml`

- `runtime_capabilities: []` (14행)
- `expected_top_level`이 `.codex-plugin`, `.mcp.json`, `assets`, `bin`,
  `hooks`, `skills` 여섯 개로 고정 (19–25행)

페이로드에 `dist`, `runtime`, `scripts`, `src`가 추가되어 이 목록과
불일치합니다. `tests/install/z01_matrix_harness.py`가 실제 자식 항목을
열거해 비교하므로 실제로 깨집니다.

`dist`와 `runtime`은 설치에 필요합니다. `scripts`와 `src`는 빌드 입력이므로
출하 페이로드에서 제외하는 편이 맞을 수 있으나, 어느 쪽이든 이 파일은 Z01
소유라 여기서 바꿀 수 없습니다.

### 4. T03 exit criteria (`manifests/development_manifest.yaml:2842`, `:2847`)

**대부분 해소됨.** 현재 페이로드는 canonical 13개를 정적으로 광고하고
`foundry.status`/`health`/`map.query` 세 개가 실제로 backed입니다. 이는 T03이
요구하는 바와 정확히 일치합니다.

남은 불일치는 셋입니다.

1. T03은 "adds exactly the mcpServers key"라고 하지만 현재 매니페스트에는
   `skills`·`hooks`·`mcpServers` 세 키가 있습니다. `skills`와 `hooks`가
   없으면 이미 출하된 29개 스킬과 SessionStart 훅이 호스트에 등록되지
   않습니다. 어느 패키지가 그 두 키를 추가해야 하는지는 별도 확인이
   필요합니다.
2. T03은 `foundry.map.query`가 "reports truncation rather than narrowing what
   the map claims to cover"를 요구합니다. `limit` 초과 시 전체 맵을
   `DEGRADED`와 함께 반환하도록 했으므로 축소는 하지 않지만, 요청된 한도를
   지키지도 않습니다. 실제 relevance 기준 절단과 그에 맞는 edge/hash 재계산은
   구현하지 않았습니다.
3. 패키지 hook runner는 H01 소스가 아니라 플러그인 자체 소스에서 생성됩니다.
   T03은 H01-owned adapter에서 생성되고 provenance hash가 기록될 것을
   요구합니다. 현재 사본은 번들 런타임 상태를 보고하도록 바뀌어 H01 소스와
   의미가 다르며, 두 소스가 독립적으로 drift할 수 있습니다.

### 5. T01 canonical catalog — **해소됨**

처음에는 손으로 쓴 6개 도구 descriptor와 프로토콜 `2025-06-18`을 썼습니다.
조사 결과 그 6개 중 canonical 이름과 일치하는 것은 `foundry.status`
하나뿐이었습니다. 즉 "canonical의 부분집합"이 아니라 **경쟁하는 별개 계약**
이었고, 이는 EF4-I22(wire literal 재선언 금지) 위반입니다.

되돌렸습니다. 현재 확인된 상태는 다음과 같습니다.

- 패키지 descriptor는 손으로 쓰지 않고, 빌드 시
  `packages/plugin-host/src/mcp/generated/tool-descriptors.json`에서
  복사합니다. 두 파일의 차이는 `generated_from` 한 줄뿐입니다.
- 프로토콜 `2026-07-28`, 13개 도구, 순서·`inputSchema`·`annotations` 일치
- result envelope은 canonical 10개 필드 정확히, error envelope은 7개 필드
  정확히
- error code는 sealed enum만 사용합니다. 런타임 고유 코드는
  `details.runtime_error_code`로 전달합니다 (T02가 하위 코드를 `details`에
  넣는 방식과 동일).
- 바인딩된 3개는 `foundry.status`, `foundry.health`, `foundry.map.query`이고
  나머지 10개는 `read_model_state: UNAVAILABLE`과 사유를 반환합니다.
- 모든 인자는 도구 자신의 `inputSchema`로 먼저 검증합니다. 잘못된 요청이
  가용성 사실로 둔갑하지 않습니다.

이는 T03 exit criteria가 원래 요구하던 형태와 같습니다.

### 6. pathless 정책

`packages/plugin-host/src/cli/pathless.mjs`는 bare interpreter 이름과 PATH
조회를 금지합니다. 새 런처는 `py`/`python`/`python3`을 PATH에서 찾습니다.

이것은 설계상 불가피한 면이 있습니다 — 플러그인은 사용자의 인터프리터 경로를
알 수 없습니다. 그러나 그 판단은 T03 계약을 바꾸는 결정이며, 구현이 단독으로
내릴 수 있는 결정이 아닙니다.

### 7. 소유권

`plugins/epistemic-foundry/**`는 X01이 소유합니다
(`development_manifest.yaml:3285`). 새로 만든 `src/**`, `runtime/**`,
`scripts/**`는 그 안에 있으므로 X01 범위입니다. 그러나
`docs/decisions/**`는 **어떤 패키지의 write scope에도 없습니다.**

또한 X01은 `depends_on: [G04, N04, T04, W04]`이며 이번 작업은 T03 계약을
바꾸는데, X01이 T03을 바꿀 권한을 갖는지는 정의되어 있지 않습니다.

## 재현성 문제 (별건, 그러나 릴리스 차단)

런타임 빌더는 HEAD가 아니라 **현재 작업 트리**의 바이트를 스테이징합니다.
매니페스트가 dirty 입력 62개를 정직하게 기록하지만, 그 62개를 커밋하지 않으면
clean clone에서 같은 페이로드를 재현할 수 없습니다.

따라서 이 페이로드는 현재 **릴리스 후보가 아닙니다.** 커밋 시점에 소스와
페이로드를 함께 커밋하거나, 빌더가 dirty 입력에서 실패하도록 바꿔야 합니다.

## 해소 방법 — 두 갈래

### 갈래 A — 상위 계약을 올린다 (권장)

제품 소유자가 릴리스 수준을 `SPEC_BUNDLE`에서 한 단계 올리기로 결정하고,
다음을 함께 개정합니다.

1. `MASTER_SPEC.md`의 fail-closed stub 문장을, 무엇이 실제로 실행되고 무엇이
   여전히 미구현인지 정확히 서술하도록 교체
2. `acceptance_matrix.yaml`에 MVP 런타임 수준과 그 게이트를 추가
3. `compatibility_matrix.yaml`의 `expected_top_level`에 `dist`, `runtime`,
   `scripts`를 추가하고 `runtime_capabilities`를 실제 여섯 동작으로 갱신
4. T03 exit criteria를 실제 도구 집합으로 갱신하거나, 이 cutover를 담당할 새
   work package를 신설
5. T01 catalog를 버전업하거나, 이 6-tool 표면을 별도 프로파일로 선언
6. `docs/decisions/**`의 소유자를 지정

### 갈래 B — 되돌린다

현재 구현을 폐기하고 fail-closed stub으로 복귀합니다. 그 경우 "설치하면
아무것도 동작하지 않는다"는 상태가 유지되며, 그것이 상위 계약이 현재 요구하는
상태입니다.

## 이 구현이 주장하지 않는 것

- 어떤 work package도 통과했다고 주장하지 않습니다.
- `156/156 PASS`를 갱신하거나 무효화하지 않습니다. 다만 그 숫자가 설치
  가능성을 의미하지 않는다는 점은 이제 명시적으로 확인됐습니다.
- 릴리스 준비 상태를 주장하지 않습니다.
- T03 또는 X01의 새 증거로 봉인되지 않았습니다.

검증된 것은 하나뿐입니다: **저장소가 없는 복사본에서 여섯 동작이 실제로
실행되고, 경로 탈출과 변조가 차단되며, Python이 없으면 정확한 코드로
실패합니다.** 그것은 동작의 증거이지 승인의 증거가 아닙니다.
