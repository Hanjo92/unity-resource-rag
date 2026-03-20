from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipeline.gateway.capabilities.vision_layout_repair_analysis import (
    CAPABILITY_NAME,
    VisionLayoutRepairAnalysisRequest,
    run_vision_layout_repair_analysis,
    validate_vision_layout_repair_analysis_request,
)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _sample_reference_image(report_dir: Path) -> Path:
    path = report_dir / "reference.png"
    image = Image.new("RGB", (1, 1), (255, 255, 255))
    image.save(path)
    return path


class GatewayRepairAnalysisTests(unittest.TestCase):
    def test_validate_request_builds_typed_request(self) -> None:
        payload = {
            "capability": CAPABILITY_NAME,
            "providerPreference": ["gateway:auto"],
            "input": {
                "referenceImage": "/tmp/reference.png",
                "capturedImage": "/tmp/captured.png",
                "resolvedBlueprint": None,
                "screenName": "RewardPopup",
            },
            "outputSchema": "repair_analysis_v1",
            "options": {
                "detail": "high",
                "timeoutMs": 30000,
                "repairIterations": 1,
            },
        }

        request = validate_vision_layout_repair_analysis_request(payload)

        self.assertIsInstance(request, VisionLayoutRepairAnalysisRequest)
        self.assertEqual(request.capability, CAPABILITY_NAME)
        self.assertEqual(request.input.screenName, "RewardPopup")

    def test_run_analysis_returns_normalized_gateway_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            reference_path = _sample_reference_image(tmp_path)
            captured_path = reference_path
            report_path = tmp_path / "resolved-blueprint.json"
            _write_json(
                report_path,
                {
                    "screenName": "RewardPopup",
                    "root": {
                        "name": "RewardPopupCanvas",
                        "canvasScaler": {"referenceResolution": {"x": 1920, "y": 1080}},
                        "rect": {
                            "anchorMin": {"x": 0.5, "y": 0.5},
                            "anchorMax": {"x": 0.5, "y": 0.5},
                            "pivot": {"x": 0.5, "y": 0.5},
                            "anchoredPosition": {"x": 0, "y": 0},
                            "sizeDelta": {"x": 1920, "y": 1080},
                        },
                        "children": [],
                    },
                },
            )

            result = run_vision_layout_repair_analysis(
                {
                    "capability": CAPABILITY_NAME,
                    "providerPreference": ["gateway:auto"],
                    "input": {
                        "referenceImage": str(reference_path),
                        "capturedImage": str(captured_path),
                        "resolvedBlueprint": str(report_path),
                        "screenName": "RewardPopup",
                    },
                    "outputSchema": "repair_analysis_v1",
                    "options": {
                        "detail": "high",
                        "timeoutMs": 30000,
                        "repairIterations": 1,
                    },
                }
            )

        self.assertEqual(result["adapterId"], "verification_pipeline")
        self.assertEqual(result["authMode"], "analysis_only")
        self.assertEqual(result["providerFamily"], "local_verification")
        self.assertEqual(result["output"]["screenName"], "RewardPopup")
        self.assertIn("verificationReport", result["output"])
        self.assertIn("repairPatchCandidates", result["output"])
        self.assertEqual(result["trace"]["capability"], CAPABILITY_NAME)
        self.assertGreaterEqual(result["usage"]["inputArtifacts"], 3)


if __name__ == "__main__":
    unittest.main()
