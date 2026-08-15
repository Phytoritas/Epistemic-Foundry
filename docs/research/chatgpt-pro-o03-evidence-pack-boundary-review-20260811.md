AUTHORIZED_LOCAL_REPAIR

* 세 결함은 모두 `python/epistemic_foundry/retrieval/evidence_pack/**` 내부의 **입력 무결성·결정론적 재구성 문제**이며, `scope_filter ↔ scope_partitions` 의미를 선택하지 않아도 고칠 수 있습니다. O03은 O01에 의존하지만, 동시에 shared sample/preprint 중복 제거와 counter/null/boundary 보존을 직접 소유합니다.  의존 evidence를 독립 표처럼 세지 않고 counter/null/boundary/method를 보존해야 한다는 상위 불변식도 이 수정을 직접 지지합니다. 

* **재귀 snapshot 수정은 필요합니다.** 각 public trust boundary에서 caller 입력을 얕게 `dict()`로 바꾸지 말고, 그 호출의 모든 JSON-bearing 인수를 하나의 합성 root에 넣어 **정확히 한 번** primitive-first 재귀 snapshot해야 합니다. 인수별로 따로 snapshot하면 동일한 stateful 객체가 여러 인수에 alias된 경우 인수 사이에서도 다른 상태를 읽을 수 있습니다.

  적용 경계는 다음과 같습니다.

  1. evidence units와 explicit review/citation links를 받아 dependency graph·cluster를 만드는 경계
  2. caller-supplied dependency cluster를 seal 또는 validate하는 경계
  3. QueryPlan, lane receipts, completeness certificate, evidence units, clusters, reconciliation inputs, `role_quotas`를 받아 pack을 조립하는 경계
  4. caller-supplied pack과 cluster를 bound inputs에서 rebuild·validate하는 경계
  5. raw mappings/sequences를 직접 받는 public effective-count·role-reconciliation 경계가 있다면 그 경계

  이미 canonical bytes로 봉인된 O03-owned artifact는 다시 caller container로 취급할 필요가 없습니다. Snapshot은 duplicate projected keys, non-string keys, cycles, byte-like/non-JSON values와 non-finite numbers를 기존 O03 typed input/canonicalization 오류로 거부하고, 이후 hash·dependency derivation·role assignment·counting·sealing은 snapshot만 읽어야 합니다.

* **`role_quotas or {}`는 제거해야 합니다.** 오직 `None`만 “quota 미지정”으로 해석하십시오. 그 외 값은 Mapping이어야 하며, 같은 합성 snapshot 안에서 detached되어야 합니다. Key는 기존 pack-role vocabulary의 exact string이어야 하고 unknown key를 거부해야 합니다. Value는 `type(value) is int and value >= 0`이어야 하므로 `True`/`False`, float, numeric subclass projection을 quota로 인정하면 안 됩니다. Quota는 최소 충족조건일 뿐 evidence 선택·절단 권한이 아니며, 0도 이미 유효하게 조립된 counter/null/boundary/method evidence를 제거할 수 없습니다.

* **`_text()`의 identity rewriting도 로컬에서 중단할 수 있습니다.** `.strip()`을 검사와 반환에 함께 사용하면 `"EV-1"`, `" EV-1"`과 `"EV-1 "`이 같은 identifier로 합쳐져 dependency edge·result reconciliation·provenance binding을 세탁할 수 있습니다. 최소 계약은 다음입니다.

  * underlying exact string을 snapshot하고 그 값을 그대로 반환합니다.
  * canonical schema가 `minLength`만 요구하는 필드는 edge whitespace를 새로 금지하지 않습니다. `"EV-1"`과 `" EV-1 "`은 서로 다른 값으로 남아야 합니다.
  * 기존 O03 field contract가 nonblank를 요구하면 whitespace-only 값은 계속 거부하되, 유효한 값을 trim하여 다른 identity로 바꾸지는 않습니다.
  * 모든 identifier에 no-edge-whitespace를 강제하려면 그것은 향후 shared schema/identifier-contract 결정입니다. 현재 integrity repair에는 필요하지 않습니다.

* **더 중요한 로컬 admission 경계는 deterministic reconstruction입니다.** “재구성할 수 있다”는 사실만으로 caller-authored pack이나 cluster가 authoritative validator를 통과하지 못한다는 보장은 없습니다. 다음을 O03의 유일한 authoritative validation path로 만들어야 합니다.

  * dependency clusters는 validated units와 deterministic dependency edges에서 연결요소를 다시 산출하고, supplied cluster set과 exact equality를 요구합니다. 한 연결요소를 여러 cluster로 쪼개기, 한 evidence ID를 여러 cluster에 중복시키기, unknown member 삽입, dependency edge 누락으로 independent count를 부풀리는 모든 경우를 거부해야 합니다.
  * effective independent count는 supplied count를 믿지 않고 재구성된 components와 truly unclustered units에서 다시 계산해야 합니다.
  * Evidence Pack은 동일한 validated QueryPlan·receipts·certificate·units·clusters·quotas로 rebuild한 결과와 exact equality를 요구해야 합니다. 각 evidence/result ID는 정확히 한 번 evidence 또는 typed unresolved disposition으로 회계되어야 하며, role 간 중복과 누락을 거부해야 합니다.
  * selected counter/null/boundary/method lane의 결과를 pack에서 숨길 수 없어야 하고, metadata-only result는 Evidence로 승격되지 않더라도 typed reconciliation에서 사라져서는 안 됩니다. Workflow 역시 raw backend output을 신뢰하지 않고, metadata-only candidate의 직접 Evidence 승격을 금지하며, dependent evidence를 counting 전에 deduplicate하도록 요구합니다. 

* 이 수정은 O01의 scope-partition 의미를 해결하지 않습니다. O03은 이미 검증되었다고 가정한 QueryPlan·receipt·certificate의 identity와 현재 공개 필드만 exact-bind해야 하며, `scope_filter`가 partition의 exact match인지 subset인지 union인지 판단해서는 안 됩니다. 따라서 로컬 수정은 진행 가능하지만, O01 결정 전에는 O03 전체 `PASS`, searched-scope completeness 또는 absence 권위를 주장할 수 없습니다. 상위 계약이 비어 있으면 `SPEC_GAP`으로 남겨야 한다는 권위 원칙도 유지됩니다. 


*Generated 1 image(s). Saved to: C:\Users\yhmoo\.oracle\sessions\pro-bb5196-c3c711\artifacts\file_00000000f92c81f8bc242b239e387e0a.png*
