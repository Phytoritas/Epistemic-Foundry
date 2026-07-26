# API Contract Summary

Canonical endpoint details are in `MASTER_SPEC.md` §18. This document defines cross-cutting behavior.

## Versioning

- URI version: `/api/v1`
- schema version inside artifacts
- additive optional response fields require minor version note
- required-field or semantic change requires a new schema/workflow version
- old artifacts remain readable through migration/adapters

## Authentication

Profiles:
- local single-user
- laboratory team
- service automation

Authorization is resource/capability based. Scientific role names do not grant infrastructure privileges.

## Idempotency

All mutation endpoints require an idempotency key. Key + canonical request hash is persisted.

## Pagination

Cursor-based:
```json
{
  "items": [],
  "next_cursor": null,
  "snapshot_id": "..."
}
```

A snapshot ID prevents corpus mutation from changing a paged result silently.

## Errors

```json
{
  "request_id": "REQ-...",
  "error": {
    "code": "INSIGHT_FALSIFIER_REQUIRED",
    "message": "The insight remains in Inbox.",
    "details": {},
    "retryable": false
  }
}
```

Classes:
- validation
- authorization
- conflict/idempotency
- unavailable dependency
- scientific gate
- internal/reconciliation

## Long-running jobs

POST returns run handle:
```json
{
  "run_id": "RUN-...",
  "status": "QUEUED",
  "status_url": "/api/v1/runs/RUN-..."
}
```

Polling, server events, or websocket are delivery choices; canonical event state is the same.

## Source text

Source rendering obeys license and authorization. API may return locator and short excerpt without returning full PDF bytes.

## Export

Exports include:
- schema versions
- provenance manifest
- corpus snapshot
- evidence IDs and allowed excerpts
- limitations/unsearched scopes
- checksum manifest
