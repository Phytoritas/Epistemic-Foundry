# Decision

Choose **Option B, constrained to a lazy optional Python bridge**.

The packaged Node server should remain the self-contained MCP transport and plugin-payload observer. It should invoke the installed Python runtime only for an authorized tool call that requires Python-backed facts. For this increment:

* Make `foundry.status` and `foundry.health` real.
* Bind **none of the other eleven tools** to the currently described Python surface.
* Advertise the **fixed canonical thirteen-tool T01 catalog**, with the eleven unbound tools returning an explicit unavailable disposition.
* Do not start Python during `initialize`, `ping`, or `tools/list`.
* Do not bundle the Python runtime, require a repository checkout, add a sixth CLI subcommand, or reinterpret lexical retrieval as another Foundry domain.

This preserves Option A’s cheap and reliable startup while actually connecting the plugin to the working runtime. A pure Option A would be honest but would leave the central integration gap unresolved.

## 1. Is spawning the Python CLI a duplicate implementation?

**No—not by itself. It is an adapter calling the existing implementation.** The process boundary is not what determines this; the responsibilities on each side do.

The permitted boundary is:

```text
MCP JSON-RPC framing in Node
→ existing validation, authorization and workspace gates
→ fixed-argv Python process invocation
→ canonical machine-readable Python result
→ existing MCP-envelope validation and transport return
```

Node may:

* Select an explicitly configured `efoundry` executable or resolve it from `PATH`.
* Spawn it without a shell, using fixed command arguments.
* Enforce timeout, output-size and exit-code limits.
* Parse machine-readable output.
* Validate that output against an existing result schema.
* Translate process failures into the existing unavailable/degraded disposition.
* Observe facts that belong exclusively to the installed plugin payload: manifest identity, payload hash, skill inventory/hash, advertised descriptor hash and Node runtime information.

Node must not:

* Read or interpret ledger SQLite, JSONL or artifact files itself.
* Recalculate hash-chain validity or ledger integrity.
* Query the FTS database directly.
* Reconstruct Python status from multiple internal files.
* Treat lexical search rows as Atlas, workspace-map or claim semantics.
* Compile any durable plan.
* Manufacture artifact or receipt identifiers.
* Infer a workspace from the current working directory or a nearby repository checkout.

Those prohibited actions would duplicate Python-owned behavior. Calling `NoeticLedger.verify()` through `efoundry ledger verify`, for example, leaves verification authority in Python and is not duplication.

The bridge should consume **structured output, not scrape human CLI text**. An already-existing JSON mode should be used. If none exists, adding a machine-readable output option to an existing command can remain an adapter-only change when it merely serializes an already-defined application result. It must not add a sixth CLI subcommand or redefine the five-command table. If no existing result type can be mapped to the frozen MCP result without inventing fields or meanings, that mapping is a **SPEC_GAP**.

## 2. How far the binding should go now

### Bind now: the two existing tools

`foundry.status` should combine independently labelled observations from:

* The Node plugin payload: actual plugin identity/version, skill inventory presence and integrity, actual MCP catalog identity, and Node runtime availability.
* The optional Python bridge: actual `efoundry status` output and only those Python facts already represented by the frozen status schema.
* Workspace-backed components: only when a workspace is explicitly and canonically bound.

`foundry.health` should report real checks rather than constants. It may include ledger verification and length where the existing health contract already has that meaning, using the Python-owned `ledger verify` implementation. Registry integrity or index availability may also be reported only where existing schema fields authorize them.

Do not make full ledger verification part of MCP startup. Run it lazily on the health call that requests it, with a bounded timeout. `initialize`, `ping`, and `tools/list` should remain pure Node and should spawn zero Python processes.

Values such as `release_level: "SPEC_BUNDLE"` are acceptable only when they are read from an authoritative packaged manifest and the existing field means declared package metadata. They must not substitute for an observed kernel, workspace or runtime state.

### Do not bind any of the eleven yet

Python availability is only a transport prerequisite. It does not prove that a particular T01 domain port exists.

| T01 tool                  | Decision now  | Reason                                                                                                                           |
| ------------------------- | ------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| `foundry.session.get`     | `UNAVAILABLE` | No FORGE session store or session read projection is identified. Runtime status is not session state.                            |
| `foundry.artifact.get`    | `UNAVAILABLE` | The canonical schema registry is package data, not a generic workspace artifact store/read model.                                |
| `foundry.claim.get`       | `UNAVAILABLE` | No claim store or claim projection is identified in the existing surface.                                                        |
| `foundry.atlas.query`     | `UNAVAILABLE` | SQLite FTS lexical results are not an Atlas snapshot or Atlas query result.                                                      |
| `foundry.passport.get`    | `UNAVAILABLE` | No passport state or passport read projection is identified.                                                                     |
| `foundry.replay.diff`     | `UNAVAILABLE` | Ledger verification and ledger length do not calculate a replay diff.                                                            |
| `foundry.map.query`       | `UNAVAILABLE` | No workspace-map snapshot exists. Lexical index statistics or query hits are not a workspace map.                                |
| `foundry.frame.compile`   | `UNAVAILABLE` | No frame compiler plus append-only plan-artifact store and receipt path is identified.                                           |
| `foundry.search.plan`     | `UNAVAILABLE` | `retrieve query` performs retrieval; `retrieve build` mutates an index. Neither compiles and persists the canonical search plan. |
| `foundry.parliament.plan` | `UNAVAILABLE` | No corresponding compiler, artifact store and receipt path is identified.                                                        |
| `foundry.validation.plan` | `UNAVAILABLE` | `efoundry validate` validates a supplied object; it does not compile and persist a validation plan.                              |

