# P01 blocker-fix follow-up

Review the two updated attached files against your immediately preceding blocker report. This is a delta-only follow-up.

Changes made:

1. `_snapshot_brief()` now reads the caller-owned top-level Mapping once, canonicalizes it once, parses detached plain JSON, and `_validate_brief_snapshot()` alone performs field validation, exact hash recomputation, normalization, ACL, and blindness projections. `seal_brief()` uses the same detached snapshot for hashing and validation.
2. RFC3339 validation now preserves the original text while checking calendar dates, local time, numeric offsets, lowercase `t/z`, year 0000, and requiring any `:60` leap second to map through its offset to UTC 23:59.
3. Regression source covers a stateful list subclass, impossible calendar/leap times, lowercase/year-0000 input, and an offset-shifted valid leap second.

Return `NO_BLOCKER` only if both prior blockers are closed without introducing a material compatibility or correctness defect. Otherwise list only concrete remaining blockers and the smallest P01-owned correction. Do not review the unresolved ContextManifest registry/corpus snapshot authority again, do not treat unrun tests as a blocker, and do not approve the whole P01 package.
