# C02-0004 generated-contract projection review

Package recommendation: `PASS`

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW`

Assurance limitation: `actor_independence=false`. Fleet and subagents are
forbidden by the active product-owner execution contract, so this is a
procedurally separate primary-session review.

## Contract and generated projection

- The canonical generator projects exactly 127 schemas and 127 matching
  examples into nine generated artifacts across Python, TypeScript, and UI.
- All seven previously stale generated files now match deterministic replay.
  The three manifests are byte-identical, Python exposes 127 models, the
  Node/Python fixture check passes, TypeScript 5.9.3 strict compilation
  passes, and active legacy promotion values are absent.
- Root schemas and examples were not modified by C02-0004. Generated outputs
  were produced by the canonical generator rather than hand editing.

## Regression and boundary

- Full Node: 819/819
  PASS with no failure, skip, todo, or cancellation.
- Full Python: 1056 passed and
  17 failed. The complete sorted failure
  records, including multiplicity, exactly match sealed C01-0009. They are
  the authorized B04-0009 projection-count debt; C02-owned and new failures
  are zero. The earlier `uv run pytest` collection result was diagnostic-only
  and was replaced by the repository-authoritative `python -B -m pytest` run.

Blocking C02-owned findings: 0. Write-scope violations: 0. C02-0004 may PASS
and B04-0009 becomes dependency-ready. This does not establish fresh package
projection, O02-0002, C04 conformance, final packaging, repository-wide green
status, release readiness, or product completion. `implementation_gate=fail`
and `completion_ready=false` remain.
