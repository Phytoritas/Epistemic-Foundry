// T01 transport framing: STDIO and Streamable HTTP POST /mcp are stateless
// shells over one injected handler port; protocol failures are typed.

import assert from "node:assert/strict";
import test from "node:test";

import {
  HTTP_MCP_PATH,
  JSONRPC_INVALID_PARAMS,
  JSONRPC_INVALID_REQUEST,
  JSONRPC_METHOD_NOT_FOUND,
  JSONRPC_PARSE_ERROR,
  PROTOCOL_VERSION,
  handleHttpPost,
  handleJsonrpc,
  serveStdio,
  toolDescriptors,
} from "../../packages/plugin-host/src/mcp/read/mcp-server.mjs";
import {
  ReceiptContractError,
  extractReceipts,
} from "../../packages/plugin-host/src/mcp/planning/receipts.mjs";

function fixtureEnvelope(tool, overrides = {}) {
  return {
    protocol_version: PROTOCOL_VERSION,
    tool,
    request_id: "R1",
    workspace_id: "WS-1",
    read_model_state: "READY",
    data: { ok: true },
    data_schema_refs: [],
    receipts: [],
    degradation_reason: null,
    generated_at: "2026-07-31T00:00:00Z",
    ...overrides,
  };
}

class FixtureHandlerPort {
  constructor() {
    this.calls = [];
  }

  async call(toolName, argumentsObject, requestId) {
    this.calls.push([toolName, argumentsObject, requestId]);
    return { envelope: fixtureEnvelope(toolName), isError: false };
  }
}

test("t01_transport_framing: initialize and tools/list are stateless constants", async () => {
  const port = new FixtureHandlerPort();
  const first = await handleJsonrpc(
    { jsonrpc: "2.0", id: 1, method: "initialize" },
    port,
  );
  const second = await handleJsonrpc(
    { jsonrpc: "2.0", id: 1, method: "initialize" },
    port,
  );
  const listed = await handleJsonrpc(
    { jsonrpc: "2.0", id: 2, method: "tools/list" },
    port,
  );

  assert.deepEqual(first, second);
  assert.equal(first.result.protocolVersion, PROTOCOL_VERSION);
  assert.deepEqual(listed.result.tools, toolDescriptors());
  assert.equal(port.calls.length, 0);
});

test("t01_transport_framing: tools/call wraps the shared envelope", async () => {
  const port = new FixtureHandlerPort();
  const response = await handleJsonrpc(
    {
      jsonrpc: "2.0",
      id: "R1",
      method: "tools/call",
      params: { name: "foundry.status", arguments: { workspace_id: "WS-1" } },
    },
    port,
  );

  assert.deepEqual(port.calls, [["foundry.status", { workspace_id: "WS-1" }, "R1"]]);
  assert.equal(response.result.isError, false);
  assert.deepEqual(response.result.structuredContent, fixtureEnvelope("foundry.status"));
  assert.deepEqual(
    JSON.parse(response.result.content[0].text),
    fixtureEnvelope("foundry.status"),
  );
});

test("t01_transport_framing: protocol failures are typed JSON-RPC errors", async () => {
  const port = new FixtureHandlerPort();

  const notObject = await handleJsonrpc(["nope"], port);
  const badVersion = await handleJsonrpc({ jsonrpc: "1.0", id: 1, method: "x" }, port);
  const unknownMethod = await handleJsonrpc(
    { jsonrpc: "2.0", id: 2, method: "resources/list" },
    port,
  );
  const missingName = await handleJsonrpc(
    { jsonrpc: "2.0", id: 3, method: "tools/call", params: {} },
    port,
  );
  const notification = await handleJsonrpc(
    { jsonrpc: "2.0", method: "notifications/initialized" },
    port,
  );

  assert.equal(notObject.error.code, JSONRPC_INVALID_REQUEST);
  assert.equal(badVersion.error.code, JSONRPC_INVALID_REQUEST);
  assert.equal(unknownMethod.error.code, JSONRPC_METHOD_NOT_FOUND);
  assert.equal(missingName.error.code, JSONRPC_INVALID_PARAMS);
  assert.equal(notification, null);
  assert.equal(port.calls.length, 0);
});

