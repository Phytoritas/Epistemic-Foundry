# Decision

**Implement K03’s canonical local `SourceSpan` emitter next:** make the existing workflow reference

```text
epistemic_foundry.ingest.spans:emit
```

resolve to a real deterministic producer that converts a registered immutable document plus reconciled parser output into schema-valid, source-resolvable spans for text, table, figure, and formula content.

This is the smallest implementation step that moves the repository toward its central guarantee without pretending that promotion already works. EF4-I02 defines that guarantee as every promoted empirical or documentary claim resolving to immutable `SourceSpan` evidence, and assigns its implementation chain to K03, O03, and Q02. K03 is therefore the first concrete evidence-bearing link, not merely another access surface. 

## Why this outranks the alternatives

### Not more MCP bindings

Binding MCP tools before their producers exist would improve discoverability, not epistemic capability. The constitution explicitly keeps plugin and provider surfaces outside canonical authority. A new MCP handler that merely wraps missing claim or evidence producers would be another honest `UNAVAILABLE` path at best, and an authority inversion at worst. 

Once `SourceSpan` production exists, an MCP read tool can expose a real immutable object. Before that, it can expose only retrieval candidates or specifications.

### Not temporal retrieval

A temporal lane would be useful, but it would require publication-version metadata that is not presently carried, and it would still leave E1 blocked on semantic retrieval. More importantly, it would improve the completeness certificate without creating the immutable evidence atom that downstream claims must resolve to.

The current BLOCKED receipt behavior already protects the system from overstating retrieval completeness. There is no corresponding runtime protection to exercise for claim grounding because the canonical span producer itself is still absent.

### Not the four adversarial lanes as one step

EF4-I06 does make counterevidence, null, boundary, and method lanes mandatory whenever applicable.  But implementing four extraction and query semantics at once is not one bounded package, and the recent BLOCKED-state repair already makes their absence visible and claim-capping rather than silent.

Those lanes cannot yet yield promotable evidence anyway: they can retrieve candidate material, but there is no runtime `SourceSpan` producer to turn selected material into immutable, source-resolvable evidence.

### Not a “trivial” evidence→claim→promotion demonstration

That is the correct strategic milestone, but it is not the correct **single next implementation package**.

A real promotion cannot use a reduced toy gate. A05 requires the exact ordered G00–G14 gate set, the exact 23-node fail-closed promotion workflow, and all specified positive and negative constitutional cases.  The audit also shows both `epistemic_foundry.ingest.spans:emit` and downstream Claim Forge projection producers as missing. 

Calling a claim “promoted” after bypassing those surfaces would demonstrate the opposite of the constitution. Building the whole path now would cross K03, O03, Q02, A05, and presently unbound Claim Forge surfaces; that is an integration program, not one bounded step.

## Exact ownership and file boundary

| Surface                                      | Disposition                                                                         | Owner                                                 |
| -------------------------------------------- | ----------------------------------------------------------------------------------- | ----------------------------------------------------- |
| `src/epistemic_foundry/ingest/spans/**`      | Implement the deterministic producer; package public surface must export `emit`     | **K03**                                               |
| `schemas/source-span.schema.json`            | Read-only governing output contract                                                 | Existing schema owner; no change                      |
| `workflows/corpus_ingest.workflow.yaml`      | Read-only; its existing `emit_source_spans` node already names the correct callable | Existing workflow owner; no change                    |
| K01 document-registration outputs            | Read-only input authority for immutable bytes and provenance identity               | **K01**                                               |
| `artifacts/work_packages/K03/report.json`    | Record resolving implementation evidence                                            | **K03**                                               |
| `artifacts/work_packages/K03/commands.jsonl` | Record exact executable verification                                                | **K03**                                               |
| `artifacts/work_packages/K03/review.md`      | Independent review evidence                                                         | **K03**                                               |
| `manifests/development_manifest.yaml`        | Narrow K03 write-scope repair                                                       | **No package currently declares this file; SPEC_GAP** |

K03 already specifies “SourceSpan emission for text/table/figure/formula,” requires source resolution and typed page/bounding-box/character locators, and names `source_span_roundtrip` and `orphan_span_test` as its checks. But its current write scope incorrectly points to:

```text
python/epistemic_foundry/ingest/spans/**
```

rather than the repository’s real runtime root:

```text
src/epistemic_foundry/ingest/spans/**
```



## Required shared-contract change and stop condition

Before implementation, the K03 row in `manifests/development_manifest.yaml` must receive the narrow additional authorization:

```text
src/epistemic_foundry/ingest/spans/**
```

