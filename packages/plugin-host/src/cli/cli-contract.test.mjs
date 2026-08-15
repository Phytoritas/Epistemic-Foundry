// cli_contract_test — commands round-trip contracts and error codes are stable.
//
// Exit criteria under test: "commands round-trip contracts" and "stable error
// codes".  The command table is projected from the sealed T01 read/planning
// catalog rather than declared, every envelope survives render → parse → render
// byte-identically, and the exit-code table must cover the sealed error
// vocabulary exactly.

import assert from "node:assert/strict";
import test from "node:test";

import { toolDescriptors } from "../mcp/read/mcp-server.mjs";
import {
  commandForTool,
  commandSurface,
  resolveCommand,
  runCommand,
} from "./command-surface.mjs";
import { JSON_FLAG, emitJson, parseJson, renderJson, roundTrips } from "./envelope.mjs";
import {
  CliContractError,
  EXIT_CODE_CEILING,
  EXIT_CODE_FLOOR,
  EXIT_SUCCESS,
  RESERVED_EXIT_CODES,
  errorCodeForExit,
  exitCodeFor,
  exitCodeTable,
  sealedErrorVocabulary,
} from "./error-codes.mjs";

function resultEnvelope(overrides = {}) {
  return {
    data: { status: "ready" },
    data_schema_refs: [],
    degradation_reason: null,
    generated_at: "2026-08-01T14:00:00Z",
    protocol_version: "2026-07-28",
    read_model_state: "READY",
    receipts: [],
    request_id: "req-1",
    tool: "foundry.status",
    workspace_id: "ws-1",
    ...overrides,
  };
}

function errorEnvelope(errorCode = "UNAUTHORIZED") {
  return {
    details: null,
    error_code: errorCode,
    message: `refused: ${errorCode}`,
    protocol_version: "2026-07-28",
    request_id: "req-1",
    retryable: false,
    tool: "foundry.status",
  };
}

function port(envelope, isError = false) {
  return {
    calls: [],
    async call(toolName, args, requestId) {
      this.calls.push({ args, requestId, toolName });
      return { envelope, isError };
    },
  };
}

test("cli_contract_test: every T01 read/planning tool projects exactly one command", () => {
  const surface = commandSurface();
  const descriptors = toolDescriptors();

  assert.equal(surface.length, descriptors.length);
  assert.equal(new Set(surface.map((entry) => entry.command)).size, surface.length);
  for (const descriptor of descriptors) {
    assert.equal(commandForTool(descriptor.name).tool, descriptor.name);
  }
});

test("cli_contract_test: the command name is the tool name without its namespace", () => {
  assert.equal(commandForTool("foundry.search.plan").command, "search plan");
  assert.deepEqual(commandForTool("foundry.search.plan").segments, ["search", "plan"]);
  assert.equal(resolveCommand(["search", "plan"]).tool, "foundry.search.plan");
});

test("cli_contract_test: the T01 command surface contains no mutating commands", () => {
  const surface = commandSurface();
  const mutating = surface.filter((entry) => entry.mutating).map((entry) => entry.tool);

  assert.equal(surface.length, 13);
  assert.equal(mutating.length, 0);
  assert.equal(commandForTool("foundry.status").mutating, false);
});

test("cli_contract_test: T02 promotion remains unavailable", () => {
  assert.throws(
    () => commandForTool("foundry.claim.promote"),
    (error) => error instanceof CliContractError && error.code === "UNKNOWN_TOOL_NAME",
  );
  assert.throws(
    () => resolveCommand(["claim", "promote"]),
    (error) => error instanceof CliContractError && error.code === "UNKNOWN_COMMAND",
  );
});

test("cli_contract_test: an unknown command is refused, not guessed", () => {
  assert.throws(
    () => resolveCommand(["claim", "unpromote"]),
    (error) => error instanceof CliContractError && error.code === "UNKNOWN_COMMAND",
  );
  assert.throws(
    () => commandForTool("foundry.invented"),
    (error) => error instanceof CliContractError && error.code === "UNKNOWN_TOOL_NAME",
  );
});

