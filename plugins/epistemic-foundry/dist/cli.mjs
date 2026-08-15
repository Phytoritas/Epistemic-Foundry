#!/usr/bin/env node
// The payload CLI that `bin/efoundry.mjs` dispatches to.
//
// This file holds no domain logic.  It finds the bundled Python runtime, hands
// the user's arguments to it unchanged, and forwards stdout, stderr and the
// exit status.  Anything it decided on its own would be a second, divergent
// implementation of a surface Python already owns.

import { runBundledCli, readRuntimeManifest, resolveInterpreter } from "./python-runtime.mjs";

// Exit status for "the runtime could not start", which is not a command
// outcome.  It must not collide with either existing table: the Python CLI
// uses 0/10/20/30/40/50/60/70/80 and the T01 CLI table reserves 10-12, 20-22,
// 30, 40, 41 and 70.  71 is free in both.
const RUNTIME_UNAVAILABLE = 71;

const HELP = `epistemic-foundry plugin CLI

Usage: efoundry [--json] <command> [args...]

Commands are provided by the bundled runtime:
  status                  report version and honest maturity
  schemas                 list canonical schemas
  validate                validate an artifact against a canonical schema
  ledger verify           verify a Noetic Ledger hash chain
  retrieve build          build a lexical index from a corpus
  retrieve query          query the index or run a retrieval lane

Plugin-local commands:
  --runtime-info          describe the bundled runtime and interpreter
  --help                  show this message

Served retrieval lanes: lexical, citation, entity_variable.
The other eight canonical lanes are declared and return UNSEARCHED.
`;

function emitRuntimeFailure(failure, wantsJson) {
  if (wantsJson) {
    process.stderr.write(
      `${JSON.stringify({
        error_code: failure.error_code,
        message: failure.message,
        status: "RUNTIME_UNAVAILABLE",
      })}\n`,
    );
  } else {
    process.stderr.write(`${failure.error_code}: ${failure.message}\n`);
  }
  return RUNTIME_UNAVAILABLE;
}

function runtimeInfo(wantsJson) {
  const manifest = readRuntimeManifest();
  const interpreter = resolveInterpreter();
  const payload = {
    interpreter: interpreter.ok
      ? { command: interpreter.command, status: "READY" }
      : {
          error_code: interpreter.error_code,
          message: interpreter.message,
          status: "UNAVAILABLE",
        },
    runtime: manifest.ok
      ? {
          closure_sha256: manifest.manifest.closure_sha256 ?? null,
          file_count: manifest.manifest.file_count ?? null,
          scope: manifest.manifest.scope ?? null,
          served_retrieval_lanes: manifest.manifest.served_retrieval_lanes ?? [],
          source_commit: manifest.manifest.source_commit ?? null,
          source_root: manifest.manifest.source_root ?? null,
        }
      : { error_code: manifest.error_code, message: manifest.message },
  };
  if (wantsJson) {
    process.stdout.write(`${JSON.stringify(payload, null, 2)}\n`);
  } else {
    process.stdout.write(
      `runtime scope: ${payload.runtime.scope ?? "unknown"}\n` +
        `source commit: ${payload.runtime.source_commit ?? "unknown"}\n` +
        `bundled files: ${payload.runtime.file_count ?? "unknown"}\n` +
        `interpreter:   ${
          interpreter.ok ? interpreter.command : interpreter.error_code
        }\n`,
    );
  }
  return interpreter.ok && manifest.ok ? 0 : RUNTIME_UNAVAILABLE;
}

export function main(argv) {
  const wantsJson = argv.includes("--json");
  const positional = argv.filter((entry) => entry !== "--json");

  if (positional.length === 0 || positional[0] === "--help" || positional[0] === "-h") {
    process.stdout.write(HELP);
    return 0;
  }
  if (positional[0] === "--runtime-info") {
    return runtimeInfo(wantsJson);
  }

  const run = runBundledCli(argv);
  if (!run.ok) {
    return emitRuntimeFailure(run, wantsJson);
  }
  if (run.stdout) process.stdout.write(run.stdout);
  if (run.stderr) process.stderr.write(run.stderr);
  return run.status;
}

process.exitCode = main(process.argv.slice(2));
