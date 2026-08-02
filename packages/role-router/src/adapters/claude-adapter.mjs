import { compileRoleSpawnDescriptor } from "./adapter-contract.mjs";

/** Compile a Claude Code dispatch from a canonical RoleSpec and exact host bindings. */
export const compileClaudeSpawnDescriptor = (candidate) =>
  compileRoleSpawnDescriptor("claude_code", candidate);
