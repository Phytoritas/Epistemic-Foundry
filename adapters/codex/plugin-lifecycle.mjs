import { fileURLToPath } from "node:url";
import { FAILURE, STATUS } from "./plugin-lifecycle/core.mjs";
import { buildLifecyclePort } from "./plugin-lifecycle/runtime.mjs";

export const PLUGIN_LIFECYCLE_STATUS = STATUS;
export const PLUGIN_LIFECYCLE_FAILURE = FAILURE;

/**
 * Create the synchronous private X01 Codex lifecycle port.
 *
 * Codex cache and configuration are never written directly. Mutating lifecycle
 * methods fail closed unless their exact-selector, quiescence, trust, migration,
 * and verification prerequisites are available.
 */
export function createCodexPluginLifecyclePort(options) {
  const contractPath = fileURLToPath(new URL("./lifecycle-state.contract.json", import.meta.url));
  return buildLifecyclePort(options, contractPath);
}
