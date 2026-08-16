// T02 composed MCP write surface: catalog composition and mutating framing.
//
// Authorized by HD-EF4-T02-SCOPE-20260801-002.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import test from "node:test";

import {
  CATALOG_SET_ID,
  GLOBAL_EXACT_COUNT,
  catalogSetMetadata,
  isMutatingTool,
  mergedToolDescriptors,
  mutatingToolDescriptors,
} from "../../packages/plugin-host/src/mcp/write/catalog-set.mjs";
import {
  composedHandlerPort,
  composedToolCount,
  handleHttpPost,
  handleJsonrpc,
  isSuccessfulMutation,
  serveStdio,
} from "../../packages/plugin-host/src/mcp/write/adapter.mjs";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const SEALED_PROJECTION = JSON.parse(
  readFileSync(join(ROOT, "packages/plugin-host/src/mcp/generated/tool-descriptors.json"), "utf8"),
);

function successPort(mutation) {
  return {
    calls: [],
    async call(toolName, args, requestId) {
      this.calls.push({ toolName, args, requestId });
      return {
        envelope: { tool: toolName, data: mutation === null ? null : { mutation } },
        isError: false,
      };
    },
  };
}

test("the composed surface exposes exactly 13 + 11 unique tools", () => {
  const merged = mergedToolDescriptors();
  const names = merged.map((tool) => tool.name);

  assert.equal(merged.length, 24);
  assert.equal(merged.length, GLOBAL_EXACT_COUNT);
  assert.equal(merged.length, composedToolCount());
  assert.equal(new Set(names).size, 24);
});

test("merge order places the sealed projection first and unchanged", () => {
  const merged = mergedToolDescriptors();
  const sealedNames = SEALED_PROJECTION.tools.map((tool) => tool.name);

  assert.deepEqual(
    merged.slice(0, sealedNames.length).map((tool) => tool.name),
    sealedNames,
  );
  assert.deepEqual(merged.slice(0, sealedNames.length), SEALED_PROJECTION.tools);
});

test("the mutating half is exactly the eleven T02 tools", () => {
  const mutating = mutatingToolDescriptors();

  assert.equal(mutating.length, 11);
  for (const tool of mutating) {
    assert.equal(tool.annotations.sideEffectClass, "MUTATING_EFFECT");
    assert.equal(tool.annotations.readOnlyHint, false);
    assert.equal(isMutatingTool(tool.name), true);
  }
  for (const tool of SEALED_PROJECTION.tools) {
    assert.equal(isMutatingTool(tool.name), false);
  }
});

test("catalog set metadata carries counts and order but no tool name", () => {
  const metadata = catalogSetMetadata();
  const text = JSON.stringify(metadata);

  assert.equal(metadata.set_id, CATALOG_SET_ID);
  assert.deepEqual(
    metadata.merge_order,
    metadata.catalogs.map((entry) => entry.catalog_id),
  );
  assert.equal(
    metadata.catalogs.reduce((total, entry) => total + entry.exact_count, 0),
    GLOBAL_EXACT_COUNT,
  );
  for (const tool of mergedToolDescriptors()) {
    assert.equal(text.includes(tool.name), false, tool.name);
  }
});

test("tools/list returns the composed table", async () => {
  const response = await handleJsonrpc(
    { jsonrpc: "2.0", id: 1, method: "tools/list" },
    successPort({ effect_status: "SUCCEEDED", dry_run: false }),
  );

  assert.equal(response.result.tools.length, 24);
  assert.deepEqual(response.result.tools, mergedToolDescriptors());
});

test("initialize describes the composed surface", async () => {
  const response = await handleJsonrpc(
    { jsonrpc: "2.0", id: 2, method: "initialize" },
    successPort(null),
  );

  assert.match(response.result.instructions, /MUTATING_EFFECT/);
  assert.match(response.result.instructions, /reconciliation_required/);
  assert.equal(response.result.capabilities.tools.listChanged, false);
});

test("a committed mutation is framed as a successful call", async () => {
  const tool = mutatingToolDescriptors()[0].name;
  const response = await handleJsonrpc(
    { jsonrpc: "2.0", id: 3, method: "tools/call", params: { name: tool, arguments: {} } },
    successPort({ effect_status: "SUCCEEDED", dry_run: false }),
  );

  assert.equal(response.result.isError, false);
});

