#!/usr/bin/env python3
"""Unit tests for venue normalization, adapters, dedupe, and site metadata."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.config_loader import load_config
from scripts.fetch_papers import PaperFetcher
from scripts.generate_html import HTMLGenerator
from scripts.paper_processing import PaperProcessor
from scripts.reindex_papers import reindex_papers
from scripts.source_adapters import CrossrefAdapter, DBLPAdapter, OpenReviewAdapter


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
        "source_url": "https://arxiv.org/abs/2501.00001",
        "source": "ArXiv",
        "source_provider": "arxiv",
        "venue": "cs.LG",
        "comment": None,
        "journal_ref": None,
        "doi": None,
    }
    paper.update(overrides)
    return paper


class PaperProcessingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_config(PROJECT_ROOT / "config.yaml")
        cls.processor = PaperProcessor(cls.config)
        cls.fetcher = PaperFetcher(str(PROJECT_ROOT / "config.yaml"))

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

    def test_paper_type_detects_journal_conference_and_review(self):
        review = self.processor.enrich_paper(
            build_paper(
                title="A Survey of Reinforcement Learning for Wireless Networks",
                abstract="This survey reviews wireless scheduling and control.",
                comment="Published in IEEE JSAC",
            )
        )
        journal = self.processor.enrich_paper(
            build_paper(
                title="Resource Allocation in Wireless Networks",
                abstract="Wireless optimization for IoT.",
                comment="Published in IEEE JSAC",
            )
        )
        conference = self.processor.enrich_paper(
            build_paper(
                title="Adaptive RL for 6G",
                abstract="Wireless network control with reinforcement learning.",
                comment="Accepted to INFOCOM 2026",
            )
        )
        self.assertEqual(review["paper_type"], "review")
        self.assertEqual(journal["paper_type"], "journal")
        self.assertEqual(conference["paper_type"], "conference")

    def test_under_review_does_not_become_review_paper(self):
        paper = self.processor.enrich_paper(
            build_paper(
                title="Wireless Optimization with Graph Neural Networks",
                abstract="Graph neural networks for edge resource scheduling.",
                comment="Currently under review at IEEE TWC",
            )
        )
        self.assertNotEqual(paper["paper_type"], "review")
        self.assertEqual(paper["publication_status"], "submitted")

    def test_arxiv_and_crossref_merge_by_doi(self):
        arxiv_paper = self.processor.enrich_paper(
            build_paper(
                title="Wireless Federated Learning With Transformers",
                abstract="ArXiv preprint abstract.",
                authors=["Alice Smith"],
                primary_category="cs.NI",
                categories=["cs.NI", "cs.LG"],
                doi="10.1109/TWC.2025.1234567",
            )
        )
        crossref_paper = self.processor.enrich_paper(
            build_paper(
                id="doi:10.1109/TWC.2025.1234567",
                title="Wireless Federated Learning With Transformers",
                abstract="Official version abstract.",
                authors=["Alice Smith"],
                published="2025-03-01",
                updated="2025-03-02",
                categories=[],
                primary_category=None,
                pdf_url=None,
                arxiv_url=None,
                source="Crossref",
                source_provider="crossref",
                source_url="https://doi.org/10.1109/TWC.2025.1234567",
                venue_name="IEEE Transactions on Wireless Communications",
                venue_type="journal",
                venue_tier="core_comms",
                publication_status="published",
                doi="10.1109/TWC.2025.1234567",
                journal_ref="IEEE Transactions on Wireless Communications",
            )
        )

        merged = self.fetcher._deduplicate_papers([arxiv_paper, crossref_paper])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["source_provider"], "crossref")
        self.assertEqual(
            merged[0]["venue_name"], "IEEE Transactions on Wireless Communications"
        )
        self.assertEqual(merged[0]["doi"], "10.1109/twc.2025.1234567")
        self.assertTrue(merged[0]["arxiv_url"].startswith("https://arxiv.org/abs/"))

    def test_arxiv_and_dblp_merge_by_title_author_year(self):
        arxiv_paper = self.processor.enrich_paper(
            build_paper(
                title="Reinforcement Learning for INFOCOM Routing",
                authors=["Alice Smith"],
                abstract="ArXiv version.",
                primary_category="cs.NI",
                categories=["cs.NI"],
                published="2025-04-12",
                updated="2025-04-12",
            )
        )
        dblp_paper = self.processor.enrich_paper(
            build_paper(
                id="dblp:conf/infocom/Smith25",
                title="Reinforcement Learning for INFOCOM Routing",
                authors=["Alice Smith"],
                abstract=None,
                categories=[],
                primary_category=None,
                pdf_url=None,
                arxiv_url=None,
                source="DBLP",
                source_provider="dblp",
                source_url="https://dblp.org/rec/conf/infocom/Smith25.html",
                venue_name="IEEE INFOCOM",
                venue_type="conference",
                venue_tier="core_comms",
                publication_status="published",
                published="2025-01-01",
                updated="2025-01-01",
            )
        )

        merged = self.fetcher._deduplicate_papers([arxiv_paper, dblp_paper])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["venue_name"], "IEEE INFOCOM")
        self.assertEqual(merged[0]["source_provider"], "dblp")
        self.assertTrue(merged[0]["arxiv_url"].startswith("https://arxiv.org/abs/"))


class AdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_config(PROJECT_ROOT / "config.yaml")

    def test_crossref_adapter_normalizes_jsac_record(self):
        config = deepcopy(self.config)
        config["sources"]["adapters"]["crossref"] = {
            "enabled": True,
            "base_url": "https://api.crossref.org",
            "days_back": 365,
            "rows_per_request": 100,
            "max_pages": 1,
            "timeout": 30,
            "venues": ["IEEE Journal on Selected Areas in Communications"],
        }
        adapter = CrossrefAdapter(config)
        payload = {
            "message": {
                "items": [
                    {
                        "DOI": "10.1109/JSAC.2025.1234567",
                        "URL": "https://doi.org/10.1109/JSAC.2025.1234567",
                        "title": ["A Survey of Semantic Communications"],
                        "author": [{"given": "Alice", "family": "Chen"}],
                        "abstract": "<jats:p>Survey abstract.</jats:p>",
                        "container-title": ["IEEE Journal on Selected Areas in Communications"],
                        "short-container-title": ["IEEE JSAC"],
                        "issued": {"date-parts": [[2025, 3, 1]]},
                        "indexed": {"date-parts": [[2025, 3, 2]]},
                        "link": [
                            {
                                "URL": "https://example.org/jsac.pdf",
                                "content-type": "application/pdf",
                            }
                        ],
                    }
                ]
            }
        }
        with patch.object(adapter, "_request_json", return_value=payload):
            papers = adapter.fetch()
        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0]["venue_name"], "IEEE Journal on Selected Areas in Communications")
        self.assertEqual(papers[0]["venue_acronym"], "JSAC")
        self.assertEqual(papers[0]["doi"], "10.1109/jsac.2025.1234567")

    def test_dblp_adapter_normalizes_infocom_record(self):
        config = deepcopy(self.config)
        config["sources"]["adapters"]["dblp"] = {
            "enabled": True,
            "base_url": "https://dblp.org",
            "years_back": 2,
            "rows_per_request": 50,
            "max_pages": 1,
            "timeout": 30,
            "venues": ["IEEE INFOCOM"],
        }
        adapter = DBLPAdapter(config)
        payload = {
            "result": {
                "hits": {
                    "hit": [
                        {
                            "info": {
                                "title": "RL for Wireless Routing",
                                "venue": "IEEE INFOCOM",
                                "year": "2025",
                                "authors": {"author": [{"text": "Alice Smith"}]},
                                "doi": "10.1109/INFOCOM.2025.7654321",
                                "url": "https://dblp.org/rec/conf/infocom/Smith25.html",
                                "ee": ["https://doi.org/10.1109/INFOCOM.2025.7654321"],
                                "key": "conf/infocom/Smith25",
                            }
                        }
                    ]
                }
            }
        }
        with patch.object(adapter, "_request_json", return_value=payload):
            papers = adapter.fetch()
        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0]["venue_name"], "IEEE INFOCOM")
        self.assertEqual(papers[0]["venue_acronym"], "INFOCOM")
        self.assertEqual(papers[0]["publication_status"], "published")

    def test_openreview_adapter_normalizes_neurips_record(self):
        config = deepcopy(self.config)
        config["sources"]["adapters"]["openreview"] = {
            "enabled": True,
            "base_url": "https://api2.openreview.net",
            "years_back": 0,
            "limit_per_request": 50,
            "max_pages": 1,
            "timeout": 30,
            "venue_id_templates": {"NeurIPS": "NeurIPS.cc/{year}/Conference"},
            "venues": ["NeurIPS"],
        }
        adapter = OpenReviewAdapter(config, now=datetime(2025, 11, 1, tzinfo=timezone.utc))
        payload = {
            "notes": [
                {
                    "id": "or123",
                    "forum": "or123",
                    "pdate": 1730419200000,
                    "tmdate": 1730505600000,
                    "content": {
                        "title": {"value": "Transformer Routing for Wireless Systems"},
                        "abstract": {"value": "Abstract from OpenReview."},
                        "authors": {"value": ["Alice Smith", "Bob Lee"]},
                        "venue": {"value": "NeurIPS 2025"},
                        "venueid": {"value": "NeurIPS.cc/2025/Conference"},
                        "decision": {"value": "Accept (Poster)"},
                    },
                }
            ]
        }
        with patch.object(adapter, "_request_json", return_value=payload) as mocked_request:
            papers = adapter.fetch()
        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0]["venue_name"], "NeurIPS")
        self.assertEqual(papers[0]["source_provider"], "openreview")
        self.assertIn("openreview.net/forum", papers[0]["source_url"])
        mocked_request.assert_called_once_with(
            "/notes",
            params={
                "invitation": "NeurIPS.cc/2025/Conference/-/Submission",
                "details": "directReplies",
                "limit": 50,
                "offset": 0,
            },
            headers=None,
        )

    def test_openreview_adapter_retries_with_login_after_forbidden(self):
        config = deepcopy(self.config)
        config["sources"]["adapters"]["openreview"] = {
            "enabled": True,
            "base_url": "https://api2.openreview.net",
            "years_back": 0,
            "limit_per_request": 50,
            "max_pages": 1,
            "timeout": 30,
            "token_expires_in": 7200,
            "venue_id_templates": {"ICLR": "ICLR.cc/{year}/Conference"},
            "venues": ["ICLR"],
        }

        payload = {
            "notes": [
                {
                    "id": "or456",
                    "forum": "or456",
                    "content": {
                        "title": {"value": "Federated RL for Wireless Edge Systems"},
                        "abstract": {"value": "Abstract from OpenReview."},
                        "authors": {"value": ["Alice Smith"]},
                        "venue": {"value": "ICLR 2025"},
                        "venueid": {"value": "ICLR.cc/2025/Conference"},
                    },
                    "details": {
                        "directReplies": [
                            {
                                "content": {
                                    "decision": {"value": "Accept (Poster)"},
                                }
                            }
                        ]
                    },
                }
            ]
        }

        forbidden = requests.HTTPError(response=Mock(status_code=403))
        call_log = []

        def side_effect(path, **kwargs):
            call_log.append((path, kwargs))
            if len(call_log) == 1:
                raise forbidden
            if path == "/login":
                return {"token": "secret-token"}
            if path == "/notes":
                return payload
            raise AssertionError(f"Unexpected OpenReview path: {path}")

        with patch.dict(
            "os.environ",
            {"OPENREVIEW_USERNAME": "user@example.com", "OPENREVIEW_PASSWORD": "secret"},
            clear=False,
        ):
            adapter = OpenReviewAdapter(config, now=datetime(2025, 6, 1, tzinfo=timezone.utc))
            with patch.object(adapter, "_request_json", side_effect=side_effect):
                papers = adapter.fetch()

        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0]["venue_name"], "ICLR")
        self.assertEqual(papers[0]["publication_status"], "accepted")
        self.assertEqual(call_log[0][0], "/notes")
        self.assertEqual(call_log[0][1]["headers"], None)
        self.assertEqual(call_log[1][0], "/login")
        self.assertEqual(call_log[1][1]["json_body"]["expiresIn"], 7200)
        self.assertEqual(call_log[2][0], "/notes")
        self.assertEqual(
            call_log[2][1]["headers"],
            {"Authorization": "Bearer secret-token"},
        )


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
                    comment="Accepted to INFOCOM 2025",
                ),
                build_paper(
                    id="doi:10.1109/JSAC.2025.1234567",
                    title="A Survey of Semantic Communications",
                    abstract="Survey of semantic communications systems.",
                    authors=["Alice Chen"],
                    categories=[],
                    primary_category=None,
                    pdf_url=None,
                    arxiv_url=None,
                    source="Crossref",
                    source_provider="crossref",
                    source_url="https://doi.org/10.1109/JSAC.2025.1234567",
                    venue_name="IEEE Journal on Selected Areas in Communications",
                    venue_type="journal",
                    venue_tier="core_comms",
                    publication_status="published",
                    doi="10.1109/JSAC.2025.1234567",
                    published="2025-02-10",
                    updated="2025-02-10",
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
            self.assertIn("paper_type", reindexed[0])
            self.assertIn("venue_filter_value", reindexed[0])

            index_payload = json.loads(
                (output_dir / "data" / "index.json").read_text(encoding="utf-8")
            )
            self.assertIn("filters", index_payload)
            self.assertIn("topic_tags", index_payload["filters"])
            self.assertIn("paper_type", index_payload["filters"])
            self.assertIn("venues", index_payload["filters"])
            self.assertEqual(index_payload["defaults"]["interest_track"], "core_rl_comms")
            self.assertTrue((output_dir / "index.html").exists())


if __name__ == "__main__":
    unittest.main()
