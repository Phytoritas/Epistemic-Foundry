# C05-0001 primary-session separate adversarial review

- Reviewer: primary session in a separate adversarial pass under the
  product-owner instruction forbidding subagents and Fleet;
  actor_independence=false is recorded, not hidden.
- The deliverable interpretation is recorded, not assumed silently.
  The manifest grants schemas/v4_c05/** while the canonical schema
  count is sealed at 127 by B04 and C04, so C05 cannot add canonical
  schemas and must not restate them (EF4-I22). Following the x05
  namespace pattern (docs/v4_a06, build/v4_b05), the bundle is a
  composition layer: pure $ref structure over the canonical sources,
  generated deterministically and regenerable byte-for-byte. The
  canonical scanners were checked to be non-recursive before the
  subdirectory was created, so the sealed 127/128 counts are
  untouched.
- The mutable-space boundary is structural, not narrative. A document
  is a candidate if and only if it is one of the four genome kinds;
  evaluator, holdout, promotion-shaped, archive and backend documents
  are refused by the same oneOf that admits genomes, and a bundle
  edited to widen or narrow that space is refused at verification as
  AUTHORITY_IN_MUTABLE_SPACE or MUTABLE_SPACE_MISMATCH.
- EF4-I53 and EF4-I63 are encoded as validation requirements rather
  than advice: adaptive-search evidence cannot validate without its
  multiplicity, sequential and selective-inference records, and an
  imported run cannot validate without the pinned backend manifest
  and its qualification — with backend_name and license enforced by
  the canonical consts, not by this bundle.
- The happy paths are synthesized, not hand-picked: one minimal
  instance per canonical member is derived mechanically from the
  schema itself and validated against both its own schema and its
  family composite. The synthesizer refuses constructs it does not
  model, so a canonical schema growing an unmodelled pattern fails
  loudly instead of being silently skipped. Its number handling was
  corrected during this attempt when ratio fields with maximum 1
  rejected salted values — caught by the validation tests doing
  exactly their job.
- Membership is exhaustive and explicit: 42 members across exactly
  the five titled families, disjoint, and four evolution-adjacent
  protocol schemas excluded by name with the owner that consumes
  them, so nothing is silently out of scope.
- Residual limitations: the composites bind documents, not runtime
  behaviour — enforcement of the boundary in the running chamber
  belongs to E05/F05 and the kernel; generated types and fixtures
  belong to C06; the synthesizer models only the constructs the
  canonical family actually uses; and this review is not external
  actor-independent certification.
