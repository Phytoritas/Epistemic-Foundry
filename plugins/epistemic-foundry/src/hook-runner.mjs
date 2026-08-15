// Codex SessionStart hook runner for the installed payload.
//
// Derived from the H01 adapter at adapters/codex/hook-runner.mjs and kept
// deliberately close to it.  The difference is that this copy reports the
// bundled runtime's real state: whether an interpreter was found, and which
// capabilities are actually served.  The H01 copy predates the bundled runtime
// and describes a tool surface this payload no longer has.
//
// Deliberately absent, because each would be a false capability claim:
//   - no session creation, resume, or restoration
//   - no ContextCapsule reconstruction
//   - no permission or tool-policy decision
//   - no ledger append, receipt, or artifact registration
//   - no package installation and no index building
//
// Wire contract: one JSON object on stdin, one JSON object on stdout, exit 0.
// A refusal writes only a stable code to stderr and exits nonzero, so a
// malformed event never becomes a silent success.

import { readFileSync } from "node:fs";

import { observeRuntime } from "./runtime-observation.mjs";

/** Verbs this runner answers. Anything else is refused, not ignored. */
export const REGISTERED_VERBS = Object.freeze(["session-start"]);

/** Upper bound on emitted context, so a hook cannot flood the session. */
export const MAX_CONTEXT_BYTES = 1024;

/** Upper bound on the complete hook event body. */
const MAX_STDIN_BYTES = 1024 * 1024;

export class HookRunnerError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "HookRunnerError";
    this.code = code;
  }
}

const readJsonOrNull = (path) => {
  try {
    return JSON.parse(readFileSync(path, "utf8"));
  } catch {
    return null;
  }
};

/**
 * Observe the installed payload and its runtime binding.
 *
 * Only facts this process can read or probe directly. An unreadable file
 * becomes a null observation rather than an assumed value.
 */
export const observeInstalledPayload = (pluginRoot) => {
  const manifest = readJsonOrNull(new URL("./.codex-plugin/plugin.json", pluginRoot));
  const inventory = readJsonOrNull(new URL("./skills/skill-inventory.json", pluginRoot));
  const descriptors = readJsonOrNull(new URL("./dist/tool-descriptors.json", pluginRoot));
  const observation = observeRuntime();

  return {
    interpreter_ready: observation.interpreter.status === "READY",
    interpreter_reason:
      observation.interpreter.message ?? observation.interpreter.error_code ?? null,
    interpreter_state: observation.interpreter.status,
    plugin_version: manifest?.version ?? null,
    served_lanes:
      observation.python_runtime.status === "READY"
        ? (observation.python_runtime.served_retrieval_lanes ?? [])
        : [],
    skill_count: Array.isArray(inventory?.skills) ? inventory.skills.length : null,
    tool_count: Array.isArray(descriptors?.tools) ? descriptors.tools.length : null,
  };
};

/**
 * Render the SessionStart context.
 *
 * `source` distinguishes a fresh start from a host resume or compaction. In
 * every case the text reports the host's action, never a Foundry session
 * action, because no Foundry session exists to act on.
 */
