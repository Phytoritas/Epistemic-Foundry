#!/usr/bin/env node

import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const payloadCli = fileURLToPath(new URL("../dist/cli.mjs", import.meta.url));
const child = spawn(process.execPath, [payloadCli, ...process.argv.slice(2)], {
  cwd: process.cwd(),
  env: process.env,
  shell: false,
  stdio: "inherit",
  windowsHide: true,
});

child.once("error", (error) => {
  console.error(`efoundry dispatcher failed to start payload CLI: ${error.message}`);
  process.exitCode = 1;
});

child.once("exit", (code, signal) => {
  if (signal !== null) {
    try {
      process.kill(process.pid, signal);
    } catch {
      process.exitCode = 1;
    }
    return;
  }
  process.exitCode = code ?? 1;
});
