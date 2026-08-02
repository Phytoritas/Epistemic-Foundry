# Node workspace boundaries

`packages/*` is the explicit Node workspace root. Each child is a private
component scaffold with a public package name. Cross-component dependencies
use those package names and must never reach into another component's `src/`
tree.

The package manifests establish boundaries only; they do not claim that the
target Node runtimes are implemented. B02 owns toolchain and lockfile pinning,
and later work packages own each component's source and generated output.

`boundary-policy.json` is the deterministic layer/dependency policy consumed
by `@epistemic-foundry/repo-checks`.
