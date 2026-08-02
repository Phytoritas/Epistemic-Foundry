#!/usr/bin/env python3
"""Normalize I03 JUnit receipts without changing test semantics."""

from __future__ import annotations

import argparse
import hashlib
import re
import xml.etree.ElementTree as ET
from pathlib import Path


HOSTNAME_ATTRIBUTE = re.compile(rb' hostname="[^"]*"')
WINDOWS_USER_PREFIX = re.compile(rb"C:\\Users\\[^\\]+\\")
WINDOWS_USER_PREFIX_FORWARD = re.compile(rb"C:/Users/[^/]+/")
REPOSITORY_PREFIXES = (
    b"file:///C:/dev/insight/Epistemic-Foundry/",
    b"C:/dev/insight/Epistemic-Foundry/",
    b"C:\\dev\\insight\\Epistemic-Foundry\\",
)
NODE_TOTAL_PATTERNS = {
    key: re.compile(rb"<!-- " + key.encode("ascii") + rb" ([0-9]+) -->")
    for key in ("tests", "pass", "fail", "cancelled", "skipped", "todo")
}
S04_EXPECTED = b"456330ae4aa950d1410d5180ad704927c5ec78a741d3c616d7a1cfd5bb0054a7"
S04_ACTUAL = b"fb9656cce2fd4d0147571bc85726ebbbbb3f26a59ac644c5a12040007475d938"


def normalize_local_text(value: str) -> str:
    normalized = re.sub(r"C:\\Users\\[^\\]+\\", "user:///", value)
    normalized = re.sub(r"C:/Users/[^/]+/", "user:///", normalized)
    for prefix in (
        "file:///C:/dev/insight/Epistemic-Foundry/",
        "C:/dev/insight/Epistemic-Foundry/",
        "C:\\dev\\insight\\Epistemic-Foundry\\",
    ):
        normalized = normalized.replace(prefix, "repo:///")
    return normalized


def semantic_summary(content: bytes) -> dict[str, object]:
    root = ET.fromstring(content)
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    suite_counts = tuple(
        sorted(
            (
                suite.get("name"),
                suite.get("tests"),
                suite.get("failures"),
                suite.get("errors"),
                suite.get("skipped"),
            )
            for suite in suites
        )
    )
    failures: list[tuple[str, str, str, str]] = []
    for case in root.findall(".//testcase"):
        failure = case.find("failure")
        if failure is None:
            failure = case.find("error")
        if failure is None:
            continue
        failures.append(
            (
                str(case.get("name") or ""),
                normalize_local_text(str(case.get("file") or "")).replace("\\", "/"),
                normalize_local_text(str(failure.get("message") or "")),
                normalize_local_text(str(failure.text or "")),
            )
        )
    node_totals: dict[str, int] = {}
    for key, pattern in NODE_TOTAL_PATTERNS.items():
        matches = pattern.findall(content)
        if len(matches) > 1:
            raise SystemExit(f"ambiguous Node JUnit footer for {key}")
        if matches:
            node_totals[key] = int(matches[0])
    return {
        "suite_counts": suite_counts,
        "testcase_count": len(root.findall(".//testcase")),
        "failure_count": len(root.findall(".//failure")),
        "error_count": len(root.findall(".//error")),
        "skipped_count": len(root.findall(".//skipped")),
        "failure_inventory": tuple(sorted(failures)),
        "node_totals": node_totals,
    }


def normalize(path: Path) -> None:
    original = path.read_bytes()
    before = semantic_summary(original)
    normalized = HOSTNAME_ATTRIBUTE.sub(b"", original)
    normalized = WINDOWS_USER_PREFIX.sub(b"user:///", normalized)
    normalized = WINDOWS_USER_PREFIX_FORWARD.sub(b"user:///", normalized)
    for prefix in REPOSITORY_PREFIXES:
        normalized = normalized.replace(prefix, b"repo:///")
    after = semantic_summary(normalized)

    # File paths are deliberately normalized, so compare the remaining semantic
    # fields separately and require failure messages and names to be identical.
    before_inventory = tuple((name, message, text) for name, _, message, text in before["failure_inventory"])
    after_inventory = tuple((name, message, text) for name, _, message, text in after["failure_inventory"])
    for key in (
        "suite_counts",
        "testcase_count",
        "failure_count",
        "error_count",
        "skipped_count",
        "node_totals",
    ):
        if before[key] != after[key]:
            raise SystemExit(f"JUnit semantic field {key} changed: {path}")
    if before_inventory != after_inventory:
        raise SystemExit(f"JUnit failure semantics changed: {path}")

    forbidden = (
        b"hostname=",
        b"C:/dev/insight/Epistemic-Foundry",
        b"C:\\dev\\insight\\Epistemic-Foundry",
        b"C:/Users/",
        b"C:\\Users\\",
    )
    if any(marker in normalized for marker in forbidden):
        raise SystemExit(f"machine-local JUnit metadata remains: {path}")
    had_s04 = S04_EXPECTED in original or S04_ACTUAL in original
    if had_s04 and not (S04_EXPECTED in normalized and S04_ACTUAL in normalized):
        raise SystemExit(f"S04-TM004 fingerprint changed: {path}")

    path.write_bytes(normalized)
    print(
        f"{path.as_posix()} sha256={hashlib.sha256(normalized).hexdigest()} "
        f"testcases={after['testcase_count']} failures={after['failure_count']} "
        f"errors={after['error_count']} skipped={after['skipped_count']} "
        f"node_totals={after['node_totals']}"
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
