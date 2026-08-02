#!/usr/bin/env python3
"""Remove machine-identifying hostname metadata from a pytest JUnit receipt."""

from __future__ import annotations

import argparse
import hashlib
import re
import xml.etree.ElementTree as ET
from pathlib import Path


HOSTNAME_ATTRIBUTE = re.compile(rb' hostname="[^"]*"')
COUNT_ATTRIBUTES = ("tests", "failures", "errors", "skipped")


def suite_counts(content: bytes) -> tuple[str | None, ...]:
    root = ET.fromstring(content)
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    if suite is None:
        raise SystemExit("JUnit document has no testsuite element")
    return tuple(suite.get(name) for name in COUNT_ATTRIBUTES)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    args = parser.parse_args()

    original = args.path.read_bytes()
    original_counts = suite_counts(original)
    normalized, replacements = HOSTNAME_ATTRIBUTE.subn(b"", original)
    if replacements != 1:
        raise SystemExit(
            f"expected exactly one JUnit hostname attribute, found {replacements}"
        )
    if b"hostname=" in normalized:
        raise SystemExit("JUnit hostname metadata remains after normalization")
    if suite_counts(normalized) != original_counts:
        raise SystemExit("JUnit aggregate counts changed during normalization")

    args.path.write_bytes(normalized)
    print(
        "normalized=1 "
        f"tests={original_counts[0]} failures={original_counts[1]} "
        f"errors={original_counts[2]} skipped={original_counts[3]} "
        f"sha256={hashlib.sha256(normalized).hexdigest()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
