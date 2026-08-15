# Decision

**There is no authoritative two-tree migration resolution in the current contract set.** The repository is therefore at `SPEC_GAP` for source consolidation.

Operationally, however, the existing configuration is unambiguous: `src/epistemic_foundry` is the install, CLI, test, and runtime root; `python/epistemic_foundry` is a non-importable component root. The missing contract is the rule that promotes, merges, or retires component code. `MASTER_SPEC.md` requires unresolved shared semantics to stop as `SPEC_GAP`, while `pyproject.toml` and the boundary policy already select `src` for runtime and prohibit direct component imports and duplicate implementations.   

The resolution that should be made authoritative is:

> **`src/epistemic_foundry` survives as the sole canonical Python implementation root. `python/epistemic_foundry` becomes transition-only source inventory and must be drained, semantically reconciled where necessary, and retired.**

The **single next step is not K03 migration**. It is an **A01 corrective successor attempt that freezes this source-root and migration contract in `MASTER_SPEC.md`**. No implementation file should move in that step.

---

## 1. Which tree survives

### `src/epistemic_foundry` survives

The current runtime facts already converge on `src`:

* setuptools discovers packages only under `src`;
* pytest adds only `src`;
* the `efoundry` entry point imports the installed `epistemic_foundry` package;
* the workspace explicitly calls `src/epistemic_foundry` the `python_runtime_root`;
* the boundary policy independently calls it `runtimeRoot`;
* `python/epistemic_foundry` is called the component root, and component-source importing is forbidden.  

Therefore, adding `python/` to `PYTHONPATH` proves that component code can execute in an artificial development environment. It does **not** prove that the shipped Foundry runtime implements that code.

Changing `pyproject.toml` so that `python/` becomes the packaged root would not resolve the defect. It would merely reverse it:

* the existing `src`-only implementations would become unreachable;
* the four nonidentical duplicate module identities would still need semantic reconciliation;
* all runtime, CLI, packaging, and test assumptions currently attached to `src` would be inverted;
* the policy’s distinction between runtime root and component root would become false rather than repaired.

Historical v3 material did describe `python/epistemic_foundry` as the scientific core. That explains how the split arose and why the component tree cannot be discarded as accidental debris. It does not supply the missing v4 promotion mechanism, and it cannot override the current runtime configuration. 

### The two trees do not legitimately coexist as two runtime roots

They may coexist **physically during migration**, but only under these restrictions:

* `python/` is not packaged, imported, or workflow-resolved;
* code present only there is reported as staged or unshipped, not runtime-implemented;
* no dotted module identity exists in both roots;
* no workflow node is marked bound merely because its callable resolves after manually injecting `python/` into `sys.path`.

The current tree violates that transitional condition because duplicate identities exist. The boundary checker treats each duplicate module path as an explicit failure and also rejects `sys.path` mutation or filesystem-based source-import bypasses. 

No compatibility solution should package both roots, use namespace-package merging, create symlinks, mutate `sys.path`, or copy component source into the runtime during startup. Each would hide the missing migration contract rather than satisfy it.

---

## 2. Ownership of the decision and migration

The ownership split should be:

| Responsibility                                                | Owner                                          | Boundary                                       |
| ------------------------------------------------------------- | ---------------------------------------------- | ---------------------------------------------- |
| Select the surviving root and freeze migration semantics      | **A01**                                        | `MASTER_SPEC.md`                               |
| Maintain the development-manifest projection after delegation | **A04**                                        | `manifests/development_manifest.yaml`          |
| Maintain Python build and root-boundary mechanics             | **B01**                                        | `pyproject.toml`, root/boundary infrastructure |
| Select semantic behavior for migrated code                    | **Original owning work package**               | Its own module and tests                       |
| Reconcile a duplicate whose implementations differ            | **The semantic owner or all affected owners**  | Explicit merge decision; no path-based winner  |
| Independently approve each migration attempt                  | Existing package reviewer/integration reviewer | New evidence, not rewritten old evidence       |

A01 owns `MASTER_SPEC.md` and the authority/status vocabulary. A04 is an integration package, but its previously declared scope was only its evidence directory; B01 owns the build scaffold and broad root mechanics.  

### Your A04 assignment

Assigning `manifests/development_manifest.yaml` to A04 is **the right intended postimage**, but it is **not yet self-authorizing**.

The development manifest cannot grant a package authority to edit the development manifest when the missing authority is the question being decided. That would be circular. An older audit also treated A04 as the integration owner of the A–Z development manifest, so A04 is not an arbitrary choice; the defect is the absence of a current higher-authority delegation. 

The A01 source-root amendment should therefore state that:

> A04 is the steward of the development-manifest projection and may reconcile exact package paths, dependencies, and integration ownership, but it does not acquire semantic ownership of every package whose paths it projects.

