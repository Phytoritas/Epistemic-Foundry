// worktree_isolation_test / negative and adversarial tests — one broken input at
// a time.
//
// Each case stages the declaring inputs into a temporary root and damages
// exactly one of them, so the refusal that follows can only be caused by that
// damage.  The real registry and the shipped agent files are never written to.
// Removing a live agent proves that DEGRADED is derived rather than constant;
// changing a shadow adapter copy proves the binding follows the host surface.

import assert from "node:assert/strict";
import test from "node:test";

import { HOOK_HOSTS } from "../../packages/plugin-host/src/hooks/gateway/hook-gateway.mjs";
import {
  ADAPTER_ROOT,
  BINDING_DECLARATION_PATH,
  BINDING_STATUS,
  ClaudeAdapterError,
  claudeBindingReceipt,
  loadClaudeBinding,
  ROLE_MAPPING_PATH,
  ROLE_REGISTRY_PATH,
} from "./index.mjs";
import {
  readStaged,
  refusal,
  removeStaged,
  stageDeclaration,
  stageMapping,
  stageRegistry,
  stageRoot,
  stageText,
  writeStaged,
} from "./claude-fixtures.mjs";

const binding = loadClaudeBinding();
const loadFrom = (root) => refusal(() => loadClaudeBinding({ root }));
const agentPath = (name) => `${binding.agentRoot}/${name}.md`;

test("x02_adversarial: a host the gateway does not declare is refused", (t) => {
  const root = stageDeclaration(t, (declaration) => {
    declaration.declared_host = `${declaration.declared_host}-agents`;
  });

  const error = loadFrom(root);
  assert.equal(error.code, "HOST_UNDECLARED");
  assert.deepEqual(error.context.declared, [...HOOK_HOSTS]);
});

test("x02_adversarial: a base tool grant that repeats a tool is refused", (t) => {
  const root = stageDeclaration(t, (declaration) => {
    declaration.base_tools = [...declaration.base_tools, declaration.base_tools[0]];
  });

  assert.equal(loadFrom(root).code, "DECLARATION_NONCANONICAL");
});

test("x02_adversarial: a write tool already granted as a base tool is refused", (t) => {
  const root = stageDeclaration(t, (declaration) => {
    declaration.write_tool = declaration.base_tools[0];
  });

  assert.equal(loadFrom(root).code, "DECLARATION_NONCANONICAL");
});

test("x02_adversarial: a declaration the adapter cannot read refuses rather than defaults", (t) => {
  const root = stageRoot(t);
  removeStaged(root, BINDING_DECLARATION_PATH);

  assert.equal(loadFrom(root).code, "DECLARATION_NONCANONICAL");
});

test("x02_adversarial: the declared live agent root cannot escape the repository", (t) => {
  const root = stageDeclaration(t, (declaration) => {
    declaration.agent_root = "../outside-agents";
  });

  assert.equal(loadFrom(root).code, "DECLARATION_NONCANONICAL");
});

test("x02_adversarial: a mapping surface the adapter does not declare is refused", (t) => {
  const root = stageMapping(t, (text) =>
    text.replace(
      "  claim_extractor:\n    surface: custom_agent",
      "  claim_extractor:\n    surface: mcp_tool",
    ),
  );

  const error = loadFrom(root);
  assert.equal(error.code, "SURFACE_UNDECLARED");
  assert.equal(error.context.candidate, "mcp_tool");
});

test("x02_adversarial: a mapping isolation mode the adapter does not declare is refused", (t) => {
  const root = stageMapping(t, (text) =>
    text.replace(
      "    result_schema: schemas/claim-card.schema.json\n    isolation: worktree",
      "    result_schema: schemas/claim-card.schema.json\n    isolation: detached",
    ),
  );

  const error = loadFrom(root);
  assert.equal(error.code, "ISOLATION_UNDECLARED");
  assert.equal(error.context.candidate, "detached");
});

test("x02_adversarial: an isolation that disagrees with the write scope is refused", (t) => {
  const root = stageMapping(t, (text) =>
    text.replace(
      "    result_schema: schemas/claim-card.schema.json\n    isolation: worktree",
      "    result_schema: schemas/claim-card.schema.json\n    isolation: shared",
    ),
  );

  const error = loadFrom(root);
  assert.equal(error.code, "ISOLATION_DRIFT");
  assert.equal(error.context.role_id, "claim_extractor");
});

test("x02_adversarial: a mapping that disagrees with the registry schema is refused", (t) => {
  const root = stageMapping(t, (text) =>
    text.replace("    result_schema: schemas/claim-card.schema.json", "    result_schema: schemas/result-envelope.schema.json"),
  );

  const error = loadFrom(root);
  assert.equal(error.code, "MAPPING_DRIFT");
  assert.equal(error.context.role_id, "claim_extractor");
});

test("x02_adversarial: a mapping row for an undeclared role is refused", (t) => {
  const root = stageMapping(t, (text) =>
    text.replace(
      "constraints:",
      [
        "  shadow_promoter:",
        "    surface: custom_agent",
        "    result_schema: schemas/result-envelope.schema.json",
        "    isolation: worktree",
        "constraints:",
      ].join("\n"),
    ),
  );

  const error = loadFrom(root);
  assert.equal(error.code, "ROLE_UNDECLARED");
  assert.equal(error.context.role_id, "shadow_promoter");
});

test("x02_adversarial: a declared role the mapping does not carry is refused", (t) => {
  const root = stageMapping(t, (text) => text.replace(/ {2}judge:\n(?: {4}.+\n)+/u, ""));

  const error = loadFrom(root);
  assert.equal(error.code, "ROLE_UNMAPPED");
  assert.equal(error.context.role_id, "judge");
});

