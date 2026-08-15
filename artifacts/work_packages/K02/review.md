# K02 package review record

Standing verdict: `PASS` (from attempt `0001`).

This file is the package-level projection the manifest requires. The
attempt review below, at `attempts/0001/review.md`, is the primary record.

---

# K02-0001 parser-adapter adversarial review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_ADVERSARIAL_REVIEW`

Final verdict: `PASS`

Blocking K02 findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_REVIEW`

Actor independence: `false`

The product owner requires serial primary-session execution without Fleet or
subagents. This review is procedurally separate from implementation, but it is
not actor-independent certification.

## Findings

1. K02 is an output-validation boundary, not a claim that GROBID, Docling, or
   a fallback backend was installed or executed. It performs no network,
   subprocess, CWD, repository-root, or source-tree discovery.
2. Every parser requires a closed role, exact non-floating version/revision,
   immutable executable digest, adapter version, and profile hash. Output must
   echo the sealed version and profile or fail `PARSER_PIN_OUTPUT_MISMATCH`.
3. GROBID TEI bytes remain retained and content-addressed; malformed XML and
   DTD/entity declarations become typed failures. Docling JSON is closed and
   preserves page/bbox, reading order, tables, cells, captions, figures, and
   formulas without inventing absent values.
4. Each element retains source-artifact, parser-artifact, parser identity,
   text hash, and a page or character locator. Captions require an addressable
   target, and table cells require both row and column header addresses.
5. A successful primary cannot be replaced by fallback output. Primary FAIL or
   BLOCKED remains visible when fallback is used; the terminal result is
   `PARTIAL`, not a fabricated PASS. Failed or unavailable fallback remains
   typed and no stream is selected.
6. Cross-parser comparison never chooses a truth value. The fixture has
   6 explicit disagreements, retains both
   GROBID and Docling paragraph observations, and records missing observations.
   Stream permutation produces the same comparison hash.
7. Deterministic fixture checks pass 40/40,
   full Python passes 1054/1054, full Node
   passes 470/470 across 54 files, and contract
   codegen remains 126 schemas / 126 examples.
8. The initial 39/40 fixture failure and incomplete 39-file/366-test Node run
   are preserved as diagnostics. Neither was presented as final evidence; the
   fixture classification was corrected and the authoritative Node inventory
   was expanded to the sealed 54-file baseline.
9. Structure, boundaries, scoped Ruff, and `git diff --check` pass. K02 product
   writes are confined to `python/epistemic_foundry/ingest/parsers/**`; prior
   reports, RAH generations, and the dirty worktree remain preserved.

## Assurance boundary

K02 proves deterministic validation and comparison of caller-supplied immutable
parser outputs. It does not claim live backend qualification, parser service
availability, K03 SourceSpan emission, K04 ingest release, the full product,
actor-independent certification, or production readiness. Global
`implementation_gate=fail` and `completion_ready=false` remain required.

Bound adapter version: `4.0.0-k02.1`.
