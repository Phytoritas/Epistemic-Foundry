# Decision

Use a **hybrid, body-local binding**:

* Use MCP only for readiness and capability discovery: `foundry.status` and, where relevant, `foundry.health`.
* Put the actual existing `efoundry` invocation directly in the small number of skill bodies with a defensible semantic match.
* Put a terse **no-producer boundary** directly in bodies that promise canonical artifacts the runtime cannot produce.
* Do not add a reference file, a fourteenth MCP tool, a new inventory binding field, or a new CLI subcommand in this increment.

This is option **(d)**: mostly direct CLI binding, with MCP as preflight. The smallest capability-producing change is to bind **`foundry-observe` only**. `foundry-admin` can also name existing diagnostic commands, but that is optional because it does not unlock a new domain workflow.

The current bodies have ample budget headroom. `foundry-observe` is only 479 bytes and 104 tokens against 4096 bytes and 1024 tokens. A useful execution stanza can remain well below 1 KB. The integrity cost is therefore mechanical rather than a genuine context-budget constraint.

---

## 1. Where the executable path belongs

### Selected form

The skill body should contain four things:

1. The readiness probe.
2. The exact executable command family.
3. The maximum truthful output.
4. The fail-closed behavior when execution is unavailable.

For `foundry-observe`, the pattern should be:

```markdown
## Executable slice

Call MCP `foundry.status` first. When `efoundry` is READY and host process
execution is permitted, run `efoundry retrieve query --help`, then invoke the
exact installed form of:

`efoundry retrieve query --lane <supported-lane> ...`

Accept only the emitted `retrieval-candidate` objects, sealed
`search-lane-receipt`, and explicit lane reconciliation. Preserve every
unserved lane as `UNSEARCHED`.

This executable slice does not emit an EvidencePack or
SearchCompletenessCertificate unless those artifacts are actually returned and
schema-valid. Do not run `efoundry retrieve build` implicitly. If the bridge,
index, command, or required workspace binding is unavailable, report that
blocker; never substitute an authoritative empty result.
```

The literal ellipsis should not remain in the committed body. At implementation time, copy the remaining required operands from the installed:

```text
efoundry retrieve query --help
```

Only `retrieve query` and `--lane` have been established in the supplied evidence, so additional flags should not be guessed in this decision.

### Why not MCP for the work itself?

None of the frozen thirteen tools means “execute lexical retrieval and seal lane receipts”:

* `foundry.search.plan` is a durable planning operation, not retrieval execution.
* `foundry.atlas.query` and `foundry.map.query` read different projections.
* Binding `retrieve query` to any of those would change their semantics.
* Adding a fourteenth tool is explicitly outside the frozen catalog.

Using `foundry.status` as a preflight is appropriate. Using an unrelated T01 tool as a retrieval executor is not.

### Why not a new reference file?

A new declared reference would change the exact J02 count from 17 to 18. Changing that accepted topology is a **SPEC_GAP** requiring authority. An undeclared file would not be a reliable progressive-disclosure path, and editing an existing scientific or constitutional reference to carry adapter commands would mix runtime instructions into the wrong authority layer.

A reference would also not eliminate the body edit when a skill must tell the agent to load it. With only one or two honestly bindable skills, inline text has the smaller semantic and mechanical blast radius.

### Seal updates

For the capability minimum, the expected change surface is:

```text
plugins/epistemic-foundry/skills/foundry-observe/SKILL.md
plugins/epistemic-foundry/skills/skill-inventory.json
tests/fixtures/j02/skill-inventory.expected.json
tests/fixtures/j02/reference-selection-cases.json
```

Recompute through the canonical counter rather than hand-calculating:

* the body SHA-256;
* `byte_count`;
* pinned `token_count`;
* the inventory hash;
* all affected fixture projections;
* the metadata projection, even if its canonical serialization ultimately remains unchanged.

---

## 2. Skills that can honestly name an executable command today

The honest count is:

