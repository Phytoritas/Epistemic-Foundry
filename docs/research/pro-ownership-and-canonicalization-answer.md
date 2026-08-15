# Recommendation: ratify complete production-source ownership closure first

The first decision should be:

> **Every tracked production Python source under `src/epistemic_foundry/` must resolve to exactly one work-package owner before it may be modified, relied upon for package completion, or used as evidence of runtime reachability.**

This must be a **complete ownership closure**, not the proposed two-file exception and not an on-demand policy. Canonicalization comes immediately afterward.

The authority order already requires missing or inconsistent shared semantics to become `SPEC_GAP`, and it explicitly separates specification from execution evidence. An unowned production source is therefore not merely an administrative inconvenience; it is a missing authority boundary. 

## 1. Why ownership dominates

### It is a strict prerequisite of canonicalization

The canonicalization correction must modify `src/epistemic_foundry/domain/hashing.py`. Until that file has a lawful owner, a canonicalization implementation would either:

* bypass `development_manifest.yaml`;
* borrow another package’s scope;
* create an ad hoc wrapper while leaving the real implementation unowned; or
* make an unreviewable root-level edit.

All four violate the stated authority order. Ownership and canonicalization are therefore not independent:

```text
production-source ownership
        ↓
canonicalization authority and migration
        ↓
cross-language hash-dependent carriers
```

### It unlocks more work with less semantic change

Ownership closure changes responsibility metadata and enforcement. It does not alter record bytes, hash preimages, schema instances, or historical identities.

Canonicalization, by contrast, affects:

* potentially 188 hash-bearing schema properties;
* roughly 64 serializer implementations;
* cross-language read/write compatibility;
* schema-version interpretation;
* legacy hash verification;
* package byte manifests;
* large-integer and signed-zero semantics.

Thus ownership has the larger immediate unlock and the smaller contract surface.

### The currently blocked ownership defects are false acceptances

The memory and retrieval examples admit invalid or unverified state:

* an expired memory is accepted;
* an inaccurate corpus snapshot can be represented as searched;
* unrederived candidates and lane receipts can enter reconciliation.

The canonicalization defect currently produces an explicit **false rejection**. That is serious, but the web path is failing closed and distinguishing the condition from tampering. Between a typed refusal and a live invalid acceptance, the invalid acceptance has the higher integrity priority.

## 2. Exact form of the ownership ratification

### `MASTER_SPEC.md`

Add one invariant, conceptually:

```text
EF4-I65 — Complete production-source ownership

Every tracked production source file under an authoritative live source root
has exactly one work-package owner. Runtime reachability, import count, package
installation, test coverage, or historical authorship does not create
ownership. Zero owners or multiple owners is SPEC_GAP. No work-package PASS,
integration acceptance, or release claim may rely on an unresolved source.
```

A01 should own this authority change. Its existing responsibility is the authority chain, repository constitution, and status vocabulary, and it already owns `MASTER_SPEC.md`. A04 remains the independent integration reviewer.  

### `manifests/development_manifest.yaml`

Make four changes.

First, add `manifests/development_manifest.yaml` itself to A01’s `write_scope`. The authority manifest currently has no declared work-package owner; the package responsible for the repository constitution is the narrowest defensible owner.

Second, add a top-level execution rule equivalent to:

```yaml
production_source_ownership_rule: >-
  Every git-tracked regular Python file under src/epistemic_foundry/
  must match exactly one work-package write_scope. Zero matches or more
  than one match is SPEC_GAP. A write attempted by a non-owner is FAIL.
```

Third, update the existing package `write_scope` entries with the complete reviewed ownership census.

Fourth, add the ownership checker to B01, whose stated responsibility is package boundaries. A04 should review the resulting closure rather than own the checker or source files.

The checker should evaluate:

```text
production_files =
  git-tracked regular files matching src/epistemic_foundry/**/*.py

owners(path) =
  every work package whose write_scope matches path

required:
  |owners(path)| == 1 for every production file
```

It should include `__init__.py` files. It should not exempt a file because it is old, highly imported, apparently stable, or currently passing tests.

The ownership census does **not** need a new runtime carrier or resolver framework. It is the deterministic expansion of existing `write_scope` declarations.

### `manifests/acceptance_matrix.yaml`

Add mandatory cases for:

| Case                                                      | Required result                 |
| --------------------------------------------------------- | ------------------------------- |
| Production file with no matching owner                    | `SPEC_GAP`                      |
| Production file matching two owners                       | `SPEC_GAP`                      |
| Package attempts to edit another package’s source         | `FAIL`                          |
| Newly added production file lacks an owner                | `SPEC_GAP`                      |
| Renamed file falls outside its owner’s scope              | `SPEC_GAP`                      |
| Imported or CLI-reachable file is omitted from the census | `SPEC_GAP`                      |
| All tracked production files have exactly one owner       | ownership gate eligible to pass |

