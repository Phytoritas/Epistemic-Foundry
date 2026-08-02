// Test scaffolding: a staged repository root the adversarial suite may damage.
//
// Every hostile case needs an input that is wrong in exactly one way, so the
// declaring inputs are copied into a temporary root and broken there.  The real
// repository — and in particular the sealed plugin payload — is never written to
// by a test.

import { cpSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";

import {
  BINDING_DECLARATION_PATH,
  PAYLOAD_ROOT,
  PLUGIN_MANIFEST_PATH,
  REPOSITORY_ROOT,
  ROLE_MAPPING_PATH,
  ROLE_REGISTRY_PATH,
} from "./codex-declarations.mjs";

/** Exactly the inputs `loadCodexBinding` reads by path. */
export const STAGED_PATHS = Object.freeze([
  PLUGIN_MANIFEST_PATH,
  `${PAYLOAD_ROOT}/assets`,
  `${PAYLOAD_ROOT}/bin`,
  `${PAYLOAD_ROOT}/hooks`,
  BINDING_DECLARATION_PATH,
  ROLE_MAPPING_PATH,
  ROLE_REGISTRY_PATH,
]);

export const stageRoot = (t) => {
  const root = mkdtempSync(join(tmpdir(), "ef-x01-"));
  t.after(() => rmSync(root, { force: true, recursive: true }));
  for (const relative of STAGED_PATHS) {
    const target = join(root, relative);
    mkdirSync(dirname(target), { recursive: true });
    cpSync(join(REPOSITORY_ROOT, relative), target, { recursive: true });
  }
  return root;
};

export const readStaged = (root, relative) => readFileSync(join(root, relative), "utf8");

export const writeStaged = (root, relative, text) =>
  writeFileSync(join(root, relative), text, "utf8");

export const removeStaged = (root, relative) =>
  rmSync(join(root, relative), { force: true, recursive: true });

/** Add a file the payload does not ship, creating its directories. */
export const addStaged = (root, relative, text) => {
  const target = join(root, relative);
  mkdirSync(dirname(target), { recursive: true });
  writeFileSync(target, text, "utf8");
};

export const readStagedJson = (root, relative) => JSON.parse(readStaged(root, relative));

export const writeStagedJson = (root, relative, value) =>
  writeStaged(root, relative, `${JSON.stringify(value, null, 2)}\n`);

/** Stage a root and break exactly one JSON input. */
const stageJson = (t, relative, mutate) => {
  const root = stageRoot(t);
  const value = readStagedJson(root, relative);
  mutate(value, root);
  writeStagedJson(root, relative, value);
  return root;
};

export const stageDeclaration = (t, mutate) => stageJson(t, BINDING_DECLARATION_PATH, mutate);

export const stageManifest = (t, mutate) => stageJson(t, PLUGIN_MANIFEST_PATH, mutate);

export const stageHookFile = (t, relative, mutate) =>
  stageJson(t, `${PAYLOAD_ROOT}/${relative}`, mutate);

/** Stage a root and break exactly one text input, by literal substitution. */
export const stageText = (t, relative, mutate) => {
  const root = stageRoot(t);
  writeStaged(root, relative, mutate(readStaged(root, relative)));
  return root;
};

/** Run `run` and return the refusal it raises, or fail loudly if it does not. */
export const refusal = (run) => {
  try {
    run();
  } catch (error) {
    return error;
  }
  throw new Error("expected a refusal, but the call succeeded");
};

/** Await `run` and return the refusal it rejects with, or fail loudly. */
export const asyncRefusal = async (run) => {
  try {
    await run();
  } catch (error) {
    return error;
  }
  throw new Error("expected a refusal, but the call resolved");
};

/** A raw Codex-host event whose fields are fixed, so every test is deterministic. */
export const RAW_EVENT_TEMPLATE = Object.freeze({
  event_id: "EFX01-RAW-0001-FIXTURE",
  hook: "pre-tool-use",
  payload: Object.freeze({ command: "efoundry status", tool_input: Object.freeze({}) }),
  received_at: "2026-08-01T07:00:00Z",
  session_id: "SESSION-X01-0001",
  tool_name: "Bash",
});

/** A decision the caller supplies; the adapter never produces one of its own. */
export const ADVISORY_DECISION = Object.freeze({
  action_intent_id: null,
  decision: "ADVISORY",
  effect_receipt_id: null,
  reasons: Object.freeze(["X01_FIXTURE_DECISION"]),
});

export const RUNTIME_TEMPLATE = Object.freeze({
  decide: () => ({ ...ADVISORY_DECISION, reasons: [...ADVISORY_DECISION.reasons] }),
  timeout_ms: 5000,
});

/** The raw event for a binding, with the host the binding actually selected. */
export const rawEventFor = (binding, overrides = {}) => ({
  ...RAW_EVENT_TEMPLATE,
  host: binding.adapterHost,
  payload: { ...RAW_EVENT_TEMPLATE.payload, tool_input: {} },
  ...overrides,
});
