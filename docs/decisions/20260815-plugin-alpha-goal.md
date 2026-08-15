# 목표 지시문 — PLUGIN_ALPHA 아키텍처 완성

아래 텍스트를 goal objective로 그대로 사용하십시오. 이 문서는 그 지시문과,
왜 그렇게 범위를 잡았는지의 근거를 함께 담습니다.

---

## goal objective (복사해서 사용)

```text
MASTER_SPEC.md를 권위로 삼아 Epistemic Foundry v4를 manifests/acceptance_matrix.yaml의
PLUGIN_ALPHA 수준까지 완성한다. 자문은 chatgpt-pro-orchestrator 스킬로 task 키
ef-impl-4를 사용한다.

완료 조건은 PLUGIN_ALPHA의 15개 게이트가 실제로 충족되고, 그 사실이 재현 가능한
명령으로 확인되는 것이다. 특히 다음이 참이어야 한다.

1. 저장소 없이 설치된 플러그인만으로 FORGE 세션을 열고, 전이시키고, 재시작 후
   복원할 수 있다. 세션 상태는 SQLite에 영속되고 원장으로 재구성된다.
2. canonical 13개 MCP 도구 중 read 계열 9개가 실제 저장소에 결합되어 있다.
   결합할 수 없는 도구는 UNAVAILABLE과 사유를 반환하되, 그 수가 왜 그만큼인지
   MASTER_SPEC 근거로 설명된다.
3. MCP가 없을 때 CLI로 같은 일을 할 수 있고, hook이 꺼져도 degraded 모드로
   동작한다.
4. 설치·업그레이드·롤백·제거가 깨끗하게 동작한다.
5. 플러그인 페이로드가 clean clone에서 재현 가능하다. 미커밋 소스에 의존하지
   않는다.
6. 설치된 dist/를 실제로 실행하는 자동 검증이 존재한다.

진행 원칙:

- 상위 권위(MASTER_SPEC, acceptance_matrix, compatibility_matrix, T01 catalog)와
  충돌하는 구현은 만들지 않는다. 충돌이 불가피하면 코드를 바꾸지 말고
  docs/decisions/에 SPEC_GAP으로 기록하고 사용자 판단을 요청한다.
- 계약이 있는 곳에는 계약을 따르고, 계약이 없는 곳에서 계약을 발명하지 않는다.
- 구현이 없는 것을 있는 것처럼 서술하지 않는다. 게이트를 통과했다는 주장은
  실행 증거로만 한다.
- 각 단계마다 작성자가 아닌 독립 리뷰어를 붙인다.
- 사용자의 미커밋 작업 900여 개를 절대 되돌리거나 커밋하지 않는다.
- 테스트·빌드·게이트 명령은 사용자가 그 턴에 요청할 때만 실행한다.

작업 순서는 의존성이 결정한다. 현재 판단으로는 durable substrate 번들링 →
read 도구 결합 → 세션 수명주기 → 설치/복구 검증 순이지만, 조사 결과가 다르면
근거와 함께 순서를 바꾼다.
```

---

## 왜 PLUGIN_ALPHA인가

"완벽한 아키텍처"를 목표로 삼으려면 끝나는 지점이 기계적으로 판정 가능해야
합니다. 저장소는 이미 그 단계를 정의해 두었습니다
(`manifests/acceptance_matrix.yaml:4-137`).

| 수준 | 범위 | 이번 목표 |
|---|---|---|
| `SPEC_BUNDLE` | 계약·스키마·워크플로 문서. 런타임 주장 없음 | 현재 위치 |
| `PLUGIN_ALPHA` | 설치 가능하고 FORGE/EVOLVE 상태가 동작하는 플러그인 | **목표** |
| `EVOLUTION_MVP_50` | 50문서 코퍼스, 검증된 evaluator, QD 진화 | 이후 |
| `PILOT_200` | 200문서, 외부 선행연구, 독립 복제 | 이후 |
| `PRODUCTION_2000` | 2000문서, 부하·보안·SLO | 이후 |

`EVOLUTION_MVP_50` 이상은 **라이선스 코퍼스, 검증된 evaluator, 통계 정책, 공급자
자격**처럼 코드로 닫히지 않는 외부 조건을 요구합니다. 지금 그걸 목표로 걸면
영원히 끝나지 않습니다.

