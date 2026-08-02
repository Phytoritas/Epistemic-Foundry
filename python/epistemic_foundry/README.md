# Reserved Epistemic Foundry Python component root

This directory is intentionally not yet an importable package. It reserves the
manifested `python/epistemic_foundry/**` write boundary without creating a
second `epistemic_foundry` implementation beside the tested runtime in
`src/epistemic_foundry`.

C02 may add generated contract modules here; later packages may add only their
declared subtrees. Any packaging change must preserve a single canonical
implementation for each module.
