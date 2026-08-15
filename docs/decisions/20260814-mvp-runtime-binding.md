# MVP 런타임 결합 — 릴리스 한정 결정

상태: **미승인**. 구현은 동작하지만 상위 계약과 충돌합니다.
범위: 이 MVP 릴리스에만 적용.

> 독립 리뷰에서 이 구현이 `MASTER_SPEC.md:43`의 fail-closed stub 요구,
> `SPEC_BUNDLE` 릴리스 수준, compatibility matrix, T03/T01 계약과 직접
> 충돌한다는 점이 확인됐습니다. 전체 목록과 해소 방법은
> [충돌 기록](20260814-mvp-runtime-binding-authority-conflicts.md)에
> 있습니다. 그 충돌이 해소되기 전까지 이 문서는 제안이지 승인이 아닙니다.

## 무엇을 결정하는가

설치된 `plugins/epistemic-foundry`가 실제로 동작하도록 만들기 위해, **이
릴리스가 어떤 바이트를 실행하는지**만 고정합니다. 전역 canonical Python 루트
비준이 아니며, 다른 패키지의 소유권을 바꾸지 않습니다.

## 배경 — 왜 이것이 필요한가

`artifacts/work_packages/*/report.json` 156개가 모두 `PASS`이지만 설치된
제품은 동작하지 않았습니다. 확인된 직접 원인은 계약 의미론이 아니라 배포
결합의 부재였습니다.

- `plugins/epistemic-foundry/bin/efoundry.mjs`가 `../dist/cli.mjs`를 실행하는데
  그 파일이 존재하지 않았습니다.
- Python 배포판 `epistemic_foundry`가 설치되어 있지 않았습니다. 그러나
  `PYTHONPATH=src`를 주면 CLI가 실제로 동작합니다.
- `plugins/epistemic-foundry/dist/`의 파일이 전부 git 미추적이어서 clone과
  릴리스에는 포함되지 않았습니다.
- MCP 서버가 13개 도구를 광고하지만 실제 backed는 3개였습니다.

## 결정 1 — MVP가 보장하는 사용자 행위

다음 여섯 가지만 보장합니다.

1. 런타임 상태 확인 (`status`)
2. canonical schema 목록 확인 (`schemas`)
3. 아티팩트 검증 (`validate`)
4. ledger 검증 (`ledger verify`)
5. retrieval 인덱스 생성 (`retrieve build`)
6. retrieval 레인 조회 (`retrieve query`)

## 결정 2 — 명시적으로 제외하는 것

아래는 MVP 범위 밖이며, 동작한다고 주장하지 않습니다.

- 23개 워크플로 350개 노드의 실행
- executor 합성 및 `executor_status` 결합
- G01–G13 증거 재계산
- effect terminal proof
- 11개 retrieval lane 완성 (3개만 제공)
- search-completeness `PASS`
- "완전한 v4" 또는 "전 기능 operational" 주장

제공 레인은 `lexical`, `citation`, `entity_variable` 세 개입니다. 나머지 여덟
개 canonical lane은 의도적으로 `UNSEARCHED` 센티널을 반환하며, 이는 결함이
아니라 선언된 미구현입니다.

## 결정 3 — 릴리스 런타임 소스

런타임 바이트는 `src/epistemic_foundry`에서만 가져옵니다.

- `python/epistemic_foundry`와 혼합하지 않습니다.
- 이 결정은 `python/epistemic_foundry`를 폐기하거나 비추천하지 않습니다.
- 두 루트 사이의 전역 canonical 결정은 여전히 미해결이며 이 문서로 종결되지
  않습니다.

선택 근거는 하나입니다. `src/epistemic_foundry`가 현재 실행이 실제로 관찰된
유일한 루트이고, `pyproject.toml`이 배포 루트로 선언한 곳입니다.

### 관문 검증 결과

MVP 여섯 동작이 실제로 import하는 모듈 13개가 전부 tracked임을 확인했습니다.

```text
cli/main.py, cli/__init__.py,
contracts/registry.py, contracts/validation.py,
domain/hashing.py, domain/ids.py, domain/status.py, domain/time.py,
noetic_ledger/ledger.py, noetic_ledger/receipts.py,
retrieval/lanes.py, retrieval/lexical_index.py, retrieval/search_state.py
```

canonical 리소스도 `src/epistemic_foundry/_canonical` 아래 129개 파일이
tracked이며 작업 트리에서 clean합니다. 따라서 릴리스 런타임은 미추적 파일에
의존하지 않습니다.

`retrieval/lanes.py`와 `retrieval/search_state.py`는 현재 수정 상태입니다.
빌드는 작업 트리 바이트를 스테이징하고 그 해시를 매니페스트에 기록하므로,
무엇이 실행되는지는 항상 정확히 드러납니다.

## 결정 4 — Python 결합 방식

플러그인은 **인터프리터만 외부에 의존**하고, 애플리케이션 코드와 canonical
리소스는 플러그인 루트 안에 번들합니다.

- `pip install -e .`를 전제하지 않습니다. 개발 checkout 위치를 제품 전제조건으로
  만들기 때문입니다.
- 전역 `efoundry` 실행 파일을 PATH에서 찾지 않습니다.
- Python 의미론을 Node로 재구현하지 않습니다. 이미 동작하는 schema registry,
  validation, ledger, FTS5 retrieval을 복제하면 오히려 전역 canonicalization과
  parity 결정이 즉시 MVP blocker가 됩니다.

인터프리터 탐지 순서는 `EFOUNDRY_PYTHON` → `py -3` → `python3` → `python`이며,
각 후보는 존재 확인이 아니라 실제 부트스트랩 실행으로 검증합니다.

## 결정 5 — 배포물 추적

재현 가능한 빌드 스크립트와 그 산출물을 **둘 다** 커밋합니다. 산출물만
커밋하면 재현성이 없고, 스크립트만 커밋하면 설치 직후 실행되지 않습니다.

`.gitignore`는 이미 `plugins/epistemic-foundry/dist/`를 예외 처리하고 있으므로
정책 변경이 필요하지 않습니다.

## 결정 6 — 정직성 경계

계약 준수와 런타임 결합은 별개의 축이며, 별개로 보고합니다.

```text
WORK-PACKAGE CONTRACT CONFORMANCE : PASS (156/156)
MVP RUNTIME READINESS             : 이 작업의 대상
FULL V4 OPERATIONAL READINESS     : NOT READY
```

`156/156 PASS`를 제품 완료 신호로 단독 표시하지 않습니다. 기존 보고서 중
설치 가능성이나 런타임 결합을 명시적으로 주장한 것이 있다면 원본 바이트를
수정하지 말고 후속 기록으로 supersede합니다.

## 이 결정이 권한을 만들지 않는 것

- 다른 68개 패키지의 소유권 재배치
- `python/epistemic_foundry`의 삭제 또는 폐기
- 전역 canonicalization profile 확정
- workflow executor 결합 계약

상위 결정 16건은 여전히 미해결입니다. 다만 그중 MVP 여섯 동작의 입력, 출력,
실행 바이트를 결정 불가능하게 만드는 것은 없습니다.
