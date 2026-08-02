#!/usr/bin/env python3
"""Verify the B02 dependency correction through the B04 build boundary.

This verifier is attempt-local evidence.  It does not edit ``pyproject.toml``,
``uv.lock``, the canonical sources, or the packaged canonical snapshot.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile
from email.parser import Parser
from pathlib import Path, PurePosixPath
from typing import Any


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/B04/attempts/0005"
ATTEMPT_ID = "B04-0005"

EXPECTED = {
    "pyproject": "31cf5dffa4703052d70536dbbb6e64d917900c70d52b039f9c9cbf09920353db",
    "uv_lock": "5c3798ff0323f9352d73f17fa93913590d7dbb5382dd0de26b1619e775b58caa",
    "b02_report": "3c2259e7d4b7ce987960b82f2fb161914637567eacf3030d24899e44f462b33a",
    "b02_review": "4b126d5d36aae2d8c742e5a16c14b7928c249e172be5934a5b1ea937b76c0f84",
    "b02_core_integrity": "b7d4ba723c8dea6fbbdf69bd5ca08dd94477ae4c28b571bd300d3bc03acd3563",
    "canonical_registry": "5f3c4514b3801cc66cc0a403d49c1dc380f7665ddc570d4987072a6f77fde1dd",
    "wheel": "cc3aa468f09092134a4bc8448f4bf60822a4d2ff8df6df16bcbc86483238cb7a",
    "prior_sdist": "560ce3afa19da1fe885785826336276315b26d1e57f248dddcbb71bc1bc6ce76",
    "current_sdist": "c2d68ad297ae295f30761cc68c48d3bd1d9cc90cd5111597bb7be9cd27ee7eed",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON artifact is not an object: {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def require_hash(relative: str, expected: str) -> str:
    observed = sha256(ROOT / relative)
    if observed != expected:
        raise RuntimeError(
            f"hash mismatch for {relative}: expected={expected} observed={observed}"
        )
    return observed


def run(command: list[str], *, environment: dict[str, str] | None = None) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(
            f"command failed ({completed.returncode}): {' '.join(command)}\n{detail}"
        )
    return {
        "command": command,
        "exit_code": completed.returncode,
        "stdout": completed.stdout.strip(),
    }


def normalized_sdist_files(path: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    roots: set[str] = set()
    with tarfile.open(path, mode="r:gz") as archive:
        for member in archive.getmembers():
            pure = PurePosixPath(member.name)
            if pure.is_absolute() or ".." in pure.parts or not pure.parts:
                raise RuntimeError(f"unsafe sdist member: {member.name}")
            roots.add(pure.parts[0])
            if member.issym() or member.islnk() or member.isdev():
                raise RuntimeError(f"unsupported sdist member: {member.name}")
            if not member.isfile():
                continue
            relative = PurePosixPath(*pure.parts[1:]).as_posix()
            if not relative or relative in files:
                raise RuntimeError(f"duplicate or root-level sdist file: {member.name}")
            extracted = archive.extractfile(member)
            if extracted is None:
                raise RuntimeError(f"cannot read sdist member: {member.name}")
            files[relative] = extracted.read()
    if roots != {"epistemic_foundry-4.0.0"}:
        raise RuntimeError(f"unexpected sdist root inventory: {sorted(roots)}")
    return files


def distribution_metadata(path: Path, *, wheel: bool) -> dict[str, Any]:
    if wheel:
        with zipfile.ZipFile(path) as archive:
            names = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
            if len(names) != 1:
                raise RuntimeError(f"wheel METADATA cardinality is {len(names)}")
            text = archive.read(names[0]).decode("utf-8")
    else:
        files = normalized_sdist_files(path)
        names = [name for name in files if name.endswith(".egg-info/PKG-INFO")]
        if len(names) != 1:
            raise RuntimeError(f"sdist PKG-INFO cardinality is {len(names)}")
        text = files[names[0]].decode("utf-8")
    metadata = Parser().parsestr(text)
    requires = metadata.get_all("Requires-Dist") or []
    if any(requirement.lower().startswith("tiktoken") for requirement in requires):
        raise RuntimeError("distribution metadata exposes tiktoken as Requires-Dist")
    return {
        "name": metadata.get("Name"),
        "requires_dist": requires,
        "runtime_tiktoken_exposure": False,
        "version": metadata.get("Version"),
    }


def verify_rah_b02_seal() -> dict[str, Any]:
    ralph = ROOT / ".rah/ralph"
    pointer = read_json(ralph / "current.json")
    generation = str(pointer.get("generation") or "")
    generation_root = ralph / "generations" / generation
    manifest = read_json(generation_root / "generation-manifest.json")
    files = manifest.get("files")
    if manifest.get("generation") != generation or not isinstance(files, dict) or len(files) != 6:
        raise RuntimeError("current RAH generation is not a six-snapshot generation")
    for relative, expected in files.items():
        if sha256(generation_root / relative) != expected:
            raise RuntimeError(f"current RAH generation hash mismatch: {relative}")
    ledger = read_json(generation_root / "evidence_ledger.json")
    entries = ledger.get("entries")
    if not isinstance(entries, list):
        raise RuntimeError("RAH evidence ledger is invalid")
    by_id = {
        str(entry.get("id")): entry
        for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("id"), str)
    }
    for identifier in ("E0090", "E0091"):
        if identifier not in by_id:
            raise RuntimeError(f"B02 seal evidence is missing: {identifier}")
    if not str(by_id["E0091"].get("summary", "")).startswith("B02-0002 PASS closeout"):
        raise RuntimeError("E0091 is not the B02-0002 closeout seal")
    return {
        "core_evidence_id": "E0090",
        "final_evidence_id": "E0091",
        "observed_generation": generation,
        "six_snapshot_hashes_verified": 6,
        "status": "PASS",
    }


def clean_frozen_sync() -> dict[str, Any]:
    fixture = ROOT / "tests/fixtures/j02/tokenizer-vectors.json"
    with tempfile.TemporaryDirectory(prefix="efoundry-b04-dependency-") as temporary:
        temporary_root = Path(temporary).resolve()
        environment = os.environ.copy()
        environment.update(
            {
                "PYTHONNOUSERSITE": "1",
                "UV_NO_PROGRESS": "1",
                "UV_PROJECT_ENVIRONMENT": str(temporary_root / "venv"),
            }
        )
        sync = run(
            [
                "uv",
                "sync",
                "--frozen",
                "--extra",
                "dev",
                "--group",
                "skill-context",
                "--no-install-project",
            ],
            environment=environment,
        )
        python = temporary_root / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        probe_path = temporary_root / "probe.py"
        probe_path.write_text(
            """from __future__ import annotations
