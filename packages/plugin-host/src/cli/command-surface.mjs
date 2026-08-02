// The CLI command table, derived from the composed MCP tool surface.
//
// Command names are not declared here.  They are projected from the sealed
// catalogs so the CLI cannot expose a command the tool surface does not have,
// or miss one it does: `foundry.claim.promote` becomes `claim promote`, and the
// mapping is reversible so a captured command line can be traced back to the
// exact tool it invoked.

import { mergedToolDescriptors } from "../mcp/write/catalog-set.mjs";
import { CliContractError, exitCodeFor, EXIT_SUCCESS } from "./error-codes.mjs";
import { emitJson, JSON_FLAG } from "./envelope.mjs";

/** Every tool name carries this prefix; the CLI drops it. */
const TOOL_NAMESPACE = "foundry.";

function commandPathFor(toolName) {
  if (!toolName.startsWith(TOOL_NAMESPACE)) {
    throw new CliContractError(
      "TOOL_NAME_UNEXPECTED",
      `${toolName} does not belong to the foundry namespace`,
    );
  }
  return toolName.slice(TOOL_NAMESPACE.length).split(".");
}

function buildSurface() {
  const byCommand = new Map();
  const byTool = new Map();
  for (const descriptor of mergedToolDescriptors()) {
    const toolName = String(descriptor.name);
    const segments = commandPathFor(toolName);
    const command = segments.join(" ");
    if (byCommand.has(command)) {
      throw new CliContractError(
        "COMMAND_COLLISION",
        `${toolName} and ${byCommand.get(command).tool} both map to "${command}"`,
      );
    }
    const entry = Object.freeze({
      command,
      mutating: descriptor.annotations.sideEffectClass === "MUTATING_EFFECT",
      segments: Object.freeze(segments),
      title: String(descriptor.title),
      tool: toolName,
    });
    byCommand.set(command, entry);
    byTool.set(toolName, entry);
  }
  if (byCommand.size === 0) {
    throw new CliContractError(
      "COMMAND_SURFACE_EMPTY",
      "the composed catalog projected no commands",
    );
  }
  return { byCommand, byTool };
}

const SURFACE = buildSurface();

/** Every command, sorted, as immutable rows. */
export function commandSurface() {
  return [...SURFACE.byCommand.values()].sort((left, right) =>
    left.command < right.command ? -1 : left.command > right.command ? 1 : 0,
  );
}

/** Resolve argv segments to the exact tool they name. */
export function resolveCommand(segments) {
  if (!Array.isArray(segments) || segments.some((entry) => typeof entry !== "string")) {
    throw new CliContractError(
      "ARGUMENTS_INVALID",
      "command segments must be an array of strings",
    );
  }
  const command = segments.join(" ");
  const entry = SURFACE.byCommand.get(command);
  if (entry === undefined) {
    throw new CliContractError(
      "UNKNOWN_COMMAND",
      `no command named "${command}"`,
      { command },
    );
  }
  return entry;
}

/** The command line that invokes one tool; the inverse of `resolveCommand`. */
export function commandForTool(toolName) {
  const entry = SURFACE.byTool.get(String(toolName));
  if (entry === undefined) {
    throw new CliContractError(
      "UNKNOWN_TOOL_NAME",
      `no command projects ${String(toolName)}`,
      { tool: toolName },
    );
  }
  return entry;
}

/** Flags that consume the token after them; their values are never segments. */
const VALUE_FLAGS = Object.freeze(["--input", "--request-id", "--workspace"]);

/**
 * Split argv into command segments, flags, and the parsed `--input` object.
 *
 * A value flag consumes the token after it, so a JSON argument can never be
 * mistaken for a command segment.  An unrecognised flag is refused rather than
 * ignored: silently dropping a flag makes a typo look like it worked.
 */
export function parseArgv(argv) {
  const segments = [];
  const flags = new Set();
  const values = new Map();
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (typeof token !== "string") {
      throw new CliContractError("ARGUMENTS_INVALID", "argv entries must be strings");
    }
    if (!token.startsWith("--")) {
      segments.push(token);
      continue;
    }
    if (VALUE_FLAGS.includes(token)) {
      const value = argv[index + 1];
      if (typeof value !== "string") {
        throw new CliContractError(
          "ARGUMENTS_INVALID",
          `${token} requires a value`,
          { flag: token },
        );
      }
      values.set(token, value);
      index += 1;
      continue;
    }
    if (token !== JSON_FLAG) {
      throw new CliContractError("ARGUMENTS_INVALID", `unknown flag ${token}`, {
        flag: token,
      });
    }
    flags.add(token);
  }
  let args = {};
  if (values.has("--input")) {
    try {
      args = JSON.parse(values.get("--input"));
    } catch (error) {
      throw new CliContractError(
        "ARGUMENTS_INVALID",
        `--input is not valid JSON: ${error.message}`,
      );
    }
    if (args === null || typeof args !== "object" || Array.isArray(args)) {
      throw new CliContractError("ARGUMENTS_INVALID", "--input must be a JSON object");
    }
  }
  return { args, segments, values, wantsJson: flags.has(JSON_FLAG) };
}

/**
 * Run one command and return its bytes and exit status.
 *
 * The envelope the handler returns is emitted verbatim; the CLI adds nothing to
 * it, so what a script parses is exactly what the tool surface produced.  A
 * command invoked without `--json` still runs, but its machine output is
 * withheld rather than approximated in prose.
 */
export async function runCommand(argv, handlerPort, { requestId }) {
  if (!Array.isArray(argv)) {
    throw new CliContractError("ARGUMENTS_INVALID", "argv must be an array");
  }
  const { args, segments, wantsJson } = parseArgv(argv);
  const entry = resolveCommand(segments);
  const { envelope, isError } = await handlerPort.call(entry.tool, args, requestId);
  return {
    command: entry.command,
    exitCode: isError ? exitCodeFor(String(envelope.error_code)) : EXIT_SUCCESS,
    isError: Boolean(isError),
    stdout: wantsJson ? emitJson(envelope) : "",
    tool: entry.tool,
  };
}
