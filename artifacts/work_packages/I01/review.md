# I01-0001 bounded Interview contract review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW`

Final verdict: `PASS`

Blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW`

The product owner requires primary-session execution without subagents or Fleet.
This is a procedurally separate review of the final I01 product bytes and
receipts. It is not actor-independent certification.

## Reviewed product boundary

- `python/epistemic_foundry/intake/interview/__init__.py` — `sha256:533f3441733c40bb38f6182add7eb553d6d6b378503ed8dbfda5e426c96d457c`
- `python/epistemic_foundry/intake/interview/engine.py` — `sha256:dded723763a007de1a1d8e51606333b2140d9821e0541ac2bdea6cf40d9db764`
- `python/epistemic_foundry/intake/interview/test_interview_readiness.py` — `sha256:d3daa0c5dc6284c1bf3086b64364c6514b3cc84caa392caf2fa8d56713b7d4c7`
- `python/epistemic_foundry/intake/interview/test_no_repeat_question.py` — `sha256:b9a14f828e75b1a1ed2854cdb3c784003c517fc23548ef471693fab16fd2a8f4`

## Findings

1. The component accepts only the closed I01-I09 rule vocabulary and typed
   dimensions. Raw enum aliases, mutable input collections, duplicate IDs,
   invalid dispositions, and rule/dimension mismatches fail closed.
2. Only decision-critical missing dimensions produce questions. Multiple needs
   for one dimension merge into one canonically ordered question; known and
   answered dimensions are not re-asked; noncritical needs remain explicit.
3. Question identity binds engine version, immutable request ID and revision,
   target type, and target ID. Same-revision retries are deterministic. A prior
   open question remains pending instead of being emitted again, and forged or
   missing-target history is rejected.
4. Every supplied contradiction is retained. Critical unresolved contradictions
   are routed to a question, resolved contradictions bind an artifact, and
   accepted blockers remain sticky. An unrecorded critical conflict cannot pass.
5. The final targeted suite is 36/36: 19 readiness cases and 17 no-repeat cases.
   Full Python is 947/947. Full Node is 360/361 with only exact unchanged
   S04-TM004, whose footer/XML testcase delta is explicitly reconciled.
6. The rejected test-only import bridge was removed. Product writes are confined
   to the I01 scope, cache artifacts are absent, and prior reports, RAH
   generations, and unrelated dirty-worktree content remain preserved.

## Assurance boundary

I01 emits a deterministic component-local Interview plan and readiness verdict.
It does not invent a new canonical schema, persist a canonical ResearchBrief,
implement a user interface or remote interview service, decide downstream
scientific claims, or claim actor-independent certification. I02 and I03 retain
framing and ontology/measurement responsibilities.

## Decision

Both I01 exit criteria and both required checks pass. Product completion,
release readiness, a globally green repository, and `completion_ready=true`
remain unclaimed.
