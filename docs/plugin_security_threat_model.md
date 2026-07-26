# Plugin security, privacy and supply-chain threat model

## 1. Trust zones

1. **Host instruction plane** — system/developer/user instructions and managed policy.
2. **Plugin control plane** — manifest, signed distribution, hook gateway, kernel policy.
3. **Evidence data plane** — PDFs, web pages, datasets, captions, metadata, retrieved text.
4. **Model output plane** — all LLM/subagent text and structured candidates.
5. **Execution plane** — shell, filesystem, MCP, parsers, network, validation targets.
6. **Memory plane** — session, workspace, user and evidence memory.
7. **External supply chain** — plugins, skills, npm/Python packages, containers, models.
8. **Presentation plane** — local dashboard, exports, notifications.

Evidence and model output are always untrusted data. They cannot grant capabilities, alter policy, change phase, or approve themselves.

## 2. Threat catalog and mandatory controls

| Threat | Failure | Mandatory control |
|---|---|---|
| Prompt injection in paper/web page | evidence text becomes instruction | data/instruction separation; quoting; no authority inheritance; injection fixtures |
| Tool-hook bypass | hosted/specialized tool not observed | hooks are guardrails; kernel capabilities and receipts are authoritative; capability report |
| Forged attestation | agent narrates a command/result | artifact hash, command/effect receipt, schema validation, independent verifier |
| Stale replay | old context used after corpus/policy change | snapshot hashes, stale propagation, compatibility and lifecycle status |
| Cross-workspace recall | confidential context leak | consent, workspace boundary, retrieval receipt, redaction, retention |
| Malicious remote skill | scripts or instructions gain authority | quarantine, static/dynamic scan, permissions, signature/hash, review, lockfile |
| Plugin upgrade tampering | modified hook or dist code | package hash, hook re-trust, SBOM, signature, source/dist equivalence |
| Symlink/path escape | write outside allowed root | canonical path resolution, no-follow policy, resource scope and sandbox |
| Secret exfiltration | evidence/model sends keys externally | secret handles only, egress allowlist, redaction, no secret in prompt/artifact |
| Partial fan-out hidden | missing critics makes verdict look complete | expected/actual count gate and PARTIAL status |
| UI outage hidden as empty | user trusts blank state | explicit UNAVAILABLE/DEGRADED state and health telemetry |
| Budget overrun | loop continues without meter | typed budget enforcement, preallocation, cancellation, hard round/concurrency caps |
| Provider drift | model version changes behavior | model identifier, adapter version, eval drift and attestation |
| Corpus licensing violation | unlicensed full text exported | source policy, license class, export filter and audit |
| Remote messaging abuse | command injection/data leakage | disabled by default; status/approval only; allowlist; no raw evidence |
| SQLite corruption/concurrency | lost phase or ledger | WAL, transactions, migrations, backup, integrity and recovery tests |
| Dependency confusion | malicious package resolution | lockfiles, registry allowlist, checksums, provenance and offline build |
| UI/API contract drift | dev and release paths differ | generated clients, one handler contract, conformance tests |
| Majority capture | correlated agents amplify error | asymmetric ACLs, veto, minority report, attestor, deterministic gates |
| Human override invisibility | unreviewable policy bypass | immutable OverrideRecord and downstream invalidation |

## 3. Hook fail-open/fail-closed matrix

- Informational bootstrap and map/recall suggestions: fail open with health warning.
- Secret/path/egress guard for local side effects: fail closed when the kernel can observe the action.
- Hosted tool path not observable: mark coverage gap; never claim enforcement.
- State integrity or migration uncertainty: SAFE_MODE; only doctor, export, backup, and recovery.
- Evidence lane unavailable: allow PARTIAL/UNDERDETERMINED, deny complete-coverage claims.
- Signature service unavailable: allow unsigned local development artifact, deny signed-release label.

## 4. Skill Vault

Remote skill acquisition is a workflow, not a copy command:

```text
discover metadata
→ fetch to quarantine
→ pin source revision and hash
→ inspect SKILL.md boundaries
→ enumerate scripts/assets/dependencies
→ license and provenance check
→ static secret/path/network scan
→ permission inference
→ sandbox smoke test
→ human or policy review
→ write SkillLockfile
→ install disabled
→ activate explicitly
```

A skill can recommend an action but cannot expand its own capabilities.

## 5. Privacy model

Memory classes:

- `EPHEMERAL`: current invocation, deleted on close unless promoted.
- `SESSION`: current FORGE run.
- `WORKSPACE`: explicit project memory.
- `USER`: cross-workspace, opt-in only.
- `EVIDENCE`: source-bound durable research artifacts.
- `REGULATED`: retention, legal hold, and access policy.

Every memory write has purpose, data classes, retention, workspace, actor, source, and consent basis. Every memory retrieval has query, searched stores, excluded stores, hits, redactions, and context hash.

## 6. Release security gates

- dependency lock and license scan;
- secret scan;
- malicious fixture suite;
- hook and MCP schema tests;
- sandbox/path escape tests;
- network egress tests;
- fresh-install and upgrade tests;
- SBOM and release provenance;
- deterministic bundle and hash manifest;
- signature verification;
- rollback package;
- compatibility matrix;
- no critical unresolved threat-model finding.
