"""Bring skill agent cards in line with what the host validator accepts.

`plugin-creator/scripts/validate_plugin.py` refuses any key it does not know,
and refuses asset paths that leave the plugin archive.  The agent cards here
were written against a richer internal vocabulary, so an install fails on 122
findings that are really six repeated shapes.

What is dropped is dropped because the host has no field for it, not because
the intent was wrong: `invocation_disposition`, `sensitive`, `side_effecting`,
`load_full_instructions`, `routing_only`, and the whole `activation` block have
no accepted equivalent today.  `allow_implicit_invocation` survives, and it is
what actually governs whether a skill may fire without being named.

Icons are kept rather than dropped.  The validator rejects any path containing
`..`, even one that lands inside the archive, so the shared brand assets are
copied next to the skill that references them and the path is rewritten.

Usage:
    python plugins/epistemic-foundry/scripts/normalize-skill-agents.py [--check]
"""
from __future__ import annotations
import argparse
import shutil
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = PLUGIN_ROOT / "skills"
#: Agent-card keys the host validator accepts today.
ACCEPTED_TOP_LEVEL = ("interface", "policy", "dependencies")
ACCEPTED_POLICY = ("allow_implicit_invocation",)
#: Interface keys the validator accepts, per its own allow-list.
ACCEPTED_INTERFACE = (
    "display_name",
    "short_description",
    "long_description",
    "brand_color",
    "default_prompt",
    "icon_small",
    "icon_large",
)


def load_yaml(path: Path) -> dict:
    import yaml

    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def dump_yaml(payload: dict) -> str:
    import yaml

    return yaml.safe_dump(
        payload, allow_unicode=True, default_flow_style=False, sort_keys=False
    )


def relocate_icon(value: str, *, skill_root: Path, write: bool) -> str | None:
    """Copy an out-of-skill icon next to its skill and return the new path.

    The existing `../../../assets/...` entries resolve from the card's own
    directory (`<skill>/agents/`), but the validator resolves icon paths from
    the skill root and rejects any `..` segment.  So the asset is copied to
    `<skill>/assets/` and the path is rewritten skill-root-relative.

    A path naming no existing file returns None, so the caller drops the field
    rather than pointing at something that is not there.
    """
    card_dir = skill_root / "agents"
    if ".." not in value:
        return value if (skill_root / value).is_file() else None
    source = (card_dir / value).resolve()
    if not source.is_file():
        return None
    destination = skill_root / "assets" / source.name
    if write:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    return f"assets/{source.name}"


def normalize(
    card: dict, *, skill_root: Path, write: bool
) -> tuple[dict, list[str], list[str]]:
    """Return the accepted projection of one card, what was dropped, and what moved."""
    dropped: list[str] = []
    moved: list[str] = []
    result: dict = {}

    for key in card:
        if key not in ACCEPTED_TOP_LEVEL:
            dropped.append(key)

    interface = card.get("interface")
    if isinstance(interface, dict):
        kept_interface = {}
        for key, value in interface.items():
            if key not in ACCEPTED_INTERFACE:
                dropped.append(f"interface.{key}")
                continue
            if key in ("icon_small", "icon_large") and isinstance(value, str):
                relocated = relocate_icon(value, skill_root=skill_root, write=write)
                if relocated is None:
                    dropped.append(f"interface.{key}")
                    continue
                if relocated != value:
                    moved.append(f"interface.{key} -> {relocated}")
                kept_interface[key] = relocated
                continue
            kept_interface[key] = value
        if kept_interface:
            result["interface"] = kept_interface

    policy = card.get("policy")
    if isinstance(policy, dict):
        kept_policy = {}
        for key, value in policy.items():
            if key in ACCEPTED_POLICY:
                kept_policy[key] = value
            else:
                dropped.append(f"policy.{key}")
        if kept_policy:
            result["policy"] = kept_policy

    dependencies = card.get("dependencies")
    if isinstance(dependencies, dict):
        kept_dependencies = {
            key: value for key, value in dependencies.items() if key == "tools"
        }
        for key in dependencies:
            if key != "tools":
                dropped.append(f"dependencies.{key}")
        if kept_dependencies:
            result["dependencies"] = kept_dependencies

    return result, dropped, moved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="normalize skill agent cards")
    parser.add_argument(
        "--check",
        action="store_true",
        help="report what would change without writing",
    )
    args = parser.parse_args(argv)

    cards = sorted(SKILLS_DIR.glob("*/agents/openai.yaml"))
    if not cards:
        print("no agent cards found", file=sys.stderr)
        return 1

    changed = 0
    for path in cards:
        card = load_yaml(path)
        skill_root = path.parent.parent
        normalized, dropped, moved = normalize(
            card, skill_root=skill_root, write=not args.check
        )
        if not dropped and not moved:
            continue
        changed += 1
        skill = skill_root.name
        notes = []
        if dropped:
            notes.append(f"drop {', '.join(sorted(dropped))}")
        if moved:
            notes.append(f"move {', '.join(sorted(moved))}")
        detail = "; ".join(notes)
        if args.check:
            print(f"{skill}: would {detail}")
            continue
        path.write_text(dump_yaml(normalized), encoding="utf-8", newline="\n")
        print(f"{skill}: {detail}")

    verb = "would change" if args.check else "changed"
    print(f"{verb} {changed} of {len(cards)} agent card(s)")
    return 1 if (args.check and changed > 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