Until that A01 delegation exists, treat your A04 write-scope addition as **provisional**. It must not be used to authorize the first code migration.

B01 likewise must not perform the semantic consolidation merely because it owns `python/**` at the scaffold level. B01 can enforce root mechanics and eventually retire the obsolete root declaration, but it cannot choose between two different `register_document` implementations or decide what K03’s emitter means.

---

## 3. Migration unit and sealed evidence

### Migration unit: original work package

The migration unit is **per original work package**, not per top-level subpackage and not one repository-wide consolidation package.

A top-level subpackage such as `ingest` or `retrieval` may contain work owned by several packages. Migrating it as a unit would silently transfer semantic authority. Conversely, one mega-package moving all 1.2 MB would be able to choose winners among K03, O02, V04, and unrelated owners without satisfying those packages’ acceptance contracts.

Within each package migration, a **dotted module identity is atomic**:

```text
accepted src postimage
+ retirement of the corresponding python implementation
+ package tests
+ installed-runtime import test
+ workflow-resolution test where applicable
+ duplicate-identity census
+ successor evidence
```

A migration must not temporarily leave the accepted implementation in both roots. For a duplicate such as `epistemic_foundry.ingest.registry`, the owning package must compare semantics and produce one accepted `src` implementation. Neither “the newer file,” “the larger file,” nor “the already packaged file” automatically wins.

Where two work packages plausibly own different sides of a duplicate, migration stops at `SPEC_GAP` until exact semantic authorship and merge responsibility are assigned.

### Existing sealed evidence remains immutable

The existing K03 evidence is not retroactively false. It proves that, in that recorded attempt:

* the component implementation existed at the recorded path;
* the recorded tests ran under the recorded environment;
* the recorded hashes and results were observed.

What it does **not** prove is current installed-runtime reachability.

Therefore, moving a package creates a **successor attempt**; it does not rewrite the old attempt.

The successor evidence must record at least:

```text
predecessor attempt/evidence identity
old path and content hash
new path and content hash
migration classification: BYTE_PRESERVING_MOVE | SEMANTIC_MERGE
selected semantic postimage and rationale
retired source paths
installed-wheel module origin
rerun test commands and results
workflow executor-resolution result
duplicate-module census
approved behavioral differences, if any
independent review
```

This follows the Foundry’s existing migration principle that old artifact IDs and hashes remain intact and new migration records reference rather than overwrite them. 

For a byte-identical move, prior semantic tests may remain predecessor evidence, but package tests, installed-runtime tests, workflow binding, and source-retirement checks must run again. For a semantic merge, the affected package must rerun its complete acceptance boundary and independent review.

If the current evidence layout has only one fixed sealed `report.json`, `commands.jsonl`, and `review.md` with no already-authorized successor-attempt carrier, that is another `SPEC_GAP`. Do not overwrite those files and do not invent a new `attempts/<id>` convention locally.

---

## 4. The single bounded next step

## A01 corrective source-root authority freeze

**Owner:** `A01`
**Normative file:** `MASTER_SPEC.md`
**Evidence:** the already-authorized append-only A01 successor-attempt mechanism only
**Code moved:** none
**Workflow changed:** none
**Manifest migration dispatched:** none

The amendment should freeze exactly this contract:

```text
PYTHON SOURCE-ROOT AUTHORITY

1. src/epistemic_foundry is the sole canonical installable, testable,
   workflow-resolvable, and distributable implementation root for the
   epistemic_foundry namespace.

2. python/epistemic_foundry is transition-only component-source inventory.
   Presence or tests under that root do not establish shipped-runtime
   implementation.

3. Runtime or build bridges that package both roots, add python/ to sys.path,
   merge the roots through namespace-package behavior, use symlinks, or copy
   component source at runtime are forbidden.

4. Consolidation is executed per original work package. One dotted module
   identity is migrated atomically: accepted src postimage, old implementation
   retirement, tests, runtime binding, duplicate scan, and successor evidence.

5. Nonidentical duplicate implementations require an explicit semantic merge
   by the owning package or affected owners. Path, timestamp, packaging status,
   or test volume does not select the winner.

6. Prior package evidence remains immutable historical evidence. Every move or
   merge creates a linked successor attempt; no sealed report or receipt is
   rewritten.

7. A04 is the development-manifest integration steward. A04 may project exact
   paths and dependencies but does not inherit package-domain semantics.

8. B01 owns source-root and build mechanics only. The original work package
   retains semantic implementation ownership.

9. Until migration is complete, python-only executors are unbound in the
   shipped runtime, and duplicate dotted identities remain policy failures.

10. Ambiguous semantic ownership, merge behavior, evidence continuation, or
    shared-workflow ownership returns SPEC_GAP.
```

