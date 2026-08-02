# Python workspace boundary

Epistemic Foundry has two explicit Python roots during the staged monorepo
transition:

- `src/epistemic_foundry` is the current tested runtime package.
- `python/epistemic_foundry` is the component root reserved by the A–Z package
  graph for generated contracts and later bounded storage/runtime additions.

The second root must not duplicate the current implementation. A later package
may add a uniquely owned module below it, but shared behavior is imported
through public package APIs and canonical schemas rather than copied between
roots. Packaging or source-root migration requires its own compatibility and
replay evidence.
