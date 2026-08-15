# A05 final corrections review

Re-read the attached current A05 files after your previous blocker and an independent reviewer finding.

Corrections now on disk:

- `approval.py` requires exact built-in `str` for `approver_id` and every maker member, so behavior-bearing `str` subclasses cannot falsify equality.
- The exact 24-case A05 negative-suite contract is preserved: new attestor assertions are inside NEG-016 and all approval assertions are inside NEG-017; no extra collected test function or parametrized case was added.
- Malformed maker fixtures use an unrelated approver, so they prove shape rejection rather than passing through the legacy self-match.
- Coverage inside NEG-017 includes scalar string, bytes, bytearray, Mapping, non-string member, empty-string member, ordinary non-Sequence, behavior-bearing maker string subclass, and behavior-bearing approver string subclass.

Return only `PASS` if no material correctness/contract/compatibility blocker remains. Otherwise identify the concrete blocker and smallest A05-local correction. Do not request test execution, evidence/report regeneration, or unrelated refactors.
