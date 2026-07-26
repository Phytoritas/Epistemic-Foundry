# CodexClaw research and Epistemic Foundry v3 gap analysis

**Research snapshot:** 2026-07-26 (Asia/Seoul)  
**Observed public branch:** `lidge-jun/codexclaw` `main`, latest visible commit `bb143d9` dated 2026-07-23  
**Observed plugin/package version:** `0.1.1`  
**Method:** public README, plugin manifest, package manifest, skills, FSM/state/attestation sources, subagent configuration, commit/tag history, and the repository's own architecture analysis were inspected. This is a source-level architectural study, not a security certification or endorsement.

## Executive result

CodexClaw proves that a disciplined workflow can be delivered as a native Codex plugin rather than as a separate harness. Its most transferable assets are the plugin packaging surface, payload-resident CLI, lifecycle hooks, progressive skill disclosure, durable phase state, recall, repository mapping, role-based subagent configuration, doctor/config guards, and fresh-install discipline.

Epistemic Foundry must not copy the development methodology literally. PABCD is software-delivery-centric, narrative attestations are weaker than Foundry's evidence receipts, hooks cannot be treated as a complete enforcement boundary, repository ranking and GUI contracts need stronger semantics, remote skill discovery needs a supply-chain quarantine, and file JSON state is insufficient as the canonical store for concurrent research sessions.

## Adoption and correction matrix

| # | CodexClaw asset or issue | v3 disposition | v3 design decision | Reason |
|---:|---|---|---|---|
| 1 | Installable plugin package | **Adopt** | Add `.codex-plugin/plugin.json`, bundled skills, hooks, optional MCP, assets, local marketplace test profile. | v2 was a runtime/spec bundle, not a first-class installable product. |
| 2 | Two-line install and payload-resident CLI | **Adopt** | Ship `bin/efoundry.mjs`; every command must also work through the plugin root when no PATH alias exists. | Fresh installs must not depend on a repository checkout. |
| 3 | Progressively disclosed skill family | **Adopt + narrow** | Use one parent router plus bounded research skills; descriptions carry only trigger and boundary metadata. | Large always-on prompts would crowd the host context. |
| 4 | Lifecycle hooks | **Adopt as guardrails** | Cover session, prompt, tool, subagent, stop, and compaction events through one normalized hook gateway. | Hooks are useful UX/policy surfaces but not a complete security boundary. |
| 5 | PABCD finite-state discipline | **Replace** | Use the research-native FORGE protocol: Interview(optional) / Frame / Observe / Reason / Gate / Export-Evolve. | Software build phases do not map cleanly to evidence formation. |
| 6 | C0-C5 work classifier | **Adapt** | Introduce E0-E5 epistemic work classes to choose retrieval depth, Parliament size, verification, and human review. | Avoid running a full council for a direct lookup. |
| 7 | Attestation-gated transitions | **Strengthen** | A forward edge requires schema-valid artifact receipts, hashes, gate outputs, and expected state revision—not prose alone. | Form-valid narrative evidence can still be invented. |
| 8 | Human free-pass transitions | **Reject** | Human decisions use `HumanDecision`/`OverrideRecord`; no actor silently bypasses artifact obligations. | Human authority is explicit and replayable, not invisible. |
| 9 | Durable goalplan ledger | **Adopt** | Represent a research docket with hypotheses, required evidence lanes, gates, and reopen criteria. | Long work survives compaction and provider changes. |
| 10 | Recall across sessions | **Adopt with consent** | Separate ephemeral, workspace, user, and evidence memory; every retrieval emits a receipt and honors retention/redaction policy. | Cross-project recall can leak confidential context. |
| 11 | Post-compaction context reinjection | **Adopt** | Regenerate a signed ContextCapsule from canonical artifacts; never rely on a prose summary as state. | Compaction must preserve authority and exclusions. |
| 12 | Repo map | **Extend** | Create a Workspace Map spanning code, schemas, workflows, papers, citations, datasets, and artifacts. | A research plugin needs more than source symbols. |
| 13 | PageRank-based ranking | **Correct** | Run real baseline centrality without query personalization, then add query-specific personalization; never return uniform scores as ranking. | CodexClaw's own audit reports uniform default ranks. |
| 14 | Remote skill search | **Quarantine** | Fetch into a disabled vault; verify hash, license, scripts, permissions, origin, and review before activation; pin in SkillLockfile. | Skills are executable supply-chain inputs. |
| 15 | Role-based subagent configuration | **Adopt + enrich** | Compile RoleSpec into host-native explorer/worker or Claude custom agents; include tool ACL, evidence ACL, write scope, budget, and expected count. | A model name and prompt override are insufficient authority control. |
| 16 | Inline role injection workaround | **Encapsulate** | Keep host-specific spawn details inside adapters; canonical role semantics remain provider-neutral. | Host limitations must not leak into scientific contracts. |
| 17 | Local GUI | **Adopt safely** | Generate clients/types from OpenAPI/JSON Schema, use explicit EMPTY/DEGRADED/UNAVAILABLE states, loopback auth, CSRF protection. | Silent empty fallbacks can hide backend outages. |
| 18 | Thin CLI dispatcher | **Adopt** | Dispatcher only resolves components and normalizes errors; domain logic lives behind stable contracts. | Prevents another monolithic command surface. |
| 19 | Config guard and doctor | **Adopt + expand** | Probe hook events, MCP, local DB, parsers, network policy, migrations, signing, and host version; emit PluginHealthReport. | Feature assumptions must be observed at runtime. |
| 20 | Provider bridge | **Generalize** | Use capability-based provider adapters and model routing by failure cost, error diversity, latency, and budget. | No provider owns canonical state. |
| 21 | Messenger bridge | **Optional/deferred** | Allow status and approval notifications only under explicit policy; remote command execution and raw evidence export are off by default. | It adds a large attack and privacy surface unrelated to the core research loop. |
| 22 | File-backed JSON session state | **Replace for authority** | Use SQLite WAL locally and PostgreSQL in team mode; JSON is export/inspection only. | Concurrent hooks, subagents, and migrations require stronger transactions. |
| 23 | Atomic reconstruction and writes | **Retain** | Use strict reconstruction, compare-and-swap revision, fsync/rename for file artifacts, and hash-chain ledger events. | Corrupt state must fail closed. |
| 24 | Component isolation | **Retain + enforce** | No component imports another component's source; shared contracts are generated into a dependency-free package. | Avoid source/dist divergence and import cycles. |
| 25 | Persistence god module | **Prevent** | One migration owner; cohesive repositories for sessions, ledger, memory, skills, artifacts, and jobs behind ports. | Schema evolution must not create a 1,000-line shared mutable center. |
| 26 | Duplicated UI/backend contracts | **Eliminate** | Canonical JSON Schema/OpenAPI generates TypeScript, Python, and UI clients plus conformance tests. | Development and packaged paths must behave identically. |
| 27 | Duplicated transport policy | **Eliminate** | Shared transport kernel owns timeout, retry, backoff, redaction, proxy, TLS, rate-limit, and receipt rules. | Provider adapters only map payloads. |
| 28 | Budget claims | **Make enforcement typed** | Distinguish HARD_METERED, HARD_PREALLOCATED, SOFT_ESTIMATE, and UNMETERED; never describe advisory spend as a kill switch. | Operational honesty is a product invariant. |
| 29 | Plugin hook trust/version drift | **Add compatibility plane** | Hash hook definitions, feature-probe each host, maintain compatibility matrix, and fall back to explicit CLI/core gates. | A plugin must remain honest when hooks are disabled or unsupported. |
| 30 | Cross-platform and fresh-install tests | **Adopt** | Test Windows, macOS, Linux; local marketplace install, upgrade, downgrade, uninstall, PATH-less dispatch, spaces and non-ASCII paths. | Installation is part of the product contract. |
| 31 | Status-honest documentation | **Adopt** | Every feature is tagged IMPLEMENTED, SPECIFIED, EXPERIMENTAL, DEFERRED, or UNSUPPORTED. | Do not turn roadmap language into capability claims. |
| 32 | Existing-host rather than forked harness | **Adopt with a kernel boundary** | Use Codex/Claude as replaceable execution surfaces while Foundry Kernel owns epistemic state, evidence gates, receipts, and replay. | The plugin should feel native without surrendering authority to a chat session. |

