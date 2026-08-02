# C04-0002 full-conformance review

## Verdict

`FAIL — RETURN_TO_C02`

The canonical contract itself is coherent: 126 schemas and 126 one-to-one
examples validate, OpenAPI 3.1.1 retains 33 unique operations, the current B04
projection receipt is valid, Python is 990/990, Node is 460/460, and the
combined targeted suite is 287/287. Repository structure, package boundaries,
and the current generated TypeScript surface compile successfully.

The non-waivable `generated_contract_parity` gate fails. Seven generated files
still contain the pre-C01-0007 projection, and the Node fixture verifier reports
exactly `examples/sample_gate_decision.json: example hash mismatch`. This is a
clear C02-generated-contract defect, not a new shared-contract ambiguity and
not a C04-owned implementation surface.

## Disposition

- Preserve C04-0002 as immutable FAIL evidence after RAH sealing.
- Return to C02 for a new C02-0003 generator-driven correction.
- Do not hand-edit generated files and do not modify product files from C04.
- Run a new C04 attempt only after C02-0003 passes.
- Do not start B04-0008 until the new C04 attempt passes.

This is a primary-session separate adversarial review with
`actor_independence=false`. The controlling product decisions prohibit Fleet
and subagents, so no external actor-independent certification is claimed.
