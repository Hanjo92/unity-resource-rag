from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipeline.verification.build_repair_patch_candidates import build_repair_patch_candidates, main


def _sample_verification_report() -> dict[str, object]:
    return {
        "kind": "ui_verification_report",
        "screenName": "RewardPopup",
        "referenceImage": "/tmp/reference.png",
        "capturedImage": "/tmp/captured.png",
        "hasMeaningfulMismatch": True,
        "issues": [
            {
                "type": "composition_shift",
                "severity": "high",
                "title": "Top-level composition is shifted from the reference",
                "details": "Foreground center delta is (0.11, -0.05) with bbox IoU 0.41.",
                "likelyFixes": [
                    "Inspect parent container ownership before touching child offsets.",
                ],
                "suspectNodes": [
                    {
                        "id": "root_canvas",
                        "name": "RewardPopupCanvas",
                        "kind": "canvas",
                        "hierarchyPath": "RewardPopupCanvas",
                        "assetPath": None,
                        "overlapScore": 0.82,
                    },
                    {
                        "id": "content_root",
                        "name": "ContentRoot",
                        "kind": "container",
                        "hierarchyPath": "RewardPopupCanvas/ContentRoot",
                        "assetPath": None,
                        "overlapScore": 0.61,
                    },
                ],
            },
            {
                "type": "scale_mismatch",
                "severity": "medium",
                "title": "The built UI is scaled differently from the reference",
                "details": "Foreground size delta is (0.18, 0.14) relative to the reference.",
                "likelyFixes": [
                    "Check CanvasScaler and top-level sizing rules first.",
                ],
                "suspectNodes": [],
            },
            {
                "type": "style_asset_mismatch",
                "severity": "medium",
                "title": "The overall asset/style looks different even where geometry is similar",
                "details": "Foreground color delta is 48.2. Geometry is close enough that asset choice is suspect.",
                "likelyFixes": [
                    "Review sprite/prefab candidate selection before changing layout.",
                ],
                "suspectNodes": [
                    {
                        "id": "frame",
                        "name": "RewardFrame",
                        "kind": "image",
                        "hierarchyPath": "RewardPopupCanvas/Frame",
                        "assetPath": "Assets/UI/Popup/RewardFrame.png",
                        "overlapScore": 0.74,
                    }
                ],
            },
            {
                "type": "broad_visual_mismatch",
                "severity": "medium",
                "title": "A broad mismatch remains between the reference and the captured UI",
                "details": "Diff coverage is 0.21 with normalized mean error 0.16.",
                "likelyFixes": [
                    "Limit the next repair to the dominant incorrect region.",
                ],
                "suspectNodes": [],
            },
        ],
    }


class RepairPatchCandidateTests(unittest.TestCase):
    def test_build_repair_patch_candidates_maps_supported_issue_types(self) -> None:
        candidate_set = build_repair_patch_candidates(_sample_verification_report(), source_path="/tmp/report.json")

        self.assertEqual(candidate_set.kind, "ui_repair_patch_candidates")
        self.assertEqual(candidate_set.candidateCount, 3)
        self.assertEqual(candidate_set.screenName, "RewardPopup")
        self.assertEqual(len(candidate_set.ignoredIssues), 1)
        self.assertEqual(candidate_set.ignoredIssues[0]["issueType"], "broad_visual_mismatch")

        composition = candidate_set.candidates[0]
        self.assertEqual(composition.issueType, "composition_shift")
        self.assertEqual(composition.repairType, "realign_composition")
        self.assertEqual(composition.targetNodes[0].hierarchyPath, "RewardPopupCanvas")
        self.assertEqual(composition.patchSteps[0].action, "inspect_parent_chain")
        self.assertEqual(composition.patchSteps[0].target, "RewardPopupCanvas")
        self.assertIn("anchors", composition.boundedScope)

        scale = candidate_set.candidates[1]
        self.assertEqual(scale.issueType, "scale_mismatch")
        self.assertEqual(scale.repairType, "restore_scale_ownership")
        self.assertEqual(scale.patchSteps[0].action, "inspect_canvas_scaler")
        self.assertEqual(scale.patchSteps[0].target, "root")

        style = candidate_set.candidates[2]
        self.assertEqual(style.issueType, "style_asset_mismatch")
        self.assertEqual(style.repairType, "replace_style_asset")
        self.assertEqual(style.targetNodes[0].assetPath, "Assets/UI/Popup/RewardFrame.png")
        self.assertEqual(style.patchSteps[1].action, "prefer_project_asset")

    def test_main_writes_candidate_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            verification_path = tmp_path / "verification-report.json"
            output_path = tmp_path / "repair-patch-candidates.json"
            verification_path.write_text(json.dumps(_sample_verification_report()), encoding="utf-8")

            exit_code = main([str(verification_path), "--output", str(output_path)])

            self.assertEqual(exit_code, 0)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["kind"], "ui_repair_patch_candidates")
            self.assertEqual(payload["candidateCount"], 3)
            self.assertEqual(payload["screenName"], "RewardPopup")
            self.assertEqual(payload["sourceVerificationReport"], str(verification_path.resolve()))


if __name__ == "__main__":
    unittest.main()
