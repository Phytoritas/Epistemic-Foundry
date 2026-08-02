"""Tool-surface honesty for the evolution adapter.

G05 sealed the binding between the evolution skills and the CLI the host
actually projects, and its declaration records the answer this package needs:
the evolution commands the specification *proposes* are, with a small handful
of exceptions, not projected by the tool surface at all.  T05 does not get to
disagree with that finding by shipping executors for them.

So the descriptor table is derived by reading the G05 declaration rather than
by listing commands here.  A command is registrable only where the surface
already projects it; everything the specification proposes but the surface
does not project is carried forward by name, so the qualification record says
out loud which parts of the evolution CLI have no executor and why.

Nothing here executes a command.  The table describes what an executor could
legally be bound to, and the registration gate refuses the rest.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from ...contracts import repo_root
from .findings import (
    _fail,
    require_identifier,
    require_mapping,
    seal,
)

#: The sealed G05 evolution surface declaration.  It is the evidence artifact
#: for the projection finding, so it is read rather than summarized.
EVOLUTION_SURFACE_PATH = (
    "plugin_blueprint/epistemic-foundry/v4_g05/evolution-surface.json"
)

#: The declaration fields this package reads.  Named here so a surface that
#: drops one is refused rather than silently projecting an empty command set.
SURFACE_FIELDS: tuple[str, ...] = ("surface_id", "surface_version", "skills")
SKILL_FIELDS: tuple[str, ...] = (
    "skill_id",
    "proposed_commands",
    "available_commands",
)


def load_evolution_surface() -> dict[str, Any]:
    """Read the sealed surface declaration, or refuse to guess at it."""
    path = repo_root() / EVOLUTION_SURFACE_PATH
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        _fail(
            "SURFACE_UNREADABLE",
            f"cannot read {EVOLUTION_SURFACE_PATH}: {error}",
            {"path": EVOLUTION_SURFACE_PATH},
        )
    if not isinstance(document, Mapping):
        _fail(
            "SURFACE_UNREADABLE",
            "the surface declaration is not an object",
            {"path": EVOLUTION_SURFACE_PATH},
        )
    missing = [field for field in SURFACE_FIELDS if field not in document]
    if missing:
        _fail(
            "SURFACE_UNREADABLE",
            "the surface declaration is missing required fields",
            {"missing": missing, "path": EVOLUTION_SURFACE_PATH},
        )
    if not isinstance(document["skills"], list) or not document["skills"]:
        _fail(
            "SURFACE_UNREADABLE",
            "the surface declaration lists no skill",
            {"path": EVOLUTION_SURFACE_PATH},
        )
    return json.loads(json.dumps(document))


def _skill_commands(skill: object, position: int) -> tuple[str, list[str], list[str]]:
    entry = require_mapping(skill, f"skills[{position}]")
    missing = [field for field in SKILL_FIELDS if field not in entry]
    if missing:
        _fail(
            "SURFACE_UNREADABLE",
            f"skills[{position}] is missing required fields",
            {"missing": missing, "position": position},
        )
    skill_id = require_identifier(entry["skill_id"], f"skills[{position}].skill_id")
    lists: list[list[str]] = []
    for field in ("proposed_commands", "available_commands"):
        value = entry[field]
        if not isinstance(value, list):
            _fail(
                "SURFACE_UNREADABLE",
                f"skills[{position}].{field} is not an array",
                {"field": field, "skill_id": skill_id},
            )
        lists.append(
            [
                require_identifier(command, f"{skill_id}.{field}")
                for command in value  # type: ignore[union-attr]
            ]
        )
    return skill_id, lists[0], lists[1]


def command_projection() -> dict[str, Any]:
    """Split the declared evolution CLI into projected and unprojected halves.

    ``proposed_unavailable_commands`` is the G05 finding restated from the
    declaration itself: a command the specification proposes and the tool
    surface does not project.  It is the set no executor may be bound to.
    """
    document = load_evolution_surface()
    owners: dict[str, set[str]] = {}
    proposed: set[str] = set()
    available: set[str] = set()
    for position, skill in enumerate(document["skills"]):
        skill_id, skill_proposed, skill_available = _skill_commands(skill, position)
        for command in skill_proposed + skill_available:
            owners.setdefault(command, set()).add(skill_id)
        proposed.update(skill_proposed)
        available.update(skill_available)
    if not proposed and not available:
        _fail(
            "SURFACE_UNREADABLE",
            "the surface declaration names no command at all",
            {"path": EVOLUTION_SURFACE_PATH},
        )
    return {
        "surface_id": require_identifier(document["surface_id"], "surface_id"),
        "surface_version": require_identifier(
            document["surface_version"], "surface_version"
        ),
        "available_commands": sorted(available),
        "proposed_commands": sorted(proposed),
        "proposed_unavailable_commands": sorted(proposed - available),
        "owning_skill_ids": {
            command: sorted(names) for command, names in sorted(owners.items())
        },
    }


def tool_descriptors() -> tuple[dict[str, Any], ...]:
    """The adapter's descriptor table for the evolution operations.

    One row per declared command, each saying which skill owns it and whether
    the tool surface projects it.  A row with ``projected`` false is a command
    this adapter describes and refuses to execute.
    """
    projection = command_projection()
    available = set(projection["available_commands"])
    return tuple(
        {
            "command": command,
            "owning_skill_ids": list(owners),
            "projected": command in available,
        }
        for command, owners in sorted(projection["owning_skill_ids"].items())
    )


def registrable_commands() -> tuple[str, ...]:
    """Commands an executor may legally be bound to."""
    return tuple(command_projection()["available_commands"])


def build_executor_registry(
    *, registry_id: str, executors: Mapping[str, str]
) -> dict[str, Any]:
    """Bind executors to commands, refusing every unprojected one.

    The refusal is on the whole request rather than per command: a registry
    that silently dropped the unprojected half would still report success
    while the caller believed those commands had executors.
    """
    identifier = require_identifier(registry_id, "registry_id")
    requested = require_mapping(executors, "executors")
    bindings = {
        require_identifier(command, "executors key"): require_identifier(
            executor, f"executors[{command}]"
        )
        for command, executor in requested.items()
    }
    projection = command_projection()
    projected = set(projection["available_commands"])
    unprojected = sorted(set(bindings) - projected)
    if unprojected:
        _fail(
            "EXECUTOR_UNPROJECTED",
            "the tool surface does not project these commands",
            {
                "projected": projection["available_commands"],
                "unprojected": unprojected,
            },
        )
    return seal(
        {
            "registry_id": identifier,
            "registrations": dict(sorted(bindings.items())),
            "surface_id": projection["surface_id"],
            "surface_version": projection["surface_version"],
            "proposed_unavailable_commands": projection[
                "proposed_unavailable_commands"
            ],
        },
        "registry_hash",
    )
