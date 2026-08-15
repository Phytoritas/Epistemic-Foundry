# Decision

Repair the release inventory gate **now**.

The correct minimum is not merely to add a few entries to `NON_BUNDLE_PREFIXES`. The inventory must become a single, shared **bundle-selection function** with three rules:

1. Always exclude proven local/generated trees.
2. Include authored repository content.
3. Treat `artifacts/` and `.codex/` as mixed-content namespaces with explicit inclusion rules.

Then generate a candidate `PACKAGE_MANIFEST.json`, review every delta, and replace the committed manifest only after the diff is fully explained.

The two unambiguous new prefix exclusions are:

```python
"node_modules/",
".ruff_cache/",
```

Do **not** add either `".codex/"` or `".github/"` as blanket exclusions.

---

## 1. Exact prefix decisions

| Root            | Decision                        | Reason                                                                                                                                                  |
| --------------- | ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `node_modules/` | Exclude unconditionally         | Installed dependency tree; not authored bundle content.                                                                                                 |
| `.ruff_cache/`  | Exclude unconditionally         | Disposable tool cache.                                                                                                                                  |
| `.codex/`       | Mixed; do not blanket-exclude   | The bundle has historically shipped authored `.codex/agents/*.toml` files. Exclude undeclared local Codex state, but retain the authored agent subtree. |
| `.github/`      | Include                         | CI workflows are authored, versioned project content, and `.github/workflows/**` is an explicit work-package write surface.                             |
| `artifacts/`    | Mixed; handle outside the tuple | Include only explicitly declared evidence files, not the entire tree.                                                                                   |

The shared tuple should become:

```python
NON_BUNDLE_PREFIXES = (
    ".git/",
    ".ai-bridge/",
    ".rah/",
    ".venv/",
    "__pycache__/",
    ".pytest_cache/",
    ".ruff_cache/",
    "node_modules/",
    "build/",
    "dist/",
    "docs/architecture/",
    "src/",
    "tests/",
)
```

### `.codex/` requires a positive rule

The minimum currently evidenced authored subtree is:

```python
CODEX_BUNDLE_PREFIXES = (
    ".codex/agents/",
)
```

The selector should apply:

```python
if relative_path.startswith(".codex/"):
    return any(
        relative_path.startswith(prefix)
        for prefix in CODEX_BUNDLE_PREFIXES
    )
```

That retains project-agent definitions and excludes unrelated repository-local Codex state. Any other authored `.codex/` child must be added explicitly after inspection; it should not become shippable merely because it lives under `.codex/`.

For `.github/`, no special rule is needed. Leaving it outside `NON_BUNDLE_PREFIXES` correctly includes authored workflows and configuration.

The two unconditional exclusions account for only **721 of the 10,418** missing files. They correct checkout contamination, but they cannot explain the stale manifest by themselves.

---

## 2. `artifacts/` should use the declared subset

Choose the middle option:

> Include only existing files whose exact repository-relative paths are declared under `work_packages[*].evidence_artifacts` in `manifests/development_manifest.yaml`.

Do not include all 8,826 artifact files, and do not exclude all evidence.

The intended rule is:

```python
if relative_path.startswith("artifacts/"):
    return relative_path in declared_evidence_paths
```

For example, Z02 presently declares these exact files:

```text
artifacts/work_packages/Z02/report.json
artifacts/work_packages/Z02/commands.jsonl
artifacts/work_packages/Z02/review.md
```

The following must remain excluded unless separately declared:

```text
artifacts/work_packages/Z02/report.json.bak
artifacts/work_packages/Z02/tmp/debug.log
artifacts/work_packages/Z02/test-results/arbitrary-output.xml
artifacts/work_packages/Z02/proof/unlisted-file.json
```

### Important semantic distinctions

`write_scope` is **not** a shipping allowlist. A package may be authorized to write an entire evidence directory while naming only three canonical release-facing evidence files.

