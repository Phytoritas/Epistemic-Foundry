# K02 parser-adapter gap review

Continue as an advisory reviewer for Epistemic Foundry v4. Determine the
smallest truthful next action for K02 using the authority and current-source
facts below. Return exactly one of `AUTHORIZED_LOCAL_REPAIR`, `SPEC_GAP`, or
`NO_BLOCKER`, followed by only material findings and the minimal safe change.
Do not ask to run tests and do not treat prior package reports as authority
over current source.

## Authority

- `MASTER_SPEC.md` names K02 “GROBID/Docling and fallback parser adapters”.
- `manifests/development_manifest.yaml` gives K02 sole write scope
  `python/epistemic_foundry/ingest/parsers/**`, depends only on the current K01
  PASS package, and requires parser versions pinned and disagreement retained.
- `workflows/corpus_ingest.workflow.yaml` requires parser disagreement to be
  retained rather than silently erased. Its deterministic reconciliation node
  additionally requires reading-order conflicts recorded, no source text
  invented, and a deterministic reconciliation hash.
- That workflow names the parser executor refs
  `epistemic_foundry.ingest.grobid:parse` and
  `epistemic_foundry.ingest.docling:parse`. Those module/symbol paths do not
  exist. K02's authorized directory contains only
  `python/epistemic_foundry/ingest/parsers/**`, so it cannot create the named
  sibling module paths without a manifest/workflow authority change.
- ADR-005 says GROBID and Docling are complementary and neither parser output
  is automatically document truth; reconciliation/QC is required.

## Current implementation

`python/epistemic_foundry/ingest/parsers/adapters.py` is a deterministic,
process-local output adapter. It explicitly does not launch parser services.
It validates caller-supplied `ParserPin` values, immutable output artifacts,
normalized GROBID/Docling/fallback streams, fallback state, and cross-parser
comparison records.

Five bounded K02-local repairs are now on disk:

1. `ArtifactEnvelope` claims an immutable bytes snapshot, but
   `_bytes_snapshot` returns an `isinstance(value, bytes)` input unchanged.
   A hostile `bytes` subclass therefore remains caller-defined and can
   override `.lower()` or `.decode()` after its buffer was content-hashed.
   The GROBID path calls `artifact.payload.lower()` before XML parsing and the
   JSON paths call `payload.decode()`. This can make validation operate on
   caller-controlled projections rather than the hashed base bytes. The repair
   detaches every bytes-like input through a base `memoryview` snapshot to an
   exact built-in `bytes` value before hashing and storage.

2. `_differing_fields` compares kind, text hash, locator, reading order, links,
   row headers, and column headers, but omits the normalized element's
   `confidence`. If two streams differ only in confidence, the address is
   reported in `agreement_addresses` and no `ParserDisagreement` retains that
   difference, even though confidence is part of each observation projection
   and stream hash. The repair includes exact normalized JSON-number/null
   confidence comparison.

3. `_json_object` uses default `json.loads`, so repeated object keys are
   silently collapsed before exact-field validation. A content-addressed
   Docling/fallback artifact can therefore contain two `parser_version`,
   `profile_hash`, or element-field members while the adapter validates only
   the last projection. The repair rejects duplicate keys during parsing,
   keeps the raw artifact bytes unchanged, and rejects non-finite JSON
   constants at that same strict boundary.

4. Finite-number normalization previously allowed an oversized JSON integer
   to raise raw `OverflowError` during float conversion. It now normalizes
   primitive numeric subclasses through base methods and converts overflow or
   other conversion failure into the existing typed `PARSER_OUTPUT_INVALID`.

5. The existing GROBID DTD/entity refusal scanned raw lowercased bytes, so an
   ordinary UTF-16/32 XML encoding inserted NUL code units between the ASCII
   declaration characters. The repair removes those encoding NULs only for the
   declaration probe before calling `ElementTree`; the immutable source bytes
   themselves are neither decoded nor changed. DTD/entity declarations remain
   a typed `GROBID_UNSAFE_XML` failure.

## Decision requested

Decide separately but under one final verdict:

- Are the five implemented changes genuine K02-local correctness repairs under
  the frozen “disagreement retained” and immutable-artifact boundary?
- Does the missing canonical `ingest.grobid:parse` / `ingest.docling:parse`
  production execution surface make full K02 completion a shared-contract
  `SPEC_GAP`, while still allowing the bounded adapter repairs?
- Identify any more important current-source defect that makes a repair unsafe
  or mis-scoped. Do not invent parser execution, effect receipts,
  provider configuration, or new workflow semantics inside K02.
