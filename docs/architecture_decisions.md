# Architecture Decision Record

## ADR-001 — Claim-first, not paper-first

**Status:** Accepted

논문은 서지·문맥 단위이고 Claim은 추론 단위다. Paper summary를 graph edge로 직접 사용하지 않는다. 모든 promoted Claim은 atomic statement, ScopeVector, author stance, evidence layer, immutable source span을 가진다.

**Rejected:** paper-level RAG as canonical evidence.

## ADR-002 — Coverage-first UI

**Status:** Accepted

첫 출력은 confidence score가 아니라 support/counter/null/boundary/method/unsearched coverage다. “0편”과 “검색하지 않음”을 분리한다.

## ADR-003 — Four-Graph separation

**Status:** Accepted

- E: 원문·실험에 앵커된 증거
- R: 가설·메커니즘·논증
- D: 에이전트/인간 심의
- X: 검증 계획·실험·시뮬레이션·형식 검증·벤치마크·코드 실행

추론 또는 비경험적 실행 결과를 직접 empirical evidence로 승격하지 않는다.

## ADR-004 — PostgreSQL canonical store

**Status:** Accepted for MVP

PostgreSQL + pgvector + object store를 source of truth로 사용한다. DuckDB/Parquet와 NetworkX는 분석 projection이다. Neo4j/Kùzu/RDF store는 실제 query benchmark가 필요성을 입증할 때 추가한다.

## ADR-005 — GROBID + Docling complementary ingest

**Status:** Accepted

GROBID는 scholarly structure/citation TEI, Docling은 page layout/table/formula/image provenance 보완에 사용한다. 한 parser의 출력을 무조건 truth로 취급하지 않고 reconciliation/QC를 둔다.

## ADR-006 — Asymmetric parliament, no majority promotion

**Status:** Accepted

Defender, Prosecutor, Method Auditor, Scope Auditor가 서로 다른 evidence ACL과 loss를 가진다. Method Auditor는 measurement incompatibility에 veto를 가진다. majority vote는 promotion authority가 아니다.

## ADR-007 — Deterministic edges

**Status:** Accepted

hash, count, dedupe, routing, dependency clustering, schema validation, completeness, gate evaluation은 code로 한다. LLM을 plumbing에 쓰지 않는다.

## ADR-008 — Provider-neutral kernel

**Status:** Accepted

RunSpec, artifacts, events, capabilities, approvals, receipts, replay는 EF kernel이 소유한다. Codex, Claude Code, OpenAI Agents SDK, Anthropic Agent SDK는 adapters다.

## ADR-009 — Concurrency bounds

**Status:** Accepted as initial safety profile

- write-heavy default ≤ 4
- read-heavy default ≤ 8
- hard cap 16 unless benchmark and operations approval

Agent count는 성능 지표가 아니다. shared contract/resource가 있으면 serial edge를 둔다.

## ADR-010 — Tiered corpus processing

**Status:** Accepted

- Tier 0: metadata/structure/index for all
- Tier 1: high-recall claim candidates
- Tier 2: query-activated precision extraction

전체 2,000편에 고가 정밀 추출을 일괄 적용하지 않는다.

## ADR-011 — Scope-aware contradiction

**Status:** Accepted

`TRUE_CONTRADICTION`은 construct, direction, scope overlap, method comparability를 통과한 경우에만 허용한다. 나머지는 boundary/method/temporal/different-question으로 분류한다.

## ADR-012 — Evidence vector, not prestige score

**Status:** Accepted

최종 UI는 directness, design, measurement validity, precision, replication, independence, scope match, extraction confidence를 분리한다. 내부 retrieval scalar는 설명 가능한 파생치일 뿐이다.

## ADR-013 — Falsifier required at registration

**Status:** Accepted

반증조건을 만들 수 없는 아이디어는 Inbox에 남는다. Council은 rhetoric을 testable hypothesis로 위장하지 않는다.

## ADR-014 — ValidationTarget as an optional falsification screen

**Status:** Accepted

가설이 등록된 `ValidationTargetManifest`의 변수·행동·입출력 계약으로 표현 가능하고, 실행 결과가 판별력을 가질 때만 `ValidationPlan`을 만든다. 대상은 시뮬레이션 모델, 분석 파이프라인, 형식 솔버, 벤치마크 하네스, 실험 플랫폼, 외부 서비스 또는 사용자 정의 실행기일 수 있다. `EXECUTION_COMPATIBLE`은 `EMPIRICALLY_SUPPORTED`가 아니다.

## ADR-015 — Replay levels

**Status:** Accepted

