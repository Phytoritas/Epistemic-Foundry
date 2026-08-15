# A05 approval-independence boundary review

We are continuing the Epistemic Foundry v4 implementation. Review one narrow, source-level A05 repair only.

Higher authority freezes EF4-I12: makers cannot approve their own work. The public A05 function currently accepts `maker_ids: Sequence[str]`, but `verify_approval_independence()` in `registry.py` only checks:

```python
if approver_id in tuple(maker_ids):
```

A caller can therefore pass the scalar string `"AGENT-MAKER-1"`; it becomes a tuple of characters and the identical approver bypasses the self-approval check. A concurrent A05 change already adds an `attestation.py` wrapper and changes the package export for the analogous attestor-input defect. Preserve that work.

Proposed smallest repair, entirely inside A05's declared write scope:

1. Add `src/epistemic_foundry/governance/evolution_authority/approval.py`.
2. Define the same public signature `verify_approval_independence(approver_id: str, maker_ids: Sequence[str]) -> None`.
3. Fail with the existing `EvolutionAuthorityError` code `SELF_APPROVAL_FORBIDDEN` when `maker_ids` is a string/bytes/bytearray, a Mapping, any non-Sequence, or contains a member that is not a non-empty string.
4. After validation, delegate exactly once to the existing `registry.verify_approval_independence` so the established identity comparison and error behavior remain authoritative.
5. Change only the package-level `__init__.py` import to export the wrapper, alongside the concurrent attestation wrapper.
6. Extend the existing A05 negative test with scalar-string, mapping, bytes, and non-string-member cases; preserve valid tuple/list callers and order/duplicates.

Questions:

- Is this repair authorized by the attached A05 authority/contracts, or does it invent any shared semantics?
- Is `SELF_APPROVAL_FORBIDDEN` the correct existing typed failure for malformed maker identity collections at this boundary?
- Should whitespace-only IDs remain accepted because existing A05 code/schema only require non-empty strings, or is there an attached higher-authority rule requiring trimming/nonblank semantics?
- Is there any direct consumer or compatibility constraint that makes the wrapper/export approach unsafe?

Return a concise decision: `AUTHORIZED` or `SPEC_GAP`, then the exact minimum validations and any concrete blocker. Do not propose evidence reports, test execution, artifact staging, or unrelated refactors.