* **One domain skill with a real executable slice:** `foundry-observe`.
* **One additional skill with diagnostic-only executable slices:** `foundry-admin`.
* **No other active skill has a producer-equivalent command in the five-command CLI.**

| Skill             | Command that may be named                             | Truthful ceiling                                                                                                                                                                                                   |
| ----------------- | ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `foundry-observe` | `efoundry retrieve query --lane <supported-lane> ...` | Real lexical retrieval candidates, a sealed lane receipt, and explicit reconciliation. It is not the full Observe workflow and must not claim an EvidencePack or completeness certificate unless actually emitted. |
| `foundry-admin`   | `efoundry status`; `efoundry ledger verify`           | Runtime/schema availability and event-ledger integrity only. It does not implement policy, consent, backup, migration, rollback, signing, or recovery.                                                             |

The MCP forms `foundry.status` and `foundry.health` may be preferred for the `foundry-admin` diagnostic slice because they are already packaged and bridge-aware. Adding CLI text to `foundry-admin` is truthful, but optional.

### Commands that do not make another skill executable

`efoundry schemas` and `efoundry validate` are useful utilities, but they do not provide producer-equivalent paths for other skills:

* `foundry-validation` requires preregistration, target and capability handling, execution, and receipts. Generic document validation is not that workflow.
* `foundry-domain-pack` requires DomainPack authoring. Validating an already-created document is not a producer.
* `foundry-plugin-dev` covers building, testing, auditing, packaging, migration, and release. Schema listing and generic validation are supporting checks, not completion of that skill.
* `foundry-claim-forge` needs claim extraction and grounding, not merely validation of a supplied object.
* `foundry-replay` needs replay comparison and stale propagation; ledger-chain verification is not replay.
* `foundry-atlas`, `foundry-map`, and `foundry-intake` have no corresponding producer.
* `retrieve build` constructs a mutable index projection. It should not be automatically executed by the implicitly invocable `foundry-observe` skill.

Thus the body should use the heading **“Executable slice”**, not wording that implies the entire skill has been implemented.

---

## 3. What a skill with no producer should say

The blocker belongs in the skill body. It is invocation-critical information that the agent must see even when no optional reference is loaded.

A detailed package-wide capability matrix may supplement it later, but it should not be the only source of this boundary.

### `foundry-map`

```markdown
## Execution status

No packaged producer currently emits a canonical `WorkspaceMapSnapshot`.
Do not synthesize one, assign artifact IDs or receipts, or claim this skill
completed. Report the missing snapshot producer as the blocker. Provisional
mapping prose may be returned only when clearly labeled noncanonical.
```

### `foundry-intake`

```markdown
## Execution status

No packaged producer currently emits a canonical `InsightCard` or
`ScopeVector`. Do not label provisional framing text as either artifact, assign
artifact IDs or receipts, or claim this skill completed. Report the missing
framing producer as the blocker.
```

This wording prevents both failure modes:

* **Silent uselessness:** the agent identifies exactly what is missing and may still provide useful provisional analysis.
* **False completion:** provisional prose cannot masquerade as a canonical artifact.

The body does not need a newly invented error code. When a corresponding MCP call is involved, its existing canonical `UNAVAILABLE` envelope remains authoritative. In ordinary skill output, plain language identifying the missing producer is sufficient.

### Scope of the current reseal

There are two defensible increments:

**Capability minimum:** edit only `foundry-observe` and the inventory/fixtures. This gives one genuine end-to-end path.

**Recommended truthfulness minimum:** in the same reseal, also add the short blocker sections to `foundry-map` and `foundry-intake`, because these are implicitly invocable and explicitly promise named canonical artifacts. This changes three bodies rather than all 29 while correcting the two clearest overpromises.

A generic rule in the parent `foundry` body can be added as defense in depth:

```markdown
A child skill may claim a canonical artifact only when that child names a bound
producer and the producer actually returns a schema-valid artifact. Otherwise
report the missing producer and keep any analysis provisional.
```

