# Harness Overlay For Recursive Architecture Refactoring

Apply this as a durable overlay only if it does not conflict with a stronger repo-local `AGENTS.md`.

## Always-On Rules
- Read and follow the nearest applicable `AGENTS.md` before non-trivial writes.
- Prefer helper scripts over raw CLI calls when the repo already provides them.
- Treat `docs/architecture/` as the design artifact spine.
- Treat `.rah/` as the harness/runtime sidecar.
- Treat Memento as a memory plane, not as a policy source.
- Rules from repo-local `AGENTS.md` outrank Memento recall.
- Do not start broad implementation before the implementation gate passes.
- Repair the earliest failed gate before creating downstream artifacts.
- Keep status, gates, wakeup, and resume files honest enough for restart.
- Use read-only exploration before broad write activity.
- Use bounded inspect-style verification for shell output and test/status checks.
- Treat team/tmux style parallelism as optional and late.
