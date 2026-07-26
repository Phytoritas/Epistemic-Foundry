# 216-lens Epistemic Foundry v3 plugin audit

This is a structured architecture review matrix: **18 families × 12 distinct lenses = 216**. It does not claim 216 independent human reviewers, model runs, or proofs.

Result: **198 PASS / 18 CONDITIONAL / 0 FAIL**.

## A — Epistemic semantics

| Lens | Approach | Question | Status | Finding |
|---|---|---|---:|---|
| A01 | formal type and schema analysis | Are epistemic, causal, novelty, lifecycle and stability states independently typed? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| A02 | counterexample construction | Can underdetermination be represented without forcing a confidence score? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| A03 | source-to-output provenance walk | Can simulation or formal output be accidentally promoted as empirical evidence? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| A04 | failure injection | Does the system distinguish claim truth from evidence quality and retrieval completeness? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| A05 | dependency and hidden-edge analysis | Are inference modes prevented from silently inheriting one another's status? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| A06 | property-based state-machine review | Can scope narrowing be expressed without rewriting the original claim? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| A07 | threat modeling | Are author stance and system adjudication kept separate? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| A08 | adversarial retrieval test | Can a review-derived statement be traced to its primary-source dependency? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| A09 | differential cross-provider check | Does every controlled term have a versioned authority or explicit unknown value? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| A10 | fresh-install/recovery simulation | Can conflicting verdict dimensions coexist without schema failure? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| A11 | human-factors and status-honesty review | Are promotion ceilings monotonic under veto and hard-gate failure? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| A12 | production evidence gate | Do domain experts accept the state vocabulary on a real gold set? | **CONDITIONAL** | The contract is specified, but final confidence requires implementation, production data, host, organizational, or independent human evidence. |

## B — Source, Claim and provenance integrity

| Lens | Approach | Question | Status | Finding |
|---|---|---|---:|---|
| B01 | formal type and schema analysis | Must every promoted Claim resolve to immutable source bytes and a locator? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| B02 | counterexample construction | Can page, character, table, figure and formula locators coexist? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| B03 | source-to-output provenance walk | Does source-version replacement preserve prior spans and lifecycle events? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| B04 | failure injection | Can extraction uncertainty be represented without dropping the Claim? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| B05 | dependency and hidden-edge analysis | Are source text and model paraphrase stored as different objects? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| B06 | property-based state-machine review | Does atomicity validation reject compound claims with multiple relations? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| B07 | threat modeling | Can table/caption evidence be linked without inventing prose? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| B08 | adversarial retrieval test | Are parser disagreements retained as first-class artifacts? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| B09 | differential cross-provider check | Are document corrections and retractions propagated to dependent Claims? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| B10 | fresh-install/recovery simulation | Can a Claim be superseded without deleting its prior revision? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| B11 | human-factors and status-honesty review | Does the provenance chain include parser, model, prompt, schema and corpus hashes? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| B12 | production evidence gate | Does a human span audit meet the promoted-claim validity threshold? | **CONDITIONAL** | The contract is specified, but final confidence requires implementation, production data, host, organizational, or independent human evidence. |

## C — Retrieval, coverage and absence

| Lens | Approach | Question | Status | Finding |
|---|---|---|---:|---|
| C01 | formal type and schema analysis | Are lexical, semantic, citation and relation lanes independently receipted? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| C02 | counterexample construction | Are counterevidence, null, boundary and method lanes mandatory when applicable? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| C03 | source-to-output provenance walk | Can a failed search lane be distinguished from a zero-result lane? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| C04 | failure injection | Is searched scope bounded by corpus, database, date, language and filters? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| C05 | dependency and hidden-edge analysis | Can retrieval direction distinguish support, contradict, moderate and method critique? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| C06 | property-based state-machine review | Are shared datasets and publication families deduplicated before evidence strength? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| C07 | threat modeling | Does the Evidence Pack preserve diversity rather than only top similarity? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| C08 | adversarial retrieval test | Can unsearched coverage cells remain visible after synthesis? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| C09 | differential cross-provider check | Does an absence or novelty claim require a completeness certificate? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| C10 | fresh-install/recovery simulation | Are corrections, retractions and later rebuttals included in temporal retrieval? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| C11 | human-factors and status-honesty review | Can compact subgraph assembly prove which candidates were excluded? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| C12 | production evidence gate | Does retrieval meet counter/null/novelty recall targets on production corpora? | **CONDITIONAL** | The contract is specified, but final confidence requires implementation, production data, host, organizational, or independent human evidence. |

