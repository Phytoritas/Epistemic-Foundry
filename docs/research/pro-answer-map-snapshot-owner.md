# Decision

Amend **M04** to own snapshot assembly, expose the assembler through the **public Node package API**, and bind the existing `foundry.map.query` through a thin cross-language adapter. The first operational profile should be a **query-focused, repository-only, on-demand snapshot**. Do not add a CLI command, a fourteenth MCP tool, or a persisted snapshot store in this increment.

## 1. Snapshot-assembly ownership

This is a **SPEC_GAP — manifest ownership gap**. None of M01–M04 implicitly owns the missing path:

* M01 cannot own assembly because it is upstream of M02 and M03.
* M02 owns only baseline ranking and cannot author query relevance or risk.
* M03 owns query personalization and risk, but does not depend on M02. Assigning assembly to M03 would require both a dependency change and a scope change.
* M04 already depends on **both M02 and M03** and is the M-phase integration and ranking-claim gate. It is the only existing package with the complete dependency closure needed to combine the outputs.

The smallest manifest amendment is one line under M04:

```yaml
- id: M04
  phase: P12-M
  phase_title: Workspace Cartographer
  title: M-phase map UI and ranking-claim gate
  depends_on:
  - M02
  - M03
  write_scope:
  - packages/workspace-map/src/snapshot/**
  - web/src/features/map/**
  - artifacts/work_packages/M04/**
```

The exact added line is:

```yaml
- packages/workspace-map/src/snapshot/**
```

No M01, M02, or M03 dependency or scope needs to change.

This amendment changes an authoritative manifest boundary, so it must be accepted before writing the new source. It does **not** change a shared canonical JSON Schema or the frozen thirteen-tool catalog.

The natural first implementation file is:

```text
packages/workspace-map/src/snapshot/workspace-map-snapshot.mjs
```

with a public function such as:

```js
export async function buildRepositoryWorkspaceMapSnapshot({
  workspaceRoot,
  workspaceId,
  expectedRootHash,
  query,
  includedScopes,
  excludedScopes,
  toolVersions,
  generatedAt,
  mapId,
  snapshotSchema,
}) {
  // inventory
  // edge extraction
  // baseline centrality
  // query personalization
  // risk/change impact
  // canonical projection
  // map_hash
  // schema validation
}
```

It should call the existing modules rather than repeat their validators, vocabularies, ranking logic, or canonical serializer.

A useful internal split would be:

```js
assembleWorkspaceMapSnapshot(...)
buildRepositoryWorkspaceMapSnapshot(...)
```

`assembleWorkspaceMapSnapshot` should be a pure composition function over already-produced inventory, edge, baseline, personalization, and risk results. `buildRepositoryWorkspaceMapSnapshot` should own the bounded filesystem read and freeze/recheck sequence.

The package must expose the assembler through the existing public API of `@epistemic-foundry/workspace-map`. If the package has a closed `exports` map and changing it requires editing:

```text
packages/workspace-map/package.json
```

then that exact file also needs an ownership amendment. Do not broaden the scope to all of `packages/workspace-map/**`. If an existing public entrypoint can re-export the new module without modifying `package.json`, use that narrower route.

## 2. Invocation and the Node/Python boundary

### Selected surface

Use **option (a): a public Node API**, followed by a private machine adapter when `foundry.map.query` is bound.

Do not add:

```text
efoundry map ...
```

Changing the verified five-command CLI table is a **SPEC_GAP** and produces no benefit because the canonical read tool already exists.

Do not add a user-facing Node CLI either. It would create a second command contract that must be documented, packaged, versioned, and kept behaviorally identical to MCP. A private worker executable is different: it is an internal adapter, not an advertised command surface.

### Required ownership split

The responsibilities should remain:

```text
M04 / @epistemic-foundry/workspace-map
    owns map semantics and snapshot assembly

T01 Python application handler
    owns existing MCP validation, authorization, workspace isolation,
    result-state selection, and envelope production

plugin-host adapter
    owns process transport only
```

The end-to-end call should be:

```text
foundry.map.query
→ existing T01 protocol/input/auth/workspace/capability gates
→ injected WorkspaceMap read-model port
→ private packaged Node worker
→ public @epistemic-foundry/workspace-map API
→ WorkspaceMapSnapshot
→ generic schema validation
→ READY / DEGRADED / UNAVAILABLE T01 envelope
```

