# T02-0001 primary-session separate adversarial review

- Reviewer: primary session in a separate adversarial pass under the
  product-owner instruction forbidding subagents and Fleet;
  actor_independence=false is recorded, not hidden.
- Catalog composition: the nine mutating names are declared exactly
  once, in contracts/mcp/t02/tool-catalog.yaml. The sealed T01 catalog,
  its generated descriptor projection, and both shared envelope schemas
  are byte-identical, and the sealed exact-13 tests still pass. The
  catalog set carries membership, order, and counts and holds no MCP
  tool-name literal, so tools/list composes 13 + 9 = 22 without a
  second declaring source.
- No mutation without lease: the effect executor is unreachable unless
  policy grants the declared capability, required approvals verify, the
  issued lease covers the exact workspace:target scope, carries that
  capability, and binds exactly the verified approvals, and the lease
  revalidates unrevoked immediately before the effect. Each negative
  case asserts the executor recorded zero calls, not merely that the
  response was an error.
- Effects reconcile: an unresolved effect answers UNKNOWN with
  reconciliation_required and committed=null. It is never rendered as
  committed=false, which would falsely claim nothing happened, and
  never as INTERNAL. A crash between intent and receipt replays as
  UNKNOWN against a recorded unobserved-effect operation id instead of
  re-attempting the effect; a reservation with no intent may safely
  continue because the effect could not have started. Reconciliation
  appends a resolving receipt and refuses to invent a terminal status
  when the probe cannot observe the operation.
- Approval placement: verification sits inside CAPABILITY_AUTHORIZATION
  after policy and before lease issuance, so every refusal leaves no
  lease, no intent, and no effect. Self-approval is rejected by the
  service itself rather than delegated to the resolver, and an
  unresolvable approval record is refused without disclosing whether it
  exists. The sealed top-level error enum is not extended; a closed
  mutation subcode rides in details and its mapping is asserted against
  the sealed schema.
- Idempotency: the fingerprint covers dry_run, so a dry-run key can
  never be reused for a live commit; approval_record_ids are excluded,
  so supplying approvals after an APPROVAL_REQUIRED refusal is not a
  conflict. A committed key replays its stored receipt without a second
  effect.
- Residual limitations: every authority and evidence port is injected
  and exercised against in-memory fakes; kernel binding to live policy,
  approval, lease, revision, intent, and receipt stores remains T04/T05.
  Reconciliation probes are not wired to any external system. This
  review is not external actor-independent certification.