반면 `PLUGIN_ALPHA`의 15개 게이트는 전부 이 저장소 안에서 판정 가능합니다.
그리고 그 정의 자체가 "완벽한 아키텍처"의 실질입니다 — 동작하는 FORGE 상태,
영속 저장소, 샌드박스, 복구, 설치 수명주기.

## 현재와 목표의 거리

현재 디스크와 설치 목록 기준입니다. 소스가 바뀐 뒤 다시 실행하지 않은 게이트는
통과로 간주하지 않습니다.

| PLUGIN_ALPHA 게이트 | 현재 |
|---|---|
| `manifest_and_skill_validation` | 소스 완료·미판정 — manifest는 skills/hook/MCP 경로를 선언하고 각 대상은 fail-closed source에 결합됨 |
| `fresh_install_matrix` | 자동화 소스 완료·미판정 — `4.0.0+codex.20260814202914` 설치본은 enabled지만 현재 소스 payload는 아직 설치·판정되지 않음 |
| `pathless_cli` | 부분 — Node dispatcher는 installed `dist/cli.mjs`를 직접 import하고 Python은 absolute-only; 호스트의 MCP launch 계약은 미확정 |
| `mcp_unavailable_cli_fallback` | 소스는 부분 — Node 진단 2개 bound, 나머지 11개는 사유와 함께 UNAVAILABLE. 현재 enabled cache는 구버전 `map.query`를 무권한으로 bind하므로 미달 |
| `hook_disabled_degraded_mode` | 소스 완료·미판정 — hook 부재와 비활성 상태를 구분하는 설치 lifecycle 자동화는 있으나 현재 설치본에서 실행되지 않음 |
| `sqlite_wal_crash_recovery` | **미달** — canonical durable session composition이 없음 |
| 나머지 9개 (evaluator/holdout/novelty/promotion 계열) | 미달 — EVOLVE 실행 경로 없음 |

가장 큰 단절은 세 가지입니다.

1. **durable session composition이 없습니다.** D01 SQLite, D03 CAS, E01 Ledger,
   F01 classification, F02 reducer와 F03 admission은 존재하지만 F02 artifact
   retention, E01 expected-head append, F01 replay read와 F04 composition 계약이
   아직 닫히지 않았습니다.
2. **authorized read binding이 없습니다.** 상태와 건강 진단 2개만 안전하게
   Node-local로 제공됩니다. 나머지 11개 도구는 canonical producer 또는 T01
   local-stdio authorization이 연결되기 전까지 UNAVAILABLE이어야 합니다.
3. **현재 소스를 설치본으로 판정하는 lifecycle이 아직 닫히지 않았습니다.**
   clean-clone payload builder와 installed-copy automation 소스는 작성됐지만,
   current payload의 build/install 결과는 아직 판정되지 않았고 upgrade/rollback
   계약은 별도 SPEC_GAP입니다. 특히 enabled cache의 구버전
   `dist/mcp-server.mjs`는 현재
   fail-closed source와 달리 `foundry.map.query`를 인증 없이 bind하므로,
   재생성·교체 전에는 현재 설치본을 안전한 후보로 취급할 수 없습니다.

## 이 목표가 요구하지 않는 것

범위를 지키기 위해 명시합니다.

- 23개 워크플로 350노드 실행
- Evolution 엔진 실제 구동, Shinka 어댑터
- 11개 retrieval lane 완성 (3개 유지)
- 라이선스 코퍼스, hidden holdout, 복제 서비스
- UI 서버, 프로덕션 배포

이것들은 `EVOLUTION_MVP_50` 이후 단계입니다. 목표에 섞으면 판정 불가능해집니다.

## 알려진 SPEC_GAP

목표를 시작하기 전에 사용자가 알아야 할 미해결 충돌입니다. 자세한 내용은
[충돌 기록](20260814-mvp-runtime-binding-authority-conflicts.md)에 있습니다.

가장 근본적인 것은 `MASTER_SPEC.md:43`입니다.

> Reference plugin executables remain fail-closed stubs.

동작하는 런타임 자체가 이 문장과 충돌합니다. `PLUGIN_ALPHA`를 목표로 삼는다는
것은 **이 문장을 개정하기로 결정한다는 뜻**입니다. 릴리스 수준을
`SPEC_BUNDLE`에서 올리는 것은 제품 소유자의 권한이며, 구현이 스스로 승격할 수
없습니다.

따라서 목표 시작 시 다음 중 하나를 먼저 정해야 합니다.

