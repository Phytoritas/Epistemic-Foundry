# B04-0007 pre-C04 projection and regression review

Overall correction status: `PASS`

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_INTEGRATION_REVIEW`

Assurance limitation: `actor_independence=false`. This is a procedurally
separate primary-session review, not external actor-independent certification.
Fleet and subagents were not used.

## Authority and projection

- Root `schemas/**` and `openapi/**` remain the sole canonical authority. The
  package snapshot is a deterministic derived projection.
- 126 schemas and one OpenAPI 3.1.1 document with
  33 unique operations produce
  127 canonical resources.
- Source `sha256:1557b03db2ad7e7d23b014d4c9d5fd643803f6613696c966d9b0379573259e7f`, snapshot
  `sha256:d01bda0057584e235331b649238fc2507c60cab329fd6b8e8b6a115fac912559`, and registry
  `sha256:6b4fcade707639e537744be4075e71d3f7e068cd42eaaaddb20ef084851175d5` match live bytes. Missing, extra,
  hash-mismatched, and duplicate-ID counts are zero.
- The official materializer found the snapshot already current and changed zero
  files. Root canonical source mutation and reverse synchronization counts are zero.

## Packaging and regression

- Targeted projection/registry/CLI contracts pass
  41/41.
- Clean wheel/sdist, sdist-to-wheel rebuild, installed-wheel-only loading,
  arbitrary empty cwd, missing/tamper fail-closed behavior, no source fallback,
  and two-build byte reproducibility all pass.
- Full Python is 990/990
  with zero failures, errors, skips, or xfails.
- Full Node is 460/460
  by the Node footer, with zero failures, cancellations, skips, or todos. The
  reporter's 457 XML testcase rows remain separately visible and are not used to
  undercount the authoritative 460 footer total.
- The 67 Python and 11 Node problems recorded by B04-0006 are now resolved.
  No failure was hidden with skip, xfail, alias, fallback, or gate weakening.

## Remaining bounded debt and decision

- `examples/sample_gate_decision.json` remains a C01-owned canonical example hash debt: stored
  `sha256:816c793545f4c3a194ce6b4fa842856defbcb34d991f27277ea9cd2a082e4be1`, recomputed `sha256:a6a50d4285e844b71093e999b5addccf969d09d4c14221a92531d73172369851`.
  B04 did not edit it. The authorized next step must correct and validate it
  before C04-0002.
- B04-0007 passes as the pre-C04 correction/revalidation attempt. This does not
  establish C04 full conformance, B04-0008 final packaging, release readiness,
  or product completion. Global `implementation_gate=fail` and
  `completion_ready=false` remain required.
