# State and Artifact Backup

## Metadata

- id: RB-Y03-BACKUP
- title: State and Artifact Backup
- owner: Foundry Operations on-call
- severity: sev2
- last_reviewed: 2026-08-02
- rpo: at most 15 minutes
- rto: at most 30 minutes

## Preconditions

- The SQLite state store and the content-addressed artifact store are the two
  canonical production stores; both must be backed up in the same cycle.
- A backup staging volume with free space of at least twice the live state size
  is mounted and writable by the backup service principal.
- The most recent backup cycle completed no more than 15 minutes ago; a longer
  gap means the RPO is already at risk and must be escalated.

## Procedure

1. Snapshot the live SQLite state store with the online backup API into the
   staging volume, never by copying the live file while it is open.
   Verify: the backup call returns a positive page count and the destination
   file exists.
2. Record the SHA-256 digest of the SQLite backup file next to the backup as
   its integrity anchor for restore.
   Verify: the stored digest is 64 lowercase hex characters and re-hashing the
   backup file reproduces it.
3. Create a content-addressed artifact-store snapshot that excludes staging and
   lock residue and writes a canonical snapshot manifest.
   Verify: the snapshot manifest validates and its file inventory matches the
   copied `sha256/` payload exactly.
4. Publish the backup pair (SQLite backup plus artifact snapshot) to the
   retention target as one labelled, timestamped cycle.
   Verify: the retention target lists the new cycle with both members present
   and the cycle timestamp is within the current 15-minute window.

## Verification

- Both the SQLite backup digest and the artifact snapshot manifest revalidate
  from the published cycle without error.
- The published cycle timestamp confirms the achieved RPO is within budget.

## Rollback

- If any step fails, discard the partial staging cycle and retain the previous
  verified cycle as the current recovery point; never publish a partial cycle.

## Escalation

- If two consecutive cycles fail or the RPO window is exceeded, page the
  Foundry Operations on-call and open a sev2 incident.
