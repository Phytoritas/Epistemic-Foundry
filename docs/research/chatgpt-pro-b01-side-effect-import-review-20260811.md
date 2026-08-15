DECISION: CHANGES_REQUIRED
BLOCKER: `import/*comment*/"../../foundry-kernel/src/private.mjs";` is valid JavaScript/TypeScript, but the extractor requires only whitespace between `import` and the quote, so this private-source import is invisible.
MINIMUM_REPAIR: Replace each inter-token `\s*` gap with a local trivia pattern accepting whitespace, block comments, and line comments, while retaining the existing specifier extraction and boundary checks.
RATIONALE: The repair closes the confirmed ordinary bare side-effect-import omission without changing the B01 contract, but JavaScript comments are valid token separators and leave one materially equivalent concealment path that can be closed locally without a general parser.
