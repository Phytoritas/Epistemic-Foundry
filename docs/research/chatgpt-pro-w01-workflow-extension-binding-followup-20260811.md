SPEC_GAP

* `retrieval_candidate_contract`를 `compiled_sha256`에서 제외하는 것은 **중대한 W01 무결성 결함**입니다. 해당 필드는 단순 메타데이터가 아니라 business output과 telemetry envelope의 구분, provider request 결속 필드, snapshot mismatch 처리, silent fallback 금지, 허용 origin 및 vector-only ceiling을 규정합니다. 이를 변경하거나 삭제해도 동일한 compiled identity가 유지되면 서로 다른 실행 계약이 동일한 workflow로 재생·감사될 수 있습니다. 

* W01이 모든 추가 필드를 재귀 canonicalize하여 **무조건 opaque binding**하는 것도 안전하지 않습니다. 그것은 내용 변조 탐지는 제공하지만, 오탈자나 임의 caller 필드까지 canonical execution identity에 편입합니다. 동시에 scheduler/runtime이 그 필드를 해석하지 않으므로 “identity에는 포함되지만 아무도 시행하지 않는 계약”이 생깁니다. 무결성 binding은 semantic admission이나 runtime ownership을 대신하지 못합니다.

* **현재 허용되는 최소 W01-local 조치**는 추가 top-level 필드를 계속 무시하는 것이 아니라, 닫힌 extension authority가 생길 때까지 모든 미등록 추가 필드를 필드명과 함께 typed fail-closed로 거부하는 것입니다. 따라서 현 상태의 `evidence_retrieval.workflow.yaml`도 조용히 컴파일하지 말고 extension-authority blocker로 중단해야 합니다. `retrieval_candidate_contract`를 W01 코드에 단독 literal allowlist로 박는 것은 compiler가 shared vocabulary를 자가 발명하는 것이므로 허용되지 않습니다.

* 상위 결정은 최소한 다음을 동결해야 합니다.

  1. 허용되는 workflow top-level extension의 닫힌 목록—현재 후보는 정확히 `retrieval_candidate_contract`;
  2. 각 extension의 schema 또는 검증 가능한 closed shape와 required/optional 규칙;
  3. canonical normalization 및 `compiled_sha256` preimage 포함 방식;
  4. scheduler projection에서 유지할지, 별도 retrieval runtime에 전달할지;
  5. 각 필드를 실제로 강제하는 runtime owner와 실패 의미;
  6. unknown extension은 항상 거부한다는 규칙.

* 이 결정은 W01의 유일한 write scope인 `packages/foundry-kernel/src/workflows/compiler/**` 밖의 공유 계약과 workflow/runtime ownership을 요구합니다. W01의 manifest 권한은 compiler 내부에 한정되고, 종료 기준은 DAG/resource 검증과 unknown-executor 차단입니다.  정확한 owner와 계약 경로는 `manifests/development_manifest.yaml`에서 먼저 배정되어야 하며, 그 뒤 W01은 **등록된 extension만** normalized projection과 함께 compiled identity에 결박할 수 있습니다. 누락된 공유 의미는 `SPEC_GAP`으로 중단하라는 상위 원칙과도 일치합니다. 
