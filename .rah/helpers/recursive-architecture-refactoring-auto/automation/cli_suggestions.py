#!/usr/bin/env python3
"""Shared argparse subclass adding did-you-mean hints for unknown flags.

R36 contextual contract: candidates come FIRST from the parser that actually
raised the error (its own options plus true global options), so a typo under
``coverage update`` never advertises a ``fleet dispatch`` flag as a drop-in.
Only when the active parser has no close match does the full tree get
searched, and that fallback names where the flag would be valid instead of
suggesting it bare. ``--dangerously-*`` options are never suggested, tokens
that look like values (numbers, paths) are ignored, and any failure while
computing hints falls back to the plain argparse error — exit code 2 and the
original message are never masked.
"""

from __future__ import annotations

import argparse
import difflib

PRIMARY_CUTOFF = 0.6
FALLBACK_CUTOFF = 0.75


def _own_option_strings(parser: argparse.ArgumentParser) -> set[str]:
    options: set[str] = set()
    for action in parser._actions:
        if isinstance(getattr(action, "choices", None), dict):
            continue
        options.update(action.option_strings)
    return options


def _tree_option_strings(parser: argparse.ArgumentParser) -> dict[str, set[str]]:
    """option -> set of subcommand names it belongs to ('' for this parser)."""

    owners: dict[str, set[str]] = {}
    for option in _own_option_strings(parser):
        owners.setdefault(option, set()).add("")
    for action in parser._actions:
        choices = getattr(action, "choices", None)
        if not isinstance(choices, dict):
            continue
        for name, sub in choices.items():
            if not isinstance(sub, argparse.ArgumentParser):
                continue
            for option in _own_option_strings(sub):
                owners.setdefault(option, set()).add(str(name))
            for nested_option, nested_owners in _tree_option_strings(sub).items():
                merged = {f"{name} {owner}".strip() for owner in nested_owners}
                owners.setdefault(nested_option, set()).update(merged)
    return owners


def _looks_like_flag(token: str) -> bool:
    if not token.startswith("--"):
        return False
    body = token[2:].split("=", 1)[0]
    if not body or body.replace("-", "").replace("_", "").isdigit():
        return False
    return True


class SuggestingArgumentParser(argparse.ArgumentParser):
    """ArgumentParser whose unknown-flag errors carry nearest-flag hints."""

    def _suggestion_lines(self, message: str) -> list[str]:
        marker = "unrecognized arguments:"
        if marker not in message:
            return []
        tail = message.split(marker, 1)[1]
        unknown_flags = [
            token.split("=", 1)[0] for token in tail.split() if _looks_like_flag(token)
        ]
        if not unknown_flags:
            return []
        own = {
            option
            for option in _own_option_strings(self)
            if not option.startswith("--dangerously")
        }
        lines: list[str] = []
        tree_owners: dict[str, set[str]] | None = None
        for flag in unknown_flags:
            close = difflib.get_close_matches(flag, sorted(own), n=2, cutoff=PRIMARY_CUTOFF)
            if close:
                lines.append(f"unknown flag {flag}: did you mean {' or '.join(close)}?")
                continue
            if tree_owners is None:
                tree_owners = {
                    option: owners
                    for option, owners in _tree_option_strings(self).items()
                    if not option.startswith("--dangerously")
                }
            fallback = difflib.get_close_matches(
                flag, sorted(tree_owners), n=1, cutoff=FALLBACK_CUTOFF
            )
            if fallback:
                option = fallback[0]
                owners = sorted(owner for owner in tree_owners[option] if owner)
                if owners:
                    lines.append(
                        f"unknown flag {flag}: did you mean {option}? (valid under: {', '.join(owners[:3])})"
                    )
                else:
                    lines.append(f"unknown flag {flag}: did you mean {option}?")
        return lines

    def error(self, message: str):  # noqa: ANN201 - argparse contract (NoReturn)
        try:
            hints = self._suggestion_lines(message)
        except Exception:
            hints = []
        if hints:
            message = message + "\n" + "\n".join(hints)
        super().error(message)
