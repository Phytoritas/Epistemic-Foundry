# BLOCKERS

## 1. BLOCKING — `brief_hash`와 ACL/실명성 판단이 동일한 detached snapshot에 결박되지 않습니다

현재 `_mapping()`은 최상위 mapping만 얕게 복사하고 중첩 배열·mapping은 원래 객체를 그대로 보존합니다. `_sequence()`도 호출될 때마다 해당 객체를 다시 순회합니다. 

그 결과 `_validate_brief()`는 먼저 중첩 assertion 배열을 읽어 `normalized`를 만들고, 나중에 원래 `brief`의 중첩 객체를 다시 순회하여 `brief_hash`를 계산합니다. 이후 `seal_dispatch()`는 그 앞서 만든 `normalized` 값을 ACL 및 blindness 판단에 사용합니다.   

따라서 JSON 직렬화가 가능한 stateful `list` subclass로 다음 경로가 실제로 성립합니다.

```text
첫 번째 순회: evidence_ids = ["EV-support"]
    → normalized brief와 ACL 판단에 사용

두 번째 순회: evidence_ids = ["EV-counter"]
    → 기존 asserted brief_hash와 일치

결과: hash 검사는 통과하지만 ACL 판단은 hash가 결박한 내용과 다른 값을 사용
```

이 형태로 현재 `seal_dispatch()`가 성공하는 것을 재현했습니다. 즉 일반 `dict`/`list`의 단순 수정은 `BRIEF_HASH_MISMATCH`로 막히지만, 현재 허용된 `Mapping`/`Sequence` 구현을 이용하면 **다른 내용이 hash되고 다른 내용이 판단될 수 있습니다.**

### 최소 P01-owned correction

`contracts.py`에 brief 전용 private snapshot 단계를 추가하십시오.

```python
def _snapshot_brief(value: object, label: str) -> dict[str, Any]:
    canonical_bytes = _canonical_json(value)
    snapshot = json.loads(canonical_bytes)
    if type(snapshot) is not dict:
        _fail("INPUT_INVALID", f"{label} must be an object")
    return snapshot
```

그리고 읽기 경계를 다음처럼 고정해야 합니다.

```text
_validate_brief:
  caller object를 정확히 한 번 snapshot
  → 그 snapshot만 field validation, hash recomputation, normalization에 사용

seal_brief:
  caller object를 정확히 한 번 snapshot
  → 그 snapshot에 brief_hash 계산
  → 같은 snapshot을 private validator에 전달
  → 그 snapshot 반환
```

원래 중첩 객체를 snapshot 이후 다시 읽어서는 안 됩니다. 배열 순서와 중복은 snapshot에 그대로 보존되고, 기존 normalization이 필요하다면 반드시 그 snapshot의 결정론적 파생값이어야 합니다.

이 수정은 P01의 정확한 write scope 안에 있습니다. 

## 2. BLOCKING — `created_at`이 실제 RFC 3339 date-time인지 검증되지 않습니다

현재 `_timestamp()`는 정규식만 확인합니다. 따라서 다음처럼 존재하지 않는 날짜도 통과합니다.

```text
2026-02-30T12:00:00Z
```

실제로 이 값을 가진 CouncilBrief가 현재 `seal_brief()`에서 성공적으로 봉인됩니다. 현재 helper는 문자열 형태만 검사합니다.  반면 CouncilBrief schema는 `created_at`을 `date-time`으로 선언합니다. 

최소 수정은 정규식 확인 뒤 실제 calendar/offset parsing을 추가하는 것입니다.

```python
from datetime import datetime

def _timestamp(value: object, label: str) -> str:
    text = _text(value, label)
    if RFC3339_PATTERN.fullmatch(text) is None:
        _fail("INPUT_INVALID", f"{label} must be an RFC3339 timestamp")
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        _fail("INPUT_INVALID", f"{label} must be a real RFC3339 timestamp")
    return text
```

원문 문자열은 정규화하지 말고 그대로 반환해야 hash preimage가 바뀌지 않습니다. 새 error vocabulary는 필요하지 않습니다.

## 그 밖의 검토 결과

* 위 두 문제를 제외하면 CouncilBrief의 14개 필수 top-level field와 assertion의 6개 필드는 hash 비교 전에 모두 검사됩니다. SemVer와 SHA-256 문법, role/verdict vocabulary, boolean `blind`, confidence 범위, 반증조건, strongest counterargument, missing-evidence 원소 타입도 확인됩니다. Schema가 요구하는 필드 집합은 현재 코드의 검사 집합과 일치합니다.  
* 일반적인 plain JSON brief를 수정하고 기존 hash를 유지하는 경로는 차단됩니다. `_validate_brief()`가 ACL·blindness 검사보다 먼저 호출되며, schema-valid field 변경도 `BRIEF_HASH_MISMATCH`에서 중단됩니다. 
* 새 role-registry parsing은 첨부된 현 registry의 정상 동작을 바꾸지 않습니다. 현재 defender와 prosecutor의 role ID 및 ACL 원소는 실제 문자열이며, 코드가 반환하는 정렬된 ACL과도 일치합니다.  실제 문자열 강제, duplicate role/ACL 거부, `str()` coercion 제거는 fail-closed correction입니다. 
* 이번 patch가 ContextManifest authority를 새로 발명하지는 않았습니다. `validate_context_manifest()`는 여전히 field shape, included/withheld disjointness, self-hash만 검사합니다. Registry revision이나 immutable evidence corpus/class snapshot을 검증하지 않습니다.  따라서 기존 `P01-CONTEXT-MANIFEST-REGISTRY-AND-EVIDENCE-SNAPSHOT-BINDING` 공백은 그대로 남고, 이번 local correction으로 P01 exit criteria나 package 완료를 주장할 수 없습니다. 상위 권위도 누락된 shared semantics는 `SPEC_GAP`으로 유지하도록 요구합니다. 

**결론: 위 두 P01-owned correction이 필요하므로 `NO_BLOCKER`가 아닙니다.**


*Generated 1 image(s). Saved to: C:\Users\yhmoo\.oracle\sessions\pro-d34e2f-f77952\artifacts\file_00000000f92c81f8bc242b239e387e0a.png*
