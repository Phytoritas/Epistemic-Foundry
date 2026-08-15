**BLOCKER** — `_pack_status_inputs` overconstrains canonical input by requiring `unsearched_scopes` to be unique. The EvidencePack schema requires an array of strings but does not declare `uniqueItems`; therefore a duplicate-bearing, schema-valid pack would be rejected only by R01.

Smallest correction: accept every schema-valid string array while still rejecting scalar, byte-like, or non-string values; then canonicalize the **synthesis output** to `sorted(set(unsearched_scopes))`. `validate_synthesis` may require the recorded output to equal that sorted-unique projection. Likewise, do not impose non-empty-string semantics on source entries unless higher authority requires them.

The remaining strict completeness/stale validation, independence re-derivation, count reconciliation, degradation projection, and status derivation are aligned with R01’s owned boundary and its independence/moderator/null obligations. 