test("cli_contract_test: a result envelope round-trips byte-identically", () => {
  const envelope = resultEnvelope();

  assert.equal(roundTrips(envelope), true);
  assert.equal(renderJson(parseJson(renderJson(envelope))), renderJson(envelope));
  assert.deepEqual(parseJson(renderJson(envelope)), envelope);
});

test("cli_contract_test: rendering sorts keys so the bytes are stable", () => {
  const forward = renderJson({ a: 1, b: 2, nested: { x: 1, y: 2 } });
  const reversed = renderJson({ nested: { y: 2, x: 1 }, b: 2, a: 1 });

  assert.equal(forward, reversed);
  assert.equal(forward.endsWith("\n"), true);
});

test("cli_contract_test: an error envelope round-trips byte-identically", () => {
  for (const name of sealedErrorVocabulary()) {
    assert.equal(roundTrips(errorEnvelope(name)), true, name);
  }
});

test("cli_contract_test: a null field survives rather than being dropped", () => {
  const envelope = resultEnvelope({ data: null, degradation_reason: "provider down" });

  const parsed = parseJson(renderJson(envelope));

  assert.equal("data" in parsed, true);
  assert.equal(parsed.data, null);
});

test("cli_contract_test: an undefined field is refused rather than silently dropped", () => {
  assert.throws(
    () => renderJson({ data: undefined }),
    (error) =>
      error instanceof CliContractError && error.code === "ENVELOPE_NOT_CANONICAL",
  );
});

test("cli_contract_test: non-JSON objects and sparse arrays are refused rather than rewritten", () => {
  const sparse = [];
  sparse.length = 1;

  for (const candidate of [new Date("2026-08-01T00:00:00Z"), new Map(), sparse]) {
    assert.throws(
      () => renderJson({ value: candidate }),
      (error) =>
        error instanceof CliContractError && error.code === "ENVELOPE_NOT_CANONICAL",
    );
  }
});

test("cli_contract_test: reserved-looking JSON keys remain ordinary data", () => {
  const envelope = JSON.parse('{"__proto__":{"polluted":true},"constructor":"data"}');

  assert.deepEqual(parseJson(renderJson(envelope)), envelope);
});

test("cli_contract_test: non-finite numbers and cycles cannot be emitted", () => {
  const cyclic = {};
  cyclic.self = cyclic;

  for (const candidate of [{ value: Number.NaN }, { value: Infinity }, cyclic]) {
    assert.throws(
      () => renderJson(candidate),
      (error) =>
        error instanceof CliContractError && error.code === "ENVELOPE_NOT_CANONICAL",
    );
  }
});

test("cli_contract_test: malformed output is refused rather than repaired", () => {
  for (const candidate of ["{", "[]", "null", '"text"']) {
    assert.throws(
      () => parseJson(candidate),
      (error) =>
        error instanceof CliContractError && error.code === "ENVELOPE_UNPARSEABLE",
    );
  }
});

test("cli_contract_test: emitJson proves the round trip before writing bytes", () => {
  const envelope = resultEnvelope();

  assert.equal(emitJson(envelope), renderJson(envelope));
});

test("cli_contract_test: the exit-code table covers the sealed vocabulary exactly", () => {
  const table = exitCodeTable();
  const sealed = sealedErrorVocabulary();

  assert.deepEqual(Object.keys(table).sort(), sealed);
  assert.equal(sealed.length, 10);
});

test("cli_contract_test: every exit code is distinct and outside the reserved range", () => {
  const codes = Object.values(exitCodeTable());

  assert.equal(new Set(codes).size, codes.length);
  for (const code of codes) {
    assert.equal(Number.isInteger(code), true);
    assert.equal(code >= EXIT_CODE_FLOOR && code <= EXIT_CODE_CEILING, true, `${code}`);
    assert.equal(RESERVED_EXIT_CODES.includes(code), false, `${code}`);
    assert.notEqual(code, EXIT_SUCCESS);
  }
});