test("x02_adversarial: an unreadable mapping line is refused, not skipped", (t) => {
  const root = stageMapping(t, (text) => text.replace("version: 4.0.0\n", "version: 4.0.0\nbogus_key: value\n"));

  const error = loadFrom(root);
  assert.equal(error.code, "MAPPING_UNREADABLE");
  assert.ok(error instanceof ClaudeAdapterError);
});

test("x02_adversarial: two roles resolving to one agent name are refused", (t) => {
  const root = stageRegistry(t, (text) => {
    const block = /- role_id: evidence_scout\n[\s\S]*?(?=- role_id: claim_extractor)/u.exec(text)[0];
    return text.replace(block, `${block}${block}`);
  });

  const error = loadFrom(root);
  assert.equal(error.code, "AGENT_NAME_COLLISION");
  assert.deepEqual(error.context.role_ids, ["evidence_scout", "evidence_scout"]);
});

test("x02_adversarial: an unreadable registry line is refused, not skipped", (t) => {
  const root = stageRegistry(t, (text) => text.replace("roles:\n", "extra_block:\nroles:\n"));

  const error = loadFrom(root);
  assert.equal(error.code, "REGISTRY_UNREADABLE");
});

test("x02_adversarial: a registry role missing a RoleSpec field is refused", (t) => {
  const root = stageRegistry(t, (text) => text.replace("  claude_agent_name: ef-judge\n", ""));

  assert.equal(loadFrom(root).code, "REGISTRY_UNREADABLE");
});

test("x02_adversarial: an agent file whose name maps to no role is refused", (t) => {
  const root = stageRoot(t);
  writeStaged(root, agentPath("ef-shadow-promoter"), "---\nname: ef-shadow-promoter\n---\n");

  const error = loadFrom(root);
  assert.equal(error.code, "AGENT_FILE_UNDECLARED");
  assert.equal(error.context.file, "ef-shadow-promoter.md");
});

test("x02_adversarial: an agent file whose name contradicts its RoleSpec is refused", (t) => {
  const root = stageText(t, agentPath("ef-judge"), (text) => text.replace("name: ef-judge", "name: ef-judgement"));

  const error = loadFrom(root);
  assert.equal(error.code, "AGENT_NAME_DRIFT");
  assert.equal(error.context.role_id, "judge");
});

test("x02_adversarial: a receipt revalidates a live agent changed after load", (t) => {
  const root = stageRoot(t);
  const loaded = loadClaudeBinding({ root });
  writeStaged(
    root,
    agentPath("ef-judge"),
    readStaged(root, agentPath("ef-judge")).replace("name: ef-judge", "name: ef-judgement"),
  );

  const error = refusal(() => claudeBindingReceipt(loaded));
  assert.equal(error.code, "AGENT_NAME_DRIFT");
});

test("x02_adversarial: an agent file whose description contradicts its RoleSpec is refused", (t) => {
  const root = stageText(t, agentPath("ef-judge"), (text) =>
    text.replace(/description: ".*"/u, 'description: "Do whatever seems best."'),
  );

  assert.equal(loadFrom(root).code, "AGENT_DESCRIPTION_DRIFT");
});

test("x02_adversarial: an agent file that grants tools its write scope does not earn is refused", (t) => {
  const root = stageText(t, agentPath("ef-judge"), (text) =>
    text.replace("tools: Read, Grep, Glob, Bash", "tools: Read, Grep, Glob"),
  );

  const error = loadFrom(root);
  assert.equal(error.code, "AGENT_TOOLS_DRIFT");
  assert.deepEqual(error.context.declared, ["Read", "Grep", "Glob"]);
});

test("x02_adversarial: an agent file whose model contradicts the declaration is refused", (t) => {
  const root = stageText(t, agentPath("ef-judge"), (text) => text.replace("model: inherit", "model: sonnet"));

  const error = loadFrom(root);
  assert.equal(error.code, "AGENT_MODEL_DRIFT");
  assert.equal(error.context.declared, "sonnet");
});

test("x02_adversarial: undeclared host-only frontmatter is refused", (t) => {
  const root = stageText(t, agentPath("ef-evolution-governor"), (text) =>
    text.replace("permissionMode: plan", "permissionMode: acceptEdits"),
  );

  assert.equal(loadFrom(root).code, "AGENT_FRONTMATTER_UNREADABLE");
});

test("x02_adversarial: an agent file with an incomplete frontmatter block is refused", (t) => {
  const root = stageText(t, agentPath("ef-judge"), (text) => text.replace("model: inherit\n", ""));

  assert.equal(loadFrom(root).code, "AGENT_FRONTMATTER_UNREADABLE");
});

test("x02_adversarial: removing a live agent makes the binding DEGRADED", (t) => {
  const root = stageRoot(t);
  removeStaged(root, agentPath("ef-evolution-governor"));

  const built = loadClaudeBinding({ root });

  assert.equal(built.status, BINDING_STATUS.DEGRADED);
  assert.deepEqual(built.missingRoleIds, ["evolution_governor"]);
  assert.equal(built.findings[0].path, `${binding.agentRoot}/ef-evolution-governor.md`);
  assert.equal(built.presentRoleIds.length, built.agentTable.length - 1);
});

test("x02_adversarial: changing a shadow agent does not change the live binding", (t) => {
  const root = stageText(t, `${ADAPTER_ROOT}/ef-judge.md`, (text) =>
    text.replace("name: ef-judge", "name: ef-shadow-judge"),
  );

  const built = loadClaudeBinding({ root });
  assert.equal(built.status, BINDING_STATUS.BOUND);
  assert.deepEqual(built.findings, []);
});