- **갈래 A**: `MASTER_SPEC.md`의 stub 문장, `acceptance_matrix`의
  `status_of_this_bundle`, `compatibility_matrix`의 `expected_top_level`과
  `runtime_capabilities`를 함께 개정한다. 그러면 나머지는 구현 문제가 된다.
- **갈래 B**: 개정하지 않는다. 그러면 `PLUGIN_ALPHA`는 목표가 될 수 없고,
  현재 상태를 되돌려야 한다.

A를 고른다면 자기권한 확대를 막는 최소 장치가 필요합니다. 매니페스트를 소유한
패키지가 없으므로, 매니페스트 밖의 권위 문서가 A01에 제한된 관리권을 부여하고
작성자와 승인자를 분리하는 방식이 안전합니다.

## Authority grant

- Authority ID: `PLUGIN_ALPHA_CUTOVER_20260815`
- Grantor: repository owner
- Authorized implementation target: `PLUGIN_ALPHA`
- Current qualified-status ceiling: `SPEC_BUNDLE`

This decision authorizes only the following shared-contract amendments:

1. Qualify the fail-closed-stub rule in `MASTER_SPEC.md` so that it does not
   prohibit an executable `PLUGIN_ALPHA` candidate.
2. Retain `status_of_this_bundle: SPEC_BUNDLE` during implementation.
3. Add the `installed_dist_execution_automation` gate, bringing the
   `PLUGIN_ALPHA` gate count to fifteen.
4. Add exactly these candidate `runtime_capabilities` identifiers:
   `installed_plugin_cli_execution`, `installed_plugin_mcp_execution`,
   `bundled_python_runtime_execution`, `runtime_payload_integrity_verification`,
   `workspace_path_confinement`, and `degraded_runtime_diagnostics`.
5. Add `dist`, `runtime`, `scripts`, and `src` to the existing
   `expected_top_level` list.
6. Assign custodial write scope for `docs/decisions/**` to A01.

For this candidate, `bundled_python_runtime_execution` means that the plugin
ships the exact Python application closure but uses an explicitly configured
absolute Python 3.12+ interpreter; it does not mean that an interpreter tree is
copied into the plugin. `runtime_payload_integrity_verification` means a
point-in-time closed-inventory/hash check for installation damage and drift. It
is not a privilege boundary against the same local user concurrently rewriting
their own plugin payload and configuration. Neither identifier authorizes a
large protected runtime copy or recursive ACL migration on the normal path.

This authority does not authorize a `PLUGIN_ALPHA` release claim, a positive
host-cell status, a passing gate without executable evidence, a new release
status, or a broader runtime/protocol contract.

X01 may implement the plugin and submit evidence. X01 may not accept its own
evidence, mark a `PLUGIN_ALPHA` gate as passing solely on its own authority, or
change `status_of_this_bundle`.

A01 may maintain the decision record and record an accepted status transition.
A01 does not thereby gain authority to manufacture or accept implementation
evidence. Every gate acceptance requires an acceptor independent of the
implementation author. The final `status_of_this_bundle` transition requires
all fifteen independently accepted gate records.

`installed_dist_execution_automation` is distinct from `fresh_install_matrix`.
The former requires checked-in automation to execute the installed copies of
`bin/efoundry.mjs`, the MCP command declared by `.mcp.json`, and every installed
hook command that loads `dist/`, while refusing repository-source, `PYTHONPATH`,
or editable-install fallbacks. The latter records host and lifecycle coverage.
Manual invocation cannot satisfy either gate by itself.

## Active implementation blocker

Durable session composition is blocked by the F02/F03 artifact-retention and
Kernel integration ownership gap recorded in
[`20260815-plugin-alpha-durable-session-gap.md`](20260815-plugin-alpha-durable-session-gap.md).
Installed read-model binding is separately bounded by the local-stdio
authorization and artifact-projection gaps recorded in
[`20260815-plugin-alpha-read-binding-gap.md`](20260815-plugin-alpha-read-binding-gap.md).
Upgrade and rollback are additionally blocked on the host lifecycle ownership
and activation contract recorded in
[`20260815-plugin-alpha-upgrade-rollback-gap.md`](20260815-plugin-alpha-upgrade-rollback-gap.md).
The remaining independent payload, pathless-runtime, truthful availability,
and lifecycle work continues without treating that gap as resolved.
