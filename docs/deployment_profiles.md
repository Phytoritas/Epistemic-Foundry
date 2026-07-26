# Deployment profiles

## Local specification profile

- filesystem artifacts,
- no external corpus,
- schema/workflow/audit tools only,
- no production credentials,
- no signing claim.

## MVP-50 profile

- PostgreSQL and S3-compatible object store,
- 50 licensed papers,
- one provider adapter plus deterministic fallback tests,
- bounded worker queue,
- local GROBID/Docling,
- human annotation and review roles.

## Pilot-200 profile

Adds backup/restore, observability, external metadata/novelty sources, accessibility, rate-limit handling, incident runbooks, and provider redundancy where evaluated.

## Production-2000 profile

Requires approved region/jurisdiction, retention, secret manager, key custody, high-availability database/object store, queue fencing, load/recovery testing, governance roles, release signing, and periodic reassessment.

## Decision requirement

The specification intentionally does not choose cloud, region, database topology, provider credentials, or signing infrastructure. Those are explicit conditional deployment decisions, not hidden defaults.