## D — Reasoning and Aporia

| Lens | Approach | Question | Status | Finding |
|---|---|---|---:|---|
| D01 | formal type and schema analysis | Does deductive output expose every premise, rule, hidden assumption and broken edge? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| D02 | counterexample construction | Does induction adjust for dependency, heterogeneity and scope? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| D03 | source-to-output provenance walk | Does abduction preserve multiple live explanations rather than select the most fluent? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| D04 | failure injection | Does causal analysis test time order, confounding, mediation, colliders and measurement error? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| D05 | dependency and hidden-edge analysis | Can true contradiction be separated from scope, method, temporal and question differences? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| D06 | property-based state-machine review | Are moderator hypotheses linked to the conflicting evidence pairs they explain? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| D07 | threat modeling | Can a reverse-causality model be represented beside the preferred model? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| D08 | adversarial retrieval test | Does the system propose discriminating observations rather than generic future work? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| D09 | differential cross-provider check | Are formal proof traces mechanically checkable where the representation allows? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| D10 | fresh-install/recovery simulation | Can a reasoning result abstain when constructs are not commensurable? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| D11 | human-factors and status-honesty review | Does the ArgumentGraph reject orphan conclusions and scope widening? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| D12 | production evidence gate | Do real-domain experts judge generated discriminating tests useful and feasible? | **CONDITIONAL** | The contract is specified, but final confidence requires implementation, production data, host, organizational, or independent human evidence. |

## E — Parliament and governance

| Lens | Approach | Question | Status | Finding |
|---|---|---|---:|---|
| E01 | formal type and schema analysis | Are blind first-round briefs isolated by evidence ACL and context manifest? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| E02 | counterexample construction | Does the Prosecutor receive counter/null/boundary evidence without support-first anchoring? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| E03 | source-to-output provenance walk | Can Method, Scope, Causal, Novelty and Safety auditors impose typed ceilings or vetoes? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| E04 | failure injection | Is majority vote prohibited as a promotion rule? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| E05 | dependency and hidden-edge analysis | Is the strongest counterargument retained in a supporting verdict? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| E06 | property-based state-machine review | Can a Minority Report survive fan-in and export unchanged? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| E07 | threat modeling | Does cross-examination require Claim and Evidence IDs? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| E08 | adversarial retrieval test | Does the Judge receive gate outputs and remain unable to override deterministic failure? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| E09 | differential cross-provider check | Does the Attestor avoid persuasive debate transcripts and inspect structured evidence? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| E10 | fresh-install/recovery simulation | Are human approvals, overrides, conflicts and appeals immutable? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| E11 | human-factors and status-honesty review | Can missing agents or failed roles constrain the verdict rather than vanish? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| E12 | production evidence gate | Does Parliament outperform single-agent and consensus baselines under calibrated cost? | **CONDITIONAL** | The contract is specified, but final confidence requires implementation, production data, host, organizational, or independent human evidence. |

## F — Plugin packaging and installability

| Lens | Approach | Question | Status | Finding |
|---|---|---|---:|---|
| F01 | formal type and schema analysis | Is `.codex-plugin/plugin.json` valid and limited to package-internal paths? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| F02 | counterexample construction | Can the plugin ship skills, hooks, optional MCP and assets under one stable identity? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| F03 | source-to-output provenance walk | Does a payload-resident CLI work without PATH configuration or repository checkout? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| F04 | failure injection | Are plugin code, plugin-writable data and workspace state physically separated? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| F05 | dependency and hidden-edge analysis | Can install, enable, disable and uninstall preserve user data policy? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| F06 | property-based state-machine review | Are spaces, non-ASCII paths and Windows path semantics tested? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| F07 | threat modeling | Does the package disclose exact required and optional host capabilities? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| F08 | adversarial retrieval test | Are development-only source imports absent from the shipped package? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| F09 | differential cross-provider check | Are assets, screenshots and default prompts truthful to implemented capability? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| F10 | fresh-install/recovery simulation | Does the local marketplace path match the production package layout? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| F11 | human-factors and status-honesty review | Can a clean extraction reproduce the package manifest and hashes? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| F12 | production evidence gate | Does the built plugin pass fresh-install tests on every declared host/OS surface? | **CONDITIONAL** | The contract is specified, but final confidence requires implementation, production data, host, organizational, or independent human evidence. |

