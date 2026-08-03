"""Committed RAH generation snapshots must survive in the working tree.

`state_store.KEEP_GENERATIONS` is 3. Every `ralph_harness.py` invocation commits
a generation and prunes back to that window, so a bare harness call silently
deletes committed generation directories from the working tree. That happened
during this wave: two directories present in git HEAD were removed by routine
harness calls, in direct tension with the goal's requirement to preserve every
generation. The sealing scripts avoid it by raising the constant before
committing; nothing makes an interactive call do the same.

The harness lives under `.rah/helpers/` — deployed skill code, not this
repository's product — so it is not patched here. What this gate does is refuse
to let the loss go unnoticed: a generation git has is a generation the tree must
still have, and whatever is there must verify against its own manifest.

The second half matters as much as the first. A review demonstrated that
restoring a deleted generation with `git checkout` *corrupts* it, because
`core.autocrlf` rewrites line endings and the manifest digests were taken over
the original bytes. A restore that looks successful in `git status` can leave
every file in the directory failing its own manifest, so content is verified
rather than presence.
"""

from __future__ import annotations

import hashlib
import json
import subprocess

import pytest

from epistemic_foundry.contracts import repo_root

GENERATIONS = "\\.rah/ralph/generations"


def _committed_generations() -> set[str]:
    result = subprocess.run(
        ["git", "ls-tree", "--name-only", "HEAD", ".rah/ralph/generations/"],
        cwd=repo_root(),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.skip("not a git checkout")
    return {line.rsplit("/", 1)[-1] for line in result.stdout.split() if line.strip()}


def _present_generations() -> set[str]:
    root = repo_root() / ".rah" / "ralph" / "generations"
    if not root.is_dir():
        return set()
    return {entry.name for entry in root.iterdir() if entry.is_dir()}


def test_no_committed_generation_was_pruned_from_the_working_tree() -> None:
    """A generation git has is a generation the tree must still have."""
    missing = sorted(_committed_generations() - _present_generations())
    assert not missing, (
        "committed RAH generation snapshots are absent from the working tree, "
        "most likely pruned by a bare ralph_harness invocation "
        f"(KEEP_GENERATIONS is 3): {missing}. Restore them by writing the raw "
        "git blobs, never with `git checkout`, which rewrites line endings and "
        "corrupts the manifest digests."
    )


def test_every_present_generation_verifies_against_its_own_manifest() -> None:
    """Presence is not integrity: a restored directory can be silently corrupt."""
    root = repo_root() / ".rah" / "ralph" / "generations"
    if not root.is_dir():
        pytest.skip("no generation store")
    broken: list[str] = []
    for name in sorted(_present_generations()):
        directory = root / name
        manifest_path = directory / "generation-manifest.json"
        if not manifest_path.is_file():
            broken.append(f"{name}: no generation-manifest.json")
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for relative, expected in (manifest.get("files") or {}).items():
            path = directory / relative
            if not path.is_file():
                broken.append(f"{name}/{relative}: missing")
                continue
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != expected:
                broken.append(f"{name}/{relative}: {digest[:12]} != {expected[:12]}")
    assert not broken, (
        "generation snapshots do not verify against their own manifests; if they "
        "were just restored, they were probably restored with `git checkout` "
        f"under core.autocrlf: {broken[:10]}"
    )


def test_the_scan_found_a_generation_store() -> None:
    """Guard the two checks above from passing on an empty directory."""
    present = _present_generations()
    assert present, "no RAH generations are present; the checks above are vacuous"
