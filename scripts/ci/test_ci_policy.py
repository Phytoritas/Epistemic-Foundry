#!/usr/bin/env python3
"""Mutation tests for the B03 workflow and cache-policy validators."""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

import cache_key_audit  # noqa: E402
import ci_matrix_lint  # noqa: E402

FIXTURE_FILES = (
    ".github/workflows/ci.yml",
    "package-lock.json",
    "uv.lock",
    "toolchains/toolchain-lock.json",
    "toolchains/python-build-constraints.txt",
)


class PolicyMutationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="efoundry-b03-policy-test-")
        self.root = Path(self.temporary.name)
        for relative in FIXTURE_FILES:
            source = REPO_ROOT / relative
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @property
    def workflow_path(self) -> Path:
        return self.root / ".github/workflows/ci.yml"

    def mutate(self, old: str, new: str) -> None:
        text = self.workflow_path.read_text(encoding="utf-8")
        self.assertIn(old, text, f"fixture mutation anchor missing: {old!r}")
        self.workflow_path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")

    def assert_matrix_rejects(self) -> None:
        result = ci_matrix_lint.validate(self.root)
        self.assertEqual("FAIL", result["status"], result)
        self.assertTrue(result["failures"], result)

    def assert_cache_rejects(self) -> None:
        result = cache_key_audit.validate(self.root)
        self.assertEqual("FAIL", result["status"], result)
        self.assertTrue(result["failures"], result)

    def test_reviewed_workflow_passes_both_validators(self) -> None:
        self.assertEqual("PASS", ci_matrix_lint.validate(self.root)["status"])
        self.assertEqual("PASS", cache_key_audit.validate(self.root)["status"])

    def test_moving_runner_alias_is_rejected(self) -> None:
        self.mutate("ubuntu-24.04", "ubuntu-latest")
        self.assert_matrix_rejects()

    def test_moving_action_tag_is_rejected(self) -> None:
        self.mutate(
            "actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803",
            "actions/checkout@v6",
        )
        self.assert_matrix_rejects()

    def test_duplicate_action_step_is_rejected(self) -> None:
        anchor = "      - name: Set up Node.js\n"
        duplicate = (
            "      - name: Duplicate checkout\n"
            "        uses: actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803\n\n"
            + anchor
        )
        self.mutate(anchor, duplicate)
        self.assert_matrix_rejects()

    def test_pull_request_target_is_rejected(self) -> None:
        self.mutate("  pull_request:\n", "  pull_request_target:\n")
        self.assert_matrix_rejects()

    def test_missing_lock_input_is_rejected(self) -> None:
        self.mutate("'uv.lock', ", "")
        self.assert_cache_rejects()

    def test_prefix_restore_is_rejected(self) -> None:
        anchor = "          enableCrossOsArchive: false\n"
        replacement = (
            "          restore-keys: |\n"
            "            efoundry-deps-v1-${{ matrix.os }}-${{ runner.arch }}-\n"
            + anchor
        )
        self.mutate(anchor, replacement)
        self.assert_cache_rejects()

    def test_cross_os_archive_is_rejected(self) -> None:
        self.mutate("enableCrossOsArchive: false", "enableCrossOsArchive: true")
        self.assert_cache_rejects()

    def test_fatal_cache_miss_is_rejected(self) -> None:
        self.mutate("fail-on-cache-miss: false", "fail-on-cache-miss: true")
        self.assert_cache_rejects()

    def test_canonical_artifact_cache_path_is_rejected(self) -> None:
        self.mutate(
            "${{ runner.temp }}/efoundry-cache/uv",
            "artifacts",
        )
        self.assert_cache_rejects()


if __name__ == "__main__":
    unittest.main(verbosity=2)