A concrete private adapter could be sourced at:

```text
packages/plugin-host/src/mcp/read/workspace-map-worker.mjs
```

and bundled into the installed plugin, for example as:

```text
plugins/epistemic-foundry/dist/workspace-map-worker.mjs
```

Its behavior should be mechanically small:

1. Read exactly one request object from stdin.
2. Call the published `@epistemic-foundry/workspace-map` function.
3. Write exactly one result or typed failure object to stdout.
4. Put diagnostics only on stderr.
5. Perform no map ranking, projection, hashing, or scope-policy logic of its own.

The Python read-model adapter can invoke that packaged worker and translate process failures into the existing T01 state model. It must not reproduce any Node algorithm. The workspace root supplied to the worker must come from the already-authorized workspace binding after workspace isolation, not from an arbitrary caller-provided path or the server’s current working directory.

This is not a duplicate implementation:

```text
Python: orchestration and envelope boundary
Node: sole map-domain implementation
```

### What not to do

Do not modify `packages/plugin-host/src/mcp/mcp-server.mjs` to special-case `foundry.map.query` and execute map business logic directly while other tools use the Python handler. The frozen T01 boundary says plugin-host owns framing and calls the common provider-neutral handler surface. Bypassing that handler for one tool would be a **SPEC_GAP — frozen transport architecture change**, even though the tool name itself remains unchanged.

Do not port PageRank, inventory extraction, personalization, risk, canonical serialization, or `map_hash` calculation into Python. That would violate `duplicateImplementationPolicy: forbidden`.

Adding a private Node worker does not change either:

* the five-command `efoundry` table; or
* the frozen thirteen-tool MCP catalog.

## 3. Honest first profile

A repository-only snapshot is legitimate. It must be presented as a **bounded repository projection**, not as complete coverage of every Workspace Cartographer layer.

The minimum honest profile may include:

* recognized code files and import edges;
* schemas and schema-reference edges;
* work-package and declared write-scope entities;
* skills, hooks, or MCP descriptors that the current extractor actually recognizes;
* declared research, dataset, or artifact entities that physically exist and have a supported parser.

The required `included_scopes` and `excluded_scopes` pair does require more than saying “the repository was walked.” That statement identifies a physical root but does not disclose semantic coverage.

The snapshot must say, using the existing frozen `ENTITY_LAYERS`, `SOURCE_CLASSES`, and related vocabulary:

* which entity classes were eligible;
* which edge classes were extracted;
* which repository regions were included;
* which known classes were deliberately excluded;
* which classes could not be parsed by this profile.

Do not invent new free-text scope literals merely for the snapshot. Project the existing vocabulary into the schema’s required shape.

For example, the profile must distinguish among these outcomes:

| Condition                                                | Honest treatment                                              |
| -------------------------------------------------------- | ------------------------------------------------------------- |
| Supported code file successfully parsed                  | Include its declared entity and edges                         |
| Generated, vendor, or test content intentionally omitted | Name its canonical scope in `excluded_scopes`                 |
| Research artifact exists but no extractor supports it    | Exclude that class; do not represent it as searched-with-none |
| File disappears or changes during the frozen scan        | Reject the snapshot rather than mix generations               |
| A requested included scope is only partially readable    | Return `DEGRADED` with the exact reason                       |
| Workspace root cannot be securely resolved or read       | Return `UNAVAILABLE`                                          |

Generated, vendor, and test content may also be included as separately classified entities. The requirement is not necessarily to exclude them; it is to avoid silently mixing them into the same source class as production code.

### Frozen-input minimum

The read should operate over one explicit file manifest:

```text
authorized workspace root
→ enumerate and normalize admissible paths
→ reject path/symlink escape
→ record exact file content hashes
→ compute the frozen root_hash
→ run all extraction and ranking over that exact manifest
→ verify the manifest/root again before returning
```

If the ending root does not match the frozen input, the call should not return `READY`. A mixed-generation graph is not a partial but useful snapshot; its node and edge relationships may never have coexisted. The conservative result is `UNAVAILABLE`, with `data: null` and `receipts: []`.

