# D05-0001 primary-session separate adversarial review

- Reviewer: primary session in a separate adversarial pass under the
  product-owner instruction forbidding subagents and Fleet;
  actor_independence=false is recorded, not hidden.
- Nothing here is mocked. The repository already forbids mock-only
  PostgreSQL tests, so the suite applies the migration to a real
  server in the image the sealed D04 gate qualified, and the
  store-preflight check fails closed when the daemon or that image is
  unavailable rather than passing against a substitute.
- The two invariants are enforced by the database, not by its callers.
  A checkpoint carries all seven bindings NOT NULL, so a partially
  bound resume point cannot be written; the parametrised test omits
  each binding in turn and the server refuses every one. A protected
  archive entry cannot be evicted for low fitness through the eviction
  function, through a direct UPDATE, or through a DELETE, because the
  runtime holds only SELECT and INSERT and the append-only guard stops
  even a superuser DELETE.
- The tests found a real defect in the migration. The first draft used
  the IEEE self-comparison idiom to reject NaN scores, but PostgreSQL
  defines NaN = NaN as true and sorts NaN above every finite value, so
  a NaN combined score was accepted. The constraint now uses the
  inequality, which is false for NaN, and the test that caught it
  stays. A migration reviewed only by reading would have shipped this.
- The adversarial suite runs as the runtime principal, not as a
  superuser, so a refusal is the refusal the deployment would actually
  get. Where a superuser could still act, that is tested separately
  and the trigger catches it.
- Crash safety is proved by rolling back mid-transaction: a sealed but
  uncommitted checkpoint leaves no resume point, and a committed one
  reads back with every binding intact.
- A combined score may be recorded but may not decide protection
  (EF4-I45): protection is a stored property with its own reason
  vocabulary, and stripping it to enable an eviction is refused as an
  immutability violation.
- Residual limitations: this is the schema and its guarantees, not a
  deployed database — provisioning, connection management and the
  runtime adapter belong elsewhere; row-level security is not applied
  here because the store is single-tenant per deployment, unlike the
  D02 team store; performance under load is unmeasured; and this
  review is not external actor-independent certification.
