# R01 dependency-cluster input-boundary review

Act as an independent, read-only contract reviewer for one bounded Epistemic
Foundry R01 change. Do not propose shared-schema changes unless this local fix
actually conflicts with a higher authority. Return only material blockers, or
`NO_BLOCKER` with one short rationale.

Authority and scope:

- `MASTER_SPEC.md`: R01 is the inductive synthesis and heterogeneity engine.
- `manifests/development_manifest.yaml`: R01 owns only
  `python/epistemic_foundry/reasoning/induction/**`; exit criteria are
  independence adjustment and retention of moderators and nulls.
- `schemas/evidence-pack.schema.json`: `dependency_clusters` is an array whose
  items are non-empty arrays of strings.
- The upstream canonical EvidencePack validator also rejects `str`, `bytes`,
  and `bytearray` as arrays and rejects empty dependency-cluster member arrays.

Current bounded change:

```diff
 def _pack_roles(pack):
-    if not isinstance(ids, Sequence) or isinstance(ids, (str, bytes)):
+    if not isinstance(ids, Sequence) or isinstance(ids, (str, bytes, bytearray)):
         fail PACK_INVALID

 declared = pack.get("dependency_clusters")
-if not isinstance(declared, Sequence) or isinstance(declared, (str, bytes)):
+if not isinstance(declared, Sequence) or isinstance(declared, (str, bytes, bytearray)):
     fail PACK_INVALID
-declared_membership = sorted(
-    tuple(sorted(text(entry) for entry in group)) for group in declared
-)
+declared_membership = []
+for index, group in enumerate(declared):
+    if not isinstance(group, Sequence) or isinstance(group, (str, bytes, bytearray)):
+        fail PACK_INVALID
+    members = tuple(sorted(text(entry) for entry in group))
+    if not members:
+        fail PACK_INVALID
+    declared_membership.append(members)
+declared_membership.sort()
```

A regression supplies `pack["dependency_clusters"] = ["EVN-0001"]` and
requires `PACK_INVALID`, preventing the scalar string from being split into
characters before membership comparison. No shared contract, schema, or
upstream package is changed.

Review questions:

1. Does this preserve valid canonical EvidencePack inputs and existing
   independence weighting?
2. Is the rejection placed at the correct R01 trust boundary and sufficiently
   fail-closed for scalar/byte-like nested cluster values?
3. Is there any material correctness or compatibility blocker in this exact
   change?
