# Plugin security and administration

- Plugin shells, hooks, skills, UIs, SDKs, and search backends are adapters; Kernel capability and ledger checks remain authoritative.
- Hooks are advisory enforcement surfaces and cannot mint approval, rewrite state, reveal holdouts, or certify completion.
- Secrets never enter prompts, artifacts, logs, receipts, or source. Capabilities are least-privilege, scoped, short-lived, and revocable.
- Administrative mutations require dry-run, expected revision, human or policy approval, backup, signed receipts, rollback, and reconciliation.
- Integrity uncertainty enters safe mode; recovery preserves immutable evidence and audit history.
