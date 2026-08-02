# I02-0001 InsightCard and ScopeVector contract review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW`

Final verdict: `PASS`

Blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW`

The product owner requires primary-session execution without subagents or Fleet.
This is a procedurally separate review of the final I02 product bytes and
receipts. It is not actor-independent certification.

## Reviewed product boundary

- `python/epistemic_foundry/intake/frame/__init__.py` — `sha256:5401aea2c12d597fc627ed30cab262cc6695d1720a697f73fe603903a93dfc49`
- `python/epistemic_foundry/intake/frame/compiler.py` — `sha256:eec74d16d02d7e5ee9ef80bb49ad5e012ade894e8c8406ba99e090eca9fbf4b9`
- `python/epistemic_foundry/intake/frame/test_falsifier_gate.py` — `sha256:43721d8510d87492226dda4ee5162e46d891bb0cab2036313962c63482a0238a`
- `python/epistemic_foundry/intake/frame/test_frame_gold.py` — `sha256:33c35e6d5e718ddd31863339847dc831fc85773750f970c3a658865f34c4c5d5`

## Findings

1. The compiler projects proposals into the existing strict `InsightCard` and
   `ScopeVector` schemas. It adds no canonical schema, does not modify the
   canonical workflow, and rejects fields outside those contracts.
2. Missing, explicit-null, and blank scalar scope inputs remain `null`; missing
   list/map inputs retain the canonical empty shape. A typed component-local
   `ScopeUnknown` sidecar records why positions are unknown without inventing
   a canonical artifact or inferred scope value.
3. Falsifier, prediction, and mechanism inputs are mandatory. An `eligible`
   card cannot retain required domain/population/unit-of-analysis unknowns or
   undefined constructs; Inbox and withdrawn cards cannot claim council
   readiness. This preserves the `F → O` fail-closed boundary.
4. The compiler preserves supplied identifiers, timestamps, and
   `registration_hash`. It validates their form but neither generates them nor
   recomputes registration-hash content binding, which remains outside I02.
5. Stable JSON output is mapping-order independent and input proposals remain
   unchanged. Strict RFC 3339 parsing rejects loose ISO forms and invalid
   calendar/offset values while preserving a valid RFC 3339 leap-second text.
6. The final targeted suite is 31/31: 19 frame-gold and 12 falsifier-gate
   cases. Full Python is 947/947. Standalone full Node is 360/361 with only
   exact unchanged S04-TM004. The earlier load-concurrent transient failure is
   preserved, failed to reproduce in 5/5 isolated runs, and is absent from the
   standalone full Node result.
7. Product writes are confined to the I02 scope, cache artifacts are absent,
   schema count remains 124, and prior reports, RAH generations, and unrelated
   dirty-worktree content remain preserved.

## Assurance boundary

I02 implements a deterministic component-local compiler and council-readiness
gate. It does not own identifier, timestamp, hash, persistence, ontology,
measurement-identity, UI, or remote-service authority. `ScopeUnknown` is a
component-local sidecar, not a new canonical artifact. The review does not
claim actor-independent certification.

## Decision

Both I02 exit criteria and both required checks pass. Product completion,
release readiness, a globally green repository, and `completion_ready=true`
remain unclaimed.
