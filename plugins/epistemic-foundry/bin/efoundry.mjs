#!/usr/bin/env node

const payloadCli = new URL("../dist/cli.mjs", import.meta.url);

try {
  await import(payloadCli.href);
} catch (error) {
  console.error(`efoundry dispatcher failed to load payload CLI: ${error.message}`);
  process.exitCode = 1;
}
