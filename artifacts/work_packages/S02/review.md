# S02 review record

Status: `PASS`

Review mode: `USER_EXPLICIT_INDEPENDENT_APPROVAL`

The user is external to the package author and explicitly stated in the active
goal that all independent reviews are approved (`독립 검토는 모두 승인한다`).
That external human authority decision is recorded here as approval of S02 for
the exact revisions listed below after the objective checks were rerun on
2026-07-27. The approval is limited to this dependency checkpoint and becomes
stale if any reviewed hash changes, any cited command record is invalidated, or
a later security finding contradicts the reviewed evidence.

The technical review below was performed by the primary author under the
user's no-subagent constraint. This record does not claim that a separate agent
or `contract_reviewer` performed another technical audit. It distinguishes the
author-produced technical evidence from the user's independent external
approval decision.

Reviewed implementation hashes:

- `packages/foundry-kernel/src/security/execution/execution-policy.mjs`: `ac5aa290bd830079abca12147e10f706326fffd1c1e9fb815d8539f0013e7fd1`
- `packages/foundry-kernel/src/security/execution/secret-exfiltration.test.mjs`: `54b662c2e87c63bb4e94731b130614071950dfe16b5f15ba2a55cea0fd010b1b`
- `packages/foundry-kernel/src/security/execution/path-escape.test.mjs`: `8ac295dfa58336e3afd06b17e9b67d74d1c95c1ebc58d2b668d69cbe0603dbb5`
- `packages/foundry-kernel/src/security/execution/README.md`: `a839b1de5bb10c3dde7cfd27ee61d0fe46b652f76cba0018734ce8f874579314`

Resolved author-review findings:

- `S02-RF001` — The first design exported module-global secret-handle and
  execution-policy issuers. Any same-process importer could mint an object the
  guard accepted. The implementation now creates isolated
  `createExecutionSecurityBoundary()` compartments with private per-boundary
  `WeakMap`/`WeakSet` brands. Kernel bootstrap can retain `issuer` and expose
  only `guard`; handles, policies, or decisions from another compartment fail.
- `S02-RF002` — A policy originally retained only the canonical resource-root
  string, and egress authorization did not state redirect behavior. The guard
  now binds root device/inode/birth identity, revalidates it on every path
  authorization, rejects URL fragments, and emits
  `REAUTHORIZE_EACH_HOP` for redirects.
- `S02-RF003` — Policy and payload inspection initially lacked explicit array,
  object-field, and field-name limits, and the path walk did not reject a
  distinct mounted filesystem. Bounded inspection and a same-device walk now
  fail closed before resource exhaustion or mount-boundary traversal.
- `S02-RF004` — The initial no-follow walk permitted an absent intermediate
  parent and covered only common Windows reserved names. Only a missing final
  component is now potentially admissible, missing parents fail, and extended
  Windows device aliases and normalization variants are rejected.
- `S02-RF005` — Secret-free payload inspection returned a public `ALLOW`
  record, which could be confused with branded execution authority, and
  `WRITE` could name a missing target. Payload inspection now returns a
  non-authoritative `PASS`; only branded decisions authorize effects. `CREATE`
  requires an absent leaf, while every other operation requires an existing
  target.

Author review confirmed:

1. Secret constructors accept identifiers and HTTPS origin bindings only; they
   never accept raw secret material. Opaque handles have no own properties,
   serialize to `{}`, and lose validity when copied or JSON-round-tripped.
2. Handles are rejected at prompt, evidence-artifact, log, export, and ordinary
   network-payload boundaries. Descriptor-only validation rejects accessors,
   Proxies, cycles, non-JSON values, oversized structures, secret-bearing field
   names, URL credentials, bearer tokens, and private-key markers without
   invoking caller code.
3. Last-mile secret use requires a policy-allowlisted exact canonical origin
   and an independent matching HTTPS origin binding on the handle. Decisions
   expose no handle ID, vault ID, or secret bytes.
4. Egress is either disabled or an exact HTTP(S) origin allowlist. Scheme,
   host, and port mismatches, userinfo, relative and non-HTTP URLs, fragments,
   unknown destinations, and unauthorized redirect destinations fail closed.
5. Resource roots must be existing real directories. Every request uses a
   forward-slash relative path, an operation grant, root identity revalidation,
   a canonical same-filesystem no-follow walk, Windows ambiguity checks, and
   explicit existing-target versus create-target semantics.
6. Execution authorization is bound to an exact sandbox profile identifier.
   This is a profile contract, not a claim that a container or OS sandbox is
   implemented.
7. Boundary inputs reject custom prototypes, Proxies, accessors, sparse arrays,
   unexpected fields, hostile coercion, copied policies, copied decisions, and
   cross-compartment brands.
8. The module performs no secret resolution, environment read, process launch,
   network request, or filesystem mutation. A separately trusted effect adapter
   must consume the branded decision and revalidate immediately before effect.
9. Both required suites pass with 18 tests. Coverage is 90.60% lines, 82.46%
   branches, and 100% functions; the integrated S01+S02 security suite has 35
   passing tests.
10. Workspace structure/boundary checks, all 789 Python tests, and the
    11-artifact byte-identical double build pass. The reproducible
    `foundry-kernel` tarball contains all four S02 files.

Open implementation-scope findings: none found by the author.

Resolved independent-approval finding:

- `S02-RB001` — Resolved by the user's explicit external human approval,
  bound to the exact hashes above and fresh command evidence `S02-C015` through
  `S02-C019`. The author did not self-approve. This approval is automatically
  invalidated by source drift or a regression in the cited checks.

Scope limits retained for later packages:

- This S02 primitive does not implement a container, process sandbox, network
  namespace, DNS pinning/rebinding defense, atomic descriptor-relative open,
  quotas, effect receipts, or integration with every future tool/provider path.
- S04 owns the phase red-team gate. T04 owns sandbox and external-tool adapter
  integration. Those later packages must prove effect-time enforcement and may
  not infer it from this policy primitive.
- Raw-secret pattern checks are defense in depth, not an exhaustive secret
  detector. The normative invariant is that trusted adapters never provide raw
  secret bytes to these outbound data paths.
- The package remains a private scaffold with no public export map; API
  stabilization and integration are later work-package scope.
