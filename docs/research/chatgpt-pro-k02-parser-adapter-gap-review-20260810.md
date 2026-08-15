AUTHORIZED_LOCAL_REPAIR

* **다섯 변경은 모두 K02 소유 범위 안의 정당한 정확성·무결성 수정입니다.**

  1. `memoryview(...).tobytes()`로 정확한 built-in `bytes`를 봉인하는 수정은 해시에 사용된 바이트와 실제 XML/JSON 해석에 사용되는 바이트가 달라지는 경로를 닫습니다. parser 실행이나 새로운 provenance 의미를 추가하지 않습니다.
  2. `confidence`를 `_differing_fields`에 포함하는 수정은 confidence-only 차이를 거짓 agreement로 분류하던 결함을 닫습니다. confidence가 observation 및 stream hash에 포함되는 이상, disagreement와 deterministic reconciliation hash에도 반영되어야 합니다.
  3. duplicate JSON key와 `NaN`/`Infinity`를 parse 시점에 거부하는 수정은 하나의 원시 artifact가 여러 의미 projection을 갖는 것을 차단합니다. 원본 바이트를 변경하지 않고 모호한 해석만 거부하므로 content-address 경계와 일치합니다.
  4. oversized integer와 numeric subclass 변환 실패를 `PARSER_OUTPUT_INVALID`로 정규화하는 것은 raw `OverflowError`가 package boundary를 빠져나가는 것을 막는 fail-closed 수정입니다.
  5. UTF-16/32의 encoding NUL을 **선언 탐지용 probe에서만** 제거하는 수정은 DTD/entity 우회를 닫으면서 immutable artifact bytes를 보존합니다. 기존 `GROBID_UNSAFE_XML` 의미도 바뀌지 않습니다.

* **그러나 K02 전체 완료는 별도의 shared-contract gap으로 남습니다:**
  `SPEC_GAP: K02-PARSER-EXECUTOR-OWNERSHIP-AND-WORKFLOW-REF-BINDING`

  현재 workflow가 요구하는

  ```text
  epistemic_foundry.ingest.grobid:parse
  epistemic_foundry.ingest.docling:parse
  ```

  는 각각 다음 sibling 경로를 요구합니다.

  ```text
  python/epistemic_foundry/ingest/grobid.py
  python/epistemic_foundry/ingest/docling.py
  ```

  두 경로 모두 K02의 유일한 write scope인 `python/epistemic_foundry/ingest/parsers/**` 밖입니다. 따라서 K02가 alias module, service launcher 또는 임의의 production `parse()`를 추가하면 manifest 권한을 위반합니다. 반대로 owned directory 안에 executor를 만들어도 현재 workflow ref와 연결되지 않습니다.

* **필요한 최소 상위 결정은 둘 중 하나를 명시적으로 선택하는 것입니다.**

  * K02 write scope를 위 두 sibling module에만 정확히 확장하고 기존 workflow refs를 유지하거나,
  * workflow refs를 `epistemic_foundry.ingest.parsers.*` 아래의 K02-owned symbol로 변경하고 그 workflow 수정 owner를 지정합니다.

  이 결정에는 실제 parser invocation이 어떤 pinned parser identity와 output artifact를 반환하는지만 최소한으로 결박해야 합니다. 서비스 discovery, credentials, timeout/cancellation, process ownership 또는 effect semantics는 현재 K02가 임의로 정할 수 없습니다.

* **현재의 최소 안전 변경은 다섯 adapter 수정만 유지하는 것입니다.** `adapters.py`는 계속 caller-supplied immutable parser output의 검증·정규화·비교·disagreement 보존만 수행해야 합니다. 존재하지 않는 executor ref를 가짜 wrapper로 채우거나, parser가 실제 실행된 것처럼 표시하거나, K02 `PASS` 또는 production reachability를 주장해서는 안 됩니다.

제시된 current-source 사실에서는 이 다섯 수정을 unsafe 또는 mis-scoped하게 만드는 더 우선적인 결함은 확인되지 않습니다.
