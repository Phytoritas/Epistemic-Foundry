# AGENTS.md — Epistemic Foundry v4

## 0) 최우선 — 실제 모델 구현 우선, 통제 계층 최소화

이 저장소의 최우선 산출물은 **과학적으로 타당하고 실제 runtime이 소비할 수
있는 모델 코드와 데이터 계약**이다. 문서, schema, registry, manifest, index,
receipt, gate, provenance, audit 또는 proof artifact의 양을 늘리는 것 자체는
진척이 아니다. 이 절은 아래의 repository 운영 절보다 우선하며 `tomics/`를
포함한 전체 작업에 적용한다.

- 과학적 무결성, 원본 데이터 불변성, 비가역 작업의 안전성,
  권위·단위·상태·flux 경계는 유지한다. 그 밖의 통제 구조는 구현에 필요한
  최소치만 둔다.
- 현재 실행 코드가 실제로 소비하는 interface와 serialization을 기본 정본으로
  삼는다. 과학적 결함이 없는 runtime 계약을 새 control-plane 형식에 맞추려고
  우회하거나 복제하지 않는다.
- 기존 interface 하나로 표현 가능한 정보를 위해 평행 schema, 중복 manifest,
  index, adapter, receipt, gate, acceptance table 또는 증명 산출물을 새로 만들지
  않는다. 필요한 경우 기존 계약 하나를 좁고 명시적으로 확장한다.
- Pro의 제안이 현재 코드와 맞지 않으면 Pro 문구에 맞추려고 계층을 추가하지
  않는다. 실제 byte와 data flow를 기준으로 가장 단순한 실행 가능 계약으로
  교정하고, 비동등한 과학적 선택만 다시 자문한다.
- 실행·test·promotion 권한이 닫혀 있다는 사실은 코드, fixture 또는 unexecuted
  binding의 **작성 자체**를 막지 않는다. 실행 권한과 구현 권한을 혼동하지
  않는다.
- 다음 항목만 해당 구현 경계를 fail-closed로 막을 수 있다: 원문에 없는
  과학식·값·단위·초기조건의 발명, 원본/권위 데이터 훼손, 상태·flux 소유권
  위반, 비가역 작업, 또는 명시적으로 필요한 실행 권한의 부재. 통제 산출물의
  부재만으로 구현을 장기간 정지시키지 않는다.
- 순서는 **모델 코드와 runtime-native 계약 → 필요한 최소 control-plane 연결 →
  사용자가 요청한 실행·검증**이다. 사용자가 명시적으로 요구하지 않은 receipt,
  evidence packet, validation artifact는 만들거나 개발 선행조건으로 삼지 않는다.

모든 에이전트는 새 통제 표면을 발명하기 전에 기존 runtime 계약으로 문제를 풀
수 있는지 먼저 확인하고, 가능한 경우 더 작은 구조를 선택한다.

## Authority

Read and obey in order:

1. `MASTER_SPEC.md`
2. `manifests/development_manifest.yaml`
3. `manifests/acceptance_matrix.yaml`
4. `manifests/product_invariants.yaml`
5. applicable `schemas/*.schema.json` and `workflows/*.workflow.yaml`
6. `manifests/role_registry.yaml`
7. this file
8. work-package-local notes

When a lower source conflicts with a higher source, stop with `SPEC_GAP`.
Never invent a missing shared contract.

## Current maturity

This bundle is a **SPEC_BUNDLE / REFERENCE_BLUEPRINT**. Do not claim that the
plugin runtime, evolutionary search, Shinka backend, hidden holdout,
replication service, hooks, MCP server, UI, parser stack, security properties,
or performance targets are implemented merely because their contracts exist.

## Constitution

- Foundry Kernel and Noetic Ledger own canonical state, authority, receipts,
  gates and replay.
- Plugin shells, hooks, skills, UIs, model SDKs, and optional search backends
  are adapters.
- Source evidence, RunSpec, policy, evaluator, holdout, promotion gates, and
  release state are never mutable genomes.
- Evolution may propose; it may not certify itself.
- Novelty, fitness, evaluator survival, and model confidence are distinct from
  scientific support.
