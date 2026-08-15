"""Recompute the J02 skill-inventory seals after a skill body changes.

Editing a `SKILL.md` invalidates its recorded sha256/byte/token seal, the
metadata projection, and the canonical `inventory_hash`.  Recomputing those by
hand is how the inventory drifts from the validator that checks it, so every
value here is derived through the canonical counter in `count_tokens.py`.

Usage:

    python tools/skill-context/reseal_inventory.py <skill-id> [<skill-id> ...]

Afterwards, `count_tokens.py verify-inventory` must report PASS, and the two
J02 fixtures must be updated to the printed `inventory_hash`.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_counter():
    spec = importlib.util.spec_from_file_location(
        "count_tokens", Path(__file__).with_name("count_tokens.py")
    )
    counter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(counter)
    return counter


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("skill_ids", nargs="+", help="skill IDs whose bodies changed")
arguments = parser.parse_args()
edited = set(arguments.skill_ids)

counter = load_counter()

encoding = counter.require_tokenizer()
inventory_path = ROOT / "plugins/epistemic-foundry/skills/skill-inventory.json"
inventory = json.loads(inventory_path.read_text(encoding="utf-8"))

known = {entry["skill_id"] for entry in inventory["skills"]}
unknown = sorted(edited - known)
if unknown:
    raise SystemExit(f"unknown skill IDs: {unknown}")

for entry in inventory["skills"]:
    if entry["skill_id"] not in edited:
        continue
    body = ROOT / "plugins/epistemic-foundry" / entry["path"]
    data, text = counter.read_canonical_text(body)
    tokens, _ = counter.count_text(text, encoding)
    entry["sha256"] = counter.sha256_bytes(data)
    entry["byte_count"] = len(data)
    entry["token_count"] = tokens
    print(f"{entry['skill_id']}: bytes={len(data)} tokens={tokens}")

metadata = counter.serialize_metadata(inventory["skills"])
metadata_bytes = metadata.encode("utf-8")
metadata_tokens, _ = counter.count_text(metadata, encoding)
inventory["metadata_projection"] = {
    "sha256": counter.sha256_bytes(metadata_bytes),
    "byte_count": len(metadata_bytes),
    "token_count": metadata_tokens,
}

preimage = dict(inventory)
preimage.pop("inventory_hash", None)
inventory["inventory_hash"] = counter.sha256_bytes(
    counter.canonical_json(preimage).encode("utf-8")
)

inventory_path.write_text(
    json.dumps(inventory, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
    newline="\n",
)
print("inventory_hash=" + inventory["inventory_hash"])
print("metadata=" + json.dumps(inventory["metadata_projection"]))