That parent rule should not replace child-local blockers, because a child may be directly selected or explicitly invoked without the parent prose being the operative context.

---

## 4. Better target for this increment?

### Decision order

| Target                                                                 | Incremental result                                                        |              Rough size | Decision                    |
| ---------------------------------------------------------------------- | ------------------------------------------------------------------------- | ----------------------: | --------------------------- |
| Bind `foundry-observe` to existing retrieval CLI                       | Immediate candidates plus sealed lane receipt from a shipped skill        |                    Tiny | **Do now**                  |
| Implement `WorkspaceMapSnapshot` producer and bind `foundry.map.query` | Unlocks one substantial skill and one existing MCP read tool              |  Medium to medium-large | **Best next kernel target** |
| Implement FORGE session store and bind `foundry.session.get`           | Unlocks session reads only after creation and transition paths also exist | Large and cross-cutting | **Not next**                |

### Workspace map producer

A real map producer is the better of the two larger targets. It can be deterministic over an explicitly frozen workspace and directly unlock:

```text
foundry-map
→ canonical WorkspaceMapSnapshot
→ foundry.map.query
```

But it is not just a directory walker. A source-defensible producer needs at least:

* explicit workspace identity and frozen input snapshot;
* typed entity inventory;
* typed edge extraction;
* classifications and exclusions;
* source, schema, parser, and configuration hashes;
* real baseline structural ranking rather than uniform placeholders;
* query-specific ranking kept separate from baseline centrality;
* risk or blast-radius dimensions kept separate from relevance;
* snapshot persistence and a read projection;
* the existing MCP adapter.

A repository-only first profile could be a **contained medium piece of work** only when the canonical schema already permits its narrower coverage to be declared honestly, including exclusions and unavailable graph layers. If producing a smaller snapshot requires weakening required fields, redefining `WorkspaceMapSnapshot`, or treating absent layers as complete, that is a **SPEC_GAP**.

There is also currently no verified producer command. Either of these would be a **SPEC_GAP** unless already authorized elsewhere:

* adding `efoundry map ...` and thereby changing the exact five-command CLI table;
* making the pure-read `foundry.map.query` construct or persist a map as a side effect.

So the map producer is a sensible next implementation target, but not a smaller substitute for the one-body Observe binding.

### FORGE session store

A session store is substantially larger. Canonical session state is not merely a mutable JSON record; it entails:

* session identity and workspace binding;
* lifecycle phase invariants;
* append-only events;
* deterministic reduction;
* revision control and concurrency handling;
* transition validation;
* blocker and artifact-obligation derivation;
* artifact bindings;
* crash-safe persistence;
* resume and replay behavior;
* a read projection;
* an authorized creation and transition producer.

Binding `foundry.session.get` without a way to create or transition sessions would only turn `UNAVAILABLE` into `EMPTY_CONFIRMED` or a permanently empty store, which does not produce a useful end-to-end capability. Adding a creation/transition command or packaged write tool would require a separate authority decision where not already frozen.

The session store is therefore a **large foundational subsystem**, not a contained read-model patch.

---

## Approved minimum increment

1. Add one bounded executable section to:

```text
plugins/epistemic-foundry/skills/foundry-observe/SKILL.md
```

2. Use `foundry.status` only as readiness preflight and `efoundry retrieve query` as the real execution path.

3. Do not invoke `retrieve build` implicitly.

4. Cap successful claims at retrieval candidates, the lane receipt, and the reconciliation actually returned.

5. Recompute the skill seal, inventory hash, exact counts, and the two affected J02 fixtures.

6. Optionally add diagnostic command text to `foundry-admin`; do not count it as full admin execution.

7. Add the short producer-absence boundaries to `foundry-map` and `foundry-intake` in the recommended truthfulness variant.

8. Leave the other skills advisory until their canonical producers exist.

9. Target a real `WorkspaceMapSnapshot` producer before a FORGE session store in a later authorized increment.

No implementation or test execution is claimed here.

### Local authority anchors
