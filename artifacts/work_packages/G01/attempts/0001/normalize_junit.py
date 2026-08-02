#!/usr/bin/env python3
"""Remove machine-local metadata from G01 JUnit receipts without changing results."""

from __future__ import annotations

import argparse
import hashlib
import re
import xml.etree.ElementTree as ET
from pathlib import Path


HOSTNAME_ATTRIBUTE = re.compile(rb' hostname="[^"]*"')
NODE_TOTALS = {
    name: re.compile(rb"<!-- " + name.encode("ascii") + rb" ([0-9]+) -->")
    for name in ("tests", "pass", "fail", "cancelled", "skipped", "todo")
}
REPOSITORY_PREFIXES = (
    rb"file:///C:/dev/insight/Epistemic-Foundry/",
    rb"C:/dev/insight/Epistemic-Foundry/",
    b"C:\\dev\\insight\\Epistemic-Foundry\\",
)
S04_EXPECTED = b"456330ae4aa950d1410d5180ad704927c5ec78a741d3c616d7a1cfd5bb0054a7"
S04_ACTUAL = b"fb9656cce2fd4d0147571bc85726ebbbbb3f26a59ac644c5a12040007475d938"


def summary(content: bytes) -> tuple[tuple[tuple[str, str | None], ...], int, int, dict[str, int]]:
    root = ET.fromstring(content)
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    pytest_counts = tuple(
        sorted(
            (
                suite.get("name", ""),
                suite.get("tests"),
                suite.get("failures"),
                suite.get("errors"),
                suite.get("skipped"),
            )
            for suite in suites
        )
    )
    failures = len(root.findall(".//failure"))
    skipped = len(root.findall(".//skipped"))
    node_totals: dict[str, int] = {}
    for name, pattern in NODE_TOTALS.items():
        matches = pattern.findall(content)
        if len(matches) > 1:
            raise SystemExit(f"ambiguous Node JUnit footer for {name}")
        if matches:
            node_totals[name] = int(matches[0])
    return pytest_counts, failures, skipped, node_totals


def normalize(path: Path) -> None:
    original = path.read_bytes()
    before = summary(original)
    normalized = HOSTNAME_ATTRIBUTE.sub(b"", original)
    normalized = normalized.replace(REPOSITORY_PREFIXES[0], b"repo:///")
    normalized = normalized.replace(REPOSITORY_PREFIXES[1], b"")
    normalized = normalized.replace(REPOSITORY_PREFIXES[2], b"")
    after = summary(normalized)
    if after != before:
        raise SystemExit(f"JUnit semantic summary changed during normalization: {path}")
    if b"hostname=" in normalized or b"C:/dev/insight/Epistemic-Foundry" in normalized:
        raise SystemExit(f"machine-local JUnit metadata remains: {path}")
    if b"C:\\dev\\insight\\Epistemic-Foundry" in normalized:
        raise SystemExit(f"machine-local Windows path remains: {path}")
    had_s04 = S04_EXPECTED in original or S04_ACTUAL in original
    if had_s04 and not (S04_EXPECTED in normalized and S04_ACTUAL in normalized):
        raise SystemExit(f"S04-TM004 fingerprint changed during normalization: {path}")
    path.write_bytes(normalized)
    print(
        f"{path.as_posix()} sha256={hashlib.sha256(normalized).hexdigest()} "
        f"failures={after[1]} skipped={after[2]} node_totals={after[3]}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    for path in args.paths:
        normalize(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
