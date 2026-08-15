# RECOMMENDED PATCH — ratify defensible ownership now; keep closure at `SPEC_GAP`

Adopt the ownership invariant and checker now, add every mapping supported by the fresh census, and deliberately leave genuinely ambiguous files unmapped. Do **not** wait for universal assignment before establishing the rule, but do not call the resulting state closed or `PASS`.

This requires a one-time product-owner bootstrap because `MASTER_SPEC.md` outranks the manifest, while A01’s current `write_scope` does not include `manifests/development_manifest.yaml`. After that bootstrap, A01 becomes the continuing authority for ownership declarations; individual packages must not self-expand their scopes. The master already requires `SPEC_GAP` for missing shared semantics and forbids treating specification text as implementation evidence.  A01 is constitutionally the authority-chain package, but its present manifest scope omits the manifest itself.  

## 1. Exact EF4-I65 wording

Change the Part II heading from `64` to `65`, then append this immediately after EF4-I64:

```markdown
### EF4-I65 — Canonical Python production-source ownership

Every Git-tracked regular `.py` file under `src/epistemic_foundry/` has exactly one work-package owner declared by `manifests/development_manifest.yaml` `write_scope`. Zero ownership is `SPEC_GAP`; ownership by more than one distinct work package is `FAIL`. Ownership is a maximum change-authorization boundary within the package's already-declared responsibility; it neither makes a path a required deliverable nor proves implementation, acceptance, or coverage by a prior `PASS`.
```

This is intentionally limited to the current canonical Python runtime source tree. It does not claim ownership closure for JavaScript/TypeScript, `python/epistemic_foundry/**`, tests, tools, migrations, or other repository roots.

The current master explicitly stops at EF4-I64, so this is a constitutional addition rather than a correction that can be inferred locally.  

## 2. Exact `production_source_ownership_rule`

Add this top-level key to `manifests/development_manifest.yaml`, between `execution_policy` and `work_packages`:

```yaml
production_source_ownership_rule:
  invariant_id: EF4-I65
  authority_owner_work_package: A01
  enforcement_owner_work_package: B01
  owner_projection: work_packages[*].write_scope
  production_source_universe:
    repository_state: git_tracked
    root: src/epistemic_foundry
    file_type: regular
    suffix: .py
  write_scope_semantics: maximum_authorization_boundary
  absent_scope_semantics: dormant_authorization_not_delivery
  delivery_evidence:
  - exit_criteria
  - required_checks
  path_matching:
    representation: repository_relative_utf8_forward_slash
    case_sensitive: true
    unicode_normalization: none
    exact_entry: exact_match_only
    recursive_entry_suffix: "/**"
    recursive_entry: descendants_only
    other_globs: forbidden
    filesystem_resolution: forbidden
  tracked_generated_source: included
  present_untracked_source:
    ignored: FAIL
    nonignored: FAIL
  symlink_entry_or_component: FAIL
  zero_owner: SPEC_GAP
  multiple_distinct_owners: FAIL
  historical_pass_extension: forbidden
```

Also add this exact path to A01’s `write_scope`:

```yaml
- manifests/development_manifest.yaml
```

That edit is the one-time owner-ratified bootstrap. Thereafter:

* A01 owns changes to the rule and to work-package ownership mappings.
* B01 owns enforcement only.
* A source package may propose a mapping but cannot authorize its own expanded scope.
* No dependency edge changes are required.

## 3. Meaning of `write_scope`

Select **(a): `write_scope` is a maximum authorization boundary**, not a mandatory deliverable set.

More precisely:

* A matching scope is necessary for a package to modify a path, but it does not independently authorize semantics outside that package’s title, dependencies, exit criteria, and higher authority.
* An absent exact path means the package is authorized to create that exact path when its existing responsibility requires it. Its absence does not mean incomplete delivery.
* An absent `root/**` means descendants may later be created under that root. Neither the root nor any particular descendant is mandatory merely because the scope exists.
* Delivery is established by `exit_criteria` and `required_checks`, followed by resolving evidence and independent review—not by path existence or by the breadth of `write_scope`.
* An implementation consolidated into a differently named file is not required to create placeholder files for absent scope entries. The actual implemented path must instead be explicitly assigned before further package-owned changes occur.
* An absent scope may be pruned later, but its absence from disk is not itself a checker error.

