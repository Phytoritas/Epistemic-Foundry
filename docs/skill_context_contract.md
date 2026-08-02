# J02 Product Requirements — Progressive Skill Context

Status: `APPROVED FOR J02-0002`  
Authority: `HD-EF4-J02-SG001-20260729-001`  
Owner: `J02`  
Review mode: procedurally separate primary-session adversarial review; no
actor-independent claim while subagents and Fleet are prohibited.

## 1. Purpose and boundaries

J02 converts a valid J01 `SkillRoutingDecision` into a deterministic,
hash-bound `ResolvedSkillContext`. It exposes all 29 production skills through
bounded initial metadata, then loads only the selected skill and its declared
reference closure. J02 does not choose the skill, assemble a ContextCapsule,
mutate FORGE state, grant capabilities, call a model, fetch network content,
or create a new public canonical schema.

The authority boundary is:

```text
J01 SkillRoutingDecision
  -> J02 inventory validation, selection, reachability, budget and load
  -> ResolvedSkillContext
J03 canonical state
  -> ContextCapsule
J02 + J03
  -> J04 post-compaction integration gate
```

## 2. Production inventory

`plugins/epistemic-foundry/skills/skill-inventory.json` is the single runtime
inventory authority. It contains exactly one parent (`foundry`), 28 children,
and 17 local Markdown references. The 29 blueprint `SKILL.md` files are
migration input only. Missing production skills are materialized once; the
blueprint is never read dynamically by runtime or tests.

Every skill entry binds its ID, description, normalized relative path,
invocation disposition, active status, SHA-256, byte count, token count,
direct references, conditional references, and child edges where applicable.
Every reference binds canonical ID, local path, mode, dependencies, SHA-256,
byte/token counts, authority-source path/hash pairs, media type and status.
The inventory hash is SHA-256 over RFC 8785-equivalent canonical JSON with the
`inventory_hash` field excluded.

### 2.1 Invocation disposition

| Disposition | Skills | Host implicit |
| --- | --- | --- |
| `PARENT_ROUTER` | `foundry` | allowed |
| `IMPLICIT_SAFE` | intake, claim-forge, observe, atlas, reason, aporia, map, passport, evolve-inspect | allowed |
| `PARENT_ROUTED` | parliament, evolve, evolve-setup, evaluator-audit, challenge, archive | denied |
| `EXPLICIT_ONLY` | admin, domain-pack, evolution-replay, evolution-stop, evolve-convert, evolve-run, plugin-dev, promote-evolved, recall, replay, replicate, shinka-adapter, validation | denied |

Reachability is discovery, not execution authority. Parent-routed skills still
require a valid J01 decision and applicable phase/policy gates. Explicit-only
skills require exact user invocation, exact approved action, or exact policy
authorization. Inventory and each `agents/openai.yaml` projection must agree.

## 3. Initial metadata contract

The projection contains exactly three tab-separated fields per skill:

```text
<name>\t<description>\t<relative_path>\n
```

It is BOM-less UTF-8 with LF, NFC normalization, parent first, then child
names in ascending UTF-8 byte order. Names and paths are ASCII. Descriptions
have no tab/newline, are trimmed, and collapse consecutive ASCII whitespace.
Paths are POSIX-relative and contain no URI, drive, absolute or workspace
component.

| Limit | Value |
| --- | ---: |
| Skill count | exactly 29 |
| Total UTF-8 bytes | <= 6,400 |
| Total `o200k_base` tokens | <= 1,600 |
| Name | <= 64 ASCII bytes |
| Description | <= 140 UTF-8 bytes |
| Relative path | <= 128 ASCII bytes |

Both total limits apply. Runtime truncation, omission, reordering, generated
summary, or reliance on host truncation is forbidden. A smaller host budget
becomes the effective limit. If all 29 entries do not fit, implicit discovery
is disabled with `HOST_SKILL_METADATA_BUDGET_INSUFFICIENT`; only a reachable,
explicit `$foundry` parent may enter `EXPLICIT_PARENT_ONLY` degraded mode.

Canonical token accounting is `tiktoken==0.13.0`, direct `o200k_base`, with
`disallowed_special=()`. The dependency artifact digest is locked in the
repository inventory/lock evidence. Model aliases, approximations and silent
version drift fail `TOKENIZER_CONTRACT_UNAVAILABLE`.

## 4. Progressive activation budgets

