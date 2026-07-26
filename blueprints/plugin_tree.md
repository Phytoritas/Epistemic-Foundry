# Reference plugin tree

This directory is a **static blueprint**, not a production implementation.

```text
plugins/epistemic-foundry/
├── .codex-plugin/
│   └── plugin.json
├── .mcp.json
├── bin/
│   └── efoundry.mjs
├── skills/
│   ├── foundry/
│   ├── foundry-intake/
│   ├── foundry-observe/
│   ├── foundry-claim-forge/
│   ├── foundry-atlas/
│   ├── foundry-reason/
│   ├── foundry-parliament/
│   ├── foundry-aporia/
│   ├── foundry-validation/
│   ├── foundry-passport/
│   ├── foundry-recall/
│   ├── foundry-map/
│   ├── foundry-replay/
│   ├── foundry-domain-pack/
│   ├── foundry-admin/
│   └── foundry-plugin-dev/
├── hooks/
│   ├── session.json
│   ├── prompt.json
│   ├── tools.json
│   ├── delegation.json
│   └── lifecycle.json
├── dist/
│   ├── hook-runner.mjs
│   ├── mcp-server.mjs
│   └── cli.mjs
└── assets/
```

The production build must generate `dist/`, validate source/dist equivalence, create an SBOM, and run fresh-install tests. The specification bundle deliberately does not ship pretend runtime code.