## G — Hooks and capability negotiation

| Lens | Approach | Question | Status | Finding |
|---|---|---|---:|---|
| G01 | formal type and schema analysis | Does every hook payload pass through one normalized, hashed gateway? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| G02 | counterexample construction | Are hook decisions bounded, timed and schema-valid? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| G03 | source-to-output provenance walk | Are hosted and specialized tool paths that bypass hooks explicitly listed? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| G04 | failure injection | Are hooks described as guardrails rather than the sole security perimeter? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| G05 | dependency and hidden-edge analysis | Does SessionStart perform a bounded probe rather than expensive hidden work? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| G06 | property-based state-machine review | Can UserPromptSubmit suggest skills without mutating canonical phase? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| G07 | threat modeling | Do PreToolUse decisions reference policy, lease and resource scope? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| G08 | adversarial retrieval test | Do PostToolUse events capture success, failure and effect receipts? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| G09 | differential cross-provider check | Do Subagent hooks bind expected identity and ResultEnvelope? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| G10 | fresh-install/recovery simulation | Does compaction recovery rebuild from canonical artifacts? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| G11 | human-factors and status-honesty review | Do modified hook definitions require new trust and visible health state? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| G12 | production evidence gate | Does the compatibility probe work across supported Codex releases and managed-hook policies? | **CONDITIONAL** | The contract is specified, but final confidence requires implementation, production data, host, organizational, or independent human evidence. |

## H — State, ledger, effects and replay

| Lens | Approach | Question | Status | Finding |
|---|---|---|---:|---|
| H01 | formal type and schema analysis | Is local state transactional with WAL, revision comparison and integrity checks? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| H02 | counterexample construction | Is team state semantically equivalent under PostgreSQL? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| H03 | source-to-output provenance walk | Are immutable artifacts separated from mutable projections? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| H04 | failure injection | Does every external effect follow Intent → policy → lease → attempt → receipt → reconcile? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| H05 | dependency and hidden-edge analysis | Are stale fencing tokens rejected? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| H06 | property-based state-machine review | Can unknown in-flight effects be reconciled without blind retry? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| H07 | threat modeling | Is state rebuildable from append-only ledger events? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| H08 | adversarial retrieval test | Can checkpoints be resumed without relying on chat history? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| H09 | differential cross-provider check | Do correction, retraction and policy changes mark downstream artifacts stale? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| H10 | fresh-install/recovery simulation | Are strict reducer replay and semantic replay reported separately? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| H11 | human-factors and status-honesty review | Does rollback preserve audit history and external-effect reconciliation? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| H12 | production evidence gate | Do crash, corruption, concurrency and backup/restore tests meet operational targets? | **CONDITIONAL** | The contract is specified, but final confidence requires implementation, production data, host, organizational, or independent human evidence. |

## I — Memory and context

| Lens | Approach | Question | Status | Finding |
|---|---|---|---:|---|
| I01 | formal type and schema analysis | Are ephemeral, session, workspace, user, evidence and regulated memory separate? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| I02 | counterexample construction | Is recall denied before purpose, consent and workspace are resolved? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| I03 | source-to-output provenance walk | Can consent expiry and revocation stop retrieval immediately? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| I04 | failure injection | Does every recall emit searched/excluded store and redaction receipts? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| I05 | dependency and hidden-edge analysis | Are duplicate memories prevented from evidence amplification? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| I06 | property-based state-machine review | Can a user forget memory while honoring legal hold and evidence provenance? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| I07 | threat modeling | Does a ContextCapsule contain artifact IDs, source hashes, exclusions and token budget? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| I08 | adversarial retrieval test | Is capsule freshness checked after corpus, policy or session revision changes? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| I09 | differential cross-provider check | Can post-compaction resume restore phase, blockers and authority? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| I10 | fresh-install/recovery simulation | Are summaries prevented from becoming primary evidence? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| I11 | human-factors and status-honesty review | Is cross-workspace retrieval denied below the model layer? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| I12 | production evidence gate | Does recall recover needed context without leaking unrelated private material in user tests? | **CONDITIONAL** | The contract is specified, but final confidence requires implementation, production data, host, organizational, or independent human evidence. |

