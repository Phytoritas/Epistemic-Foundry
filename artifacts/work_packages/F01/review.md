# F01 package review record

Standing verdict: `PASS` (from attempt `0003`).

The earlier package-level review recorded the original `SPEC_GAP` and is
preserved in the attempt history under `attempts/`. The current review, at
`attempts/0003/review.md`, is reproduced below as the standing record.

---

# F01-0003 independent implementation review

Overall package recommendation: `PASS`

Review mode: `INDEPENDENT_IMPLEMENTATION_REVIEW`

Non-waivable findings: 0

The review followed implementation and verification. It examined the current
classifier and committer paths, targeted and full regression receipts, the
B04-0004 canonical projection receipt, and the F01 write boundary.

## Resolved authority defects

1. `request_text` is cryptographically bound to `request_input_hash`.
2. `classifier_version` is frozen at `4.0.1-f01.1`.
3. An override resolves and validates a canonical HumanDecision rather than
   trusting a caller-supplied decision hash.
4. Only a `correct` HumanDecision can authorize an override.
5. Exactly one human-authored, authority-bound ArtifactReceipt is required.

All five defects are resolved. Gold cases are 14/14, adversarial cases 16/16,
hash vectors 4/4, override fixtures 6/6, targeted Node 33/33, targeted Python
24/24, and the exhaustive underprocessing contract covers 1,023 non-empty
subsets and 58,025 subset-to-superset comparisons with zero violations.

Full Python is 947/947. Full Node is 270/271 with only the exact pre-existing
S04-TM004 stale-hash debt. That debt has no F01 causal impact and remains owned
by S04; it is not hidden by skip or xfail.

## Low limitations retained

- Tests instantiate `reject` and `service` directly, while the generic
  implementation rejects all non-`correct` decisions and all non-`human`
  actors. `hold`, `agent`, and `tool` are not each separately instantiated.
- The canonical HumanDecision schema does not structurally encode exact
  `target_work_class`, `add_interview`, or `interview_rule` intent. The current
  assurance is therefore limited to canonical human provenance, integrity,
  scope, `correct`-only authority, and upward-only protection. No stronger
  shared contract is claimed.
- Node's JUnit reporter accounts one top-level parent as a suite container,
  leaving one fewer `<testcase>` element than its authoritative footer in both
  targeted and full receipts. The footer counts, failure inventory, and
  skip/todo counts are preserved and independently checked.

The product-owner HumanDecision validates against its canonical schema and
self-hash. The live OpenAPI document is version 3.1.1 with 33 unique
operations. The B04-0004 source, snapshot, registry, projection receipt,
packaging evidence, retained wheel receipt, and registry bytes inside the
wheel all match live bytes.
No F01 write-scope violation, test weakening, or new regression was found.
F01-0001 and F01-0002 remain immutable history. `completion_ready` remains
false because the wider product objective is not complete.