Likewise, declaration and requiredness are separate:

* The inventory selector includes an exact declared evidence path when the file exists.
* The current release gate determines whether its absence is blocking.
* A future or inactive package does not create a phantom manifest entry merely because its future evidence path is declared.
* Evidence required for the current `SPEC_BUNDLE` must remain visibly missing when absent; it must not be represented by an empty substitute.

The path parser should reject absolute paths, `..`, path escape, and ambiguous wildcard expansion.

If any current `evidence_artifacts` value is a directory, glob, or prefix rather than an exact file path, and no expansion semantics are already frozen, that is:

> **SPEC_GAP — evidence-artifact path expansion semantics**

Do not recursively expand such an entry by assumption.

### Preserve recursive-manifest self-exclusion

Continue excluding:

```text
PACKAGE_MANIFEST.json
MANIFEST.sha256
```

from the recursive file list. The manifest cannot meaningfully hash itself as one of its own inputs.

---

## 3. Regenerating `PACKAGE_MANIFEST.json` is correct—but not automatic repair

Regeneration does not defeat drift detection when it is a controlled release action.

The distinction is:

### Legitimate regeneration

Regeneration is legitimate when:

* the bundle-selection policy was deliberately corrected;
* authored bundle content genuinely changed;
* declared evidence was intentionally added or replaced;
* every old-versus-candidate manifest delta is classified;
* there are zero unexplained entries.

This repository qualifies because the committed manifest predates substantial authored content and the selector also misclassifies local dependency/cache trees.

### Papering over drift

Regeneration is not legitimate when the only rationale is:

> “Validation failed, so rewrite expected values from whatever is currently on disk.”

That would absorb untracked caches, accidental outputs, tampered files, and unexplained changes into the trusted baseline.

### Required two-phase behavior

`tools/validate_spec_bundle.py` must remain read-only.

`tools/build_release.py` should produce a candidate manifest first. Before replacing the committed root manifest, classify every delta into one of:

```text
AUTHORED_BUNDLE_CHANGE
DECLARED_EVIDENCE_CHANGE
INVENTORY_POLICY_CHANGE
NEWLY_EXCLUDED_LOCAL_STATE
UNEXPLAINED
```

Replacement is authorized only when:

```text
UNEXPLAINED count == 0
```

The candidate review should confirm, at minimum:

* `node_modules/**` and `.ruff_cache/**` disappear because of the corrected policy;
* undeclared `artifacts/**` disappear;
* declared evidence appears when present;
* authored `packages/**`, `python/**`, `plugins/**`, `docs/**`, `.github/**`, and authorized `.codex/**` entries appear or change for explained reasons;
* no unrelated local output enters the manifest.

The committed manifest should therefore be regenerated in the same reviewed change as the selector correction. It should not be regenerated before the selector is frozen.

---

## 4. Neither existing script should be the authority

Create one pure shared module:

```text
tools/release_inventory.py
```

Both scripts should import it:

```text
tools/build_release.py
    → iter_bundle_files(...)
    → hashes selected files and constructs the candidate manifest

tools/validate_spec_bundle.py
    → iter_bundle_files(...)
    → compares the observed set and bytes with the committed manifest
```

Do not make the validator import the builder. A builder may stage files, write outputs, normalize archives, or perform other effects. The shared authority should be side-effect-free.

A suitable narrow public surface is:

```python
NON_BUNDLE_PREFIXES: tuple[str, ...]
CODEX_BUNDLE_PREFIXES: tuple[str, ...]

def load_declared_evidence_paths(repo_root: Path) -> frozenset[str]:
    ...

def is_bundle_path(
    relative_path: str,
    *,
    declared_evidence_paths: frozenset[str],
) -> bool:
    ...

def iter_bundle_files(repo_root: Path) -> tuple[Path, ...]:
    ...
```

The selection order should be exact:

