// What the Codex adapter is allowed to say, and where every word of it comes
// from.
//
// This module declares no vocabulary of its own beyond its refusals.  The hook
// event types, hosts and coverage classes belong to the sealed hook gateway;
// the role vocabulary belongs to `manifests/role_registry.yaml`; the payload
// shape belongs to `plugins/epistemic-foundry`.  What lives here is the finding
// set, the typed error, the paths the adapter reads, and the small readers that
// keep an unreadable input from passing as an absent one.
//
// The one string the adapter must name to bind itself — its host — is written
// in `adapters/codex/codex-binding.json`, not in code, and is admitted only if
// the gateway's own host list contains it.  `selectDeclared` is that admission.

import { createHash } from "node:crypto";
import { readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

/** Repository root, resolved from this file rather than the process cwd. */
export const REPOSITORY_ROOT = fileURLToPath(new URL("../../", import.meta.url));

export const ADAPTER_ROOT = "adapters/codex";
export const BINDING_DECLARATION_PATH = `${ADAPTER_ROOT}/codex-binding.json`;
export const ROLE_MAPPING_PATH = `${ADAPTER_ROOT}/role_mapping.yaml`;
export const ROLE_REGISTRY_PATH = "manifests/role_registry.yaml";
export const PAYLOAD_ROOT = "plugins/epistemic-foundry";
export const PLUGIN_MANIFEST_PATH = `${PAYLOAD_ROOT}/.codex-plugin/plugin.json`;

/**
 * The adapter's own binding vocabulary, taken from `adapters/codex/README.md`:
 * "A missing hook selects DEGRADED mode; it does not disable kernel gates."
 * DEGRADED is a report, not a refusal: the payload is bound, and the parts of
 * it that cannot run at this revision are named rather than implied.
 */
export const BINDING_STATUS = Object.freeze({ BOUND: "BOUND", DEGRADED: "DEGRADED" });

/** Every way this adapter refuses or reports, and why that finding exists. */
export const FINDING_CODES = Object.freeze({
  COVERAGE_UNDECLARED:
    "a declared coverage class matches no entry the hook gateway declares, so the adapter would publish a coverage value the kernel cannot read",
  DECLARATION_NONCANONICAL:
    "the adapter binding declaration is not in canonical form (exactly the declared fields, sorted, unique), so two equal bindings could hash differently",
  DESCRIPTOR_NAME_COLLISION:
    "two role descriptors resolved to the same Codex subagent name, so a delegation could not name exactly one bounded role and its scopes",
  DISPATCHER_PAYLOAD_MISSING:
    "the plugin dispatcher spawns a payload CLI that is not present on disk, so the Codex host would install a shell whose commands cannot run",
  DISPATCHER_UNREADABLE:
    "the plugin dispatcher does not name exactly one payload-relative target this adapter can resolve, so its binding cannot be verified at all",
  ENTRYPOINT_MISSING:
    "the plugin manifest or binding declaration names an entrypoint or asset that is absent from the payload, so the manifest describes files that do not ship",
  HOOK_COMMAND_TARGET_MISSING:
    "a registered hook command names a runner script that is not present in the payload, so that hook event would be unobserved at runtime",
  HOOK_COMMAND_UNPARSEABLE:
    "a hook registration carries a command this adapter cannot resolve to one payload-relative Node script and one verb, so its target cannot be verified",
  HOOK_EVENT_UNDECLARED:
    "a hook registration names an event type the hook gateway does not declare, and an adapter may not widen the canonical event vocabulary",
  HOOK_FILE_MISSING:
    "the binding declaration names a hook registration file that is absent from the payload, so the declared registration set is not the set that ships",
  HOOK_HOST_UNDECLARED:
    "the declared adapter host matches no entry the hook gateway declares, so the adapter would bind events to a host the kernel does not know",
  HOOK_REGISTRATION_UNREADABLE:
    "a hook registration file is not the object shape this adapter requires, and an unreadable registration must never pass as an absent one",
  HOOK_VERB_AMBIGUOUS:
    "two registrations pass the same hook verb for different event types, so a raw event carrying that verb could not resolve to one event type",
  HOOK_VERB_UNREGISTERED:
    "the raw host event names a hook verb that no registration in the payload passes, so no declared event type can be derived from it",
  MANIFEST_UNREADABLE:
    "the Codex plugin manifest could not be read as the JSON object this adapter requires, so nothing about the host binding can be verified",
  MAPPING_DRIFT:
    "the Codex role mapping disagrees with the role registry about a role's agent type, prompt source or output schema reference",
  PLUGIN_NAME_DRIFT:
    "the plugin manifest names a package other than the one the binding declaration binds, so the adapter would be validating a different payload",
  RAW_EVENT_HOST_FOREIGN:
    "the raw event declares a host other than the Codex host this adapter binds, and the adapter must not translate another host's events",
  RAW_EVENT_UNREADABLE:
    "the raw host event is not the exact minimal record this adapter accepts, so it cannot be translated without inventing the fields it lacks",
  REGISTRY_UNREADABLE:
    "a role declaration source could not be read as the bounded YAML subset this adapter accepts, and a partly read source is not evidence of any role",
  ROLE_UNDECLARED:
    "a Codex descriptor was requested for a role the role registry does not declare, and the adapter may not invent a role, its scopes or its schema",
  ROLE_UNMAPPED:
    "the role registry declares a role the Codex role mapping does not carry, so part of the canonical role vocabulary would have no host binding",
});

export class CodexAdapterError extends Error {
  constructor(code, message, context = {}) {
    super(message);
    this.name = "CodexAdapterError";
    this.code = code;
    this.context = context;
  }
}

export const fail = (code, message, context = {}) => {
  throw new CodexAdapterError(code, message, context);
};

export const sha256 = (bytes) => `sha256:${createHash("sha256").update(bytes).digest("hex")}`;

export const isPlainObject = (value) =>
  value !== null && typeof value === "object" && !Array.isArray(value);

export const pathExists = (root, relative) => {
  try {
    return statSync(join(root, relative)).isFile();
  } catch {
    return false;
  }
};

export const readBytes = (root, relative, code) => {
  try {
    return readFileSync(join(root, relative));
  } catch (error) {
    fail(code, `cannot read ${relative}: ${error.message}`, { path: relative });
    return Buffer.alloc(0);
  }
};

export const readText = (root, relative, code) => readBytes(root, relative, code).toString("utf8");

export const readJson = (root, relative, code) => {
  const text = readText(root, relative, code);
  try {
    return JSON.parse(text);
  } catch (error) {
    fail(code, `${relative} is not JSON: ${error.message}`, { path: relative });
    return undefined;
  }
};

/** Require an object that declares exactly `fields`, no more and no fewer. */
export const requireFields = (value, fields, label, code) => {
  if (!isPlainObject(value)) fail(code, `${label} must be an object`, { label });
  const actual = Object.keys(value).sort();
  const expected = [...fields].sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) {
    fail(code, `${label} must declare exactly ${expected.join(", ")}`, { actual, expected, label });
  }
  return value;
};

