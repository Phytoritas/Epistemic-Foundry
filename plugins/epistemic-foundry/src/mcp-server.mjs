#!/usr/bin/env node
// Installed stdio composition for the canonical T01 read/planning surface.

import { dirname } from "node:path";
import { fileURLToPath } from "node:url";

import { serveStdio } from "./plugin-host/mcp/read/mcp-server.mjs";
import { createLocalStdioHandlerPort } from "./plugin-host/mcp/read/local-stdio-handler.mjs";
import { buildRepositoryWorkspaceMapSnapshot } from "./workspace-map/snapshot/index.mjs";

import { openPluginForgeReadRuntime } from "./installed-forge-runtime.mjs";
import {
  createHealthProjection,
  createStatusProjection,
} from "./runtime-observation.mjs";
import { createStoreReadModel } from "./store-read-model.mjs";

const MAX_JSON_FRAME_BYTES = 1024 * 1024;
const OVERSIZED_FRAME_SENTINEL = "\u0000";
const PLUGIN_ROOT = dirname(dirname(fileURLToPath(import.meta.url)));

let forgeReadRuntime = null;
let storeReadModel = null;
let sessionReadState = "CONFIGURED_UNVERIFIED";
let closeAttempted = false;

const closeForgeReadRuntimeOnce = () => {
  if (closeAttempted) return;
  closeAttempted = true;
  const runtime = forgeReadRuntime;
  forgeReadRuntime = null;
  storeReadModel = null;
  if (runtime === null) return;
  try {
    runtime.close();
  } catch {
    process.stderr.write("installed Forge read runtime close failed\n");
    process.exitCode = 1;
  }
};

const sessionReadPort = Object.freeze({
  fetch(operation, workspaceId, arguments_) {
    if (storeReadModel === null) {
      let openedRuntime = null;
      try {
        openedRuntime = openPluginForgeReadRuntime();
        const openedReadModel = createStoreReadModel({
          workspaceId: openedRuntime.workspaceId,
          artifactStore: openedRuntime.runtime.artifactStore,
          sessionPort: openedRuntime.runtime.sessionPort,
        });
        forgeReadRuntime = openedRuntime;
        storeReadModel = openedReadModel;
        sessionReadState = "READY";
      } catch (error) {
        sessionReadState = "UNAVAILABLE";
        if (openedRuntime !== null) {
          try {
            openedRuntime.close();
          } catch {
            process.stderr.write("installed Forge read runtime close failed\n");
            process.exitCode = 1;
          }
        }
        throw error;
      }
    }
    return storeReadModel.fetch(operation, workspaceId, arguments_);
  },
});

const handlerPort = createLocalStdioHandlerPort({
  pluginRoot: PLUGIN_ROOT,
  pluginData: process.env.PLUGIN_DATA,
  workspaceRoot: process.env.EFOUNDRY_WORKSPACE_ROOT,
  buildWorkspaceMapSnapshot: buildRepositoryWorkspaceMapSnapshot,
  statusProjection: () =>
    createStatusProjection({ sessionReadState }),
  healthProjection: () =>
    createHealthProjection({ sessionReadState }),
  sessionReadPort,
});

/**
 * Bound byte-to-line adapter for canonical T01 stdio framing.
 *
 * It retains at most one 1 MiB frame. Oversized input is discarded through
 * the next delimiter and represented by invalid JSON so T01 remains the only
 * parser and JSON-RPC error mapper.
 */
async function* boundedDecodedLines(input) {
  const frame = Buffer.alloc(MAX_JSON_FRAME_BYTES + 1);
  let frameLength = 0;
  let frameTooLarge = false;

  for await (const rawChunk of input) {
    const chunk = Buffer.isBuffer(rawChunk)
      ? rawChunk
      : Buffer.from(rawChunk, "utf8");
    let offset = 0;

    while (offset < chunk.length) {
      const newline = chunk.indexOf(0x0a, offset);
      const segmentEnd = newline === -1 ? chunk.length : newline;
      const segmentLength = segmentEnd - offset;

      if (!frameTooLarge && segmentLength > 0) {
        const remaining = frame.length - frameLength;
        if (segmentLength > remaining) {
          frameTooLarge = true;
        } else {
          chunk.copy(frame, frameLength, offset, segmentEnd);
          frameLength += segmentLength;
          if (
            frameLength > MAX_JSON_FRAME_BYTES &&
            frame[frameLength - 1] !== 0x0d
          ) {
            frameTooLarge = true;
          }
        }
      }

      if (newline === -1) break;

      if (frameTooLarge) {
        yield OVERSIZED_FRAME_SENTINEL;
      } else {
        const lineLength =
          frameLength > 0 && frame[frameLength - 1] === 0x0d
            ? frameLength - 1
            : frameLength;
        yield frame.subarray(0, lineLength).toString("utf8");
      }
      frameLength = 0;
      frameTooLarge = false;
      offset = newline + 1;
    }
  }

  if (frameTooLarge) {
    yield OVERSIZED_FRAME_SENTINEL;
  } else if (frameLength > 0) {
    const lineLength =
      frame[frameLength - 1] === 0x0d ? frameLength - 1 : frameLength;
    yield frame.subarray(0, lineLength).toString("utf8");
  }
}

const onSignal = (signal) => {
  closeForgeReadRuntimeOnce();
  process.exit(signal === "SIGINT" ? 130 : 143);
};

process.once("exit", closeForgeReadRuntimeOnce);
process.once("uncaughtExceptionMonitor", closeForgeReadRuntimeOnce);
process.once("SIGINT", () => onSignal("SIGINT"));
process.once("SIGTERM", () => onSignal("SIGTERM"));

try {
  await serveStdio(
    boundedDecodedLines(process.stdin),
    (payload) => process.stdout.write(payload),
    handlerPort,
  );
} catch {
  process.stderr.write("installed stdio read service failed\n");
  process.exitCode = 1;
} finally {
  closeForgeReadRuntimeOnce();
}