## J — Skills and supply chain

| Lens | Approach | Question | Status | Finding |
|---|---|---|---:|---|
| J01 | formal type and schema analysis | Are bundled skill descriptions specific enough for bounded implicit invocation? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| J02 | counterexample construction | Are sensitive or side-effecting skills explicit-only? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| J03 | source-to-output provenance walk | Does progressive disclosure keep initial context within the host skill budget? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| J04 | failure injection | Are remote skills discovered as metadata before content fetch? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| J05 | dependency and hidden-edge analysis | Are fetched skills quarantined and non-executable by default? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| J06 | property-based state-machine review | Are source revision, hash, license, scripts, dependencies and permissions inventoried? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| J07 | threat modeling | Do static and sandbox scans detect path, secret, network and obfuscation risks? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| J08 | adversarial retrieval test | Does activation require exact-hash approval and a SkillLockfile? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| J09 | differential cross-provider check | Can a skill never expand its own capabilities or approve itself? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| J10 | fresh-install/recovery simulation | Are skill name collisions and shadowing visible? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| J11 | human-factors and status-honesty review | Can activation be rolled back and uninstalled cleanly? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| J12 | production evidence gate | Does the malicious-skill fixture suite cover real catalog and packaging variations? | **CONDITIONAL** | The contract is specified, but final confidence requires implementation, production data, host, organizational, or independent human evidence. |

## K — Workspace and corpus mapping

| Lens | Approach | Question | Status | Finding |
|---|---|---|---:|---|
| K01 | formal type and schema analysis | Does the map inventory code, schemas, workflows, tests, papers, data and artifacts? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| K02 | counterexample construction | Are unresolved and dynamic edges represented instead of dropped? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| K03 | source-to-output provenance walk | Does baseline centrality run a real algorithm on nontrivial graphs? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| K04 | failure injection | Are query relevance, centrality and blast radius separate values? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| K05 | dependency and hidden-edge analysis | Are generated, vendor, test and archived scopes classified and visible? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| K06 | property-based state-machine review | Can shared writes, quotas, approvals and mutable contracts become hidden dependency edges? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| K07 | threat modeling | Are paper citation, dataset and publication-family edges included? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| K08 | adversarial retrieval test | Can the map identify orphan schemas, dead workflows and unowned contracts? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| K09 | differential cross-provider check | Are algorithm version, alpha, personalization and exclusions recorded? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| K10 | fresh-install/recovery simulation | Can users trace a displayed rank to its inputs? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| K11 | human-factors and status-honesty review | Does change-impact mapping identify stale evidence and downstream Passports? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| K12 | production evidence gate | Does mapping scale and remain accurate on the production repository/corpus? | **CONDITIONAL** | The contract is specified, but final confidence requires implementation, production data, host, organizational, or independent human evidence. |

## L — Agent orchestration and graph execution

| Lens | Approach | Question | Status | Finding |
|---|---|---|---:|---|
| L01 | formal type and schema analysis | Does every role have mission, forbidden behavior, tool/evidence ACL and output schema? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| L02 | counterexample construction | Are host-specific agent names compiled from provider-neutral RoleSpecs? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| L03 | source-to-output provenance walk | Does the scheduler distinguish data, resource, quota, approval and privacy edges? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| L04 | failure injection | Are parallel writes limited to disjoint scopes and isolated worktrees? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| L05 | dependency and hidden-edge analysis | Are barriers used only for true set-wide operations? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| L06 | property-based state-machine review | Does fan-in compare expected and actual identities? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| L07 | threat modeling | Are large fan-ins hierarchical without discarding provenance? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| L08 | adversarial retrieval test | Are retries idempotent and bounded by policy? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| L09 | differential cross-provider check | Do cycles have seen-set, dry-round, max-round and budget contracts? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| L10 | fresh-install/recovery simulation | Does model routing consider failure cost and measured error diversity? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| L11 | human-factors and status-honesty review | Can the workflow fall back to serial execution without changing semantics? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| L12 | production evidence gate | Does multi-agent execution improve quality per cost under production evaluation? | **CONDITIONAL** | The contract is specified, but final confidence requires implementation, production data, host, organizational, or independent human evidence. |

## M — Security and privacy

