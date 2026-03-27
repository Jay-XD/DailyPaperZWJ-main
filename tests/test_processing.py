#!/usr/bin/env python3
"""Unit tests for venue normalization, tagging, and site metadata generation."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.config_loader import load_config
from scripts.generate_html import HTMLGenerator
from scripts.paper_processing import PaperProcessor
from scripts.reindex_papers import reindex_papers


def build_paper(**overrides):
    paper = {
        "id": "2501.00001v1",
        "title": "Test Paper",
        "authors": ["Alice", "Bob"],
        "abstract": "Baseline abstract.",
        "published": "2025-01-15",
        "updated": "2025-01-15",
        "categories": ["cs.LG"],
        "primary_category": "cs.LG",
        "pdf_url": "https://arxiv.org/pdf/2501.00001.pdf",
        "arxiv_url": "https://arxiv.org/abs/2501.00001",
        "source": "ArXiv",
        "venue": "cs.LG",
        "comment": None,
        "journal_ref": None,
    }
    paper.update(overrides)
    return paper


class PaperProcessingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_config(PROJECT_ROOT / "config.yaml")
        cls.processor = PaperProcessor(cls.config)

    def test_infocom_acceptance_is_normalized(self):
        paper = self.processor.enrich_paper(
            build_paper(
                title="Reinforcement Learning for Wireless Resource Allocation",
                abstract="We study reinforcement learning for wireless scheduling in 6G systems.",
                primary_category="cs.NI",
                categories=["cs.NI", "cs.LG"],
                comment="Accepted to INFOCOM 2026",
            )
        )
        self.assertEqual(paper["venue_acronym"], "INFOCOM")
        self.assertEqual(paper["venue_name"], "IEEE INFOCOM")
        self.assertEqual(paper["publication_status"], "accepted")

    def test_journal_alias_and_submitted_status_are_preserved(self):
        paper = self.processor.enrich_paper(
            build_paper(
                title="Edge Scheduling with Reinforcement Learning",
                abstract="Resource allocation over mobile edge computing systems.",
                primary_category="cs.NI",
                categories=["cs.NI"],
                comment="Submitted to IEEE TWC",
            )
        )
        self.assertEqual(
            paper["venue_name"], "IEEE Transactions on Wireless Communications"
        )
        self.assertEqual(paper["publication_status"], "submitted")

    def test_iotj_publication_alias_works(self):
        paper = self.processor.enrich_paper(
            build_paper(
                title="IoT Federated Learning Over Wireless Networks",
                abstract="Federated learning over wireless IoT systems.",
                primary_category="cs.NI",
                categories=["cs.NI"],
                comment="Accepted for publication in IEEE Internet of Things Journal",
            )
        )
        self.assertEqual(paper["venue_acronym"], "IoTJ")
        self.assertEqual(paper["publication_status"], "accepted")

    def test_nips_and_globalcom_aliases_work(self):
        nips_paper = self.processor.enrich_paper(
            build_paper(
                title="LLM Planning",
                abstract="Large language model planning with transformer reasoning.",
                primary_category="cs.CL",
                categories=["cs.CL"],
                comment="NIPS 2025",
            )
        )
        globalcom_paper = self.processor.enrich_paper(
            build_paper(
                title="Beamforming for Wireless Networks",
                abstract="Beamforming for 6G wireless communication systems.",
                primary_category="eess.SP",
                categories=["eess.SP"],
                comment="GlobalCOM 2025",
            )
        )
        self.assertEqual(nips_paper["venue_name"], "NeurIPS")
        self.assertEqual(globalcom_paper["venue_name"], "IEEE Globecom")

    def test_noise_tokens_do_not_become_fake_venues(self):
        paper = self.processor.enrich_paper(
            build_paper(
                title="Generic Paper",
                comment="This work has been submitted to the IEEE for possible publication",
            )
        )
        self.assertIsNone(paper["venue_name"])
        self.assertEqual(paper["publication_status"], "submitted")

    def test_core_track_for_rl_and_communications(self):
        paper = self.processor.enrich_paper(
            build_paper(
                title="Deep Reinforcement Learning for Wireless Resource Allocation in 6G MEC",
                abstract=(
                    "We study reinforcement learning for wireless resource allocation, "
                    "mobile edge computing, and beamforming."
                ),
                primary_category="cs.NI",
                categories=["cs.NI", "cs.LG"],
            )
        )
        self.assertEqual(paper["interest_track"], "core_rl_comms")
        self.assertIn("Reinforcement Learning", paper["topic_tags"])
        self.assertIn("Wireless Communications", paper["topic_tags"])
        self.assertIn("MEC / Edge Cloud", paper["scenario_tags"])

    def test_secondary_track_for_pure_llm(self):
        paper = self.processor.enrich_paper(
            build_paper(
                title="A Large Language Model for Alignment",
                abstract="This large language model uses transformer reasoning for alignment.",
                primary_category="cs.CL",
                categories=["cs.CL"],
                comment="Accepted at NeurIPS 2025",
            )
        )
        self.assertEqual(paper["interest_track"], "secondary_llm_mm_nn")
        self.assertIn("LLM", paper["method_tags"])

    def test_video_generation_stays_out_of_core_track(self):
        paper = self.processor.enrich_paper(
            build_paper(
                title="Diffusion Policy for Text-to-Video Generation",
                abstract="A diffusion model for video generation with multimodal prompts.",
                primary_category="cs.CV",
                categories=["cs.CV"],
            )
        )
        self.assertNotEqual(paper["interest_track"], "core_rl_comms")

    def test_federated_edge_wireless_gets_multiple_tags(self):
        paper = self.processor.enrich_paper(
            build_paper(
                title="Federated Learning for Wireless Edge Intelligence",
                abstract=(
                    "Federated learning for wireless IoT and mobile edge computing "
                    "with beamforming."
                ),
                primary_category="cs.NI",
                categories=["cs.NI", "cs.LG"],
            )
        )
        self.assertIn("Federated Learning", paper["topic_tags"])
        self.assertIn("Edge Intelligence", paper["topic_tags"])
        self.assertIn("Wireless Communications", paper["topic_tags"])
        self.assertIn("IoT / IIoT", paper["scenario_tags"])


class SiteGenerationTests(unittest.TestCase):
    def test_reindex_and_site_metadata_generation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            data_path = temp_root / "papers.json"
            output_dir = temp_root / "docs"

            sample_papers = [
                build_paper(
                    id="2501.00001v1",
                    title="RL for Wireless Resource Allocation",
                    abstract="Reinforcement learning for wireless scheduling in 6G.",
                    primary_category="cs.NI",
                    categories=["cs.NI", "cs.LG"],
                    published="2025-01-15",
                ),
                build_paper(
                    id="2502.00002v1",
                    title="Large Language Model Compression",
                    abstract="A large language model with transformer adaptation.",
                    primary_category="cs.CL",
                    categories=["cs.CL"],
                    comment="Accepted at AAAI 2025",
                    published="2025-02-10",
                ),
            ]
            data_path.write_text(json.dumps(sample_papers, ensure_ascii=False), encoding="utf-8")

            reindex_papers(str(data_path), str(PROJECT_ROOT / "config.yaml"))

            generator = HTMLGenerator(
                data_path=str(data_path),
                output_dir=str(output_dir),
                config_path=str(PROJECT_ROOT / "config.yaml"),
            )
            generator.run()

            reindexed = json.loads(data_path.read_text(encoding="utf-8"))
            self.assertIn("topic_tags", reindexed[0])
            self.assertIn("interest_track", reindexed[0])
            self.assertIn("tags", reindexed[0])

            index_payload = json.loads(
                (output_dir / "data" / "index.json").read_text(encoding="utf-8")
            )
            self.assertIn("filters", index_payload)
            self.assertIn("topic_tags", index_payload["filters"])
            self.assertEqual(index_payload["defaults"]["interest_track"], "core_rl_comms")
            self.assertTrue((output_dir / "index.html").exists())


if __name__ == "__main__":
    unittest.main()
