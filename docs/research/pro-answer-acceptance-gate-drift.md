# Decision

Correct `manifests/acceptance_matrix.yaml` to:

```yaml
canonical_workflow_count: '23'
workflow_node_count: '350'
```

The available evidence indicates that `22/327` was a valid **former bundle snapshot**, while `23/350` is the current accepted specification inventory. The defect is that the acceptance matrix was not reconciled when the bundle changed.

At the same time, remove the duplicated workflow-count authority from `tools/validate_spec_bundle.py`. The validator must compare:

```text
declared inventory pin from acceptance_matrix.yaml
                    versus
observed inventory derived from repository content
```

It must not compare two separately maintained expected-value tables.

Assign `manifests/acceptance_matrix.yaml` to **A04**, not A01, A02, Z02, or Z04. That ownership amendment is a **SPEC_GAP** and must precede or accompany the count correction.

The 179 unrelated uncommitted files do not need to be resolved before this correction. They must remain excluded from `PACKAGE_MANIFEST.json` regeneration.

---

## 1. The correct direction is 22/327 → 23/350

The decisive evidence is cumulative:

* The earlier verified bundle really had 22 workflows and 327 nodes.
* The current `MASTER_SPEC.md` enumerates 23 workflows and states a 350-node total.
* The deterministic maturity-projection design explicitly says that the acceptance matrix is stale until it is reconciled to 23 workflows and 350 nodes.
* Your current parser independently observes 23/350.
* The delta is internally exact: one additional workflow and 23 additional nodes.

That is not the pattern of an arbitrary hardcoded number being changed to make a validator pass. It is the pattern of an older accepted snapshot remaining in one projection after a later specification addition.

### Narrow provenance check before editing the matrix

Do not establish legitimacy merely from the working-tree count. Confirm only these four facts:

1. The additional workflow is tracked in the accepted source lineage and is not one of the 179 unexplained working files.
2. Its addition is represented in the current authoritative `MASTER_SPEC.md`.
3. The workflow explains the full inventory delta, or any other node edits are separately accounted for:

   ```text
   workflows: 22 → 23
   nodes:     327 → 350
   ```
4. The workflow addition had an authorized write owner and resolving review/evidence.

You do **not** need to reconcile all 179 files to perform this check. You only need to establish that the workflow and its authoritative specification entry are not part of that unexplained set.

If that narrow check failed, the matrix should remain at 22/327 and the added workflow would be unapproved scope drift. On the evidence currently available, it should pass, so the matrix correction is the right result.

### Exact matrix edit

In:

```text
manifests/acceptance_matrix.yaml
```

change only:

```diff
-      canonical_workflow_count: '22'
-      workflow_node_count: '327'
+      canonical_workflow_count: '23'
+      workflow_node_count: '350'
```

Do not change the release label, scope statement, other gates, or later release levels in this increment.

Because this changes a shared canonical release-gate declaration, it is also:

> **SPEC_GAP — SPEC_BUNDLE inventory-pin reconciliation requires an authorized canonical-contract owner.**

The factual answer is clear, but the currently missing ownership still has to be repaired before the edit is governance-valid.

---

## 2. The validator should compare the matrix with observation, not `EXPECTED` with the matrix

The current three-way arrangement is wrong:

```text
acceptance_matrix.yaml: 22/327
validator EXPECTED:     23/350
observed repository:    23/350
```

The corrected authority model is:

```text
manifests/acceptance_matrix.yaml
    = declared, reviewed release inventory pin

repository parsing
    = observed inventory fact

tools/validate_spec_bundle.py
    = neutral comparator
```

`EXPECTED` has no legitimate role as a second inventory authority.

### Required validator behavior

For the selected release level:

```python
release_level = acceptance_matrix["status_of_this_bundle"]
gates = acceptance_matrix["release_levels"][release_level]["gates"]
```

the validator should parse and compare at least:

```python
declared_workflows = parse_non_negative_int(
    gates["canonical_workflow_count"]
)
declared_nodes = parse_non_negative_int(
    gates["workflow_node_count"]
)

if declared_workflows != observed_workflow_count:
    errors.append(
        "SPEC_BUNDLE gate mismatch: "
        f"canonical_workflow_count "
        f"declared={declared_workflows} "
        f"observed={observed_workflow_count}"
    )

if declared_nodes != observed_workflow_node_count:
    errors.append(
        "SPEC_BUNDLE gate mismatch: "
        f"workflow_node_count "
        f"declared={declared_nodes} "
        f"observed={observed_workflow_node_count}"
    )
```

Invalid, missing, Boolean, negative, or non-integer-like count declarations should fail closed rather than being ignored.

### Remove duplicated derived counts

Remove these inventory literals from `EXPECTED`:

```python
"workflows": 23,
"workflow_nodes": 350,
```

More generally, every exact count already declared in the acceptance matrix should follow the same declared-versus-observed path rather than remain duplicated in `EXPECTED`, including schemas, examples, work packages, invariants, prompts, roles, lenses, blueprint skills, and blueprint hook bundles.

This does not require redesigning all validation logic. The validator may retain fixed structural expectations that are not derived inventory, such as the current release-level-name set:

```python
expected_levels = {
    "SPEC_BUNDLE",
    "PLUGIN_ALPHA",
    "EVOLUTION_MVP_50",
    "PILOT_200",
    "PRODUCTION_2000",
    "CROSS_DOMAIN_QUALIFIED",
}
```