test("an intentional dry run is framed as a successful call", async () => {
  const tool = mutatingToolDescriptors()[0].name;
  const response = await handleJsonrpc(
    { jsonrpc: "2.0", id: 4, method: "tools/call", params: { name: tool, arguments: {} } },
    successPort({ effect_status: "NOT_EXECUTED", dry_run: true }),
  );

  assert.equal(response.result.isError, false);
});

test("an unresolved or failed effect is never framed as success", async () => {
  const tool = mutatingToolDescriptors()[0].name;

  for (const status of ["UNKNOWN", "FAILED", "ROLLED_BACK"]) {
    const response = await handleJsonrpc(
      { jsonrpc: "2.0", id: 5, method: "tools/call", params: { name: tool, arguments: {} } },
      successPort({ effect_status: status, dry_run: false }),
    );

    assert.equal(response.result.isError, true, status);
    assert.equal(response.result.structuredContent.data.mutation.effect_status, status);
  }
});

test("a non-dry-run NOT_EXECUTED is never framed as success", () => {
  assert.equal(
    isSuccessfulMutation({ data: { mutation: { effect_status: "NOT_EXECUTED", dry_run: false } } }),
    false,
  );
  assert.equal(isSuccessfulMutation({ data: null }), false);
  assert.equal(isSuccessfulMutation({}), false);
});

test("a sealed read tool keeps the port's own isError verdict", async () => {
  const tool = SEALED_PROJECTION.tools[0].name;
  const port = successPort({ effect_status: "UNKNOWN", dry_run: false });

  const response = await handleJsonrpc(
    { jsonrpc: "2.0", id: 6, method: "tools/call", params: { name: tool, arguments: {} } },
    port,
  );

  assert.equal(response.result.isError, false);
});

test("an error envelope stays an error through the wrapper", async () => {
  const port = {
    async call() {
      return { envelope: { error_code: "UNAUTHORIZED" }, isError: true };
    },
  };
  const wrapped = composedHandlerPort(port);

  const outcome = await wrapped.call(mutatingToolDescriptors()[0].name, {}, "req");

  assert.equal(outcome.isError, true);
});

test("HTTP POST /mcp round-trips the composed table", async () => {
  const result = await handleHttpPost({
    path: "/mcp",
    body: JSON.stringify({ jsonrpc: "2.0", id: 7, method: "tools/list" }),
    headers: { "content-type": "application/json" },
    handlerPort: successPort(null),
  });

  assert.equal(result.status, 200);
  assert.equal(JSON.parse(result.body).result.tools.length, 24);
});

test("HTTP transport keeps the sealed framing rules", async () => {
  const port = successPort(null);

  assert.equal((await handleHttpPost({ path: "/other", body: "{}", headers: {}, handlerPort: port })).status, 404);
  assert.equal(
    (await handleHttpPost({ path: "/mcp", body: "{}", headers: { "content-type": "text/plain" }, handlerPort: port })).status,
    415,
  );
  assert.equal(
    (await handleHttpPost({ path: "/mcp", body: "{", headers: { "content-type": "application/json" }, handlerPort: port })).status,
    400,
  );
  const notification = await handleHttpPost({
    path: "/mcp",
    body: JSON.stringify({ jsonrpc: "2.0", method: "tools/list" }),
    headers: { "content-type": "application/json" },
    handlerPort: port,
  });
  assert.equal(notification.status, 202);
});

test("STDIO serves the composed table line by line", async () => {
  const written = [];
  const lines = [
    JSON.stringify({ jsonrpc: "2.0", id: 8, method: "tools/list" }),
    "",
    JSON.stringify({ jsonrpc: "2.0", method: "tools/list" }),
  ];

  const handled = await serveStdio(lines, (line) => written.push(line), successPort(null));

  assert.equal(handled, 1);
  assert.equal(JSON.parse(written[0]).result.tools.length, 24);
});

test("an unknown method is rejected by the sealed framing", async () => {
  const response = await handleJsonrpc(
    { jsonrpc: "2.0", id: 9, method: "tools/teleport" },
    successPort(null),
  );

  assert.equal(response.error.code, -32601);
  assert.equal(response.result, undefined);
});
