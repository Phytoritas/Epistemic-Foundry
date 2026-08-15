# Epistemic Foundry v4 — the `python/` vs `src/` split

Same conversation as the last question. Your previous answer selected K03's
`SourceSpan` producer as the next step, on the stated ground that
`epistemic_foundry.ingest.spans:emit` is missing. I checked, and that premise is
half right in a way that changes the decision. Details below; the question at the
end is what I actually need.

## What I found after your answer

`emit` is not missing. `python/epistemic_foundry/ingest/spans/emitter.py` is a
30 KB implementation with 36 passing tests recorded in K03's evidence, and
`from epistemic_foundry.ingest.spans import emit` resolves when `python/` is on
`sys.path`.

What is true is your second point: it is unreachable from the shipped runtime.
`pyproject.toml` packages only `src`:

```toml
[tool.setuptools.package-dir]
"" = "src"
[tool.setuptools.packages.find]
where = ["src"]
[tool.pytest.ini_options]
pythonpath = ["src"]

[tool.epistemic-foundry.workspace]
python_runtime_root = "src/epistemic_foundry"
python_component_root = "python/epistemic_foundry"
component_source_imports = "forbidden"
```

`packages/boundary-policy.json` repeats this and adds
`python.duplicateImplementationPolicy: "forbidden"`.

So this is not one missing producer. It is a structural split, and K03 is one of
its 25 instances.

## The census

A full read-only census of the current tree found:

**Volume.** `python/epistemic_foundry/` holds 1,196,132 bytes across 53
production files in 11 top-level subpackages: contracts, ingest, intake,
ontology, parliament, reasoning, reassessment, retrieval, storage, tools,
validation.

**Executor reachability.** Of 350 workflow nodes, 265 name a Python
`module.path:symbol` executor. Resolving each against the two roots separately:

| resolves in | refs |
|---|---|
| `src` only | 24 |
| both trees | 12 |
| `python/` only | 5 |
| neither | 224 |

The five `python/`-only refs are `ingest.spans:emit`
(`corpus_ingest.workflow.yaml:309`), three `retrieval.planning` entry points
(`compile_query_plan`, `seal_search_lane_receipt`, `reconcile_search_run`, at
`evidence_retrieval.workflow.yaml:123,691,907`), and
`validation.reconcile:evidence` (`validation_execution.workflow.yaml:429`) —
though that last one names a symbol that exists in neither tree; the public API
is `reconcile_evidence`, so its ref may simply be wrong.

The 224 that resolve in neither tree are the honest measure of how much of the
workflow layer is still specification.

**Duplicate module identity.** Four dotted paths now exist in both trees, which
the declared `duplicateImplementationPolicy: forbidden` prohibits:
`epistemic_foundry.contracts`, `epistemic_foundry.ingest.registry` (both export
`register_document`), `epistemic_foundry.retrieval`, and
`epistemic_foundry.retrieval.lanes` (a package in one tree, a module file in the
other).

**Manifest split.** 24 work packages declare write_scope only under
`python/epistemic_foundry/**`; 43 declare only `src/epistemic_foundry/**`; O02
declares both, because I corrected it by hand in the previous turn.

**No promotion path exists.** `python/README.md` calls the tree a "staged
monorepo transition" component root and forbids duplicates, but names no
package, command, or owner for consolidation. B01's report defers it to a "later
package" that was never created. B05/B06 own only `build/v4_b05|b06/**`. The
actual build materializer copies only `schemas/` and `openapi/` into
`src/epistemic_foundry/_canonical`; it never moves component source. No workflow
node and no repo-check performs or verifies a promotion. The repo checks only
detect that both roots exist and that duplicates are forbidden.

## Why I am not just moving files

Three reasons I want your decision rather than my own:

1. Moving 1.2 MB across 24 unowned packages is not a bounded work package, and
   every one of those packages has sealed evidence (report.json, commands.jsonl,
   review.md) whose recorded paths would become wrong.
2. The four duplicate module identities are not identical implementations. At
   least `ingest.registry` has two different versions of `register_document`.
   Consolidating them is a semantic merge, not a move.
3. `component_source_imports = "forbidden"` and
   `duplicateImplementationPolicy = "forbidden"` are declared policy. Whatever
   happens has to end with both satisfied, and I do not know which tree the
   policy intends to survive.

## The question

**What is the authoritative resolution of the two-tree split, and what is the
single bounded next step under it?**

Specifically:

1. Which tree survives as canonical Python source? If `src`, then `python/` is
   1.2 MB of unreachable code awaiting migration. If `python/`, then packaging
   is wrong and `pyproject.toml` must change. If both legitimately coexist,
   explain what makes `python/` reachable at runtime, because I could not find
   it.

2. Who owns the decision and the migration? No work package currently declares
   `manifests/development_manifest.yaml` in its write_scope — I assigned it to
   A04 this turn, alongside the `acceptance_matrix.yaml` it already owned, since
   A04 is the A-phase integration package. Tell me if that is wrong.

3. What is the migration unit? Per work package, per subpackage, or one
   consolidation package? What happens to the sealed evidence of a package whose
   files move — is it re-attempted, or does the evidence record the move?

4. What is the single bounded step I should do next under that resolution? If it
   is still K03, say so and say what makes it bounded given that 24 packages
   share the same defect. If the split must be resolved first, name the smallest
   first increment.

5. Is `validation.reconcile:evidence` (`validation_execution.workflow.yaml:429`)
   simply a wrong ref for `reconcile_evidence`, or does it name something that
   should exist? That one looks like a plain defect I could fix cheaply, but the
   workflow file is not in any write_scope I hold.

Constraints: no embedding models, no network dependencies, no external services.
Local determinism is hard. I will verify by running the real chain, so state the
observable outcome that proves the step worked and the one that proves it only
appeared to work. Name one step, not a roadmap. If something requires a
shared-contract change outside a single write_scope, say so explicitly — that is
a `SPEC_GAP` I must stop on rather than improvise.