```python
def is_bundle_path(
    relative_path: str,
    *,
    declared_evidence_paths: frozenset[str],
) -> bool:
    if relative_path in {"PACKAGE_MANIFEST.json", "MANIFEST.sha256"}:
        return False

    if relative_path.startswith("artifacts/"):
        return relative_path in declared_evidence_paths

    if relative_path.startswith(".codex/"):
        return any(
            relative_path.startswith(prefix)
            for prefix in CODEX_BUNDLE_PREFIXES
        )

    return not any(
        relative_path.startswith(prefix)
        for prefix in NON_BUNDLE_PREFIXES
    )
```

`iter_bundle_files()` should own normalization, deterministic sorting, regular-file checks, and path-containment checks. The builder and validator must not each add private filtering afterward.

This makes the authority relationship clear:

```text
development_manifest.yaml
    owns exact evidence declarations

tools/release_inventory.py
    owns deterministic bundle selection

PACKAGE_MANIFEST.json
    is the generated snapshot

build_release.py
    produces the snapshot

validate_spec_bundle.py
    verifies the snapshot
```

---

## 5. Ownership is a SPEC_GAP

The two existing tool files and the root manifest lack a declared current write owner. That is:

> **SPEC_GAP — release inventory implementation and generated-manifest ownership gap**

Assign them to **Z02**, whose existing title and exit criteria already cover deterministic bundle production, SBOM, signing, clean extraction, and provenance.

The smallest amendment is:

```yaml
- id: Z02
  phase: P25-Z
  phase_title: Zero-trust release and lifecycle
  title: SBOM, signing, provenance and deterministic bundle
  depends_on:
  - Z01
  write_scope:
  - release/**
  - scripts/release/**
  - tools/build_release.py
  - tools/validate_spec_bundle.py
  - tools/release_inventory.py
  - PACKAGE_MANIFEST.json
```

Do not use:

```yaml
- tools/**
```

That would grant unnecessarily broad authority.

Z02 may own both builder and validator code because they must share one inventory contract. That does not give Z02 independent release-approval authority. Z04 can continue consuming the results at the final gate without owning the selector implementation.

Add `MANIFEST.sha256` to Z02 only when the current tools actually generate or rewrite that root file and no existing owner already covers it.

No shared canonical schema or frozen MCP catalog change is required for this selected correction.

---

## 6. This is the right next increment

Yes. This gate should be repaired before adding another domain store or MCP binding.

A release-integrity gate that routinely fails on disposable checkout state creates three bad incentives:

* real release drift becomes indistinguishable from cache noise;
* developers learn to ignore or bypass the check;
* subsequent genuine plugin capabilities cannot receive trustworthy final-byte attestation.

The selected work is bounded:

```text
manifests/development_manifest.yaml
tools/release_inventory.py
tools/build_release.py
tools/validate_spec_bundle.py
PACKAGE_MANIFEST.json
```

It restores a real capability:

> Given an accepted source state and bundle profile, the repository can deterministically select the intended files, construct a reviewed final-byte manifest, and later detect unexplained byte or membership drift.

That is more valuable now than implementing another unavailable domain store behind a release gate whose signal is known to be unreliable.

## Approved minimum increment

1. Accept the Z02 ownership amendment.
2. Add only `"node_modules/"` and `".ruff_cache/"` to the unconditional prefix tuple.
3. Keep `.github/` eligible as authored bundle content.
4. Retain only explicitly authorized `.codex/` subtrees, beginning with `.codex/agents/`.
5. Make `artifacts/` exact-declaration-gated through `work_packages[*].evidence_artifacts`.
6. Extract all selection behavior into `tools/release_inventory.py`.
7. Make both existing tools call the same `iter_bundle_files()`.
8. Produce and inspect a candidate manifest.
9. Replace `PACKAGE_MANIFEST.json` only after every delta is classified and unexplained deltas are zero.

No implementation or test execution is claimed here.

### Local authority anchors
