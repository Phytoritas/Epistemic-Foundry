# Cost, concurrency, and hidden-edge contract

## Defaults

- write-heavy concurrency: 4,
- read-heavy concurrency: 8,
- hard agent cap: 16,
- higher limits require measured benchmark and ADR.

## Hidden edges

Two nodes are not independent when they share:

- a write scope,
- an exclusive database or projection lock,
- a rate-limited provider or parser,
- an approval or human decision,
- a mutable schema or shared contract,
- a non-idempotent external effect,
- a budget or data-access quota.

## Budget truthfulness

A predicted token or currency budget is advisory unless the runtime measures spend and can cancel work. The UI and logs distinguish:

- estimated budget,
- metered usage,
- hard limit,
- cancellation threshold,
- overrun reason.

## Fan-in

Large fan-in uses deterministic reduce and layered summaries. The final synthesizer receives compact typed artifacts, not every raw node transcript.
