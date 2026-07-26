# Release and supply-chain assurance

## Release evidence

A release bundle contains:

- frozen input snapshot,
- schema and workflow validation,
- 144-lens audit results,
- scientific and adversarial evaluation artifacts,
- dependency and license scan,
- SBOM,
- build provenance,
- independent attestation,
- PackageManifest and per-file hashes,
- archive checksum and integrity report,
- unresolved conditions.

## Final-byte rule

Manifest generation occurs after all content changes. A recursive manifest excludes only itself and its detached checksum according to a documented rule. The ZIP is then built deterministically from sorted entries and verified by extraction, CRC, duplicate-name scan, and per-file hash comparison.

## Signing

Signing is optional for the specification bundle but mandatory for a production signed-release claim. If identity or key custody is unavailable, report `SIGNING_NOT_CONFIGURED`.

## Readiness labels

- `SPEC_BUNDLE`: architecture contracts validate.
- `MVP_50`: 50-paper vertical slice passes.
- `PILOT_200`: 200-paper reliability and product gates pass.
- `PRODUCTION_2000`: full corpus, governance, security, recovery, and scale gates pass.

No lower label implies a higher one.
