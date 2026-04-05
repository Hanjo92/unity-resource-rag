from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipeline.workflows.build_mcp_handoff_bundle import build_bundle


class BuildMcpHandoffBundleTests(unittest.TestCase):
    def test_build_bundle_includes_catalog_access_guidance(self) -> None:
        blueprint_path = Path("/tmp/03-resolved-blueprint.json")
        binding_report_path = Path("/tmp/03-binding-report.json")
        blueprint = {
            "screenName": "RewardPopup",
            "root": {
                "name": "RewardPopupCanvas",
            },
        }
        binding_report = {
            "catalog": "/tmp/resource_catalog.jsonl",
            "hasErrors": True,
            "bindings": [
                {
                    "hierarchyPath": "RewardPopupCanvas/Body/RewardIcon",
                    "target": "asset",
                    "bindingState": "review_needed",
                    "bindingDecision": "low_confidence_review:0.4200<0.5500",
                    "query": {
                        "queryText": "reward badge icon",
                        "preferredKind": "sprite",
                    },
                    "chosenCandidate": {
                        "id": "reward-icon",
                        "name": "RewardIcon",
                        "path": "Assets/UI/RewardIcon.png",
                        "assetType": "Sprite",
                        "score": 0.42,
                    },
                    "alternatives": [
                        {
                            "id": "reward-icon-alt",
                            "name": "RewardIconAlt",
                            "path": "Assets/UI/RewardIconAlt.png",
                            "assetType": "Sprite",
                            "score": 0.40,
                        }
                    ],
                }
            ],
            "issues": [
                {
                    "message": "Could not resolve asset query for RewardPopupCanvas/Body/RewardIcon: low_confidence_review:0.4200<0.5500",
                }
            ],
        }

        bundle = build_bundle(
            blueprint_path=blueprint_path,
            blueprint=blueprint,
            binding_report_path=binding_report_path,
            binding_report=binding_report,
        )

        self.assertEqual(bundle["requests"]["inspectCatalog"]["customToolName"], "query_ui_asset_catalog")
        self.assertEqual(bundle["directToolFallback"]["inspectCatalog"]["tool"], "query_ui_asset_catalog")
        self.assertEqual(bundle["contracts"]["catalogQueryToolName"], "query_ui_asset_catalog")
        self.assertEqual(bundle["contracts"]["catalogResourceName"], "ui_asset_catalog")
        self.assertEqual(bundle["catalogAccess"]["catalogPath"], "/tmp/resource_catalog.jsonl")
        self.assertEqual(bundle["catalogAccess"]["resourceFallback"]["resource"], "ui_asset_catalog")
        self.assertEqual(bundle["bindingSummary"]["reviewTargetCount"], 1)
        self.assertEqual(bundle["artifacts"]["catalogPath"], "/tmp/resource_catalog.jsonl")
        self.assertIn("query_ui_asset_catalog", "\n".join(bundle["notes"]))
        self.assertEqual(bundle["catalogAccess"]["reviewTargets"][0]["queryText"], "reward badge icon")

    def test_build_bundle_keeps_catalog_request_without_binding_report(self) -> None:
        blueprint = {
            "screenName": "RewardPopup",
            "root": {
                "name": "RewardPopupCanvas",
            },
        }

        bundle = build_bundle(
            blueprint_path=Path("/tmp/03-resolved-blueprint.json"),
            blueprint=blueprint,
            binding_report_path=None,
            binding_report=None,
        )

        self.assertEqual(bundle["requests"]["inspectCatalog"]["customToolName"], "query_ui_asset_catalog")
        self.assertEqual(bundle["catalogAccess"]["catalogPath"], None)
        self.assertEqual(bundle["catalogAccess"]["reviewTargets"], [])


if __name__ == "__main__":
    unittest.main()