import json
import sys
import unicodedata
from importlib import metadata
from pathlib import Path
import tiktoken

fixture = json.loads(Path(sys.argv[1]).read_text(encoding=\"utf-8\"))
encoding = tiktoken.get_encoding(\"o200k_base\")
results = []
for vector in fixture[\"vectors\"]:
    text = vector[\"text\"]
    if vector.get(\"normalize_nfc\"):
        text = unicodedata.normalize(\"NFC\", text)
    observed = encoding.encode(text, disallowed_special=())
    if observed != vector[\"token_ids\"]:
        raise SystemExit(2)
    results.append({\"id\": vector[\"id\"], \"token_count\": len(observed)})
print(json.dumps({
    \"encoding\": encoding.name,
    \"tiktoken_version\": metadata.version(\"tiktoken\"),
    \"vectors\": results,
}, sort_keys=True))
""",
            encoding="utf-8",
            newline="\n",
        )
        probe = run([str(python), "-I", str(probe_path), str(fixture)])
        result = json.loads(probe["stdout"])
        if result.get("tiktoken_version") != "0.13.0":
            raise RuntimeError("clean environment did not install tiktoken 0.13.0")
        if result.get("encoding") != "o200k_base" or len(result.get("vectors", [])) != 7:
            raise RuntimeError("clean environment tokenizer vector contract failed")
        return {
            "environment_outside_repository": not str(python).startswith(str(ROOT)),
            "frozen_sync": "PASS",
            "sync_exit_code": sync["exit_code"],
            "tiktoken_version": result["tiktoken_version"],
            "tokenizer_encoding": result["encoding"],
            "tokenizer_vector_pass_count": len(result["vectors"]),
            "tokenizer_vectors": result["vectors"],
        }


def verify() -> dict[str, Any]:
    paths = {
        "wheel": ATTEMPT / "dist/epistemic_foundry-4.0.0-py3-none-any.whl",
        "current_sdist": ATTEMPT / "dist/epistemic_foundry-4.0.0.tar.gz",
        "prior_wheel": ROOT / "artifacts/work_packages/B04/attempts/0004/dist/epistemic_foundry-4.0.0-py3-none-any.whl",
        "prior_sdist": ROOT / "artifacts/work_packages/B04/attempts/0004/dist/epistemic_foundry-4.0.0.tar.gz",
    }
    hashes = {
        "pyproject.toml": require_hash("pyproject.toml", EXPECTED["pyproject"]),
        "uv.lock": require_hash("uv.lock", EXPECTED["uv_lock"]),
        "B02-0002/report.json": require_hash(
            "artifacts/work_packages/B02/attempts/0002/report.json", EXPECTED["b02_report"]
        ),
        "B02-0002/review.md": require_hash(
            "artifacts/work_packages/B02/attempts/0002/review.md", EXPECTED["b02_review"]
        ),
        "B02-0002/rah-core-integrity.json": require_hash(
            "artifacts/work_packages/B02/attempts/0002/rah-core-integrity.json",
            EXPECTED["b02_core_integrity"],
        ),
        "canonical-registry.json": require_hash(
            "src/epistemic_foundry/_canonical/canonical-registry.json",
            EXPECTED["canonical_registry"],
        ),
    }
    if sha256(paths["wheel"]) != EXPECTED["wheel"] or sha256(paths["prior_wheel"]) != EXPECTED["wheel"]:
        raise RuntimeError("current and prior wheels are not byte-identical")
    if sha256(paths["prior_sdist"]) != EXPECTED["prior_sdist"]:
        raise RuntimeError("prior B04 sdist hash changed")
    if sha256(paths["current_sdist"]) != EXPECTED["current_sdist"]:
        raise RuntimeError("current B04 sdist hash is not the verified build output")

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    if pyproject.get("dependency-groups") != {"skill-context": ["tiktoken==0.13.0"]}:
        raise RuntimeError("skill-context dependency group is not exact")
    runtime_declarations = list(pyproject["project"].get("dependencies", []))
    for values in pyproject["project"].get("optional-dependencies", {}).values():
        runtime_declarations.extend(values)
    if any(str(item).lower().startswith("tiktoken") for item in runtime_declarations):
        raise RuntimeError("pyproject exposes tiktoken as runtime or optional metadata")

    prior_files = normalized_sdist_files(paths["prior_sdist"])
    current_files = normalized_sdist_files(paths["current_sdist"])
    if set(prior_files) != set(current_files):
        raise RuntimeError("B02 correction changed the sdist member inventory")
    changed_sdist_files = sorted(
        name for name in current_files if current_files[name] != prior_files[name]
    )
    if changed_sdist_files != ["pyproject.toml"]:
        raise RuntimeError(f"unrelated sdist content drift: {changed_sdist_files}")
    if current_files["pyproject.toml"] != (ROOT / "pyproject.toml").read_bytes():
        raise RuntimeError("current sdist pyproject does not match the root authority")
    if hashlib.sha256(prior_files["pyproject.toml"]).hexdigest() != (
        "29d7a25d530884a4a2dff3d8ca2d9878717a43a4dc3c2710fc5317f533a7be44"
    ):
        raise RuntimeError("prior sdist does not contain the sealed pre-B02 pyproject")

    lock_check = run(["uv", "lock", "--check"])
    b02_report = read_json(ROOT / "artifacts/work_packages/B02/attempts/0002/report.json")
    if b02_report.get("package_status") != "PASS" or b02_report.get("completion_ready") is not False:
        raise RuntimeError("B02-0002 report is not the sealed package PASS")

    return {
        "attempt_id": ATTEMPT_ID,
        "b02_binding": {
            "attempt_id": "B02-0002",
            "hashes": hashes,
            "rah_seal": verify_rah_b02_seal(),
            "status": "PASS",
        },
        "clean_environment": clean_frozen_sync(),
        "dependency_group": {
            "declaration": "tiktoken==0.13.0",
            "group": "skill-context",
            "lock_check": "PASS",
            "lock_check_output": lock_check["stdout"],
            "runtime_dependency_exposure": False,
        },
        "distribution_metadata": {
            "sdist": distribution_metadata(paths["current_sdist"], wheel=False),
            "wheel": distribution_metadata(paths["wheel"], wheel=True),
        },
        "reproducibility": {
            "current_sdist_sha256": EXPECTED["current_sdist"],
            "prior_sdist_sha256": EXPECTED["prior_sdist"],
            "sdist_changed_files": changed_sdist_files,
            "sdist_member_inventory_equal": True,
            "unrelated_sdist_drift_count": 0,
            "wheel_byte_equal_to_B04_0004": True,
            "wheel_sha256": EXPECTED["wheel"],
        },
        "status": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, default=ATTEMPT / "dependency-revalidation.json")
    args = parser.parse_args()
    try:
        result = verify()
    except Exception as error:
        result = {"attempt_id": ATTEMPT_ID, "error": str(error), "status": "FAIL"}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.report, result)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