- strict replay: canonical inputs/version/model where possible, exact artifacts/events
- semantic replay: provider drift가 있을 때 schema/gate/decision differences report

재현 불가능한 floating alias를 최종 manifest에 남기지 않는다.

## ADR-016 — Gold evaluation before scale

**Status:** Accepted

50편 gold에서 grounding/false-claim/retrieval/council 검증 전 2000편 확장을 금지한다.

## ADR-017 — Domain-neutral core with versioned DomainPacks

**Status:** Accepted

Core schemas, workflows, prompts, gates, and provider adapters may not require any one scientific or professional domain. Domain vocabulary, measurement constructs, scope axes, method comparability rules, evidence hierarchies, and optional validation adapters are supplied through versioned `DomainPack` and `ValidationTargetManifest` plug-ins. Core upgrades and domain-pack upgrades remain independently versioned and replayable.

## ADR-018 — Epistemic Foundry product language

**Decision:** Adopt Epistemic Foundry as the product name and the module taxonomy Foundry Kernel, Claim Forge, Epistemic Atlas, Evidence Parliament, Aporia Engine, Noetic Ledger, Validation Bay, and Hypothesis Passport.

**Reason:** The architecture is broader than a graph database or multi-agent debate. The names describe durable responsibilities without making a truth guarantee.

## ADR-019 — Search receipts before absence or novelty claims

**Decision:** Every retrieval lane emits SearchLaneReceipt, including zero, blocked, and failed states. RetrievalRun issues a bounded completeness certificate.

**Reason:** “Not found” otherwise collapses search failure, unsearched scope, and genuine zero results.

## ADR-020 — Append-only lifecycle and targeted invalidation

**Decision:** Claim, Evidence, Passport, policy, and human decisions use immutable revisions and lifecycle events. Updates traverse dependency edges and trigger targeted reassessment.

**Reason:** In-place edits destroy the ability to reproduce past decisions and to evaluate retractions.

## ADR-021 — Corpus and tool output are hostile by default

**Decision:** Source documents, metadata, tool output, and prior-agent text are untrusted data and may not alter instructions or capabilities.

**Reason:** Research corpora can contain active content, prompt injection, poisoned citations, or accidental instruction-like text.

## ADR-022 — Human decisions do not overwrite machine artifacts

**Decision:** Approvals, rejections, overrides, and appeals are append-only HumanDecision/ApprovalRecord objects.

**Reason:** Accountability requires seeing both the machine recommendation and the accountable human action.

## ADR-023 — ActionIntent and EffectReceipt for all side effects

**Decision:** Controlled execution requires exact-hash ActionIntent and a reconciled EffectReceipt.

**Reason:** A model request, action authorization, and observed external effect are different facts.

## ADR-024 — Breaking changes require SchemaMigration

**Decision:** No breaking schema/API change without compatibility classification, fixtures, transforms, review, and migration event.

**Reason:** Long-lived evidence graphs must remain replayable across contract evolution.

## ADR-025 — Multidimensional calibration and decision stability

**Decision:** Report separate confidence dimensions and run registered perturbation analysis; do not expose one overall scientific confidence score.

**Reason:** Grounding, method validity, independence, causal identification, and stability are not interchangeable probabilities.

## ADR-026 — 144-lens assurance, not 144-agent voting

**Decision:** Final architecture review uses 144 independent questions in 12 families, executed concurrently by deterministic checks where possible.

**Reason:** More agents do not create independent truth. Diverse, explicit assurance questions provide auditable coverage without consensus theater.

## ADR-027 — Seven canonical workflows

**Decision:** Canonical workflows are ingest, extraction, retrieval, deliberation, validation, update/reassessment, and evaluation/release.

**Reason:** Retrieval, lifecycle reassessment, and release assurance require first-class DAGs rather than hidden steps inside deliberation.

## ADR-028 — Release provenance and final-byte manifest

**Decision:** Generate manifests and checksums only after content finalization; verify archive extraction, CRC, duplicates, and per-file hashes.

**Reason:** A checksum generated before later edits does not attest the delivered package.

## ADR-029 — Explicit conditional deployment decisions

**Decision:** Credentials, licensing, infrastructure, signing, governance roles, and production corpus are tracked as CONDITIONAL, not silently defaulted.

**Reason:** Architecture completeness and deployment readiness are distinct claims.

## ADR-030 — Specification validation is not product validation

**Decision:** Use separate readiness levels: SPEC_BUNDLE, MVP_50, PILOT_200, PRODUCTION_2000.

**Reason:** A coherent specification cannot demonstrate parser accuracy, scientific validity, security, or scale without implementation and data.