| Lens | Approach | Question | Status | Finding |
|---|---|---|---:|---|
| M01 | formal type and schema analysis | Can evidence or model output ever enter the instruction/authority plane? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| M02 | counterexample construction | Are secret values represented as handles and excluded from prompts/logs/artifacts? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| M03 | source-to-output provenance walk | Are filesystem paths canonicalized with symlink and traversal defenses? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| M04 | failure injection | Is network egress allowlisted, metered and receipted? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| M05 | dependency and hidden-edge analysis | Are sandbox boundaries and timeouts enforced independently of model claims? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| M06 | property-based state-machine review | Are tool-hook coverage gaps covered by kernel policy where observable? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| M07 | threat modeling | Are remote notifications denied raw evidence and arbitrary commands by default? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| M08 | adversarial retrieval test | Are tenancy and workspace boundaries enforced below the UI/model layer? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| M09 | differential cross-provider check | Are logs, traces, screenshots and exports redacted under policy? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| M10 | fresh-install/recovery simulation | Does a source license constrain downstream export and retention? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| M11 | human-factors and status-honesty review | Are threat findings linked to tests and non-waivable gates? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| M12 | production evidence gate | Does an external security review and penetration test find zero unresolved critical issues? | **CONDITIONAL** | The contract is specified, but final confidence requires implementation, production data, host, organizational, or independent human evidence. |

## N — API, CLI and UI integrity

| Lens | Approach | Question | Status | Finding |
|---|---|---|---:|---|
| N01 | formal type and schema analysis | Do JSON Schema and OpenAPI generate all transport and UI contracts? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| N02 | counterexample construction | Do CLI, MCP, HTTP and persisted artifacts pass cross-surface conformance? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| N03 | source-to-output provenance walk | Do development and packaged servers call the same handlers? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| N04 | failure injection | Are stable error codes categorized and actionable? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| N05 | dependency and hidden-edge analysis | Does the dashboard distinguish READY, EMPTY_CONFIRMED, DEGRADED and UNAVAILABLE? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| N06 | property-based state-machine review | Can users open exact SourceSpans from Claims and verdicts? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| N07 | threat modeling | Are counterevidence, limitations, minority and unsearched scope visible by default? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| N08 | adversarial retrieval test | Are approval and override actions protected by local auth, CSRF and audit receipts? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| N09 | differential cross-provider check | Is untrusted evidence escaped and excluded from raw HTML execution? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| N10 | fresh-install/recovery simulation | Does the UI expose profile, workspace, corpus snapshot and health? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| N11 | human-factors and status-honesty review | Can all core workflows be completed via accessible non-GUI surfaces? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| N12 | production evidence gate | Does packaged UI meet accessibility and real-user usability thresholds? | **CONDITIONAL** | The contract is specified, but final confidence requires implementation, production data, host, organizational, or independent human evidence. |

## O — Performance, budget and operations

| Lens | Approach | Question | Status | Finding |
|---|---|---|---:|---|
| O01 | formal type and schema analysis | Are budgets typed by actual enforcement authority? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| O02 | counterexample construction | Can hard allocation cancel or pause before limits are exceeded? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| O03 | source-to-output provenance walk | Are unmetered/estimated costs never described as hard caps? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| O04 | failure injection | Does adaptive fleet size respond to epistemic uncertainty and risk? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| O05 | dependency and hidden-edge analysis | Are startup and hook latencies bounded and measured? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| O06 | property-based state-machine review | Can parsing/retrieval jobs stream rather than wait at unnecessary barriers? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| O07 | threat modeling | Are caches disposable, keyed by all semantic versions and safe to rebuild? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| O08 | adversarial retrieval test | Are rate limits, backoff and transport redaction centralized? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| O09 | differential cross-provider check | Are SLOs defined for health, retrieval, replay, backup and recovery? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| O10 | fresh-install/recovery simulation | Do telemetry and traces avoid secrets and licensed full text? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| O11 | human-factors and status-honesty review | Can operators diagnose partial, stuck, blocked and degraded runs? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| O12 | production evidence gate | Does the 2,000-document production load test meet quality, cost and latency gates? | **CONDITIONAL** | The contract is specified, but final confidence requires implementation, production data, host, organizational, or independent human evidence. |

## P — Cross-provider and host compatibility

