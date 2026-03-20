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

from pipeline.evaluation.publish_benchmark_gate_report import (
    GATE_REPORT_MARKDOWN_NAME,
    GATE_REPORT_NAME,
    RETRIEVAL_SCORECARD_NAME,
    SCREEN_SCORECARD_NAME,
    main as publish_gate_main,
    publish_benchmark_gate_report,
)


BENCHMARK_ROOT = REPO_ROOT / "examples" / "benchmarks" / "v0.3.0-reference-suite"
MANIFEST_PATH = BENCHMARK_ROOT / "benchmark-manifest.json"
SAMPLE_RETRIEVAL_PATH = BENCHMARK_ROOT / "sample-retrieval-result.json"
SAMPLE_REPORT_PATH = BENCHMARK_ROOT / "sample-benchmark-report.json"


class PublishBenchmarkGateReportTests(unittest.TestCase):
    def _write_json(self, path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def test_publish_main_writes_portable_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "baseline-artifacts"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = publish_gate_main(
                    [
                        str(MANIFEST_PATH),
                        str(SAMPLE_RETRIEVAL_PATH),
                        str(SAMPLE_REPORT_PATH),
                        "--output-dir",
                        str(output_dir),
                        "--generated-at",
                        "2026-03-20T00:00:00Z",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertTrue((output_dir / RETRIEVAL_SCORECARD_NAME).exists())
            self.assertTrue((output_dir / SCREEN_SCORECARD_NAME).exists())
            self.assertTrue((output_dir / GATE_REPORT_NAME).exists())
            self.assertTrue((output_dir / GATE_REPORT_MARKDOWN_NAME).exists())

            printed = json.loads(stdout.getvalue())
            self.assertEqual(printed["gateStatus"], "pass")
            self.assertEqual(printed["benchmarkName"], "v0.3.0-reference-suite")

            gate_report = json.loads((output_dir / GATE_REPORT_NAME).read_text(encoding="utf-8"))
            self.assertEqual(gate_report["kind"], "benchmark_gate_report")
            self.assertEqual(gate_report["gateStatus"], "pass")
            self.assertEqual(gate_report["artifacts"]["retrievalScorecard"], RETRIEVAL_SCORECARD_NAME)
            self.assertEqual(gate_report["artifacts"]["screenScorecard"], SCREEN_SCORECARD_NAME)
            self.assertEqual(gate_report["artifacts"]["summaryMarkdown"], GATE_REPORT_MARKDOWN_NAME)
            messages = " ".join(item["message"] for item in gate_report["followUps"])
            self.assertIn("sample benchmark artifacts", messages)

    def test_publish_report_marks_failed_retrieval_gate(self) -> None:
        payload = copy.deepcopy(json.loads(SAMPLE_RETRIEVAL_PATH.read_text(encoding="utf-8")))
        payload["screens"][0]["regions"][1]["selectedCandidateScore"] = 0.42
        payload["screens"][0]["regions"][1]["bindingDecision"] = "low_confidence_review"

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            retrieval_path = temp_path / "retrieval.json"
            output_dir = temp_path / "baseline-artifacts"
            self._write_json(retrieval_path, payload)

            gate_report = publish_benchmark_gate_report(
                MANIFEST_PATH,
                retrieval_path,
                SAMPLE_REPORT_PATH,
                output_dir,
                generated_at_utc="2026-03-20T00:00:00Z",
            )

            self.assertEqual(gate_report["gateStatus"], "fail")
            self.assertEqual(gate_report["gates"][0]["status"], "fail")
            self.assertEqual(gate_report["gates"][1]["status"], "pass")
            messages = " ".join(item["message"] for item in gate_report["followUps"])
            self.assertIn("reward_popup:reward_title", messages)


if __name__ == "__main__":
    unittest.main()
