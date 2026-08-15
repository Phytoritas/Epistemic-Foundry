**BLOCKER — `SPEC_GAP: T03-MCP-STDIO-PRODUCTION-COMPOSITION-AND-INSTALLED-PATHLESS-BINDING`**

The **T01-only command surface is correct fail-closed behavior**. T03 depends only on T01, and the current command table is derived exclusively from T01’s generated read/planning descriptors. It therefore correctly excludes T02 mutating tools while their live lifecycle binding remains unavailable.  

However, the reusable CLI modules are **not sufficient to satisfy the complete frozen T03 responsibility**. The MCP transport contract explicitly assigns both:

```text
mcp serve --transport stdio
Node adapter → provider-neutral Python handler-set bridge
```

to T03. Current framing accepts only an injected `handlerPort`; it neither constructs nor obtains the production Python handler service, authentication/workspace context, provider ports, compiler/store dependencies, or a defined cross-process request ABI.  

That composition cannot be completed truthfully under the sole write scope:

```text
packages/plugin-host/src/cli/**
```

without an owner decision for the Python composition root and installed payload projection. The gap is therefore an authority/ownership conflict, not a defect that T03 should patch by inventing local business handlers.

A second part of the same blocker is installed PATH-less startup. The registered MCP command begins with ambient `"node"`, so executable discovery occurs before any T03 helper or dispatcher can use `process.execPath`.  The dispatcher is PATH-independent only **after Node has already launched**.  This does not establish the MASTER_SPEC requirement that fresh-install PATH-less execution be tested. 

No additional material wrong-accept, wrong-reject, or reinterpretation defect is established in the stated current argv, canonical-JSON, error-code, or child-process helpers. Those remain valid T03-local reusable surfaces, but they cannot support a T03 completion claim until the production handler composition and installed PATH-less bootstrap ownership are frozen.


*Generated 1 image(s). Saved to: C:\Users\yhmoo\.oracle\sessions\pro-f863aa-043e1b\artifacts\file_00000000f92c81f8bc242b239e387e0a.png*
