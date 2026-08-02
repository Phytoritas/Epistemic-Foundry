# Pinned build toolchain

`toolchain-lock.json` is the B02 authority for the exact Node, npm, CPython,
uv, and Python build-backend versions. A build fails closed when the active
tool versions differ.

`python-build-requirements.in` pins the PEP 517 backend named by
`pyproject.toml`. `python-build-constraints.txt` is generated from that input
with artifact hashes and is consumed by `uv build --require-hashes`.

All builds use `SOURCE_DATE_EPOCH=1767225600` (2026-01-01T00:00:00Z). The
reproducibility gate builds from two fresh source copies, compares the complete
artifact inventory, and requires byte-identical SHA-256 digests.

The Node workspace packages are private scaffolds. Their tarballs are build
evidence, not a publication claim. The Python wheel is likewise a reference
implementation artifact; B04 and later release packages own integration and
release qualification.
