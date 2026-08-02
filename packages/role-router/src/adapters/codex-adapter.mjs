import { compileRoleSpawnDescriptor } from "./adapter-contract.mjs";

/** Compile a Codex CLI dispatch from a canonical RoleSpec and exact host bindings. */
export const compileCodexSpawnDescriptor = (candidate, host = "codex_cli") =>
  compileRoleSpawnDescriptor(host, candidate);
