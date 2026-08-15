# N03 RFC 3339 scheduler timestamp boundary review

Act as an advisory contract reviewer for Epistemic Foundry v4. Return exactly
one of `AUTHORIZED_LOCAL_REPAIR`, `SPEC_GAP`, or `NO_BLOCKER`, followed only by
decisive reasoning and the smallest safe change. Do not ask to run tests.

## Scope and authority

- N03 is `DAG scheduler, leases, retries and concurrency` and solely owns
  `packages/foundry-kernel/src/scheduler/**`.
- It seals and validates `BudgetEnvelope.created_at` and validates every lease,
  attempt, heartbeat, reconciliation, and loop timestamp used for ordering and
  duration enforcement.
- Canonical schemas use Draft 2020-12 `format: date-time`; the BudgetEnvelope
  schema adds no uppercase-only, year-minimum, or leap-second prohibition.

## Current defect

`dag-scheduler.mjs` uses an uppercase-only RFC3339 regex plus
`Number.isFinite(Date.parse(value))`. It then uses `Date.parse` again for all
ordering and elapsed-time checks.

Consequences:

1. ECMAScript parsing can normalize impossible calendar dates such as
   `2026-02-30T00:00:00Z` instead of rejecting them.
2. Schema-valid lowercase `t`/`z` is rejected.
3. RFC 3339 year `0000` and a valid leap second are rejected or become `NaN`.
4. Arbitrary fractional seconds are accepted by the schema, while `Date.parse`
   collapses precision beyond milliseconds during scheduler ordering.

The current W02 checkpoint runtime already implements explicit calendar
validation with `[Tt]`/`[Zz]`, year 0000, offset-aware leap-second validation at
UTC minute 23:59, and preserves the original timestamp bytes. N03 cannot edit
or import W02's private helper, and its elapsed-time logic additionally needs a
deterministic comparable time value.

## Decision requested

Decide whether N03 may locally replace `Date.parse` validation with an exact
RFC 3339 parser while preserving the original string in sealed hashes. If
authorized, freeze the smallest comparable-time rule for:

- valid calendar dates including year 0000;
- lowercase `t`/`z`;
- numeric offsets;
- an offset-shifted leap second only when it maps to UTC 23:59;
- arbitrary fractional seconds used in monotonicity and duration checks.

If arbitrary fractional precision or leap-second ordering lacks a shared
semantic contract, say `SPEC_GAP` rather than authorizing a millisecond-truncating
partial fix. Do not change canonical schemas or unrelated budget primitives.