export const renderSessionStartContext = (payload, source) => {
  const boundary =
    source === "compact"
      ? "The host compacted the conversation; no Foundry session state was rebuilt."
      : source === "resume"
        ? "The host resumed a Codex session; no Foundry session state was restored."
        : "No Foundry session was created; the Foundry holds no session state.";

  const surface = payload.interpreter_ready
    ? `The canonical ${payload.tool_count ?? "?"}-tool MCP catalog is advertised; the Node-local foundry.status and foundry.health diagnostics are bound, every stateful or authorized tool returns UNAVAILABLE with a reason, and the auxiliary Python CLI is ready.`
    : payload.interpreter_state === "CONFIGURED_UNVERIFIED"
      ? `The canonical ${payload.tool_count ?? "?"}-tool MCP catalog is advertised; only foundry.status and foundry.health are bound. An absolute auxiliary Python interpreter is configured, but Python 3.12+ and dependency compatibility remain unverified until a CLI command runs.`
      : `The Node-local foundry.status and foundry.health diagnostics still answer. The auxiliary Python CLI is unavailable (${payload.interpreter_reason ?? "unknown"}); configure EFOUNDRY_PYTHON as an absolute path to Python 3.12 or newer.`;

  const lanes =
    payload.served_lanes.length > 0
      ? `Schema validation, ledger verification, and retrieval run through the bundled CLI, where ${payload.served_lanes.join(", ")} lanes are served and the other eight canonical lanes return UNSEARCHED.`
      : "No retrieval lanes are served in this state.";

  const skills =
    payload.skill_count === null
      ? "The skill inventory could not be read."
      : `${payload.skill_count} skills are installed.`;

  const text = [
    `Epistemic Foundry ${payload.plugin_version ?? "(unknown version)"} bootstrap observation.`,
    boundary,
    surface,
    lanes,
    skills,
    "Workflow execution, promotion, and evidence recomputation are not part of this package.",
  ].join(" ");

  return Buffer.byteLength(text, "utf8") <= MAX_CONTEXT_BYTES
    ? text
    : `${text.slice(0, MAX_CONTEXT_BYTES - 1)}\u2026`;
};

/**
 * Handle one raw Codex hook event.
 *
 * The host object is read, not trusted for authority: `source` only selects
 * wording, and no field is echoed back into the emitted context.
 */
export const handleHookEvent = (verb, rawEvent, pluginRoot) => {
  if (!REGISTERED_VERBS.includes(verb)) {
    throw new HookRunnerError("HOOK_VERB_UNREGISTERED", `unregistered hook verb: ${verb}`);
  }
  if (rawEvent === null || typeof rawEvent !== "object" || Array.isArray(rawEvent)) {
    throw new HookRunnerError("RAW_EVENT_UNREADABLE", "the hook event is not a JSON object");
  }
  if (rawEvent.hook_event_name !== undefined && rawEvent.hook_event_name !== "SessionStart") {
    throw new HookRunnerError(
      "HOOK_VERB_UNREGISTERED",
      `the session-start verb does not answer ${rawEvent.hook_event_name}`,
    );
  }

  const payload = observeInstalledPayload(pluginRoot);
  return {
    hookSpecificOutput: {
      hookEventName: "SessionStart",
      additionalContext: renderSessionStartContext(payload, rawEvent.source ?? null),
    },
  };
};

const readStdin = async () => {
  const body = Buffer.alloc(MAX_STDIN_BYTES);
  let bodyLength = 0;
  for await (const rawChunk of process.stdin) {
    const chunk = Buffer.isBuffer(rawChunk)
      ? rawChunk
      : Buffer.from(rawChunk, "utf8");
    if (chunk.length > MAX_STDIN_BYTES - bodyLength) {
      throw new HookRunnerError(
        "RAW_EVENT_UNREADABLE",
        "the hook event exceeds the 1 MiB limit",
      );
    }
    chunk.copy(body, bodyLength);
    bodyLength += chunk.length;
  }
  return body.subarray(0, bodyLength).toString("utf8");
};

export const main = async (argv, pluginRoot) => {
  const verb = argv[2];
  const text = await readStdin();
  let rawEvent;
  try {
    rawEvent = text.trim() === "" ? {} : JSON.parse(text);
  } catch {
    throw new HookRunnerError("RAW_EVENT_UNREADABLE", "the hook event is not valid JSON");
  }
  return handleHookEvent(verb, rawEvent, pluginRoot);
};

/** Run as a process: read stdin, emit one JSON response, exit 0 or 1. */
try {
  const response = await main(process.argv, new URL("../", import.meta.url));
  process.stdout.write(`${JSON.stringify(response)}\n`);
} catch (cause) {
  process.stderr.write(`${cause.code ?? "HOOK_RUNNER_FAILED"}\n`);
  process.exitCode = 1;
}
