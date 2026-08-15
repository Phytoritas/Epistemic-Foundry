# F05 package review record

Standing verdict: `PASS` (from attempt `0001`).

This file is the package-level projection the manifest requires. The
attempt review below, at `attempts/0001/review.md`, is the primary record.

---

# F05-0001 primary-session separate adversarial review

- Reviewer: primary session in a separate adversarial pass under the
  product-owner instruction forbidding subagents and Fleet;
  actor_independence=false is recorded, not hidden.
- The return edge is the whole point. A pipeline that only moves
  forward cannot search, and looping is exactly how a search escapes
  its own limits, so the machine constrains the loop rather than the
  line: a loop back is admitted only across a committed checkpoint, is
  bounded by the run's own LoopContract, and must run between the
  endpoints that contract declares.
- Nothing is restated. The 26 nodes, their dependencies and the five
  terminal states are read from the declaring workflow and compared
  against it in the tests, and the stop classification comes from the
  chamber module that owns it. A workflow that renames a node breaks
  this suite instead of leaving a machine describing a graph that no
  longer exists.
- EF4-I22 caught a real violation during this attempt: the report used
  'dry_rounds' as a key, which is also a canonical stop reason, along
  with two other colliding keys. The fields were renamed rather than
  the module being registered as a declaring owner it is not.
- One claim was withdrawn because it could not be derived. The first
  draft refused a run that looped 'after' an adverse stop, but the
  caller supplies transitions and a certificate with no evidence of
  which came first, so the rule was asserting an ordering the data
  does not carry — and it wrongly rejected the normal case of a run
  that looped and then hit a safety stop. It was replaced with a check
  that is derivable: the certified resume point must be one the run
  actually committed. The machine now records that limitation
  explicitly instead of implying a guarantee it cannot give.
- Partial work cannot be hidden. A certificate that sets
  partial_results_visible false, records no observed condition, or
  names no checkpoint is refused, and the runtime builder forces the
  flag true so a caller cannot stop a run and erase where the search
  had got to.
- One file outside the manifest grant was authorized and recorded:
  src/epistemic_foundry/evolution/__init__.py, on the same verified
  grounds as the effects marker. A named packaging-discovery check
  proves the machine stays discoverable and reads the discovery mode
  from pyproject rather than assuming it.
- Residual limitations: the machine evaluates a run that is handed to
  it, it does not drive one — executing the nodes belongs to the
  kernel scheduler; it does not order the stop against the
  transitions, as recorded above; the loop contract is read as data
  rather than resolved from a run spec, which T05 and the runtime
  own; and this review is not external actor-independent
  certification.
