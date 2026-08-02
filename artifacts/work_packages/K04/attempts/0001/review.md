# K04-0001 corpus security and ingest-quality adversarial review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW`

Final verdict: `PASS`

Blocking K04 findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_REVIEW`

Actor independence: `false`

The product owner requires serial primary-session execution without Fleet or
subagents. This review is procedurally separated from implementation, but it is
not actor-independent certification.

## Findings

1. PDF, web-page, and dataset instruction-like text is passed to the actual S01
   trust-boundary runtime. It stays non-executable data, cannot become an
   instruction, approval, policy change, or capability grant, and forged
   authority sidecars fail before sealing.
2. A clean injection scan and even a `trusted` extraction label do not confer
   authority. The assembled model context has no `instructions` or `messages`
   channel and contains only runtime-branded data segments.
3. The actual release integrity runtime maps malware, provenance, and tamper
   failures to `QUARANTINE`; extraction, export, and projection remain denied.
   Passive malformed parser output is visibly typed `FAIL`, not falsely called
   `QUARANTINE`, and is likewise not trusted or exported.
4. Integrity scanning precedes all 6
   parser/reconciliation/manifest stages. The deterministic, single-attempt
   quality gate is the sole direct predecessor of projection, and projection
   accepts only PASS manifests.
5. The tests import the existing trust boundary, release integrity runtime, and
   canonical workflow. They contain no test-local substitute runtime and K04
   modifies no schema, workflow, policy, or product runtime authority.
6. K04 targeted tests pass Python
   10/10 and Node
   6/6. Current predecessors pass
   K01 85/85,
   K02/K03 76/76,
   and S01 17/17.
   Full Python passes 1064/1064 and full Node
   passes 476/476 over 55 files; codegen remains
   126 schemas / 126 examples. Structure, boundaries, scoped Ruff, and
   `git diff --check` pass.
7. The initial Node fixture error (2 pass / 4 fail) and obsolete provisional K01
   component run (86 pass / 24 fail) are retained as diagnostics. Neither is
   hidden or reclassified as a product PASS; corrected authoritative runs are
   separately identified and green.
8. Product files are exactly three UTF-8/LF tests under the declared scope.
   No skip/xfail masking, reset, clean, stash, commit, push, Fleet, or subagent
   action was used.

## Assurance boundary

K04 proves the current repository's integration boundary for corpus prompt
injection, integrity quarantine/failure visibility, workflow ordering, and
projection gating. It does not claim that external GROBID, Docling, archive
scanner, metadata resolver, object store, or database services are deployed;
it does not claim actor-independent certification, full product completion,
release readiness, production readiness, or `completion_ready=true`.

Observed malformed-passive status: `FAIL`.