test("cli_contract_test: exit codes are reversible for diagnosis", () => {
  for (const [name, code] of Object.entries(exitCodeTable())) {
    assert.equal(errorCodeForExit(code), name);
  }
  assert.equal(errorCodeForExit(99), null);
});

test("cli_contract_test: an unmapped error code is refused, not folded into INTERNAL", () => {
  assert.throws(
    () => exitCodeFor("SOMETHING_NEW"),
    (error) => error instanceof CliContractError && error.code === "UNKNOWN_ERROR_CODE",
  );
});

test("cli_contract_test: a successful command emits the envelope verbatim and exits zero", async () => {
  const envelope = resultEnvelope();
  const handler = port(envelope);

  const outcome = await runCommand(["status", JSON_FLAG], handler, {
    requestId: "req-1",
  });

  assert.equal(outcome.exitCode, EXIT_SUCCESS);
  assert.equal(outcome.tool, "foundry.status");
  assert.equal(outcome.stdout, renderJson(envelope));
  assert.deepEqual(parseJson(outcome.stdout), envelope);
});

test("cli_contract_test: a refusal maps to its stable exit code", async () => {
  for (const [name, code] of Object.entries(exitCodeTable())) {
    const handler = port(errorEnvelope(name), true);

    const outcome = await runCommand(["status", JSON_FLAG], handler, {
      requestId: "req-1",
    });

    assert.equal(outcome.exitCode, code, name);
    assert.equal(outcome.isError, true, name);
    assert.equal(parseJson(outcome.stdout).error_code, name, name);
  }
});

test("cli_contract_test: the CLI adds nothing to the envelope it was given", async () => {
  const envelope = resultEnvelope();
  const handler = port(envelope);

  const outcome = await runCommand(["status", JSON_FLAG], handler, {
    requestId: "req-1",
  });

  assert.deepEqual(Object.keys(parseJson(outcome.stdout)).sort(), Object.keys(envelope).sort());
});

test("cli_contract_test: --input is forwarded as parsed arguments", async () => {
  const handler = port(resultEnvelope());

  await runCommand(
    ["status", JSON_FLAG, "--input", '{"workspace_id":"ws-1"}'],
    handler,
    { requestId: "req-1" },
  );

  assert.deepEqual(handler.calls[0].args, { workspace_id: "ws-1" });
  assert.equal(handler.calls[0].requestId, "req-1");
});

test("cli_contract_test: malformed --input is refused before the handler runs", async () => {
  const handler = port(resultEnvelope());

  await assert.rejects(
    runCommand(["status", JSON_FLAG, "--input", "{oops"], handler, {
      requestId: "req-1",
    }),
    (error) => error instanceof CliContractError && error.code === "ARGUMENTS_INVALID",
  );
  assert.deepEqual(handler.calls, []);
});

test("cli_contract_test: duplicate --input is refused instead of silently overriding", async () => {
  const handler = port(resultEnvelope());

  await assert.rejects(
    runCommand(
      ["status", "--input", '{"workspace_id":"first"}', "--input", '{"workspace_id":"second"}'],
      handler,
      { requestId: "req-1" },
    ),
    (error) => error instanceof CliContractError && error.code === "ARGUMENTS_INVALID",
  );
  assert.deepEqual(handler.calls, []);
});

for (const unsupportedFlag of ["--request-id", "--workspace"]) {
  test(`cli_contract_test: unsupported ${unsupportedFlag} is refused before the handler runs`, async () => {
    const handler = port(resultEnvelope());

    await assert.rejects(
      runCommand(["status", JSON_FLAG, unsupportedFlag, "value"], handler, {
        requestId: "req-1",
      }),
      (error) => error instanceof CliContractError && error.code === "ARGUMENTS_INVALID",
    );
    assert.deepEqual(handler.calls, []);
  });
}

test("cli_contract_test: without --json the machine surface is withheld, not approximated", async () => {
  const handler = port(resultEnvelope());

  const outcome = await runCommand(["status"], handler, { requestId: "req-1" });

  assert.equal(outcome.stdout, "");
  assert.equal(outcome.exitCode, EXIT_SUCCESS);
});
