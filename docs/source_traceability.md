# Source Traceability

Access date: 2026-07-25

This document separates **design input**, **official capability confirmation**,
**standards**, and **research evidence**. Social-media performance claims are
not release requirements, and no external source may override a canonical
schema without an ADR and migration.

## User-provided design sources

| Source | Adopted design asset | Explicitly not adopted as fact |
|---|---|---|
| `붙여넣은 마크다운(1)(21).md` | Claim/Evidence contract, coverage-first reasoning, Four-Graph, asymmetric parliament, provenance, retrieval lanes, evaluation | benchmark numbers or scientific-agent performance as product guarantees |
| `붙여넣은 텍스트 (2)(3).txt` | real-edge test, fan-out/fan-in, layered aggregation, expected-node checks | 1,000-agent and exact latency claims |
| `붙여넣은 텍스트 (3)(2).txt` | node/edge schemas, deterministic plumbing, verifier edge, model tiering, bounded cycles | “zero-token orchestration” as a total-cost claim and unverified product syntax |
| `붙여넣은 텍스트 (4)(1).txt` | specification freeze, bounded concurrency, worktrees, maker/reviewer/integrator, checkpoints, stop conditions | 10+ hour autonomy as a guaranteed outcome |
| `붙여넣은 텍스트 (5).txt` | maker-checker, parallel factor analogy, explicit budget and gates | finance/alpha claims and commercial-runtime claims |

## Official execution documentation

| Topic | Official source | Architectural use |
|---|---|---|
| Codex `AGENTS.md` | `https://developers.openai.com/codex/agent-configuration/agents-md` | layered repository instructions |
| Codex subagents | `https://developers.openai.com/codex/subagents` | bounded parallel delegation and explicit return contracts |
| Codex skills | `https://developers.openai.com/codex/skills-and-plugins` | reusable project workflow packaging |
| OpenAI Agents SDK | `https://openai.github.io/openai-agents-python/` | optional provider adapter and tracing; never canonical state |
| Claude Code agents | `https://code.claude.com/docs/en/agents` | role/tool/context isolation and bounded parallel work |
| Claude Code worktrees | `https://code.claude.com/docs/en/worktrees` | parallel write isolation |
| Claude Code hooks | `https://code.claude.com/docs/en/hooks` | deterministic lifecycle guardrails |
| Anthropic Agent SDK | `https://docs.anthropic.com/en/docs/agents-and-tools/claude-code/sdk` | optional provider adapter; never canonical state |

Provider features are treated as adapter capabilities. Availability, syntax,
quotas, pricing, and model identifiers are deployment-time facts and must be
verified by the adapter conformance suite.

## Parsing, storage, provenance, and release standards

| Topic | Source | Decision |
|---|---|---|
| JSON Schema Draft 2020-12 | `https://json-schema.org/draft/2020-12` | canonical JSON contract dialect |
| GROBID | `https://grobid.readthedocs.io/` | scholarly structure, TEI, citation parsing |
| Docling | `https://docling-project.github.io/docling/` | layout/table/formula/image extraction and source provenance |
| pgvector | `https://github.com/pgvector/pgvector` | PostgreSQL-integrated vector projection |
| PROV-O | `https://www.w3.org/TR/prov-o/` | optional provenance interchange mapping |
| SHACL | `https://www.w3.org/TR/shacl/` | optional RDF projection validation |
| SLSA provenance | `https://slsa.dev/provenance` | release artifact provenance model and threat framing |

PostgreSQL remains the canonical transactional implementation target in the
MVP. Vector, graph, RDF, and search engines are replaceable projections.

## Scientific-agent and claim research

| Work | Source | Use and limitation |
|---|---|---|
| PaperQA2 | `https://arxiv.org/abs/2409.13740` | evidence-grounded literature QA and contradiction motivation; not general proof |
| SciAgents | `https://arxiv.org/abs/2409.05556` | knowledge-graph plus multi-agent hypothesis pattern |
| CLAIM-BENCH | `https://aclanthology.org/2025.ijcnlp-long.127/` | claim identification and distributed grounding remain difficult |
| ClaimCheck | `https://aclanthology.org/2025.findings-acl.504/` | evidence-grounded critique limitations |
| MAST | `https://arxiv.org/abs/2503.13657` | multi-agent failure taxonomy motivation |

Preprints and benchmarks motivate tests; they do not establish this
architecture's accuracy. Epistemic Foundry must earn its own results on the
gold corpus, adversarial set, time-sliced backtest, and production monitoring.

## Traceability rule

Every external proposition that creates or changes a MUST requirement records:

1. source and access date;
2. exact adopted proposition;
3. source class: official, standard, peer-reviewed, preprint, or design input;
4. known limitation and local validation plan;
5. affected ADR, invariant, schema, workflow node, and acceptance gate.

A changed external fact triggers an adapter or evidence reassessment. It cannot
silently mutate canonical semantics.