Leave that separate check unchanged in this increment.

### No arbitrary winner

When declared and observed values disagree, the validator should not decide that either one automatically wins. It reports:

```text
declared=X observed=Y
```

Then the provenance decision has only two valid outcomes:

* the bundle change is authorized, so the matrix pin is reviewed and changed;
* the bundle change is unauthorized, so the bundle content is removed or corrected.

That preserves the gate’s purpose.

---

## 3. Exact counts should remain in the acceptance matrix

Keep them.

They are best understood not as automatically generated documentation but as **reviewed inventory pins** for the exact bundle accepted at that release level.

The distinction is:

```text
Observed count
    derived automatically on every validation run

Accepted count
    changed only through reviewed canonical-contract amendment
```

That arrangement detects both directions of drift:

```text
23 → 24   unreviewed growth
23 → 22   accidental deletion
350 → 351 unreviewed node addition
350 → 349 missing node
```

If the validator automatically rewrote the matrix to whatever it observed, an unauthorized addition would approve itself. That would destroy the gate in the same way that blindly regenerating `PACKAGE_MANIFEST.json` would destroy hash-drift detection.

The fact that exact counts require maintenance is therefore not itself a defect. The defect was that nothing compared the maintained declaration with the observed state.

Renaming these fields to something such as:

```yaml
expected_canonical_workflow_count:
expected_workflow_node_count:
```

might communicate their role more clearly, but it would be a shared canonical contract/schema change:

> **SPEC_GAP — acceptance-matrix field-semantics migration**

That migration is unnecessary for the current repair and should not be included.

---

## 4. Acceptance-matrix ownership is a SPEC_GAP

No current `write_scope` owns:

```text
manifests/acceptance_matrix.yaml
```

That is:

> **SPEC_GAP — acceptance-matrix canonical write ownership is absent.**

Assign it to **A04 — A-phase integration and independent architecture review**.

### Exact amendment

In:

```text
manifests/development_manifest.yaml
```

change A04 from:

```yaml
- id: A04
  phase: P00-A
  phase_title: Authority and architecture
  title: A-phase integration and independent architecture review
  depends_on:
  - A02
  - A03
  write_scope:
  - artifacts/work_packages/A04/**
```

to:

```yaml
- id: A04
  phase: P00-A
  phase_title: Authority and architecture
  title: A-phase integration and independent architecture review
  depends_on:
  - A02
  - A03
  write_scope:
  - artifacts/work_packages/A04/**
  - manifests/acceptance_matrix.yaml
```

No broad pattern such as:

```yaml
- manifests/**
```

should be granted.

### Why A04

A04 already owns reconciliation of A01–A03 evidence and independent approval of authority and boundaries. Updating an accepted inventory pin after reconciling the authoritative specification and measured bundle is exactly that integration responsibility.

The alternatives are weaker:

* **A01:** conceptually close to authority, but its frozen maturity-authority slice explicitly excluded changing release-gate thresholds.
* **A02:** measures and projects inventory; it should not also author the value against which its own measurement is judged.
* **Z02:** owns release-building and validation mechanisms; it should not control the expected gate values those mechanisms enforce.
* **Z04:** is the final consumer and independent gate; it should not edit its own pass criteria.

The separation should therefore be:

```text
A04
    owns manifests/acceptance_matrix.yaml
    approves reviewed inventory-pin changes

Z02
    owns tools/validate_spec_bundle.py
    implements the declared-versus-observed comparison

Z04
    consumes the resulting gate outcome
    does not rewrite either side
```

The development-manifest edit cannot be treated as A04 self-granting authority. The operator or existing repository-level canonical-contract authority must approve the ownership amendment as the resolution of the SPEC_GAP.

---

## 5. This is worth doing now

Do it before moving to unrelated capability work.

The bounded correction is:

```text
manifests/development_manifest.yaml
manifests/acceptance_matrix.yaml
tools/validate_spec_bundle.py
```

It fixes a known silent-failure path: the acceptance matrix could previously disagree with the bundle indefinitely while the validator continued to pass its own hardcoded count.

The 179 uncommitted files remain a separate release-manifest blocker. They should not be:

* committed on the user’s behalf;
* added to `PACKAGE_MANIFEST.json`;
* reclassified as explained merely because this gate repair is being made;
* required to disappear before the count-comparison defect is corrected.

After this increment, the expected state is not an overall green repository. It is a more truthful failure set:

```text
acceptance-matrix inventory mismatch: resolved

PACKAGE_MANIFEST content/hash differences:
    still reported until their provenance is resolved
```

That is meaningful progress. A gate that now reports only real unresolved drift is substantially better than one that mixes real drift with stale internal declarations.

## Approved minimum change

1. Resolve the **SPEC_GAP** by adding `manifests/acceptance_matrix.yaml` to A04’s exact `write_scope`.
2. Verify narrowly that the +1 workflow/+23 nodes are outside the unexplained uncommitted set and have accepted provenance.
3. Change the SPEC_BUNDLE values to `'23'` and `'350'`.
4. Remove workflow and workflow-node count literals from the validator’s `EXPECTED` dictionary.
5. Have the validator compare matrix declarations directly with observed inventory.
6. Apply the same comparator pattern to the other exact inventory counts already present in the matrix.
7. Leave `PACKAGE_MANIFEST.json` untouched.
8. Leave the 179 unrelated working files untouched.

No implementation or test execution is claimed here.