## Source inventory

- Repository and README: `https://github.com/lidge-jun/codexclaw`
- Plugin manifest: `plugins/codexclaw/.codex-plugin/plugin.json`
- Package manifest: `package.json`
- PABCD skill: `plugins/codexclaw/skills/pabcd/SKILL.md`
- PABCD state/FSM/attestation: `plugins/codexclaw/components/pabcd-state/src/`
- Subagent store and spawn wrapper: `plugins/codexclaw/components/subagent-config/src/`
- Recall, repo map, skill search, config guard, operations, and messenger components: `plugins/codexclaw/components/` and `plugins/codexclaw/skills/`
- Repository-authored architecture review: `architecture-analysis-report.md`
- OpenAI primary documentation consulted: plugin architecture, skills, hooks, subagents, MCP, worktrees, plugin packaging and testing.

## What v3 intentionally does not inherit

1. It does not make remote messaging a prerequisite.
2. It does not use free-form attestation as proof of work.
3. It does not allow a human chat path to skip canonical gates.
4. It does not claim hook coverage over hosted tools or treat hooks as the security perimeter.
5. It does not silently treat backend failure as an empty state.
6. It does not install discovered skills directly into the active trust domain.
7. It does not conflate a repository symbol map with an importance ranking.
8. It does not let provider-specific subagent names become canonical role semantics.
9. It does not place scientific evidence, memory, job state, and migrations in one persistence module.
10. It does not describe estimated cost as hard-enforced budget.

## Resulting v3 thesis

> **Epistemic Foundry v3 is a domain-neutral, evidence-gated research operating system delivered through a native plugin shell. The shell supplies host integration and user experience; the Foundry Kernel owns state, evidence, authority, side effects, replay, and scientific promotion.**