It must **not** receive a broad grant such as:

```text
src/epistemic_foundry/ingest/**
```

Any new test files must likewise be enumerated exactly in the authorized K03 scope before they are created.

This is a shared-contract change. On the available manifest evidence, **no work package owns `manifests/development_manifest.yaml` itself**. S04 owns only the manifest’s source-binding projection and requirements traceability, not the authoritative manifest file.  Therefore:

> **The selected next package is K03, but code dispatch is presently `SPEC_GAP` until a higher-authority decision assigns or authorizes the narrow development-manifest amendment.**

Do not infer that K03 may edit its own governing row. Do not assign the manifest to S04 merely because S04 refreshes its binding. After the manifest amendment is validly authorized, S04 may own any consequent binding/traceability refresh within its declared scope.

No `SourceSpan` schema change is indicated. The existing contract already carries the required immutable-source identifiers, page/bounding-box and character locators, verbatim-text hash, and parser identity/version.  If implementation reveals that these fields are insufficient to represent one of the four required span kinds without ambiguity, that is a separate schema-owner `SPEC_GAP`; K03 must not invent an extension locally.

## Observable outcome that proves it worked

Run the canonical node boundary against a real local registered document, not a handwritten output fixture.

A successful verification must demonstrate all of the following:

1. **The canonical callable resolves**

   ```python
   from epistemic_foundry.ingest.spans import emit
   ```

   succeeds from the actual installed or repository runtime, and the executor-resolution audit no longer reports `epistemic_foundry.ingest.spans:emit` as `python_module_missing`.

2. **Real bytes are the authority**

   The input identifies a K01-registered immutable source and its provenance manifest. Each returned span resolves back to that exact registered source, not merely to a title, file path, or parser-local document ID.

3. **All four declared content kinds are exercised**

   A deterministic fixture or local document produces representative text, table, figure, and formula spans. Unsupported input must be explicit; silently dropping three kinds while passing a text-only test is not K03 completion.

4. **Locator round-trip succeeds**

   For a text span:

   ```text
   source_text[char_start:char_end] == verbatim_text
   sha256(verbatim_text) == text_hash
   ```

   For layout-bearing spans, the page, bounding box, and coordinate system resolve to the registered source representation and satisfy the canonical schema.

5. **Parser provenance is retained**

   `parser_name` and `parser_version` come from the actual parsed input and participate in the emitted provenance rather than being hard-coded test decorations.

6. **Replay is deterministic**

   Running `emit` twice with byte-identical registered source and canonicalized parser input produces identical ordered output and identical span/artifact hashes.

7. **Negative paths fail closed**

   At minimum, each of these produces a typed refusal and no successful span artifact:

   * unknown or orphaned `provenance_manifest_id`;
   * source bytes changed after registration;
   * character bounds outside the registered text;
   * `verbatim_text` inconsistent with the source slice;
   * mismatched `text_hash`;
   * malformed page or bounding-box locator;
   * unrecognized content kind presented as a supported one.

8. **The package evidence is replayable**

   The K03 `commands.jsonl` contains the exact commands, inputs, exit codes, and hashes; `report.json` records the positive and negative results; and independent review verifies the source resolution rather than merely schema-validating the JSON.

This proves a real immutable evidence-anchor producer. It does **not** yet prove EF4-I02 end to end, Claim Forge completion, corpus-ingest workflow completion, or scientific promotion.

## Observable outcome that proves it only appeared to work

Treat the implementation as a false success if any of the following occurs:

* code is added only under `python/epistemic_foundry/...` while the running namespace comes from `src/...`;
* the canonical audit still reports `epistemic_foundry.ingest.spans:emit` as missing;
* tests validate handcrafted `SourceSpan` JSON but never invoke `emit`;
* a `span_id` and `text_hash` are generated, but the exact source bytes or coordinates cannot be recovered;
* replay changes span order, IDs, or hashes;
* orphaned provenance, altered source bytes, or mismatched text is accepted;
* only text spans work while table, figure, or formula inputs are silently flattened or discarded;
* output is schema-valid only because locators are filled with plausible dummy values;
* the result is advertised as a complete `corpus_ingest.workflow` run while other required nodes remain unbound;
* a downstream object is labeled `PROMOTED` without the exact A05 promotion authority and receipts.

The highest-value next move is therefore **K03’s real SourceSpan producer, preceded only by the narrowly authorized K03 manifest-path correction**. It establishes the first executable object that future claims, adversarial retrieval results, MCP reads, and eventual promotion can all reference without fabrication.
