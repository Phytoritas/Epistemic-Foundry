# B04 integration review record

Status: `SPEC_GAP_WITH_RECORDED_PROCEDURE_DEVIATION`

Review mode: `USER_AUTHORIZED_SELF_REVIEW`

The user prohibited subagents and authorized the independent-review steps to
be handled directly. The author therefore performed the integration-review
role. This record does not claim independent assurance, and the procedure
deviation does not waive a failed build gate.

Reviewed input and failure bindings:

- B02 report: `98abe689dbfb9399d2f50f87a18376ca9a85ed4a50c938513778e312e3e67dad`
- B03 report: `baa07e997402a290f2602cea39a78a1acdeeb69dd7ea8c89331c84e78976338f`
- `pyproject.toml`: `347e1a8a544735cf24b40da807f5f23ef301b8fd5ca5f40a5982be97cd9d4708`
- `src/epistemic_foundry/contracts/registry.py`: `21e970e7b9db7c98b4bfd7a21cc82a4848f62ab542ca986aed3dbe6ebc1790d4`
- `toolchains/toolchain-lock.json`: `ee07ad9b59cb2cd03607276f46d863c1a4154e1842a77457d19fea16a9a70ede`
- deterministic wheel: `fb6f1b7fe5452118108656fc66d05b78db026d1be9735e91c597e1aeec150014`

Review confirmed:

1. B02 and B03 remain `PASS`, all of their declared checks resolve to success,
   and all declared output artifacts exist.
2. With the B02 `SOURCE_DATE_EPOCH`, the B04 probe rebuilds the exact Python
   wheel already recorded by B02.
3. The isolated source path executes `status`, reports version `4.0.0`, retains
   the honest `SPEC_BUNDLE` / `PARTIAL_IMPLEMENTATION` labels, and loads all
   124 canonical schemas.
4. The deterministic wheel contains zero `*.schema.json` files. When extracted
   outside the repository, its identical command fails with `SchemaNotFound`
   because the installed registry resolves a nonexistent sibling `schemas/`
   directory.
5. Therefore source and distribution exit codes and outputs differ, and B04's
   non-waivable `build_smoke` and source/dist convergence criterion fail.
6. The smallest correct repair needs packaging metadata to include one
   canonical schema resource bundle and runtime registry logic to resolve that
   installed resource without duplicating schema authority.
7. The manifest assigns `pyproject.toml` to B01, `schemas/**` to C01, and B04
   only `artifacts/work_packages/B04/**`; it assigns no dependency-ready work
   package both `pyproject.toml` and
   `src/epistemic_foundry/contracts/registry.py`. Expanding scope would invent
   a shared contract, which the authority rules forbid.

Finding: one blocking `SPEC_GAP`.

Required resolution:

- Authorize and record a work-package scope that covers Python packaging
  metadata plus installed-runtime schema resource resolution, then rerun B02
  reproducibility evidence and B04 source/dist smoke.

Decision: B04 is not integrated and downstream packages that require B04 are
not dependency-ready. This is a truthful typed blocker, not a release or
runtime-readiness claim.
