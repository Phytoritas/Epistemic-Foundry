We are implementing Epistemic Foundry v4 work package O02 (provider-neutral lexical, semantic, citation, and relation retrieval). Please act only as an advisory contract reviewer. Local authority order is MASTER_SPEC.md, development_manifest.yaml, acceptance/invariant manifests, then schemas/workflows. Do not infer approval from prior work-package reports.

The frozen O02 requirements relevant here are:

- RetrievalCandidate identity, content hash, snapshot, and receipt bindings must be deterministic and fail closed.
- `schemas/retrieval-candidate.schema.json` explicitly specifies `RFC 8785 JCS-equivalent UTF-8` for both identity and content-hash preimages.
- O02 owns `python/epistemic_foundry/retrieval/lanes/**`, but not `src/epistemic_foundry/domain/**`, Node packages, `pyproject.toml`, or lockfiles.

Current-disk facts:

1. O02's public `canonical_json()` uses Python `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)`. This is not RFC 8785: Python emits examples such as `1.0`, `1e-06`, and `-0.0` where ECMAScript/JCS emits `1`, `0.000001`, and `0`; Python key sorting is Unicode-code-point order rather than UTF-16 code-unit order.
2. There is no reusable Python JCS implementation in the repository. The shared `src/.../domain/hashing.py` and O01 sibling use the same incomplete `json.dumps` form, and the repository forbids component-source imports across that boundary. A private JavaScript ledger implementation is closer but is outside O02 scope and is not a reusable export.
3. The local O02 repair now snapshots caller-owned nested Mapping/Sequence inputs once through base JSON primitives, rejects numeric subclasses, non-finite values, byte-like values, cycles, and duplicate projected keys, and never calls caller `__deepcopy__` hooks.
4. `SealedBackendRequest` now stores only canonical bytes plus request hash/query text. Every response-sealing, response-validation, and candidate-building authority path re-parses and re-seals those bytes and exact-compares all bindings before use.
5. Candidate ID/hash computation now snapshots the entire supplied Mapping before selecting the schema-declared preimage fields. Relation classification rejects scalar strings masquerading as triplet arrays; the release guard rejects scalar candidate containers and boolean fallback counts and snapshots candidate/state inputs before decisions.
6. We have not changed the canonical schema, dependency manifests, or shared hashing modules.

Decision requested:

A. Is a strict, package-local RFC 8785 serializer in `retrieval/lanes/**` an AUTHORIZED_LOCAL_REPAIR, or is this a SPEC_GAP because the shared canonical-hashing owner must define one cross-language implementation/API first?

B. If local repair is authorized, state the exact fail-closed Python input rule for integers/floats. In particular, should O02 reject integers not exactly representable as IEEE-754 binary64 and serialize every accepted number with ECMAScript `Number::toString` rules, or does the current schema leave that decision unresolved?

C. Review facts 3-5 for one concrete correctness or compatibility blocker. Focus on authority-affecting behavior only; do not request reports, tests, evidence packets, or broader refactors.

Return exactly:

- `DECISION: AUTHORIZED_LOCAL_REPAIR` or `DECISION: SPEC_GAP`
- `NUMBER_RULE:` one precise rule or `UNRESOLVED`
- `BLOCKER:` `none` or one highest-impact concrete blocker with smallest valid repair
- `RATIONALE:` concise authority-based reasoning
