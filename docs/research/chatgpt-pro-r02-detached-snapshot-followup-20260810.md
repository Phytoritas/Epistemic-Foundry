**BLOCKER — detached snapshot이 유효하지 않은 중첩 mapping key를 문자열로 세탁합니다.**

기존 alias-drift/재읽기 blocker 자체는 닫혔습니다. 두 public 경로 모두 hash·semantic validation 전에 detached object로 교체하고, 회귀도 이후 원본 mutation이 봉인 결과에 영향을 주지 않음을 확인합니다.   

그러나 `_detached_json_object()`가 caller tree를 곧바로 `json.dumps → json.loads`하기 때문에, Python JSON encoder가 중첩된 integer·boolean 등의 mapping key를 문자열로 변환한 뒤 semantic validator에 넘깁니다.  예를 들어 premise와 conclusion의 `conditions`가 모두 `{1: "x"}`이면 `"1"` key로 변환되어 통과할 수 있습니다. 이는 `_mapping()`이 모든 mapping key를 실제 문자열로 요구하고, `_validate_scope()`가 `conditions`와 `domain_extensions`에 그 검사를 적용하려는 기존 계약을 우회합니다.  

**최소 R02-owned correction:** caller tree를 먼저 JSON 직렬화하지 말고, Mapping/Sequence를 **한 번만 재귀 순회하여** plain `dict`/`list` snapshot을 구성하십시오. 그 과정에서 모든 mapping key가 실제 `str`인지 검사하고 비문자열 key를 `INPUT_INVALID`로 거부한 뒤, 완성된 plain snapshot만 canonicalize하십시오. 원본에 대한 별도 preflight 후 재직렬화하는 방식은 다시 이중 읽기 창을 만들므로 사용하면 안 됩니다.
