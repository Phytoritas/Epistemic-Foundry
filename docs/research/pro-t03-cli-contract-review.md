# T03 current CLI contract review

Review the current T03 production implementation against repository authority. Return `NO_BLOCKER` or only material correctness, authority, compatibility, or security blockers. Ignore style and do not ask to run tests.

Authority and scope:

- `MASTER_SPEC.md`: T03 is “Stable CLI JSON/error and PATH-less surfaces”.
- `manifests/development_manifest.yaml`: T03 depends only on T01; its sole write scope is `packages/plugin-host/src/cli/**`; exit criteria are “commands round-trip contracts” and “stable error codes”.
- The current T02 adapter now has a bounded durable Attempt/CAS consumer contract, but still truthfully has no live Python-to-E02 kernel binding. Do not infer that T02 mutating runtime reachability exists.

Current T03 production behavior:

1. `command-surface.mjs` derives commands only from the sealed T01 read/planning catalog (`toolDescriptors()`), so T02 mutating commands remain unavailable/fail closed. The mapping between `foundry.*` tool names and CLI segments is reversible and collision-checked.
2. `parseArgv()` accepts only `--json` and one `--input <JSON object>`; duplicate input, malformed JSON, unknown flags, arrays, and scalars are rejected before the handler call.
3. `runCommand()` forwards the exact tool/arguments/request ID, emits the returned envelope only for `--json`, maps sealed error names to stable unique exit codes, and emits no improvised human substitute when JSON is absent.
4. `envelope.mjs` recursively accepts only plain JSON values, rejects cycles, sparse/accessor arrays, accessor/non-enumerable/symbol object properties, undefined and non-finite numbers, sorts object keys, preserves array order and nulls, and requires render→parse→render byte identity.
5. `error-codes.mjs` loads the sealed T01 error enum and refuses any missing, unknown, duplicated, reserved, non-integer, or out-of-range mapping.
6. `pathless.mjs` launches only `process.execPath` with an absolute script, `shell:false`, an absolute/default current cwd, a frozen allowlisted child environment, and case-insensitive rejection of PATH/PATHEXT/NODE_OPTIONS/NODE_PATH/PYTHONPATH overrides. A source scanner rejects known ambient executable-lookup forms.

The current dirty diff in T03 changes only its owned source/test paths and specifically removes the prior composed T02 command projection, rejects duplicate `--input`, hardens JSON object/array descriptors, and rejects lookup-variable override casing on Windows.

Questions:

1. Is the T01-only command surface the correct fail-closed T03 behavior until a later authority-owned mutating runtime binding exists?
2. Does any T03 requirement demand a production executable/transport bridge that cannot be implemented in the sole `packages/plugin-host/src/cli/**` scope, or are the current reusable CLI surfaces sufficient for this package?
3. Identify any concrete input that the current JSON, exit-code, argv, or PATH-less logic would wrongly accept, reject, or reinterpret in a way that violates the cited T03 contract.

Do not treat static source scanning as a complete security sandbox; judge only the stated T03 PATH-less/CLI boundary. Do not demand changes to shared schemas, G02 dispatcher files, T01/T02 catalogs, manifests, or evidence artifacts unless the authority truly makes T03 a `SPEC_GAP`.
