---
name: foundry-recall
description: "Retrieve prior session or workspace decisions only when materially needed and permitted by consent, retention, and workspace policy. Do not search unrelated personal context or treat memory as source evidence."
metadata:
  architecture-version: "4.0.0"
  status: "REFERENCE_BLUEPRINT"
---

# Consent-bound recall

Resolve purpose, workspace, allowed memory classes, and consent. Emit a MemoryRetrievalReceipt with searched and excluded stores, hits, redactions, and result hash. Add selected items to a bounded ContextCapsule.