This is a shared-contract change. If A01 cannot legally open a successor attempt, or if no append-only evidence carrier is authorized, stop there with `SPEC_GAP`.

### Why this precedes K03

Moving K03 now would implicitly decide all of the following without authority:

* that `src` is the final root;
* how old sealed evidence survives a path move;
* whether a moved package is reopened or merely relabeled;
* who may alter the development manifest;
* whether duplicate implementations are copied, replaced, or merged;
* whether `python/` remains an allowed source after migration.

K03 is bounded only **after** those rules are frozen. Its 36 passing tests establish useful predecessor evidence, but they do not grant repository-wide migration semantics.

---

## 5. Observable verification

### Outcome that proves the A01 step worked

A read-only verification of the resulting revision should observe all of these:

1. `git diff --name-only` contains only:

   * `MASTER_SPEC.md`; and
   * already-authorized A01 successor evidence files.

2. The specification-bundle validator passes.

3. An independent reviewer can derive these exact values from `MASTER_SPEC.md`, without consulting `pyproject.toml` or a work-package note:

   ```text
   canonical_python_root = src/epistemic_foundry
   component_root_disposition = TRANSITION_ONLY_UNSHIPPED
   migration_unit = ORIGINAL_WORK_PACKAGE
   atomic_identity = DOTTED_MODULE
   duplicate_resolution = EXPLICIT_SEMANTIC_MERGE
   prior_evidence_disposition = IMMUTABLE_PREDECESSOR
   manifest_steward = A04
   build_root_owner = B01
   ambiguous_case = SPEC_GAP
   ```

4. A clean wheel still contains only the `src`-derived package, and importing `epistemic_foundry` reports a location under the installed wheel or `src`, never under repository `python/`.

5. The executor census remains unchanged—for example, the five `python/`-only references do **not** suddenly become bound. A contract-freeze step is not supposed to improve runtime reachability.

6. The current duplicate identities remain visible as unresolved migration debt rather than being allowlisted or suppressed.

That result proves that the repository now has a non-circular authority under which a later package migration can be judged.

### Outcome that proves it only appeared to work

Treat the step as false closure if any of these occurs:

* K03 becomes importable only because `PYTHONPATH=python` was set;
* setuptools packages both roots;
* a symlink, import hook, `.pth` file, namespace package, or `sys.path` mutation bridges the roots;
* `duplicateImplementationPolicy` is weakened, removed, or allowlisted;
* files are copied into `src` while their active `python/` implementations remain;
* an old sealed K03/A01 report is edited in place;
* only the A04 manifest row changes, with no higher-authority A01 delegation;
* the executor-resolution count improves during this contract-only step;
* a package is called “migrated” because its path changed even though its installed-runtime origin and workflow invocation were never tested.

---

## 6. `validation.reconcile:evidence`

The current reference is definitely **not a valid bound executor**: the workflow names `epistemic_foundry.validation.reconcile:evidence`, and the executor census reports that reference unresolved. 

It is not yet safe to classify it as merely a spelling error.

There are two legitimate postimages:

1. **Wrong workflow reference**

   This applies only if `reconcile_evidence` already implements the canonical executor boundary: it accepts the workflow’s invocation contract and returns or seals the required `ResultEnvelope`. Then the correct reference is:

   ```text
   epistemic_foundry.validation.reconcile:reconcile_evidence
   ```

2. **Missing executor adapter**

   If `reconcile_evidence` is a business-level function that accepts validation results or domain objects rather than `NodeInvocation`, then `evidence` may have been intended as a thin executor adapter that validates the invocation, loads inputs, calls `reconcile_evidence`, persists outputs, and constructs the envelope.

Do **not** add this solely to make attribute resolution green:

```python
evidence = reconcile_evidence
```

That could turn a missing-symbol failure into a callable that has the wrong input, output, persistence, or receipt semantics.

The proving test is:

```text
clean installed wheel
→ resolve exact module:symbol
→ invoke with schema-valid NodeInvocation
→ validate returned ResultEnvelope
→ verify required evidence-class and failure semantics
→ replay same immutable input
→ obtain identical deterministic business result/hash
```

Import success alone is the false-positive oracle.

There is also an ownership gap. V04 owns only `python/epistemic_foundry/validation/reconcile/**`, while W01 owns the workflow compiler, not the semantic contents of `validation_execution.workflow.yaml`.   K01 demonstrates the explicit pattern used when a domain package is allowed to change both its source and its canonical workflow; that corresponding grant is absent here. 

Therefore, do not fix this reference cheaply in the current turn. It is a real executor-binding defect, but changing the workflow is presently an unowned shared-contract edit and must remain `SPEC_GAP` until its semantic workflow owner is assigned.
