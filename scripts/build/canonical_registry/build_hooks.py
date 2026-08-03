"""Setuptools commands that project canonical contracts during every build."""

from __future__ import annotations

import gzip
import importlib.util
import os
import sys
import tarfile
from pathlib import Path
from types import ModuleType

from setuptools.command.build_py import build_py
from setuptools.command.sdist import sdist


def _load_materializer() -> ModuleType:
    """Load the sibling module under setuptools' isolated file loader.

    ``setuptools.config.expand`` loads a declarative command class directly
    from its file and does not necessarily create the dotted parent packages.
    Loading the sibling explicitly keeps the hook importable in an isolated
    PEP 517 backend without adding the repository root to ``sys.path``.
    """
    module_name = "_epistemic_foundry_canonical_materializer"
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    module_path = Path(__file__).with_name("materialize.py")
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load canonical materializer: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_materializer = _load_materializer()
materialize = _materializer.materialize
build_registry_document = _materializer.build_registry_document


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _canonical_source_files(root: Path) -> list[str]:
    paths = [
        *sorted((root / "schemas").glob("*.schema.json")),
        root / "openapi" / "epistemic-foundry-v1.openapi.yaml",
        root / "toolchains" / "toolchain-lock.json",
        root / "toolchains" / "python-build-constraints.txt",
        *sorted((root / "scripts" / "build" / "canonical_registry").glob("*.py")),
    ]
    return [path.relative_to(root).as_posix() for path in paths]


class CanonicalBuildPy(build_py):
    """Build Python modules only after materializing package resources."""

    def run(self) -> None:
        materialize(_project_root())
        super().run()

    def get_source_files(self) -> list[str]:
        root = _project_root()
        materialize(root)
        return sorted(set(super().get_source_files()) | set(_canonical_source_files(root)))


class CanonicalSdist(sdist):
    """Include authorities and the build hook in a self-contained sdist."""

    def run(self) -> None:
        materialize(_project_root())
        super().run()

    def make_archive(
        self,
        base_name: str | os.PathLike[str],
        format: str,
        root_dir: str | os.PathLike[str] | None = None,
        base_dir: str | None = None,
        owner: str | None = None,
        group: str | None = None,
    ) -> str:
        """Create a byte-reproducible gzip-compressed source archive.

        Setuptools 82.0.1 does not apply ``SOURCE_DATE_EPOCH`` to tar members
        or the gzip header.  B04 keeps that pinned backend and supplies its
        deterministic archive policy through this native command hook.
        """
        if format != "gztar":
            return super().make_archive(
                base_name,
                format,
                root_dir=root_dir,
                base_dir=base_dir,
                owner=owner,
                group=group,
            )

        epoch = build_registry_document(_project_root())[0]["build_epoch"]
        archive_path = Path(os.fspath(base_name) + ".tar.gz").resolve()
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        archive_root = Path(root_dir).resolve() if root_dir is not None else Path.cwd()
        source_root = archive_root / (base_dir or os.curdir)
        if not source_root.is_dir() or source_root.is_symlink():
            raise RuntimeError(f"invalid sdist release tree: {source_root}")

        def normalize(member: tarfile.TarInfo) -> tarfile.TarInfo:
            member.mtime = epoch
            member.uid = 0
            member.gid = 0
            member.uname = ""
            member.gname = ""
            member.mode = 0o755 if member.isdir() else 0o644
            member.pax_headers = {}
            return member

        with archive_path.open("wb") as raw_archive:
            with gzip.GzipFile(
                filename="",
                mode="wb",
                fileobj=raw_archive,
                compresslevel=9,
                mtime=epoch,
            ) as compressed_archive:
                with tarfile.open(
                    fileobj=compressed_archive,
                    mode="w",
                    format=tarfile.PAX_FORMAT,
                ) as archive:
                    archive.add(
                        source_root,
                        arcname=source_root.name,
                        recursive=True,
                        filter=normalize,
                    )
        return str(archive_path)