This gate must run before work-package status or release aggregation. Existing package-local PASS records cannot override it.

### `manifests/product_invariants.yaml`

Record the new invariant and assign its governance coverage to:

* A01: authority rule and manifest ownership;
* B01: deterministic source-boundary enforcement;
* A04: independent architecture-level reconciliation.

No ownership semantics should be introduced later in `role_registry.yaml`.

## 3. Immediate file assignments

The proposed L01 assignment is correct, but the proposed two-file closure is incomplete.

| Production path                                    | Owner   | Rationale                                                                                |
| -------------------------------------------------- | ------- | ---------------------------------------------------------------------------------------- |
| `src/epistemic_foundry/memory/policy.py`           | **L01** | Memory classes, consent, and retention policy are exactly L01’s responsibility           |
| `src/epistemic_foundry/retrieval/lexical_index.py` | **O02** | Lexical retrieval implementation and indexed-corpus integrity                            |
| `src/epistemic_foundry/retrieval/lanes.py`         | **O02** | Search-lane execution and candidate/receipt reconciliation                               |
| `src/epistemic_foundry/domain/hashing.py`          | **C03** | Runtime hash compatibility, legacy verification, and canonicalization migration boundary |

L01’s current scope points only to `packages/foundry-kernel/src/memory/policy/**`, despite its explicit retention-policy responsibility. The actual Python source and its direct unit tests should be added to L01. 

O02 already owns lexical, semantic, citation, and relation retrieval, but its current scope points to `python/epistemic_foundry/retrieval/lanes/**`. The two live `src/` paths should be assigned there rather than to O01 or a generic core package. 

C03 is the correct owner for `domain/hashing.py` **as an exact file assignment**, because C03 owns compatibility windows, runtime migration, and existing hash-bound Python runtime surfaces. 

### Do not assign the entire `domain/` and `contracts/` cluster to C03

Import centrality is a review-priority signal, not an ownership rule.

The shared cluster should remain semantically divided:

* canonical hash compatibility and migration primitives → C03;
* generated Python/TypeScript/UI contract projections → C02;
* canonical registry/build projection surfaces → B04;
* feature-specific domain logic → the corresponding feature package.

`src/epistemic_foundry/contracts/registry.py` is already explicitly assigned to B04. Moving the entire `contracts/` directory to C03 would create an overlap and would conflate build-registry responsibility with runtime migration. 

For `src/epistemic_foundry/contracts/__init__.py`:

* assign it to B04 if it is only the public façade over `contracts/registry.py`;
* if it mixes registry exports, generated contracts, and runtime migration functions, split that façade before assigning ownership;
* do not assign it to C03 solely because 45 modules import it.

That is the only honest disposition without inventing the contents of the other shared files.

### Assign the rest in the same census

The remainder of the unowned production set should **not** be left until each file happens to block a repair.

The ownership ratification is accepted only when all tracked production files have exactly one defensible owner. The census may use non-overlapping directory scopes where a directory is genuinely cohesive, and exact file paths where a directory crosses responsibilities.

An ambiguous file remains `SPEC_GAP`; it must not be dropped into a catch-all package merely to reach zero unowned files.

## 4. No generic maintenance package

A new “shared maintenance,” “legacy,” or “miscellaneous core” package would be worse than targeted assignment.

It would:

* become the default owner for files nobody has analyzed;
* collect unrelated authority-bearing utilities;
* hide semantic dependencies behind a single broad scope;
* permit feature packages to depend on an administrative package rather than the actual contract owner;
* make future ownership audits formally complete but substantively meaningless.

A new package would be justified only if the census demonstrated a genuinely cohesive subsystem with a stable public contract and no suitable existing owner. The facts supplied do not establish such a subsystem. They establish several different semantic groups that happen to be highly imported.

## 5. Canonicalization after ownership

### JCS does not yet govern all canonical hashes

The A05 charter explicitly states RFC 8785-equivalent canonical JSON and defines missing canonicalization as `SPEC_GAP`. 

However, that document cannot silently establish a global rule for every self-hash schema because:

* `MASTER_SPEC.md` does not currently establish a global JSON number profile;
* the affected schemas do not bind one;
* the charter is a lower and locally scoped source;
* the authority order forbids lower documents from filling an unresolved higher-level semantic silently. 

Therefore:

> **JCS is a strong intended successor, but not yet the globally ratified current profile.**

The web views’ current behavior—refusal with a typed unratified-canonicalization diagnosis—is correct. They must not “try Python, then JavaScript” and accept whichever hash matches.

