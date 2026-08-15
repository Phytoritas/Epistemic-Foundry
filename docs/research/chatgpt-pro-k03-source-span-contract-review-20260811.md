AUTHORIZED_LOCAL_REPAIR

* **null-page, detached snapshot, primitive detachment, `section` 보존 수정은 모두 정당합니다.** Canonical 분기대로 `page=None`은 `coordinate_system="not_available"` 및 `bbox=None`일 때만 허용해야 하며, 양의 정수 page도 계속 허용해야 합니다. K03은 정확히 SourceSpan emission 경로를 소유하고, 종료 기준도 source resolution과 typed page/bbox/char locator입니다. 

* **source 결속에는 추가 blocker가 보이지 않습니다.** 설명된 현재 경로는 immutable source snapshot → exact char slice → `verbatim_text`/`text_hash` → document/version/provenance/source hash → deterministic `span_id`를 재검증하므로, caller alias나 재해시만으로 다른 source slice를 동일 span으로 통과시킬 수 없습니다. Workflow도 기존 `epistemic_foundry.ingest.spans:emit`을 요구하므로 별도 executor-owner `SPEC_GAP`은 없습니다. 

* **남은 K03-local blocker는 기존 `_bbox`의 schema 초과 제약입니다.** 현재 로직이 여전히 다음을 강제한다면 canonical 스키마보다 입력을 부당하게 좁힙니다.

  * `bbox=None`이면 항상 `coordinate_system=not_available`
  * `not_available`이면 bbox 배열 금지
  * 좌표는 모두 0 이상
  * `x1>x0`, `y1>y0`
  * normalized 좌표는 모두 1 이하

  Canonical 계약은 bbox에 대해 `null` 또는 **네 개의 number**만 요구하고, 추가로 **`page=null`일 때에만** `not_available + bbox=null`을 강제합니다. 따라서 위 역방향·기하학 제약은 higher authority 없이 schema-valid locator를 거부합니다.

* **최소 안전 변경:** `_bbox`는 배열인 경우 정확히 네 개의 finite JSON number인지 검사하고 그 값을 그대로 보존하십시오. page validator는 `None` 또는 exact `int >= 1`만 허용하고, 오직 `page is None → coordinate_system == not_available and bbox is None`만 결합 검사해야 합니다. 기존 char-range, nonempty resolved slice, text hash, span ID 재검증은 source-resolution 종료 기준에 직접 필요하므로 유지합니다.
