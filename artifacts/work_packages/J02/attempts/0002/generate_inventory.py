#!/usr/bin/env python3
"""Generate the sealed J02 skill inventory from production bytes."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[5]
PLUGIN = ROOT / "plugins/epistemic-foundry"
SKILLS_ROOT = PLUGIN / "skills"
TARGET = SKILLS_ROOT / "skill-inventory.json"
sys.dont_write_bytecode = True

try:
    import tiktoken
except ImportError as exc:  # pragma: no cover - execution precondition
    raise SystemExit("TOKENIZER_CONTRACT_UNAVAILABLE") from exc

if importlib.metadata.version("tiktoken") != "0.13.0":
    raise SystemExit("TOKENIZER_CONTRACT_UNAVAILABLE")
ENCODING = tiktoken.get_encoding("o200k_base")


REFERENCE_IDS = {
    "R01": "EFREF-CORE-CONSTITUTION-V4",
    "R02": "EFREF-CORE-STATUS-RECEIPTS-V4",
    "R03": "EFREF-ROUTER-E0-E5-V4",
    "R04": "EFREF-EVIDENCE-CLAIM-SEARCH-V4",
    "R05": "EFREF-EVIDENCE-SCOPE-METHOD-DEPENDENCY-V4",
    "R06": "EFREF-REASONING-TYPED-MODES-V4",
    "R07": "EFREF-PARLIAMENT-ASYMMETRIC-GATES-V4",
    "R08": "EFREF-PASSPORT-PROMOTION-V4",
    "R09": "EFREF-VALIDATION-REPLICATION-V4",
    "R10": "EFREF-EVOLUTION-RUN-GENOMES-V4",
    "R11": "EFREF-EVOLUTION-VERIFIER-STATISTICS-V4",
    "R12": "EFREF-EVOLUTION-ARCHIVE-REDQUEEN-V4",
    "R13": "EFREF-CONTEXT-MEMORY-REPLAY-V4",
    "R14": "EFREF-EXTENSIONS-MAP-DOMAINPACK-V4",
    "R15": "EFREF-PLUGIN-SECURITY-ADMIN-V4",
    "R16": "EFREF-BACKEND-SHINKA-V4",
    "R17": "EFREF-PLUGIN-DEVELOPMENT-RELEASE-V4",
}

REFERENCE_SPECS = {
    "R01": ("core/constitution.md", []),
    "R02": ("core/status-receipts.md", ["R01"]),
    "R03": ("router/e0-e5-routing.md", ["R01"]),
    "R04": ("evidence/claim-search.md", ["R01"]),
    "R05": ("evidence/scope-method-dependency.md", ["R04"]),
    "R06": ("reasoning/typed-modes.md", ["R05"]),
    "R07": ("parliament/asymmetric-gates.md", ["R02", "R04", "R05"]),
    "R08": ("passport/promotion.md", ["R02", "R07"]),
    "R09": ("validation/replication.md", ["R02", "R05"]),
    "R10": ("evolution/run-genomes.md", ["R02", "R03"]),
    "R11": ("evolution/verifier-statistics.md", ["R09", "R10"]),
    "R12": ("evolution/archive-red-queen.md", ["R10", "R11"]),
    "R13": ("context/memory-replay.md", ["R02", "R03"]),
    "R14": ("extensions/map-domain-pack.md", ["R05"]),
    "R15": ("plugin/security-administration.md", ["R01", "R02"]),
    "R16": ("backends/shinka.md", ["R10", "R15"]),
    "R17": ("plugin/development-release.md", ["R02", "R15"]),
}

SKILL_REFERENCES = {
    "foundry": ["R01", "R03"],
    "foundry-admin": ["R01", "R02", "R15", "R17"],
    "foundry-aporia": ["R01", "R05", "R06"],
    "foundry-archive": ["R01", "R10", "R12"],
    "foundry-atlas": ["R01", "R04", "R05"],
    "foundry-challenge": ["R01", "R11", "R12"],
    "foundry-claim-forge": ["R01", "R04", "R05"],
    "foundry-domain-pack": ["R01", "R05", "R14"],
    "foundry-evaluator-audit": ["R01", "R09", "R11"],
    "foundry-evolution-replay": ["R01", "R10", "R13"],
    "foundry-evolution-stop": ["R01", "R02", "R10"],
    "foundry-evolve-convert": ["R01", "R10"],
    "foundry-evolve-inspect": ["R01", "R10", "R12"],
    "foundry-evolve-run": ["R01", "R10", "R11", "R12"],
    "foundry-evolve-setup": ["R01", "R03", "R10", "R11"],
    "foundry-evolve": ["R01", "R03", "R10"],
    "foundry-intake": ["R01", "R03", "R05"],
    "foundry-map": ["R01", "R14"],
    "foundry-observe": ["R01", "R04", "R05"],
    "foundry-parliament": ["R01", "R07"],
    "foundry-passport": ["R01", "R08"],
    "foundry-plugin-dev": ["R01", "R15", "R17"],
    "foundry-promote-evolved": ["R01", "R08", "R11", "R12"],
    "foundry-reason": ["R01", "R05", "R06"],
    "foundry-recall": ["R01", "R13"],
    "foundry-replay": ["R01", "R02", "R13"],
    "foundry-replicate": ["R01", "R09", "R11"],
    "foundry-shinka-adapter": ["R01", "R16"],
    "foundry-validation": ["R01", "R09", "R11"],
}

CONDITIONAL_REFERENCES = {
    "foundry-evolve-convert": [
        {
            "reference_id": REFERENCE_IDS["R16"],
            "mode": "CONDITIONAL",
            "predicate": {"key": "backend_id", "operator": "EQUALS", "value": "shinka"},
        }
    ],
    "foundry-parliament": [
        {
            "reference_id": REFERENCE_IDS["R11"],
            "mode": "CONDITIONAL",
            "predicate": {
                "key": "candidate_origin",
                "operator": "EQUALS",
                "value": "EVOLUTION",
            },
        }
    ],
    "foundry-passport": [
        {
            "reference_id": REFERENCE_IDS["R09"],
            "mode": "CONDITIONAL",
            "predicate": {
                "key": "artifact_kind",
                "operator": "ANY_OF",
                "value": ["ValidationResult", "ReplicationResult"],
            },
        }
    ],
}

IMPLICIT_SAFE = {
    "foundry-intake",
    "foundry-claim-forge",
    "foundry-observe",
    "foundry-atlas",
    "foundry-reason",
    "foundry-aporia",
    "foundry-map",
    "foundry-passport",
    "foundry-evolve-inspect",
}
PARENT_ROUTED = {
    "foundry-parliament",
    "foundry-evolve",
    "foundry-evolve-setup",
    "foundry-evaluator-audit",
    "foundry-challenge",
    "foundry-archive",
}

AUTHORITY_FILES = {
    "master": "MASTER_SPEC.md",
    "decision": "artifacts/authority_decisions/HD-EF4-J02-SG001-20260729-001.human-decision.json",
    "contract": "docs/skill_context_contract.md",
}


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def read_canonical(path: Path) -> tuple[bytes, str]:
    data = path.read_bytes()
    if data.startswith(b"\xef\xbb\xbf"):
        raise SystemExit(f"BOM forbidden: {path}")
    text = data.decode("utf-8", errors="strict")
    if "\r" in text or not text.endswith("\n"):
        raise SystemExit(f"LF/newline contract failed: {path}")
    return data, text


def token_count(text: str) -> int:
    return len(ENCODING.encode(text, disallowed_special=()))


def parse_frontmatter(text: str) -> dict[str, str]:
    match = re.match(r"\A---\n(?P<frontmatter>[\s\S]*?)\n---\n", text)
    if match is None:
        raise SystemExit("invalid skill frontmatter")
    frontmatter = match.group("frontmatter")
    values: dict[str, str] = {}
    for key in ("name", "description"):
        line = re.search(rf"^{key}: (?P<value>.+)$", frontmatter, re.MULTILINE)
        if line is None:
            raise SystemExit(f"missing frontmatter {key}")
        raw = line.group("value")
        values[key] = json.loads(raw) if raw.startswith('"') else raw
    status = re.search(r'^  status: "(?P<value>[^"]+)"$', frontmatter, re.MULTILINE)
    if status is None:
        raise SystemExit("missing J02 skill status")
    values["status"] = status.group("value")
    return values


def parse_agent_policy(skill_id: str) -> tuple[str, bool]:
    path = SKILLS_ROOT / skill_id / "agents/openai.yaml"
    _, text = read_canonical(path)
    disposition = re.search(
        r"^  invocation_disposition: (?P<value>[A-Z_]+)$", text, re.MULTILINE
    )
    implicit = re.search(
        r"^  allow_implicit_invocation: (?P<value>true|false)$", text, re.MULTILINE
    )
    if disposition is None or implicit is None:
        raise SystemExit(f"missing J02 agent policy projection: {skill_id}")
    return disposition.group("value"), implicit.group("value") == "true"


def expected_disposition(skill_id: str) -> str:
    if skill_id == "foundry":
        return "PARENT_ROUTER"
    if skill_id in IMPLICIT_SAFE:
        return "IMPLICIT_SAFE"
    if skill_id in PARENT_ROUTED:
        return "PARENT_ROUTED"
    return "EXPLICIT_ONLY"


def source_entries(*names: str) -> list[dict[str, str]]:
    return [
        {
            "path": AUTHORITY_FILES[name],
            "sha256": sha256_bytes((ROOT / AUTHORITY_FILES[name]).read_bytes()),
        }
        for name in names
    ]


def build_skills() -> list[dict[str, Any]]:
    directories = sorted(
        (entry for entry in SKILLS_ROOT.iterdir() if entry.is_dir() and (entry / "SKILL.md").is_file()),
        key=lambda entry: entry.name.encode("utf-8"),
    )
    if len(directories) != 29 or set(entry.name for entry in directories) != set(SKILL_REFERENCES):
        raise SystemExit("production skill set is not exactly the approved 29")
    child_ids = sorted(
        (entry.name for entry in directories if entry.name != "foundry"),
        key=lambda value: value.encode("utf-8"),
    )
    result: list[dict[str, Any]] = []
    for directory in directories:
        skill_id = directory.name
        data, text = read_canonical(directory / "SKILL.md")
        metadata = parse_frontmatter(text)
        disposition = expected_disposition(skill_id)
        projected_disposition, projected_implicit = parse_agent_policy(skill_id)
        if (
            metadata["name"] != skill_id
            or metadata["status"] != "ACTIVE"
            or projected_disposition != disposition
            or projected_implicit != (disposition in {"PARENT_ROUTER", "IMPLICIT_SAFE"})
        ):
            raise SystemExit(f"skill metadata mismatch: {skill_id}")
        description = unicodedata.normalize("NFC", metadata["description"].strip())
        if len(description.encode("utf-8")) > 140:
            raise SystemExit(f"description exceeds 140 bytes: {skill_id}")
        result.append(
            {
                "skill_id": skill_id,
                "name": skill_id,
                "description": description,
                "path": f"skills/{skill_id}/SKILL.md",
                "status": "ACTIVE",
                "invocation_disposition": disposition,
                "allow_implicit_invocation": disposition in {"PARENT_ROUTER", "IMPLICIT_SAFE"},
                "sha256": sha256_bytes(data),
                "byte_count": len(data),
                "token_count": token_count(text),
                "direct_references": [REFERENCE_IDS[value] for value in SKILL_REFERENCES[skill_id]],
                "conditional_references": CONDITIONAL_REFERENCES.get(skill_id, []),
                "child_skills": child_ids if skill_id == "foundry" else [],
            }
        )
    return result


def build_references() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for alias, reference_id in sorted(REFERENCE_IDS.items(), key=lambda item: item[1].encode("utf-8")):
        relative_path, dependencies = REFERENCE_SPECS[alias]
        inventory_path = f"skills/foundry/references/{relative_path}"
        data, text = read_canonical(PLUGIN / inventory_path)
        # The approved decision and local PRD define J02 projection semantics; MASTER_SPEC
        # remains the product-level scientific and governance source summarized by each file.
        result.append(
            {
                "reference_id": reference_id,
                "path": inventory_path,
                "mode": "CONDITIONAL" if alias in {"R09", "R11", "R16"} else "REQUIRED",
                "depends_on": [REFERENCE_IDS[value] for value in dependencies],
                "sha256": sha256_bytes(data),
                "byte_count": len(data),
                "token_count": token_count(text),
                "authority_sources": source_entries("master", "decision", "contract"),
                "media_type": "text/markdown",
                "status": "ACTIVE",
            }
        )
    return result


def serialize_metadata(skills: list[dict[str, Any]]) -> str:
    parent = next(entry for entry in skills if entry["skill_id"] == "foundry")
    children = sorted(
        (entry for entry in skills if entry["skill_id"] != "foundry"),
        key=lambda entry: entry["name"].encode("utf-8"),
    )
    return unicodedata.normalize(
        "NFC",
        "".join(
            f"{entry['name']}\t{entry['description']}\t{entry['path']}\n"
            for entry in [parent, *children]
        ),
    )


def main() -> int:
    skills = build_skills()
    references = build_references()
    metadata = serialize_metadata(skills)
    metadata_bytes = metadata.encode("utf-8")
    inventory: dict[str, Any] = {
        "inventory_id": "EF-SKILL-INVENTORY-V4-J02-0002",
        "inventory_version": "4.0.1-j02.1",
        "inventory_hash": "sha256:" + "0" * 64,
        "parent_skill_id": "foundry",
        "tokenizer": {
            "package": "tiktoken",
            "version": "0.13.0",
            "encoding": "o200k_base",
            "disallowed_special": [],
            "dependency_artifact": {
                "artifact_kind": "sdist",
                "filename": "tiktoken-0.13.0.tar.gz",
                "sha256": "sha256:c9435714c3a84c2319499de9a300c0e604449dd0799ff246458b3bb6a7f433c1",
                "source_url": "https://files.pythonhosted.org/packages/source/t/tiktoken/tiktoken-0.13.0.tar.gz",
            },
        },
        "budgets": {
            "initial_metadata_max_utf8_bytes": 6400,
            "initial_metadata_max_o200k_tokens": 1600,
            "skill_body_max_utf8_bytes": 4096,
            "skill_body_max_o200k_tokens": 1024,
            "reference_file_max_utf8_bytes": 4096,
            "reference_file_max_o200k_tokens": 1024,
            "reference_closure_max_count": 12,
            "reference_closure_max_depth": 5,
            "reference_closure_max_utf8_bytes": 24576,
            "reference_closure_max_o200k_tokens": 6144,
            "activation_max_utf8_bytes": 28672,
            "activation_max_o200k_tokens": 7168,
        },
        "metadata_projection": {
            "sha256": sha256_bytes(metadata_bytes),
            "byte_count": len(metadata_bytes),
            "token_count": token_count(metadata),
        },
        "skills": skills,
        "references": references,
    }
    preimage = dict(inventory)
    preimage.pop("inventory_hash")
    inventory["inventory_hash"] = sha256_bytes(canonical_json(preimage).encode("utf-8"))
    TARGET.write_bytes(
        (json.dumps(inventory, ensure_ascii=False, indent=2, sort_keys=False) + "\n").encode("utf-8")
    )
    print(
        json.dumps(
            {
                "inventory": TARGET.relative_to(ROOT).as_posix(),
                "inventory_hash": inventory["inventory_hash"],
                "metadata_projection": inventory["metadata_projection"],
                "skill_count": len(skills),
                "reference_count": len(references),
                "status": "GENERATED",
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
