# T03-0001 primary-session separate adversarial review

- Reviewer: primary session in a separate adversarial pass under the
  product-owner instruction forbidding subagents and Fleet;
  actor_independence=false is recorded, not hidden.
- The command table is projected, not declared. Every one of the 22
  composed tools maps to exactly one command and back, so the CLI can
  neither expose a command the tool surface lacks nor miss one it has,
  and no tool name is restated outside its catalog. An unknown command
  or an unknown tool name is refused rather than guessed.
- Round-tripping is byte identity, not structural equality. Rendering
  sorts keys and keeps nulls, an undefined field is refused rather than
  silently dropped, and non-finite numbers and cycles cannot be
  emitted at all. The round trip is proved before the bytes are
  written, so a non-round-tripping envelope never reaches a consumer,
  and the CLI adds no field of its own to what the tool produced.
- Exit codes are a checked contract. The table is verified at load
  against the sealed error vocabulary and fails closed on either a
  missing or an extra entry; codes are distinct, inside 1..125, and
  never 126, 127, or 0, so a tool failure can never be confused with a
  launch failure or a success. The mapping is reversible for
  diagnosis, and an unmapped code is refused rather than folded into
  INTERNAL, because a caller told the wrong failure is worse off than
  one told the contract diverged.
- PATH-lessness is enforced three ways: the only executable is
  process.execPath, the child environment is built from an allowlist
  that excludes PATH and cannot be overridden back in, and every CLI
  source plus the shipped dispatcher is scanned for shell:true, exec
  by string, PATH reads, and bare interpreter names. The spawn plan is
  frozen, so a caller cannot re-enable the shell after the fact.
- Without --json the machine surface is withheld rather than
  approximated in prose, so nothing can parse a human string by
  accident.
- Residual limitations: this package delivers the CLI surface, not a
  built dist/cli.mjs payload, which remains a build package; argument
  schema validation belongs to the sealed tool catalogs and is not
  duplicated here; and the PATH-less guarantee covers the CLI and its
  dispatcher, not arbitrary code elsewhere in the host. This review is
  not external actor-independent certification.
