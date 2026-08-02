# Disaster Recovery Restore Drill

## Metadata

- id: RB-Y03-DR-RESTORE
- title: Disaster Recovery Restore Drill
- owner: Foundry Operations on-call
- severity: sev1
- last_reviewed: 2026-08-02
- rpo: at most 15 minutes
- rto: at most 30 minutes

## Preconditions

- A disaster is declared: the live SQLite state store or artifact store is
  corrupt, unreadable, or has entered SAFE_MODE and cannot serve production.
- The most recent verified backup cycle from RB-Y03-BACKUP is available and its
  integrity anchors (SQLite digest, artifact snapshot manifest) are known.
- A clean recovery location exists that does not overlap the corrupt primary,
  so the corrupt primary is preserved as evidence during recovery.

## Procedure

1. Freeze writes to the corrupt primary and confirm it is preserved unchanged
   as failure evidence rather than reset or deleted.
   Verify: the corrupt primary still hashes to its corrupt-state digest and the
   store reports SAFE_MODE instead of silently reinitializing.
2. Restore the SQLite backup into the recovery location through the hash-checked
   staged restore, which refuses any digest or staging mismatch.
   Verify: the restore publishes only when the backup and staged copy both match
   the recorded digest, and the restored store opens ACTIVE.
3. Restore the artifact snapshot into the recovery location through the
   manifest-checked staged restore.
   Verify: the restored artifact store opens ACTIVE, resolves seeded receipts to
   byte-exact artifacts, and passes its integrity check.
4. Reconcile recovered contents against the last backup and record the measured
   RPO and RTO for the drill.
   Verify: every pre-backup record and artifact is present and byte-exact,
   post-backup writes are absent as bounded expected loss, and the measured RTO
   is within the 30-minute budget.

## Verification

- The recovered state store and artifact store both report ACTIVE with passing
  integrity checks and reproduce all pre-backup data byte-for-byte.
- The measured RPO and RTO from the drill are recorded and within budget, and
  the corrupt primary remains intact as preserved evidence.

## Rollback

- If any restore step fails its hash or manifest check, abandon the recovery
  location without publishing it and retry from an earlier verified cycle;
  never promote an unverified restore to production.

## Escalation

- If no verified backup cycle restores cleanly, declare a sev1 data-loss
  incident, page the Foundry Operations on-call and the data owner, and
  preserve all corrupt primaries for forensic review.