- A promoted Claim resolves to immutable source evidence.
- An Insight requires scope, prediction, falsifier, and searched-scope
  accounting.
- Counter, null, boundary, method, leakage, and OOD lanes remain visible.
- Dependency clusters prevent evidence-count inflation.
- Induction, deduction, abduction, causal identification, simulation, and
  empirical observation remain typed and separate.
- Scalar fitness cannot override hard gates or become the promotion authority.
- Evaluator bundles are immutable within a run.
- Holdouts remain access-controlled; leakage creates invalidation, not a score.
- Adaptive search requires a sequential-testing ledger, multiplicity policy,
  and selective-inference report.
- Quality-diversity archives preserve negative knowledge, failed replications,
  unsafe candidates, and minority lineages where policy permits.
- Prompt and evaluator mutations are quarantined future-run proposals.
- Majority vote cannot promote.
- Method/safety veto and failed deterministic gates constrain promotion.
- Every effect and completion claim requires resolving receipts.
- `UNDERDETERMINED`, `UNASSESSED`, `BLOCKED`, `INVALIDATED`, and
  `REPLICATION_FAILED` are valid truthful outcomes.

## Work-package protocol

1. Select the earliest dependency-ready package from
   `manifests/development_manifest.yaml`.
2. Read exact dependencies, write scope, criteria, checks, and stop conditions.
3. Inspect the current repository and preserve unrelated user changes.
4. Freeze shared contracts before parallel work.
5. Use only bounded roles from `manifests/role_registry.yaml`.
6. Parallel writers require disjoint scopes and isolated worktrees; default
   implementation concurrency is four.
7. Implement the smallest change satisfying the package contract.
8. Use deterministic code for routing, transforms, hashing, policy, statistics,
   archive bookkeeping, state transitions, and gates.
9. Use model judgment only for bounded semantic tasks with typed input/output.
10. Run required checks and capture command outputs as immutable artifacts.
11. Dispatch a reviewer who did not author the change.
12. Integrate only after all non-waivable criteria pass.
13. Emit a `WorkPackageReport`; never substitute narrative confidence.

## Evolution work

Before running or implementing an evolution node, verify:

- immutable `EvolutionRunSpec` and `EvaluatorBundle`;
- genome schema and compatibility rules;
- parent-selection and model-routing receipts;
- novelty state including `UNASSESSED` and `FAILED`;
- hard validation cascade and budget;
- hidden/OOD access boundary;
- archive and island policy;
- complete candidate reconciliation;
- adaptive-search statistical policy;
- stop certificate conditions.

The same context may not generate a candidate, reveal the hidden holdout, alter
the evaluator, and promote that candidate.

## ShinkaEvolve adapter

The adapter is optional. Pin an exact upstream revision/package digest,
license record, configuration, and backend qualification result. Treat raw
Shinka `combined_score`, `correct`, novelty, island, archive, and bandit state
as advisory backend observations. Map them through Foundry contracts before
they can influence a Passport or promotion.

## Stop conditions

Stop with a typed blocker when:

- a required source, evaluator, holdout, corpus license, credential, or
  infrastructure is unavailable;
- a shared contract must change outside the current write scope;
- hidden-test leakage or evaluator mutation is detected;
- multiplicity or selective-inference policy is undefined;
- candidate/result counts cannot be reconciled;
- the only path requires fake evidence, silent fallback, or weakened gates;
- repeated review exposes an unresolved product or scientific decision.

## Web ChatGPT Git writer contract

When the Web ChatGPT Git writer app is selected, Web ChatGPT is the primary autonomous coding agent.
It must translate the user's natural-language request into a complete implementation without waiting
for another orchestrator. It must read this file, investigate and reproduce material findings, change
every required source and directly related test, critically inspect the complete diff, run all applicable
checks, fix failures, commit and push only chatgpt/*, create or update a pull request, and squash-merge it
after required checks pass. It must not impose arbitrary file-count or scope limits.
It must never push directly to main, force-push, delete branches, expose secrets, weaken tests,
or modify protected repository, workflow, credential, or writer files.
