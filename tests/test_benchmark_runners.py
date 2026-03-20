from __future__ import annotations

import contextlib
import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipeline.evaluation import evaluate_retrieval_benchmark, evaluate_screen_benchmark, load_benchmark_suite
from pipeline.evaluation.run_retrieval_benchmark import main as run_retrieval_main
from pipeline.evaluation.run_screen_benchmark import main as run_screen_main


BENCHMARK_ROOT = REPO_ROOT / "examples" / "benchmarks" / "v0.3.0-reference-suite"
MANIFEST_PATH = BENCHMARK_ROOT / "benchmark-manifest.json"
SAMPLE_REPORT_PATH = BENCHMARK_ROOT / "sample-benchmark-report.json"


class BenchmarkRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.suite = load_benchmark_suite(MANIFEST_PATH)

    def _write_json(self, path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _build_retrieval_payload(self, *, low_confidence_region_id: str | None = None) -> dict[str, object]:
        payload: dict[str, object] = {
            "schemaVersion": "0.3.0",
            "benchmarkName": self.suite.manifest.benchmark_name,
            "projectName": self.suite.manifest.project_name,
            "generatedAtUtc": "2026-03-20T00:00:00Z",
            "screens": [],
            "notes": ["Deterministic retrieval benchmark payload for tests."],
        }
        screens: list[dict[str, object]] = []
        for bundle in self.suite.screens:
            screen_payload: dict[str, object] = {
                "screenName": bundle.entry.screen_name,
                "notes": [f"Scored screen {bundle.entry.screen_name}."],
                "regions": [],
            }
            region_payloads: list[dict[str, object]] = []
            for region in bundle.retrieval_fixture.regions:
                floor = region.min_score if region.min_score is not None else 0.55
                if region.region_id == low_confidence_region_id:
                    candidate_score = round(max(0.0, floor - 0.1), 2)
                    binding_decision = "low_confidence_review"
                else:
                    candidate_score = round(min(0.99, floor + 0.05), 2)
                    binding_decision = "confident_match"

                top1 = round(min(0.99, bundle.thresholds.retrieval_top1_min + 0.08), 2)
                top3 = round(min(0.99, bundle.thresholds.retrieval_top3_min + 0.03), 2)
                region_payloads.append(
                    {
                        "regionId": region.region_id,
                        "top1HitRate": top1,
                        "top3HitRate": top3,
                        "selectedCandidateScore": candidate_score,
                        "bindingDecision": binding_decision,
                        "notes": [f"Region {region.region_id} evaluated deterministically."],
                    }
                )
            screen_payload["regions"] = region_payloads
            screens.append(screen_payload)
        payload["screens"] = screens
        return payload

    def _mutate_failure_report(self) -> dict[str, object]:
        report = copy.deepcopy(json.loads(SAMPLE_REPORT_PATH.read_text(encoding="utf-8")))
        report["results"][1]["repairIterations"] = 2
        report["results"][1]["status"] = "fail"
        report["summary"]["passedScreens"] = 1
        report["summary"]["failedScreens"] = 1
        return report

    def test_retrieval_runner_scores_payload_and_writes_scorecard(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            payload_path = temp_path / "retrieval-result.json"
            output_path = temp_path / "retrieval-scorecard.json"
            self._write_json(payload_path, self._build_retrieval_payload())

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = run_retrieval_main([str(MANIFEST_PATH), str(payload_path), "--output", str(output_path)])

            self.assertEqual(exit_code, 0)
            self.assertTrue(output_path.exists())
            printed = json.loads(stdout.getvalue())
            self.assertEqual(printed["output"], str(output_path))
            self.assertFalse(printed["hasErrors"])
            self.assertEqual(printed["screenCount"], 2)

            written = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(written["kind"], "retrieval_benchmark_scorecard")
            self.assertFalse(written["hasErrors"])
            self.assertEqual(written["summary"]["screenCount"], 2)
            self.assertEqual(written["summary"]["passedScreens"], 2)
            self.assertEqual([check["status"] for check in written["screenChecks"]], ["pass", "pass"])

    def test_retrieval_runner_flags_low_confidence_region(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            payload_path = temp_path / "retrieval-result.json"
            self._write_json(payload_path, self._build_retrieval_payload(low_confidence_region_id="reward_title"))

            output = evaluate_retrieval_benchmark(MANIFEST_PATH, payload_path)

            self.assertTrue(output["hasErrors"])
            self.assertEqual(output["summary"]["failedScreens"], 1)
            reward_screen = next(item for item in output["screenChecks"] if item["screenName"] == "reward_popup")
            reward_region = next(item for item in reward_screen["regionChecks"] if item["regionId"] == "reward_title")
            self.assertEqual(reward_region["status"], "fail")

    def test_screen_runner_scores_sample_report_and_writes_scorecard(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            output_path = temp_path / "screen-scorecard.json"

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = run_screen_main([str(MANIFEST_PATH), str(SAMPLE_REPORT_PATH), "--output", str(output_path)])

            self.assertEqual(exit_code, 0)
            self.assertTrue(output_path.exists())
            printed = json.loads(stdout.getvalue())
            self.assertEqual(printed["output"], str(output_path))
            self.assertFalse(printed["hasErrors"])
            self.assertEqual(printed["screenCount"], 2)

            written = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(written["kind"], "screen_benchmark_scorecard")
            self.assertFalse(written["hasErrors"])
            self.assertEqual(written["summary"]["screenCount"], 2)
            self.assertEqual(written["summary"]["passedScreens"], 2)
            self.assertEqual([check["status"] for check in written["screenChecks"]], ["pass", "pass"])

    def test_screen_runner_flags_threshold_breach(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            report_path = temp_path / "screen-report.json"
            self._write_json(report_path, self._mutate_failure_report())

            output = evaluate_screen_benchmark(MANIFEST_PATH, report_path)

            self.assertTrue(output["hasErrors"])
            self.assertEqual(output["summary"]["failedScreens"], 1)
            inventory_screen = next(item for item in output["screenChecks"] if item["screenName"] == "inventory_panel")
            self.assertEqual(inventory_screen["status"], "fail")


if __name__ == "__main__":
    unittest.main()
