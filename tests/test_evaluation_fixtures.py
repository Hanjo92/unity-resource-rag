from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipeline.evaluation.fixtures import load_benchmark_report, load_benchmark_suite
from pipeline.evaluation.models import (
    BenchmarkFixtureError,
    BenchmarkRegionFixture,
    BenchmarkRetrievalFixture,
    BenchmarkScreenFixture,
)
from pipeline.evaluation.report_models import BenchmarkRunReport, BenchmarkRunSummary


BENCHMARK_ROOT = REPO_ROOT / "examples" / "benchmarks" / "v0.3.0-reference-suite"


class EvaluationFixtureTests(unittest.TestCase):
    def test_load_benchmark_suite_resolves_relative_paths(self) -> None:
        suite = load_benchmark_suite(BENCHMARK_ROOT / "benchmark-manifest.json")

        self.assertEqual(suite.manifest.benchmark_name, "v0.3.0-reference-suite")
        self.assertEqual(len(suite.screens), 2)
        self.assertEqual(
            [screen.entry.screen_name for screen in suite.screens],
            ["reward_popup", "inventory_panel"],
        )
        self.assertEqual(
            suite.screens[0].reference_image_path,
            (BENCHMARK_ROOT / "reward-popup" / "reference.png").resolve(),
        )
        self.assertEqual(suite.screens[0].retrieval_fixture.screen_name, "reward_popup")
        self.assertEqual(suite.screens[1].thresholds.retrieval_top3_min, 0.9)

    def test_fixture_models_round_trip(self) -> None:
        retrieval_fixture = BenchmarkRetrievalFixture.from_dict(
            json.loads((BENCHMARK_ROOT / "reward-popup" / "retrieval-fixture.json").read_text(encoding="utf-8"))
        )
        screen_fixture = BenchmarkScreenFixture.from_dict(
            json.loads((BENCHMARK_ROOT / "inventory-panel" / "screen-fixture.json").read_text(encoding="utf-8"))
        )
        region = BenchmarkRegionFixture.from_dict(retrieval_fixture.to_dict()["regions"][0])

        self.assertEqual(retrieval_fixture.screen_name, "reward_popup")
        self.assertEqual(screen_fixture.expected_mismatch_classes, ("scale_mismatch", "composition_shift", "layout_mismatch"))
        self.assertEqual(region.region_id, "popup_frame")
        self.assertIn("gold trimmed", region.query_text)

    def test_report_model_round_trip(self) -> None:
        report = load_benchmark_report(BENCHMARK_ROOT / "sample-benchmark-report.json")

        self.assertIsInstance(report, BenchmarkRunReport)
        self.assertEqual(report.summary.screen_count, 2)
        self.assertEqual(report.summary.failed_screens, 0)
        self.assertEqual(report.results[0].screen_name, "reward_popup")
        self.assertEqual(report.results[1].status, "pass")

        summary = BenchmarkRunSummary.from_results(report.results)
        self.assertEqual(summary.to_dict(), report.summary.to_dict())

    def test_invalid_fixture_raises_clear_error(self) -> None:
        with self.assertRaises(BenchmarkFixtureError):
            BenchmarkRetrievalFixture.from_dict(
                {
                    "schemaVersion": "0.3.0",
                    "screenName": "broken_screen",
                    "regions": [
                        {
                            "regionType": "popup_frame",
                            "queryText": "missing region id",
                            "normalizedBounds": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
                            "preferredAssetKinds": ["sprite"],
                        }
                    ],
                }
            )

    def test_retrieval_fixture_rejects_invalid_repeat_count_and_planner_values(self) -> None:
        base_region = {
            "regionId": "broken_region",
            "regionType": "asset_query",
            "queryText": "broken",
            "normalizedBounds": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
            "preferredAssetKinds": ["sprite"],
            "repeatCount": 1,
            "interactionLevel": "static",
            "bindingPolicy": "require_confident",
        }

        invalid_cases = [
            ("repeatCount zero", {**base_region, "repeatCount": 0}),
            ("repeatCount negative", {**base_region, "repeatCount": -1}),
            ("repeatCount float", {**base_region, "repeatCount": 1.5}),
            ("repeatCount string", {**base_region, "repeatCount": "2"}),
            ("repeatCount bool", {**base_region, "repeatCount": True}),
            ("interactionLevel invalid", {**base_region, "interactionLevel": "hover"}),
            ("bindingPolicy invalid", {**base_region, "bindingPolicy": "hold_if_uncertain"}),
        ]

        for case_name, region in invalid_cases:
            with self.subTest(case_name=case_name):
                with self.assertRaises(BenchmarkFixtureError):
                    BenchmarkRetrievalFixture.from_dict(
                        {
                            "schemaVersion": "0.3.0",
                            "screenName": "broken_screen",
                            "regions": [region],
                        }
                    )


if __name__ == "__main__":
    unittest.main()