test("t01_transport_framing: stdio and http produce identical responses", async () => {
  const request = {
    jsonrpc: "2.0",
    id: "R-parity",
    method: "tools/call",
    params: { name: "foundry.health", arguments: { workspace_id: "WS-1" } },
  };

  const stdioPort = new FixtureHandlerPort();
  const written = [];
  const handled = await serveStdio(
    [JSON.stringify(request)],
    (line) => written.push(line),
    stdioPort,
  );
  const stdioResponse = JSON.parse(written[0]);

  const httpPort = new FixtureHandlerPort();
  const httpResult = await handleHttpPost({
    path: HTTP_MCP_PATH,
    body: JSON.stringify(request),
    headers: { "content-type": "application/json" },
    handlerPort: httpPort,
  });

  assert.equal(handled, 1);
  assert.equal(httpResult.status, 200);
  assert.deepEqual(stdioResponse, JSON.parse(httpResult.body));
  assert.deepEqual(stdioPort.calls, httpPort.calls);
});

test("t01_transport_framing: http transport failures are typed", async () => {
  const port = new FixtureHandlerPort();

  const wrongPath = await handleHttpPost({
    path: "/rpc",
    body: "{}",
    headers: { "content-type": "application/json" },
    handlerPort: port,
  });
  const wrongType = await handleHttpPost({
    path: HTTP_MCP_PATH,
    body: "{}",
    headers: { "content-type": "text/plain" },
    handlerPort: port,
  });
  const badJson = await handleHttpPost({
    path: HTTP_MCP_PATH,
    body: "{nope",
    headers: { "content-type": "application/json" },
    handlerPort: port,
  });
  const notification = await handleHttpPost({
    path: HTTP_MCP_PATH,
    body: JSON.stringify({ jsonrpc: "2.0", method: "notifications/initialized" }),
    headers: { "content-type": "application/json" },
    handlerPort: port,
  });

  assert.equal(wrongPath.status, 404);
  assert.equal(wrongType.status, 415);
  assert.equal(badJson.status, 400);
  assert.equal(JSON.parse(badJson.body).error.code, JSONRPC_PARSE_ERROR);
  assert.equal(notification.status, 202);
  assert.equal(notification.body, "");
  assert.equal(port.calls.length, 0);
});

test("t01_transport_framing: malformed stdio lines answer parse errors", async () => {
  const written = [];
  const handled = await serveStdio(
    ["{nope", "", JSON.stringify({ jsonrpc: "2.0", id: 9, method: "initialize" })],
    (line) => written.push(line),
    new FixtureHandlerPort(),
  );

  assert.equal(handled, 2);
  assert.equal(JSON.parse(written[0]).error.code, JSONRPC_PARSE_ERROR);
  assert.equal(JSON.parse(written[1]).result.protocolVersion, PROTOCOL_VERSION);
});

test("t01_transport_framing: receipt projection enforces side-effect classes", () => {
  const planningEnvelope = fixtureEnvelope("foundry.search.plan", {
    receipts: [
      {
        artifact_id: "PLAN-1",
        receipt_id: "AR-1",
        sha256: `sha256:${"a".repeat(64)}`,
      },
    ],
  });

  const receipts = extractReceipts(planningEnvelope, "DURABLE_PLAN_ARTIFACT");
  assert.equal(receipts.length, 1);
  assert.equal(receipts[0].artifact_id, "PLAN-1");

  assert.throws(
    () => extractReceipts(fixtureEnvelope("foundry.search.plan"), "DURABLE_PLAN_ARTIFACT"),
    ReceiptContractError,
  );
  assert.throws(
    () => extractReceipts(planningEnvelope, "PURE_READ"),
    ReceiptContractError,
  );
  assert.throws(
    () =>
      extractReceipts(
        { ...planningEnvelope, receipts: [{ artifact_id: "x", receipt_id: "y", sha256: "nope" }] },
        "DURABLE_PLAN_ARTIFACT",
      ),
    ReceiptContractError,
  );
  assert.throws(
    () =>
      extractReceipts(
        {
          protocol_version: PROTOCOL_VERSION,
          tool: "foundry.search.plan",
          request_id: "R1",
          error_code: "INTERNAL",
          message: "x",
          retryable: true,
          details: null,
        },
        "DURABLE_PLAN_ARTIFACT",
      ),
    ReceiptContractError,
  );
});
