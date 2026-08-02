# I03-0001 ontology and measurement construct resolution review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW`

Final verdict: `PASS`

Blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW`

The product owner requires primary-session execution without subagents or Fleet.
This is a procedurally separate review of the final I03 product bytes and
receipts. It is not actor-independent certification.

## Reviewed product boundary

- `python/epistemic_foundry/ontology/__init__.py` — `sha256:6f165694369ae8a53ff5f86d64823ae959bef655b4774f5f7c68833c898e0f10`
- `python/epistemic_foundry/ontology/resolver.py` — `sha256:99d8b3036636188c4bcd8e1c94c35ab24588d85364b77de49c8ba9b2a4c29c8d`
- `python/epistemic_foundry/ontology/test_ontology_fixture.py` — `sha256:a85c9c84a0f960133516a40bd13db8993789a247b6f86f9b6f4aa28c71d6f358`
- `python/epistemic_foundry/ontology/test_measurement_identity.py` — `sha256:71d6f3e1572aa25d6d4329d9df82d5a0d6589d325d4e4ea2908ffa50a10ae0d3`

## Findings

1. Resolution accepts only exact compatibility-normalized labels within the
   pinned ontology and DomainPack authority. It uses structural constraints to
   disambiguate and never turns edit distance, embeddings, stemming, or an
   inferred synonym into mapping authority.
2. Identical labels attached to different constructs remain `AMBIGUOUS` when
   context cannot select one complete candidate. Unknown authority, missing
   context, conflicts, duplicate IDs, and mutable boundary inputs fail closed.
3. High-impact and high-frequency mappings produce deterministic review-queue
   items. A queue item remains a proposal: it does not select the construct and
   explicitly requires an external immutable `HumanDecision`.
4. Measurement identity preserves construct, method, protocol, unit, timing,
   calibration, population/entity, unit of analysis, ontology, DomainPack, and
   proxy identity. Unit conversion requires an explicit directional bridge
   with an external authority reference.
5. Review found a conservative-gate defect: a bridge with `SAME` construct and
   `CONVERTIBLE` status could still pool under `METHOD_BOUNDARY_ONLY` or
   `BLOCK_AGGREGATION`. The final bytes require both an eligible compatibility
   status and a permissive ceiling (`NO_RESTRICTION` or `CONDITIONAL_ONLY`). Two
   regression cases bind the fix.
6. The final targeted suite is 39/39: 16 ontology fixture and 23 measurement
   identity cases. The official full Python suite is 947/947. The broader
   optional collection diagnostic is preserved separately and stops only on
   the unavailable optional `psycopg` fixture dependency.
7. Final serial Node execution is 360/361 with only exact unchanged S04-TM004.
   Two earlier concurrency transients are preserved; each passed 5/5 isolated
   reproductions and neither appears in the serial final run.
8. Product writes are confined to the I03 scope, cache artifacts are absent,
   canonical schema count remains 124, and no schema or workflow was modified.

## Assurance boundary

I03 supplies deterministic component-local execution contracts. It does not
create a canonical schema, persist ontology authority, issue a HumanDecision,
implement a review UI or remote service, or claim that a review item is an
approval. The optional PostgreSQL fixture diagnostic and S04-TM004 remain
outside I03 ownership. This review does not claim actor-independent
certification.

## Decision

Both I03 exit criteria and both required checks pass. Product completion,
release readiness, a globally green repository, and `completion_ready=true`
remain unclaimed.
