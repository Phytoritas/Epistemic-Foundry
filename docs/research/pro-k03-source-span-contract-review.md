# K03 SourceSpan contract review

Continue as an advisory reviewer for Epistemic Foundry v4. Review the current
K03 implementation against repository authority. Return `NO_BLOCKER`,
`AUTHORIZED_LOCAL_REPAIR`, or `SPEC_GAP`, followed only by material findings
and the smallest safe changes. Do not ask to run tests.

## Authority and scope

- K03 is “SourceSpan emission for text/table/figure/formula”, depends only on
  current K01 PASS, and solely owns
  `python/epistemic_foundry/ingest/spans/**`.
- Exit criteria: a span hash resolves to source; page/bbox/char locators are
  typed.
- `schemas/source-span.schema.json` is canonical. It explicitly permits
  `page` as integer >=1 or null. When page is null, its `allOf` requires
  `coordinate_system == "not_available"` and `bbox == null`. Character ranges
  remain required, so a char-resolvable span without page geometry is a valid
  representation.
- `workflows/corpus_ingest.workflow.yaml` names the existing importable
  `epistemic_foundry.ingest.spans:emit` entry point and requires span hashes to
  verify against normalized source, typed locators, and orphan refusal.

## Current implementation and bounded delta

`emitter.py` captures an immutable normalized source snapshot, derives
verbatim text/hash/span ID from its char slice, emits exact schema projections,
and verifies document version, provenance, source hash, slice, text hash, and
span ID on resolution.

The prior dataclasses and persisted-record parser required `page` to be a
positive integer, making the schema-defined null-page branch impossible. The
current delta changes candidate/span page to `int | None`, accepts null only
with `not_available` plus null bbox, preserves that value through emission and
mapping restoration, and keeps positive-integer validation otherwise.

The same delta also:

- detaches text subclasses with `str.__str__` and bytes-like content through a
  base `memoryview(...).tobytes()` snapshot before hashing/decoding;
- converts bbox numeric subclasses through base primitives and maps oversized
  or non-finite values to the existing typed input error instead of leaking a
  raw conversion exception.
- snapshots a persisted caller Mapping exactly once through a primitive-first
  recursive JSON walker, rejects duplicate projected keys, cycles, bytes,
  non-string keys, non-finite values, and all other non-JSON values, then
  validates only the owned snapshot;
- preserves an empty or edge-whitespace `section` string because the canonical
  schema has no `minLength` or pattern for that nullable string.

## Remaining questions

1. Is the null-page repair exactly required by the canonical schema, or does a
   higher source authorize the previous integer-only narrowing?
2. Are the persisted-Mapping snapshot and exact schema-compatible `section`
   changes correctly scoped, or does a higher source contradict either one?
3. Is there a current path that can still mint a span whose ID/hash does not
   resolve to the exact document/version/provenance/source slice, or reject a
   canonical schema-valid page/bbox/char locator without higher authority?

Do not invent storage, parser reconciliation, effect receipts, or a new source
locator unit. Distinguish a K03-local validator defect from any genuinely
missing shared contract.