This resolves the A05 ambiguity without introducing a second `deliverable_paths` field across 156 packages.

## 4. Apply defensible mappings now

Add at least these four exact entries:

```yaml
# L01
- src/epistemic_foundry/memory/policy.py

# O02
- src/epistemic_foundry/retrieval/lexical_index.py
- src/epistemic_foundry/retrieval/lanes.py

# C03
- src/epistemic_foundry/domain/hashing.py
```

The assignments align with the packages’ already-declared responsibilities: L01 governs memory policy, O02 governs lexical and relation retrieval, and C03 governs runtime compatibility and canonical hash identity.   

The earlier `76 defensible / 39 unresolved` result must not be imported as a current count. Apply every additional mapping only when the fresh current-tree census provides an exact path-to-owner row and the existing package responsibility supports it. The four rows above are immediately executable; all unprovided rows remain unratified.

The gate must intentionally return `SPEC_GAP` while any current production file has zero owners. A partial mapping is useful progress, but it is not ownership closure.

### Directory-level assignments

A cohesive directory may be assigned to an existing package as `path/**` when all of the following are already true:

1. The package title and exit criteria expressly cover the whole subsystem.
2. Every current file below the root has that same responsibility.
3. The root does not contain shared infrastructure or another package’s responsibility.
4. The new scope creates no multiple-owner result.
5. The assignment is explicit in the manifest; the checker never infers it from module names, imports, or proximity.

Therefore not every ambiguous file needs a new package. A new owner decision is needed only when no existing package responsibility defensibly covers the file. Mixed directories should use exact-file entries. The four immediate mappings above should remain exact; they must not be broadened into catch-all `memory/**`, `retrieval/**`, or `domain/**` ownership.

## 5. B01 checker contract

Add one independent checker:

```text
packages/repo-checks/check_production_source_ownership.py
```

B01 already owns `packages/**` and repository/package-boundary checking, so the checker requires no further B01 path expansion.  Add only:

```yaml
# B01 exit_criteria
- every tracked canonical Python production source resolves to exactly one work package

# B01 required_checks
- production_source_ownership_check
```

The checker should be separate from the JavaScript import lexer. Git-index enumeration, YAML authority parsing, lexical path matching, and owner cardinality are a different contract from parsing JS/TS import syntax.

### Deterministic behavior

1. **Authority input**

   Read only the repository-root `manifests/development_manifest.yaml`. Parse it as data; do not import or execute repository Python, JavaScript, build hooks, or plugins. No network access.

2. **Repository root**

   Obtain the root from Git. If Git or the repository root is unavailable, return `BLOCKED`. Do not guess a root from the process working directory.

3. **Tracked universe**

   Enumerate:

   ```text
   git ls-files --stage -z -- src/epistemic_foundry
   ```

   Include exactly index modes `100644` and `100755` whose strict UTF-8, repository-relative path:

   * starts with `src/epistemic_foundry/`;
   * ends with `.py`;
   * contains no NUL, backslash, empty segment, `.` segment, or `..` segment.

   `__init__.py` files and direct as well as nested descendants are included.

4. **Symlinks and special entries**

   Any tracked symlink, submodule entry, or symlink encountered in the source root or any path component is `FAIL`. Do not follow or resolve symlinks. A tracked source missing from the working tree or materialized as a non-regular file is also `FAIL`.

5. **Untracked files**

   Walk the source root lexically with `lstat`, without following symlinks. Any present regular `.py` file absent from the Git index is `FAIL/UNTRACKED_PRODUCTION_SOURCE`, whether Git-ignored or nonignored. It is not added to the ownership universe because no manifest mapping can make untracked source authoritative.

6. **Generated files**

   Generated status supplies no exemption. A generated `.py` under the source root must be tracked and owned exactly once. An untracked generated `.py` fails under the preceding rule.

7. **Scope grammar**

   Permit only:

   * an exact repository-relative path; or
   * a repository-relative root ending in the literal suffix `/**`.

   Reject absolute paths, backslashes, repeated slashes, trailing slashes other than `/**`, `.`, `..`, `*` outside the final `/**`, `?`, character classes, braces, and non-UTF-8 entries.