export const requireCanonicalStrings = (value, label, code) => {
  if (!Array.isArray(value) || value.some((entry) => typeof entry !== "string")) {
    fail(code, `${label} must be an array of strings`, { label });
  }
  const sorted = [...value].sort();
  if (value.some((entry, index) => entry !== sorted[index])) {
    fail(code, `${label} must be sorted`, { label, value });
  }
  if (new Set(value).size !== value.length) {
    fail(code, `${label} must not repeat an entry`, { label, value });
  }
  return Object.freeze([...value]);
};

/**
 * Admit one declared value by finding it in a list the kernel declares.
 *
 * The adapter holds the *name of the declaration*, never a copy of the
 * canonical vocabulary: the value is selected from `declared` by equality, and
 * a predicate that matches nothing is a refusal rather than a silent default.
 */
export const selectDeclared = (declared, candidate, label, code) => {
  const matches = declared.filter((entry) => entry === candidate);
  if (matches.length !== 1) {
    fail(code, `${label} "${String(candidate)}" is not one declared value`, {
      candidate,
      declared: [...declared],
      label,
    });
  }
  return matches[0];
};

export const deepFreeze = (value) => {
  if (value === null || typeof value !== "object") return value;
  for (const key of Reflect.ownKeys(value)) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (descriptor !== undefined && Object.hasOwn(descriptor, "value")) deepFreeze(descriptor.value);
  }
  return Object.freeze(value);
};
