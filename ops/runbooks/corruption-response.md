# Corruption Detection Response

## Metadata

- id: RB-Y03-CORRUPTION
- title: Corruption Detection Response
- owner: Foundry Operations on-call
- severity: sev1
- last_reviewed: 2026-08-02
- rpo: at most 15 minutes
- rto: at most 30 minutes

## Preconditions

- A store integrity check has failed or a store has opened in SAFE_MODE,
  signalling detected corruption rather than a transient read error.
- The RB-Y03-BACKUP and RB-Y03-DR-RESTORE runbooks are available, since
  corruption response ends in a verified restore.

## Procedure

1. Capture the corrupt store's on-disk digest and SAFE_MODE reason as evidence
   before any recovery action touches the host.
   Verify: the recorded digest and reason code are stored in the incident
   record and the corrupt bytes remain unmodified.
2. Isolate the corrupt store from production traffic so no reader or writer can
   observe or extend the corrupt state.
   Verify: production routing no longer points at the corrupt store and no new
   writes reach it.
3. Execute the RB-Y03-DR-RESTORE drill to rebuild a verified store in a clean
   recovery location from the last good backup cycle.
   Verify: the disaster recovery drill reports ACTIVE recovered stores with
   passing integrity checks and RTO within budget.
4. Cut production over to the recovered store and retain the corrupt primary for
   forensic root-cause analysis.
   Verify: production serves from the recovered store and the corrupt primary is
   archived read-only rather than deleted.

## Verification

- The corrupt store is preserved as evidence and never silently reset, and the
  recovered store passes integrity checks before taking production traffic.
- The measured RTO for the corruption response is within the 30-minute budget.

## Rollback

- If the recovered store fails post-cutover verification, route production back
  to a read-only maintenance mode and restart from an earlier verified cycle
  rather than serving unverified data.

## Escalation

- If corruption recurs after restore or spans multiple stores, page the Foundry
  Operations on-call and the data owner and open a sev1 incident for
  root-cause analysis.
