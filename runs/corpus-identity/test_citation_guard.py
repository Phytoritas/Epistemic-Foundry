"""Tests for the corpus identity map and its citation guard.

Run from the Epistemic-Foundry repo root:
    uv run --locked python -B -m unittest discover -s runs/corpus-identity -t runs/corpus-identity
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import citation_guard as guard

HERE = Path(__file__).resolve().parent
MAP_PATH = HERE / "corpus-identity-map.json"


class MapIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = json.loads(MAP_PATH.read_text(encoding="utf-8"))
        cls.docs = cls.data["documents"]

    def test_counts_agree_with_documents(self) -> None:
        counts = self.data["counts"]
        self.assertEqual(counts["directories_scanned"], len(self.docs))
        self.assertEqual(
            counts["documents_citable"],
            sum(1 for d in self.docs.values() if d["citable"]),
        )
        self.assertEqual(
            counts["distinct_texts"],
            len({d["content_sha256"] for d in self.docs.values()}),
        )

    def test_duplicate_groups_are_internally_consistent(self) -> None:
        for slug, doc in self.docs.items():
            group = doc["duplicate_group"]
            if group is None:
                self.assertEqual(doc["resolution"], "unique", slug)
                continue
            self.assertIn(slug, group, slug)
            self.assertEqual(group, sorted(group), slug)
            hashes = {self.docs[m]["content_sha256"] for m in group}
            self.assertEqual(hashes, {doc["content_sha256"]}, slug)

    def test_unresolved_groups_are_never_citable(self) -> None:
        """The core safety property: no UNRESOLVED directory may be cited."""
        for slug, doc in self.docs.items():
            if doc["resolution"] == "UNRESOLVED":
                self.assertFalse(doc["citable"], slug)
                self.assertIsNone(doc["canonical_title"], slug)
                self.assertIsNone(doc["doi"], slug)
                self.assertIsNotNone(doc["duplicate_group"], slug)

    def test_resolved_groups_share_one_canonical_identity(self) -> None:
        for slug, doc in self.docs.items():
            if doc["resolution"] != "resolved":
                continue
            titles = {self.docs[m]["canonical_title"] for m in doc["duplicate_group"]}
            self.assertEqual(len(titles), 1, slug)
            self.assertIsNotNone(doc["canonical_title"], slug)

    def test_every_resolution_carries_evidence(self) -> None:
        for slug, doc in self.docs.items():
            self.assertTrue(doc["evidence"], slug)
            self.assertIn(doc["resolution"], {"unique", "resolved", "UNRESOLVED"}, slug)

    def test_exactly_one_member_per_resolved_group_keeps_its_own_label(self) -> None:
        for group in self.data["resolved_groups"]:
            correct = [m for m in group["members"] if not self.docs[m]["mislabelled"]]
            self.assertEqual(correct, [group["winner"]], group["members"])

    def test_text_quality_block_is_complete(self) -> None:
        allowed = {"ok", "low_printable", "stub", "formfeed_heavy"}
        for slug, doc in self.docs.items():
            q = doc["text_quality"]
            self.assertEqual(set(q), {"char_count", "printable_ratio", "form_feed_count",
                                      "form_feeds_per_10k_chars", "quality_flag"}, slug)
            self.assertIn(q["quality_flag"], allowed, slug)
            self.assertGreaterEqual(q["char_count"], 0, slug)
            self.assertTrue(0.0 <= q["printable_ratio"] <= 1.0, slug)


class GuardBehaviourTests(unittest.TestCase):
    """Behaviour is asserted against a synthetic map so the tests stay valid
    even when the corpus later gains or loses an unresolvable group."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.fake = Path(cls._tmp.name) / "map.json"
        cls.fake.write_text(json.dumps({
            "corpus_root": "C:/fake",
            "documents": {
                "AAA_good": {
                    "content_sha256": "a" * 64, "canonical_title": "Good Paper",
                    "doi": "10.1000/good", "resolution": "unique", "evidence": "unique text",
                    "duplicate_group": None, "citable": True, "index_title": "Good Paper",
                    "index_doi": "10.1000/good", "in_index": True, "mislabelled": False,
                    "identity_corroborated": True, "resolution_rule": "unique_text",
                    "text_quality": {"char_count": 5000, "printable_ratio": 1.0,
                                     "form_feed_count": 0, "quality_flag": "ok"},
                },
                "BBB_relabelled": {
                    "content_sha256": "b" * 64, "canonical_title": "Real Paper",
                    "doi": "10.1000/real", "resolution": "resolved",
                    "evidence": "DOI in head", "duplicate_group": ["BBB_relabelled", "CCC_winner"],
                    "citable": True, "index_title": "Wrong Label", "index_doi": "10.1000/wrong",
                    "in_index": True, "mislabelled": True, "identity_corroborated": True,
                    "resolution_rule": "doi_in_head",
                    "text_quality": {"char_count": 900, "printable_ratio": 1.0,
                                     "form_feed_count": 0, "quality_flag": "stub"},
                },
                "CCC_winner": {
                    "content_sha256": "b" * 64, "canonical_title": "Real Paper",
                    "doi": "10.1000/real", "resolution": "resolved",
                    "evidence": "DOI in head", "duplicate_group": ["BBB_relabelled", "CCC_winner"],
                    "citable": True, "index_title": "Real Paper", "index_doi": "10.1000/real",
                    "in_index": True, "mislabelled": False, "identity_corroborated": True,
                    "resolution_rule": "doi_in_head",
                    "text_quality": {"char_count": 5000, "printable_ratio": 1.0,
                                     "form_feed_count": 0, "quality_flag": "ok"},
                },
                "DDD_ambiguous": {
                    "content_sha256": "d" * 64, "canonical_title": None, "doi": None,
                    "resolution": "UNRESOLVED", "evidence": "no rule fired",
                    "duplicate_group": ["DDD_ambiguous", "EEE_ambiguous"], "citable": False,
                    "index_title": "Candidate One", "index_doi": "10.1000/one",
                    "in_index": True, "mislabelled": None, "identity_corroborated": False,
                    "resolution_rule": "none",
                    "text_quality": {"char_count": 5000, "printable_ratio": 1.0,
                                     "form_feed_count": 0, "quality_flag": "ok"},
                },
                "EEE_ambiguous": {
                    "content_sha256": "d" * 64, "canonical_title": None, "doi": None,
                    "resolution": "UNRESOLVED", "evidence": "no rule fired",
                    "duplicate_group": ["DDD_ambiguous", "EEE_ambiguous"], "citable": False,
                    "index_title": "Candidate Two", "index_doi": "10.1000/two",
                    "in_index": True, "mislabelled": None, "identity_corroborated": False,
                    "resolution_rule": "none",
                    "text_quality": {"char_count": 5000, "printable_ratio": 1.0,
                                     "form_feed_count": 0, "quality_flag": "ok"},
                },
            },
        }), encoding="utf-8")

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_citable_document_passes(self) -> None:
        guard.assert_citable("AAA_good", map_path=self.fake)

    def test_unresolved_raises_and_lists_every_candidate(self) -> None:
        with self.assertRaises(guard.UncitableDocumentError) as ctx:
            guard.assert_citable("DDD_ambiguous", map_path=self.fake)
        message = str(ctx.exception)
        self.assertIn("DDD_ambiguous", message)
        self.assertIn("EEE_ambiguous", message)
        self.assertIn("Candidate Two", message)
        self.assertIn("<- requested", message)

    def test_unknown_document_raises(self) -> None:
        with self.assertRaises(guard.UnknownDocumentError):
            guard.assert_citable("ZZZ_nonexistent", map_path=self.fake)

    def test_canonical_citation_refuses_unresolved(self) -> None:
        with self.assertRaises(guard.UncitableDocumentError):
            guard.canonical_citation("EEE_ambiguous", map_path=self.fake)

    def test_canonical_citation_repairs_a_mislabelled_directory(self) -> None:
        cite = guard.canonical_citation("BBB_relabelled", map_path=self.fake)
        self.assertEqual(cite["canonical_title"], "Real Paper")
        self.assertEqual(cite["doi"], "10.1000/real")
        self.assertEqual(cite["directory_label"], "Wrong Label")
        self.assertTrue(cite["directory_label_is_wrong"])
        self.assertTrue(any("cite canonical_title" in w for w in cite["warnings"]))

    def test_strict_label_rejects_mislabelled(self) -> None:
        guard.assert_citable("BBB_relabelled", map_path=self.fake)  # lenient default
        with self.assertRaises(guard.MislabelledDocumentError):
            guard.assert_citable("BBB_relabelled", map_path=self.fake, strict_label=True)
        guard.assert_citable("CCC_winner", map_path=self.fake, strict_label=True)

    def test_require_quality_rejects_degraded_text(self) -> None:
        with self.assertRaises(guard.DegradedTextError):
            guard.assert_citable("BBB_relabelled", map_path=self.fake, require_quality=True)
        guard.assert_citable("AAA_good", map_path=self.fake, require_quality=True)

    def test_helpers(self) -> None:
        self.assertEqual(list(guard.iter_uncitable(map_path=self.fake)),
                         ["DDD_ambiguous", "EEE_ambiguous"])
        self.assertEqual(list(guard.iter_mislabelled(map_path=self.fake)), ["BBB_relabelled"])
        self.assertEqual(guard.duplicate_group_of("AAA_good", map_path=self.fake), [])
        self.assertEqual(guard.duplicate_group_of("CCC_winner", map_path=self.fake),
                         ["BBB_relabelled", "CCC_winner"])


class RealCorpusGuardTests(unittest.TestCase):
    """Spot checks against the real map, including the citations that motivated it."""

    def test_known_relabelled_directory_is_repaired(self) -> None:
        cite = guard.canonical_citation(
            "1276_Validation_of_a_building_energy_model_of_a_hydroponic_contai",
            map_path=MAP_PATH,
        )
        self.assertTrue(cite["directory_label_is_wrong"])
        self.assertIn("methodology for model-based greenhouse design",
                      cite["canonical_title"])

    def test_every_citable_document_has_a_title(self) -> None:
        data = json.loads(MAP_PATH.read_text(encoding="utf-8"))
        for slug, doc in data["documents"].items():
            if doc["citable"]:
                self.assertTrue(guard.canonical_citation(slug, map_path=MAP_PATH)
                                ["canonical_title"], slug)

    def test_uncitable_documents_all_raise(self) -> None:
        for slug in guard.iter_uncitable(map_path=MAP_PATH):
            with self.assertRaises(guard.UncitableDocumentError):
                guard.assert_citable(slug, map_path=MAP_PATH)


if __name__ == "__main__":
    unittest.main()
