# S02-0001 independent review of bounded-agent work

- Author: the bounded implementation agent that wrote
  packages/foundry-kernel/src/security/execution. Reviewer: this seal-prep
  session, a distinct actor that did not author the execution boundary. The
  author never approves its own work, so actor_independence HOLDS for this
  review; external actor-independent certification does NOT, and no such
  claim is made. S02 is risk_class=medium but is a security-critical secret,
  path, and egress boundary, so it was attacked on its no-exfiltration,
  no-path-escape, and controlled-egress contracts rather than skimmed.
- Secrets never leave the boundary. Secret references are opaque frozen
  handles created from an identifier and HTTPS origin bindings only; the
  constructor accepts no raw material and rejects any extra field
  (UNEXPECTED_FIELD), so value/token/password inputs fail. Handles have no
  own properties, serialize to {}, and lose validity when copied or
  JSON-round-tripped. assertSecretFreeBoundaryPayload denies those handles
  (SECRET_HANDLE_BOUNDARY_DENIED), secret-bearing field names
  (SECRET_FIELD_BOUNDARY_DENIED after NFKC normalization), and secret-shaped
  text -- private-key headers, Bearer tokens, and URL userinfo
  (SECRET_PATTERN_BOUNDARY_DENIED) -- at all five outbound boundaries
  including PROMPT, fail-closed. Inspection is descriptor-only and rejects
  accessors, Proxies, cycles, non-JSON values, and oversized structures
  without running attacker code. The secret-free result is a
  non-authoritative PASS record, not a branded decision.
- Last-mile secret use is doubly bound. authorizeSecretEgress requires both
  a policy-allowlisted exact canonical origin and a handle independently
  bound to that same HTTPS origin (SECRET_DESTINATION_DENIED otherwise); the
  returned decision exposes origin and profile but no handle id, vault id,
  or secret bytes, verified by asserting the serialized decision contains
  neither the synthetic handle nor vault identifier.
- Path escape is prevented. Resource paths must be portable forward-slash
  relative paths; drive letters, backslashes, colons, '.'/'..', trailing
  dot/space, and Windows reserved and device-alias basenames are denied
  (PATH_ESCAPE_DENIED). The canonical path.relative result may not escape
  the root, and a per-segment lstat/realpath no-follow walk denies symlinks
  and junctions (PATH_LINK_DENIED), mount crossings (PATH_MOUNT_DENIED),
  non-directory traversal (PATH_NOT_TRAVERSABLE), and missing parents
  (PATH_PARENT_MISSING). Root device/inode/birth identity is revalidated on
  every request, so a replaced root fails closed (RESOURCE_ROOT_CHANGED),
  and only create may name an absent leaf. On this host the symlink/junction
  fixtures were created and exercised (no t.skip), so both no-follow tests
  ran fully.
- Egress is controlled. Network policy is disabled or an exact canonical
  HTTP(S) origin allowlist; scheme, host, and port mismatches, userinfo
  (EGRESS_CREDENTIALS_DENIED), fragments (EGRESS_FRAGMENT_DENIED), relative
  and non-HTTP URLs, unknown destinations (EGRESS_DESTINATION_DENIED), and
  unauthorized redirect hops fail closed; allowed decisions carry
  redirectPolicy=REAUTHORIZE_EACH_HOP. Every authorization is bound to an
  exact sandbox profile identifier -- a profile contract, not a claim that
  an OS or container sandbox exists.
- Compartment isolation. Handles, policies, and decisions carry per-boundary
  private WeakMap/WeakSet brands, so objects minted by a foreign compartment
  or copied through JSON are rejected (UNRECOGNIZED_POLICY,
  UNRECOGNIZED_SECRET_HANDLE, isAuthorizationDecision=false). Importing the
  module is not enough to mint authority the kernel guard accepts.
- Dependency and checks: the boundary is a pure ESM module that imports only
  node:fs, node:path, and node:util and adds no new production dependency.
  It builds on the sealed S01 trust-zone package (S01-0001 PASS), a
  report-level dependency rather than imported code. Ruff lint and format,
  the two required checks (secret_exfiltration_test 9/9, path_escape_test
  9/9), targeted 18/18, full Python 1261/1261, full Node 1274/1274 across
  113 files, and git diff --check all pass with zero failures. The full Node
  inventory grew from the sealed S01/D03 baseline of 111 files as concurrent
  observability work added two unrelated test modules; the gate is zero Node
  failures against the live inventory, not a fixed count.
- Residual limitations: the module performs no secret resolution, process
  launch, network request, or filesystem mutation; a separately trusted and
  qualified effect adapter must consume the branded decision and revalidate
  immediately before effect. It does not implement a container, process
  sandbox, network namespace, DNS-rebinding defense, quota, or atomic
  descriptor-relative open, and raw-secret pattern checks are defense in
  depth rather than exhaustive detection. The S04 red-team gate and T04
  sandbox/tool-adapter integration are later scope. Verdict: PASS on the
  exact S02 package contract.