| Surface | Bytes | Tokens | Other |
| --- | ---: | ---: | --- |
| Selected `SKILL.md` | 4,096 | 1,024 | frontmatter + body |
| Each reference | 4,096 | 1,024 | atomic `text/markdown`, UTF-8/LF/no BOM |
| Reference closure | 24,576 | 6,144 | <=12 files, depth <=5 |
| Skill + closure | 28,672 | 7,168 | all limits are AND conditions |

An over-budget mandatory closure fails `REFERENCE_CONTEXT_BUDGET_EXCEEDED`.
No reference is cut, omitted, summarized, substituted, or partially executed.

## 5. Canonical reference graph

| ID | Relative path | Dependencies |
| --- | --- | --- |
| `EFREF-CORE-CONSTITUTION-V4` | `skills/foundry/references/core/constitution.md` | none |
| `EFREF-CORE-STATUS-RECEIPTS-V4` | `skills/foundry/references/core/status-receipts.md` | constitution |
| `EFREF-ROUTER-E0-E5-V4` | `skills/foundry/references/router/e0-e5-routing.md` | constitution |
| `EFREF-EVIDENCE-CLAIM-SEARCH-V4` | `skills/foundry/references/evidence/claim-search.md` | constitution |
| `EFREF-EVIDENCE-SCOPE-METHOD-DEPENDENCY-V4` | `skills/foundry/references/evidence/scope-method-dependency.md` | claim-search |
| `EFREF-REASONING-TYPED-MODES-V4` | `skills/foundry/references/reasoning/typed-modes.md` | scope-method-dependency |
| `EFREF-PARLIAMENT-ASYMMETRIC-GATES-V4` | `skills/foundry/references/parliament/asymmetric-gates.md` | status-receipts, claim-search, scope-method-dependency |
| `EFREF-PASSPORT-PROMOTION-V4` | `skills/foundry/references/passport/promotion.md` | status-receipts, parliament |
| `EFREF-VALIDATION-REPLICATION-V4` | `skills/foundry/references/validation/replication.md` | status-receipts, scope-method-dependency |
| `EFREF-EVOLUTION-RUN-GENOMES-V4` | `skills/foundry/references/evolution/run-genomes.md` | status-receipts, router |
| `EFREF-EVOLUTION-VERIFIER-STATISTICS-V4` | `skills/foundry/references/evolution/verifier-statistics.md` | validation-replication, run-genomes |
| `EFREF-EVOLUTION-ARCHIVE-REDQUEEN-V4` | `skills/foundry/references/evolution/archive-red-queen.md` | run-genomes, verifier-statistics |
| `EFREF-CONTEXT-MEMORY-REPLAY-V4` | `skills/foundry/references/context/memory-replay.md` | status-receipts, router |
| `EFREF-EXTENSIONS-MAP-DOMAINPACK-V4` | `skills/foundry/references/extensions/map-domain-pack.md` | scope-method-dependency |
| `EFREF-PLUGIN-SECURITY-ADMIN-V4` | `skills/foundry/references/plugin/security-administration.md` | constitution, status-receipts |
| `EFREF-BACKEND-SHINKA-V4` | `skills/foundry/references/backends/shinka.md` | run-genomes, security-administration |
| `EFREF-PLUGIN-DEVELOPMENT-RELEASE-V4` | `skills/foundry/references/plugin/development-release.md` | status-receipts, security-administration |

All 17 references must be reachable from an active skill, with no orphan,
alias, duplicate ID/path, case-only collision, cycle or missing file.

## 6. Direct and conditional mappings

The exact direct mappings are:

```text
foundry: R01 R03
admin: R01 R02 R15 R17
aporia: R01 R05 R06
archive: R01 R10 R12
atlas: R01 R04 R05
challenge: R01 R11 R12
claim-forge: R01 R04 R05
domain-pack: R01 R05 R14
evaluator-audit: R01 R09 R11
evolution-replay: R01 R10 R13
evolution-stop: R01 R02 R10
evolve-convert: R01 R10; add R16 when backend_id == shinka
evolve-inspect: R01 R10 R12
evolve-run: R01 R10 R11 R12
evolve-setup: R01 R03 R10 R11
evolve: R01 R03 R10
intake: R01 R03 R05
map: R01 R14
observe: R01 R04 R05
parliament: R01 R07; add R11 when candidate_origin == EVOLUTION
passport: R01 R08; add R09 when artifact_kind includes ValidationResult or ReplicationResult
plugin-dev: R01 R15 R17
promote-evolved: R01 R08 R11 R12
reason: R01 R05 R06
recall: R01 R13
replay: R01 R02 R13
replicate: R01 R09 R11
shinka-adapter: R01 R16
validation: R01 R09 R11
```