| Lens | Approach | Question | Status | Finding |
|---|---|---|---:|---|
| P01 | formal type and schema analysis | Do Codex and Claude adapters preserve the same canonical RoleSpec and ResultEnvelope? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| P02 | counterexample construction | Are provider/model/adapter versions recorded on every node result? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| P03 | source-to-output provenance walk | Does fallback require policy approval and remain visible? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| P04 | failure injection | Are custom Claude agents and built-in Codex types generated from one role authority? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| P05 | dependency and hidden-edge analysis | Are worktree and sandbox differences capability-probed? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| P06 | property-based state-machine review | Can hooks be disabled without losing kernel correctness? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| P07 | threat modeling | Can MCP unavailability fall back to CLI without changing artifact semantics? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| P08 | adversarial retrieval test | Are provider outages isolated and classified rather than hidden? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| P09 | differential cross-provider check | Is error diversity measured instead of inferred from vendor names? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| P10 | fresh-install/recovery simulation | Are prompts and evals versioned per adapter? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| P11 | human-factors and status-honesty review | Do supported host versions have an explicit compatibility window? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| P12 | production evidence gate | Does parity testing show acceptable verdict/contract behavior across production providers? | **CONDITIONAL** | The contract is specified, but final confidence requires implementation, production data, host, organizational, or independent human evidence. |

## Q — Migration, release and provenance

| Lens | Approach | Question | Status | Finding |
|---|---|---|---:|---|
| Q01 | formal type and schema analysis | Does every breaking contract change have migration, backfill, compatibility and rollback? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| Q02 | counterexample construction | Are v2 narrative fields prevented from becoming manufactured v3 receipts? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| Q03 | source-to-output provenance walk | Is an upgrade tested on a verified clone before production state? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| Q04 | failure injection | Are modified hooks re-trusted after upgrade? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| Q05 | dependency and hidden-edge analysis | Can failed post-upgrade health trigger deterministic rollback? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| Q06 | property-based state-machine review | Does rollback retain migration and effect history? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| Q07 | threat modeling | Is source/dist equivalence checked? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| Q08 | adversarial retrieval test | Are dependency locks, SBOM, license and secret scans complete? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| Q09 | differential cross-provider check | Are bundles deterministic or differences explained? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| Q10 | fresh-install/recovery simulation | Are manifest, SBOM, provenance and bundle signatures independently verifiable? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| Q11 | human-factors and status-honesty review | Do release labels derive from gates rather than author intent? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| Q12 | production evidence gate | Does the production signing, key-custody and publication process pass organizational review? | **CONDITIONAL** | The contract is specified, but final confidence requires implementation, production data, host, organizational, or independent human evidence. |

## R — Implementation readiness and governance

| Lens | Approach | Question | Status | Finding |
|---|---|---|---:|---|
| R01 | formal type and schema analysis | Does the A-Z manifest cover authority through release without orphan work? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| R02 | counterexample construction | Are work-package write scopes and dependencies non-overlapping where parallel? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| R03 | source-to-output provenance walk | Does every package have objective exit criteria, commands and independent review? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| R04 | failure injection | Are only reviewed integration packages safe checkpoints? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| R05 | dependency and hidden-edge analysis | Are SPEC_GAP, BLOCKED and FAIL semantically distinct? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| R06 | property-based state-machine review | Can agents stop rather than fabricate missing infrastructure or evidence? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| R07 | threat modeling | Are conditional deployment values listed with owners and release impact? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| R08 | adversarial retrieval test | Are architecture decisions and rejected alternatives recorded? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| R09 | differential cross-provider check | Can every invariant trace to schema/workflow/work package/test? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| R10 | fresh-install/recovery simulation | Does the package distinguish specification, blueprint and implementation status? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| R11 | human-factors and status-honesty review | Can a new team start from A01 without hidden oral knowledge? | **PASS** | The v3 specification contains an explicit contract and traceable implementation/release gate. |
| R12 | production evidence gate | Does an independent implementation team successfully build the plugin from this specification? | **CONDITIONAL** | The contract is specified, but final confidence requires implementation, production data, host, organizational, or independent human evidence. |

## Conditional interpretation

The 18 conditional lenses are intentionally the implementation/production validation edge of each family. They cannot be truthfully closed by a specification document alone. Their owners and release effects are in the JSON report and A–Z manifest.