Thus, “repository-only” is an honest coverage ceiling. “Complete workspace map” is not.

## 4. `query` and `personalization` for a baseline map

The list of required fields does not determine the permitted absence representation. Requiredness only means the member must be present; it does not establish whether its value may be `null`, an empty string, or a tagged object.

The semantic decision is:

* Do **not** use `""` as a generic no-query value. An empty string is still a string value and may be normalized, tokenized, or ranked differently by different implementations.
* Do **not** invent values such as `"baseline"`, `"none"`, `"NO_QUERY"`, or `{ "applied": false }` unless the canonical schema already defines that exact representation.
* Use `null` only when the schema explicitly permits and defines it as absence.
* If the schema contains an existing canonical no-personalization variant, use that exact variant instead of inventing another one.

If neither `query` nor `personalization` can represent absence under the current schema, a global no-query snapshot has a **SPEC_GAP — shared canonical contract gap**. Changing the schema to add `null` or a tagged no-query variant would be a shared-contract change.

That gap need not block the first useful capability. Bind the first profile as **query-focused**:

```text
query
    = the real, non-empty query supplied to foundry.map.query
      after the already-authorized canonical normalization

personalization
    = the actual output or canonical projection of
      computeQueryPersonalization(...)
```

The same rule applies to each node’s required `query_relevance`: publish the real computed value. Do not use a fabricated query merely to fill the field, and do not assign a uniform “neutral” relevance unless the query-personalization module explicitly defines that baseline behavior.

This ordering provides a genuine `foundry.map.query` capability without first reopening the baseline absence representation.

## 5. Persistence versus on-demand computation

A persisted snapshot store is **not required** for the first binding.

`foundry.map.query` may compute a complete snapshot on demand from a frozen authorized workspace input. “PURE_READ” prohibits writes and state drift; it does not prohibit deterministic computation over read-only inputs.

The first implementation may therefore:

* read workspace files;
* construct inventory and edges in memory;
* calculate all three ranking dimensions;
* assemble and validate a schema-valid snapshot;
* return the full snapshot in the tool result.

It must not, during that call:

* write a snapshot file;
* append a ledger event;
* allocate an artifact receipt;
* update a database row;
* refresh a durable cache;
* modify repository or plugin-data timestamps;
* return anything other than `receipts: []`.

A request-local in-memory cache is harmless. A durable cache populated as a side effect of the read is not.

A store becomes necessary only when a separately accepted requirement says that:

* the `map_id` must be retrievable later;
* another call must resolve the same historical snapshot by identity;
* replay must access the exact prior bytes rather than recompute them; or
* map generation is moved to an explicit producer job.

None of those is needed merely to make the existing query tool return a verified snapshot.

### Hash and time behavior

Use one injected `generated_at` value for the entire assembly. Compute `map_hash` only after all other fields have been fixed, using the existing canonical JSON serializer and the schema’s established hash basis.

If `generated_at` participates in `map_hash`, two otherwise identical on-demand calls at different times may legitimately have different hashes. Do not claim identical-input hash stability unless the canonical contract explicitly defines a stable observation timestamp or excludes `generated_at` from the hash basis.

Likewise, use an existing canonical `map_id` generator or derivation. Do not silently invent a new content-ID formula. If the repository has no accepted source for `map_id` issuance, that identity rule is a separate **SPEC_GAP**, although it does not imply that persistence itself is required.

# Approved minimum increment

1. Amend M04 with:

   ```yaml
   - packages/workspace-map/src/snapshot/**
   ```

2. Create:

   ```text
   packages/workspace-map/src/snapshot/workspace-map-snapshot.mjs
   ```

3. Export a single public Node assembly API from `@epistemic-foundry/workspace-map`.

4. Implement the first profile as query-focused and repository-only, with exact included and excluded scope disclosure.

5. Bind the existing `foundry.map.query` through an injected Python read-model port that invokes a private packaged Node worker. Keep all map semantics in Node.

6. Compute on demand and return the full snapshot without persistence, receipts, or state drift.

7. Do not add an `efoundry map` command, public Node CLI, new MCP tool, Python map implementation, or snapshot store.

No implementation or test execution is claimed here.
