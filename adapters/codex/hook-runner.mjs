// Codex SessionStart hook runner.
//
// This is the only hook the Foundry can answer truthfully today.  There is no
// FORGE session store, no ContextCapsule producer, and no policy engine, so
// the runner does exactly one thing: it observes what the installed payload
// actually is and states the boundary of what it does not do.
//
// Deliberately absent, because each would be a false capability claim:
//   - no session creation, resume, or restoration
//   - no ContextCapsule reconstruction
//   - no permission or tool-policy decision
//   - no ledger append, receipt, or artifact registration
//   - no subagent adjudication
//
// Wire contract: one JSON object on stdin, one JSON object on stdout, exit 0.
// A refusal writes only a stable code to stderr and exits nonzero, so a
// malformed event never becomes a silent success.

import { readFileSync } from "node:fs";

/** Verbs this runner answers.  Anything else is refused, not ignored. */
export const REGISTERED_VERBS = Object.freeze(["session-start"]);

/** Upper bound on emitted context, so a hook cannot flood the session. */
export const MAX_CONTEXT_BYTES = 1024;

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
 * Observe the installed payload.
 *
 * Only facts this process can read directly.  An unreadable file becomes a
 * null observation rather than an assumed value.
 */
export const observeInstalledPayload = (pluginRoot) => {
  const manifest = readJsonOrNull(new URL("./.codex-plugin/plugin.json", pluginRoot));
  const inventory = readJsonOrNull(new URL("./skills/skill-inventory.json", pluginRoot));
  const descriptors = readJsonOrNull(new URL("./dist/tool-descriptors.json", pluginRoot));

  return {
    plugin_version: manifest?.version ?? null,
    skills_registered: typeof manifest?.skills === "string",
    mcp_registered: typeof manifest?.mcpServers === "string",
    skill_count: Array.isArray(inventory?.skills) ? inventory.skills.length : null,
    advertised_tool_count: Array.isArray(descriptors?.tools) ? descriptors.tools.length : null,
  };
};

/**
 * Render the SessionStart context.
 *
 * `source` distinguishes a fresh start from a host resume or compaction.  In
 * every case the text reports the host's action, never a Foundry session
 * action, because no Foundry session exists to act on.
 */
export const renderSessionStartContext = (payload, source) => {
  const boundary =
    source === "compact"
      ? "The host compacted the conversation. No Foundry ContextCapsule was rebuilt and no FORGE session state was restored."
      : source === "resume"
        ? "The host resumed a Codex session. No FORGE session was resumed; the Foundry holds no session state."
        : "No FORGE session was created; the Foundry holds no session state.";

  const surface =
    payload.advertised_tool_count === null
      ? "The packaged tool catalog could not be read."
      : `The packaged MCP surface advertises ${payload.advertised_tool_count} canonical tools; only status, health, and map query are backed, and the rest return UNAVAILABLE.`;

  const skills =
    payload.skill_count === null
      ? "The skill inventory could not be read."
      : `${payload.skill_count} skills are installed.`;

  const text = [
    `Epistemic Foundry ${payload.plugin_version ?? "(unknown version)"} bootstrap observation.`,
    boundary,
    surface,
    skills,
    "Permission, tool-policy, prompt, post-tool, and subagent hooks are unregistered because no producer backs them.",
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
  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  return Buffer.concat(chunks).toString("utf8");
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

/** Resolve the installed plugin root relative to this module's location. */
export const defaultPluginRoot = (moduleUrl, packaged) =>
  packaged ? new URL("../", moduleUrl) : new URL("../../plugins/epistemic-foundry/", moduleUrl);

/** Run as a process: read stdin, emit one JSON response, exit 0 or 1. */
export const runAsProcess = async (moduleUrl, packaged) => {
  try {
    const response = await main(process.argv, defaultPluginRoot(moduleUrl, packaged));
    process.stdout.write(`${JSON.stringify(response)}\n`);
  } catch (cause) {
    process.stderr.write(`${cause.code ?? "HOOK_RUNNER_FAILED"}\n`);
    process.exitCode = 1;
  }
};

// Only self-run when this file is the process entry point, so importing it
// from a test never consumes stdin.
if (process.argv[1] !== undefined && import.meta.url === new URL(`file://${process.argv[1].replaceAll("\\", "/")}`).href) {
  await runAsProcess(import.meta.url, false);
}
