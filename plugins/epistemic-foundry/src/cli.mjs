#!/usr/bin/env node
// The payload CLI that `bin/efoundry.mjs` dispatches to.
//
// Status and health are read-only observations owned by this Node payload.
// Commands whose semantics belong to the bundled Python runtime are handed to
// it unchanged, with stdout, stderr, and the exit status forwarded verbatim.

import { runBundledCli } from "./python-runtime.mjs";
import {
  createHealthProjection,
  createStatusProjection,
  observeRuntime,
} from "./runtime-observation.mjs";

// Exit status for "the runtime could not start", which is not a command
// outcome.  It must not collide with either existing table: the Python CLI
// uses 0/10/20/30/40/50/60/70/80 and the T01 CLI table reserves 10-12, 20-22,
// 30, 40, 41 and 70.  71 is free in both.
const RUNTIME_UNAVAILABLE = 71;

const HELP = `epistemic-foundry plugin CLI

Usage: efoundry [--json] <command> [args...]

Node-only diagnostic commands:
  status                  report version and honest maturity
  health                  report component readiness and degraded states

Commands provided by the optional bundled Python runtime:
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

function emitStatus(projection, wantsJson) {
  const payload = projection.data;
  if (wantsJson) {
    process.stdout.write(`${JSON.stringify(payload, null, 2)}\n`);
  } else {
    process.stdout.write(
      `Epistemic Foundry ${payload.plugin_version ?? "unknown"}\n` +
        `qualified status:      ${payload.current_qualified_status}\n` +
        `implementation target: ${payload.implementation_target} (${payload.implementation_target_status})\n` +
        `overall state:         ${projection.state}\n` +
        `full v4 operational:   ${payload.full_v4_operational}\n` +
        `plugin payload:        ${payload.payload.status}\n` +
        `Node runtime:          ${payload.node_runtime.status} (${payload.node_runtime.version})\n` +
        `optional Python:       ${payload.interpreter.status}\n` +
        `workspace mapping:     ${payload.workspace.status}\n` +
        `bound MCP tools:       ${payload.bound_tools.join(", ")}\n` +
        `unavailable MCP tools: ${payload.unbound_tools.join(", ")}\n`,
    );
  }
  return 0;
}

function emitHealth(projection, wantsJson) {
  const payload = projection.data;
  if (wantsJson) {
    process.stdout.write(`${JSON.stringify(payload, null, 2)}\n`);
  } else {
    process.stdout.write(
      `overall state: ${projection.state}\n` +
        `qualified status: ${payload.current_qualified_status}\n` +
        `implementation target: ${payload.implementation_target} (${payload.implementation_target_status})\n`,
    );
    for (const component of payload.components) {
      process.stdout.write(
        `${component.component}: ${component.state}${component.reason ? ` — ${component.reason}` : ""}\n`,
      );
    }
  }
  return 0;
}

function emitLocalArgumentFailure(command, wantsJson) {
  const message = `${command} accepts no positional arguments`;
  if (wantsJson) {
    process.stderr.write(`${JSON.stringify({ message, status: "FAIL" })}\n`);
  } else {
    process.stderr.write(`${message}\n`);
  }
  return 2;
}

function runtimeInfo(wantsJson) {
  const observation = observeRuntime();
  const interpreter = observation.interpreter;
  const payload = {
    interpreter,
    runtime: observation.python_runtime,
  };
  if (wantsJson) {
    process.stdout.write(`${JSON.stringify(payload, null, 2)}\n`);
  } else {
    process.stdout.write(
      `runtime scope: ${payload.runtime.scope ?? "unknown"}\n` +
        `source commit: ${payload.runtime.source_commit ?? "unknown"}\n` +
        `bundled files: ${payload.runtime.file_count ?? "unknown"}\n` +
        `interpreter:   ${
          interpreter.status === "READY" ? interpreter.command : interpreter.error_code
        }\n`,
    );
  }
  return interpreter.status === "READY" && payload.runtime.status === "READY"
    ? 0
    : RUNTIME_UNAVAILABLE;
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
  if (positional[0] === "status") {
    if (positional.length !== 1) return emitLocalArgumentFailure("status", wantsJson);
    return emitStatus(createStatusProjection(), wantsJson);
  }
  if (positional[0] === "health") {
    if (positional.length !== 1) return emitLocalArgumentFailure("health", wantsJson);
    return emitHealth(createHealthProjection(), wantsJson);
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
