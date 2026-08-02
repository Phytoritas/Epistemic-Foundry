# B03 review record

Status: `PASS_WITH_RECORDED_PROCEDURE_DEVIATION`

Review mode: `USER_AUTHORIZED_SELF_REVIEW`

The user prohibited subagents and authorized the independent-review steps to
be handled directly. The author therefore performed the contract-review role.
This record does not claim independent assurance.

Reviewed implementation hashes:

- `.github/workflows/ci.yml`: `cb296023a66880b758fee201f0bd3a51a8a29943e8bea8cdb96b6694e22108fa`
- `scripts/ci/ci_matrix_lint.py`: `580fa21b83325dbec00e623d0779edfb0008f3c269e51a465a4fbb541c902606`
- `scripts/ci/cache_key_audit.py`: `151fcfbb182e62967503e6e5a987dc4875949efd40f2ba58c4d67c093360b449`
- `scripts/ci/test_ci_policy.py`: `1b76fae609a1a259ae305439938f8d1940af11e0bd43d08b67309c8938d8fb4d`
- `docs/cache_contract.md`: `d64a2331ae8f2db076903eed3058b301ec2d2d9f98e6edcb115d2d9de9557f3d`
- `artifacts/work_packages/B03/ci-matrix-lint.json`: `5a13f9b1de1913a589950bbb6a307de7f979b1bf96bfabd30274bda7a4b54b14`
- `artifacts/work_packages/B03/cache-key-audit.json`: `265e056fed569fec46b190cac99d63ce3c7a63047a20074033cb764cb19dfc4d`

Review confirmed:

1. The workflow defines exactly three versioned runner lanes:
   `ubuntu-24.04`, `macos-15`, and `windows-2025`.
2. Workflow permissions are exactly `contents: read`; checkout persistence is
   disabled; `pull_request_target`, ignored failures, and moving action tags
   are rejected.
3. Checkout, Node, Python, uv, and cache actions are allowlisted at reviewed
   full commit SHAs, occur exactly once, and their tool versions match the B02
   toolchain lock.
4. The matrix runs the lock check, locked dependency installation, CI-policy
   validators, structure and boundary checks, the complete Python test suite,
   and the independent double-build comparison on every lane.
5. Only npm and uv dependency data below `runner.temp` is cached. Source,
   tests, build products, evidence, `.rah`, credentials, holdouts, and ledger
   material are excluded.
6. Cache identity binds the versioned OS label, architecture, Node and Python
   locks, the toolchain lock, and hashed Python build constraints. Prefix
   restore and cross-OS archives are disabled; cache misses are non-fatal.
7. Ten mutation tests demonstrate fail-closed rejection of the reviewed drift
   cases, including duplicate approved actions and canonical-output caching.
8. Both machine-readable B03 reports pass with empty failure lists; workspace
   boundaries, all 789 Python tests, and the 11-artifact reproducible build
   remain green.
9. Evidence artifacts contain no user or temporary absolute path.
10. Documentation explicitly distinguishes disposable cache acceleration from
    canonical state and does not claim that hosted runners executed.

Findings: none.

Scope limits retained for later packages:

- B03 proves the workflow and cache-policy definitions by local static and
  mutation checks. It does not prove a GitHub-hosted run on the three OS
  images.
- B04 owns the source/dist convergence gate, machine-readable phase
  reconciliation, and any available hosted-run evidence.
- Z-phase packages own SBOM, signing, clean-release extraction, and release
  provenance. B03 makes no release-readiness claim.