8. **Matching**

   * Exact entries match only byte-identical paths.
   * `root/**` matches direct and nested descendants of `root`, never a sibling prefix.
   * Matching is case-sensitive.
   * Perform no Unicode normalization, case folding, `realpath`, path aliasing, or filesystem glob expansion.
   * Count distinct work-package IDs. Two matching entries within the same package still constitute one owner; duplicate identical scope entries should separately fail manifest validation.

9. **Outcomes**

   Apply this precedence:

   ```text
   BLOCKED
     Git or required authority input cannot be accessed.

   FAIL
     Invalid manifest/rule/scope syntax;
     source-root or path symlink;
     tracked source missing or wrong type;
     present untracked source;
     or at least one multiple-owner source.

   SPEC_GAP
     No FAIL condition exists, but at least one tracked source has zero owners.

   PASS
     Every source in the universe has exactly one owner and no other violation exists.
   ```

   Suggested process exits are `0=PASS`, `1=FAIL`, `2=SPEC_GAP`, and `3=BLOCKED`.

10. **Output**

    Emit one deterministic JSON object to stdout containing:

    ```text
    status
    universe_count
    owned_count
    zero_owner_paths
    multiple_owner_paths with sorted owner IDs
    invalid_paths
    untracked_paths
    symlink_paths
    ```

    Sort paths by their UTF-8 bytes and owner IDs lexically. Emit no timestamp, machine-specific absolute path, random value, or audit artifact. The checker itself must not write a report or make a package `PASS` claim.

## 6. Historical package `PASS`

Historical reviews remain immutable and retain only their original meaning:

* A report that reviewed exact files, hashes, checks, and claims remains historical evidence for those exact subjects.
* Adding a file to a package’s `write_scope` does not retroactively add that file to an old review subject.
* A newly assigned file remains unproved for that package until a new bounded implementation/review attempt explicitly covers its bytes and relevant exit criteria.
* An absent authorized path does not become a historical deliverable and cannot make an old report claim that the path existed.
* A historical package-level `PASS` cannot be extended from “the files actually reviewed” to “every path now authorized.”
* Any source binding or review whose subject included the old development-manifest bytes remains historical; it must not be rewritten or presented as a current-manifest review.

This follows the existing rule that evidence or traceability presence alone never proves runtime effectiveness. 

## Exact patch responsibilities

| File                                                                                                 | Authority/responsibility                              | Change                                                                                                                                                   |
| ---------------------------------------------------------------------------------------------------- | ----------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `MASTER_SPEC.md`                                                                                     | Product-owner constitutional decision, thereafter A01 | Change `64` to `65`; append exact EF4-I65 text.                                                                                                          |
| `manifests/development_manifest.yaml`                                                                | One-time product-owner bootstrap, thereafter A01      | Add top-level rule; add the manifest to A01 scope; add reviewed ownership mappings; add B01 criterion/check.                                             |
| `manifests/product_invariants.yaml`                                                                  | A02 projection                                        | Change the normative anchor and contiguous range to I01–I65; append I65 with evidence references to the manifest and checker and owner packages A01/B01. |
| `packages/repo-checks/check_production_source_ownership.py`                                          | B01                                                   | Implement the deterministic checker above.                                                                                                               |
| All schemas, workflows, runtime source, canonical projections, tests, reports and evidence artifacts | Unchanged                                             | No change in this slice.                                                                                                                                 |

`manifests/product_invariants.yaml` currently fixes I01–I64 and requires every invariant to resolve to verification checks, while the acceptance matrix currently reports only 64 traceable invariants.   Therefore `traceable_invariant_count` must remain `64` in this slice; changing it to `65` would be an unsupported closure claim.

The remaining condition is explicitly:

> **`SPEC_GAP`: EF4-I65 is not closed until every tracked source in its exact universe has one owner, S04 adds the I65 verification binding to `manifests/requirements_traceability.yaml`, the B01 checker has an independent review, and the acceptance authority can truthfully advance the traceable-invariant count.**

S04 already owns the requirements-traceability file and its active development-manifest source binding, so neither A01 nor B01 may fabricate that downstream closure. 