The full IDs, not R01-R17 aliases, are persisted.

## 7. Deterministic selection and ordering

Modes are closed to `REQUIRED`, `CONDITIONAL`, `EXPLICIT_ONLY`, `DISABLED`.
Typed condition keys are `work_class`, `forge_phase`, `request_signal`,
`artifact_kind`, `capability`, `backend_id`, `candidate_origin`, `operation`,
and `status`; operators are `EQUALS`, `IN`, `ANY_OF`, `ALL_OF`. Arbitrary
code, regex, embedding similarity, model judgment and network lookup are
forbidden.

The Kernel validates the J01 decision and inventory hash, checks skill and
invocation disposition, collects required and matching conditional IDs,
accepts only authorized exact explicit IDs, expands dependencies, rejects
missing/cycle/depth/traversal faults, deduplicates by canonical ID, and emits a
topological order. Within a layer the order priority is constitution,
transitive prerequisite, direct required, matching conditional, explicit;
ties use canonical ID UTF-8 byte order. Content hash and counts are verified
before budgets. LLM proposals are non-authoritative exact-ID hints only.

## 8. Filesystem and freshness security

Reference paths must remain below
`plugins/epistemic-foundry/skills/foundry/references/` after lexical and
realpath resolution. Reject `.`/`..`, leading slash, backslash, drive or UNC,
URI, encoded traversal, NUL/control characters, symlink, junction, hard-link
escape and case-fold containment escape. Remote or MCP resources are not local
references.

Actual SHA-256, byte count, token count, and every authority-source hash must
match inventory or fail `REFERENCE_CONTENT_DRIFT`. Missing selected skill,
reference, dependency, hash/count or authority pointer fails
`REFERENCE_TARGET_MISSING`. Cycles fail `REFERENCE_GRAPH_CYCLE`; depth overflow
fails `REFERENCE_DEPTH_EXCEEDED`.

## 9. Runtime output

`ResolvedSkillContext` binds inventory ID/hash, routing decision ID, selected
skill ID/path/hash/counts, ordered reference IDs/paths/hashes, selection
reasons, depth, reference and activation totals, invocation disposition,
degraded mode, warnings and errors. Success requires this structured result
and verified file bytes; a `ResultEnvelope` alone is insufficient.

The implementation files are the exact J02-owned files under
`packages/plugin-host/src/skill-context/`, plus the canonical Python counter
`tools/skill-context/count_tokens.py`. No J01 router, J03 ContextCapsule,
schema, OpenAPI, workflow, prompt, package snapshot or pyproject file changes
are authorized.

## 10. Acceptance oracle

`python -m pytest -q tests/test_j02_context_budget.py` must prove exactly 29
skills, 1 parent, 28 children, metadata <=6,400 bytes/1,600 tokens, every
description <=140 bytes, all 29 progressive activations within limits, every
tokenizer vector exact, no skip/xfail/network/model call, and all 12 boundary
cases exact.

The two Node commands must prove 29/29 skill reachability, 17/17 reference
reachability, zero graph/integrity faults, 29 default + 3 positive + 3 negative
selection cases, 16/16 exact fail-closed adversarial cases, and 100/100 stable
IDs/order/hash/totals across repeated runs:

```text
node --test tests/node/j02-reference-reachability.test.mjs
node --test tests/node/j02-skill-context-loader.test.mjs
```

J01 `skill_routing_eval` and `skill_metadata_lint`, full Python and Node
regressions, inventory/hash verification, write-scope audit and
`git diff --check` must add zero J02-caused failures or skip/xfail. Existing
bounded debt may remain only with exact test ID, fingerprint, path, count,
owner and causal-separation evidence.

## 11. Evidence and release meaning

J02-0002 must emit report, command ledger, review, metadata/tokenizer,
inventory, selection, reachability, regression and RAH integrity artifacts.
PASS means deterministic bounded skill context is available to J03/J04; it
does not mean ContextCapsule, post-compaction recovery, plugin release,
production readiness or overall completion.