### The next decision should be a versioned profile, not an in-place switch

After ownership closure, ratify two explicit profiles:

```text
EF-CJSON-PYTHON-LEGACY-1
EF-CJSON-RFC8785-JCS-1
```

The binding should be determined by immutable schema or schema-bundle identity, for example:

```text
schema_bundle_hash
+ schema_id/schema_revision
+ self_hash_field
→ canonicalization_profile_id
```

Readers should be **dual-profile capable but single-profile deterministic**:

* determine the one allowed profile from immutable schema identity;
* verify using only that profile;
* return `SPEC_GAP` when no profile is bound;
* return `FAIL` when a record claiming a bound profile does not match.

Writers should be **single-write**:

* legacy records remain legacy and immutable;
* all new revisions after the cutover use JCS;
* no new legacy-profile record is written after the cutover.

This reconciles migration with the higher rule that historical hashes are never rewritten. 

A blind migration window in which the same schema accepts either Python or JCS bytes would be unsafe. It would make the hash rule depend on which implementation happens to validate the record.

### Integer and float merging

Under JCS, `1` and `1.0` intentionally canonicalize to the same JSON number representation. That is not an accidental hash collision; JSON has one number type, while Python’s `int` and `float` distinction is a host-language distinction.

The migration rule should therefore be:

* existing legacy records retain their distinct legacy hashes;
* new JCS records treat `1` and `1.0` as the same JSON value;
* any domain that truly needs integer-versus-floating semantics must represent that distinction structurally, such as a tagged object or a canonical decimal string.

The same applies to signed zero. If `-0` has scientific meaning, it cannot be carried only as an ordinary JCS JSON number.

The JCS decision must also audit integers and decimals against finite IEEE-754 binary64 semantics. Arbitrary-precision Python integers must either be schema-bounded to an exactly representable range or encoded canonically as strings/tagged quantities.

### The other canonicalizers

Do not mechanically replace all approximately 64 implementations.

First classify each one as:

1. authority-bearing JSON self-hash writer;
2. authority-bearing JSON self-hash reader;
3. foreign digest/reference verifier;
4. raw-byte/package-manifest hasher;
5. non-authoritative local cache or lookup key.

Only classes 1 and 2 require canonical-profile convergence. Raw-byte package hashes must remain raw-byte hashes.

The cutover is complete only when every authority-bearing writer and reader:

* delegates to the canonical profile implementation or a reviewed compatibility adapter;
* passes one shared cross-language vector suite;
* covers exponent thresholds, `-0`, integer/float normalization, Unicode, escaping, key ordering, unsafe integers, and finite-number rejection.

`PACKAGE_MANIFEST.json` should receive a new manifest revision with new byte pins. The old package manifest remains historical; it is not rewritten.

## 6. Sequencing

The authority sequence should be:

```text
1. Complete production-source ownership closure
2. Canonicalization-profile ratification and compatibility design
3. Cross-language canonicalization implementation and conformance migration
4. NodeAttemptEffectTerminalProof
```

Once step 1 is ratified, the L01 retention repair and the O02 integrity repairs may proceed immediately under their real owners. Those local repairs need not wait for the entire canonicalization migration unless they change the cross-language hash format.

`NodeAttemptEffectTerminalProof` should now come **after canonicalization**, even though its semantic priority remains high. It is itself intended to be a new hash-bound, cross-runtime authority carrier. Introducing its `proof_hash`, intent bindings, and receipt bindings before canonicalization is resolved would create another carrier whose honest Python and JavaScript verification could disagree.

The previous proof recommendation therefore remains valid, but its implementation order moves:

```text
ownership prerequisite
→ hash profile prerequisite
→ effect-terminal proof
```

## 7. What remains blocked after ownership ships

Ownership closure alone does not fix runtime behavior. It leaves the following unresolved:

* the L01 retention defect until `memory/policy.py` is repaired and directly tested;
* the O02 corpus-snapshot and lane-reconciliation defects until both retrieval files are repaired;
* the Python/JavaScript honest-record false rejection;
* the global canonicalization profile and migration rules;
* classification and convergence of the authority-bearing canonicalizers;
* `NodeAttemptEffectTerminalProof`;
* N03 effect-terminal resolution and A05 G14 reconciliation;
* A05 G01–G13, which correctly remain `SPEC_GAP` until their evidence carrier and recomputation contract exist;
* W04’s authoritative run-reference inventory;
* Q05’s selective-inference source-input provenance, unless separately repaired;
* end-to-end runtime reachability.

The 156 recorded package PASS values remain historical package reports, not proof that any of these boundaries are reachable or compositionally correct.