In particular:

* Do not route `retrieve query` into `foundry.atlas.query` or `foundry.map.query`.
* Do not route `validate` into `foundry.validation.plan`.
* Do not use ledger verification as `foundry.replay.diff`.
* Do not expose `retrieve build` through a pure-read tool; it is a write.
* Do not return a successful planning envelope unless the domain compiler, canonical schema validation, append-only artifact persistence and required receipt all exist.

Thus, the Python bridge makes the current two tools genuinely useful, but it does **not** activate any of the eleven merely because Python happens to be installed.

## 3. Required behavior when Python or workspace state is missing

The server should distinguish four conditions rather than collapsing them into an empty result:

| Observed condition                                                             | Truthful disposition                                                                                             |
| ------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------- |
| Python executable/package is absent                                            | Python-backed component is `UNAVAILABLE`, with the existing reason field identifying the missing bridge/runtime. |
| Python exists but no canonical workspace is bound                              | Runtime capability may be reported as present, but workspace-backed state is `UNAVAILABLE`.                      |
| Python times out, exits unsuccessfully, or emits malformed/incompatible output | `UNAVAILABLE`, not empty and not ready; include the existing explicit degradation/error reason.                  |
| Python returns only part of the required projection                            | `DEGRADED`, with the missing component identified.                                                               |
| An authoritative, complete projection successfully returns zero records        | `EMPTY_CONFIRMED`.                                                                                               |

`EMPTY_CONFIRMED` must never mean “Python was missing,” “the database could not be opened,” “the workspace was unknown,” or “the process timed out.”

For `foundry.status` and `foundry.health`, a truthful composite in the common missing-Python case is:

```text
plugin_payload_component: READY
mcp_transport_component: READY
python_runtime_component: UNAVAILABLE
workspace_read_model_component: UNAVAILABLE
overall_read_model_state: DEGRADED
```

That overall `DEGRADED` state is justified because useful, real Node observations exist while optional or workspace-backed components are missing. It should not be a hardcoded constant: if the Node payload probe also fails, the result must change accordingly.

For the unbound tools:

* A `PURE_READ` tool returns its canonical unavailable envelope, no data and `receipts: []`.
* A `DURABLE_PLAN_ARTIFACT` tool returns its canonical unavailable/error disposition, with **no artifact and no receipt**.
* A missing backend must not produce zero counts, empty arrays presented as authoritative, placeholder IDs or successful plan-shaped objects.

Use only existing error and degradation vocabulary. If the frozen schemas do not have a way to distinguish “bridge missing,” “workspace unbound” and “backend failed,” that absence is a **SPEC_GAP**; Node should not invent private error codes.

Workspace selection also needs to remain fail-closed. The bridge may use an existing explicit workspace binding from host metadata or installed configuration. It must not assume that the plugin installation directory, process working directory or nearest repository is the intended workspace. If no canonical binding mechanism currently exists, workspace-backed observations remain unavailable.

## 4. Should unavailable tools be advertised?

**For this T01 surface, advertising them is better than omitting them.**

The frozen contract defines exactly thirteen tools—nine pure-read and four durable-plan tools—and the transport declares a stable tool list. Backend readiness should therefore be represented in the result envelope, not by shrinking the catalog.

This gives an agent three distinct and useful meanings:

* **Not in the canonical catalog:** the operation does not exist on this surface.
* **Canonical but unauthorized for this caller:** authorization denial.
* **Canonical and authorized, but its required backend is not bound:** `UNAVAILABLE`.

The current two-tool catalog conflates the second and third cases: an authorized agent calling a canonical but unadvertised tool receives `UNAUTHORIZED`, even though the actual problem is absent implementation or state. That is less truthful.

The catalog should therefore remain static across environments. Do not dynamically add or remove tools when Python appears or disappears. Dynamic discovery would make agent planning nondeterministic, conflict with the stable-list declaration and allow stale capability assumptions. Readiness belongs in `foundry.status`, `foundry.health`, and each tool’s own response.

This is not a general rule that every imagined future tool should be advertised. It applies because these thirteen tools are already the frozen T01 catalog. Advertising an unavailable tool does not claim that its read model or compiler has been implemented, and it must not receive delivery credit merely for having a descriptor and an unavailable handler.

## Approved minimum increment

The narrow implementation boundary is:

1. Keep the packaged Node server and its zero-checkout startup unchanged.
2. Replace hardcoded status and health facts with real plugin-local observations.
3. Add a lazy, one-shot `efoundry` bridge for structured `status` and, where already semantically authorized, `ledger verify`.
4. Preserve the exact five-command CLI table; do not add a new bridge command.
5. Advertise the canonical thirteen tools statically.
6. Return explicit unavailable dispositions for all eleven currently unbound tools.
7. Do not call `retrieve query` or `retrieve build` from any T01 tool in this increment.
8. Do not add a Python runtime copy, repository-path fallback, new domain result shape or shared-contract change.

This is an architecture decision only; no implementation or test execution is claimed.

### Authority sources
