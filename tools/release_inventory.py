"""Single authority for which repository files are release-bundle content.

The builder and the validator previously each carried their own copy of the
selection rules.  A comment on the builder's copy warned that they had to be
kept in sync or "every local checkout reports a spurious manifest mismatch" --
which is exactly what happened: `node_modules/` and `.ruff_cache/` were treated
as shippable, so a clean checkout failed the release gate for reasons that had
nothing to do with the bundle.

Selection has three kinds of rule:

1. Unconditional exclusions: installed dependencies, caches, and local state.
2. Mixed namespaces (`artifacts/`, `.codex/`): a positive rule decides, because
   these directories hold both authored bundle content and local working files.
3. Everything else authored in the repository is bundle content.

This module performs no writes and is safe for the read-only validator to
import.
"""

from __future__ import annotations

from pathlib import Path

import yaml

#: The manifest cannot hash itself as one of its own inputs.
SELF_EXCLUDED = frozenset({"PACKAGE_MANIFEST.json", "MANIFEST.sha256"})

#: Trees that are never bundle content: version control, local runtime state,
#: installed dependencies, tool caches, build output, and the implementation
#: and test trees that the specification bundle does not ship.
NON_BUNDLE_PREFIXES: tuple[str, ...] = (
    ".git/",
    ".ai-bridge/",
    ".rah/",
    ".venv/",
    "__pycache__/",
    ".pytest_cache/",
    ".ruff_cache/",
    "node_modules/",
    "build/",
    "dist/",
    "docs/architecture/",
    "src/",
    "tests/",
)

#: `.codex/` holds both authored project-agent definitions and local session
#: state, so membership is decided by an allowlist rather than by the prefix.
CODEX_BUNDLE_PREFIXES: tuple[str, ...] = (".codex/agents/",)

NON_BUNDLE_FILES = frozenset({".gitignore", "pyproject.toml"})

NON_BUNDLE_SUFFIXES = (".pyc", ".pyo", ".egg-info")


class EvidenceDeclarationError(RuntimeError):
    """A declared evidence path cannot be resolved to exact bundle members."""


def load_declared_evidence_paths(repo_root: Path) -> frozenset[str]:
    """Collect the exact evidence files the development manifest declares.

    `artifacts/` holds thousands of working files; only the paths a work
    package names are release content.  A wildcard entry has no frozen
    expansion contract, so it is refused rather than guessed at.
    """
    manifest_path = repo_root / "manifests" / "development_manifest.yaml"
    document = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))

    declared: set[str] = set()
    wildcards: list[str] = []
    for package in document.get("work_packages", []):
        for entry in package.get("evidence_artifacts", []) or []:
            value = str(entry)
            if "*" in value:
                wildcards.append(value)
                continue
            if value.startswith("/") or ".." in Path(value).parts:
                raise EvidenceDeclarationError(
                    f"evidence path escapes the repository: {value}"
                )
            declared.add(value)

    if wildcards:
        # SPEC_GAP: no frozen semantics say whether a wildcard evidence entry
        # means "every current match" or "at least one".  Expanding it here
        # would invent a release contract.
        raise EvidenceDeclarationError(
            "evidence_artifacts wildcard entries have no frozen expansion "
            f"semantics: {sorted(wildcards)}"
        )
    return frozenset(declared)


def is_bundle_path(relative_path: str, *, declared_evidence_paths: frozenset[str]) -> bool:
    """Decide membership for one repository-relative POSIX path."""
    if relative_path in SELF_EXCLUDED:
        return False
    if relative_path in NON_BUNDLE_FILES:
        return False
    if relative_path.endswith(NON_BUNDLE_SUFFIXES):
        return False
    if any(f"/{marker}" in f"/{relative_path}" for marker in ("__pycache__/", ".pytest_cache/")):
        return False

    if relative_path.startswith("artifacts/"):
        return relative_path in declared_evidence_paths

    if relative_path.startswith(".codex/"):
        return any(relative_path.startswith(prefix) for prefix in CODEX_BUNDLE_PREFIXES)

    return not any(
        relative_path == prefix.rstrip("/") or relative_path.startswith(prefix)
        for prefix in NON_BUNDLE_PREFIXES
    )


def iter_bundle_files(repo_root: Path) -> tuple[Path, ...]:
    """Every bundle file under `repo_root`, deterministically ordered."""
    declared = load_declared_evidence_paths(repo_root)
    selected = [
        path
        for path in repo_root.rglob("*")
        if path.is_file()
        and is_bundle_path(
            path.relative_to(repo_root).as_posix(),
            declared_evidence_paths=declared,
        )
    ]
    return tuple(sorted(selected, key=lambda item: item.relative_to(repo_root).as_posix()))
